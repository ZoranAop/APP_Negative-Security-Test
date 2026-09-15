#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_xhs_video_850_comments.py — 发布小红书视频（pre 企管用户_850）+ 互动用户池_670 评论互动

流程（一组 = 20 个视频帖）:
  Phase 0: 采集小红书 explore 视频笔记（标题/描述/视频流/封面）
  Phase 1: 从 pre_企管用户_850.csv 选 20 个未用账号
  Phase 2: 顺序登录 → S3 凭证 → 下载视频+封面 → S3 上传 → 发布视频动态
  Phase 3: 发布完一组后，从 互动用户池_670账号.xlsx 随机选 2-30 个账号
  Phase 4: 结合每个视频的文本内容生成评论（60% 英文 / 40% 繁体中文），登录评论账号并回帖

用法:
  py -3 scripts/run_xhs_video_850_comments.py --num-videos 20 --yes
  py -3 scripts/run_xhs_video_850_comments.py --num-videos 20 --min-cmt 2 --max-cmt 30 --yes
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    print("[FATAL] 缺少依赖。请: py -3 -m pip install requests boto3", file=sys.stderr)
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    print("[FATAL] 缺少 openpyxl。请: py -3 -m pip install openpyxl", file=sys.stderr)
    sys.exit(1)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

# ─── 载入 .env（复用 config 的环境变量）─────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    if (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

LOGIN_URL = os.getenv("LOGIN_URL", "https://api.xxai.com/login")
UPLOAD_URL = os.getenv("UPLOAD_CREDENTIALS_URL", "https://api.xxai.com/file/upload/credentials")
MOMENTS_API_URL = os.getenv("MOMENTS_API_URL", "https://feed-api.xxai.com/api/v1/moments/")
COMMENTS_API_URL = "https://feed-api.xxai.com/api/v1/comments"

# 账号池
CSV_850 = ROOT / "pre_企管用户_850.csv"
XLSX_670 = ROOT / "互动用户池_670账号.xlsx"
TOKENS_PATH = ROOT / "result" / "tokens.json"

# ─── 小红书采集配置 ──────────────────────────────────────────────────────────
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
REFERER_MAP = {
    "xhscdn.com": "https://www.xiaohongshu.com/",
    "xiaohongshu.com": "https://www.xiaohongshu.com/",
}
MAX_VIDEO_SIZE_MB = 15
MAX_DURATION_SEC = 90


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def log(msg: str) -> None:
    print(msg, flush=True)


try:
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8",
                      buffering=1, errors="replace")
    sys.stderr = open(sys.stderr.fileno(), mode="w", encoding="utf-8",
                      buffering=1, errors="replace")
except Exception:
    pass


def resolve_referer(url: str) -> str:
    host = urlparse(url).hostname or ""
    for sub, ref in REFERER_MAP.items():
        if sub in host:
            return ref
    return "https://www.xiaohongshu.com/"


def parse_initial_state(html: str) -> dict:
    marker = "window.__INITIAL_STATE__="
    idx = html.find(marker)
    if idx == -1:
        return {}
    js_start = idx + len(marker)
    end = html.find("</script>", js_start)
    if end == -1:
        return {}
    raw = html[js_start:end].replace(":undefined", ":null").replace(": undefined", ":null")
    try:
        return json.loads(raw)
    except Exception:
        return {}


def is_en_nick(nick: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_.\-]*$", str(nick)))


def is_zh_nick(nick: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in str(nick))


def load_used_emails() -> set[str]:
    used: set[str] = set()
    if TOKENS_PATH.exists():
        try:
            used.update(json.loads(TOKENS_PATH.read_text(encoding="utf-8")).keys())
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


