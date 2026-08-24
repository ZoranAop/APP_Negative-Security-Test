#!/usr/bin/env python3
"""
publish_from_tokens.py — Two-phase publisher that keeps you from tripping the
login rate-limiter, then concurrently publishes moments.

Batch 1 (Section 5 of docs) learned the hard way:
    * post_moments.py logs in all 20 accounts concurrently → 12/20 get 429
    * We had to hand-roll a fix (sequential login + shared S3 upload cache)

This script formalises that recipe.

Phase 1 - Login
    Log in each account **sequentially** with a configurable delay
    (LOGIN_SPACING seconds) and exponential backoff on 429. Persist the resulting
    ``{email: token}`` map to ``--tokens-out`` (default result/tokens.json).

Phase 2 - Upload
    Enumerate every external image URL referenced in the moments CSV,
    download once, upload to S3 once (reusing tokens[anchor] for creds).

Phase 3 - Publish
    Round-robin (or by --plan) assign each row to one of the logged-in accounts,
    then fire posts concurrently (default 4 workers). Failures are recorded per row.

Reuse existing tokens
    If ``--tokens-in`` is given and contains valid tokens for every listed account,
    Phase 1 is skipped entirely.

CSV in
    content,visibility,room_id,image_urls,location_name,...

Accounts CSV
    Must contain columns recognised by ``config.py``
    (``邮箱|email|username`` and ``密码|password``). Optional ``昵称`` for reports.

Output
    result/publish_<timestamp>.csv   per-post results
    result/tokens.json               token map (unless --no-persist-tokens)
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import config  # noqa: E402
from utils import log_info, log_success, log_warn, log_error, ensure_utf8_stdout  # noqa: E402
from validation import validate_account_csv  # noqa: E402

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None


# ---------------------------------------------------------------------------
# tiny utils
# ---------------------------------------------------------------------------

def _ensure_utf8_stdout():
    ensure_utf8_stdout()


# ---------------------------------------------------------------------------
# phase 1: login
# ---------------------------------------------------------------------------

def _login_once(email: str, password: str, *, login_url: str, timeout: int) -> str | None:
    r = requests.post(
        login_url,
        json={
            "email": email.strip(),
            "password": password.strip(),
            "device_id": config.POST_DEVICE_ID,
            "device_name": config.POST_DEVICE_NAME,
        },
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    if r.status_code == 200 and r.json().get("code") == 0:
        return r.json()["data"]["token"]
    if r.status_code == 429:
        return "__429__"
    return None


def sequential_login(
    accounts: list[tuple[str, str]],
    *,
    login_url: str,
    timeout: int,
    spacing: float,
    max_retries: int = 6,
) -> dict[str, str]:
    """Login accounts sequentially with 429-aware backoff."""
    tokens: dict[str, str] = {}
    for i, (email, password) in enumerate(accounts, 1):
        got = None
        for attempt in range(max_retries):
            try:
                got = _login_once(email, password, login_url=login_url, timeout=timeout)
            except Exception as e:  # noqa: BLE001
                log_warn(f"  {email} attempt {attempt+1} exception: {e}")
                time.sleep(3)
                continue
            if got and got != "__429__":
                break
            if got == "__429__":
                delay = spacing * (2 ** attempt)
                log_warn(f"  {email} 429; sleeping {delay:.1f}s (retry {attempt+1})")
                time.sleep(delay)
                continue
            log_warn(f"  {email} login failed")
            got = None
            break
        if got and got != "__429__":
            tokens[email] = got
            log_success(f"  [{i}/{len(accounts)}] {email} OK")
        else:
            log_error(f"  [{i}/{len(accounts)}] {email} FAILED")
        time.sleep(spacing)
    return tokens


# ---------------------------------------------------------------------------
# phase 2: S3 upload
# ---------------------------------------------------------------------------

# Per-host Referer map for CDNs that reject cross-site / empty Referer.
# Extend via the POST_REFERER_MAP env var (JSON: {"host substring": "referer url"}).
_DEFAULT_REFERER_MAP: dict[str, str] = {
    "opennana.com": "https://opennana.com/",
    "yituyu.com": "https://www.yituyu.com/",
    "tuziyouwang.com": "http://tuziyouwang.com/",
    "aituitu.com": "https://ww.aituitu.com/",
    "open-prompts.com": "https://www.open-prompts.com/",
    "lovimg.com": "https://lovimg.com/",
    "twimg.com": "https://twitter.com/",
    "pbs.twimg.com": "https://twitter.com/",
    "xhscdn.com": "https://www.xiaohongshu.com/",
    "xiaohongshu.com": "https://www.xiaohongshu.com/",
}


def _referer_map() -> dict[str, str]:
    m = dict(_DEFAULT_REFERER_MAP)
    raw = os.getenv("POST_REFERER_MAP", "")
    if raw:
        try:
            m.update(json.loads(raw))
        except Exception:  # noqa: BLE001
            pass
    return m


def resolve_referer(image_url: str) -> str:
    """Pick a Referer matching the image host, so CDNs that check Referer
    (yituyu / tuzi / opennana / twimg …) don't reject the download.

    Falls back to the image's own scheme://host, which is the safest default
    for an unknown host (self-referential requests are rarely blocked)."""
    host = (urlsplit(image_url).hostname or "").lower()
    for needle, referer in _referer_map().items():
        if needle in host:
            return referer
    parts = urlsplit(image_url)
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}/"
    return "https://opennana.com/"


def get_s3_creds(token: str, *, upload_url: str, timeout: int) -> dict:
    r = requests.post(upload_url,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                      timeout=timeout)
    r.raise_for_status()
    j = r.json()
    if j.get("code") != 0:
        raise RuntimeError(f"upload creds fail: {j}")
    return j["data"]


# ---------------------------------------------------------------------------
# watermark crop: some sources burn a watermark into the bottom / bottom-right
# of the image. Crop off a bottom strip to remove it. Same treatment for:
#   - Xiaohongshu / 小红书  (xhscdn.com / xiaohongshu.com)
#   - backpackers.com.tw    (sa.bbkz.net / sa1.bbkz.net attachment photos)
#   - turismo.cc / 爱尤物   (img.youwushow.top — 底部烧录水印，含 xiuren/cosplay/youmi 等栏目)
#   POST_CROP_BOTTOM_HOSTS  comma list of host substrings to crop
#   POST_CROP_BOTTOM_PCT    fraction of height to crop off the bottom (default 0.08)
# Set POST_CROP_BOTTOM_HOSTS="" to disable entirely.
# ---------------------------------------------------------------------------

_DEFAULT_CROP_HOSTS = "xhscdn.com,xiaohongshu.com,bbkz.net,erv-nsa.gov.tw,youwushow.top"


def _crop_hosts() -> list[str]:
    raw = os.getenv("POST_CROP_BOTTOM_HOSTS", _DEFAULT_CROP_HOSTS)
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def _crop_bottom_pct() -> float:
    try:
        v = float(os.getenv("POST_CROP_BOTTOM_PCT", "0.08"))
    except ValueError:
        v = 0.08
    return min(max(v, 0.0), 0.5)  # clamp to a sane range


def _should_crop(image_url: str) -> bool:
    hosts = _crop_hosts()
    if not hosts:
        return False
    host = (urlsplit(image_url).hostname or "").lower()
    return any(h in host for h in hosts)


def _maybe_crop_bottom(local: Path, image_url: str) -> None:
    """If the image host is in the crop list, crop off the bottom strip
    (removing the burned-in bottom-right watermark) and overwrite `local`.

    Silently no-ops if Pillow is unavailable or the image can't be processed —
    the original file is left intact so the upload still proceeds."""
    if not _should_crop(image_url):
        return
    pct = _crop_bottom_pct()
    if pct <= 0:
        return
    try:
        from PIL import Image  # local import; optional dependency
    except ImportError:
        log_warn("  Pillow not installed; skipping watermark crop "
                 "(pip install pillow)")
        return
    try:
        with Image.open(local) as im:
            im.load()
            w, h = im.size
            new_h = int(round(h * (1.0 - pct)))
            if new_h <= 0 or new_h >= h:
                return
            cropped = im.crop((0, 0, w, new_h))
            fmt = (im.format or "").upper()
            save_kwargs = {}
            if fmt in ("JPEG", "JPG"):
                cropped = cropped.convert("RGB")
                save_kwargs = {"quality": 92}
            elif fmt == "WEBP":
                save_kwargs = {"quality": 92}
            cropped.save(local, format=im.format, **save_kwargs)
    except Exception as e:  # noqa: BLE001
        log_warn(f"  watermark crop skipped ({e}); using original")



def upload_url_to_s3(
    image_url: str,
    creds: dict,
    cache: dict[str, str],
    *,
    images_dir: Path,
) -> str:
    if image_url in cache:
        return cache[image_url]
    if boto3 is None:
        raise RuntimeError("boto3 not installed; run pip install boto3")
    url_hash = hashlib.md5(image_url.encode()).hexdigest()[:12]
    ext = ".jpg"
    for e in (".png", ".webp", ".gif"):
        if e in image_url.lower():
            ext = e
            break
    images_dir.mkdir(parents=True, exist_ok=True)
    local = images_dir / f"downloaded_{url_hash}{ext}"
    if not (local.exists() and local.stat().st_size > 0):
        referer = resolve_referer(image_url)
        # Some hosts (e.g. gov sites like erv-nsa.gov.tw) ship an incomplete TLS
        # chain; allow host-scoped verify=False via POST_NO_VERIFY_HOSTS.
        _nv = os.getenv("POST_NO_VERIFY_HOSTS", "erv-nsa.gov.tw")
        _host = (urlsplit(image_url).hostname or "").lower()
        _verify = not any(h.strip() and h.strip() in _host for h in _nv.split(","))
        if not _verify:
            try:
                requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                r = requests.get(image_url, timeout=30, verify=_verify,
                                 headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                                          "Chrome/120.0.0.0 Safari/537.36",
                                          "Referer": referer})
                if r.status_code == 200 and len(r.content) > 0:
                    local.write_bytes(r.content)
                    _maybe_crop_bottom(local, image_url)
                    break
                last_err = RuntimeError(f"HTTP {r.status_code} ({len(r.content)}B) for {image_url}")
            except Exception as e:  # noqa: BLE001
                last_err = e
            if attempt < 2:
                time.sleep(1)
        if not (local.exists() and local.stat().st_size > 0):
            raise RuntimeError(f"download failed (referer={referer}): {last_err}")
    # --- Image quality gate: skip thumbnails / too-small images ---
    # If the downloaded image is below minimum dimensions, treat it as unusable
    # (the post will fallback to text-only if all images fail this check).
    _min_w = int(os.getenv("POST_MIN_IMAGE_WIDTH", "400"))
    _min_h = int(os.getenv("POST_MIN_IMAGE_HEIGHT", "300"))
    if _min_w > 0 and _min_h > 0:
        try:
            from PIL import Image as _Img
            with _Img.open(local) as _im:
                _iw, _ih = _im.size
            if _iw < _min_w or _ih < _min_h:
                log_warn(f"  thumbnail skipped: {_iw}x{_ih} < {_min_w}x{_min_h} ({image_url[:60]})")
                local.unlink(missing_ok=True)
                raise RuntimeError(f"image too small: {_iw}x{_ih}")
        except ImportError:
            pass  # Pillow not installed; skip size check
        except RuntimeError:
            raise
        except Exception:
            pass  # Can't open image; proceed anyway
    s3 = boto3.client(
        "s3",
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds["session_token"],
        region_name=creds.get("region", "ap-northeast-1"),
    )
    date_path = time.strftime("%Y/%m/%d")
    key = f"square/original/{date_path}/{local.name}"
    ct = "image/jpeg" if ext == ".jpg" else f"image/{ext.strip('.')}"
    s3.upload_file(str(local), creds["bucket"], key,
                   ExtraArgs={"ContentType": ct,
                              "CacheControl": "public, max-age=31536000, immutable"})
    domain = creds.get("domain", "teststatic-x.tp-ex.com")
    aws_url = f"https://{domain}/{key}"
    cache[image_url] = aws_url
    return aws_url


# ---------------------------------------------------------------------------
# phase 3: publish
# ---------------------------------------------------------------------------

def send_moment(
    token: str, content: str, image_urls: list[str],
    *,
    api_url: str, timeout: int,
    max_retries: int = 3, backoff: float = 1.5,
) -> tuple[bool, str]:
    """Publish one moment with per-post retry + exponential backoff.

    Retries on network errors, HTTP 429/5xx, so a transient failure does not
    permanently drop a post. Business-level failures (code!=0) are not retried,
    except token expiry which returns a recognizable error string."""
    payload: dict[str, Any] = {"content": content, "visibility": 0}
    if image_urls:
        payload["media_info"] = {"type": "image", "images": image_urls}
    else:
        payload["media_info"] = {"type": "text"}
    last = ""
    for attempt in range(max_retries):
        try:
            r = requests.post(api_url, json=payload,
                              headers={"Authorization": f"Bearer {token}",
                                       "Content-Type": "application/json"},
                              timeout=timeout)
        except Exception as e:  # noqa: BLE001
            last = f"exc: {e}"
            time.sleep(backoff * (2 ** attempt))
            continue
        if r.status_code in (200, 201):
            j = r.json()
            if j.get("code") == 0:
                return True, str(j.get("data", {}).get("moment_id", ""))
            msg = j.get("msg", "")
            if "token_invalid" in msg or "expired" in msg.lower() or "session has expired" in msg.lower():
                return False, f"TOKEN_EXPIRED: {msg[:80]}"
            return False, f"biz-fail: {j}"  # 业务失败不重试
        if r.status_code == 429 or 500 <= r.status_code < 600:
            last = f"HTTP {r.status_code}: {r.text[:120]}"
            time.sleep(backoff * (2 ** attempt))
            continue
        # 4xx（非 429）：部分后端用 401 + code 10007/reason token_invalid 表示会话过期，
        # 需识别并触发外层重新登录重试，否则会被当作普通业务失败静默丢弃。
        try:
            _j = r.json()
        except Exception:  # noqa: BLE001
            _j = {}
        if (_j.get("code") == 10007
                or "token_invalid" in str(_j.get("data", {}).get("reason", ""))
                or "expired" in str(_j.get("msg", "")).lower()
                or "sign in again" in str(_j.get("msg", "")).lower()):
            return False, f"TOKEN_EXPIRED: {_j.get('msg', '')[:80]}"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"  # 4xx（非429）不重试
    return False, f"retry-exhausted: {last}"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def load_accounts(path: str) -> list[tuple[str, str, str]]:
    """Return list of (email, password, nickname)."""
    ok, err, email_field, pwd_field = validate_account_csv(path)
    if not ok:
        raise SystemExit(err)
    out: list[tuple[str, str, str]] = []
    with open(path, "r", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            e = (row.get(email_field) or "").strip()
            p = (row.get(pwd_field) or "").strip()
            n = (row.get("昵称") or row.get("nickname") or "").strip()
            if e and p:
                out.append((e, p, n))
    return out


def load_moments(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def unique_image_urls(rows: list[dict]) -> list[str]:
    urls: set[str] = set()
    for row in rows:
        for u in (row.get("image_urls") or "").split(","):
            u = u.strip()
            if u.startswith("http"):
                urls.add(u)
    return sorted(urls)


def main() -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="Two-phase safe publisher (pre-login + parallel publish)")
    ap.add_argument("--accounts-csv", required=True)
    ap.add_argument("--csv", required=True, help="moments CSV")
    ap.add_argument("--api-url", default=config.MOMENTS_API_URL)
    ap.add_argument("--login-url", default=config.LOGIN_URL)
    ap.add_argument("--upload-url", default=os.getenv("UPLOAD_CREDENTIALS_URL",
                                                     "https://api.xxai.com/file/upload/credentials"))
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=config.POST_REQUEST_TIMEOUT)
    ap.add_argument("--login-spacing", type=float,
                    default=float(os.getenv("LOGIN_SPACING", "2.5")),
                    help="seconds between sequential login attempts (default: 2.5)")
    ap.add_argument("--adaptive-login", action="store_true",
                    help="auto-scale login spacing & disable it below a small "
                         "account count; grows spacing as account count rises to avoid 429")
    ap.add_argument("--post-delay-min", type=float, default=0.0,
                    help="min random delay (s) before each publish, to de-burst (default 0)")
    ap.add_argument("--post-delay-max", type=float, default=0.0,
                    help="max random delay (s) before each publish, to de-burst (default 0)")
    ap.add_argument("--post-retries", type=int, default=3,
                    help="per-post publish retries on 429/5xx/network (default 3)")
    ap.add_argument("--record-dedupe", action="store_true",
                    help="after publish, write successfully-posted keys back to dedupe "
                         "files so they are never re-posted (uses _dedupe_key column)")
    ap.add_argument("--web3-dedupe-file", default="state/seen_web3.json")
    ap.add_argument("--img-dedupe-file", default="data/used_slugs.json")
    ap.add_argument("--tokens-in", default=None,
                    help="pre-existing tokens JSON; skip re-login when full coverage")
    ap.add_argument("--tokens-out", default="result/tokens.json",
                    help="where to persist tokens for later reuse")
    ap.add_argument("--no-persist-tokens", action="store_true")
    ap.add_argument("--output-csv", default="",
                    help="publish-result CSV (default: result/publish_<ts>.csv)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # ---- adaptive login spacing (optimize against 429) ----
    if args.adaptive_login:
        nacc = len(load_accounts(args.accounts_csv))
        if nacc <= 5:
            args.login_spacing = min(args.login_spacing, 1.0)
        elif nacc <= 12:
            args.login_spacing = max(args.login_spacing, 2.5)
        else:
            args.login_spacing = max(args.login_spacing, 3.5)
        log_info(f"[adaptive-login] {nacc} accounts -> login-spacing={args.login_spacing:.1f}s")

    accts = load_accounts(args.accounts_csv)
    rows = load_moments(args.csv)
    log_info(f"[Init] {len(accts)} accounts, {len(rows)} moments")

    # ---- Phase 1: login ----
    tokens: dict[str, str] = {}
    if args.tokens_in and Path(args.tokens_in).exists():
        tokens = json.loads(Path(args.tokens_in).read_text(encoding="utf-8"))
        missing = [a[0] for a in accts if a[0] not in tokens]
        if not missing:
            log_success(f"[Phase 1] reusing {len(tokens)} tokens from {args.tokens_in}")
        else:
            log_warn(f"[Phase 1] {args.tokens_in} missing {len(missing)}/{len(accts)}; will login them")
            tokens.update(sequential_login(
                [(e, p) for (e, p, _) in accts if e in missing],
                login_url=args.login_url,
                timeout=args.timeout,
                spacing=args.login_spacing,
            ))
    else:
        log_info(f"[Phase 1] sequential login of {len(accts)} accounts (spacing={args.login_spacing:.1f}s)")
        tokens = sequential_login(
            [(e, p) for (e, p, _) in accts],
            login_url=args.login_url,
            timeout=args.timeout,
            spacing=args.login_spacing,
        )
    if not args.no_persist_tokens:
        out_path = Path(args.tokens_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")
        log_success(f"[Phase 1] tokens persisted → {out_path}")

    if not tokens:
        log_error("no valid tokens; aborting")
        return 1

    if args.dry_run:
        log_info("[dry-run] stopping after login phase")
        return 0

    # ---- Phase 2: upload ----
    anchor_email = next(iter(tokens))
    creds = get_s3_creds(tokens[anchor_email], upload_url=args.upload_url, timeout=args.timeout)
    log_info(f"[Phase 2] S3 creds via {anchor_email} bucket={creds.get('bucket')}")

    all_urls = unique_image_urls(rows)
    # Filter out known watermarked image sources — these will be skipped and
    # their posts will fallback to text-only (content description without image).
    _wm_hosts_raw = os.getenv("POST_WATERMARK_SKIP_HOSTS",
                              "500px.com,dpreview.com,petapixel.com,gettyimages.com,"
                              "shutterstock.com,istockphoto.com,alamy.com,dreamstime.com,"
                              "depositphotos.com,123rf.com,stockphoto.com")
    _wm_hosts = [h.strip().lower() for h in _wm_hosts_raw.split(",") if h.strip()]
    watermark_skipped = set()
    if _wm_hosts:
        for u in all_urls:
            host = (urlsplit(u).hostname or "").lower()
            if any(wh in host for wh in _wm_hosts):
                watermark_skipped.add(u)
        if watermark_skipped:
            log_info(f"[Phase 2] skipping {len(watermark_skipped)} watermarked image(s) "
                     f"(hosts: {','.join(sorted(set((urlsplit(u).hostname or '') for u in watermark_skipped)))})")

    upload_urls = [u for u in all_urls if u not in watermark_skipped]
    log_info(f"[Phase 2] uploading {len(upload_urls)} unique urls "
             f"(concurrency={args.concurrency})")
    cache: dict[str, str] = {}
    img_dimensions: dict[str, tuple[int, int]] = {}  # url -> (width, height)
    _cache_lock = threading.Lock()
    _dim_lock = threading.Lock()

    def _upload_one(u: str) -> None:
        upload_url_to_s3(u, creds, cache, images_dir=Path("images"))
        if u in cache:
            with _cache_lock:
                s3_url = cache[u]
            url_hash = hashlib.md5(u.encode()).hexdigest()[:12]
            ext = ".jpg"
            for e in (".png", ".webp", ".gif"):
                if e in u.lower():
                    ext = e
                    break
            local = Path("images") / f"downloaded_{url_hash}{ext}"
            if local.exists():
                try:
                    from PIL import Image as _DimImg
                    with _DimImg.open(local) as _dim:
                        with _dim_lock:
                            img_dimensions[u] = _dim.size
                except Exception:
                    pass

    if len(upload_urls) <= 1:
        for u in upload_urls:
            try:
                _upload_one(u)
            except Exception as e:
                log_error(f"  ✗ upload {u[:70]}: {e}")
    else:
        done = 0
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(args.concurrency, len(upload_urls))
        ) as _pool:
            _futures = {_pool.submit(_upload_one, u): u for u in upload_urls}
            for _f in concurrent.futures.as_completed(_futures):
                u = _futures[_f]
                try:
                    _f.result()
                except Exception as e:
                    log_error(f"  ✗ upload {u[:70]}: {e}")
                done += 1
                if done % 20 == 0:
                    log_info(f"  uploaded ~{done}/{len(upload_urls)}")
    log_success(f"[Phase 2] cached {len(cache)}/{len(upload_urls)}")

    # ---- Phase 3: publish ----
    emails = [e for (e, _p, _n) in accts if e in tokens]
    if not emails:
        log_error("no accounts logged in; abort")
        return 1
    nickname_by = {e: n for (e, _p, n) in accts}

    tasks = []
    text_fallback_count = 0
    consistency_trimmed = 0

    # =========================================================================
    # Image Selection Rules (媒体内容规范)
    # =========================================================================
    # Image posts (media_info type=image):
    #   - Maximum: POST_MAX_IMAGES (default 9) images per post
    #   - Minimum: 1 image (if at least 1 passes all quality checks)
    #   - Best-effort: take as many qualifying images as available, up to max
    #   - If 0 images qualify → fallback to text-only post
    #   - Quality gates applied during upload:
    #       * Watermark domain skip (POST_WATERMARK_SKIP_HOSTS)
    #       * Minimum pixel dimensions (POST_MIN_IMAGE_WIDTH x HEIGHT)
    #   - Multi-image presentation rules:
    #       * Aspect ratio consistency: group by orientation, keep same type
    #       * Resolution consistency: prefer images of similar pixel size
    #       * Grid-friendly count: prefer 1/2/3/4/6/9 (trim 5→4, 7→6, 8→6)
    #       * Sort order: largest/highest-quality image first (hero image)
    #
    # Video posts (media_info type=video):
    #   - Exactly 1 video per post (handled by post_video.py)
    #   - Contains video_url + thumbnail_url
    #
    # Text posts (media_info type=text):
    #   - No media, content description only
    #   - Auto-fallback when no images pass quality checks
    # =========================================================================
    _max_images = int(os.getenv("POST_MAX_IMAGES", "9"))
    _ar_tolerance = float(os.getenv("POST_IMAGE_AR_TOLERANCE", "0.25"))
    # Grid-friendly counts: these numbers form clean visual grids in most feeds
    # 1(单图), 2(1×2), 4(2×2), 6(2×3), 9(3×3) — 小红书最佳宫格布局
    _grid_friendly = {1, 2, 4, 6, 9}
    _grid_enabled = os.getenv("POST_GRID_FRIENDLY", "true").lower() in ("1", "true", "yes")

    def _select_images(orig_urls: list[str]) -> list[str]:
        """Select best images for a post following media content rules.

        Pipeline:
         1. Filter to only successfully uploaded images (in cache)
         2. Aspect ratio consistency: group by orientation, keep same type
         3. Resolution consistency: remove outliers (>2x median resolution diff)
         4. Orientation-aware cap
         5. Sort: largest image first (hero/cover image)
         6. Grid-friendly count adjustment (trim to nearest clean grid number)
         7. Cap at POST_MAX_IMAGES (default 9)

        Returns S3 URLs ready for publishing."""
        # Step 1: get eligible URLs (uploaded successfully)
        eligible = [u for u in orig_urls if u in cache]
        if not eligible:
            return []

        # Step 2: aspect ratio consistency
        if len(eligible) > 1:
            eligible = _filter_consistent_ar(eligible)

        # Step 3: resolution consistency (remove outlier sizes)
        if len(eligible) > 1:
            eligible = _filter_consistent_resolution(eligible)

        # Step 4: orientation-aware max count
        # Portrait images take more vertical space; limit count for better layout
        if len(eligible) > 1:
            eligible = _cap_by_orientation(eligible)

        # Step 5: sort by resolution descending (hero image first)
        eligible = _sort_by_quality(eligible)

        # Step 6: grid-friendly count
        if _grid_enabled and len(eligible) > 1:
            eligible = _adjust_to_grid(eligible)

        # Step 7: cap to max images
        eligible = eligible[:_max_images]

        # Map to S3 URLs
        return [cache[u] for u in eligible if u in cache]

    def _filter_consistent_ar(urls: list[str]) -> list[str]:
        """Keep only images with similar aspect ratios for clean grid layout."""
        items = []
        for u in urls:
            if u in img_dimensions:
                w, h = img_dimensions[u]
                ar = w / h if h > 0 else 1.0
                items.append((u, ar))
            else:
                items.append((u, 1.33))  # assume landscape if unknown
        if len(items) <= 1:
            return urls

        # Group by orientation
        landscape = [(u, ar) for u, ar in items if ar > 1.1]
        portrait = [(u, ar) for u, ar in items if ar < 0.9]
        square = [(u, ar) for u, ar in items if 0.9 <= ar <= 1.1]

        # Pick largest group
        groups = sorted([landscape, portrait, square], key=len, reverse=True)
        best = groups[0]
        if not best:
            return urls

        # Within group, filter by median AR ± tolerance
        ars = sorted(ar for _, ar in best)
        median_ar = ars[len(ars) // 2]
        consistent = [u for u, ar in best
                      if abs(ar - median_ar) / max(median_ar, 0.01) <= _ar_tolerance]
        return consistent if consistent else [u for u, _ in best]

    def _filter_consistent_resolution(urls: list[str]) -> list[str]:
        """Remove images with drastically different resolution from the set.
        Prevents mixing a 1200px image with a 400px image in the same post."""
        if len(urls) <= 1:
            return urls
        sizes = []
        for u in urls:
            if u in img_dimensions:
                w, h = img_dimensions[u]
                sizes.append((u, w * h))  # total pixel count
            else:
                sizes.append((u, 800 * 600))  # assume medium if unknown
        if not sizes:
            return urls
        # Compute median resolution
        sorted_sizes = sorted(s for _, s in sizes)
        median_res = sorted_sizes[len(sorted_sizes) // 2]
        # Keep images within 3x of median (generous — just removes extreme outliers)
        min_res = median_res / 3.0
        filtered = [u for u, s in sizes if s >= min_res]
        return filtered if filtered else urls

    def _cap_by_orientation(urls: list[str]) -> list[str]:
        """Apply orientation-aware max image count for better feed layout.

        Portrait (vertical) images occupy more screen height, so displaying
        many in one post creates a cramped layout. Limits:
          - Portrait (AR < 0.9):  max 4 images (2x2 grid looks best)
          - Square (0.9~1.1):    max 9 images (3x3 grid)
          - Landscape (AR > 1.1): max 6 images (2x3 or 3x2 grid)

        Configurable via POST_MAX_PORTRAIT_IMAGES / POST_MAX_LANDSCAPE_IMAGES."""
        if len(urls) <= 1:
            return urls
        _max_portrait = int(os.getenv("POST_MAX_PORTRAIT_IMAGES", "4"))
        _max_landscape = int(os.getenv("POST_MAX_LANDSCAPE_IMAGES", "6"))
        _max_square = int(os.getenv("POST_MAX_SQUARE_IMAGES", "9"))

        # Determine dominant orientation of this set
        ars = []
        for u in urls:
            if u in img_dimensions:
                w, h = img_dimensions[u]
                ars.append(w / h if h > 0 else 1.0)
            else:
                ars.append(1.33)
        if not ars:
            return urls
        median_ar = sorted(ars)[len(ars) // 2]

        if median_ar < 0.9:  # portrait dominant
            return urls[:_max_portrait]
        elif median_ar > 1.1:  # landscape dominant
            return urls[:_max_landscape]
        else:  # square dominant
            return urls[:_max_square]

    def _adjust_to_grid(urls: list[str]) -> list[str]:
        """Adjust image count to a grid-friendly number for clean feed layout.
        Grid-friendly: 1, 2, 4, 6, 9 (optimized for XHS/square feed grids).
        Trims excess: 3→2, 5→4, 7→6, 8→6. Does NOT add images."""
        n = len(urls)
        if n in _grid_friendly or n <= 1:
            return urls
        # Find nearest smaller grid-friendly number
        targets = sorted(x for x in _grid_friendly if x < n)
        if targets:
            target = targets[-1]  # largest grid-friendly number below current
            return urls[:target]
        return urls

    def _sort_by_quality(urls: list[str]) -> list[str]:
        """Sort images by pixel count descending — best/largest image first (hero)."""
        def _px(u):
            if u in img_dimensions:
                w, h = img_dimensions[u]
                return w * h
            return 0
        return sorted(urls, key=_px, reverse=True)

    for i, row in enumerate(rows):
        email = emails[i % len(emails)]
        original = [u.strip() for u in (row.get("image_urls") or "").split(",") if u.strip()]

        # Apply image selection rules (graceful degradation):
        # original N images → quality/AR/resolution filter → grid adjust → final M images
        # If M < N: post publishes with fewer (but consistent) images
        # If M = 0: fallback to text-only post
        s3imgs = _select_images(original)

        # Track consistency trimming
        raw_eligible = [u for u in original if u in cache]
        if len(raw_eligible) > 1 and len(s3imgs) < len(raw_eligible):
            consistency_trimmed += 1

        # If all images were watermarked/failed/empty, post as text-only
        if original and not s3imgs:
            text_fallback_count += 1

        tasks.append({
            "csv_line": i + 1,
            "email": email,
            "nickname": nickname_by.get(email, ""),
            "content": row.get("content", ""),
            "s3_images": s3imgs,
            "_orig_img_count": len(original),
            "_final_img_count": len(s3imgs),
            "_source": row.get("_source", ""),
            "_lang": row.get("_lang", ""),
            "_scene": row.get("_scene", ""),
            "_dedupe_key": row.get("_dedupe_key", ""),
        })

    # Summary log: show degradation stats
    degraded = [(t["_orig_img_count"], t["_final_img_count"])
                for t in tasks if t["_orig_img_count"] > 0 and t["_final_img_count"] < t["_orig_img_count"]]
    if degraded:
        log_info(f"[Phase 3] {len(degraded)} post(s) image count reduced for quality "
                 f"(e.g. {degraded[0][0]}→{degraded[0][1]} imgs)")
    if consistency_trimmed:
        log_info(f"[Phase 3] {consistency_trimmed} post(s) trimmed for dimension consistency")
    if text_fallback_count:
        log_info(f"[Phase 3] {text_fallback_count} post(s) will be text-only "
                 f"(watermarked/failed images skipped, using content description)")
    log_info(f"[Phase 3] publishing {len(tasks)} with concurrency={args.concurrency}")

    # Build password map for token refresh
    pwd_map: dict[str, str] = {e: p for (e, p, _) in accts}
    tok_lock = threading.Lock()
    refresh_stats: dict[str, int] = {"count": 0}

    def worker(t):
        email = t["email"]
        # de-burst: small random pre-post delay so posts don't fire in a rigid burst
        if args.post_delay_max > 0:
            import random as _r
            time.sleep(_r.uniform(args.post_delay_min, args.post_delay_max))
        ok, info = send_moment(tokens[email], t["content"], t["s3_images"],
                                api_url=args.api_url, timeout=args.timeout,
                                max_retries=args.post_retries)
        # Token expired: re-login and retry once
        if not ok and info.startswith("TOKEN_EXPIRED") and email in pwd_map:
            new_tok = _login_once(email, pwd_map[email],
                                  login_url=args.login_url, timeout=args.timeout)
            if new_tok and new_tok != "__429__":
                with tok_lock:
                    tokens[email] = new_tok
                    refresh_stats["count"] += 1
                    if not args.no_persist_tokens:
                        try:
                            Path(args.tokens_out).parent.mkdir(parents=True, exist_ok=True)
                            Path(args.tokens_out).write_text(
                                json.dumps(tokens, ensure_ascii=False, indent=2),
                                encoding="utf-8")
                        except Exception:
                            pass
                ok, info = send_moment(new_tok, t["content"], t["s3_images"],
                                        api_url=args.api_url, timeout=args.timeout,
                                        max_retries=1)
                if ok:
                    info = f"{info} (token-refreshed)"
        return {**t, "success": ok, "info": info}

    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(worker, t) for t in tasks]
        for i, f in enumerate(concurrent.futures.as_completed(futs), 1):
            r = f.result()
            results.append(r)
            tag = "\u2713" if r["success"] else "\u2717"
            n_img = len(r.get("s3_images") or [])
            if n_img == 0:
                mode = "[text]"
            else:
                mode = f"[{n_img}img]"
            log_info(f"  {tag} [{i}/{len(tasks)}] {r['nickname'] or r['email']} "
                     f"lang={r.get('_lang','')} src={r.get('_source','')} "
                     f"{mode} {r['info'][:60]}")

    ok = sum(1 for r in results if r["success"])
    log_success(f"[Done] {ok}/{len(results)}")

    if refresh_stats["count"]:
        log_info(f"[Token] refreshed {refresh_stats['count']} expired token(s) during publish")
        if not args.no_persist_tokens:
            out_path = Path(args.tokens_out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")
            log_info(f"[Token] updated tokens persisted → {out_path}")

    out_path = Path(args.output_csv or f"result/publish_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["csv_line", "email", "nickname", "_source", "_lang", "_scene",
              "success", "moment_id_or_err", "content"]
    with out_path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(fields)
        for r in sorted(results, key=lambda x: x["csv_line"]):
            w.writerow([r["csv_line"], r["email"], r["nickname"], r.get("_source",""),
                        r.get("_lang",""), r.get("_scene",""),
                        r["success"], r["info"], r["content"]])
    log_success(f"[Report] → {out_path}")

    # ---- dedupe write-back: only successfully-posted content is recorded ----
    if args.record_dedupe:
        _record_dedupe(
            [r for r in results if r["success"]],
            web3_file=args.web3_dedupe_file,
            img_file=args.img_dedupe_file,
        )
    return 0


def _record_dedupe(success_rows: list[dict], *, web3_file: str, img_file: str) -> None:
    """Write successfully-posted keys back to the dedupe ledgers so future runs
    skip them. Reads `_dedupe_key` formatted as ``web3:<norm-title>`` or
    ``img:<slug-or-url>`` (produced by assemble_mixed.py)."""
    import re as _re
    web3_keys, img_keys = set(), set()
    for r in success_rows:
        dk = (r.get("_dedupe_key") or "").strip()
        if dk.startswith("web3:"):
            # normalize the title the same way fetch_web3._norm does
            t = dk[len("web3:"):]
            norm = _re.sub(r"[\s\u3000\-—–_、，。！？；：·]+", "", t).lower()
            if norm:
                web3_keys.add(norm)
        elif dk.startswith("img:"):
            v = dk[len("img:"):]
            if v:
                img_keys.add(v)

    def _merge(path_str: str, new_keys: set, wrapper_key: str | None = None):
        if not new_keys:
            return
        import tempfile as _tmp
        p = Path(path_str)
        p.parent.mkdir(parents=True, exist_ok=True)
        existing: list = []
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                existing = data.get(wrapper_key, []) if (wrapper_key and isinstance(data, dict)) else data
            except Exception:  # noqa: BLE001
                existing = []
        merged = sorted(set(existing) | new_keys)
        out = {wrapper_key: merged} if wrapper_key else merged
        # Atomic write: temp file + rename to avoid corruption on crash
        fd, tmp_path = _tmp.mkstemp(suffix=".json", dir=str(p.parent), prefix=".dedupe_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as _f:
                json.dump(out, _f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(p))
        except Exception:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
            raise
        log_success(f"[dedupe] +{len(new_keys)} keys → {p} (total {len(merged)})")

    _merge(web3_file, web3_keys)
    _merge(img_file, img_keys)


if __name__ == "__main__":
    sys.exit(main())
