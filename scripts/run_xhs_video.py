#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_xhs_video.py — 小红书视频采集 → 批量发布到 XXAI 广场（一键脚本）。

★ 完整流程 ★
  1. 从小红书 explore 推荐流采集视频笔记（type=video，CDN 直链，不落地本地）
  2. 从 test/dev 企管用户表中选取 N 个用户
  3. 顺序登录（间隔可配，避免 429）→ S3 凭证 → 下载视频+封面 → S3 上传 → 发布
  4. 确保每条视频的文案描述与 #话题标签 语言一致

核心优化：
  - 视频大小过滤：采集阶段 HEAD 预检 + 下载后二次校验（默认 ≤15MB，可配）
  - 视频时长过滤：详情页提取 duration 字段，默认 ≤90s（可配 --max-duration）
  - 登录字段自适应：test 环境用 email / dev 环境用 username
  - Referer 自动映射：xhscdn.com → xiaohongshu.com Referer（避免 403）
  - 封面多级 fallback：video.image → imageList[0] → explore feed cover
  - 失败自动重试：下载超时自动切换备用视频，不卡死整个流程
  - 文案标签一致性：保留原始标签或根据内容语言自动推导

用法：
    # 20 用户各发 1 个视频（默认）
    py -3 scripts/run_xhs_video.py --accounts-xlsx test_企管用户_邮箱密码pincode_500.csv.xlsx --num-users 20

    # 指定视频数量和环境
    py -3 scripts/run_xhs_video.py --accounts-xlsx accounts.xlsx --num-users 10 --env test

    # 限制视频大小为 10MB 以内
    py -3 scripts/run_xhs_video.py --accounts-xlsx accounts.xlsx --num-users 10 --max-video-size 10

    # 限制视频时长为 60 秒以内
    py -3 scripts/run_xhs_video.py --accounts-xlsx accounts.xlsx --num-users 10 --max-duration 60

    # 只采集不发布（预览模式）
    py -3 scripts/run_xhs_video.py --crawl-only --target 30 --output my_videos.csv

    # 从已有 CSV 发布（跳过采集）
    py -3 scripts/run_xhs_video.py --accounts-xlsx accounts.xlsx --csv moments_video.csv --num-users 20

环境变量（可选，优先级高于默认值）：
    LOGIN_URL / UPLOAD_CREDENTIALS_URL / MOMENTS_API_URL
    详见 .env.example

完整文档：docs/16-xiaohongshu-square.md §16.8
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import mimetypes
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# ─── UTF-8 stdout（Windows GBK 兼容）───────────────────────────────────────
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", write_through=True)
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    print("[FATAL] boto3 未安装。请先: py -3 -m pip install boto3", file=sys.stderr)
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    print("[FATAL] openpyxl 未安装。请先: py -3 -m pip install openpyxl", file=sys.stderr)
    sys.exit(1)

from config import config

# ═══════════════════════════════════════════════════════════════════════════════
# 常量 & 配置
# ═══════════════════════════════════════════════════════════════════════════════

XHS_EXPLORE_URL = "https://www.xiaohongshu.com/explore"
XHS_NOTE_URL_TPL = "https://www.xiaohongshu.com/explore/{note_id}"
XHS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.xiaohongshu.com/",
}

# Referer 映射表（域名子串 → 请求时附带的 Referer）
REFERER_MAP = {
    "xhscdn.com": "https://www.xiaohongshu.com/",
    "xiaohongshu.com": "https://www.xiaohongshu.com/",
    "opennana.com": "https://opennana.com/",
}

