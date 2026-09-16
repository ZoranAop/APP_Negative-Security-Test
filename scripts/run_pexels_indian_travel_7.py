#!/usr/bin/env python3
"""
run_pexels_indian_travel_7.py — 7 Pexels India-themed videos published
by 7 EN-nick accounts, each with a distinct English first-person travel/
photography voice. No image dedup needed (video posts).
"""
from __future__ import annotations

import argparse, csv, io, json, re, subprocess, sys, time, uuid, datetime, os
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

POOL_850_CSV = ROOT / "pre_企管用户_850.csv"
PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"
STATE_DIR = ROOT / "state"
DEDUPE_FILE = STATE_DIR / "seen_pexels_indian_travel_7.json"
CAPTION_DEDUPE = STATE_DIR / "seen_pexels_indian_travel_7_captions.json"
EN_NICK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-\ ]*$")

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY",
                           "qPYcteScsZbLDvxBcXSX1inBxLWdklBUBirESLX9d8Mosmf4vh3DzfnF")

UPLOAD_CREDENTIALS_URL = os.getenv("UPLOAD_CREDENTIALS_URL",
                                   "https://api.xxai.com/file/upload/credentials")
MOMENTS_API_URL = os.getenv("MOMENTS_API_URL",
                            "https://feed-api.xxai.com/api/v1/moments/")
LOGIN_URL = os.getenv("LOGIN_URL", "https://api.xxai.com/login")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TOKENS_FILE = ROOT / "result" / "tokens.json"

import requests
try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    print("[FATAL] boto3 not installed", file=sys.stderr)
    sys.exit(1)

# 7 captions — each a distinct voice/style, all first-person, travel/photography angle
CAPTIONS = [
    # Voice: documentary-style, restrained
    "Shot this in the early hours in Varanasi, before the crowds found the river. "
    "The light here doesn't behave like anywhere else — it just sits on the water "
    "and holds still. Most of it I don't even use. It's the silence between shots "
    "that gets me.",

    # Voice: casual, slightly self-deprecating
    "Okay so I accidentally spent four hours in a spice market in Mumbai instead of "
    "finding the beach I was supposed to be shooting. Not gonna pretend this was "
    "planned. It was the best unplanned frame of the whole trip.",

    # Voice: poetic, minimal
    "Jaipur at 5:47am. No people, just the pink light hitting the sandstone. "
    "I stayed until my feet hurt. Worth every step.",

    # Voice: analytical, photographer's eye
    "The depth of field in this shot does all the work. The background is "
    "completely out of focus — that's how I knew the light was right. "
    "Sometimes you just point and wait for the frame to resolve itself.",

    # Voice: warm, personal anecdote
    "A woman in Udaipur handed me chai without saying a word. I almost didn't "
    "want to keep shooting because the moment was too small and too right. "
    "Ended up staying twenty more minutes just to sit and drink it slowly.",

    # Voice: matter-of-fact, slightly dry
    "The camera battery died at exactly the moment the sunset hit the minarets. "
    "Shot the last two frames with whatever light I had left. Sometimes the "
    "constraint makes the image.",

    # Voice: sensory, present-tense
    "You can hear the temple bells before you see them in Amritsar. This clip "
    "is from that exact second — the point where sound and architecture merge "
    "and the whole city seems to hold its breath.",
]

# Pexels search query for "印度美女" ≈ Indian female / India travel
PEXELS_QUERY = "india woman"
VIDEO_COUNT = 7


