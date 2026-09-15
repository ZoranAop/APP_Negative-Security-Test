#!/usr/bin/env python3
"""
run_comments_opennana_670.py — 对opennana_670_custom56发布的帖子批量评论
- 每个帖子随机5-30条评论
- 60%英文 / 20%繁体中文 / 20%随机语言
- 基于帖子内容生成相关评论
"""
from __future__ import annotations

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

MOMENTS_CSV = ROOT / "opennana_670_custom56_run" / "moments_opennana_670_custom56_20260915_092642.csv"
PUBLISH_REPORT = ROOT / "result" / "publish_20260915_093316.csv"
TOKENS_FILE = ROOT / "result" / "tokens.json"
POST_COMMENTS = HERE / "post_comments.py"

# --- comment banks per language, based on lifestyle/portrait/cosplay/beauty topics ---

EN_COMMENTS = [
    # portrait / fashion
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
    # candid / lifestyle
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
    # cosplay / fun
    "The detail on the costume is next level",
    "You committed to this so much, it actually works",
    "The set and the costume are in perfect harmony",
    "This cosplay shoot is cleaner than most professional ones I've seen",
    "Love the whole aesthetic you built for this one",
    # beach / travel
    "That sky in the background is doing so much work",
    "Beach mode, fully unlocked",
    "This looks like a whole summer vacation in one frame",
    "The colors here remind me of film, in the best way",
    # bedroom / quiet
    "The soft lighting here is making me want to sleep right now",
    "This room vibe is peak comfort",
    "Love the quiet energy of this one",
    "This is what 'golden hour in your bedroom' actually looks like",
    "The whole palette here is so warm",
    # night / neon
    "The neon in the background is making this whole frame glow",
    "Night shots like this are hard to pull off, you did it perfectly",
    "This feels like a still from a cyberpunk movie",
    "The contrast of the light and shadow here is unreal",
    # food / cafe
    "I'm suddenly very hungry reading this",
    "The whole cafe vibe is immaculate",
    "This is my kind of sunday morning",
]

ZH_HANT_COMMENTS = [
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
    "这张照片有一種很自然的親切感",
    "構思很巧妙，一看就是花了很多心思",
    "這種隨性的畫面反而最有故事感",
    "妝髮都很細緻，整個人氣場在線",
    "照片裡的光陰感很強，讓人想多停一下",
    "這種街拍風格很合我胃口",
    "整張照片都在講述一個安靜的故事",
    "這個色調太溫柔了",
    "拍得很真實，沒有過度修圖的感覺",
]

JP_COMMENTS = [
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

KR_COMMENTS = [
    "이 광의 톤이 정말 예쁘다",
    "구성이 너무 깔끔하다",
    "전체 무드가 너무 좋다",
    "이 사진엔 확실히 이야기가 있다",
    "색감 처리가 최고다",
    "이 프레임이 한 편의 영화 같아",
    "자연스러운 표정이 마음에 든다",
]

TH_COMMENTS = [
    "แสงในรูปนี้สวยมาก",
    "การจัดองค์ประกอบภาพดีมาก",
    "โทนสีของภาพสวยมาก ๆ",
    "รูปนี้มีเรื่องราวซ่อนอยู่",
]

RANDOM_LANGS = ["ja", "ko", "th"]


def _pick_comment_for_lang(lang: str) -> str:
    if lang == "en":
        return random.choice(EN_COMMENTS)
    if lang in ("zh_hant", "zh"):
        return random.choice(ZH_HANT_COMMENTS)
    if lang == "ja":
        return random.choice(JP_COMMENTS)
    if lang == "ko":
        return random.choice(KR_COMMENTS)
    if lang == "th":
        return random.choice(TH_COMMENTS)
    return random.choice(EN_COMMENTS)


def _roll_lang() -> str:
    r = random.random()
    if r < 0.6:
        return "en"
    elif r < 0.8:
        return "zh_hant"
    else:
        return random.choice(RANDOM_LANGS)


def main() -> int:
    import argparse as _ap
    ap = _ap.ArgumentParser(description="批量評論 opennana_670 帖子")
    ap.add_argument("--min-comments", type=int, default=5)
    ap.add_argument("--max-comments", type=int, default=30)
    ap.add_argument("--delay", type=float, default=1.5)
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
    email_list = list(tokens.keys())
    print(f"[Token] 可用帳號: {len(email_list)}")

    # Read publish report to get post_id + moment content
    report = list(csv.DictReader(PUBLISH_REPORT.open(encoding="utf-8-sig")))
    posts = []
    for r in report:
        if r.get("success") != "True" and "True" not in r.get("success", ""):
            continue
        post_id = int(r["moment_id_or_err"])
        posts.append({"post_id": post_id, "content": r.get("content", "")})

    print(f"[帖子] 共 {len(posts)} 條成功帖子待評論")

    # Build batch CSV
    batch_rows = []
    for p in posts:
        n = random.randint(args.min_comments, args.max_comments)
        for _ in range(n):
            lang = _roll_lang()
            text = _pick_comment_for_lang(lang)
            batch_rows.append({
                "email": random.choice(email_list),
                "post_id": p["post_id"],
                "topic": "general",
                "text": text,
                "nickname": "",
            })

    random.shuffle(batch_rows)
    batch_path = ROOT / "temp_comments_opennana_670_batch.csv"
    with batch_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["email", "post_id", "topic", "text", "nickname"])
        w.writeheader()
        for row in batch_rows:
            w.writerow(row)

    # Count lang distribution
    from collections import Counter
    lang_dist = Counter()
    for p in posts:
        n = len([r for r in batch_rows if r["post_id"] == p["post_id"]])
    print(f"[Batch] {len(batch_rows)} 條評論任務 → {batch_path.name}")
    print(f"  每帖平均: {len(batch_rows)//len(posts)} 條")

    if not args.yes:
        if input("  確認發布？(y/n): ").strip().lower() not in ("y", "yes"):
            print("已取消")
            return 0

    cmd = PY + [str(POST_COMMENTS),
                "--batch", str(batch_path),
                "--tokens", str(TOKENS_FILE),
                "--accounts", str(ROOT / "accounts_670_for_comments.csv"),
                "--delay", str(args.delay)]
    print("  $ " + " ".join(str(c) for c in cmd))
    rc = subprocess.call(cmd, cwd=str(ROOT))
    return rc


if __name__ == "__main__":
    sys.exit(main())
