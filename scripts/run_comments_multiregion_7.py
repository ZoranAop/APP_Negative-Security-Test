#!/usr/bin/env python3
"""
run_comments_multiregion_7.py — Add 2–10 random-language comments to each of
the 7 posts published by run_regional_news_multiregion_7.py.
Commenter accounts: English-nickname-only, from 互动用户池_670账号.xlsx,
separate from publisher accounts (excluded via tokens.json + run dir CSVs).
Comment language: random mix — en, zh_hant, th, ms, hi, ja, ko, id, vi, ar.
"""
from __future__ import annotations

import argparse, csv, json, random, re, subprocess, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"
POOL_850_CSV = ROOT / "pre_企管用户_850.csv"
TOKENS = ROOT / "result" / "tokens.json"
POST_COMMENTS = HERE / "post_comments.py"
BATCH_OUT = ROOT / "temp_comments_regional_multiregion_7_batch.csv"
PUBLISH_REPORT_GLOB = "result/publish_*.csv"

# Per-topic concise comment banks (random language, random selection)
BANKS = {
    "tech_ai": {
        "en": [
            "The compliance angle is where things get interesting.",
            "Model pipeline restructures are already showing up in job postings.",
            "Inference cost reduction is the real unlock here.",
            "This gap between innovation speed and regulation won't close soon.",
        ],
        "zh_hant": [
            "合規成本會影響到部署節奏。",
            "open source inference 的成本結構確實在改善。",
            "regulation 與 innovation 的落差會持續。",
        ],
        "ja": ["コンプライアンスが部署スピードに影響します。", "インフェレンスコストが鍵ですね。"],
        "ko": ["컴플라이언스가 배포 속도에 영향을 줍니다.", "인퍼런스 비용이 핵심 포인트입니다."],
        "th": ["ด้าน compliance มีผลต่อจังหวะ deploy.", "ต้นทุน inference กำลังลดลงจริง ๆ."],
        "ms": ["Aspek compliance memang paling relevan.", "Kurangan kos inference pun jadi unlock utama."],
        "id": ["Sisi compliance paling berdampak di sini.", "Biaya inferensi memang sedang turun signifikan."],
        "hi": ["compliance का असर deployment speed पर दिख रहा है।", "inference cost की गिरावट असली unlock है।"],
        "ar": ["جانب الامتثال هو الأهم هنا.", "تكلفة الاستدلال تنخفض بشكل حقيقي."],
        "vi": ["Yếu tố compliance ảnh hưởng lớn tới nhịp deploy.", "Chi phí inference đang giảm thực sự."],
    },
    "web3": {
        "en": [
            "Licensing clarity is the whole story here.",
            "Regulatory framework really did just land.",
            "The hub potential is real if execution follows.",
            "Watching this closely — next quarter will be the test.",
        ],
        "zh_hant": [
            "監管框架真的落地了。",
            "hub 的潛力要看執行。",
            "下季會是真正的考驗。",
        ],
        "ja": ["規制フレームワークが現実になった。", "hub の可能性は実行次第。"],
        "ko": ["규제 프레임워크가 실제로落地되었습니다.", "hub 가능성은 실행에 달렸습니다."],
        "th": ["กรอบ regulatsion จริง ๆ ลงที่แล้ว.", "ศักยภาพ hub ขึ้นอยู่กับการ execute."],
        "ms": ["Framework regulation memang betul-betul dah landa.", "Potensi hub bergantung pada eksekusi."],
        "id": ["Kerangka regulasi benar-benar sudah berlaku.", "Potensi hub-nya tergantung eksekusi."],
        "hi": ["नियमन framework सच में लागू हो गया है।", "hub की possibility execution पर निर्भर है।"],
        "ar": ["إطار الضوابط أصبح واقعاً فعلاً.", "إمكانية المركز تعتمد على التنفيذ."],
        "vi": ["Khung quản lý đã thực sự có hiệu lực.", "Tiềm năng hub phụ thuộc vào cách thực thi."],
    },
    "national_policy": {
        "en": [
            "The 40% tax incentive is a serious signal.",
            "Hyperscaler site surveys are the tell — they don't waste time.",
            "If this plays out, the region's compute story changes completely.",
            "Policy-first approach is doing the heavy lifting here.",
        ],
        "zh_hant": [
            "40% 的稅務激勵是很強的訊號。",
            "hyperscaler 的 survey 不會白做。",
            "這區域的 compute 格局會因此改變。",
        ],
        "ja": ["40%の税優遇は強いシグナルです。", "hyperscalerのsite調査が本気度を示している。"],
        "ko": ["40% 세액 인센티브가 강력한 신호입니다.", "hyperscaler의 현장 조사가 진정성을 보여줍니다."],
        "th": ["มาตรการลดหย่อน 40% เป็นสัญญาณที่ชัดเจนมาก.", "การสำรวจ hyperscaler บอกว่าจริงจังจริง ๆ."],
        "ms": ["Insentif 40% memang signal yang sangat serius.", "Site survey hyperscaler menunjukkan komitmen sebenar."],
        "id": ["Insentif 40% adalah sinyal yang sangat serius.", "Site survey hyperscaler menunjukkan komitmen nyata."],
        "hi": ["40% की rebate एक powerful signal है।", "hyperscaler की survey commitment दिखाती है।"],
        "ar": ["حوافز 40% إشارة جدية جداً.", "مسوح hyperscaler تدل على جديّة كبيرة."],
        "vi": ["Ưu đãi 40% là tín hiệu rất mạnh.", "Khảo sát hyperscaler cho thấy cam kết thực sự."],
    },
    "coin": {
        "en": [
            "Phase 2 stablecoin pilot is the event to watch.",
            "Tokenised treasury market will define the next cycle.",
            "Regulatory clarity is the real moat — not the exchanges.",
            "Institutional flows are coming and they need clarity first.",
        ],
        "zh_hant": [
            "stablecoin pilot Phase 2 是重點。",
            "tokenised treasury 市場會定義下一輪週期。",
            "監管清晰度才是真正的護城河。",
        ],
        "ja": ["stablecoin pilot Phase 2 が注目イベント。", "トークン化短期債市場が次のサイクルを定義する。"],
        "ko": ["stablecoin pilot Phase 2가 핵심 이벤트입니다.", "토큰화 국채 시장이 다음 사이클을 결정합니다."],
        "th": ["stablecoin pilot Phase 2 คือสิ่งต้องจับตา.", "ตลาด tokenised Treasury จะกำหนดรอบถัดไป."],
        "ms": ["Pilot stablecoin Phase 2 memang fokus utama.", "Pasar tokenised Treasury akan tentukan kitaran seterusnya."],
        "id": ["Pilot stablecoin Phase 2 memang yang paling ditunggu.", "Pasar treasury ter-tokenisasi akan menentukan siklus berikutnya."],
        "hi": ["stablecoin pilot Phase 2 ही बड़ा event है।", "tokenised treasury market अगले cycle को define करेगा।"],
        "ar": ["Pilot stablecoin Phase 2 هو الحدث الأهم.", "سوق الخزينة المُرمّزة سيعرّف الدورة القادمة."],
        "vi": ["Pilot stablecoin Phase 2 mới là sự kiện đáng theo dõi.", "Thị trường treasury tokenised sẽ định hình chu kỳ tiếp theo."],
    },
    "entertainment": {
        "zh_hant": [
            "台劇口碑確實走高，AI 主題處理得很成熟。",
            "跨區域內容流通速度比過去快很多。",
            "兩支獨立電子樂團被推薦是很好的事。",
        ],
        "en": [
            "The AI themes were handled way more seriously than expected.",
            "Cross-region content circulation is accelerating.",
            "The indie electronica scene is quietly breaking through.",
        ],
        "ja": ["台ドラマのAIテーマの扱いが意外に成熟していた。", "クロスリージョナルのコンテンツ流通が加速中。"],
        "ko": ["대만 드라마의 AI 테마가 생각보다 성숙하게 다뤄졌어요.", "크로스리전널 콘텐츠 순환이 빨라지고 있습니다."],
        "th": ["ซีรีส์ไต้หวันเรื่อง AI ถูกทำมา出乎意料ที่โตมาก.", "กระแสครอสรีเจียนเร็วขึ้นจริง ๆ."],
        "ms": ["Kualiti drama Taiwan bahagian AI memang lebih matang dari jangkaan.", "Aliran kandungan serantau makin laju."],
        "id": ["Drama Taiwan bagian AI ternyata lebih matang dari ekspektasi.", "Sirkulasi konten cross-region memang makin cepat."],
        "hi": ["Taiwan drama का AI theme expected से बेहतर handle किया गया।", "cross-region content circulation तेज़ हो रही है।"],
        "ar": ["معالجة موضوع AI في الدراما التايوانية أعمق من المتوقع.", "توزيع المحتوى بين المناطق يسارع."],
        "vi": ["Xử lý chủ đề AI của drama Taiwan vượt mong đợi.", "Lộ trình nội dung cross-region đang tăng tốc."],
    },
}