def _login(email: str, password: str, max_retries: int = 5) -> str | None:
    """登录 pre 环境，返回 token（兼容多种响应格式 + 429 退避）。"""
    for attempt in range(max_retries):
        try:
            r = requests.post(LOGIN_URL, json={
                "email": email.strip(),
                "password": password.strip(),
                "device_id": "auto_poster",
                "device_name": "auto_poster_client",
            }, timeout=20)
            if r.status_code == 429:
                delay = 3.0 * (2 ** attempt)
                log(f"    [429] 登录频控，退避 {delay:.0f}s 后重试")
                time.sleep(delay)
                continue
            if r.status_code != 200:
                return None
            j = r.json()
            if j.get("code") not in (0, None):
                # 业务失败（非 429）直接返回，不再重试
                return None
            tok = (
                (j.get("data") or {}).get("token")
                or (j.get("data") or {}).get("access_token")
                or j.get("token")
                or j.get("access_token")
            )
            return tok
        except Exception:
            time.sleep(2)
            continue
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 0: 采集小红书视频
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_explore_videos(target: int) -> list[dict]:
    log(f"[crawl] 请求 explore 推荐流 ...")
    try:
        resp = requests.get(XHS_EXPLORE_URL, headers=XHS_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        log(f"[error] explore 请求失败: {e}")
        return []
    state = parse_initial_state(resp.text)
    feeds = state.get("feed", {}).get("feeds", [])
    videos = []
    for feed in feeds:
        card = feed.get("noteCard", {})
        if (card.get("type", "") or "").lower() != "video":
            continue
        note_id = str(feed.get("id") or "").strip()
        if not note_id:
            continue
        xsec = str(feed.get("xsecToken", "") or "").strip()
        title = (card.get("displayTitle", "") or "").strip()
        cover = card.get("cover", {}) or {}
        cover_url = cover.get("urlDefault") or cover.get("urlPre") or ""
        videos.append({
            "note_id": note_id,
            "xsec_token": xsec,
            "title": title,
            "cover_fallback": cover_url,
        })
        if len(videos) >= target * 3:
            break
    log(f"[crawl] explore 页发现 {len(videos)} 条视频笔记")
    return videos


def fetch_video_detail(note_id: str, xsec_token: str) -> dict | None:
    url = XHS_NOTE_URL_TPL.format(note_id=note_id)
    if xsec_token:
        url += f"?xsec_token={xsec_token}&xsec_source=pc_feed"
    try:
        resp = requests.get(url, headers=XHS_HEADERS, timeout=30)
        if resp.status_code != 200:
            return None
    except Exception:
        return None
    state = parse_initial_state(resp.text)
    note = (state.get("note", {}).get("noteDetailMap", {}).get(note_id, {}) or {}).get("note", {})
    if not note:
        return None

    video = note.get("video", {})
    stream = video.get("media", {}).get("stream", {})
    video_url = ""
    duration_sec = 0
    if stream:
        h264 = stream.get("h264", [])
        if h264:
            video_url = (h264[0].get("masterUrl") or h264[0].get("backupUrl") or "").strip()
            duration_ms = h264[0].get("duration", 0)
            duration_sec = duration_ms / 1000.0 if duration_ms else 0
    if not video_url:
        return None
    if not duration_sec:
        duration_sec = (video.get("capa", {}) or {}).get("duration", 0) / 1000.0
    if not duration_sec:
        duration_sec = video.get("duration", 0) / 1000.0

    cover_url = ""
    video_image = video.get("image", {}) or {}
    if video_image:
        cover_url = video_image.get("urlDefault") or video_image.get("url") or ""
    if not cover_url:
        image_list = note.get("imageList", [])
        if image_list:
            cover_url = image_list[0].get("urlDefault") or image_list[0].get("url") or ""

    title = (note.get("title", "") or "").strip()
    desc = (note.get("desc", "") or "").strip()
    content = f"{title}\n{desc}".strip() if desc else title
    content = re.sub(r"#([^\s#]+)\[话题\]#", r"#\1", content)
    content = re.sub(r"\[[^\]]+R\]", "", content)
    content = re.sub(r"@[\w\u4e00-\u9fff]+", "", content)
    content = re.sub(r" +", " ", content).strip()

    return {
        "note_id": note_id,
        "video_url": video_url,
        "cover_url": cover_url,
        "content": content,
        "duration_sec": duration_sec,
    }


def probe_size(url: str, timeout: int = 8) -> float:
    try:
        resp = requests.head(url, headers={
            "User-Agent": XHS_HEADERS["User-Agent"],
            "Referer": resolve_referer(url),
        }, timeout=timeout, allow_redirects=True)
        cl = resp.headers.get("Content-Length")
        if cl:
            return int(cl) / 1024 / 1024
    except Exception:
        pass
    return -1


def collect_videos(num: int) -> list[dict]:
    """采集足够的有效视频（过滤大小/时长）。多轮 explore 以补足数量。"""
    moments: list[dict] = []
    seen: set[str] = set()
    for round_no in range(1, 4):  # 最多 3 轮 explore
        if len(moments) >= num:
            break
        log(f"[crawl] 第 {round_no} 轮 explore ...")
        explore = fetch_explore_videos(num)
        if not explore:
            log(f"[crawl] 第 {round_no} 轮无新笔记，重试中")
            time.sleep(3)
            continue
        for ev in explore:
            if len(moments) >= num:
                break
            if ev["note_id"] in seen:
                continue
            seen.add(ev["note_id"])
            time.sleep(1.2)
            detail = fetch_video_detail(ev["note_id"], ev["xsec_token"])
            if not detail:
                continue
            if detail["duration_sec"] > MAX_DURATION_SEC:
                continue
            size = probe_size(detail["video_url"])
            if size > 0 and size > MAX_VIDEO_SIZE_MB:
                continue
            if not detail["cover_url"]:
                detail["cover_url"] = ev.get("cover_fallback", "")
            moments.append(detail)
            log(f"  [OK] {detail['duration_sec']:.0f}s {size:.1f}MB: {detail['content'][:32].replace(chr(10),' ')}")
        time.sleep(2)
    return moments


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2: S3 上传 & 发布
# ═══════════════════════════════════════════════════════════════════════════════

def get_s3_creds(token: str) -> dict | None:
    try:
        resp = requests.post(UPLOAD_URL, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }, json={}, timeout=15)
        resp.raise_for_status()
        j = resp.json()
        if j.get("code") == 0:
            return j.get("data", {})
    except Exception as e:
        log(f"[s3-creds error] {e}")
    return None