def _fetch_pexels(query: str, per_page: int = 20, page: int = 1) -> list:
    r = requests.get(
        "https://api.pexels.com/videos/search",
        params={"query": query, "per_page": per_page, "page": page, "locale": "en-US"},
        headers={"Authorization": PEXELS_API_KEY},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("videos", [])


def _load_seen_videos() -> set:
    if DEDUPE_FILE.exists():
        try:
            return set(json.loads(DEDUPE_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def _save_seen_videos(ids: set) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DEDUPE_FILE.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def _get_fresh_videos(seen: set, count: int = VIDEO_COUNT) -> list:
    videos = []
    page = 1
    while len(videos) < count and page <= 10:
        batch = _fetch_pexels(PEXELS_QUERY, per_page=20, page=page)
        if not batch:
            break
        for v in batch:
            vid_id = v.get("id")
            if vid_id in seen:
                continue
            duration = v.get("duration", 0)
            if duration < 5 or duration > 60:
                continue
            vf = v.get("video_files", [])
            best = None
            for f in vf:
                w, h = f.get("width", 0), f.get("height", 0)
                quality = f.get("quality", "")
                if quality in ("uhd", "hd") and h >= 720:
                    best = f
                    break
            if best is None:
                best = vf[0] if vf else None
            if best is None:
                continue
            link = best.get("link", "")
            if not link:
                continue
            cover = v.get("image", "")
            videos.append({
                "id": vid_id,
                "url": link,
                "cover": cover,
                "duration": duration,
                "width": v.get("width", 0),
                "height": v.get("height", 0),
            })
            if len(videos) >= count:
                break
        page += 1
    return videos[:count]


def _load_used_emails() -> set:
    used = set()
    if TOKENS_FILE.exists():
        try:
            used.update(json.loads(TOKENS_FILE.read_text(encoding="utf-8")).keys())
        except Exception:
            pass
    for d in ROOT.glob("*_run"):
        for f in d.glob("accounts_merged_*.csv"):
            try:
                for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                    e = (row.get("邮箱") or row.get("email") or "").strip().lower()
                    if e:
                        used.add(e)
            except Exception:
                pass
    return used


def load_en_nick_accounts(n: int, exclude: set) -> list:
    picked = []
    seen = set(exclude)
    for csv_path in [PHOTOGRAPHER_CSV, POOL_850_CSV]:
        if len(picked) >= n:
            break
        if not csv_path.exists():
            continue
        for r in csv.DictReader(open(csv_path, encoding="utf-8-sig")):
            if len(picked) >= n:
                break
            email = (r.get("邮箱") or r.get("email") or "").strip()
            nick = (r.get("昵称") or "").strip()
            password = (r.get("密码") or "").strip()
            pincode = (r.get("pincode") or "").strip()
            seq = (r.get("序号") or "").strip()
            if not email or not password or email.lower() in seen:
                continue
            if not EN_NICK_RE.match(nick):
                continue
            seen.add(email.lower())
            picked.append({"email": email, "password": password,
                           "pincode": pincode, "nickname": nick, "seq": seq})
    return picked


def _login(email: str, password: str) -> str:
    r = requests.post(LOGIN_URL, json={
        "email": email, "password": password,
        "device_id": "auto_poster", "device_name": "auto_poster_client",
    }, headers={"Content-Type": "application/json"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("code") == 0:
        return data["data"]["token"]
    raise RuntimeError(f"login failed: {data}")


def _get_s3_creds(token: str) -> dict:
    r = requests.post(UPLOAD_CREDENTIALS_URL,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                      timeout=15)
    r.raise_for_status()
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"upload creds fail: {data}")
    return data["data"]


def _download(url: str, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    dst = target_dir / f"{uuid.uuid4().hex}.mp4"
    headers = {"User-Agent": UA, "Referer": "https://www.pexels.com/"}
    with requests.get(url, stream=True, headers=headers, timeout=120) as resp:
        resp.raise_for_status()
        with dst.open("wb") as fh:
            for chunk in resp.iter_content(1 << 16):
                fh.write(chunk)
    return dst


def _upload_s3(local: Path, creds: dict, content_type: str = "video/mp4") -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    date_str = now.strftime("%Y/%m/%d")
    key = f"square/original/{date_str}/{local.name}"
    s3 = boto3.client(
        "s3",
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds["session_token"],
        region_name=creds["region"],
        config=BotoConfig(signature_version="s3v4"),
    )
    s3.upload_file(str(local), creds["bucket"], key,
                   ExtraArgs={"ContentType": content_type})
    return f"https://{creds['domain']}/{key}"


def _publish_video(token: str, caption: str, video_url: str,
                  thumbnail_url: str) -> dict:
    body = {
        "content": caption,
        "visibility": 0,
        "media_info": {
            "type": "video",
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
        },
    }
    r = requests.post(MOMENTS_API_URL,
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"},
                      json=body, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"publish failed: {r.status_code} {r.text}")
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="pexels_indian_travel_7_run")
    ap.add_argument("--login-spacing", type=float, default=2.5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    # Fetch fresh Pexels videos
    seen_videos = _load_seen_videos()
    print(f"[pexels] previously seen: {len(seen_videos)}")
    videos = _get_fresh_videos(seen_videos, count=VIDEO_COUNT)
    if not videos:
        print("[ERROR] No usable Pexels videos found", file=sys.stderr)
        return 1
    for i, v in enumerate(videos):
        print(f"  [{i+1}] vid={v['id']} {v['width']}x{v['height']} {v['duration']}s")
    _save_seen_videos(seen_videos | {v["id"] for v in videos})

    # Load accounts
    used = _load_used_emails()
    accounts = load_en_nick_accounts(len(videos), used)
    print(f"\n[accounts] {len(accounts)} EN-nick accounts: {[a['nickname'] for a in accounts]}")
    if len(accounts) < len(videos):
        print(f"[ERROR] Need {len(videos)} EN-nick accounts, found {len(accounts)}",
              file=sys.stderr)
        return 1

    # Build moments
    moments = []
    for i, v in enumerate(videos):
        cap = CAPTIONS[i % len(CAPTIONS)]
        moments.append({
            "content": cap,
            "video_url": v["url"],
            "cover_url": v["cover"],
            "_vid_id": v["id"],
        })

    if args.dry_run:
        print("\n[dry-run] Stopping before login/publish")
        for i, m in enumerate(moments):
            print(f"  [{i+1}] {accounts[i]['nickname']:15} | {m['content'][:55]}...")
        return 0

    if not args.yes:
        if input("Confirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    # Phase 2: Login
    print("\n=== Phase 2: Login ===")
    tokens = {}
    for a in accounts:
        print(f"  Logging in {a['email']} ...", end=" ", flush=True)
        try:
            tok = _login(a["email"], a["password"])
            tokens[a["email"]] = tok
            print("OK")
        except Exception as e:
            print(f"FAILED: {e}")
        time.sleep(args.login_spacing)

    # Load/merge existing tokens
    if TOKENS_FILE.exists():
        try:
            existing = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
            tokens.update(existing)
        except Exception:
            pass
    TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_FILE.write_text(json.dumps(tokens, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Phase 2] tokens persisted: {len(tokens)}")

    # Phase 3: Video download + S3 upload + publish
    print("\n=== Phase 3: Video publish ===")
    media_dir = wd / "media"
    published = []
    for i, m in enumerate(moments):
        a = accounts[i]
        token = tokens.get(a["email"])
        if not token:
            print(f"  [{i+1}] {a['nickname']}: no token, skip")
            continue
        print(f"  [{i+1}] {a['nickname']}: download ...", end=" ", flush=True)
        try:
            local = _download(m["video_url"], media_dir)
        except Exception as e:
            print(f"download fail: {e}")
            continue
        print("S3 upload ...", end=" ", flush=True)
        try:
            creds = _get_s3_creds(token)
            video_url = _upload_s3(local, creds, "video/mp4")
        except Exception as e:
            print(f"upload fail: {e}")
            continue
        print("publish ...", end=" ", flush=True)
        try:
            result = _publish_video(token, caption=m["content"],
                                    video_url=video_url,
                                    thumbnail_url=m["cover_url"])
            mid = (result.get("data") or {}).get("id") or (result.get("data") or {}).get("moment_id") or str(result)
            print(f"OK moment_id={mid}")
            published.append({"email": a["email"], "nick": a["nickname"],
                              "moment_id": mid, "vid_id": m["_vid_id"]})
        except Exception as e:
            print(f"publish fail: {e}")
        time.sleep(args.login_spacing * 0.5)

    print(f"\n{'='*50}")
    print(f"[Done] {len(published)}/{len(moments)} published")
    for p in published:
        print(f"  OK  {p['nick']:15} vid={p['vid_id']}  moment={p['moment_id']}")
    return 0 if len(published) == len(moments) else 1


if __name__ == "__main__":
    sys.exit(main())
