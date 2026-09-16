#!/usr/bin/env python3
"""
run_comments_pexels_indian_7.py — 1-3 random-language comments per video post
for the 7 Pexels Indian-travel posts. EN-nick commenters, distinct voices.
"""
from __future__ import annotations

import argparse, csv, json, random, re, subprocess, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

POOL_850_CSV = ROOT / "pre_企管用户_850.csv"
PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"
TOKENS = ROOT / "result" / "tokens.json"
POST_COMMENTS = HERE / "post_comments.py"
EN_NICK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-\ ]*$")

# Per-style comment banks — each bank is tied to the voice used in the post
# to keep the "conversation" feel consistent.

BANKS = {
    # Matches caption 0 (documentary, restrained)
    "doc_restrained": {
        "en": [
            "The silence framing on this one is exactly what makes it work.",
            "You can feel the weight of that early-morning light.",
            "This is how you document a place without narrating it.",
        ],
        "ja": ["夜明けの光の感じが最高ですね。", "静けさを撮りようとは稀有な視点です。"],
        "ko": ["아침 어둠의 그 느낌을 잘 담았습니다.", "침묵으로 담는 방식이 참 독창적입니다."],
    },
    # Matches caption 1 (casual, self-deprecating)
    "casual_playful": {
        "en": [
            "The accidental frame is often the real one. No notes.",
            "Four hours of spice market chaos? That's the best kind of detour.",
            "This is the honest version of travel. I'm here for it.",
        ],
        "ja": ["偶然のショットこそ本物ですね。", "スパイス市場の4時間は最高でしたよ。"],
        "ko": ["우연한 프레임이 진짜 프레임이죠.", "향신료 시장 4시간 최고였어요."],
        "ar": ["الإطار الصدفي هو الحقيقي دائمًا.", "أربع ساعات في سوق التوابل — أفضل انحراف."],
    },
    # Matches caption 2 (poetic, minimal)
    "poetic_minimal": {
        "en": [
            "Pink light on sandstone at 5:47am — I'll remember this frame.",
            "Short and perfect. Sometimes that's all you need.",
            "The wait paid off. You can tell.",
        ],
        "ja": ["5時47分のピンクの光、覚えているわ。", "短くて完璧。それで十分。"],
        "ko": ["5:47 분 분홍빛, 기억할 거예요.", "짧고 완벽해요. 그것만으로도 충분합니다."],
        "th": ["แสงพ่ึงตอนตี 5 ครึ่่ง — จำชั้ดเจน", "สั้นแต่เพียบพร้่อง — ถ่องแท้"],
    },
    # Matches caption 3 (analytical, photographer's eye)
    "analytical": {
        "en": [
            "The DoF story is clearly doing all the heavy lifting here.",
            "Good call waiting for the frame to resolve itself.",
            "Background blur on sandstone — that's a strong choice.",
        ],
        "ja": ["DoF の使い方が的確ですね。", "フレームが自然に固まるまで待ったのが正解。"],
        "ko": ["DoF 활용이 정확합니다.", "프레임이 안정될 때까지 기다린 게 정답입니다."],
        "ar": ["استخدام عمق الميدان دقيق جداً.", "انتظار حتى يثبت الإطار كان قراراً صحيحاً."],
    },
    # Matches caption 4 (warm, personal)
    "warm_personal": {
        "en": [
            "The chai moment is the whole story. Twenty extra minutes well spent.",
            "That's the kind of frame you carry with you. Beautiful.",
            "Small moments, biggest impact. This is it.",
        ],
        "ja": ["紅茶のあの瞬間が全てですね。20分延びて正解。", "こんなショットは一生持ち歩けます。"],
        "ko": ["차 한 잔의 그 순간이 전부예요. 20분 더 있어 잘했죠.", "이런 프레임은 오래 갖고 있게 됩니다."],
        "th": ["ชั้ด moment คือ story ท้่อง", "frame น้ีจะติดต้วไปนานมาก"],
    },
    # Matches caption 5 (matter-of-fact, dry)
    "dry_matter": {
        "en": [
            "Battery died at the exact right moment. The constraint did the work.",
            "Two frames is enough when the light is right.",
            "Sometimes less battery means better image. Proven.",
        ],
        "ja": ["バッテリー切れのタイミングは絶妙ですね。", "2枚で十分。光が良ければ。"],
        "ko": ["배터리가 떨어진 타이밍이 딱이었네요.", "2프레임이면 충분합니다."],
        "ar": ["انتهاء البطارية في الوقت المناسب تماماً.", "إطاران يكفيان عندما تكون الإضاءة جيدة."],
    },
    # Matches caption 6 (sensory, present-tense)
    "sensory_present": {
        "en": [
            "The bell-to-architecture merge is beautifully captured.",
            "You can almost hear the city holding its breath.",
            "That exact second is a masterclass in audio-visual sync.",
        ],
        "ja": ["鐘と建築の融合が美しく捉えられています。", "街が息を吸い込む音が聞こえそうです。"],
        "ko": ["종소리과 건축의 융화가 아름답게 담겼어요.", "도시가 숨을 참는 소리가 거의 들려요."],
        "th": ["เสียงระหงกับสถาปัตยกรรมผสานกันสวยมาก", "ฟังเหมือนเมืองกำลังกลั้นหายใจ"],
    },
}

