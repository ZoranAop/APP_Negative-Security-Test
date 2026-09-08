#!/usr/bin/env python3
"""
run_xhs_video_publish.py — 小红书视频采集 → 批量发布到 XXAI 广场（纯英文/繁体中文文案）。

流程：
  1. 从 XHS explore 推荐流采集视频笔记（type=video，CDN 直链）
  2. 从 pre_企管用户_街拍摄影师.csv 选取 N 个英文昵称用户
  3. 登录 → S3 凭证 → 下载视频+封面 → S3 上传 → 发布
  4. 文案使用英文或繁体中文，第一人称口吻

用法：
    py -3 scripts/run_xhs_video_publish.py --num-users 5 --yes
    py -3 scripts/run_xhs_video_publish.py --num-users 5 --lang en --yes
    py -3 scripts/run_xhs_video_publish.py --num-users 5 --lang zh_hant --yes
    py -3 scripts/run_xhs_video_publish.py --num-users 5 --lang mixed --yes
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
XHS_HEADERS = {"User-Agent": UA, "Referer": "https://www.xiaohongshu.com/"}
PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"
INTERACT_CSV = ROOT / "互动用户池_220账号_完整信息.xlsx"
STATE_DIR = ROOT / "state"
DEDUPE_FILE = STATE_DIR / "seen_xhs_video_publish.json"

# English caption templates for XHS videos (first-person, concise)
EN_CAPTIONS = [
    "Just came across this video and had to share. The content is genuinely engaging and well-produced.",
    "This caught my attention on my feed. Really nice quality and storytelling here.",
    "Love seeing this kind of content from Xiaohongshu. The production value is impressive.",
    "Something worth watching — the creativity in this video really stands out.",
    "This is the kind of video that makes me stop scrolling. Well done!",
    "Impressive work here. The attention to detail and composition is really well executed.",
    "Found this gem on my timeline. The energy and style are exactly what I look for.",
    "Really enjoying this creator's content. Consistently high quality and engaging.",
    "This video has such a unique perspective. Glad I stumbled upon it today.",
    "The storytelling in this one is top-notch. Really draws you in from the start.",
]

ZH_HANT_CAPTIONS = [
    "剛在小紅書上看到這段影片，覺得很有共鳴，分享給大家～",
    "這段內容真的做得很用心，看得出來花了很多心思在製作上。",
    "喜歡這種風格的影片，節奏感和畫面都很舒服，推薦給大家！",
    "今天刷到這個，忍不住要分享。創作者的創意真的很棒！",
    "這個主題很有趣，影片的呈現方式也很獨特，值得一看。",
    "小紅書上的好內容，品質穩定又有趣，每次都能看到驚喜。",
    "這段影片讓我駐足看了好幾遍，細節處理得很到位。",
    "很喜歡這種真實自然的風格，不像刻意擺拍的內容。",
    "分享一個我最近很愛的創作類型，看完心情都變好了～",
    "創作者的視角很特別，把平凡的小事拍得如此有感染力。",
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


def pick_accounts(n, source="photographer"):
    """Pick accounts from either photographer pool or interact pool."""
    import openpyxl
    
    tokens = _load_tokens()
    prev_used = _load_used_emails()
    exclude = tokens | prev_used
    
    if source == "interact":
        # Load from 互动用户池_220账号_完整信息.xlsx
        wb = openpyxl.load_workbook(str(INTERACT_CSV), read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(min_row=2, values_only=True))
        wb.close()
        
        picked = []
        seen = set(exclude)
        for row in rows:
            if len(row) < 5:
                continue
            email = str(row[1]).strip() if row[1] else ""  # 邮箱列
            nick = str(row[3]).strip() if row[3] else ""   # 昵称列
            password = str(row[4]).strip() if row[4] else ""  # 密码列
            
            if not email or not password:
                continue
            if email.lower() in seen:
                continue
            seen.add(email.lower())
            picked.append({"邮箱": email, "昵称": nick, "密码": password})
            if len(picked) >= n:
                break
        return picked
    else:
        # Default: photographer pool
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


def fetch_xhs_videos(target=10, delay=1.0):
    """Fetch video notes from XHS explore page."""
    r = requests.get("https://www.xiaohongshu.com/explore", headers=XHS_HEADERS, timeout=20)
    m = re.search(r"window.__INITIAL_STATE__=(.*?)</script>", r.text, re.S)
    if not m:
        return []
    data = json.loads(m.group(1).replace(":undefined", ":null"))
    feeds = data.get("feed", {}).get("feeds", [])
    videos = [f for f in feeds if f.get("noteCard", {}).get("type", "").lower() == "video"]
    
    results = []
    seen_ids = set()
    for v in videos:
        nid = v.get("id", "")
        if nid in seen_ids:
            continue
        seen_ids.add(nid)
        token = v.get("xsecToken", "")
        title = v.get("noteCard", {}).get("displayTitle", "")
        results.append({"note_id": nid, "xsec_token": token, "title": title})
        if len(results) >= target:
            break
        time.sleep(delay)
    return results


def fetch_video_detail(note_id, xsec_token):
    """Fetch video URL and metadata from XHS note detail page."""
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    if xsec_token:
        url += f"?xsec_token={xsec_token}&xsec_source=pc_feed"
    
    r = requests.get(url, headers=XHS_HEADERS, timeout=30)
    m = re.search(r"window.__INITIAL_STATE__=(.*?)</script>", r.text, re.S)
    if not m:
        return None
    
    data = json.loads(m.group(1).replace(":undefined", ":null"))
    note = data.get("note", {}).get("noteDetailMap", {}).get(note_id, {}).get("note", {})
    
    # Extract video URL
    video = note.get("video", {})
    h264 = video.get("media", {}).get("stream", {}).get("h264", [])
    if not h264:
        return None
    
    video_url = h264[0].get("masterUrl") or h264[0].get("backupUrl")
    duration_ms = h264[0].get("duration", 0)
    duration_sec = duration_ms / 1000 if duration_ms else 0
    
    # Extract cover image from imageList (XHS stores video covers here)
    cover_url = ""
    image_list = note.get("imageList", [])
    if image_list:
        cover_url = image_list[0].get("urlDefault") or image_list[0].get("urlPre") or ""
    
    # Fallback: check video.image for thumbnail
    if not cover_url:
        cover = video.get("image", {})
        cover_url = cover.get("urlDefault") or cover.get("url") or ""
    
    # Content
    title = note.get("title", "")
    desc = note.get("desc", "")
    content = f"{title}\n{desc}".strip() if desc else title
    
    # Clean up XHS-specific formatting
    content = re.sub(r"#([^\[#]+)\[话题\]#", r"#\1", content)
    content = re.sub(r"\[[^\]]+R\]", "", content)
    content = re.sub(r"@[\w\u4e00-\u9fff]+", "", content)
    content = re.sub(r" +", " ", content)
    content = re.sub(r"\n+", "\n", content).strip()
    
    return {
        "video_url": video_url,
        "cover_url": cover_url,
        "content": content,
        "duration_sec": duration_sec,
    }


def login_user(email, password):
    """Login and get Bearer token."""
    payload = {
        "email": email,
        "password": password,
        "device_id": "xhs_video_publisher",
        "device_name": "auto_poster_client",
    }
    r = requests.post("https://api.xxai.com/login", json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token") or data.get("token") or (data.get("data") or {}).get("token")
    if not token:
        raise RuntimeError(f"Login failed for {email}: {data}")
    return token


def get_s3_creds(token):
    """Get S3 upload credentials."""
    r = requests.post("https://api.xxai.com/file/upload/credentials",
        headers={"Authorization": f"Bearer {token}"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    creds = data.get("data") or data
    return creds


def download_file(url, save_dir, timeout=120):
    """Download file from URL with Referer handling."""
    save_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".mp4"
    name = f"{uuid.uuid4().hex}{suffix}"
    dst = save_dir / name
    
    headers = {"User-Agent": UA, "Referer": "https://www.xiaohongshu.com/"}
    with requests.get(url, stream=True, headers=headers, timeout=timeout) as resp:
        resp.raise_for_status()
        with dst.open("wb") as f:
            for chunk in resp.iter_content(1 << 16):
                f.write(chunk)
    return dst


def upload_to_s3(local_path, creds):
    """Upload file to S3 and return public URL."""
    today = time.strftime("%Y/%m/%d")
    key = f"square/original/{today}/{local_path.name}"
    
    content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    if local_path.suffix.lower() == ".mp4":
        content_type = "video/mp4"
    
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
    """Publish video moment to XXAI square."""
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
    ap = argparse.ArgumentParser(description="XHS Video Publisher")
    ap.add_argument("--num-users", type=int, default=5)
    ap.add_argument("--lang", choices=["en", "zh_hant", "mixed"], default="mixed")
    ap.add_argument("--target", type=int, default=10, help="Target videos to fetch")
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="xhs_video_publish_run")
    ap.add_argument("--source", choices=["photographer", "interact"], default="photographer",
                    help="Account source: photographer (街拍摄影师) or interact (互动用户池)")
    ap.add_argument("--login-spacing", type=float, default=5.0,
                    help="Login interval seconds (default 5.0, avoid 429)")
    ap.add_argument("--max-retries", type=int, default=3,
                    help="Max login retry attempts (default 3)")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)
    MEDIA_DIR = wd / "media"
    MEDIA_DIR.mkdir(exist_ok=True)

    # Pick accounts
    source = args.source
    accounts = pick_accounts(args.num_users, source=source)
    print(f"[accounts] {len(accounts)} photographers from {source} pool: {[a['昵称'] for a in accounts]}")

    # Fetch XHS videos
    print(f"\n=== Fetching XHS videos (target: {args.target}) ===")
    video_notes = fetch_xhs_videos(target=args.target, delay=1.0)
    print(f"Found {len(video_notes)} video notes")

    # Fetch details and build moments
    moments = []
    for vnote in video_notes[:args.num_users]:
        detail = fetch_video_detail(vnote["note_id"], vnote["xsec_token"])
        if not detail:
            print(f"  [SKIP] No video detail for {vnote['note_id']}")
            continue
        
        # Choose caption language
        if args.lang == "en":
            lang = "en"
            caption_pool = EN_CAPTIONS
        elif args.lang == "zh_hant":
            lang = "zh_hant"
            caption_pool = ZH_HANT_CAPTIONS
        else:  # mixed
            lang = "en" if len(moments) % 2 == 0 else "zh_hant"
            caption_pool = EN_CAPTIONS if lang == "en" else ZH_HANT_CAPTIONS
        
        caption = f"{detail['content']}\n\n{caption_pool[len(moments) % len(caption_pool)]}"
        moments.append({
            "note_id": vnote["note_id"],
            "video_url": detail["video_url"],
            "cover_url": detail["cover_url"],
            "content": detail["content"],
            "caption": caption,
            "lang": lang,
            "duration_sec": detail["duration_sec"],
        })
        print(f"  [OK] {vnote['note_id'][:12]} | {lang} | {detail['duration_sec']:.0f}s")

    print(f"\n[OK] {len(moments)} videos ready")

    if not args.yes:
        if input("\nConfirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    # Download, upload, publish
    print(f"\n=== Publishing {len(moments)} videos ===")
    results = []
    
    for i, m in enumerate(moments):
        acct = accounts[i] if i < len(accounts) else None
        email = acct["邮箱"] if acct else None
        nick = acct["昵称"] if acct else "?"
        
        print(f"\n[{i+1}/{len(moments)}] {nick} ({email})")
        print(f"  Video: {m['note_id']} | {m['duration_sec']:.0f}s | lang={m['lang']}")
        
        try:
            # Login with retry
            token = None
            for retry in range(args.max_retries):
                try:
                    token = login_user(email, acct["密码"])
                    print(f"  [1/5] Login OK")
                    break
                except Exception as e:
                    if retry < args.max_retries - 1:
                        wait = 10 * (retry + 1)
                        print(f"  [1/5] Login failed ({e}), retry {retry+1}/{args.max_retries} in {wait}s...")
                        time.sleep(wait)
                    else:
                        raise
            
            if not token:
                raise RuntimeError("Login failed after retries")
            
            # S3 creds
            creds = get_s3_creds(token)
            print(f"  [2/5] S3 creds OK")
            
            # Download video
            video_local = download_file(m["video_url"], MEDIA_DIR, timeout=120)
            size_mb = video_local.stat().st_size / 1024 / 1024
            print(f"  [3/5] Downloaded video: {size_mb:.1f} MB")
            
            # Download cover
            if m["cover_url"]:
                cover_local = download_file(m["cover_url"], MEDIA_DIR, timeout=30)
                print(f"  [3/5] Downloaded cover")
            else:
                # Generate cover from video first frame
                cover_local = None
            
            # Upload video to S3
            s3_video = upload_to_s3(video_local, creds)
            print(f"  [4/5] Uploaded video")
            
            # Upload cover to S3
            s3_cover = ""
            if cover_local:
                s3_cover = upload_to_s3(cover_local, creds)
            else:
                # Use video URL as cover fallback
                s3_cover = s3_video
            
            print(f"  [4/5] Uploaded cover")
            
            # Publish
            result = publish_video(token, m["caption"], s3_video, s3_cover)
            moment_id = (result.get("data") or {}).get("moment_id") or result.get("data", {}).get("id", "?")
            print(f"  [5/5] SUCCESS! moment_id={moment_id}")
            
            results.append({
                "idx": i+1, "user": nick, "email": email,
                "moment_id": str(moment_id), "lang": m["lang"],
                "status": "OK",
            })
            
            # Cleanup
            video_local.unlink(missing_ok=True)
            if cover_local:
                cover_local.unlink(missing_ok=True)
                
        except Exception as e:
            print(f"  [ERROR] {e}")
            results.append({
                "idx": i+1, "user": nick, "email": email,
                "moment_id": "", "lang": m["lang"],
                "status": f"FAIL: {e}",
            })
        
        # Delay between posts to avoid 429
        if i < len(moments) - 1:
            time.sleep(args.login_spacing)

    # Summary
    print(f"\n{'='*60}")
    ok_count = sum(1 for r in results if r["status"] == "OK")
    fail_count = len(results) - ok_count
    print(f"Results: {ok_count}/{len(results)} OK, {fail_count} failed")
    for r in results:
        icon = "OK  " if r["status"] == "OK" else "FAIL"
        print(f"  [{r['idx']:2}] {icon} {r['user']:<15} lang={r['lang']} moment_id={r['moment_id']}")
    
    # Save dedupe
    dedupe_file = DEDUPE_FILE
    used = set()
    if dedupe_file.exists():
        try:
            used = set(json.loads(dedupe_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    new_keys = {m["note_id"] for m in moments}
    dedupe_file.write_text(json.dumps(sorted(used | new_keys), ensure_ascii=False), encoding="utf-8")
    
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
