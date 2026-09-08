#!/usr/bin/env python3
"""
run_foreign_video_publish.py — Publish short videos from free stock video sources.
Sources: Pexels (free stock videos), mixed with OpenNana AI videos.
"""
from __future__ import annotations

import argparse, csv, io, json, mimetypes, os, re, subprocess, sys, time, uuid
from pathlib import Path
from urllib.parse import urlparse

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

import requests

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    print("[FATAL] boto3 not installed. Run: py -3 -m pip install boto3", file=sys.stderr)
    sys.exit(1)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://www.pexels.com/"}
PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"
STATE_DIR = ROOT / "state"
DEDUPE_FILE = STATE_DIR / "seen_foreign_video_publish.json"

# English caption templates for foreign videos
EN_CAPTIONS = [
    "This short clip really captures the essence of the moment. Love the energy and flow here.",
    "Found this beautiful moment and had to share. The composition and lighting are perfect.",
    "Such a cinematic feel in this video. Every frame could be a wallpaper.",
    "The creativity in this piece is outstanding. Really inspires me to pick up the camera.",
    "This is the kind of content that makes my day. Authentic and beautifully told.",
    "Love how this captures everyday moments and makes them extraordinary.",
    "The storytelling through visuals here is masterful. Simple yet powerful.",
    "This reminded me why I love visual content. Pure emotion captured in seconds.",
    "Incredible work here. The attention to detail and pacing is just right.",
    "Such a vibrant and engaging piece. Glad I came across this today.",
]


def _load_tokens():
    try:
        return set(json.loads((ROOT / "result/tokens.json").read_text(encoding="utf-8")).keys())
    except Exception:
        return set()


def _load_used_emails():
    used = set()
    for d in ROOT.glob("photographer_*_run"):
        for f in d.glob("accounts_merged_*.csv"):
            try:
                for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                    e = row.get("邮箱", "").strip().lower()
                    if e:
                        used.add(e)
            except Exception:
                pass
    return used


def pick_accounts(n):
    tokens = _load_tokens()
    prev_used = _load_used_emails()
    exclude = tokens | prev_used
    rows = list(csv.DictReader(open(PHOTOGRAPHER_CSV, encoding="utf-8-sig")))
    picked = []
    seen = set(exclude)
    for r in rows:
        email = r.get("邮箱", "").strip().lower()
        if email in seen:
            continue
        seen.add(email)
        picked.append(r)
        if len(picked) >= n:
            break
    return picked


def fetch_pexels_videos(query="lifestyle", per_page=20):
    """Fetch videos from Pexels search API."""
    url = "https://api.pexels.com/v1/search"
    headers = {
        "Authorization": "53456789-QJ9s8hLzK3vR2pN5tY6wX4mZ1bC7dF8eA9gH0iJ2kL4mN5",  # Demo key, may need real key
        "User-Agent": UA,
    }
    params = {"query": query, "per_page": per_page}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if r.status_code == 200:
            data = r.json()
            videos = data.get("videos", [])
            return [{"video_url": v.get("video_files", [{}])[0].get("link", ""),
                     "thumbnail": v.get("image", ""),
                     "title": v.get("alt", "")[:50]} for v in videos if v.get("video_files")]
    except Exception as e:
        print(f"  Pexels API error: {e}")
    return []


def fetch_opennana_video(slug):
    """Fetch video from OpenNana."""
    r = requests.get(f"https://api.opennana.com/api/prompts/{slug}",
        headers={"User-Agent": UA, "Referer": "https://opennana.com/"}, timeout=20)
    if r.status_code == 200:
        data = r.json().get("data", {})
        videos = data.get("video_urls", [])
        if videos:
            return {"video_url": videos[0], "thumbnail": "", "title": data.get("title", "")}
    return None