DEFAULT_BANK = BANKS["doc_restrained"]

# Assign banks to posts by index
BANK_BY_IDX = {
    0: "doc_restrained", 1: "casual_playful", 2: "poetic_minimal",
    3: "analytical", 4: "warm_personal", 5: "dry_matter", 6: "sensory_present",
}


def _load_excluded_emails() -> set:
    excluded = set()
    if TOKENS.exists():
        try:
            excluded.update(json.loads(TOKENS.read_text(encoding="utf-8")).keys())
        except Exception:
            pass
    for d in ROOT.glob("*_run"):
        for f in d.glob("accounts_merged_*.csv"):
            try:
                for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                    e = (row.get("邮箱") or row.get("email") or "").strip().lower()
                    if e:
                        excluded.add(e)
            except Exception:
                pass
    return excluded


def _load_publishers() -> set:
    """Return email addresses of accounts that published the video posts."""
    publishers = set()
    run_dir = sorted(ROOT.glob("pexels_indian_travel_7_run"))
    if run_dir:
        for f in run_dir[-1].glob("accounts_*.csv"):
            try:
                for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                    e = (row.get("邮箱") or row.get("email") or "").strip().lower()
                    if e:
                        publishers.add(e)
            except Exception:
                pass
    return publishers


def load_en_nick_commenters(n: int) -> list:
    """
    Pick EN-nick accounts with valid tokens, excluding only the 7 publishers.
    This allows re-using accounts that already have tokens (no re-login needed).
    """
    tokened = set(json.loads(TOKENS.read_text(encoding="utf-8")).keys())
    publishers = _load_publishers()
    available = tokened - publishers
    picked = []
    seen = set()
    for csv_path in [PHOTOGRAPHER_CSV, POOL_850_CSV]:
        if len(picked) >= n:
            break
        if not csv_path.exists():
            continue
        for r in csv.DictReader(open(csv_path, encoding="utf-8-sig")):
            if len(picked) >= n:
                break
            email = (r.get("邮箱") or r.get("email") or "").strip()
            nick = (r.get("昵称") or "").strip()
            password = (r.get("密码") or "").strip()
            seq = (r.get("序号") or "").strip()
            if not email or not password:
                continue
            if email.lower() not in available:
                continue
            if email.lower() in seen:
                continue
            if not EN_NICK_RE.match(nick):
                continue
            seen.add(email.lower())
            picked.append({"email": email, "password": password,
                           "nickname": nick, "seq": seq})
    return picked