# Default bank used when topic not in BANKS
DEFAULT_BANK = BANKS["tech_ai"]

EN_NICK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-\ ]*$")


def _load_excluded_emails() -> set:
    """All emails in tokens.json + all prior accounts_merged CSVs."""
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
    """Pick n fresh EN-nick accounts from photographer + 850 CSV pools."""
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


def _pick_report_file() -> Path:
    """Find the latest publish_*.csv report (must match our 7 post keys)."""
    reports = sorted(ROOT.glob("result/publish_*.csv"), key=lambda p: p.stat().st_mtime)
    if not reports:
        print("[ERROR] No publish_*.csv found in result/", file=sys.stderr)
        sys.exit(1)
    return reports[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-comments", type=int, default=2)
    ap.add_argument("--max-comments", type=int, default=10)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--report", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    report_path = ROOT / args.report if args.report else _pick_report_file()
    if not report_path.exists():
        print(f"[ERROR] Report not found: {report_path}", file=sys.stderr)
        return 1
    print(f"[report] {report_path}")

    report_rows = list(csv.DictReader(report_path.open(encoding="utf-8-sig")))
    posts, publishers = [], set()
    for r in report_rows:
        pid = (r.get("moment_id_or_err") or "").strip()
        email = (r.get("email") or "").strip().lower()
        topic = (r.get("_topic") or "general").strip()
        source = (r.get("_source") or "").strip()
        if pid.isdigit() and "True" in str(r.get("success", "")) and "regional_news" in source:
            posts.append({"post_id": int(pid), "topic": topic, "email": email})
            if email:
                publishers.add(email)

    if not posts:
        print("[ERROR] No successful regional_news posts found in report", file=sys.stderr)
        return 1
    print(f"[posts] {len(posts)} posts: {[(p['post_id'], p['topic']) for p in posts]}")

    # Commenter accounts: EN-nick, separate from publishers (excluded via tokens + run dirs)
    excluded = _load_excluded_emails()
    print(f"[commenters] excluded={len(excluded)} (tokens + prior runs)")
    n_commenters = len(posts) * args.max_comments
    commenters = load_en_nick_accounts(n_commenters, excluded)
    if not commenters:
        print("[ERROR] No fresh EN-nick commenter accounts found", file=sys.stderr)
        return 1
    print(f"[commenters] {len(commenters)} EN-nick accounts: "
          f"{[c['nickname'] for c in commenters[:10]]}...")

    # Build batch
    batch = []
    for p in posts:
        n = random.randint(args.min_comments, args.max_comments)
        bank = BANKS.get(p["topic"], DEFAULT_BANK)
        langs = list(bank.keys())
        for _ in range(n):
            lang = random.choice(langs)
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
    BATCH_OUT.parent.mkdir(parents=True, exist_ok=True)
    with BATCH_OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["email", "post_id", "topic", "text", "nickname"])
        w.writeheader()
        for row in batch:
            w.writerow(row)

    per_post = Counter(r["post_id"] for r in batch)
    lang_cnt = Counter()
    for r in batch:
        for lang in BANKS.get(r["topic"], DEFAULT_BANK).keys():
            if lang in r["text"]:
                lang_cnt[lang] += 1
                break
    print(f"\n[batch] {len(batch)} comments across {len(posts)} posts")
    print(f"  per-post: {dict(per_post)}")

    if args.dry_run:
        print("\n[dry-run] Stopping before posting comments")
        return 0

    if not args.yes:
        if input("\nConfirm post comments? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    # Write commenter accounts CSV for post_comments.py
    accounts_csv = ROOT / "accounts_regional_multiregion_7_commenters.csv"
    with accounts_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
        w.writeheader()
        for i, c in enumerate(commenters):
            w.writerow({"序号": i + 1, "昵称": c["nickname"],
                        "邮箱": c["email"], "密码": c["password"]})

    cmd = PY + [str(POST_COMMENTS),
                "--batch", str(BATCH_OUT),
                "--tokens", str(TOKENS),
                "--accounts", str(accounts_csv),
                "--delay", str(args.delay)]
    print(f"\n[exec] {' '.join(str(c) for c in cmd)}")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    return rc


if __name__ == "__main__":
    sys.exit(main())
