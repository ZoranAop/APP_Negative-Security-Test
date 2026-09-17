#!/usr/bin/env python3
"""
run_pexels_video.py — Pexels video publisher.

Flow:
    1. Discover Pexels video URLs (known IDs or Pexels search page scrape)
    2. Dedupe against data/used_pexels_video_ids.json
    3. Pick accounts from CSV by nickname category (en/jp/cn/random/auto)
    4. Sequential login with 429 backoff → result/tokens.json
    5. Get S3 creds (anchor token)
    6. For each video: download MP4 + thumbnail → upload S3 → post moment
    7. Persist used video IDs + publish report CSV

Usage:
    py -3 scripts/run_pexels_video.py --theme cambodia --nick-filter en --count 10 --yes
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import random
from pathlib import Path
from datetime import datetime

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import config  # noqa: E402

try:
    import boto3
except ImportError:
    print("[FATAL] boto3 not installed. Run: py -3 -m pip install boto3", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Known valid Pexels video IDs by theme (avoid re-scraping Cloudflare)
# ---------------------------------------------------------------------------
KNOWN_VIDEO_IDS = {
    "cambodia": [30170009, 29383140, 29247677, 29247695, 30170008,
                 29074122, 29383143, 29089383, 32927000, 30797834],
    "tokyo": [854140, 7677258, 8926451, 9915238],
    "korea": [32927000, 29191440, 4684166, 7677258, 8926451, 9678901, 9915238],
    "india": [32927000, 4684166, 8926451, 9678901, 9915238],
    "southeast-asia": [29074122, 29104184, 29228800, 29247803, 29383140,
                       29458118, 31136459, 30570498, 30797834, 4030306],
}

# ---------------------------------------------------------------------------
# Caption banks — traveler voice, short, no AI-flavor
# ---------------------------------------------------------------------------
CAPTION_BANKS = {
    "cambodia": [
        "Wandering through old Cambodia. The air is thick with history, every stone remembers.",
        "Angkor from above. 1,000 years of empire, still standing. The scale is humbling.",
        "Breakfast at a little Cambodian cafe. Strong coffee, warm bread, slow morning.",
        "A quiet corner in Phnom Penh. The kind of stop you don't plan, just live in for a while.",
        "Cambodia in 2025. Markets, temples, the river. It moves at its own pace, and that's the point.",
        "Angkor Wat at dawn. You don't need words. You just stand there and let it in.",
        "Drone run over the old capital. The geometry of it is still unreal, nine centuries on.",
        "Lost in the temple corridors. The carvings tell stories nobody's written down.",
        "Evening walk through the lanes. Lanterns coming up, the heat finally breaking.",
        "The 12th century built this. And it still stops you mid-stride.",
    ],
    "tokyo": [
        "Shinjuku at night. The neon never really turns off, and tonight it's my turn to disappear into it.",
        "Quiet morning walk through the old quarter. Tokyo hides the best moments in its smallest alleys.",
        "Caught the sky over Shibuya just as it turned gold. Tokyo rewards you for looking up.",
        "Ramen at 1am. The right bowl after a long day tastes better than you'd expect.",
        "The trains run on time here, but the city itself runs on a rhythm only Tokyo knows.",
        "A single maple leaf on the wet pavement. Autumn in Tokyo arrives quietly, then all at once.",
        "Surrendered to the crowd on the crossing. Just another face in the beautiful chaos.",
        "A bench, a river, and the whole city humming beyond the water. Tokyo is easier to love from here.",
        "Neon, rain, and the smell of warm bread. Tokyo in the rain has a mood you can't plan for.",
        "Last light over Tokyo Tower. The city glows from within, even before the dark.",
    ],
    "korea": [
        "Seoul, late afternoon. The city slows down just enough to let you breathe.",
        "A quiet street in Hongdae. The kind of moment you don't need to photograph, just remember.",
        "Busan at dusk. The harbour lights come up one by one, and the whole bay turns gold.",
        "A tiny cafe in Incheon, steam rising off the cup, rain on the window. Perfect.",
        "Walking through Myeongdong after the crowds thin out. The neon looks better at night.",
        "The Han River on a Sunday. People bring picnic blankets and let the afternoon just pass.",
        "A hanok district in the morning. The silence here feels different, older.",
        "The night market in Jeonju. Steam, smoke, and a thousand small fires.",
        "Gyeongju's stone pagodas. A thousand years of stillness, and it's still standing.",
        "The ferry to Nampo-dong. The sea turns the colour of milk at this hour.",
    ],
    "india": [
        "Jaipur at golden hour. The pink city earns its name every evening.",
        "The Ganges at dawn. A hundred boats, a million small prayers on the water.",
        "Delhi's own chaos, its own rhythm. You stop fighting it after a while.",
        "A quiet street in Udaipur. The lake is just a wall away, and the whole place breathes.",
        "The road through the Deccan. Open sky, old stone, and nowhere to rush to.",
        "Mumbai's Marine Drive at night. The Arabian Sea and the city, in one long breath.",
        "The spice market in Varanasi. You can taste the colour before the smell reaches you.",
        "A train through the Aravalli hills. No schedule, no hurry, just the landscape sliding by.",
        "The backwaters of Kerala. Palm trees bending over water that seems to go on forever.",
        "Amritsar at dawn. The temple bells start before the light, and the whole city listens.",
    ],
    "southeast-asia": [
        "Bangkok's Grand Palace at sunrise. The whole city holds its breath, then starts all at once.",
        "A boat on the Chao Phraya, the bridge lights coming up one by one. Bangkok rewards the patient.",
        "The street food of Singapore's night market is its own language. You just have to listen.",
        "A coconut by the water in Bali. The kind of stop where time stops with you.",
        "The rice terraces of Vietnam at dawn. Water in every field, gold in every layer.",
        "Malacca's old quarter. The Dutch built it, the centuries kept it, and it still works beautifully.",
        "A temple deep in the jungle. The stones are older than the country's name.",
        "Phuket's harbour at sunset. The boats turn into a thousand small lights.",
        "The road through Cambodia's highlands. Red earth, green water, and no hurry at all.",
        "A night train into the hills of Laos. The dark outside the window does the talking.",
    ],
    "japan": [
        "The temple gates open before the sun. A single light on the path, and the whole mountain is awake.",
        "Osaka's Dotonbori at night. The neon hums; you stop counting streets after a while.",
        "A narrow lane in Kyoto. The moss is doing the talking, and it's been doing it for 400 years.",
        "Hokkaido in winter. The snow is so clean it looks like the world just reset.",
        "A vending machine on a mountain road. No one's around, but the light is on for you.",
        "Tokyo's last train. The city empties its streets in twenty minutes, then falls asleep.",
        "Nara's deer are waiting. They've been waiting a lot longer than you have.",
        "The coast from a fishing boat. Japan's edge is wider and quieter than you'd expect.",
        "A shrine in the snow. The stone fox has seen ten thousand winters; this one is just a Tuesday.",
        "Ryukyu's coral reefs from above. The water here has a colour I don't have a word for.",
    ],
}

# ---------------------------------------------------------------------------
# Pexels URL discovery
# ---------------------------------------------------------------------------

def _pexels_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.pexels.com/",
        "Accept-Language": "en-US,en",
    }


def discover_pexels_videos(theme: str, limit: int = 10) -> list[dict]:
    """Return list of {"vid": int, "video_url": str}.

    Uses KNOWN_VIDEO_IDS if available, otherwise scrapes the Pexels search page.
    Each ID is verified via the download redirect endpoint.
    """
    candidates = KNOWN_VIDEO_IDS.get(theme, [])

    # If no known IDs, try scraping the search page
    if not candidates:
        try:
            r = requests.get(
                f"https://www.pexels.com/zh-cn/search/videos/{theme.replace(' ', '%20')}/",
                timeout=30, verify=False, headers=_pexels_headers()
            )
            ids = list(dict.fromkeys(re.findall(r'/video/(\d+)/', r.text)))
            candidates = [int(v) for v in ids[:limit * 3]]
        except Exception as e:
            print(f"  [WARN] Pexels search scrape failed: {e}", file=sys.stderr)

    if not candidates:
        return []

    # Verify each ID via download redirect
    results = []
    for vid in candidates[:limit * 3]:
        if len(results) >= limit:
            break
        try:
            dr = requests.get(
                f"https://www.pexels.com/download/video/{vid}/",
                timeout=15, allow_redirects=False, verify=False,
                headers=_pexels_headers()
            )
            loc = dr.headers.get("Location", "")
            if "video-files" in loc:
                results.append({"vid": int(vid), "video_url": loc})
        except:
            pass
        time.sleep(0.2)
    return results


def load_used_pexels_ids() -> set[int]:
    """Load previously-used Pexels video IDs for deduplication."""
    p = ROOT / "data" / "used_pexels_video_ids.json"
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return set(int(k) for k in data.keys())
    except:
        return set()


def save_used_pexels_ids(new_entries: list[dict]) -> None:
    """Merge new entries into the used-IDs ledger."""
    p = ROOT / "data" / "used_pexels_video_ids.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except:
            existing = {}
    for e in new_entries:
        existing[str(e["vid"])] = {
            "theme": e.get("theme", ""),
            "posted_at": e.get("posted_at", datetime.now().strftime("%Y-%m-%d")),
            "account": e.get("account", ""),
            "moment_id": e.get("moment_id", ""),
        }
    p.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Account selection
# ---------------------------------------------------------------------------

def classify_nick(nick: str) -> str:
    has_kana = any(0x3040 <= ord(c) <= 0x30FF for c in nick)
    has_jp = any(c in nick for c in "にこまる星の")
    if has_kana or has_jp:
        return "jp"
    if any('\u4e00' <= c <= '\u9fff' for c in nick):
        return "cn"
    if re.match(r'^[A-Za-z][A-Za-z0-9_.\- ]+$', nick):
        return "en"
    return "random"


def pick_accounts(csv_path: Path, n: int, nick_filter: str = "auto") -> tuple[list[dict], dict]:
    """Pick n unused accounts, preferring the requested category.

    Returns (accounts, stats) where stats has keys 'picked', 'skipped_used'.
    """
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    used = set()
    tokens_file = ROOT / "result" / "tokens.json"
    if tokens_file.exists():
        try:
            used = set(json.loads(tokens_file.read_text(encoding="utf-8")).keys())
        except:
            pass

    groups: dict[str, list[dict]] = {"en": [], "jp": [], "cn": [], "random": []}
    for r in rows:
        nick = (r.get("昵称") or "").strip()
        email = (r.get("邮箱") or "").strip()
        pwd = (r.get("密码") or "").strip()
        if not email or not pwd or email in used:
            continue
        groups[classify_nick(nick)].append(r)

    # Build preference order
    if nick_filter == "auto":
        order = ["en", "random", "cn", "jp"]
    elif nick_filter in ("en", "jp", "cn", "random"):
        order = [nick_filter] + [c for c in ["en", "random", "cn", "jp"] if c != nick_filter]
    else:
        order = ["en", "random", "cn", "jp"]

    picked: list[dict] = []
    for cat in order:
        pool = list(groups[cat])
        random.shuffle(pool)
        for acct in pool:
            if len(picked) >= n:
                break
            picked.append(acct)

    stats = {
        "picked": len(picked),
        "skipped_used": len(used),
        "categories": {cat: len(groups[cat]) for cat in groups},
    }
    return picked[:n], stats


# ---------------------------------------------------------------------------
# Video download + thumbnail
# ---------------------------------------------------------------------------

PEXELS_VIDEO_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def download_pexels_video(url: str, out_path: Path, retries: int = 3) -> bool:
    """Download a Pexels video with retry and resume support."""
    for attempt in range(retries):
        existing = out_path.stat().st_size if out_path.exists() else 0
        headers = {"User-Agent": PEXELS_VIDEO_UA, "Referer": "https://www.pexels.com/"}
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"
        try:
            r = requests.get(url, stream=True, timeout=300, headers=headers, verify=False)
            mode = "ab" if existing > 0 and r.status_code == 206 else "wb"
            if r.status_code == 200:
                existing = 0
            with out_path.open(mode) as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            size_mb = out_path.stat().st_size // 1024 // 1024
            print(f"    video: {size_mb}MB")
            return True
        except Exception as e:
            print(f"    download attempt {attempt+1} failed: {e}")
            time.sleep(3)
    return False


def get_pexels_thumbnail(vid: int, media_dir: Path, video_file: Path) -> Path:
    """Get thumbnail: try Pexels image URLs, fall back to video file."""
    thumb = media_dir / f"pexels_thumb_{vid}.jpg"
    if thumb.exists() and thumb.stat().st_size > 1000:
        return thumb
    patterns = [
        f"https://images.pexels.com/videos/{vid}/pexels-photo-{vid}.jpeg?cs=tinysrgb&dpr=1&w=800",
        f"https://images.pexels.com/videos/{vid}/{vid}.jpeg?cs=tinysrgb&w=800",
    ]
    for pat in patterns:
        try:
            r = requests.get(pat, timeout=15, verify=False,
                              headers={"User-Agent": PEXELS_VIDEO_UA,
                                       "Referer": "https://www.pexels.com/"})
            if r.status_code == 200 and len(r.content) > 1000:
                thumb.write_bytes(r.content)
                print(f"    thumbnail: Pexels image OK")
                return thumb
        except:
            continue
    print(f"    [WARN] thumbnail fallback: using video file")
    return video_file


# ---------------------------------------------------------------------------
# S3 upload
# ---------------------------------------------------------------------------

def get_s3_creds(token: str) -> dict:
    resp = requests.post(
        config.UPLOAD_CREDENTIALS_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=config.POST_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    j = resp.json()
    if j.get("code") != 0:
        raise RuntimeError(f"S3 creds failed: {j}")
    return j["data"]


def s3_client(creds: dict):
    return boto3.client(
        "s3",
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds["session_token"],
        region_name=creds.get("region", "ap-northeast-1"),
    )


def upload_to_s3(local: Path, creds: dict, s3, content_type: str) -> str:
    date_path = time.strftime("%Y/%m/%d")
    key = f"square/original/{date_path}/{local.name}"
    s3.upload_file(str(local), creds["bucket"], key,
                   ExtraArgs={"ContentType": content_type,
                              "CacheControl": "public, max-age=31536000"})
    domain = creds.get("domain", "teststatic-x.tp-ex.com")
    return f"https://{domain}/{key}"


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login_account(email: str, password: str) -> str | None:
    try:
        r = requests.post(
            config.LOGIN_URL,
            json={"email": email, "password": password,
                  "device_id": config.POST_DEVICE_ID,
                  "device_name": config.POST_DEVICE_NAME},
            headers={"Content-Type": "application/json"},
            timeout=config.POST_REQUEST_TIMEOUT,
        )
        j = r.json()
        if j.get("code") == 0:
            return j["data"]["token"]
    except:
        pass
    return None


def sequential_login(accounts: list[dict], spacing: float = 2.5,
                     max_retries: int = 4) -> dict[str, str]:
    """Login all accounts sequentially. Returns {email: token}."""
    tokens: dict[str, str] = {}
    for i, acct in enumerate(accounts, 1):
        email, pwd = acct["邮箱"], acct["密码"]
        nick = acct.get("昵称", email)
        for attempt in range(max_retries):
            tok = login_account(email, pwd)
            if tok:
                tokens[email] = tok
                print(f"  [{i}/{len(accounts)}] {nick}: OK")
                break
            time.sleep(spacing * (2 ** attempt))
        else:
            print(f"  [{i}/{len(accounts)}] {nick}: FAILED (login)")
        time.sleep(spacing)
    return tokens


# ---------------------------------------------------------------------------
# Post moment
# ---------------------------------------------------------------------------

def post_video_moment(token: str, caption: str,
                      video_s3_url: str, thumb_s3_url: str) -> tuple[bool, str]:
    payload = {
        "content": caption,
        "visibility": 0,
        "media_info": {
            "type": "video",
            "video_url": video_s3_url,
            "thumbnail_url": thumb_s3_url,
        },
    }
    for attempt in range(3):
        try:
            r = requests.post(
                config.MOMENTS_API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                timeout=30,
            )
            j = r.json()
            if j.get("code") == 0:
                return True, str(j.get("data", {}).get("moment_id", ""))
            if r.status_code in (429, 500, 502, 503):
                time.sleep(5 * (2 ** attempt))
                continue
            return False, f"code={j.get('code')} {j.get('msg')}"
        except Exception as e:
            time.sleep(3)
    return False, "retry-exhausted"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Pexels video publisher for XXAI Square")
    ap.add_argument("--theme", default="cambodia",
                    help="Pexels search keyword (cambodia/tokyo/korea/india/southeast-asia/japan/...)")
    ap.add_argument("--accounts-csv", default="pre_企管用户_街拍摄影师.csv")
    ap.add_argument("--nick-filter", default="auto",
                    choices=["auto", "en", "jp", "cn", "random"],
                    help="Preferred account nickname category")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--caption-lang", default="en", choices=["en", "ja"])
    ap.add_argument("--login-spacing", type=float, default=2.5)
    ap.add_argument("--post-delay", type=float, default=5.0)
    ap.add_argument("--no-dedupe", action="store_true",
                    help="Skip Pexels video ID deduplication")
    ap.add_argument("--no-comments", action="store_true", default=True,
                    help="Skip comment posting (always skipped for this script)")
    ap.add_argument("--yes", action="store_true", help="Skip interactive confirmation")
    args = ap.parse_args()

    theme = args.theme
    n = args.count

    # 1. Discover videos
    print(f"[Pexels] theme={theme}, count={n}")
    videos = discover_pexels_videos(theme, limit=n)
    if not videos:
        print(f"[ERROR] no valid Pexels video URLs found for theme '{theme}'", file=sys.stderr)
        return 1

    # 2. Dedup
    if not args.no_dedupe:
        used_ids = load_used_pexels_ids()
        before = len(videos)
        videos = [v for v in videos if v["vid"] not in used_ids]
        print(f"[Dedupe] {before} -> {len(videos)} (skipped {before - len(videos)} already-used)")
        if not videos:
            print("[INFO] all Pexels videos already posted; nothing new to do.")
            return 0

    videos = videos[:n]

    # 3. Pick accounts
    acc_path = ROOT / args.accounts_csv
    if not acc_path.is_absolute():
        acc_path = ROOT / acc_path
    accounts, stats = pick_accounts(acc_path, n, args.nick_filter)
    print(f"[Accounts] picked {len(accounts)}: categories available={stats['categories']}, "
          f"already-used={stats['skipped_used']}")
    for a in accounts:
        print(f"    {a.get('昵称')} | {a.get('邮箱')} | {classify_nick(a.get('昵称',''))}")

    if not accounts:
        print("[ERROR] no unused accounts available", file=sys.stderr)
        return 1

    videos = videos[:len(accounts)]
    n = len(videos)

    if not args.yes:
        try:
            input(f"  Confirm publishing {n} Pexels {theme} videos? (y/n): ")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return 0

    # 4. Login
    print(f"\n=== Login {len(accounts)} accounts (spacing={args.login_spacing}s) ===")
    new_tokens = sequential_login(accounts, spacing=args.login_spacing)
    # Merge into global tokens
    tokens_file = ROOT / "result" / "tokens.json"
    existing_tokens = {}
    if tokens_file.exists():
        try:
            existing_tokens = json.loads(tokens_file.read_text(encoding="utf-8"))
        except:
            pass
    existing_tokens.update(new_tokens)
    tokens_file.parent.mkdir(parents=True, exist_ok=True)
    tokens_file.write_text(json.dumps(existing_tokens, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"  tokens saved → {tokens_file.relative_to(ROOT)}")

    # 5. S3 creds
    anchor_email = next(iter(new_tokens))
    creds = get_s3_creds(new_tokens[anchor_email])
    s3 = s3_client(creds)
    print(f"\n  S3 bucket: {creds.get('bucket')}")

    # 6. Download + upload + post each video
    media = ROOT / f"pexels_{theme}_video_run" / "media"
    media.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Post {n} videos ===")
    ok = 0
    used_entries: list[dict] = []
    report_rows: list[dict] = []

    for i, (vid, acct) in enumerate(zip(videos, accounts)):
        email = acct["邮箱"]
        nick = acct.get("昵称", email)
        token = new_tokens.get(email)
        caption = random.choice(CAPTION_BANKS.get(theme, CAPTION_BANKS["cambodia"]))

        if not token:
            print(f"  [{i+1}/{n}] {nick}: no token, skipping")
            continue

        # Download video
        vfile = media / f"pexels_video_{vid}.mp4"
        print(f"  [{i+1}/{n}] {nick}: downloading video {vid}...")
        if not download_pexels_video(vid, vfile, retries=3):
            print(f"  [SKIP] {vid}: download failed")
            report_rows.append({
                "csv_line": i + 1, "email": email, "nickname": nick,
                "vid": vid, "theme": theme, "success": False,
                "moment_id_or_err": "video_download_failed", "content": caption,
            })
            continue

        # Thumbnail
        tfile = get_pexels_thumbnail(vid, media, vfile)

        # Upload to S3
        try:
            video_s3 = upload_to_s3(vfile, creds, s3, "video/mp4")
            thumb_s3 = upload_to_s3(tfile, creds, s3, "image/jpeg" if tfile.suffix in (".jpg", ".jpeg") else "video/mp4")
        except Exception as e:
            print(f"  [SKIP] {vid}: S3 upload failed: {e}")
            report_rows.append({
                "csv_line": i + 1, "email": email, "nickname": nick,
                "vid": vid, "theme": theme, "success": False,
                "moment_id_or_err": f"s3_upload_failed: {e}", "content": caption,
            })
            continue

        # Post
        post_ok, post_info = post_video_moment(token, caption, video_s3, thumb_s3)
        if post_ok:
            ok += 1
            print(f"  ✓ {nick} -> moment_id={post_info}")
            used_entries.append({
                "vid": vid, "theme": theme, "account": email,
                "posted_at": datetime.now().strftime("%Y-%m-%d"),
                "moment_id": post_info,
            })
        else:
            print(f"  ✗ {nick} -> {post_info}")

        report_rows.append({
            "csv_line": i + 1, "email": email, "nickname": nick,
            "vid": vid, "theme": theme, "success": post_ok,
            "moment_id_or_err": post_info, "content": caption,
        })
        time.sleep(args.post_delay)

    # 7. Persist state
    if used_entries:
        save_used_pexels_ids(used_entries)
        print(f"\n[Dedupe] saved {len(used_entries)} used Pexels video IDs")

    ts = time.strftime("%Y%m%d_%H%M%S")
    out = ROOT / "result" / f"publish_pexels_{theme}_{ts}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["csv_line", "email", "nickname", "vid", "theme", "success",
              "moment_id_or_err", "content"]
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in report_rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"[Report] → {out.relative_to(ROOT)}")

    print(f"\n[Done] {ok}/{n} Pexels {theme} video posts")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
