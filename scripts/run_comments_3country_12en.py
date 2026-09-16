#!/usr/bin/env python3
"""
run_comments_3country_12en.py — Add 2–10 comments to both batches:
  1. econ_policy_3country_20 posts (India / Bangladesh / Malaysia)
  2. mideast_12_en posts (Middle East, EN)
Commenter accounts: EN-nick, separate from all publishers (excluded).
Comment language: random mix — en, hi, bn, ms, ja, ko, ar, th.
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

# Per-topic concise comment banks
BANKS = {
    "economic": {
        "en": [
            "GDP number is above forecast — that's the headline.",
            "Watch the PMI data next quarter; that's the real signal.",
            "Supply chain is still the bottleneck, not demand.",
            "This cycle is more durable than last time.",
        ],
        "hi": [
            "यह growth rate forecast से ऊपर है।",
            "supply chain अभी भी bottleneck है।",
            "इस cycle में durability ज़्यादा है।",
        ],
        "bn": [
            "GDP growth forecast-এর উপরে আছে।",
            "supply chain এখনো bottleneck।",
            "এই cycle-এ durability বেশি।",
        ],
        "ms": [
            "GDP figure dah lebih kuat dari jangkaan.",
            "Supply chain masih bottleneck, bukan demand.",
            "Kitaran ini lebih bertahan berbanding sebelum.",
        ],
        "ja": ["growth rateは予想を上回っています。", "supply chainがボトルネックです。"],
        "ko": ["GDP 수치가 예상보다 좋습니다.", "supply chain이 여전히 병목입니다."],
        "ar": ["نمو الناتج أعلى من التوقعات.", "سلسلة الإمداد لا تزال عائقاً."],
        "th": ["GDP สูงกว่า forecast.", "supply chain ยังเป็น bottleneck."],
    },
    "policy": {
        "en": [
            "Regulatory clarity is the unlock here.",
            "Compliance cost is going down with the new framework.",
            "This is where the next wave of FDI lands.",
            "The implementation is what matters now.",
        ],
        "hi": [
            "regulatory clarity ही unlock है।",
            "naya framework compliance cost घटाएगा।",
            "implementation ही असली test है।",
        ],
        "bn": [
            "regulatory clarity unlock।",
            "নতুন framework compliance cost কমাবে।",
            "implementation-ই আসল test।",
        ],
        "ms": [
            "Kejelasan regulasi adalah kunci dia.",
            "Cost compliance akan turun dengan framework baru.",
            "Implementation barang yang paling penting sekarang.",
        ],
        "ja": ["regulatory clarityが鍵ですね。", "新フレームワークでcompliance costが下がる見込み。"],
        "ko": ["규제 명확성이 핵심입니다.", "신규 프레임워크가 compliance 비용을 낮추겠습니다."],
        "ar": ["وضوح الضوابط هو المفتاح.", "البنية الجديدة ستنزل كلفة الامتثال."],
        "th": ["ความชัดเจนของ regulatory เป็น unlock.", "framework ใหม่ทำให้ cost compliance น้อยลง."],
    },
    "public_policy": {
        "en": [
            "The last-mile delivery is where it gets hard.",
            "This is a real structural improvement, not just a headline.",
            "Watch the fiscal impact — that's the real question.",
            "The rollout speed is the key metric.",
        ],
        "hi": [
            "last-mile delivery ही असली test है।",
            "यह real structural improvement है।",
            "fiscal impact ही असली सवाल है।",
        ],
        "bn": [
            "last-mile delivery-ই আসল test।",
            "এটা real structural improvement।",
            "fiscal impact-ই আসল প্রশ্ন।",
        ],
        "ms": [
            "Last-mile delivery memang paling susah.",
            "Ini improvement struktural sebenar, bukan headline saja.",
            "Impact fiskal baru yang paling penting dipantau.",
        ],
        "ja": ["last-mile deliveryが試金石です。", "これは構造的な改善。"],
        "ko": ["last-mile delivery가 진짜 시험대입니다.", "구조적 개선이지 헤드라인이 아닙니다."],
        "ar": ["التسليم الأخير هو الاختبار الحقيقي.", "هذا تحسين بنيوي حقيقي."],
        "th": ["last-mile delivery คือ test ท่รียง.", "น้ีเป็น structural improvement จริง ๆ."],
    },
    "military": {
        "en": [
            "The layered defense shift is the real story here.",
            "Cost per interception is dropping fast — that changes everything.",
            "Joint exercises are where real coordination gets tested.",
            "The doctrine shift is more significant than the hardware.",
        ],
        "ja": ["多層防御のシフトが本当の話ですね。", "interceptコストの低下がすべてを変える。"],
        "ko": ["층별 방어 전환이 핵심입니다.", "intercept 비용 급감이 전부를 바꿉니다."],
        "ar": ["تحويل الدفاع متعدد الطبقات هو القصة الحقيقية.", "انخفاض تكلفة الاعتراض يغيّر كل شيء."],
        "th": ["การเปลี่ยน layered defense คือเรื่องราวจริง ๆ.", "cost ต่อมื interception ต่ำลงเร็วมาก."],
    },
    "oil": {
        "en": [
            "The forward curve inversion is the metric to watch.",
            "Demand-side weakness is starting to show in the data.",
            "Shadow fleet exports are the hidden variable here.",
            "The dividend was a distraction — the demand plateau is the story.",
        ],
        "ja": ["forward curveのinversionが注目指標。", "需要側の弱さがデータに出始めています。"],
        "ko": ["forward curve 역전이 핵심 지표입니다.", "수요 측 약세가 데이터에서 보이기 시작합니다."],
        "ar": ["منحنى العرض العكسي هو المؤشر الأهم.", "ضعف جانب الطلب بدأ يظهر في البيانات."],
        "th": ["forward curve inversion คือ metrics ท่รีนใจ.", "demand-side weakness เริ่่มเห็นในข้อมูลแล้ว."],
    },
    "social": {
        "en": [
            "Tourism numbers are the real competitive signal here.",
            "Talent pipeline is the bottleneck, not demand.",
            "The cultural shift is real but uneven.",
            "Healthcare access is a quiet but powerful competitiveness lever.",
        ],
        "ja": ["観光統計が本当の競争シグナルです。", "talent pipelineがボトルネックです。"],
        "ko": ["관광 데이터가 진짜 경쟁 신호입니다.", "talent pipeline이 병목입니다."],
        "ar": ["أرقام السياحة هي إشارة المنافسة الحقيقية.", "تalisent pipeline هو العائق."],
        "th": ["ตัวเลขท่องเที่ยวเป็น signal ของการแข่งขันจริง ๆ.", "talent pipeline คือ bottleneck."],
    },
}

DEFAULT_BANK = BANKS["economic"]

# Language roll weights
LANG_WEIGHTS = [
    ("en", 0.35), ("hi", 0.10), ("bn", 0.10),
    ("ms", 0.10), ("ja", 0.08), ("ko", 0.08),
    ("ar", 0.08), ("th", 0.11),
]


def _roll_lang() -> str:
    r = random.random()
    acc = 0.0
    for lang, w in LANG_WEIGHTS:
        acc += w
        if r < acc:
            return lang
    return "en"


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


def _collect_posts_from_report(report: Path, source_marker: str) -> list:
    posts = []
    for r in csv.DictReader(report.open(encoding="utf-8-sig")):
        pid = (r.get("moment_id_or_err") or "").strip()
        source = (r.get("_source") or "").strip()
        topic = (r.get("_topic") or "general").strip()
        if pid.isdigit() and "True" in str(r.get("success", "")) and source_marker in source:
            posts.append({"post_id": int(pid), "topic": topic,
                         "email": (r.get("email") or "").strip()})
    return posts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--econ-report", default="", help="publish_*.csv for econ_policy batch")
    ap.add_argument("--mideast-report", default="", help="publish_*.csv for mideast batch")
    ap.add_argument("--min-comments", type=int, default=2)
    ap.add_argument("--max-comments", type=int, default=10)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    # Find latest reports if not specified
    if not args.econ_report:
        econ_reports = sorted(ROOT.glob("result/publish_*.csv"), key=lambda p: p.stat().st_mtime)
        args.econ_report = str(econ_reports[-1]) if econ_reports else ""
    if not args.mideast_report:
        me_reports = sorted(ROOT.glob("result/publish_*.csv"), key=lambda p: p.stat().st_mtime)
        args.mideast_report = str(me_reports[-1]) if me_reports else ""

    econ_report = ROOT / args.econ_report
    me_report = ROOT / args.mideast_report

    econ_posts = _collect_posts_from_report(econ_report, "econ_policy")
    me_posts = _collect_posts_from_report(me_report, "mideast")
    all_posts = econ_posts + me_posts

    if not all_posts:
        print("[ERROR] No posts found in either report", file=sys.stderr)
        return 1
    print(f"[posts] econ={len(econ_posts)} mideast={len(me_posts)} total={len(all_posts)}")

    excluded = _load_excluded_emails()
    print(f"[commenters] excluded={len(excluded)}")
    n_commenters = len(all_posts) * args.max_comments
    commenters = load_en_nick_accounts(n_commenters, excluded)
    if not commenters:
        print("[ERROR] No fresh EN-nick commenter accounts", file=sys.stderr)
        return 1
    print(f"[commenters] {len(commenters)} EN-nick: "
          f"{[c['nickname'] for c in commenters[:10]]}...")

    batch = []
    for p in all_posts:
        n = random.randint(args.min_comments, args.max_comments)
        bank = BANKS.get(p["topic"], DEFAULT_BANK)
        available_langs = [l for l, _ in LANG_WEIGHTS if l in bank]
        for _ in range(n):
            lang = random.choice(available_langs) if available_langs else "en"
            text = random.choice(bank.get(lang, bank["en"]))
            commenter = random.choice(commenters)
            batch.append({
                "email": commenter["email"],
                "post_id": p["post_id"],
                "topic": p["topic"],
                "text": text,
                "nickname": commenter["nickname"],
            })

    random.shuffle(batch)
    batch_path = ROOT / "temp_comments_3country_12en_batch.csv"
    with batch_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["email", "post_id", "topic", "text", "nickname"])
        w.writeheader()
        for row in batch:
            w.writerow(row)

    per_post = Counter(r["post_id"] for r in batch)
    print(f"\n[batch] {len(batch)} comments across {len(all_posts)} posts")
    print(f"  per-post range: {min(per_post.values())}-{max(per_post.values())}")

    if args.dry_run:
        print("\n[dry-run] Stopping")
        return 0

    if not args.yes:
        if input("\nConfirm post comments? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    accounts_csv = ROOT / "accounts_3country_12en_commenters.csv"
    with accounts_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
        w.writeheader()
        for i, c in enumerate(commenters):
            w.writerow({"序号": i + 1, "昵称": c["nickname"],
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
