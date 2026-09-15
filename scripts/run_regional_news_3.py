#!/usr/bin/env python3
"""
run_regional_news_3.py — Batch 3: concise news posts for
  - India (EN, official context)
  - Vietnam (VI)
  - Brazil (PT)
  - Philippines (EN / Filipino mix)
  - Saudi/UAE (AR simplified + EN)
3 posts each = 15 total. Fresh content, no repeat of batch 1/2.
Fresh accounts from 670 pool.

Usage:
  py -3 scripts/run_regional_news_3.py --yes
"""
from __future__ import annotations

import argparse, csv, io, json, subprocess, sys, time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

INTERACT_XLSX = ROOT / "互动用户池_670账号.xlsx"
STATE_DIR = ROOT / "state"
DEDUPE_FILE = STATE_DIR / "seen_regional_news_3.json"
CAPTION_DEDUPE = STATE_DIR / "seen_regional_news_3_captions.json"

# (region, lang, topic, caption)
POSTS = [
    # ── India — English ─────────────────────────────────────────────────────
    (
        "in", "en", "politics",
        "India's budget focus is shifting hard toward capex and rural demand. "
        "That's the thing to watch — if the multiplier holds, the growth story gets much more durable.",
    ),
    (
        "in", "en", "tech",
        "India is becoming a real data-center and AI-training market, not just a user one. "
        "Cheap power, a young engineer base, and hyperscaler money are aligning in the same direction.",
    ),
    (
        "in", "en", "web3",
        "India's crypto tax regime is settling into something workable. "
        "Once the compliance path is clear, the retail and institutional flow has room to grow fast.",
    ),

    # ── Vietnam — Vietnamese ────────────────────────────────────────────────
    (
        "vn", "vi", "politics",
        "Việt Nam đang đặt cược lớn vào tăng trưởng công nghiệp và FDI. "
        "Nếu chuỗi cung ứng dịch chuyển đúng hướng, đó là cơ hội mười năm tới.",
    ),
    (
        "vn", "vi", "tech",
        "Lực lượng kỹ thuật phần mềm của Việt Nam đang lên nhanh. "
        "Nhiều công ty toàn cầu chọn đây làm hub研发, và đó là tín hiệu thực sự quan trọng.",
    ),
    (
        "vn", "vi", "web3",
        "Cộng đồng crypto Việt Nam luôn năng động. Khi khung pháp lý rõ dần, "
        "dòng vốn trong nước sẽ có lối vào chính thống hơn nhiều.",
    ),

    # ── Brazil — Portuguese ────────────────────────────────────────────────
    (
        "br", "pt", "politics",
        "A política industrial brasileira está mudando o ritmo. "
        "Se o investimento público e privado alinharem, o próximo ciclo de crescimento pode ser mais sólido.",
    ),
    (
        "br", "pt", "tech",
        "O Brasil está virando hub de mineração de dados e energia renovável para IA. "
        "Essa combinação é um diferencial que pouca gente no mundo tem.",
    ),
    (
        "br", "pt", "web3",
        "A regulamentação de cripto no Brasil anda mais madura que a maioria dos emergentes. "
        "Quando a clareza vier, o fluxo institucional tem espaço enorme.",
    ),

    # ── Philippines — English ──────────────────────────────────────────────
    (
        "ph", "en", "politics",
        "The Philippines is leaning on BPO and infrastructure to keep growth up. "
        "Remittances stay strong, but the real question is whether it can build its own export engine.",
    ),
    (
        "ph", "en", "tech",
        "PH talent is a serious asset in the global digital economy. "
        "The question is how much of that talent stays vs. keeps leaving for overseas roles.",
    ),
    (
        "ph", "en", "web3",
        "The PH crypto scene is loud and active. With a clearer licensing track, "
        "the institutional entry point would finally be real instead of just retail speculation.",
    ),

    # ── Saudi / UAE — Arabic (simplified) ──────────────────────────────────
    (
        "gulf2", "ar", "politics",
        "منطقة الخليج تركز على تنويع الاقتصاد بعيداً عن النفط. "
        "الآن هو الوقت الذي تُحسم فيه هذه التحولات إما بالسرعة أو بالتباطؤ.",
    ),
    (
        "gulf2", "ar", "tech",
        "الاستثمار في مراكز البيانات والذكاء الاصطناعي يتسارع في المنطقة. "
        "هذا ليس مجرد كلام — هناك تحولات حقيقية على أرض الواقع.",
    ),
    (
        "gulf2", "ar", "web3",
        "دبي وأبوظبي تقودان المنطقة في البنية التحتية للكريبتو. "
        "التراخيص الميسّرة وجاذبية المؤسسات تجعلها الوجهة الأولى للمنطقة.",
    ),
]


