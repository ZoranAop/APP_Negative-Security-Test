#!/usr/bin/env python3
"""
post_room_moments.py — 把动态发布到某个 **群组 / 房间（Matrix room）** 并在群聊中显示。

与 ``post_moments.py`` 的区别
    ``post_moments.py`` 只做第 1 步（创建动态）。发到房间时，动态虽然进入
    房间的 feed，但**不会作为一条消息出现在群聊里**。本脚本补上第 2 步：
    向 Matrix ``m.room.message`` 端点 PUT 一条 ``xxai.fee_message``，
    使帖子真正显示在群聊中。

两步流程
    1. POST  ${MOMENTS_API_URL}                       -> 创建动态, 拿 moment_id
       body: {content, room_id, is_async, media_info}
    2. PUT   ${MATRIX_BASE}/rooms/{room}/send/m.room.message/{txn}
       body: {msgtype: "xxai.fee_message", body, content, post_id, images_url, ...}
       -> 帖子在群聊显示, 返回 event_id

认证
    先用 ``POST ${LOGIN_URL}`` 换取登录响应, 其 ``data`` 同时含:
      - ``token`` : 同一枚 token 兼容 **发帖 API** 和 **Matrix 消息接口**
      - ``mxid``  : Matrix 用户 ID（如 @user_26:xxai.com）, 用于构造事务 ID
    发帖账号必须是目标房间的**创建者 / 有发帖权限**, 否则后端返回
    ``code=50006 只有房间创建者可以在该房间发帖``。

关键参数：is_async（广场发帖开关）
    room_id 非空时:
      - is_async=true  -> 发到房间的同时, 后端**再复制一条公开帖到广场**
                          (响应含 public_moment_id)
      - is_async=false -> **只发到房间, 不进广场**（默认, 见 --square）

多图聚合
    某些图片源（如 tuziyouwang.com）每个详情页只有 1 张原图。用 --group-size N
    可把多张图**聚合成一条多图帖**（N=2/4/9…）。也支持逗号分隔的混合分配,
    如 --group-plan 4,4,2,4,2 表示 5 条帖分别 4/4/2/4/2 张图。

素材来源（三选一）
    --csv FILE          读取 moments CSV（表头见 docs/03 / docs/14；room_id 列可留空,
                        用 --room-id 覆盖）。图片列 image_urls 里若是外部 URL,
                        会自动下载并转存到 S3。
    --tuzi-column SLUG  直接从 tuziyouwang.com 抓某栏目（xiongqi/meitui/…）的原图,
                        配合 --group-plan / --group-size 聚合成多图帖。
    --text "文案"       发一条纯文字帖。

全部敏感配置从 .env / 环境变量读取, 脚本内**不硬编码任何账号 / 密码 / token / room_id**。
详见 docs/21-room-group-post.md 与 docs/runbooks/run-room-group-post.md。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
import time
from pathlib import Path
from typing import Iterable

import requests

try:
    import boto3  # optional, only needed when uploading external images to S3
except ImportError:  # pragma: no cover
    boto3 = None

# ---------------------------------------------------------------------------
# 配置（全部来自环境变量 / .env）
# ---------------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


LOGIN_URL       = _env("LOGIN_URL", "https://testapi-x.tp-ex.com/login")
UPLOAD_CRED_URL = _env("UPLOAD_CREDENTIALS_URL", "https://testapi-x.tp-ex.com/file/upload/credentials")
# 房间发帖走 feed 网关域名（客户端实测）；也可用内网 MOMENTS_API_URL。
MOMENTS_API_URL = _env("ROOM_MOMENTS_API_URL",
                       _env("MOMENTS_API_URL", "https://testapi-feed-x.tp-ex.com/api/v1/moments"))
# Matrix client-server API base（到 /rooms 的前缀）
MATRIX_BASE     = _env("MATRIX_API_BASE", "https://testd-x.tp-ex.com/_matrix/client/v3/rooms")
# 读房间 feed（核对用）
ROOM_FEED_URL   = _env("ROOM_FEED_URL", "http://100.64.0.53:8889/api/v1/feed/room_moments")

DEVICE_ID   = _env("POST_DEVICE_ID", "auto_poster")
DEVICE_NAME = _env("POST_DEVICE_NAME", "auto_poster_client")
TIMEOUT     = int(_env("POST_REQUEST_TIMEOUT", "20") or "20")
MAX_IMAGES  = int(_env("POST_MAX_IMAGES", "9") or "9")

TUZI_BASE = _env("TUZI_BASE", "http://tuziyouwang.com")
UA = _env("TUZI_USER_AGENT",
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

IMG_DIR = Path(_env("ROOM_POST_IMG_DIR", "images"))


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------
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
    token = data.get("token")
    mxid = data.get("mxid")
    if not token or not mxid:
        raise RuntimeError(f"login response missing token/mxid: {j}")
    log(f"[login] {email} -> mxid={mxid}, token={token[:12]}...")
    return Session(token, mxid)


# ---------------------------------------------------------------------------
# S3 上传（外部图片 URL -> 站内 URL）
# ---------------------------------------------------------------------------
def get_s3_creds(sess: Session) -> dict:
    r = requests.post(UPLOAD_CRED_URL, headers=sess.headers, timeout=TIMEOUT)
    r.raise_for_status()
    j = r.json()
    if j.get("code") != 0:
        raise RuntimeError(f"upload creds fail: {j}")
    return j["data"]


def _referer_for(url: str) -> str:
    if "tuziyouwang" in url:
        return f"{TUZI_BASE}/"
    from urllib.parse import urlsplit
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}/" if p.scheme and p.netloc else ""


def upload_to_s3(image_url: str, creds: dict, cache: dict[str, str]) -> str:
    """下载外部图片并转存 S3, 返回站内 URL。已缓存则直接返回。"""
    if image_url in cache:
        return cache[image_url]
    if boto3 is None:
        raise RuntimeError("boto3 not installed; run `pip install boto3`")
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(image_url.encode()).hexdigest()[:12]
    ext = ".jpg"
    for e in (".png", ".webp", ".gif"):
        if e in image_url.lower():
            ext = e
            break
    local = IMG_DIR / f"downloaded_{h}{ext}"
    if not (local.exists() and local.stat().st_size > 0):
        rr = requests.get(image_url, timeout=30,
                          headers={"User-Agent": UA, "Referer": _referer_for(image_url)})
        if rr.status_code != 200 or not rr.content:
            raise RuntimeError(f"download HTTP {rr.status_code} for {image_url}")
        local.write_bytes(rr.content)
    s3 = boto3.client(
        "s3",
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds["session_token"],
        region_name=creds.get("region", "ap-northeast-1"),
    )
    key = f"square/original/{time.strftime('%Y/%m/%d')}/{local.name}"
    ct = "image/jpeg" if ext == ".jpg" else f"image/{ext.strip('.')}"
    s3.upload_file(str(local), creds["bucket"], key,
                   ExtraArgs={"ContentType": ct,
                              "CacheControl": "public, max-age=31536000, immutable"})
    domain = creds.get("domain", "teststatic-x.tp-ex.com")
    aws_url = f"https://{domain}/{key}"
    cache[image_url] = aws_url
    return aws_url


def _is_external(url: str) -> bool:
    return url.startswith("http") and "tp-ex.com" not in url and "xxai.com" not in url


def ensure_s3(images: list[str], sess: Session, creds_box: dict, cache: dict) -> list[str]:
    """把 images 里的外部 URL 转存 S3；站内 URL 原样保留。"""
    out = []
    for u in images[:MAX_IMAGES]:
        if _is_external(u):
            if not creds_box.get("creds"):
                creds_box["creds"] = get_s3_creds(sess)
            out.append(upload_to_s3(u, creds_box["creds"], cache))
        else:
            out.append(u)
    return out


# ---------------------------------------------------------------------------
# tuziyouwang.com 抓图（每个详情页取第一张原图 /d/file/*）
# ---------------------------------------------------------------------------
def _get_html(url: str, referer: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA,
                                   "Accept-Language": "zh-CN,zh;q=0.9",
                                   "Referer": referer}, timeout=30)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="ignore")


def tuzi_list_ids(column: str, want: int) -> list[str]:
    ids, seen = [], set()
    page = 1
    while len(ids) < want and page <= 8:
        url = f"{TUZI_BASE}/{column}/" if page == 1 else f"{TUZI_BASE}/{column}/index_{page}.html"
        try:
            txt = _get_html(url, f"{TUZI_BASE}/{column}/")
        except Exception as e:  # noqa: BLE001
            log(f"[warn] list {url}: {e}")
            break
        for aid in re.findall(rf"/{column}/(\d+)\.html", txt):
            if aid not in seen:
                seen.add(aid)
                ids.append(aid)
        page += 1
        time.sleep(0.3)
    return ids


def tuzi_first_photo(column: str, aid: str) -> str | None:
    txt = _get_html(f"{TUZI_BASE}/{column}/{aid}.html", f"{TUZI_BASE}/{column}/")
    for u in re.findall(r'(?:src|data-original)="(/d/file/[^"]+\.(?:jpg|jpeg|png|webp))"', txt, re.I):
        return u if u.startswith("http") else TUZI_BASE + u
    return None


def tuzi_collect(column: str, need: int) -> list[str]:
    """抓 need 张原图 URL（外部）。"""
    urls: list[str] = []
    for aid in tuzi_list_ids(column, need + 8):
        if len(urls) >= need:
            break
        try:
            p = tuzi_first_photo(column, aid)
        except Exception as e:  # noqa: BLE001
            log(f"[warn] tuzi aid={aid}: {e}")
            continue
        if p:
            urls.append(p)
    return urls


# ---------------------------------------------------------------------------
# 发帖两步
# ---------------------------------------------------------------------------
def create_moment(sess: Session, content: str, room_id: str,
                  images: list[str] | None, is_async: bool,
                  visibility: int | None = None) -> str | None:
    if images:
        media = {"type": "image", "images": images}
    else:
        media = {"type": "text"}
    payload = {"content": content, "room_id": room_id,
               "is_async": is_async, "media_info": media}
    if visibility is not None:
        payload["visibility"] = visibility
    r = requests.post(MOMENTS_API_URL, headers=sess.headers, json=payload, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        log(f"    [POST moment] HTTP {r.status_code} {r.text}")
        return None
    j = r.json()
    if j.get("code") not in (0, None):
        log(f"    [POST moment] code!=0 {r.text}")
        return None
    return (j.get("data") or {}).get("moment_id") or j.get("moment_id")


def send_to_room(sess: Session, room_id: str, post_id: str,
                 content: str, images: list[str] | None) -> str | None:
    txn = f"{sess.mxid}-11-{int(time.time() * 1000)}"
    url = (f"{MATRIX_BASE}/{requests.utils.quote(room_id, safe='')}"
           f"/send/m.room.message/{requests.utils.quote(txn, safe='')}")
    payload = {
        "msgtype": "xxai.fee_message",
        "body": content,
        "content": content,
        "post_id": post_id,
        "is_sync": False,
        "images_url": images or [],
        "video_url": "",
        "video_thumnail": "",  # 保持后端接口原拼写
    }
    r = requests.put(url, headers=sess.headers, json=payload, timeout=TIMEOUT)
    if r.status_code != 200:
        log(f"    [PUT m.room.message] HTTP {r.status_code} {r.text}")
        return None
    return r.json().get("event_id")


def publish_one(sess: Session, room_id: str, content: str,
                images: list[str] | None, is_async: bool) -> tuple[str, str] | None:
    mid = create_moment(sess, content, room_id, images, is_async)
    if not mid:
        return None
    eid = send_to_room(sess, room_id, mid, content, images)
    if not eid:
        return None
    return mid, eid


# ---------------------------------------------------------------------------
# 素材装配
# ---------------------------------------------------------------------------
def _parse_bool(v: str):
    v = (v or "").strip().lower()
    if v in ("1", "true", "yes", "y", "t"):
        return True
    if v in ("0", "false", "no", "n", "f"):
        return False
    return None


def rows_from_csv(path: str, room_id: str) -> Iterable[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            content = (row.get("content") or "").strip()
            if not content:
                continue
            imgs = [u.strip() for u in (row.get("image_urls") or "").split(",") if u.strip()]
            rid = (row.get("room_id") or "").strip() or room_id
            yield {"content": content, "images": imgs, "room_id": rid,
                   "is_async": _parse_bool(row.get("is_async", ""))}


def plan_groups(images: list[str], group_plan: list[int] | None,
                group_size: int) -> list[list[str]]:
    """把一串图片按 group_plan（混合张数）或 group_size（固定张数）切成多条帖。"""
    groups: list[list[str]] = []
    idx = 0
    if group_plan:
        for cnt in group_plan:
            chunk = images[idx: idx + cnt]
            idx += cnt
            if chunk:
                groups.append(chunk)
    else:
        size = max(1, group_size)
        while idx < len(images):
            groups.append(images[idx: idx + size])
            idx += size
    return groups


def load_captions(path: str | None) -> list[str]:
    if not path:
        return []
    return [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="发布动态到群组/房间(Matrix room)并在群聊显示")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="moments CSV 素材文件")
    src.add_argument("--tuzi-column", help="从 tuziyouwang.com 抓某栏目(如 xiongqi/meitui)")
    src.add_argument("--text", help="发一条纯文字帖")

    ap.add_argument("--email", default=os.getenv("ROOM_POST_EMAIL"),
                    help="发帖账号邮箱(默认读环境变量 ROOM_POST_EMAIL)")
    ap.add_argument("--password", default=os.getenv("ROOM_POST_PASSWORD"),
                    help="发帖账号密码(默认读环境变量 ROOM_POST_PASSWORD)")
    ap.add_argument("--room-id", default=os.getenv("ROOM_POST_ROOM_ID"),
                    help="目标房间 Matrix ID, 如 !xxx:xxai.com (默认读 ROOM_POST_ROOM_ID)")

    ap.add_argument("--square", action="store_true",
                    help="同时复制一份到广场(is_async=true)。默认 false=只进群")
    ap.add_argument("--group-size", type=int, default=1,
                    help="tuzi 源: 每条帖聚合多少张图(默认1)")
    ap.add_argument("--group-plan", default="",
                    help="tuzi 源: 逗号分隔的混合张数, 如 4,4,2,4,2")
    ap.add_argument("--num-posts", type=int, default=5,
                    help="tuzi 源在无 --group-plan 时要发的帖子数(默认5)")
    ap.add_argument("--captions-file", default=None,
                    help="每行一个文案, 依次套用到各条帖(可选)")
    ap.add_argument("--delay", type=float, default=1.5, help="每条帖之间的间隔秒数")
    ap.add_argument("--dry-run", action="store_true", help="只装配不实际发布")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if not args.email or not args.password:
        log("[error] 缺少账号: 用 --email/--password 或环境变量 ROOM_POST_EMAIL/ROOM_POST_PASSWORD")
        return 2
    if not args.room_id and not args.csv:
        log("[error] 缺少房间: 用 --room-id 或环境变量 ROOM_POST_ROOM_ID(CSV 里也可带 room_id 列)")
        return 2

    is_async = bool(args.square)
    group_plan = [int(x) for x in args.group_plan.split(",") if x.strip()] if args.group_plan else None
    captions = load_captions(args.captions_file)

    # ---- 装配待发帖子列表 [{content, images, room_id}] ----
    tasks: list[dict] = []
    if args.text:
        tasks.append({"content": args.text, "images": [], "room_id": args.room_id})
    elif args.csv:
        tasks = list(rows_from_csv(args.csv, args.room_id or ""))
    elif args.tuzi_column:
        need = sum(group_plan) if group_plan else args.num_posts * max(1, args.group_size)
        log(f"[tuzi] 抓取栏目 {args.tuzi_column}, 需要 {need} 张原图")
        ext_urls = tuzi_collect(args.tuzi_column, need)
        log(f"[tuzi] 拿到 {len(ext_urls)} 张原图")
        groups = plan_groups(ext_urls, group_plan, args.group_size)
        for i, g in enumerate(groups):
            cap = captions[i % len(captions)] if captions else f"分享 #{i + 1}"
            tasks.append({"content": cap, "images": g, "room_id": args.room_id})

    if not tasks:
        log("[warn] 没有可发布的素材")
        return 1

    if args.dry_run:
        log(f"[dry-run] 将发布 {len(tasks)} 条:")
        for i, t in enumerate(tasks):
            log(f"  {i+1}. room={t['room_id']} imgs={len(t['images'])} | {t['content'][:30]}")
        return 0

    # ---- 登录 + 逐条发布 ----
    sess = login(args.email, args.password)
    creds_box: dict = {}
    cache: dict[str, str] = {}
    published = []
    for i, t in enumerate(tasks):
        rid = t.get("room_id") or args.room_id
        if not rid:
            log(f"[skip] 帖子 {i+1}: 无 room_id")
            continue
        imgs = ensure_s3(t["images"], sess, creds_box, cache) if t["images"] else []
        row_async = t.get("is_async")
        eff_async = row_async if row_async is not None else is_async
        log(f"\n=== 帖子 {i+1}/{len(tasks)}  imgs={len(imgs)} is_async={eff_async} ===")
        log(f"    {t['content'][:40]}")
        res = publish_one(sess, rid, t["content"], imgs, eff_async)
        if not res:
            log("    [FAIL]")
            continue
        mid, eid = res
        log(f"    [OK] moment_id={mid} event_id={eid}")
        published.append((mid, eid, len(imgs)))
        time.sleep(args.delay)

    log("\n" + "=" * 60)
    log(f"完成: 成功 {len(published)}/{len(tasks)} 条")
    for mid, _eid, n in published:
        log(f"  - {n}图 moment_id={mid}")
    return 0 if published else 1


if __name__ == "__main__":
    sys.exit(main())