# 话题标签推导映射（content 关键词 → 标签列表）
TOPIC_TAG_MAP = {
    "美食": ["美食", "吃货", "日常"],
    "做饭": ["美食", "做饭", "家常菜"],
    "早餐": ["早餐", "美食", "日常"],
    "拌面": ["美食", "一人食", "日常"],
    "减肥": ["减肥", "健身", "健康"],
    "瘦腿": ["减肥", "健身", "日常"],
    "腹肌": ["健身", "运动", "马甲线"],
    "穿搭": ["穿搭", "时尚", "日常"],
    "睡衣": ["穿搭", "好物分享", "日常"],
    "化妆": ["化妆", "美妆", "日常"],
    "眼妆": ["美妆", "化妆教程", "日常"],
    "护肤": ["护肤", "美妆", "日常"],
    "水光": ["护肤", "医美", "日常"],
    "旅行": ["旅行", "旅游", "日常"],
    "旅游": ["旅行", "旅游", "日常"],
    "唱歌": ["唱歌", "声乐", "日常"],
    "书法": ["书法", "练字", "日常"],
    "收纳": ["收纳", "家居", "日常"],
    "盲盒": ["盲盒", "玩具", "日常"],
    "蛋糕": ["甜点", "烘焙", "美食"],
    "奶酪": ["美食", "甜点", "日常"],
    "甜点": ["甜点", "烘焙", "美食"],
    "咖啡": ["咖啡", "生活", "日常"],
    "校招": ["校招", "求职", "日常"],
    "旗袍": ["旗袍", "国风", "手工"],
    "国风": ["国风", "传统文化", "日常"],
    "猫": ["猫咪", "萌宠", "日常"],
    "狗": ["萌宠", "狗狗", "日常"],
}

DEFAULT_TAGS_FALLBACK = ["日常", "生活", "记录"]

# 视频大小策略（默认值，可通过 CLI --max-video-size 覆盖）
DEFAULT_MAX_VIDEO_SIZE_MB = 15  # 默认最大 15MB
DEFAULT_MIN_VIDEO_SIZE_MB = 0.5  # 最小 0.5MB（过小可能是损坏文件）

# 视频时长策略（默认值，可通过 CLI --max-duration 覆盖）
DEFAULT_MAX_VIDEO_DURATION_SEC = 90  # 默认最长 90 秒


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def log(msg: str) -> None:
    print(msg, flush=True)


def resolve_referer(url: str) -> str:
    """根据 URL 域名自动选择正确的 Referer（避免防盗链 403）。"""
    hostname = urlparse(url).hostname or ""
    for domain_substr, referer in REFERER_MAP.items():
        if domain_substr in hostname:
            return referer
    return "https://www.xiaohongshu.com/"


def probe_video_size(url: str, timeout: int = 10) -> float:
    """
    通过 HEAD 请求探测视频文件大小（MB）。

    返回值：
      > 0: 实际大小（MB）
      -1: 无法获取（服务器不返回 Content-Length）

    用于采集阶段预过滤超大/超小视频，避免浪费下载带宽。
    """
    try:
        headers = {
            "User-Agent": XHS_HEADERS["User-Agent"],
            "Referer": resolve_referer(url),
        }
        resp = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        cl = resp.headers.get("Content-Length")
        if cl:
            return int(cl) / 1024 / 1024
    except Exception:
        pass
    return -1


def ensure_tag_consistency(content: str) -> str:
    """
    确保文案与话题标签的语言一致性。

    策略优先级：
      1. 原文已有 #标签 → 直接保留（小红书原始标签与内容语言/主题天然一致）
      2. 无标签 → 根据正文关键词推导对应语言的话题标签
      3. 兜底 → 通用标签 #日常 #生活 #记录
    """
    existing_tags = re.findall(r"#([^\s#]+)", content)
    if existing_tags:
        return content

    for keyword, tags in TOPIC_TAG_MAP.items():
        if keyword in content:
            tag_str = " ".join(f"#{t}" for t in tags)
            return f"{content} {tag_str}"

    tag_str = " ".join(f"#{t}" for t in DEFAULT_TAGS_FALLBACK)
    return f"{content} {tag_str}"


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 0: 采集小红书视频
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_initial_state(html: str) -> dict:
    """从页面 HTML 中提取 window.__INITIAL_STATE__ JSON 对象。"""
    marker = "window.__INITIAL_STATE__="
    idx = html.find(marker)
    if idx == -1:
        return {}
    json_start = idx + len(marker)
    # 用 </script> 作为结束标记（比逐字符匹配大括号快 10x+，页面约 1MB）
    script_end = html.find("</script>", json_start)
    if script_end == -1:
        return {}
    json_text = html[json_start:script_end]
    json_text = json_text.replace(":undefined", ":null").replace(": undefined", ": null")
    try:
        return json.loads(json_text)
    except (json.JSONDecodeError, ValueError):
        return {}