def download_bytes(url: str, referer: str, timeout: int = 120) -> bytes | None:
    try:
        resp = requests.get(url, headers={
            "User-Agent": XHS_HEADERS["User-Agent"],
            "Referer": referer,
        }, timeout=timeout, stream=True)
        resp.raise_for_status()
        return b"".join(resp.iter_content(chunk_size=65536))
    except Exception:
        return None


def upload_to_s3(data: bytes, key: str, content_type: str, creds: dict) -> str | None:
    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=creds.get("access_key_id", ""),
            aws_secret_access_key=creds.get("secret_access_key", ""),
            aws_session_token=creds.get("session_token", ""),
            region_name=creds.get("region", "ap-northeast-1"),
            config=BotoConfig(retries={"max_attempts": 3, "mode": "adaptive"}),
        )
        s3.put_object(Bucket=creds.get("bucket", ""), Key=key, Body=data,
                      ContentType=content_type)
        return f"https://{creds.get('domain', '')}/{key}"
    except Exception as e:
        log(f"[s3-upload error] {e}")
        return None


def publish_moment(token: str, content: str, video_url: str, cover_url: str) -> tuple[bool, str]:
    try:
        resp = requests.post(MOMENTS_API_URL, json={
            "content": content,
            "visibility": 0,
            "media_info": {"type": "video", "video_url": video_url, "thumbnail_url": cover_url},
        }, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }, timeout=30)
        if resp.status_code == 200:
            j = resp.json()
            if j.get("code") == 0:
                return True, str((j.get("data") or {}).get("moment_id", "") or (j.get("data") or {}).get("id", ""))
            return False, j.get("msg", "unknown")
        return False, f"http_{resp.status_code}"
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════════
# 账号加载
# ═══════════════════════════════════════════════════════════════════════════════

