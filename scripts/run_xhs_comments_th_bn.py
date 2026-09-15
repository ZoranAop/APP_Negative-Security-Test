#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_xhs_comments_th_bn.py — 泰语 + 孟加拉语评论互动

针对 pre_企管用户_850 池已发布的 140 条 XHS 视频帖，
从「街拍摄影师池 + op200 运营列表」随机抽账号，
每帖 3-15 条评论（随机），语言混合：泰语 + 孟加拉语 + 英文兜底。

账号来源：
  1. pre_企管用户_街拍摄影师.csv  （180 账号）
  2. accounts_interact_200_20260827.csv（op200 运营列表，200 账号）

用法:
  py -3 -X utf8 scripts/run_xhs_comments_th_bn.py --yes
  py -3 -X utf8 scripts/run_xhs_comments_th_bn.py --min-cmt 3 --max-cmt 15 --yes
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

try:
    import requests
except ImportError:
    print("[FATAL] requests not installed", file=sys.stderr)
    sys.exit(1)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

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
COMMENTS_API = os.getenv("MOMENTS_API_URL", "https://feed-api.xxai.com/api/v1/moments/").replace("/moments/", "/comments/")
if "comments" not in COMMENTS_API:
    COMMENTS_API = "https://feed-api.xxai.com/api/v1/comments"

TOKENS_PATH = ROOT / "result" / "tokens.json"
CSV_850 = ROOT / "pre_企管用户_850.csv"
CSV_STREET = ROOT / "pre_企管用户_街拍摄影师.csv"
CSV_OP200 = ROOT / "accounts_interact_200_20260827.csv"

try:
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8",
                      buffering=1, errors="replace")
    sys.stderr = open(sys.stderr.fileno(), mode="w", encoding="utf-8",
                      buffering=1, errors="replace")
except Exception:
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 泰语 / 孟加拉语 / 英文 评论库
# ═══════════════════════════════════════════════════════════════════════════════

TH_COMMENTS: dict[str, list[str]] = {
    "food": [
        "เมนูนี้ดูน่ากินมาก เลยนะคะ",
        "ทำง่ายๆ แถมอร่อยด้วย ชอบมากค่ะ",
        "อยากลองทำตามเลยค่ะ รับรองว่าเข้ากันดีแน่",
        "ดูแล้วน้ำลายไหลเลยค่ะ เมนูนี้ควรค่าแก่การลอง",
        "ใครอยู่คนเดียวก็ทำได้เหมือนกันนะคะ",
        "วัตถุดิบไม่เยอะ แต่รสชาติเยี่ยมเลยค่ะ",
    ],
    "beauty": [
        "ลุคนี้ดูเรียบร้อยมาก ชอบมากค่ะ",
        "สอนได้ดีมากค่ะ ทำตามง่าย",
        "สีนี้เข้ากับผิวมากเลยนะคะ",
        "ดูเป็นธรรมชาติมากค่ะ ชอบที่สุด",
        "เก็บไว้ลองทำแน่นอน",
        "เทคนิคสวยมากค่ะ ใครทำเป็นเยอะจริง",
    ],
    "fashion": [
        "ชุดนี้ดูดีมากค่ะ ชอบสไตล์นี้",
        "ผสมสีเก่งมากค่ะ ดูเข้ากันดี",
        "เก็บไว้เป็นไอเดียแน่นอน",
        "ลุคนี้เหมาะกับฤดูกาลนี้มาก",
        "แต่งตัวเก่งมากค่ะ รับรองว่าใครเห็นก็ชอบ",
        "อยากลองทำตามดูเลยค่ะ",
    ],
    "fitness": [
        "ท่านี้ทำให้เห็นภาพชัดมากค่ะ",
        "ลองทำตามแล้วผลดีมาก",
        "จังหวะดีมากๆ ค่ะ ชอบ",
        "ขอบคุณที่สอนค่ะ",
        "ฝึกไปเรื่อยๆ จะเห็นผลแน่นอน",
        "วิดีโอนี้ช่วยให้เข้าใจง่ายมาก",
    ],
    "travel": [
        "สถานที่นี้ดูสวยมากค่ะ อยากไปมาก",
        "มุมกล้องดีมากๆ ค่ะ",
        "ฟังแล้วเหมือนในฝันเลย",
        "วางแผนไปเที่ยวแน่นอน",
        "บรรยากาศนี้ดีใจมากที่เห็น",
        "ใครแนะนำที่พักแถวนั้นบ้างคะ",
    ],
    "pet": [
        "ขนปุยมากค่ะ น่ารักจริงๆ",
        "ดูแล้วยิ้มไปทั้งวันเลย",
        "ดูซ้ำสามรอบแล้วค่ะ",
        "นี่คือคอนเทนต์ที่ฮีลใจจริงๆ",
        "ซื้อตัวนี้ได้ยังไงคะ?",
        "看完วิดีโอแล้วดีใจมาก",
    ],
    "home": [
        "มุมนี้ดูอบอุ่นมากค่ะ",
        "จัดวางดีมาก น่าทำตาม",
        "อยากแต่งห้องแบบนี้บ้าง",
        "ของตกแต่งดูดีทั้งนั้นเลยค่ะ",
        "พืชในบ้านทำให้สวยขึ้นมาก",
        "ไอเดียดีเก็บไว้แน่นอน",
    ],
    "general": [
        "วิดีโอนี้ดูสนุกมากค่ะ",
        "ดูจบทั้งเรื่องแล้ว ชอบมาก",
        "จังหวะตัดต่อดีเยี่ยม",
        "เพลงประกอบเข้ากับคอนเทนต์มาก",
        "ขอบคุณที่แชร์นะคะ",
        "ดูซ้ำแล้วซ้ำอีก",
        "วิดีโอที่ดีที่สุดในวันนี้เลย",
        "เก็บไว้ในรายการแล้วค่ะ",
    ],
}

