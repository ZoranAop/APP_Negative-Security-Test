#!/usr/bin/env python3
"""
run_econ_policy_3country_20.py — 20 text-only posts on economic / policy /
public policy news for India, Bangladesh, and Malaysia.
- Languages: hi (India), bn (Bangladesh), ms (Malaysia)
- Publisher accounts: EN-nick, from pre_企管用户_850.csv
- Topics cycle: economic, policy, public_policy
"""
from __future__ import annotations

import argparse, csv, io, json, re, subprocess, sys, time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

POOL_850_CSV = ROOT / "pre_企管用户_850.csv"
PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"
STATE_DIR = ROOT / "state"
DEDUPE_FILE = STATE_DIR / "seen_econ_policy_3country_20.json"
CAPTION_DEDUPE = STATE_DIR / "seen_econ_policy_3country_20_captions.json"

EN_NICK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-\ ]*$")

# ------------------------------------------------------------------
# Post definitions: (country, lang, topic, caption)
# All captions use first-person voice, concise, highlight-first.
# ------------------------------------------------------------------
POSTS = [
    # --- India (hi) — economic / policy / public policy ---
    ("india", "hi", "economic",
     "मैंने देखा है कि इस तिमाही में भारत के GDP growth rate 7.2% पर पहुँचा है, जो forecast "
     "से ऊपर है। Manufacturing PMI भी 54.8 होकर expand zone में है। RBI की next monetary "
     "policy meeting में rate cut की उम्मीद है — अगर जून में 25bp का cut आया तो retail "
     "credit expansion में और तेज़ी आनी है।"),
    ("india", "hi", "policy",
     "बिज़नेस community के लिए एक बड़ा नोट: भारत में GST slab rationalization "
     "अब 4-tier system पर चली गई है — 5%, 12%, 18%, 28%। Middle slab में commodity tax "
     "कम होना consumer prices को थोड़ा down push करेगा। Small business owners के लिए "
     "input credit recovery में simplification है, जो compliance cost घटाएगी।"),
    ("india", "hi", "public_policy",
     "PM-KISAN scheme अब 15 करोड़ farmers तक पहुँच चुकी है, annual ₹6,000 "
     "direct transfer के साथ। Rural consumption data में recovery दिख रहा है। "
     "लेकिन implementation में last-mile delivery पर अभी work है — खासकर "
     "बिना bank account वाले किसानों के लिए।"),
    ("india", "hi", "economic",
     "IT exports Q2 में $75B के mark के ऊपर गए, जो 18% YoY growth है। "
     "AI adoption में India अभी early stage है, लेकिन enterprise pilots "
     "fast बढ़ रहे हैं — AWS और Azure दोनों ने India में new data centers "
     "announce किए हैं, जो long-term में infrastructure demand को pull करेगा।"),
    ("india", "hi", "policy",
     "NITI Aayog का नया public-private partnership framework infrastructure "
     "sector में game-changer हो सकता है। Toll collection, risk sharing, "
     "और financing structure में clarity आई है। Private capital में "
     "re-entry का path अब visible है।"),

    # --- Bangladesh (bn) — economic / policy / public policy ---
    ("bangladesh", "bn", "economic",
     "বাংলাদেশের GDP growth এবার fiscal year-এ 6.5% ছাড়িয়ে 7% এর কাছাকাছি যাচ্ছে, "
     "রমজান-পূর্ব পোশাক-বস্ত্র সেক্টর রপ্তানি 12% up যাওয়ার পর। RMG exports এখনও "
     "মূল engine, কিন্তু diversification পৌঁছে গেছে — IT services ও pharmaceuticals "
     "এখন দ্বিতীয় tier হিসেবে কাজ করছে।"),
    ("bangladesh", "bn", "policy",
     "Bangladesh Bank নতুন FX policy ঘোষণা করেছে — importers এখন USD "
     "allocation-এর জন্য automated system ব্যবহার করবে, manual approval "
     "প্রসেস ছাড়া। Trade finance access উন্মুক্ত হবে, যেখানে আগে "
     "queueing system-এ 3-6 সপ্তাহের delay ছিল। SME exporters-এর জন্য "
     "এটা সরাসরি positive।"),
    ("bangladesh", "bn", "public_policy",
     "গ্রামীন Electrification program এখন 98% household-এর কাছে "
     "electricity পৌঁছে দিয়েছে, যা world-এর fastest rollout-এর একটা "
     "উদাহরণ। কিন্তু last 2% — remote riverine communities — এখনো "
     "solar micro-grid-এর মুখোমুখি, investment gap সেখানে বড়।"),
    ("bangladesh", "bn", "economic",
     "Remittance inflow এই fiscal quarter-এ $4.2B, যা record high। "
     "Diaspora-দের earnings এখনো USD-এ চলছে, তাই BDT-এর উপর "
     "upward pressure তৈরি হচ্ছে — central bank এখনো rate "
     "stabilize-তে focus করে আছে, capital inflow control "
     "tight করা হচ্ছে।"),
    ("bangladesh", "bn", "policy",
     "Digital Finance Act 2024 নতুন করে clarify করেছে — "
     "e-wallets এখন bank-level KYC-এর আওতায়, peer-to-peer transfer "
     "daily limit $500-এ থাকবে। Fintech startup-দের জন্য compliance "
     "cost বাড়াচ্ছে, কিন্তু user protection level-ও ওপরে যাবে।"),

    # --- Malaysia (ms) — economic / policy / public policy ---
    ("malaysia", "ms", "economic",
     "GDP Malaysia Q2 2024 mencatat pertumbuhan 4.8% — lebih kuat dari "
     "jangkaan awal. Exports elektronik dan perkapalan masih jadi pendorong, "
     "tapi konsumsi domestik pun naik 5.1%. Saya perasan inflasi masih "
     " terkawal di bawah 2.5%, jadi BNM mungkin akan kekalkan polisi "
     "moneter yang sama untuk masa lagi."),
    ("malaysia", "ms", "policy",
     "Kerajaan baru sahaja keluarkan framework incentive untuk data center "
     "bernilai RM45 billion — tax relief sehingga 40% untuk syarikat "
     "hyperscaler yang bangun pusat data di Penang dan Johor. Saya "
     "nampak beberapa pemain besar dah mula site survey. Kalau jadi, "
     "ini akan jadi engine pertumbuhan baharu untuk sektor teknologi."),
    ("malaysia", "ms", "public_policy",
     "Program Perumahan Rakyat fasa 2 akan bina 50,000 unit baharu — "
     "fokus kepada pekerja sektor awam dan golongan B40. Saya nampak "
     "demand memang tinggi, terutamanya di KL, PJ dan Ipoh. Tapi "
     "kena pantau supply chain material construction — harga bes dan "
     "cement masih high."),
    ("malaysia", "ms", "economic",
     "RM (Ringgit) masih stable di paras 4.35-4.40 terhadap USD walaupun "
     "dollar kuat. Fitch baru recently upgrade outlook kita ke "
     "stable — sovereign debt ratio turun ke 62%. Saya rasa capital "
     "inflow dalam bond market akan berterusan kalau fiscal "
     "discipline dikekalkan."),
    ("malaysia", "ms", "public_policy",
     "MyDIGITAL blueprint kini dalam fasa implementasi — target digital "
     "skiller sebanyak 200,000 sebelum 2026. Program upskilling untuk "
     "sektor pengilangan dan logistik dah bermula di beberapa "
     "university. Saya nampak synergy dengan growth data center "
     "ecosystem — talent pool akan jadi bottleneck utama kalau "
     "investment datang lebih cepat dari training."),
]

