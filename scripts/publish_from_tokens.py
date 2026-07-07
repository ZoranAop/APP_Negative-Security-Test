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
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import config  # noqa: E402
from utils import log_info, log_success, log_warn, log_error  # noqa: E402
from validation import validate_account_csv  # noqa: E402

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None


# ---------------------------------------------------------------------------
# tiny utils
# ---------------------------------------------------------------------------

def _ensure_utf8_stdout():
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


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
#   POST_CROP_BOTTOM_HOSTS  comma list of host substrings to crop
#   POST_CROP_BOTTOM_PCT    fraction of height to crop off the bottom (default 0.08)
# Set POST_CROP_BOTTOM_HOSTS="" to disable entirely.
# ---------------------------------------------------------------------------

_DEFAULT_CROP_HOSTS = "xhscdn.com,xiaohongshu.com,bbkz.net,erv-nsa.gov.tw"


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
) -> tuple[bool, str]:
    payload: dict[str, Any] = {"content": content, "visibility": 0}
    if image_urls:
        payload["media_info"] = {"type": "image", "images": image_urls}
    else:
        payload["media_info"] = {"type": "text"}
    r = requests.post(api_url, json=payload,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                      timeout=timeout)
    if r.status_code in (200, 201):
        j = r.json()
        if j.get("code") == 0:
            return True, str(j.get("data", {}).get("moment_id", ""))
        return False, f"biz-fail: {j}"
    return False, f"HTTP {r.status_code}: {r.text[:200]}"


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
                                                     "https://testapi-x.tp-ex.com/file/upload/credentials"))
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=config.POST_REQUEST_TIMEOUT)
    ap.add_argument("--login-spacing", type=float,
                    default=float(os.getenv("LOGIN_SPACING", "2.5")),
                    help="seconds between sequential login attempts (default: 2.5)")
    ap.add_argument("--tokens-in", default=None,
                    help="pre-existing tokens JSON; skip re-login when full coverage")
    ap.add_argument("--tokens-out", default="result/tokens.json",
                    help="where to persist tokens for later reuse")
    ap.add_argument("--no-persist-tokens", action="store_true")
    ap.add_argument("--output-csv", default="",
                    help="publish-result CSV (default: result/publish_<ts>.csv)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

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
    log_info(f"[Phase 2] uploading {len(all_urls)} unique urls")
    cache: dict[str, str] = {}
    for i, u in enumerate(all_urls, 1):
        try:
            upload_url_to_s3(u, creds, cache, images_dir=Path("images"))
            if i % 20 == 0:
                log_info(f"  uploaded {i}/{len(all_urls)}")
        except Exception as e:  # noqa: BLE001
            log_error(f"  ✗ upload {u[:70]}: {e}")
    log_success(f"[Phase 2] cached {len(cache)}/{len(all_urls)}")

    # ---- Phase 3: publish ----
    emails = [e for (e, _p, _n) in accts if e in tokens]
    if not emails:
        log_error("no accounts logged in; abort")
        return 1
    nickname_by = {e: n for (e, _p, n) in accts}

    tasks = []
    for i, row in enumerate(rows):
        email = emails[i % len(emails)]
        original = [u.strip() for u in (row.get("image_urls") or "").split(",") if u.strip()]
        s3imgs = [cache[u] for u in original if u in cache]
        tasks.append({
            "csv_line": i + 1,
            "email": email,
            "nickname": nickname_by.get(email, ""),
            "content": row.get("content", ""),
            "s3_images": s3imgs,
            "_source": row.get("_source", ""),
            "_lang": row.get("_lang", ""),
            "_scene": row.get("_scene", ""),
        })
    log_info(f"[Phase 3] publishing {len(tasks)} with concurrency={args.concurrency}")

    def worker(t):
        ok, info = send_moment(tokens[t["email"]], t["content"], t["s3_images"],
                               api_url=args.api_url, timeout=args.timeout)
        return {**t, "success": ok, "info": info}

    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(worker, t) for t in tasks]
        for i, f in enumerate(concurrent.futures.as_completed(futs), 1):
            r = f.result()
            results.append(r)
            tag = "✓" if r["success"] else "✗"
            log_info(f"  {tag} [{i}/{len(tasks)}] {r['nickname'] or r['email']} "
                     f"lang={r.get('_lang','')} src={r.get('_source','')} {r['info'][:70]}")

    ok = sum(1 for r in results if r["success"])
    log_success(f"[Done] {ok}/{len(results)}")

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
