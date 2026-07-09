#!/usr/bin/env python3
"""
post_room_video.py — 把 **视频动态** 发布到某个群组/房间(Matrix room)并在群聊中显示。

结合两个现有脚本的能力(见 docs/06-post-video.md 与 docs/21-room-group-post.md):
  * post_video.py       : 视频 media_info(snake_case video_url/thumbnail_url) + S3 上传
  * post_room_moments.py: 房间两步发帖(POST moment(room_id) -> PUT m.room.message)

两步流程
    1. 登录拿 token + mxid
    2. POST UPLOAD_CREDENTIALS_URL 拿 S3 临时凭证
    3. 下载 opennana mp4 + 封面(带 Referer 绕过防盗链) -> boto3 上传 S3 -> 站内 URL
    4. POST ${ROOM_MOMENTS_API_URL}  body={content, room_id, is_async,
       media_info:{type:video, video_url, thumbnail_url}}  -> moment_id
    5. PUT  ${MATRIX_BASE}/{room}/send/m.room.message/{txn}
       body={msgtype:xxai.fee_message, post_id:moment_id, video_url, video_thumnail, ...}
       -> event_id (帖子在群聊显示)

素材从 opennana CSV(opennana_fetch.py --media-type video 产出)读取:
    列: content, _video_url, _cover_url

全部敏感配置从 .env / 环境变量读取, 不硬编码任何账号 / 密码 / room_id。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import mimetypes
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # noqa: BLE001
    pass

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    print("[FATAL] boto3 未安装。请先: py -3 -m pip install boto3", file=sys.stderr)
    raise


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


LOGIN_URL       = _env("LOGIN_URL", "https://testapi-x.tp-ex.com/login")
UPLOAD_CRED_URL = _env("UPLOAD_CREDENTIALS_URL", "https://testapi-x.tp-ex.com/file/upload/credentials")
MOMENTS_API_URL = _env("ROOM_MOMENTS_API_URL",
                       _env("MOMENTS_API_URL", "https://testapi-feed-x.tp-ex.com/api/v1/moments"))
MATRIX_BASE     = _env("MATRIX_API_BASE", "https://testd-x.tp-ex.com/_matrix/client/v3/rooms")
ROOM_FEED_URL   = _env("ROOM_FEED_URL", "https://testapi-feed-x.tp-ex.com/api/v1/feed/room_moments")

DEVICE_ID   = _env("POST_DEVICE_ID", "auto_poster")
DEVICE_NAME = _env("POST_DEVICE_NAME", "auto_poster_client")
TIMEOUT     = int(_env("POST_REQUEST_TIMEOUT", "30") or "30")

OPENNANA_REFERER = _env("OPENNANA_REFERER", "https://opennana.com/")
OPENNANA_UA = _env(
    "OPENNANA_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)

MEDIA_DIR = Path(_env("ROOM_POST_MEDIA_DIR", "media"))


def log(msg: str) -> None:
    print(msg, flush=True)


# --------------------------------------------------------------------------- #
# 认证
# --------------------------------------------------------------------------- #
class Session:
    def __init__(self, token: str, mxid: str):
        self.token = token
        self.mxid = mxid
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Device-Id": DEVICE_ID,
            "Device-Name": "iPhone",
            "Device-OS": "iOS",
            "Device-OS-Version": "26.1",
            "Accept-Language": "zh-Hans",
        }


def login(email: str, password: str) -> Session:
    r = requests.post(
        LOGIN_URL,
        json={"email": email.strip(), "password": password.strip(),
              "device_id": DEVICE_ID, "device_name": DEVICE_NAME},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    j = r.json()
    if j.get("code") not in (0, None):
        raise RuntimeError(f"login failed: {j}")
    data = j.get("data") or {}
    token = data.get("token") or data.get("access_token")
    mxid = data.get("mxid")
    if not token or not mxid:
        raise RuntimeError(f"login response missing token/mxid: {j}")
    log(f"[login] {email} -> mxid={mxid}, token={token[:12]}...")
    return Session(token, mxid)


# --------------------------------------------------------------------------- #
# S3 上传
# --------------------------------------------------------------------------- #
def get_s3_creds(sess: Session) -> dict:
    r = requests.post(UPLOAD_CRED_URL, headers=sess.headers, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    creds = j.get("data") or j
    required = ("access_key_id", "secret_access_key", "session_token", "region", "bucket", "domain")
    missing = [k for k in required if not creds.get(k)]
    if missing:
        raise RuntimeError(f"upload-credentials missing keys: {missing}, raw={j}")
    return creds


def download(url_or_path: str, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    if os.path.exists(url_or_path):
        return Path(url_or_path)
    parsed = urlparse(url_or_path)
    suffix = Path(parsed.path).suffix or ".bin"
    dst = target_dir / f"{uuid.uuid4().hex}{suffix}"
    headers = {"User-Agent": OPENNANA_UA, "Referer": OPENNANA_REFERER}
    with requests.get(url_or_path, stream=True, headers=headers, timeout=120) as r:
        r.raise_for_status()
        with dst.open("wb") as fh:
            for chunk in r.iter_content(1 << 16):
                fh.write(chunk)
    return dst


def upload_to_s3(local: Path, creds: dict) -> str:
    today = dt.datetime.utcnow()
    key = f"square/original/{today:%Y/%m/%d}/{local.name}"
    content_type = mimetypes.guess_type(local.name)[0]
    if not content_type:
        content_type = "video/mp4" if local.suffix.lower() == ".mp4" else "application/octet-stream"
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


# --------------------------------------------------------------------------- #
# 发帖两步(视频)
# --------------------------------------------------------------------------- #
def create_video_moment(sess: Session, content: str, room_id: str,
                        video_url: str, thumbnail_url: str,
                        is_async: bool) -> str | None:
    payload = {
        "content": content,
        "room_id": room_id,
        "is_async": is_async,
        "media_info": {
            "type": "video",
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
        },
    }
    r = requests.post(MOMENTS_API_URL, headers=sess.headers, json=payload, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        log(f"    [POST moment] HTTP {r.status_code} {r.text}")
        return None
    j = r.json()
    if j.get("code") not in (0, None):
        log(f"    [POST moment] code!=0 {r.text}")
        return None
    return (j.get("data") or {}).get("moment_id") or j.get("moment_id")


def send_video_to_room(sess: Session, room_id: str, post_id: str, content: str,
                       video_url: str, thumbnail_url: str) -> str | None:
    txn = f"{sess.mxid}-11-{int(time.time() * 1000)}"
    url = (f"{MATRIX_BASE}/{requests.utils.quote(room_id, safe='')}"
           f"/send/m.room.message/{requests.utils.quote(txn, safe='')}")
    payload = {
        "msgtype": "xxai.fee_message",
        "body": content,
        "content": content,
        "post_id": post_id,
        "is_sync": False,
        "images_url": [],
        "video_url": video_url,
        "video_thumnail": thumbnail_url,  # 保持后端接口原拼写(thumnail)
    }
    r = requests.put(url, headers=sess.headers, json=payload, timeout=TIMEOUT)
    if r.status_code != 200:
        log(f"    [PUT m.room.message] HTTP {r.status_code} {r.text}")
        return None
    return r.json().get("event_id")


# --------------------------------------------------------------------------- #
# 素材读取(opennana video CSV)
# --------------------------------------------------------------------------- #
def rows_from_csv(path: str, limit: int) -> list[dict]:
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            content = (row.get("content") or "").strip()
            video = (row.get("_video_url") or "").strip()
            cover = (row.get("_cover_url") or "").strip()
            if not content or not video:
                continue
            out.append({"content": content, "video_url": video, "cover_url": cover})
            if limit and len(out) >= limit:
                break
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="发布视频动态到群组/房间(Matrix room)并在群聊显示")
    ap.add_argument("--csv", required=True, help="opennana video CSV (含 _video_url/_cover_url)")
    ap.add_argument("--email", default=os.getenv("ROOM_POST_EMAIL"))
    ap.add_argument("--password", default=os.getenv("ROOM_POST_PASSWORD"))
    ap.add_argument("--room-id", default=os.getenv("ROOM_POST_ROOM_ID"))
    ap.add_argument("--limit", type=int, default=0, help="最多发几条(0=全部)")
    ap.add_argument("--rows", default="", help="只发指定行(1-based, 逗号分隔), 如 1,2,3,5")
    ap.add_argument("--square", action="store_true", help="同时复制一份到广场(is_async=true)")
    ap.add_argument("--delay", type=float, default=2.0, help="每条帖之间的间隔秒数")
    ap.add_argument("--media-dir", default=str(MEDIA_DIR), help="下载素材本地缓存目录")
    ap.add_argument("--dry-run", action="store_true", help="只装配不实际发布")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if not args.email or not args.password:
        log("[error] 缺少账号: --email/--password 或 ROOM_POST_EMAIL/ROOM_POST_PASSWORD")
        return 2
    if not args.room_id:
        log("[error] 缺少房间: --room-id 或 ROOM_POST_ROOM_ID")
        return 2

    tasks = rows_from_csv(args.csv, args.limit)
    if args.rows.strip():
        want = {int(x) for x in args.rows.split(",") if x.strip().isdigit()}
        tasks = [t for i, t in enumerate(tasks, start=1) if i in want]
    if not tasks:
        log("[warn] 没有可发布的视频素材")
        return 1

    is_async = bool(args.square)
    media_dir = Path(args.media_dir)

    if args.dry_run:
        log(f"[dry-run] 将发布 {len(tasks)} 条视频到 room={args.room_id} is_async={is_async}:")
        for i, t in enumerate(tasks, start=1):
            log(f"  {i}. {t['content'][:40]}")
            log(f"     video={t['video_url']}")
        return 0

    sess = login(args.email, args.password)
    creds = get_s3_creds(sess)
    log(f"[s3] bucket={creds['bucket']} domain={creds['domain']} region={creds['region']}")

    published = []
    for i, t in enumerate(tasks, start=1):
        log(f"\n=== 视频 {i}/{len(tasks)} is_async={is_async} ===")
        log(f"    {t['content'][:50]}")
        try:
            lv = download(t["video_url"], media_dir)
            lc = download(t["cover_url"], media_dir) if t["cover_url"] else None
            vurl = upload_to_s3(lv, creds)
            curl = upload_to_s3(lc, creds) if lc else ""
            log(f"    video_url     = {vurl}")
            log(f"    thumbnail_url = {curl}")
        except Exception as e:  # noqa: BLE001
            log(f"    [FAIL] 下载/上传失败: {e}")
            continue

        mid = create_video_moment(sess, t["content"], args.room_id, vurl, curl, is_async)
        if not mid:
            log("    [FAIL] 创建动态失败")
            continue
        eid = send_video_to_room(sess, args.room_id, mid, t["content"], vurl, curl)
        if not eid:
            log(f"    [WARN] 动态已建(moment_id={mid})但群消息发送失败(帖子可能不显示在群聊)")
            continue
        log(f"    [OK] moment_id={mid} event_id={eid}")
        published.append((mid, eid))
        time.sleep(args.delay)

    log("\n" + "=" * 60)
    log(f"完成: 成功 {len(published)}/{len(tasks)} 条")
    for mid, eid in published:
        log(f"  - moment_id={mid} event_id={eid}")
    return 0 if published else 1


if __name__ == "__main__":
    sys.exit(main())
