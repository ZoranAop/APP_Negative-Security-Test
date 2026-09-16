#!/usr/bin/env python3
"""
run_comments_multi_reg_12.py — 1–2 random-language comments per post
for the multi_reg_en_12 posts. EN-nick commenter pool.
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

# Random language comment banks per topic
BANKS = {
    "web3": {
        "en": ["The regulatory timing is what matters here.", "Institutional flow is the real signal, not retail.", "This framework will either unlock it or just add friction — we'll see."],
        "ja": ["規制のタイミングがカギですね。", "機関のフローが本命です。"],
        "ko": ["규제 타이밍이 핵심입니다.", "기관 자금 흐름이 진짜 지표입니다."],
        "ar": ["توقيت التنظيم هو المفتاح.", "تيار المؤسسات هو الإشارة الحقيقية."],
        "th": ["timing ของ regulation คือคักครับ/ค่ะ", "inst flow เป็ินสัญญาณที่แท้จริง"],
    },
    "ai": {
        "en": ["The 5% gap compression is the story most people miss.", "Regulatory engineering incentive is real.", "Benchmark gap going to close faster than expected."],
        "ja": ["5%のギャップ圧縮が本当の話。", "規制がエンジニアリングのインセンティブを生んでる。"],
        "ko": ["5% gap 압축이 진짜 핵심.", "규제 엔지니어링 인센티브가 실재합니다."],
        "ar": ["ضغط الفجوة 5% هو القصة الحقيقية.", "التنظيم يخلق حافز هندسي حقيقي."],
        "th": ["gap 5% น้อยลงคี่น story ท่แท้จริง", "regulation ทำให้คนคิด innovation จิ่่ง"],
    },
    "finance": {
        "en": ["BNM moved right when the market needed it.", "Liquidity framework is the quiet hero here.", "That's what calm policy looks like."],
        "ja": ["BNMのタイミングが完璧でした。", "liquidity frameworkが本当のhero。"],
        "ko": ["BNM 타이밍이 정확했습니다.", "liquidity framework가 진짜 주인공입니다."],
        "ar": ["توقيت BNM كان مثالياً.", "إطار السيولة هو البطل الحقيقي."],
        "th": ["BNM ทำถูกจังหวะแล่ว", "liquidity framework เปี่น hero ท่แท้"],
    },
    "economics": {
        "en": ["Four months of contraction is telling.", "Energy cost gap is the structural story.", "The relocation narrative is running out of steam."],
        "ja": ["4ヶ月のshrinkingはメッセージです。", "エネルギーコストの差が構造のstory。"],
        "ko": ["4개월 연속 위축이 말해줍니다.", "에너지 비용 차이가 구조적 스토리입니다."],
        "ar": ["أربعة شهور من الانكماش تقول الكثير.", "فجوة تكاليف الطاقة هي القصة الهيكلية."],
        "th": ["4 เด่นหดตัวบอกอะไรมาก", "cost gap พลังงานเปี่น story ชุ้่น"],
    },
    "policy": {
        "en": ["Give the sandbox two years — it'll work.", "Patient policy-making is rare and valuable.", "The FCA is playing the long game."],
        "ja": ["もう2年待てば届きます。", "忍耐強いpolicyは貴重です。"],
        "ko": ["두 해만 더 지켜봅시다.", "내성 있는 정책이 드문 겁니다."],
        "ar": ["امنح الصندوق سنتين.", "صبر السياسة نادر ثمّن."],
        "th": ["อีก2ปีถึงเห็นผล", "policy อย่า่ rush ดีท่สุด"],
    },
    "military": {
        "en": ["Shared warning network is the real threshold.", "Institutional commitment beats hardware.", "Regional calculus just shifted."],
        "ja": ["共有警報ネットワークが本当の分岐点。", "制度的コミットメントがハードより大事。"],
        "ko": ["공유 경보 네트워크가 진짜 분기점.", "제도적 커밋먼트가 하드웨어보다 중요합니다."],
        "ar": ["شبكة الإنذار المشتركة هي العتبة الحقيقية.", "التزام مؤسساتي أهم من العتاد."],
        "th": ["network ระวังท่ร่วมใช้เปี่น threshold ท่แท้", "institute commitment สำคัญกว่า hardware"],
    },
    "oil": {
        "en": ["Contango after 8 weeks is structural.", "Watch the forward curve, not spot.", "Cushing build plus OPEC discipline = squeeze."],
        "ja": ["8週間ぶりのcontangoは構造的。", "forward curveこそ見るべき。"],
        "ko": ["8주 만의 contango가 구조적 전환.", "forward curve를 봐야 합니다."],
        "ar": ["contango بعد ثمانية أسابيع هيكلي.", "راقب المنحنى الأمامي لا السعر الفوري."],
        "th": ["contango 8 เด่นเปี่น structural", "ดู forward curve จ่า spot"],
    },
    "social": {
        "en": ["500K enrollees in Q1 — that's a real signal.", "The hiring pipeline is the next question.", "Nomad communities are now population segments."],
        "ja": ["50万人でQ1は本物のシグナル。", "採用パイプラインが次の問。"],
        "ko": ["50만 명이 Q1 — 진짜 시그널입니다.", "채용 파이프라인이 다음 과제."],
        "ar": ["500 ألف مسجل في Q1 إشارة حقيقية.", "خط التوظيف هو السؤال التالي."],
        "th": ["500K Q1 เปี่น signal ท่แท้", "hiring pipeline คือคำถามถัดไป"],
    },
    "public_policy": {
        "en": ["7.2% transfer increase is a real uplift.", "Rural recovery is no longer anecotal.", "Two consecutive quarters of data saying the same thing."],
        "ja": ["7.2%の増額は本当の上昇。", "rural recoveryはもうanecdoteじゃない。"],
        "ko": ["7.2% 인상은 진짜 상승입니다.", "rural recovery가 이제 우발적이지 않습니다."],
        "ar": ["زيادة 7.2% حقيقية.", "تعافي الريف لم يعد مجرد قصة."],
        "th": ["7.2% เพิ่่มขึ้นเปี่น signal ท่แท้", "rural recovery ท่ม่เปี่น anecdote แล่ว"],
    },
}

DEFAULT_BANK = BANKS["web3"]
LANG_POOL = ["en", "ja", "ko", "ar", "th"]


def _roll_lang() -> str:
    return random.choice(LANG_POOL)


def _load_excluded_emails() -> set:
    excluded = set()
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


def load_en_nick_accounts(n: int, excluded: set) -> list:
    picked = []
    seen = set(excluded)
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
            if not email or not password or email.lower() in seen:
                continue
            if not EN_NICK_RE.match(nick):
                continue
            seen.add(email.lower())
            picked.append({"email": email, "password": password,
                           "nickname": nick, "seq": seq})
    return picked


def _collect_posts(report: Path, marker: str) -> list:
    posts = []
    for r in csv.DictReader(report.open(encoding="utf-8-sig")):
        pid = (r.get("moment_id_or_err") or "").strip()
        source = (r.get("_source") or "").strip()
        topic = (r.get("_topic") or "general").strip()
        if pid.isdigit() and "True" in str(r.get("success","")) and marker in source:
            posts.append({"post_id": int(pid), "topic": topic,
                         "email": (r.get("email") or "").strip()})
    return posts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="", help="publish_*.csv for multi_reg_en_12")
    ap.add_argument("--min-comments", type=int, default=1)
    ap.add_argument("--max-comments", type=int, default=2)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.report:
        report = ROOT / args.report
    else:
        reports = sorted(ROOT.glob("result/publish_*.csv"), key=lambda p: p.stat().st_mtime)
        if not reports:
            print("[ERROR] No publish_*.csv found", file=sys.stderr)
            return 1
        report = reports[-1]

    posts = _collect_posts(report, "multi_reg")
    if not posts:
        print("[ERROR] No multi_reg posts found in report", file=sys.stderr)
        return 1
    print(f"[posts] {len(posts)} posts found")

    excluded = _load_excluded_emails()
    n_needed = len(posts) * args.max_comments
    commenters = load_en_nick_accounts(n_needed, excluded)
    if not commenters:
        print("[ERROR] No fresh EN-nick commenters", file=sys.stderr)
        return 1
    print(f"[commenters] {len(commenters)} EN-nick: "
          f"{[c['nickname'] for c in commenters[:10]]}...")

    batch = []
    for p in posts:
        n = random.randint(args.min_comments, args.max_comments)
        bank = BANKS.get(p["topic"], DEFAULT_BANK)
        avail_langs = [l for l in LANG_POOL if l in bank] or ["en"]
        for _ in range(n):
            lang = random.choice(avail_langs)
            text = random.choice(bank[lang])
            commenter = random.choice(commenters)
            batch.append({
                "email": commenter["email"],
                "post_id": p["post_id"],
                "topic": p["topic"],
                "text": text,
                "nickname": commenter["nickname"],
            })

    random.shuffle(batch)
    batch_path = ROOT / "temp_comments_multi_reg_12_batch.csv"
    with batch_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["email","post_id","topic","text","nickname"])
        w.writeheader()
        for row in batch:
            w.writerow(row)

    per_post = Counter(r["post_id"] for r in batch)
    print(f"\n[batch] {len(batch)} comments across {len(posts)} posts "
          f"(range: {min(per_post.values())}-{max(per_post.values())})")

    if args.dry_run:
        print("[dry-run] Stopping")
        return 0

    if not args.yes:
        if input("Confirm? (y/n): ").strip().lower() not in ("y","yes"):
            print("Cancelled.")
            return 0

    accounts_csv = ROOT / "accounts_multi_reg_12_commenters.csv"
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
