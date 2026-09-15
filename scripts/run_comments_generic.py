#!/usr/bin/env python3
"""
run_comments_generic.py — 通用帖子批量评论发布工具
支持图文贴 / 纯文本贴，任意 publish report，670 账号池或 100/220 互动池。

用法：
    py -3 scripts/run_comments_generic.py \
        --report result/publish_20260915_093316.csv \
        --pool 670 \
        --min-comments 5 \
        --max-comments 30 \
        --yes

    # 纯文本贴（指定语言分布：全英文）
    py -3 scripts/run_comments_generic.py \
        --report result/publish_xxx.csv \
        --pool 670 \
        --lang-mix en:1.0 \
        --min-comments 3 \
        --max-comments 10

参数说明：
    --report        发布报告 CSV 路径（result/publish_*.csv）
    --pool          用户池: 670 | 100 | 220 | all
    --lang-mix      语言分布 "en:0.6:zh_hant:0.2:ja:0.1:ko:0.1" (默认 0.6/0.2/0.2随机)
    --min-comments  每帖最少评论数
    --max-comments  每帖最多评论数
    --topic         评论话题: beauty | web3 | general | auto
    --delay         评论间隔秒数
    --tokens        token 文件路径
    --yes           跳过确认直接执行
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]
TOKENS_FILE = ROOT / "result" / "tokens.json"
POST_COMMENTS = HERE / "post_comments.py"

# ─── 评论语料库（按话题）────────────────────────────────────────────────────

BEAUTY_EN = [
    "This lighting is insane, how did you get it so soft?",
    "The way the fabric catches light here is perfect",
    "This photo has such a cinematic quality to it, love it",
    "Ootd fire. The fit works so well for this setting",
    "The composition here is clean, you nailed the framing",
    "This shot has that editorial look, really impressive",
    "Love the color grading, the whole mood is there",
    "The background is so subtle but adds to the whole feel",
    "This is the kind of shot that just works without trying",
    "Golden hour really shows up in this one",
    "The way you styled your hair for this is perfect",
    "This is pure film aesthetic, I'm saving this one",
    "The contrast between the subject and background here is beautiful",
    "You captured a whole moment in one frame",
    "This is exactly the kind of photo that makes me stop scrolling",
    "The light in the background is so flattering",
    "This is a 10/10 for texture and mood",
    "I've been trying to get this kind of shot for weeks, you made it look effortless",
    "The softness in this one is unreal",
    "This belongs on a magazine cover",
    "This feels so natural, no forced posing at all",
    "Love that you captured this unfiltered moment",
    "The casual energy here is perfect, very real",
    "This is the kind of snapshot that actually matters",
    "You made everyday look stunning",
    "So genuine and I mean that in the best way",
    "The little details in this are what make it special",
    "This photo tells a whole story without saying a word",
    "I could stare at this one for a while",
    "The candid vibe here is so good",
    "The detail on the costume is next level",
    "You committed to this so much, it actually works",
    "The set and the costume are in perfect harmony",
    "Love the whole aesthetic you built for this one",
    "That sky in the background is doing so much work",
    "Beach mode, fully unlocked",
    "This looks like a whole summer vacation in one frame",
    "The colors here remind me of film, in the best way",
    "The soft lighting here is making me want to sleep right now",
    "This room vibe is peak comfort",
    "Love the quiet energy of this one",
    "The whole palette here is so warm",
    "The neon in the background is making this whole frame glow",
    "Night shots like this are hard to pull off, you did it perfectly",
    "This feels like a still from a cyberpunk movie",
    "The contrast of the light and shadow here is unreal",
    "I'm suddenly very hungry reading this",
    "The whole cafe vibe is immaculate",
    "This is my kind of sunday morning",
]

BEAUTY_ZH_HANT = [
    "這張照片的光線真的太美了，柔到不行",
    "構圖乾淨，很喜歡這種留白感",
    "服裝搭配得好，整個氛圍對了",
    "這張真的很有電影感，收藏了",
    "抓拍得太好，沒有刻意擺pose的味道",
    "色調處理得很舒服，一眼就喜歡",
    "這套衣服好適合這種場景",
    "整體質感很高級，拍得很用心",
    "光線從側面打過來的效果特別好",
    "這種安靜的畫面最容易打動人",
    "背景雖然是簡單的，但反而讓主題更突出",
    "構思很巧妙，一看就是花了很多心思",
    "這種隨性的畫面反而最有故事感",
    "妝髮都很細緻，整個人氣場在線",
    "照片裡的光陰感很強，讓人想多停一下",
    "這種街拍風格很合我胃口",
    "整張照片都在講述一個安靜的故事",
    "這個色調太溫柔了",
    "拍得很真實，沒有過度修圖的感覺",
    "看了這張照片心情都變好了",
]

BEAUTY_JA = [
    "この光の加減がほんとに好き",
    "構図がすっとしていて、すごく落ち着く",
    "全体のトーンがやわらかくていい感じ",
    "この一枚には物語がある気がする",
    "色使いがすごく素敵",
    "この雰囲気、何の映画のワンシーンに見える",
    "光の角度が完璧",
    "こういう静かなカットが一番好き",
    "背景とのバランスがきれいに取れてますね",
    "この一枚、本当に残したくなるショット",
    "全体の質感が高い",
    "自然な表情がすごくいい",
    "この構図、勉強になります",
    "光が当たった瞬間がきれいに捉えてある",
    "こういう日常の一コマが一番好きなタイプ",
]

BEAUTY_KO = [
    "이 광의 톤이 정말 예쁘다",
    "구성이 너무 깔끔하다",
    "전체 무드가 너무 좋다",
    "이 사진엔 확실히 이야기가 있다",
    "색감 처리가 최고다",
    "이 프레임이 한 편의 영화 같아",
    "자연스러운 표정이 마음에 든다",
]

BEAUTY_TH = [
    "แสงในรูปน้ีสวยมาก",
    "การจัดองคก์ประกอบภาพดมีี",
    "โทนสสีีของภาพสวยมาก ๆ",
    "ร้ปนี้มีีเรื่่องราวซ่อนอยู่",
]

WEB3_EN = [
    "Solid analysis, the data checks out completely.",
    "I've been watching this space and this is a well-written take.",
    "The ETF inflow data really does change the narrative here.",
    "Not financial advice but I'm getting more bullish on this thesis.",
    "The institutional adoption curve is steeper than most people expect.",
    "This is exactly the kind of deep dive the community needs more of.",
    "I was skeptical until I read the L2 transaction volumes — game changed.",
    "The narrative has completely flipped. What was speculative is now structural.",
    "Watching the weekly flow data like a hawk — something's shifting.",
    "My portfolio feels more comfortable with this kind of exposure now.",
]

WEB3_ZH_HANT = [
    "分析得很透，數據都對得上。",
    "這篇深度文章正好填補市場空白。",
    "機構採用曲線比多數人想像的還要陡。",
    "看完後對這個賽道的信心提升不少。",
    "L2 的成交數據真的改變了整個敘事。",
    "這種深度研究在中文圈很稀缺。",
    "長期看好，短期波動很正常。",
    "收藏了，空閒時候仔細再讀一遍。",
]

WEB3_JA = [
    "データがしっかりしていて、信頼できる分析です。",
    "L2の採用速度は想像以上でした。",
    "この視点は以前誰も上げていなかった。",
    "長期で見たら、この流れは逆転できないと思います。",
]

GENERAL_EN = [
    "Really appreciate you sharing this.",
    "This resonated with me more than expected.",
    "Great post, very informative.",
    "I was looking for exactly this kind of content.",
    "Well written and thought-provoking.",
    "This is the kind of post that gets bookmarked.",
    "Added to my reading list, thanks!",
    "Finally someone said it out loud.",
]

GENERAL_ZH_HANT = [
    "說得好，非常有共鳴。",
    "這種分享太有價值了。",
    "看完收穫很多，感謝分享。",
    "說到了我心裡。",
]

GENERAL_JA = [
    "こういう記事、本当に嬉しくなります。",
    "とても参考になりました。",
]

RANDOM_LANGS = ["ja", "ko", "th"]

TOPIC_MAP = {
    "beauty": {
        "en": BEAUTY_EN, "zh_hant": BEAUTY_ZH_HANT,
        "ja": BEAUTY_JA, "ko": BEAUTY_KO, "th": BEAUTY_TH,
    },
    "web3": {
        "en": WEB3_EN, "zh_hant": WEB3_ZH_HANT,
        "ja": WEB3_JA, "ko": BEAUTY_KO, "th": BEAUTY_TH,
    },
    "general": {
        "en": GENERAL_EN, "zh_hant": GENERAL_ZH_HANT,
        "ja": GENERAL_JA, "ko": BEAUTY_KO, "th": BEAUTY_TH,
    },
}

# ─── 用户池加载 ────────────────────────────────────────────────────────────

POOL_FILES = {
    "670": ROOT / "互动用户池_670账号.xlsx",
    "100": ROOT / "互动用户池_100账号_完整信息.xlsx",
    "220": ROOT / "互动用户池_220账号_完整信息.xlsx",
}


def _load_pool_accounts(pool_name: str, exclude_emails: set) -> list[dict]:
    """从指定 xlsx 用户池加载账号，返回 [{email, nick, password}] 列表"""
    xlsx = POOL_FILES.get(pool_name)
    if not xlsx or not xlsx.exists():
        print(f"[ERROR] 用户池文件不存在: {xlsx}", file=sys.stderr)
        return []
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        d = dict(zip(headers, row))
        email = str(d.get("邮箱", "") or "").strip()
        if not email or email in exclude_emails:
            continue
        rows.append({
            "email": email,
            "nick": str(d.get("昵称", "") or ""),
            "password": str(d.get("密码", "") or ""),
        })
    wb.close()
    return rows


# ─── 评论选择 ──────────────────────────────────────────────────────────────

def _pick_lang(lang_mix: list[tuple[str, float]]) -> str:
    """按语言比例随机选一个语言。"""
    r = random.random()
    cumulative = 0.0
    for lang, prob in lang_mix:
        cumulative += prob
        if r <= cumulative:
            return lang
    return lang_mix[-1][0]


def _pick_comment(topic: str, lang: str, content_hint: str = "") -> str:
    """基于话题+语言从语料库随机选一条评论。"""
    bank = TOPIC_MAP.get(topic, TOPIC_MAP["general"])
    pool = bank.get(lang, bank.get("en"))
    if not pool:
        return random.choice(TOPIC_MAP["general"]["en"])
    return random.choice(pool)


def _parse_lang_mix(s: str) -> list[tuple[str, float]]:
    """解析 "en:0.6:zh_hant:0.2:ja:0.1:ko:0.1" 格式"""
    parts = s.split(":")
    result = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts):
            try:
                prob = float(parts[i + 1])
                result.append((parts[i], prob))
                i += 2
            except ValueError:
                break
        else:
            break
    if not result:
        result = [("en", 0.6), ("zh_hant", 0.2), ("ja", 0.1), ("ko", 0.1)]
    total = sum(p for _, p in result)
    return [(l, p / total) for l, p in result]


# ─── 主流程 ───────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="通用帖子批量评论发布工具")
    ap.add_argument("--report", required=True,
                    help="发布报告 CSV 路径（result/publish_*.csv）")
    ap.add_argument("--pool", default="670",
                    choices=list(POOL_FILES.keys()) + ["all"],
                    help="用户池: 670 | 100 | 220 | all(使用所有 token)")
    ap.add_argument("--lang-mix",
                    default="en:0.6:zh_hant:0.2:ja:0.1:ko:0.1",
                    help='语言分布 "en:0.6:zh_hant:0.2:ja:0.1:ko:0.1"')
    ap.add_argument("--min-comments", type=int, default=5)
    ap.add_argument("--max-comments", type=int, default=30)
    ap.add_argument("--topic", default="beauty",
                    choices=["beauty", "web3", "general", "auto"],
                    help="评论话题: beauty | web3 | general | auto(根据帖子内容)")
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--tokens", default=str(TOKENS_FILE))
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    tokens_path = Path(args.tokens)
    lang_mix = _parse_lang_mix(args.lang_mix)

    # 加载 token
    if not tokens_path.exists():
        print(f"[ERROR] token 文件不存在: {tokens_path}", file=sys.stderr)
        return 1
    tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
    print(f"[Token] 已加载 {len(tokens)} 个账号 token")

    # 读取发布报告获取帖子 ID 列表
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    if not report_path.exists():
        print(f"[ERROR] 报告文件不存在: {report_path}", file=sys.stderr)
        return 1
    report_rows = list(csv.DictReader(report_path.open(encoding="utf-8-sig")))
    posts = []
    for r in report_rows:
        pid = (r.get("moment_id_or_err") or "").strip()
        success = str(r.get("success", "")).strip()
        if pid.isdigit() and ("True" in success or "OK" in success):
            posts.append({
                "post_id": int(pid),
                "content": (r.get("content") or "").strip(),
                "lang": (r.get("_lang") or "").strip(),
                "email": (r.get("email") or "").strip(),
            })
    print(f"[帖子] 共 {len(posts)} 条成功帖子待评论")
    if not posts:
        print("[ERROR] 报告中没有成功帖子", file=sys.stderr)
        return 1

    # 确定评论话题
    topic = args.topic
    if topic == "auto":
        # 简单关键词检测
        topic = "beauty"
        all_content = " ".join(p["content"] for p in posts).lower()
        web3_kws = ["web3", "btc", "bitcoin", "eth", "crypto", "defi", "nft", "solana"]
        beauty_kws = ["beauty", "photo", "ootd", "portrait", "outfit", "fashion"]
        if any(k in all_content for k in web3_kws):
            topic = "web3"
        print(f"[auto] 检测到话题: {topic}")

    # 选择用户池
    if args.pool == "all":
        # 直接用已有 token 的账号（随机）
        available_emails = list(tokens.keys())
        print(f"[账号池] 使用全部 {len(available_emails)} 个已有 token 账号")
        accounts_pool = [{"email": e, "nick": "", "password": ""} for e in available_emails]
    else:
        used_emails = set(tokens.keys())
        accounts_pool = _load_pool_accounts(args.pool, used_emails)
        # 包含已有 token 的账号也可参与评论
        accounts_pool_with_tokens = []
        if args.pool in POOL_FILES:
            xlsx = POOL_FILES[args.pool]
            import openpyxl
            wb = openpyxl.load_workbook(xlsx, read_only=True)
            ws = wb.active
            headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
            for row in ws.iter_rows(min_row=2, values_only=True):
                d = dict(zip(headers, row))
                email = str(d.get("邮箱", "") or "").strip()
                if email in used_emails:
                    accounts_pool_with_tokens.append(
                        {"email": email,
                         "nick": str(d.get("昵称", "") or ""),
                         "password": str(d.get("密码", "") or "")})
            wb.close()
        print(f"[账号池] {args.pool}: 未用={len(accounts_pool)}  已用(token)={len(accounts_pool_with_tokens)}")
        accounts_pool = accounts_pool + accounts_pool_with_tokens

    if not accounts_pool:
        print("[ERROR] 没有可用账号，请检查用户池文件", file=sys.stderr)
        return 1

    # 生成评论任务
    batch_rows = []
    for p in posts:
        n = random.randint(args.min_comments, args.max_comments)
        for _ in range(n):
            lang = _pick_lang(lang_mix)
            text = _pick_comment(topic, lang, p.get("content", ""))
            acct = random.choice(accounts_pool)
            batch_rows.append({
                "email": acct["email"],
                "post_id": p["post_id"],
                "topic": topic,
                "text": text,
                "nickname": acct.get("nick", ""),
            })

    random.shuffle(batch_rows)
    ts = time.strftime("%Y%m%d_%H%M%S")
    batch_path = ROOT / f"temp_comments_generic_{ts}.csv"
    with batch_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["email", "post_id", "topic", "text", "nickname"])
        w.writeheader()
        for row in batch_rows:
            w.writerow(row)

    from collections import Counter
    lang_counter = Counter()
    for r in batch_rows:
        # infer lang from text
        t = r["text"]
        if any("\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff" for c in t):
            # CJK: distinguish ja vs zh
            ja_chars = sum(1 for c in t if "\u3040" <= c <= "\u30ff")
            lang_counter["ja" if ja_chars > 2 else "zh_hant"] += 1
        else:
            lang_counter["en"] += 1

    print(f"[Batch] {len(batch_rows)} 条评论任务 → {batch_path.name}")
    print(f"  每帖平均: {len(batch_rows) // max(len(posts), 1)} 条")
    print(f"  语言分布: {dict(lang_counter)}")

    if not args.yes:
        if input("  确认发布评论？(y/n): ").strip().lower() not in ("y", "yes"):
            print("已取消。")
            return 0

    # 构建账号 CSV 用于 post_comments.py 的 token 刷新
    accounts_csv = ROOT / f"accounts_for_comments_{ts}.csv"
    with accounts_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
        w.writeheader()
        for i, a in enumerate(accounts_pool):
            if a.get("password"):
                w.writerow({"序号": i + 1, "昵称": a.get("nick", ""),
                            "邮箱": a["email"], "密码": a["password"]})

    # 调用 post_comments.py 执行
    cmd = PY + [str(POST_COMMENTS),
                "--batch", str(batch_path),
                "--tokens", str(tokens_path),
                "--accounts", str(accounts_csv),
                "--delay", str(args.delay)]
    print("  $ " + " ".join(str(c) for c in cmd))
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        print("[ERROR] post_comments.py 返回非零，部分评论可能失败。", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