def _collect_posts(report: Path) -> list:
    posts = []
    for r in csv.DictReader(report.open(encoding="utf-8-sig")):
        pid = (r.get("moment_id_or_err") or "").strip()
        source = (r.get("_source") or "").strip()
        if pid.isdigit() and "True" in str(r.get("success", "")) and "pexels_indian" in source:
            posts.append({"post_id": int(pid),
                         "email": (r.get("email") or "").strip()})
    return posts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="")
    ap.add_argument("--post-ids", default="", help="Comma-separated moment IDs")
    ap.add_argument("--min-comments", type=int, default=1)
    ap.add_argument("--max-comments", type=int, default=3)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.post_ids:
        pids = [int(x.strip()) for x in args.post_ids.split(",") if x.strip()]
        posts = [{"post_id": pid, "email": ""} for pid in pids]
    elif args.report:
        report = ROOT / args.report
        posts = _collect_posts(report)
    else:
        # Read from the run dir's published list
        posts = []
        run_dir = sorted(ROOT.glob("pexels_indian_travel_7_run"))
        if run_dir:
            pub_file = run_dir[-1] / "published.json"
            if pub_file.exists():
                import json
                for item in json.loads(pub_file.read_text(encoding="utf-8")):
                    posts.append({"post_id": int(item.get("moment_id", 0)),
                                  "email": item.get("email", "")})
        if not posts:
            print("[ERROR] No pexels_indian posts found", file=sys.stderr)
            return 1

    if not posts:
        print("[ERROR] No pexels_indian posts found", file=sys.stderr)
        return 1
    print(f"[posts] {len(posts)} video posts")

    n_needed = len(posts) * args.max_comments
    commenters = load_en_nick_commenters(n_needed)
    if not commenters:
        print("[ERROR] No fresh EN-nick commenters", file=sys.stderr)
        return 1
    print(f"[commenters] {len(commenters)} EN-nick")

    batch = []
    for i, p in enumerate(posts):
        n = random.randint(args.min_comments, args.max_comments)
        bank_key = BANK_BY_IDX.get(i, "doc_restrained")
        bank = BANKS.get(bank_key, DEFAULT_BANK)
        avail_langs = list(bank.keys())
        for _ in range(n):
            lang = random.choice(avail_langs)
            text = random.choice(bank[lang])
            commenter = random.choice(commenters)
            batch.append({
                "email": commenter["email"],
                "post_id": p["post_id"],
                "topic": "travel",
                "text": text,
                "nickname": commenter["nickname"],
            })

    random.shuffle(batch)
    batch_path = ROOT / "temp_comments_pexels_indian_7_batch.csv"
    with batch_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["email","post_id","topic","text","nickname"])
        w.writeheader()
        for row in batch:
            w.writerow(row)

    per_post = Counter(r["post_id"] for r in batch)
    print(f"\n[batch] {len(batch)} comments across {len(posts)} posts "
          f"(range {min(per_post.values())}-{max(per_post.values())})")

    if args.dry_run:
        print("[dry-run] Stopping")
        return 0

    if not args.yes:
        if input("Confirm? (y/n): ").strip().lower() not in ("y","yes"):
            print("Cancelled.")
            return 0

    accounts_csv = ROOT / "accounts_pexels_indian_7_commenters.csv"
    with accounts_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号","昵称","邮箱","密码"])
        w.writeheader()
        for i, c in enumerate(commenters):
            w.writerow({"序号": i+1, "昵称": c["nickname"],
                        "邮箱": c["email"], "密码": c["password"]})

    cmd = PY + [str(POST_COMMENTS),
                "--batch", str(batch_path),
                "--tokens", str(TOKENS),
                "--accounts", str(accounts_csv),
                "--delay", str(args.delay)]
    print(f"\n[exec] {' '.join(str(c) for c in cmd)}")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    return rc


if __name__ == "__main__":
    sys.exit(main())