def fetch_explore_videos() -> list[dict]:
    """从小红书 explore 推荐流获取视频笔记列表（仅 type=video）。"""
    resp = requests.get(XHS_EXPLORE_URL, headers=XHS_HEADERS, timeout=20)
    resp.raise_for_status()
    state = _parse_initial_state(resp.text)
    feeds = state.get("feed", {}).get("feeds", [])

    results = []
    for feed in feeds:
        note_card = feed.get("noteCard", {})
        if note_card.get("type", "").lower() != "video":
            continue
        note_id = feed.get("id")
        if not note_id:
            continue
        xsec_token = feed.get("xsecToken", "")
        title = note_card.get("displayTitle", "").strip()
        cover = note_card.get("cover", {})
        cover_url = cover.get("urlDefault") or cover.get("urlPre") or ""
        results.append({
            "note_id": note_id,
            "xsec_token": xsec_token,
            "title": title,
            "cover_fallback": cover_url,
        })
    return results


def fetch_video_detail(note_id: str, xsec_token: str) -> Optional[dict]:
    """
    进入笔记详情页提取视频流 URL、封面图、正文及标签。

    返回 dict keys: note_id, video_url, cover_url, content
    失败返回 None。
    """
    url = XHS_NOTE_URL_TPL.format(note_id=note_id)
    if xsec_token:
        url += f"?xsec_token={xsec_token}&xsec_source=pc_feed"

    try:
        resp = requests.get(url, headers=XHS_HEADERS, timeout=30)
        if resp.status_code != 200:
            return None
    except requests.RequestException:
        return None

    state = _parse_initial_state(resp.text)
    note = (
        state.get("note", {})
        .get("noteDetailMap", {})
        .get(note_id, {})
        .get("note", {})
    )
    if not note:
        return None

    # 提取视频流 URL（h264 优先）
    video = note.get("video", {})
    stream = video.get("media", {}).get("stream", {})
    video_url = ""
    duration_ms = 0
    if stream:
        h264_list = stream.get("h264", [])
        if h264_list:
            video_url = h264_list[0].get("masterUrl", "") or h264_list[0].get("backupUrl", "")
            # 时长：优先从流信息获取（单位毫秒）
            duration_ms = h264_list[0].get("duration", 0)
    if not video_url:
        return None

    # 时长 fallback：从 video.capa.duration 或 video.duration 获取
    if not duration_ms:
        duration_ms = video.get("capa", {}).get("duration", 0)
    if not duration_ms:
        duration_ms = video.get("duration", 0)

    duration_sec = duration_ms / 1000.0 if duration_ms else 0

    # 封面图多级 fallback
    cover_url = ""
    video_image = video.get("image", {})
    if video_image:
        cover_url = video_image.get("urlDefault", "") or video_image.get("url", "")
    if not cover_url:
        image_list = note.get("imageList", [])
        if image_list:
            cover_url = image_list[0].get("urlDefault", "") or image_list[0].get("url", "")

    # 正文：Title + Desc
    title = (note.get("title", "") or "").strip()
    desc = (note.get("desc", "") or "").strip()
    content = f"{title}\n{desc}".strip() if desc else title

    # 清理小红书特有格式
    content = re.sub(r"#([^#\[]+)\[话题\]#", r"#\1", content)  # #话题[话题]# → #话题
    content = re.sub(r"\[[^\]]+R\]", "", content)  # [表情R]
    content = re.sub(r"@[\w\u4e00-\u9fff]+", "", content)  # @用户
    content = re.sub(r" +", " ", content)
    content = re.sub(r"\n+", "\n", content).strip()

    return {
        "note_id": note_id,
        "video_url": video_url,
        "cover_url": cover_url,
        "content": content,
        "duration_sec": duration_sec,
    }


