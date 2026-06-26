#!/usr/bin/env python3
"""
post_video.py — 向 XXAI 广场发布视频动态。

流程：
    1. 用 --account 在 accounts CSV 里找对应账号，登录 LOGIN_URL 拿 Bearer token。
    2. POST UPLOAD_CREDENTIALS_URL 拿 S3 临时凭证。
    3. 下载视频 + 封面图（带 Referer 绕过防盗链）。
    4. 用 boto3 上传到 S3，key = square/original/YYYY/MM/DD/<filename>。
    5. POST MOMENTS_API_URL，body 含 video media_info（snake_case：video_url / thumbnail_url）。

完整说明：docs/06-post-video.md
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
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    print("[FATAL] boto3 未安装。请先：py -3 -m pip install boto3", file=sys.stderr)
    raise

# 复用 config.py 的全局配置（统一走 .env）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import config  # noqa: E402

UPLOAD_CREDENTIALS_URL = os.getenv(
    "UPLOAD_CREDENTIALS_URL",
    "https://devapi-x.tp-ex.com/file/upload/credentials",
)

OPENNANA_REFERER = os.getenv("OPENNANA_REFERER", "https://opennana.com/")
OPENNANA_USER_AGENT = os.getenv(
    "OPENNANA_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def find_account(accounts_csv: Path, identifier: str) -> Tuple[str, str]:
    """从 CSV 里按邮箱 / user_id 查 (email, password)。"""
    if not accounts_csv.exists():
        raise FileNotFoundError(f"accounts CSV not found: {accounts_csv}")
    with accounts_csv.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            email = next(
                (row[k] for k in config.ACCOUNTS_CSV_EMAIL_FIELDS if k in row and row[k]),
                None,
            )
            password = next(
                (row[k] for k in config.ACCOUNTS_CSV_PASSWORD_FIELDS if k in row and row[k]),
                None,
            )
            user_id = row.get("user_id") or row.get("uid") or ""
            if email and password and (email == identifier or user_id == identifier):
                return email, password
    raise LookupError(f"account {identifier!r} not found in {accounts_csv}")


def login(email: str, password: str) -> str:
    """登录并返回 Bearer token。"""
    payload = {
        "username": email,
        "password": password,
        "device_id": config.POST_DEVICE_ID,
        "device_name": config.POST_DEVICE_NAME,
    }
    resp = requests.post(config.LOGIN_URL, json=payload, timeout=config.POST_REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    # 兼容若干常见结构
    token = (
        data.get("access_token")
        or data.get("token")
        or (data.get("data") or {}).get("access_token")
        or (data.get("data") or {}).get("token")
    )
    if not token:
        raise RuntimeError(f"login: cannot extract token from response: {data}")
    return token


def get_upload_credentials(token: str) -> dict:
    resp = requests.post(
        UPLOAD_CREDENTIALS_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=config.POST_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    creds = data.get("data") or data
    required = ("access_key_id", "secret_access_key", "session_token", "region", "bucket", "domain")
    missing = [k for k in required if not creds.get(k)]
    if missing:
        raise RuntimeError(f"upload-credentials missing keys: {missing}, raw={data}")
    return creds


def download(url_or_path: str, target_dir: Path) -> Path:
    """下载或拷贝到本地。返回本地文件路径。"""
    target_dir.mkdir(parents=True, exist_ok=True)
    if os.path.exists(url_or_path):  # 本地路径
        return Path(url_or_path)

    parsed = urlparse(url_or_path)
    suffix = Path(parsed.path).suffix or ".bin"
    name = f"{uuid.uuid4().hex}{suffix}"
    dst = target_dir / name

    headers = {
        "User-Agent": OPENNANA_USER_AGENT,
        "Referer": OPENNANA_REFERER,
    }
    with requests.get(url_or_path, stream=True, headers=headers, timeout=60) as r:
        r.raise_for_status()
        with dst.open("wb") as fh:
            for chunk in r.iter_content(1 << 16):
                fh.write(chunk)
    return dst


def upload_to_s3(local: Path, creds: dict) -> str:
    """上传到 S3，返回公网 URL。"""
    today = dt.datetime.utcnow()
    key = f"square/original/{today:%Y/%m/%d}/{local.name}"

    content_type = mimetypes.guess_type(local.name)[0] or (
        "video/mp4" if local.suffix.lower() == ".mp4" else "application/octet-stream"
    )

    s3 = boto3.client(
        "s3",
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds["session_token"],
        region_name=creds["region"],
        config=BotoConfig(signature_version="s3v4"),
    )
    s3.upload_file(
        str(local),
        creds["bucket"],
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return f"https://{creds['domain']}/{key}"


def publish_video(
    token: str,
    *,
    caption: str,
    video_url: str,
    thumbnail_url: str,
    visibility: int = 0,
    room_id: Optional[str] = None,
) -> dict:
    body = {
        "content": caption,
        "visibility": visibility,
        "media_info": {
            "type": "video",
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
        },
    }
    if room_id:
        body["room_id"] = room_id

    resp = requests.post(
        config.MOMENTS_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=config.POST_REQUEST_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"publish video failed: {resp.status_code} {resp.text}")
    return resp.json()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="发布视频动态到 XXAI 广场")
    ap.add_argument("--account", required=True, help="账号邮箱或 user_id")
    ap.add_argument("--accounts-csv", default=config.POST_DEFAULT_ACCOUNTS_CSV)
    ap.add_argument("--video", required=True, help="本地路径或 URL")
    ap.add_argument("--cover", required=True, help="本地路径或 URL (.png/.jpg)")
    ap.add_argument("--caption", required=True, help="正文")
    ap.add_argument("--visibility", type=int, default=0, choices=(0, 1, 2))
    ap.add_argument("--room-id", default=None)
    ap.add_argument("--media-dir", default="media", help="下载素材的本地缓存目录")
    args = ap.parse_args()

    accounts_csv = Path(args.accounts_csv)
    media_dir = Path(args.media_dir)

    print(f"[1/5] 解析账号 {args.account} …")
    email, password = find_account(accounts_csv, args.account)

    print(f"[2/5] 登录 {email} …")
    token = login(email, password)

    print("[3/5] 获取 S3 上传凭证 …")
    creds = get_upload_credentials(token)

    print("[4/5] 下载并上传视频 / 封面 …")
    local_video = download(args.video, media_dir)
    local_cover = download(args.cover, media_dir)
    video_url = upload_to_s3(local_video, creds)
    cover_url = upload_to_s3(local_cover, creds)
    print(f"      video_url     = {video_url}")
    print(f"      thumbnail_url = {cover_url}")

    print("[5/5] 发布动态 …")
    result = publish_video(
        token,
        caption=args.caption,
        video_url=video_url,
        thumbnail_url=cover_url,
        visibility=args.visibility,
        room_id=args.room_id,
    )
    moment_id = (result.get("data") or {}).get("id") or result.get("id") or result
    print(f"[OK] moment_id = {moment_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