def load_850_accounts(n: int) -> list[dict]:
    """从 pre_企管用户_850.csv 选 n 个未用账号。"""
    used = load_used_emails()
    picked: list[dict] = []
    with open(CSV_850, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if len(picked) >= n:
                break
            email = (row.get("邮箱") or "").strip()
            pwd = (row.get("密码") or "").strip()
            nick = (row.get("昵称") or "").strip()
            pin = (row.get("pincode") or "").strip()
            if not email or not pwd or email.lower() in used:
                continue
            picked.append({"email": email, "nickname": nick, "password": pwd, "pincode": pin})
    return picked


def load_670_accounts(n: int, lang: str = "any", exclude: set[str] | None = None) -> list[dict]:
    """从 互动用户池_670账号.xlsx 选账号。lang: en/zh/any。"""
    exclude = set(exclude or set())
    wb = openpyxl.load_workbook(XLSX_670, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    picked: list[dict] = []
    for r in rows[1:]:
        if len(picked) >= n:
            break
        email = str(r[1] or "").strip()
        nick = str(r[3] or "").strip()
        pwd = str(r[4] or "").strip()
        pin = str(r[5] or "").strip() if len(r) > 5 else ""
        if not email or not pwd or email.lower() in exclude:
            continue
        if lang == "en" and not is_en_nick(nick):
            continue
        if lang == "zh" and not is_zh_nick(nick):
            continue
        picked.append({"email": email, "nickname": nick, "password": pwd, "pincode": pin})
    return picked


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4: 评论内容生成（结合视频文本，60% 英文 / 40% 繁体中文）
# ═══════════════════════════════════════════════════════════════════════════════

# 主题关键词 → 主题标签（用于让评论贴合视频内容）
TOPIC_KEYWORDS: list[tuple[str, str]] = [
    ("美食", "food"), ("做饭", "food"), ("早餐", "food"), ("晚餐", "food"), ("咖啡", "food"),
    ("蛋糕", "food"), ("甜点", "food"), ("烘焙", "food"), ("咖啡", "food"), ("茶", "food"),
    ("火锅", "food"), ("寿司", "food"), ("披萨", "food"), ("面包", "food"),
    ("化妆", "beauty"), ("美妆", "beauty"), ("护肤", "beauty"), ("眼妆", "beauty"),
    ("口红", "beauty"), ("粉底", "beauty"), ("美甲", "beauty"), ("发型", "beauty"),
    ("穿搭", "fashion"), ("旗袍", "fashion"), ("睡衣", "fashion"), ("时尚", "fashion"),
    ("健身", "fitness"), ("减肥", "fitness"), ("运动", "fitness"), ("瑜伽", "fitness"),
    ("腹肌", "fitness"), ("跑步", "fitness"), ("健身", "fitness"), ("撸铁", "fitness"),
    ("旅行", "travel"), ("旅游", "travel"), ("度假", "travel"), ("民宿", "travel"),
    ("露营", "travel"), ("海岛", "travel"), ("景点", "travel"), ("打卡", "travel"),
    ("猫", "pet"), ("狗", "pet"), ("萌宠", "pet"), ("宠物", "pet"), ("仓鼠", "pet"),
    ("收纳", "home"), ("家居", "home"), ("布置", "home"), ("装修", "home"), ("房间", "home"),
    ("书桌", "home"), ("工位", "home"), ("绿植", "home"), ("花", "home"),
    ("唱歌", "music"), ("音乐", "music"), ("钢琴", "music"), ("吉他", "music"), ("乐器", "music"),
    ("学习", "study"), ("读书", "study"), ("笔记", "study"), ("考研", "study"), ("考试", "study"),
    ("编程", "tech"), ("代码", "tech"), ("数码", "tech"), ("手机", "tech"), ("相机", "tech"),
    ("手工", "craft"), ("手作", "craft"), ("编织", "craft"), ("刺绣", "craft"), ("绘画", "craft"),
    ("绘画", "craft"), ("水彩", "craft"), ("书法", "craft"), ("diy", "craft"),
]

# 各主题 / 通用的英文评论库
EN_COMMENTS: dict[str, list[str]] = {
    "food": [
        "The way you plate this is so clean, instant save.",
        "Watched this while starving and now I need to cook tonight.",
        "This recipe looks effortless but so delicious.",
        "Okay the texture of this is everything.",
        "Adding this to my weekend meal list.",
        "This is the kind of comfort food I love.",
    ],
    "beauty": [
        "The finish on this is so clean, great tutorial.",
        "Loving the color combo here, very wearable.",
        "This routine looks so simple but effective.",
        "Saved this for my next makeup night.",
        "The skin texture in this video is unreal.",
        "Such a practical look, thank you for sharing.",
    ],
    "fashion": [
        "This outfit is giving clean and effortless.",
        "Love how you styled this, great piece.",
        "The colors go so well together.",
        "Saving this as a styling reference.",
        "This is such a good look for the season.",
        "Instant inspiration for my next fit.",
    ],
    "fitness": [
        "This form tip actually makes sense now.",
        "Finally someone breaking this down clearly.",
        "Been doing this routine and seeing results.",
        "The pacing of this workout is perfect.",
        "Motivated to start tomorrow thanks to this.",
        "Such a practical breakdown, thank you.",
    ],
    "travel": [
        "This spot looks unreal, adding it to my list.",
        "The cinematography here is so calming.",
        "You make this place sound like a dream.",
        "Saving this for my next trip planning.",
        "The vibe of this location is exactly what I need.",
        "This is the kind of escape I could use right now.",
    ],
    "pet": [
        "The fluff on this one is ridiculous, so cute.",
        "Okay this little face just made my whole day.",
        "Watched it three times, can't stop smiling.",
        "This is peak comfort content.",
        "Where is the link to this breed?",
        "Instant serotonin, thank you for this.",
    ],
    "home": [
        "This space feels so cozy, great setup.",
        "Love how organized this is, very motivating.",
        "Adding a few of these ideas to my room.",
        "This little corner is such a lovely touch.",
        "The plants here make the whole space come alive.",
        "Saving this for my next setup refresh.",
    ],
    "music": [
        "This covers so well, great technique.",
        "The tone on this is beautiful.",
        "Been wanting to try this for ages.",
        "You should drop a full version of this.",
        "This is a great practice reference.",
        "Loved the flow of this take.",
    ],
    "study": [
        "This note system is so clean, great method.",
        "Saving this as a reference, very helpful.",
        "You make this topic way less intimidating.",
        "The summary here is gold.",
        "This is exactly the explanation I needed.",
        "So practical, thank you for laying it out.",
    ],
    "tech": [
        "This setup is a clean flex.",
        "The workflow here is super practical.",
        "Saving this, need to try it out.",
        "You explain this way better than the docs.",
        "This is a neat little trick.",
        "Instantly useful, thanks for sharing.",
    ],
    "craft": [
        "The detail in this work is impressive.",
        "So satisfying to watch this come together.",
        "This is a great process video.",
        "The result is way better than I expected.",
        "Saving this for inspiration.",
        "You make this look so elegant.",
    ],
    "general": [
        "This is so satisfying to watch.",
        "Instant save, exactly the kind of clip I need today.",
        "Watched it twice already, the pacing is perfect.",
        "Where's the full version? Need more of this.",
        "This made my whole day, thank you for sharing.",
        "The BGM choice is perfect for this.",
        "Okay this is going on my replay list.",
        "Great energy in this one, love it.",
    ],
}

# 各主题 / 通用的繁体中文评论库
ZH_COMMENTS: dict[str, list[str]] = {
    "food": [
        "擺盤好乾淨，馬上收藏了。",
        "看餓了，今晚就想去煮。",
        "這道菜看起來超簡單又好吃。",
        "這個口感真的絕了。",
        "加入我週末的菜單了。",
        "這就是我愛的療癒系食物。",
    ],
    "beauty": [
        "妝容好精緻，超實用的教學。",
        "這配色很日常，愛了。",
        "流程好簡單但很有效果。",
        "收藏了，下次化妝就照這個。",
        "皮膚狀態在這影片裡好真實。",
        "很實用，感謝分享。",
    ],
    "fashion": [
        "這套穿搭很有質感。",
        "搭配得好好，喜歡。",
        "顏色超 harmony。",
        "存下來當下次穿搭參考。",
        "很適合這季節的LOOK。",
        "馬上想照著穿。",
    ],
    "fitness": [
        "這個動作要點講得超清楚。",
        "終於有人講得這麼明白了。",
        "有在練這個，確實有效。",
        "訓練節奏剛剛好。",
        "看完想去健身了。",
        "很實用的拆解，謝謝。",
    ],
    "travel": [
        "這地方看起來超美，加入清單。",
        "拍得好療癒。",
        "聽你講好想立刻出發。",
        "存下來規劃下次旅行。",
        "這個氛圍就是我需要的。",
        "現在超想去這種地方放空。",
    ],
    "pet": [
        "毛超蓬鬆，好可愛。",
        "這張小臉讓我整天都在笑。",
        "重播三次了。",
        "這是最療癒的內容。",
        "请问這種品種哪裡買？",
        "看完心情瞬間變好。",
    ],
    "home": [
        "這個空間好溫馨。",
        "整理得好整齊，很有感。",
        "想在自己的房間加一些靈感。",
        "這個小角落超有質感。",
        "植物让整个空間生動起來。",
        "收藏了，下次佈置參考。",
    ],
    "music": [
        "彈得好紮實，技巧不錯。",
        "音色好好聽。",
        "早想嘗試這首了。",
        "出一個完整版吧。",
        "是很好的練習参考。",
        "喜歡這個節奏感。",
    ],
    "study": [
        "筆記整理得好清楚。",
        "收藏了，很受用。",
        "讓你一講就不那麼難了。",
        "這個總結超實用。",
        "正好是我需要的解釋。",
        "很實用的整理，謝謝。",
    ],
    "tech": [
        "這套設定很實用。",
        "工作流程超方便。",
        "存下來想試試。",
        "比官方文件講得清楚。",
        "這招很聰明。",
        "馬上實用，感謝分享。",
    ],
    "craft": [
        "細節超讚。",
        "看這個過程好療癒。",
        "是很好的過程記錄。",
        "成品比想像中還好看。",
        "收藏了當靈感。",
        "你做起來好優雅。",
    ],
    "general": [
        "看到影片超療癒，心情好多了！",
        "剪接好流暢，愛死了。",
        "已經重播兩次，節奏剛剛好。",
        "收藏了，就是要這種影片的療癒感。",
        "搭配的背景音樂超對味。",
        "這種影片就是療癒系的本質，太喜歡了。",
        "看完心情超好，感謝分享。",
        "求完整版，想看更多！",
    ],
}


def detect_topic(text: str) -> str:
    t = text.lower()
    for kw, topic in TOPIC_KEYWORDS:
        if kw in t or kw.lower() in t:
            return topic
    return "general"


def make_comment(text: str, lang: str) -> str:
    """结合视频文本生成一条自然评论（en 或 zh_hant）。"""
    topic = detect_topic(text)
    bank = (EN_COMMENTS if lang == "en" else ZH_COMMENTS).get(topic)
    if not bank:
        bank = (EN_COMMENTS if lang == "en" else ZH_COMMENTS)["general"]
    return random.choice(bank)


def post_comment(token: str, moment_id: str, content: str) -> tuple[bool, str]:
    try:
        r = requests.post(COMMENTS_API_URL,
                          json={"moment_id": int(moment_id), "content": content},
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json"},
                          timeout=15)
        if r.status_code in (200, 201):
            j = r.json()
            if j.get("code") == 0:
                return True, ""
            return False, j.get("msg", "")[:80]
        return False, f"http_{r.status_code}"
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser(description="发布 XHS 视频（850 池）+ 670 池随机评论互动")
    ap.add_argument("--num-videos", type=int, default=20, help="一组视频帖数量（默认 20）")
    ap.add_argument("--min-cmt", type=int, default=3, help="评论账号池最小值（默认 3）")
    ap.add_argument("--max-cmt", type=int, default=10, help="评论账号池最大值（默认 10）")
    ap.add_argument("--login-spacing", type=float, default=3.0, help="发布账号登录间隔（默认 3s）")
    ap.add_argument("--cmt-delay", type=float, default=2.0, help="评论之间间隔（默认 2s）")
    ap.add_argument("--workdir", default="xhs_video_850_cmt_run")
    ap.add_argument("--skip-comments", action="store_true", help="只发布视频，不发评论")
    ap.add_argument("--yes", "-y", action="store_true", help="跳过确认")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    random.seed()

    log("═" * 60)
    log(f"  发布 {args.num_videos} 个 XHS 视频帖（pre 企管用户_850 池）")
    log(f"  评论账号池：互动用户池_670 随机 {args.min_cmt}-{args.max_cmt} 个")
    log(f"  评论语言：60% 英文 / 40% 繁体中文")
    log("═" * 60)

    # ── Phase 0: 采集 ──────────────────────────────────────────────
    log(f"\n[Phase 0] 采集 {args.num_videos} 条有效小红书视频")
    moments = collect_videos(args.num_videos)
    log(f"[Phase 0] 采集到 {len(moments)} 条有效视频")
    if not moments:
        log("[error] 未采集到有效视频，退出")
        return 1

    # ── Phase 1: 发布账号 ──────────────────────────────────────────
    pub_accounts = load_850_accounts(args.num_videos)
    log(f"\n[Phase 1] 从 850 池选取 {len(pub_accounts)} 个发布账号")
    if len(pub_accounts) < args.num_videos:
        log(f"[warn] 850 池未用账号不足（{len(pub_accounts)}），将循环复用")
        while len(pub_accounts) < args.num_videos:
            pub_accounts.append(pub_accounts[0])

    if not args.yes:
        if input("\n确认发布并评论？(y/n): ").strip().lower() not in ("y", "yes"):
            log("取消")
            return 0

    # ── Phase 2: 发布视频 ──────────────────────────────────────────
    log(f"\n[Phase 2] 发布视频（{len(moments)} 条）")
    published: list[dict] = []  # {moment_id, content, note_id, account}
    for i, m in enumerate(moments):
        acc = pub_accounts[i % len(pub_accounts)]
        token = _login(acc["email"], acc["password"])
        if not token:
            log(f"  [{i+1}/{len(moments)}] {acc['nickname']} 登录失败，跳过")
            continue

        creds = get_s3_creds(token)
        if not creds:
            log(f"  [{i+1}/{len(moments)}] S3 凭证失败，跳过")
            continue

        vid_data = download_bytes(m["video_url"], resolve_referer(m["video_url"]), timeout=120)
        if not vid_data:
            log(f"  [{i+1}/{len(moments)}] 视频下载失败，跳过")
            continue
        vid_key = f"square/original/{time.strftime('%Y/%m/%d')}/{uuid.uuid4().hex}.mp4"
        vid_url = upload_to_s3(vid_data, vid_key, "video/mp4", creds)
        if not vid_url:
            log(f"  [{i+1}/{len(moments)}] 视频上传失败，跳过")
            continue

        cover_url_s3 = ""
        if m.get("cover_url"):
            cov_data = download_bytes(m["cover_url"], resolve_referer(m["cover_url"]), timeout=30)
            if cov_data:
                cov_key = f"square/original/{time.strftime('%Y/%m/%d')}/{uuid.uuid4().hex}.jpg"
                cover_url_s3 = upload_to_s3(cov_data, cov_key, "image/jpeg", creds) or ""

        ok, mid = publish_moment(token, m["content"], vid_url, cover_url_s3)
        if ok:
            log(f"  [{i+1}/{len(moments)}] ✓ {acc['nickname']} moment_id={mid}")
            published.append({
                "moment_id": mid,
                "content": m["content"],
                "note_id": m["note_id"],
                "account": acc["nickname"],
                "email": acc["email"],
            })
        else:
            log(f"  [{i+1}/{len(moments)}] ✗ 发布失败: {mid}")

        time.sleep(args.login_spacing * 0.5)

    log(f"\n[Phase 2] 成功发布 {len(published)}/{len(moments)} 条视频")
    if not published:
        log("[error] 无成功发布，无法评论，退出")
        return 1

    # 保存发布结果
    with (wd / f"published_{ts}.json").open("w", encoding="utf-8") as f:
        json.dump(published, f, ensure_ascii=False, indent=2)

    # ── Phase 3+4: 评论互动 ────────────────────────────────────────
    if args.skip_comments:
        log("\n[skip-comments] 跳过评论")
        return 0

    if not published:
        log("[error] 无已发布视频，跳过评论")
        return 1

    pub_emails = {p["email"].lower() for p in published}
    used = load_used_emails() | pub_emails
    k = random.randint(args.min_cmt, args.max_cmt)
    n_en = round(k * 0.6)
    n_zh = k - n_en

    en_accts = load_670_accounts(n_en, lang="en", exclude=used)
    zh_accts = load_670_accounts(n_zh, lang="zh", exclude=used | {a["email"].lower() for a in en_accts})
    log(f"\n[Phase 3] 评论账号池：{len(en_accts)} 英文账号 + {len(zh_accts)} 繁中账号（共 {k} 计划）")

    # 任务分配：每个评论账号随机对应一条已发布视频
    # 缺额时用另一语言账号兜底，确保总评论数尽量达到 k
    tasks: list[dict] = []
    for a in en_accts:
        vid = random.choice(published)
        tasks.append({"account": a, "lang": "en", "post": vid})
    for a in zh_accts:
        vid = random.choice(published)
        tasks.append({"account": a, "lang": "zh", "post": vid})
    # 若繁中账号不足，用多余英文账号补到 k 条（标记为 en）
    short = k - len(tasks)
    if short > 0:
        used_emails = {a["email"].lower() for a in en_accts + zh_accts}
        filler = load_670_accounts(short, lang="en", exclude=used | used_emails)
        for a in filler:
            vid = random.choice(published)
            tasks.append({"account": a, "lang": "en", "post": vid})
        if not filler:
            log(f"  [warn] 账号池不足，实际 {len(tasks)}/{k}")
    random.shuffle(tasks)

    # 评论账号 token 缓存
    cmt_tokens: dict[str, str] = {}

    def get_cmt_token(acc: dict) -> str | None:
        email = acc["email"].lower()
        if email in cmt_tokens:
            return cmt_tokens[email]
        # 先查 tokens.json
        tok = None
        if TOKENS_PATH.exists():
            try:
                toks = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
                tok = toks.get(acc["email"])
            except Exception:
                tok = None
        if tok:
            cmt_tokens[email] = tok
            return tok
        tok = _login(acc["email"], acc["password"])
        if tok:
            cmt_tokens[email] = tok
        return tok

    log(f"\n[Phase 4] 发评论（{len(tasks)} 条，结合视频文本，60% 英文 / 40% 繁中）")
    success = 0
    cmt_report: list[dict] = []
    for i, t in enumerate(tasks):
        acc, lang, post = t["account"], t["lang"], t["post"]
        comment_text = make_comment(post["content"], lang)
        tok = get_cmt_token(acc)
        if not tok:
            log(f"  [{i+1}/{len(tasks)}] {acc['nickname']} 登录失败")
            cmt_report.append({"account": acc["nickname"], "moment": post["moment_id"],
                              "lang": lang, "text": comment_text, "status": "LOGIN_FAIL"})
            continue
        ok, reason = post_comment(tok, post["moment_id"], comment_text)
        if ok:
            success += 1
            log(f"  [{i+1}/{len(tasks)}] ✓ {acc['nickname']} ({lang}) → {post['moment_id']}")
        else:
            log(f"  [{i+1}/{len(tasks)}] ✗ {acc['nickname']} ({lang}) → {reason[:40]}")
        cmt_report.append({"account": acc["nickname"], "moment": post["moment_id"],
                           "lang": lang, "text": comment_text, "status": "OK" if ok else f"FAIL:{reason}"})
        if i < len(tasks) - 1:
            time.sleep(args.cmt_delay + random.uniform(0.5, 1.5))

    with (wd / f"comments_{ts}.json").open("w", encoding="utf-8") as f:
        json.dump(cmt_report, f, ensure_ascii=False, indent=2)

    # 保存 tokens 供后续复用
    if cmt_tokens:
        try:
            merged = json.loads(TOKENS_PATH.read_text(encoding="utf-8")) if TOKENS_PATH.exists() else {}
            merged.update(cmt_tokens)
            TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOKENS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    log(f"\n{'═'*60}")
    log(f"  完成：发布 {len(published)} 视频帖 | 评论 {success}/{len(tasks)}")
    log(f"  运行目录：{wd.name}")
    log(f"{'═'*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