def crawl_xhs_videos(target: int = 25, delay: float = 1.5, max_rounds: int = 10,
                     max_size_mb: float = DEFAULT_MAX_VIDEO_SIZE_MB,
                     min_size_mb: float = DEFAULT_MIN_VIDEO_SIZE_MB,
                     max_duration_sec: float = DEFAULT_MAX_VIDEO_DURATION_SEC) -> list[dict]:
    """
    批量采集小红书视频笔记。

    Args:
        target: 目标视频数量
        delay: 详情页请求间隔（秒），防频控
        max_rounds: 最大 explore 请求轮数
        max_size_mb: 视频最大大小（MB），超过则跳过（默认 15MB）
        min_size_mb: 视频最小大小（MB），低于则跳过（默认 0.5MB）
        max_duration_sec: 视频最大时长（秒），超过则跳过（默认 90s）

    Returns:
        list of {note_id, video_url, cover_url, content, size_mb, duration_sec}
    """
    log(f"\n{'═'*60}")
    log(f"  Phase 0: 采集小红书视频 (目标: {target} 条, ≤{max_size_mb}MB, ≤{max_duration_sec}s)")
    log(f"{'═'*60}")

    collected = []
    seen_ids: set[str] = set()

    for round_num in range(1, max_rounds + 1):
        if len(collected) >= target:
            break

        log(f"\n[Round {round_num}/{max_rounds}] 请求 explore 推荐流...")
        try:
            briefs = fetch_explore_videos()
        except Exception as e:
            log(f"  [WARN] explore 请求失败: {e}")
            time.sleep(3)
            continue

        new_briefs = [b for b in briefs if b["note_id"] not in seen_ids]
        log(f"  发现 {len(new_briefs)} 条新视频笔记")

        for brief in new_briefs:
            if len(collected) >= target:
                break
            seen_ids.add(brief["note_id"])
            time.sleep(delay)

            detail = fetch_video_detail(brief["note_id"], brief["xsec_token"])
            if detail:
                # 封面 fallback：详情页为空时用 explore feed 的封面
                if not detail["cover_url"] and brief["cover_fallback"]:
                    detail["cover_url"] = brief["cover_fallback"]
                if not detail["video_url"] or not detail["cover_url"]:
                    log(f"  [SKIP] 无视频/封面: {brief['note_id']}")
                    continue

                # 视频时长预检（从详情页 JSON 提取）
                dur = detail.get("duration_sec", 0)
                if dur > 0 and dur > max_duration_sec:
                    log(f"  [SKIP] 视频过长 {dur:.0f}s > {max_duration_sec}s: {brief['title'][:25]}")
                    continue

                # 视频大小预检（HEAD 请求探测）
                size_mb = probe_video_size(detail["video_url"])
                if size_mb > 0:
                    if size_mb > max_size_mb:
                        log(f"  [SKIP] 视频过大 {size_mb:.1f}MB > {max_size_mb}MB: {brief['title'][:25]}")
                        continue
                    if size_mb < min_size_mb:
                        log(f"  [SKIP] 视频过小 {size_mb:.1f}MB < {min_size_mb}MB: {brief['title'][:25]}")
                        continue

                detail["size_mb"] = size_mb
                collected.append(detail)
                size_str = f"{size_mb:.1f}MB" if size_mb > 0 else "?MB"
                dur_str = f"{dur:.0f}s" if dur > 0 else "?s"
                title_short = detail["content"][:35].replace("\n", " ")
                log(f"  [OK] #{len(collected)} ({size_str}/{dur_str}): {title_short}")
            else:
                log(f"  [SKIP] 详情页失败: {brief['note_id']}")

        time.sleep(2)  # 轮间冷却

    log(f"\n[采集完成] 共获取 {len(collected)} 条视频 (≤{max_size_mb}MB, ≤{max_duration_sec}s)")
    return collected


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1: 认证 & 上传 & 发布
# ═══════════════════════════════════════════════════════════════════════════════