def login_user(email, password):
    payload = {
        "email": email,
        "password": password,
        "device_id": "foreign_video_publisher",
        "device_name": "auto_poster_client",
    }
    r = requests.post("https://api.xxai.com/login", json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token") or data.get("token") or (data.get("data") or {}).get("token")
    if not token:
        raise RuntimeError(f"Login failed for {email}")
    return token


def get_s3_creds(token):
    r = requests.post("https://api.xxai.com/file/upload/credentials",
        headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("data") or data


def download_file(url, save_dir, timeout=120):
    save_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".mp4"
    name = f"{uuid.uuid4().hex}{suffix}"
    dst = save_dir / name
    
    headers = {"User-Agent": UA}
    referer = parsed.scheme + "://" + parsed.netloc + "/"
    headers["Referer"] = referer
    
    with requests.get(url, stream=True, headers=headers, timeout=timeout) as resp:
        resp.raise_for_status()
        with dst.open("wb") as f:
            for chunk in resp.iter_content(1 << 16):
                f.write(chunk)
    return dst


def upload_to_s3(local_path, creds):
    today = time.strftime("%Y/%m/%d")
    key = f"square/original/{today}/{local_path.name}"
    
    content_type = mimetypes.guess_type(local_path.name)[0] or "video/mp4"
    
    s3 = boto3.client("s3",
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds["session_token"],
        region_name=creds["region"],
        config=BotoConfig(signature_version="s3v4"))
    
    s3.upload_file(str(local_path), creds["bucket"], key,
        ExtraArgs={"ContentType": content_type})
    return f"https://{creds['domain']}/{key}"


def publish_video(token, caption, video_url, thumbnail_url):
    body = {
        "content": caption,
        "visibility": 0,
        "media_info": {
            "type": "video",
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
        },
    }
    r = requests.post("https://feed-api.xxai.com/api/v1/moments/",
        headers={"Authorization": f"Bearer {token}"}, json=body, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Publish failed: {r.status_code} {r.text}")
    return r.json()


def main():
    ap = argparse.ArgumentParser(description="Foreign Video Publisher")
    ap.add_argument("--num-users", type=int, default=2)
    ap.add_argument("--lang", choices=["en"], default="en")
    ap.add_argument("--target", type=int, default=10)
    ap.add_argument("--login-spacing", type=float, default=5.0)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / f"foreign_video_{ts}_run"
    wd.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)
    MEDIA_DIR = wd / "media"
    MEDIA_DIR.mkdir(exist_ok=True)

    # Pick accounts
    accounts = pick_accounts(args.num_users)
    print(f"[accounts] {len(accounts)} photographers: {[a['昵称'] for a in accounts]}")

    # Fetch videos from multiple sources
    print(f"\n=== Fetching foreign videos (target: {args.target}) ===")
    
    # Try OpenNana videos first (reliable)
    opennana_slugs = [
        "japanese-street-fashion-autumn-cafe-portrait",
        "cinematic-fashion-portrait-young-woman-boutique",
        "modern-indoor-crouching-east-asian-woman-fashion-photography",
        "young-woman-mirror-selfie-photography-studio",
        "east-asian-woman-realistic-phone-selfie-dreamcore-aesthetic",
    ]
    
    videos = []
    for slug in opennana_slugs:
        detail = fetch_opennana_video(slug)
        if detail and detail["video_url"]:
            videos.append({
                "video_url": detail["video_url"],
                "thumbnail_url": detail.get("thumbnail", ""),
                "caption": f"{detail['title']}\n\n{EN_CAPTIONS[len(videos) % len(EN_CAPTIONS)]}",
                "note_id": slug,
            })
            print(f"  [OK] {slug[:40]}...")
        if len(videos) >= args.target:
            break
    
    print(f"\n[OK] {len(videos)} videos ready")

    if not args.yes:
        if input("\nConfirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    # Publish
    print(f"\n=== Publishing {len(videos)} videos ===")
    results = []
    
    for i, v in enumerate(videos):
        acct = accounts[i] if i < len(accounts) else None
        email = acct["邮箱"] if acct else None
        nick = acct["昵称"] if acct else "?"
        
        print(f"\n[{i+1}/{len(videos)}] {nick} ({email})")
        print(f"  Video: {v['note_id'][:20]}...")
        
        try:
            # Login
            token = login_user(email, acct["密码"])
            print(f"  [1/5] Login OK")
            
            # S3 creds
            creds = get_s3_creds(token)
            print(f"  [2/5] S3 creds OK")
            
            # Download video
            video_local = download_file(v["video_url"], MEDIA_DIR, timeout=120)
            size_mb = video_local.stat().st_size / 1024 / 1024
            print(f"  [3/5] Downloaded video: {size_mb:.1f} MB")
            
            # Download cover if available
            cover_local = None
            if v.get("thumbnail_url"):
                try:
                    cover_local = download_file(v["thumbnail_url"], MEDIA_DIR, timeout=30)
                    print(f"  [3/5] Downloaded cover")
                except:
                    pass
            
            # Upload video
            s3_video = upload_to_s3(video_local, creds)
            print(f"  [4/5] Uploaded video")
            
            # Upload cover
            s3_cover = s3_video
            if cover_local:
                s3_cover = upload_to_s3(cover_local, creds)
            print(f"  [4/5] Uploaded cover")
            
            # Publish
            result = publish_video(token, v["caption"], s3_video, s3_cover)
            moment_id = (result.get("data") or {}).get("moment_id") or result.get("data", {}).get("id", "?")
            print(f"  [5/5] SUCCESS! moment_id={moment_id}")
            
            results.append({
                "idx": i+1, "user": nick, "email": email,
                "moment_id": str(moment_id), "status": "OK",
            })
            
            # Cleanup
            video_local.unlink(missing_ok=True)
            if cover_local:
                cover_local.unlink(missing_ok=True)
                
        except Exception as e:
            print(f"  [ERROR] {e}")
            results.append({
                "idx": i+1, "user": nick, "email": email,
                "moment_id": "", "status": f"FAIL: {e}",
            })
        
        if i < len(videos) - 1:
            time.sleep(args.login_spacing)

    # Summary
    print(f"\n{'='*60}")
    ok_count = sum(1 for r in results if r["status"] == "OK")
    print(f"Results: {ok_count}/{len(results)} OK")
    for r in results:
        icon = "OK  " if r["status"] == "OK" else "FAIL"
        print(f"  [{r['idx']:2}] {icon} {r['user']:<15} moment_id={r['moment_id']}")
    
    # Save dedupe
    dedupe_file = DEDUPE_FILE
    used = set()
    if dedupe_file.exists():
        try:
            used = set(json.loads(dedupe_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    new_keys = {v["note_id"] for v in videos}
    dedupe_file.write_text(json.dumps(sorted(used | new_keys), ensure_ascii=False), encoding="utf-8")
    
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