# Repeat some topics to reach 20 posts
POSTS += [
    ("india", "hi", "economic",
     "Crude oil import bill इस महीने ₹1.2 lakh crore, जो YoY 15% बढ़ा है। "
     "Refinery utilization high है, इसलिए trade deficit में pressure बढ़ रहा है। "
     "लेकिन IT exports में strength इस risk को частично offset कर रही है।"),
    ("india", "hi", "public_policy",
     "MUDRA loan scheme में इस quarter ₹2.1 lakh crore disbursed हुआ, "
     "small business lending recovery को दर्शाता है। Rural demand में "
     "recovery दिखने लगी है, खासकर tractor और two-wheeler sales में।"),
    ("bangladesh", "bn", "economic",
     "RMG sector-এর next growth engine হবে value addition — "
     "readymade garments-এর পাশাপাশি home textiles ও technical textiles-এ "
     "investment বাড়ছে। Europe-র buyer-দের demand এখনো strong, "
     "তবে compliance cost বাড়ছে।"),
    ("bangladesh", "bn", "policy",
     "Tax reform-এর পর CVA (Customs Valuation Authority) "
     "nতুন guidelines দিচ্ছে — importers-দের জন্য documentation "
     "সহজ হবে, clearances সময় কমতে পারে। FDI inflow-এর "
     "upside-এর জন্য regulatory clarity বাড়ছে, "
     "investment court এখনও early।"),
    ("malaysia", "ms", "policy",
     "BNM kini dalam proses review framework stablecoin — "
     "e-money yang ada sekarang (e-wallet retail) dah cukup "
     "matang, tapi institutional stablecoin masih belum ada "
     "regulatory path yang clear. Saya nampak beberapa "
     "bank sudah masuk pilot program. KPMG report pun "
     "kata readiness level masih early stage."),
    ("malaysia", "ms", "public_policy",
     "Program JKM untuk B40 household-er subsidy "
     "akan diperluas dari 2.8 juta ke 4 juta household "
     "mulai tahun depan. Saya rasa impact-nya direct "
     "kepada daya beli di peringkat akar umbi — "
     "terutama untuk golongan yang tak dapat "
     "tangkap program upskilling dulu."),
    ("india", "hi", "policy",
     "Semiconductor mission में अब fab construction phase शुरू हुआ "
     "गोवा और अमृतसारी में। TSMC partnership confirm होने के बाद "
     "supply chain reshaping visible है। India का target "
     "2030 तक 5% से 10% global semiconductor production "
     "share लेना है — infrastructure investment अभी early।"),
    ("bangladesh", "bn", "public_policy",
     "WASH (Water, Sanitation, Hygiene) program গ্রামীন "
     "area-তে এখন 85% coverage-এ আছে। But last mile "
     "— floaters, river islands — এখনো challenge। "
     "NGO partnership model-এ investment ঘনত্ব "
     "বাড়াচ্ছে, যা positive signal।"),
    ("malaysia", "ms", "economic",
     "Logistics sector Malaysia sedang naik — "
     "Port Klang dan Tanjung Pelepas terus expand, "
     "dan KLIA transit pun upgrade. Cost-to-ship "
     "dari Malaysia ke Asia-Pacific masih competitive "
     "banding Singapura. Saya nampak growth dalam "
     "cold chain, terutamanya food & pharma."),
]