def login_user(email: str, password: str, env: str = "test") -> str:
    """
    登录并返回 Bearer token。

    test 环境使用 'email' 字段，dev 环境使用 'username' 字段。
    """
    if env == "test":
        payload = {"email": email, "password": password}
    else:
        payload = {"username": email, "password": password}
    payload["device_id"] = config.POST_DEVICE_ID
    payload["device_name"] = config.POST_DEVICE_NAME

    resp = requests.post(config.LOGIN_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    token = (
        data.get("access_token")
        or data.get("token")
        or (data.get("data") or {}).get("access_token")
        or (data.get("data") or {}).get("token")
    )
    if not token:
        raise RuntimeError(f"登录失败 ({email}): {data}")
    return token


def get_upload_credentials(token: str) -> dict:
    """获取 S3 临时上传凭证。"""
    upload_url = os.getenv(
        "UPLOAD_CREDENTIALS_URL",
        "https://testapi-x.tp-ex.com/file/upload/credentials",
    )
    resp = requests.post(
        upload_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    creds = data.get("data") or data
    required = ("access_key_id", "secret_access_key", "session_token", "region", "bucket", "domain")
    missing = [k for k in required if not creds.get(k)]
    if missing:
        raise RuntimeError(f"upload-credentials 缺少字段: {missing}")
    return creds


def download_file(url: str, target_dir: Path, timeout: int = 180) -> Path:
    """
    下载文件到本地，自动处理 Referer 防盗链。

    xhscdn.com 域名自动附带小红书 Referer。
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".bin"
    name = f"{uuid.uuid4().hex}{suffix}"
    dst = target_dir / name

    headers = {
        "User-Agent": XHS_HEADERS["User-Agent"],
        "Referer": resolve_referer(url),
    }
    with requests.get(url, stream=True, headers=headers, timeout=timeout) as r:
        r.raise_for_status()
        with dst.open("wb") as fh:
            for chunk in r.iter_content(1 << 16):
                fh.write(chunk)
    return dst


def upload_to_s3(local: Path, creds: dict) -> str:
    """上传文件到 S3，返回公网 CDN URL。"""
    today = dt.datetime.utcnow()
    key = f"square/original/{today:%Y/%m/%d}/{local.name}"

    content_type = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
    if local.suffix.lower() == ".mp4":
        content_type = "video/mp4"
    elif local.suffix.lower() in (".jpg", ".jpeg"):
        content_type = "image/jpeg"
    elif local.suffix.lower() == ".png":
        content_type = "image/png"

    s3 = boto3.client(
        "s3",
        aws_access_key_id=creds["access_key_id"],
        aws_secret_access_key=creds["secret_access_key"],
        aws_session_token=creds["session_token"],
        region_name=creds["region"],
        config=BotoConfig(signature_version="s3v4"),
    )
    s3.upload_file(
        str(local), creds["bucket"], key,
        ExtraArgs={"ContentType": content_type},
    )
    return f"https://{creds['domain']}/{key}"


def publish_video_moment(token: str, caption: str, video_url: str, thumbnail_url: str) -> dict:
    """发布视频动态到 XXAI 广场。"""
    body = {
        "content": caption,
        "visibility": 0,
        "media_info": {
            "type": "video",
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
        },
    }
    resp = requests.post(
        config.MOMENTS_API_URL,
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"发布失败: {resp.status_code} {resp.text}")
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 用户加载
# ═══════════════════════════════════════════════════════════════════════════════

def load_users_xlsx(xlsx_path: str, n: int = 20, offset: int = 0) -> list[dict]:
    """
    从企管用户 xlsx 表加载用户。

    表格格式：序号, 用户昵称, 注册账户, 用户密码, 用户邮箱, Pincode
    """
    path = Path(xlsx_path)
    if not path.exists():
        # 自动查找仓库根目录下的 xlsx
        repo_root = Path(__file__).resolve().parent.parent
        candidates = [f for f in os.listdir(repo_root) if f.endswith(".xlsx")]
        if candidates:
            path = repo_root / candidates[0]
        else:
            raise FileNotFoundError(f"找不到用户表: {xlsx_path}")

    wb = openpyxl.load_workbook(str(path), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2 + offset, max_row=1 + offset + n, values_only=True))
    wb.close()

    users = []
    for row in rows:
        if len(row) >= 5 and row[4] and row[3]:
            users.append({
                "nickname": str(row[1] or ""),
                "email": str(row[4]).strip(),
                "password": str(row[3]).strip(),
            })
    return users


def load_users_csv(csv_path: str, n: int = 20) -> list[dict]:
    """从 CSV 格式的用户表加载（兼容旧格式）。"""
    users = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = next(
                (row[k] for k in config.ACCOUNTS_CSV_EMAIL_FIELDS if k in row and row[k]),
                None,
            )
            password = next(
                (row[k] for k in config.ACCOUNTS_CSV_PASSWORD_FIELDS if k in row and row[k]),
                None,
            )
            if email and password:
                users.append({"nickname": "", "email": email, "password": password})
            if len(users) >= n:
                break
    return users


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args():
    ap = argparse.ArgumentParser(
        description="小红书视频采集 → 批量发布到 XXAI 广场",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 20 用户各发 1 个视频
  py -3 scripts/run_xhs_video.py --accounts-xlsx test_企管用户_邮箱密码pincode_500.csv.xlsx --num-users 20

  # 只采集不发布
  py -3 scripts/run_xhs_video.py --crawl-only --target 30

  # 从已有 CSV 发布
  py -3 scripts/run_xhs_video.py --accounts-xlsx accounts.xlsx --csv moments_video.csv --num-users 10
""",
    )
    # 用户来源
    ap.add_argument("--accounts-xlsx", default="", help="用户表 xlsx 路径（test500 格式）")
    ap.add_argument("--accounts-csv", default="", help="用户表 CSV 路径（邮箱+密码列）")
    ap.add_argument("--num-users", type=int, default=20, help="使用的用户数量（默认 20）")
    ap.add_argument("--user-offset", type=int, default=0, help="从第几个用户开始（默认 0，即第1个）")

    # 采集参数
    ap.add_argument("--target", type=int, default=25, help="采集视频目标数量（默认 25，需 > num-users）")
    ap.add_argument("--crawl-delay", type=float, default=1.5, help="采集详情页间隔秒数（默认 1.5）")
    ap.add_argument("--crawl-only", action="store_true", help="只采集不发布（输出 CSV）")
    ap.add_argument("--output", default="moments_video.csv", help="采集输出 CSV 路径（默认 moments_video.csv）")
    ap.add_argument("--max-video-size", type=float, default=DEFAULT_MAX_VIDEO_SIZE_MB,
                    help=f"视频最大大小 MB（默认 {DEFAULT_MAX_VIDEO_SIZE_MB}，超过则跳过）")
    ap.add_argument("--min-video-size", type=float, default=DEFAULT_MIN_VIDEO_SIZE_MB,
                    help=f"视频最小大小 MB（默认 {DEFAULT_MIN_VIDEO_SIZE_MB}，低于则跳过）")
    ap.add_argument("--max-duration", type=float, default=DEFAULT_MAX_VIDEO_DURATION_SEC,
                    help=f"视频最大时长 秒（默认 {DEFAULT_MAX_VIDEO_DURATION_SEC}，超过则跳过）")

    # 发布参数
    ap.add_argument("--csv", default="", help="已有视频 CSV（跳过采集直接发布）")
    ap.add_argument("--env", choices=("test", "dev"), default="test", help="目标环境（默认 test）")
    ap.add_argument("--login-spacing", type=float, default=5.0,
                    help="登录间隔秒数（默认 5.0，避免 429）")
    ap.add_argument("--download-timeout", type=int, default=180,
                    help="视频下载超时秒数（默认 180）")
    ap.add_argument("--max-retries", type=int, default=2,
                    help="单个视频失败后最大重试次数（默认 2）")
    ap.add_argument("--yes", "-y", action="store_true", help="跳过确认直接执行")

    return ap.parse_args()


def main() -> int:
    args = parse_args()

    log("═" * 60)
    log("  run_xhs_video.py — 小红书视频 → XXAI 广场批量发布")
    log("═" * 60)
    log(f"  环境:       {args.env}")
    log(f"  LOGIN_URL:  {config.LOGIN_URL}")
    log(f"  MOMENTS:    {config.MOMENTS_API_URL}")
    log(f"  用户数量:    {args.num_users}")
    log(f"  视频限制:    ≤{args.max_video_size}MB, ≤{args.max_duration}s")
    log("═" * 60)

    # ─── Phase 0: 采集或加载视频 ─────────────────────────────────────────
    if args.csv:
        # 从已有 CSV 加载
        log(f"\n[加载] 从 CSV 读取视频: {args.csv}")
        with open(args.csv, encoding="utf-8-sig") as f:
            videos = list(csv.DictReader(f))
        log(f"[加载] 读取到 {len(videos)} 条视频")
    else:
        # 采集（带大小+时长过滤）
        videos_raw = crawl_xhs_videos(
            target=args.target,
            delay=args.crawl_delay,
            max_size_mb=args.max_video_size,
            min_size_mb=args.min_video_size,
            max_duration_sec=args.max_duration,
        )
        # 写入 CSV
        out_path = args.output
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["content", "video_url", "thumbnail_url"])
            w.writeheader()
            for v in videos_raw:
                w.writerow({
                    "content": v["content"],
                    "video_url": v["video_url"],
                    "thumbnail_url": v["cover_url"],
                })
        log(f"\n[保存] 视频列表已写入: {out_path}")

        if args.crawl_only:
            log("[完成] --crawl-only 模式，跳过发布。")
            return 0

        # 转换为发布格式
        videos = [
            {"content": v["content"], "video_url": v["video_url"], "thumbnail_url": v["cover_url"]}
            for v in videos_raw
        ]

    if len(videos) < args.num_users:
        log(f"[WARN] 视频数量({len(videos)}) < 用户数量({args.num_users})，将循环复用")
        while len(videos) < args.num_users:
            videos.extend(videos[: args.num_users - len(videos)])

    # ─── 加载用户 ────────────────────────────────────────────────────────
    if args.accounts_xlsx:
        users = load_users_xlsx(args.accounts_xlsx, args.num_users, args.user_offset)
    elif args.accounts_csv:
        users = load_users_csv(args.accounts_csv, args.num_users)
    else:
        # 自动查找 xlsx
        users = load_users_xlsx("", args.num_users, args.user_offset)

    log(f"[用户] 加载 {len(users)} 个用户")

    if len(users) < args.num_users:
        log(f"[WARN] 实际用户 {len(users)} < 目标 {args.num_users}")

    num = min(args.num_users, len(users), len(videos))

    # ─── 确认 ────────────────────────────────────────────────────────────
    if not args.yes:
        log(f"\n即将为 {num} 个用户各发布 1 条视频。按 Enter 继续，Ctrl+C 取消...")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            log("\n[取消]")
            return 1

    # ─── Phase 1: 逐用户发布 ─────────────────────────────────────────────
    log(f"\n{'═'*60}")
    log(f"  Phase 1: 发布视频 ({num} 用户 × 1 视频)")
    log(f"{'═'*60}")

    media_dir = Path("media")
    media_dir.mkdir(exist_ok=True)

    results = []
    spare_idx = num  # 备用视频起始索引

    for i in range(num):
        user = users[i]
        video = videos[i]
        idx = i + 1

        content = video["content"]
        caption = ensure_tag_consistency(content)

        log(f"\n{'─'*60}")
        log(f"[{idx}/{num}] {user['nickname']} ({user['email']})")
        log(f"  视频: {content[:50].replace(chr(10), ' ')}...")
        log(f"  文案: {caption[:60].replace(chr(10), ' ')}...")

        success = False
        retries = 0

        while not success and retries <= args.max_retries:
            if retries > 0:
                log(f"  [重试 {retries}/{args.max_retries}]")
                # 切换到备用视频
                if spare_idx < len(videos):
                    video = videos[spare_idx]
                    spare_idx += 1
                    content = video["content"]
                    caption = ensure_tag_consistency(content)
                    log(f"  切换备用视频: {content[:40].replace(chr(10), ' ')}")

            try:
                # 1. Login
                log(f"  [1/5] 登录...")
                token = login_user(user["email"], user["password"], args.env)
                log(f"  [1/5] OK")

                # 2. S3 credentials
                log(f"  [2/5] 获取上传凭证...")
                creds = get_upload_credentials(token)
                log(f"  [2/5] OK")

                # 3. Download
                log(f"  [3/5] 下载视频...")
                local_video = download_file(video["video_url"], media_dir, args.download_timeout)
                size_mb = local_video.stat().st_size / 1024 / 1024
                log(f"  [3/5] 视频: {size_mb:.1f} MB")

                # 下载后二次校验大小（HEAD 可能拿不到 Content-Length）
                if size_mb > args.max_video_size:
                    log(f"  [SKIP] 下载后实际 {size_mb:.1f}MB > {args.max_video_size}MB，跳过")
                    local_video.unlink(missing_ok=True)
                    raise RuntimeError(f"视频过大 {size_mb:.1f}MB")

                log(f"  [3/5] 下载封面...")
                local_cover = download_file(video["thumbnail_url"], media_dir, 60)
                size_kb = local_cover.stat().st_size / 1024
                log(f"  [3/5] 封面: {size_kb:.0f} KB")

                # 4. Upload S3
                log(f"  [4/5] 上传 S3...")
                s3_video = upload_to_s3(local_video, creds)
                s3_cover = upload_to_s3(local_cover, creds)
                log(f"  [4/5] OK")

                # 5. Publish
                log(f"  [5/5] 发布动态...")
                result = publish_video_moment(token, caption, s3_video, s3_cover)
                moment_id = (result.get("data") or {}).get("id") or result.get("id") or "?"
                log(f"  [5/5] SUCCESS! moment_id={moment_id}")

                results.append({
                    "idx": idx,
                    "user": user["nickname"],
                    "email": user["email"],
                    "moment_id": str(moment_id),
                    "caption": caption[:80],
                    "status": "OK",
                })
                success = True

                # 清理本地临时文件
                try:
                    local_video.unlink()
                    local_cover.unlink()
                except Exception:
                    pass

            except Exception as e:
                log(f"  [ERROR] {e}")
                retries += 1
                # 清理可能的半成品文件
                for f in media_dir.glob("*.tmp"):
                    f.unlink(missing_ok=True)

        if not success:
            results.append({
                "idx": idx,
                "user": user["nickname"],
                "email": user["email"],
                "moment_id": "",
                "caption": caption[:80] if caption else "",
                "status": f"FAIL (retries={retries})",
            })

        # 用户间隔（避免 429）
        if i < num - 1:
            time.sleep(args.login_spacing)

    # ─── 汇总 ────────────────────────────────────────────────────────────
    log(f"\n{'═'*60}")
    log("  发布结果汇总")
    log(f"{'═'*60}")
    ok_count = sum(1 for r in results if r["status"] == "OK")
    fail_count = len(results) - ok_count
    log(f"  成功: {ok_count}/{num}  |  失败: {fail_count}/{num}")
    log(f"{'─'*60}")
    for r in results:
        icon = "OK  " if r["status"] == "OK" else "FAIL"
        log(f"  [{r['idx']:>2}] {icon} {r['user']:<18} moment_id={r['moment_id']}")
    log(f"{'═'*60}")

    # 保存结果 JSON
    out_dir = Path("result")
    out_dir.mkdir(exist_ok=True)
    results_path = out_dir / "xhs_video_results.json"
    with results_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log(f"\n[保存] 结果文件: {results_path}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