BN_COMMENTS: dict[str, list[str]] = {
    "food": [
        "এটা দেখে আসলেই ক্ষুধা পেয়েছি, খাবারটা খুব সুন্দর লাগছে!",
        "রান্নার পদ্ধতিটা খুব সহজ আর দারুণ, আমি অবশ্যই চেষ্টা করবো।",
        "রেসিপিটা অনেক ভালো, ধন্যবাদ শেয়ার করার জন্য!",
        "খাবারের উপকরণগুলো একসাথে দারুণ, কাল থেকে একটু করে বানাবো।",
        "দুর্দান্ত টেস্ট, আমি সত্যিই পছন্দ করেছি!",
        "একমাত্র মানুষের জন্যও পারফেক্ট, খুবই সুন্দর!",
    ],
    "beauty": [
        "মেকআপের লুকটা দারুণ, খুব প্র্যাকটিক্যাল লাগছে!",
        "কালার কম্বিনেশনটা অনেক সুন্দর, আমি পছন্দ করছি।",
        "রুটিনটা খুব সিম্পল কিন্তু কার্যকর, ভালো দেখলাম!",
        "আগামী রাতের জন্য সেভ করেছি!",
        "স্কিনের টেক্সচারটা দেখে চমকে গেছি, দারুণ!",
        "ধন্যবাদ শেয়ার করার জন্য, সত্যিই সহায়ক।",
    ],
    "fashion": [
        "আউটফিটটা দারুণ ক্লিন আর এফোর্টলেস লাগছে!",
        "স্টাইল দেখে অনেক ভালো লেগেছে!",
        "কালারগুলোর কম্বিনেশনটা দারুণ, খুব সৌন্দর্য্য।",
        "স্টাইলিং রিফারেন্স হিসেবে সেভ করলাম!",
        "সিজনের জন্য পারফেক্ট লুক!",
        "আমার আগামী ফিটের অনুপ্রেরণা!",
    ],
    "fitness": [
        "মোভমেন্ট টিপটা সত্যিই কাজ করে, এখন বুঝতে পারছি!",
        "সবশেষ কারোকে এত স্পষ্ট ব্যাখ্যা করতে দেখলাম!",
        "এই রুটিনটা করছি আর ফল পাচ্ছি!",
        "ওয়ার্কআউটের পেসিংটা পারফেক্ট!",
        "এই ভিডিও দেখে আগামীকাল শুরু করার ভরসা পেলাম!",
        "প্র্যাকটিকাল ব্যাখ্যা, ধন্যবাদ!",
    ],
    "travel": [
        "এই জায়গাটা অস্বাভাবিক সুন্দর, আমার লিস্টে যোগ করেছি!",
        "সিনেমাটোগ্রাফিটা অসাধারণ, মন শান্ত করে দেয়!",
        "তোমার গল্পের পর সত্যিই যেতে ইচ্ছা করছে!",
        "পরবর্তী ট্রিপ প্ল্যানিংয়ের জন্য সেভ করলাম!",
        "এই জায়গার ভাইবটা ঠিক যেটা এখন প্রয়োজন!",
        "এই জাতীয় এক্সক্যাপ এখন বেশ লাগবে!",
    ],
    "pet": [
        "এর ফাফটা অবিশ্বাস্য, খুবই মিষ্টি!",
        "এই ছোট্ট মুখটা আমার পুরো দিনটা বদলে দিল!",
        "তিনবার দেখেছি, হাসি থামছে না!",
        "এটা ঠিক কামফোর্ট কন্টেন্ট!",
        "এই জাতীয়টা কোথায় পাবো?",
        "ইনস্ট্যান্ট সিরোটোনিন, ধন্যবাদ!",
    ],
    "home": [
        "এই স্পেসটা খুব আরামদায়ক লাগছে, দারুণ সেটআপ!",
        "এতটা তাত্পর্য দিয়ে সাজানো দেখে অনুপ্রাণিত হয়েছি!",
        "আমার ঘরে একটু এই ধরনের আইডিয়া যোগ করবো!",
        "এই ছোট্ট কর্নারটা খুব সুন্দর টাচ!",
        "গাছপালার জন্য পুরো স্পেস জীবন্ত হয়ে গেছে!",
        "সেটআপ রিফ্রেশের জন্য সেভ করলাম!",
    ],
    "general": [
        "এই ভিডিওটা দেখতে খুবই চাংপালো!",
        "ইনস্ট্যান্ট সেভ, আজকের জন্য দরকারি ক্লিপ!",
        "দুইবার দেখেছি, পেসিংটা পারফেক্ট!",
        "পূর্ণ ভার্সন কোথায়? আরও চাই!",
        "এই ভিডিও আমার পুরো দিনটা বদলে দিল, ধন্যবাদ!",
        "বিজিএমের চয়েসটা পারফেক্ট!",
        "এটা আমার রিপ্লে লিস্টে যোগ করলাম!",
        "এই ভিডিওতে দারুণ এনার্জি আছে, ভালোবাসছি!",
    ],
}