assert len(POSTS) == 24, f"Expected 24 posts, got {len(POSTS)}"


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


def load_en_nick_accounts(n: int, exclude: set) -> list:
    picked = []
    seen = set(exclude)
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
            pincode = (r.get("pincode") or "").strip()
            seq = (r.get("序号") or "").strip()
            if not email or not password or email.lower() in seen:
                continue
            if not EN_NICK_RE.match(nick):
                continue
            seen.add(email.lower())
            picked.append({"email": email, "password": password,
                           "pincode": pincode, "nickname": nick, "seq": seq})
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="econ_policy_3country_20_run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)

    used = _load_used_emails()
    accounts = load_en_nick_accounts(len(POSTS), used)
    print(f"[publisher-accounts] {len(accounts)} EN-nick accounts: "
          f"{[a['nickname'] for a in accounts[:10]]}...")
    if len(accounts) < len(POSTS):
        print(f"[ERROR] Need {len(POSTS)} EN-nick accounts, found {len(accounts)}",
              file=sys.stderr)
        return 1

    used_caps = set()
    if CAPTION_DEDUPE.exists():
        try:
            used_caps = set(json.loads(CAPTION_DEDUPE.read_text(encoding="utf-8")))
        except Exception:
            pass

    moments = []
    for i in range(len(POSTS)):
        country, lang, topic, caption = POSTS[i]
        if caption in used_caps:
            print(f"  [skip] post {i+1} ({country}) caption already used")
            continue
        used_caps.add(caption)
        moments.append({
            "content": caption,
            "visibility": "0",
            "room_id": "",
            "image_urls": "",
            "location_name": "",
            "location_address": "",
            "location_lat": "",
            "location_lon": "",
            "_lang": lang,
            "_source": f"econ_policy_{country}",
            "_topic": topic,
            "_dedupe_key": f"ep3c_{country}_{i}",
        })

    if not moments:
        print("[ERROR] All captions already used", file=sys.stderr)
        return 1

    moments_csv = wd / f"moments_econ_policy_3country_20_{ts}.csv"
    fields = ["content", "visibility", "room_id", "image_urls", "location_name",
              "location_address", "location_lat", "location_lon",
              "_lang", "_source", "_topic", "_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow(m)

    lang_count = {}
    for m in moments:
        lang_count[m["_lang"]] = lang_count.get(m["_lang"], 0) + 1
    print(f"\n[OK] {len(moments)} text-only posts ready")
    print(f"[OK] lang dist: {lang_count}")
    for i, m in enumerate(moments[:10]):
        acct = accounts[i] if i < len(accounts) else {"nickname": "?"}
        preview = m["content"][:50].replace("\n", " ")
        print(f"  [{i+1}] {acct['nickname']:15} [{m['_lang']:6}] "
              f"[{m['_topic']:14}] | {preview}...")

    if args.dry_run:
        print("\n[dry-run] Stopping before publish")
        return 0

    if not args.yes:
        if input("\nConfirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    CAPTION_DEDUPE.write_text(json.dumps(sorted(used_caps), ensure_ascii=False), encoding="utf-8")
    dedupe_file = DEDUPE_FILE
    old = set()
    if dedupe_file.exists():
        try:
            old = set(json.loads(dedupe_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    new_keys = {m["_dedupe_key"] for m in moments}
    dedupe_file.write_text(json.dumps(sorted(old | new_keys), ensure_ascii=False), encoding="utf-8")

    merged_acc = wd / f"accounts_merged_{ts}.csv"
    tokens_path = ROOT / args.tokens
    tokens_path.parent.mkdir(parents=True, exist_ok=True)
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
                "--web3-dedupe-file", str(dedupe_file),
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