def _load_used_emails():
    used = set()
    try:
        used.update(json.loads((ROOT / "result" / "tokens.json").read_text(encoding="utf-8")).keys())
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


def load_accounts(n: int, exclude: set) -> list:
    import openpyxl
    if not INTERACT_XLSX.exists():
        print(f"[ERROR] {INTERACT_XLSX} not found", file=sys.stderr)
        return []
    wb = openpyxl.load_workbook(INTERACT_XLSX, read_only=True)
    ws = wb.active
    raw_rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not raw_rows:
        return []
    headers = [str(h or "") for h in raw_rows[0]]
    picked, seen = [], set(exclude)
    for row in raw_rows[1:]:
        if len(picked) >= n:
            break
        rd = dict(zip(headers, row))
        email = str(rd.get("邮箱", "") or "").strip()
        if not email or email in seen:
            continue
        seen.add(email)
        picked.append({
            "email": email,
            "password": str(rd.get("密码", "") or "").strip(),
            "pincode": str(rd.get("pincode", "") or "").strip(),
            "nickname": str(rd.get("昵称", "") or "").strip(),
            "seq": str(rd.get("序号", "") or "").strip(),
        })
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="regional_news_3_run")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)

    used = _load_used_emails()
    accounts = load_accounts(len(POSTS), used)
    print(f"[accounts] {len(accounts)} fresh from 互动用户池_670:")
    for i, a in enumerate(accounts):
        print(f"  [{i+1}] {a['nickname']} ({a['email']})")

    used_caps = set()
    if CAPTION_DEDUPE.exists():
        try:
            used_caps = set(json.loads(CAPTION_DEDUPE.read_text(encoding="utf-8")))
        except Exception:
            pass

    moments = []
    for i, (region, lang, topic, caption) in enumerate(POSTS):
        if caption in used_caps:
            continue
        used_caps.add(caption)
        moments.append({
            "content": caption, "visibility": "0", "room_id": "",
            "image_urls": "", "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_lang": lang, "_source": f"regional3_{region}_{topic}",
            "_topic": topic, "_dedupe_key": f"r3_{region}_{topic}_{i}",
        })

    moments_csv = wd / f"moments_regional_news_3_{ts}.csv"
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_lang", "_source", "_topic", "_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow(m)

    lang_count = {}
    for m in moments:
        lang_count[m["_lang"]] = lang_count.get(m["_lang"], 0) + 1
    print(f"\n[OK] {len(moments)} posts ready  lang_dist={lang_count}")
    for i, m in enumerate(moments):
        acct = accounts[i] if i < len(accounts) else {"nickname": "?"}
        print(f"  [{i+1}] {acct['nickname']:12} [{m['_source']:22}] | {m['content'][:45]}...")

    if not args.yes:
        if input("\nConfirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    CAPTION_DEDUPE.write_text(json.dumps(sorted(used_caps), ensure_ascii=False), encoding="utf-8")
    old = set()
    if DEDUPE_FILE.exists():
        try:
            old = set(json.loads(DEDUPE_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    DEDUPE_FILE.write_text(json.dumps(sorted(old | {m["_dedupe_key"] for m in moments}),
                                     ensure_ascii=False), encoding="utf-8")

    merged_acc = wd / f"accounts_merged_{ts}.csv"
    tokens_path = ROOT / args.tokens
    with merged_acc.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码", "pincode"])
        w.writeheader()
        for a in accounts[:len(moments)]:
            w.writerow({"序号": a["seq"], "昵称": a["nickname"],
                        "邮箱": a["email"], "密码": a["password"], "pincode": a["pincode"]})

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(merged_acc),
                "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "3.0",
                "--record-dedupe",
                "--web3-dedupe-file", str(DEDUPE_FILE),
                "--skip-upload",
                "--tokens-out", str(tokens_path)]
    if tokens_path.exists():
        cmd += ["--tokens-in", str(tokens_path)]

    print(f"\n=== publishing {len(moments)} text-only posts ===")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    print(f"Exit code: {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