EN_COMMENTS: dict[str, list[str]] = {
    "food": [
        "The plating on this is so clean, instant save.",
        "Watched while starving and now I need to cook tonight.",
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
        "Where's the link to this breed?",
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

# 语言比例: 泰语 40%, 孟加拉语 35%, 英文 25%
LANG_RATIOS = {"th": 0.4, "bn": 0.35, "en": 0.25}


def detect_topic(text: str) -> str:
    t = text.lower()
    kw_map = {
        "food": ["美食", "做饭", "早餐", "晚餐", "咖啡", "蛋糕", "甜点", "烘焙",
                "火锅", "寿司", "披萨", "面包", "茶", "noodle", "pizza", "coffee"],
        "beauty": ["化妆", "美妆", "护肤", "眼妆", "口红", "粉底", "美甲", "发型",
                 "makeup", "skincare", "nail"],
        "fashion": ["穿搭", "旗袍", "睡衣", "时尚", "outfit", "style", "fashion", "dress"],
        "fitness": ["健身", "减肥", "运动", "瑜伽", "腹肌", "跑步", "撸铁",
                   "fitness", "workout", "gym", "yoga"],
        "travel": ["旅行", "旅游", "度假", "民宿", "露营", "海岛", "景点", "打卡",
                  "travel", "trip", "vacation", "beach"],
        "pet": ["猫", "狗", "萌宠", "宠物", "仓鼠", "cat", "dog", "pet", "kitten"],
        "home": ["收纳", "家居", "布置", "装修", "房间", "书桌", "工位", "绿植", "花",
                "room", "home", "plant", "decor"],
    }
    for topic, kws in kw_map.items():
        for kw in kws:
            if kw in t:
                return topic
    return "general"


def pick_comment(text: str, lang: str) -> str:
    topic = detect_topic(text)
    bank = {"th": TH_COMMENTS, "bn": BN_COMMENTS, "en": EN_COMMENTS}[lang]
    pool = bank.get(topic) or bank["general"]
    return random.choice(pool)


def pick_lang() -> str:
    r = random.random()
    if r < LANG_RATIOS["th"]:
        return "th"
    elif r < LANG_RATIOS["th"] + LANG_RATIOS["bn"]:
        return "bn"
    return "en"


# ═══════════════════════════════════════════════════════════════════════════════
# 账号加载
# ═══════════════════════════════════════════════════════════════════════════════

def load_accounts_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig") as f:
        out = []
        for row in csv.DictReader(f):
            email = (row.get("邮箱") or "").strip()
            pwd = (row.get("密码") or "").strip()
            nick = (row.get("昵称") or "").strip()
            pin = (row.get("pincode") or "").strip()
            if email and pwd:
                out.append({"email": email, "nickname": nick, "password": pwd, "pincode": pin})
        return out


def load_all_comment_accounts() -> list[dict]:
    """合并街拍摄影师 + op200 列表，去重。"""
    accounts = load_accounts_csv(CSV_STREET) + load_accounts_csv(CSV_OP200)
    seen: set[str] = set()
    deduped: list[dict] = []
    for a in accounts:
        e = a["email"].lower()
        if e in seen:
            continue
        seen.add(e)
        deduped.append(a)
    return deduped


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


def load_published_posts() -> list[dict]:
    """加载所有已发布的 XHS 视频帖（from xhs_video_850_cmt_run）。"""
    posts: list[dict] = []
    seen: set[str] = set()
    for f in sorted(ROOT.glob("xhs_video_850_cmt_run/published_*.json"),
                   key=lambda x: x.stat().st_mtime):
        try:
            for p in json.loads(f.read_text(encoding="utf-8")):
                mid = p.get("moment_id", "")
                if mid and mid not in seen:
                    seen.add(mid)
                    posts.append({"moment_id": mid, "content": p.get("content", ""),
                                  "account": p.get("account", "")})
        except Exception:
            pass
    return posts


# ═══════════════════════════════════════════════════════════════════════════════
# 登录 & 评论
# ═══════════════════════════════════════════════════════════════════════════════

def login_with_backoff(email: str, pwd: str) -> str | None:
    for attempt in range(5):
        try:
            r = requests.post(LOGIN_URL, json={
                "email": email, "password": pwd,
                "device_id": "auto_poster", "device_name": "auto_poster_client",
            }, timeout=20)
            if r.status_code == 429:
                time.sleep(3.0 * (2 ** attempt))
                continue
            if r.status_code == 200:
                j = r.json()
                if j.get("code") == 0:
                    return (j.get("data") or {}).get("token")
        except Exception:
            time.sleep(2)
    return None


def post_comment(token: str, moment_id: str, content: str) -> tuple[bool, str]:
    try:
        r = requests.post(COMMENTS_API,
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-cmt", type=int, default=3, help="每帖最少评论数（默认 3）")
    ap.add_argument("--max-cmt", type=int, default=15, help="每帖最多评论数（默认 15）")
    ap.add_argument("--delay", type=float, default=2.0, help="评论间隔秒数")
    ap.add_argument("--workdir", default="th_bn_cmt_run")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    # 加载已发布帖子
    posts = load_published_posts()
    log(f"[posts] 加载 {len(posts)} 条已发布 XHS 视频帖")
    if not posts:
        log("[error] 无已发布帖子"); return 1

    # 加载评论账号（合并去重，排除已用）
    all_accounts = load_all_comment_accounts()
    used = load_used_emails()
    available = [a for a in all_accounts if a["email"].lower() not in used]
    log(f"[accounts] 可用评论账号 {len(available)}/{len(all_accounts)}")

    if not args.yes:
        if input("\n确认发评论？(y/n): ").strip().lower() not in ("y", "yes"):
            log("取消"); return 0

    # 每帖随机 3-15 条，语言 40% th / 35% bn / 25% en
    tasks: list[dict] = []
    tokens_cache: dict[str, str] = {}
    total = 0

    for i, post in enumerate(posts):
        n_cmt = random.randint(args.min_cmt, args.max_cmt)
        total += n_cmt
        log(f"  [{i+1}/{len(posts)}] moment={post['moment_id']} → {n_cmt} 条评论")

    log(f"\n[plan] 共 {total} 条评论，跨 {len(posts)} 帖子")

    success = 0
    report: list[dict] = []
    tokens_cache: dict[str, str] = {}

    # ── 先批量登录所有需要的账号，避免逐条触发登录 429 ──
    needed_accounts: list[dict] = []
    seen_acct: set[str] = set()
    for i, post in enumerate(posts):
        n_cmt = random.randint(args.min_cmt, args.max_cmt)
        for j in range(n_cmt):
            acct = available[(i * 30 + j) % len(available)] if available else None
            if acct and acct["email"].lower() not in seen_acct:
                seen_acct.add(acct["email"].lower())
                needed_accounts.append(acct)
    log(f"\n[login] 批量登录 {len(needed_accounts)} 个唯一账号")
    for idx, a in enumerate(needed_accounts):
        key = a["email"].lower()
        if key in tokens_cache:
            continue
        tok = login_with_backoff(a["email"], a["password"])
        if tok:
            tokens_cache[key] = tok
            log(f"  [{idx+1}/{len(needed_accounts)}] ✓ {a['nickname']}")
        else:
            log(f"  [{idx+1}/{len(needed_accounts)}] ✗ {a['nickname']} 登录失败")
        time.sleep(1.0)  # 登录间隔，降低 429 概率

    # ── 发评论 ──
    for i, post in enumerate(posts):
        n_cmt = random.randint(args.min_cmt, args.max_cmt)
        for j in range(n_cmt):
            lang = pick_lang()
            text = pick_comment(post["content"], lang)
            acct = available[(i * 30 + j) % len(available)] if available else None
            if not acct:
                break
            tok = tokens_cache.get(acct["email"].lower())
            if not tok:
                log(f"  [{i+1}.{j+1}] {acct['nickname']} 无 token，跳过")
                report.append({"post": post["moment_id"], "account": acct["nickname"],
                              "lang": lang, "text": text, "status": "NO_TOKEN"})
                continue
            ok, reason = post_comment(tok, post["moment_id"], text)
            success += 1 if ok else 0
            report.append({"post": post["moment_id"], "account": acct["nickname"],
                           "lang": lang, "text": text, "status": "OK" if ok else f"FAIL:{reason}"})
            time.sleep(args.delay + random.uniform(0.5, 1.5))

    # 保存结果
    with (wd / f"th_bn_comments_{ts}.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 持久化 tokens
    if tokens_cache:
        try:
            merged = json.loads(TOKENS_PATH.read_text(encoding="utf-8")) if TOKENS_PATH.exists() else {}
            merged.update(tokens_cache)
            TOKENS_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    log(f"\n{'═'*60}")
    log(f"  完成：{success}/{total} 条评论")
    log(f"  运行目录：{wd.name}")
    log(f"{'═'*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
