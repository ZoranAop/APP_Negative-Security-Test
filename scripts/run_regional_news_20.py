#!/usr/bin/env python3
"""
run_regional_news_20.py — 20 text-only news posts across 5 regions:
  - UK/Europe (EN)  : politics + tech
  - United Kingdom (EN)
  - Hong Kong (EN)
  - Singapore (EN)
  - Malaysia (MS)   : politics + tech + web3
  - Indonesia (ID)  : politics + tech + crypto

4 posts per country, each in that country's official language (HK/UK/SG/US = English).
First-person voice, no source attribution, pure text. Fresh accounts from 670 pool.

Usage:
  py -3 scripts/run_regional_news_20.py --yes
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

INTERACT_XLSX = ROOT / "互动用户池_670账号.xlsx"
STATE_DIR = ROOT / "state"
DEDUPE_FILE = STATE_DIR / "seen_regional_news_20.json"
CAPTION_DEDUPE = STATE_DIR / "seen_regional_news_20_captions.json"

# (region, lang, topic, caption)
POSTS = [
    # ── UK / Europe — English (4) ──────────────────────────────────────────
    (
        "uk", "en", "politics",
        "Watching the UK's post-election policy shift and I keep coming back to one thing: the cost-of-living promise. "
        "Energy prices, housing, and interest rates are still the defining issues for most households here. "
        "Whatever the government does next on fuel subsidies and social support, I think the next two years will be "
        "judged almost entirely on whether the middle of the market stops bleeding.",
    ),
    (
        "uk", "en", "tech",
        "The UK's AI strategy is quietly catching up. Cambridge's research output and the new national compute plans "
        "mean we're not just riding the US and China wave anymore. There's real momentum in the robotics and "
        "biotech sectors too. I don't think the headlines will do this movement justice, but the signal is there.",
    ),
    (
        "uk", "en", "web3",
        "FCA is still the world's most active crypto regulator and I think that's actually good for the UK. "
        "When the rules are clear, legitimate projects set up here instead of offshore. My own exposure to "
        "British stablecoin issuers and DeFi protocols has only grown since the new guidance dropped.",
    ),
    (
        "uk", "en", "crypto",
        "Bitcoin halving cycles aside, what's changing in the UK is the retail behaviour. The pension-fund whisper "
        "networks are talking about crypto allocation like it's a normal asset class now. I'm seeing more "
        "401k-style discussions than at any point in the last cycle.",
    ),

    # ── United States — English (4) ────────────────────────────────────────
    (
        "us", "en", "politics",
        "Midterms are reshaping the federal policy landscape and the crypto bill fight in Congress is the most "
        "important piece of it. Whether we get the CLARITY framework or a slower path, the floor is rising. "
        "I've been tracking the committee votes and the momentum is genuinely different from the last cycle.",
    ),
    (
        "us", "en", "tech",
        "The US chip export rules are creating real supply-chain bifurcation and I think most people underestimate "
        "the second-order effects. Data-center buildout in Texas and the new fab subsidies are moving faster than "
        "the headlines suggest. The AI compute race is a geopolitical arms race now.",
    ),
    (
        "us", "en", "web3",
        "RWA tokenization in the US is moving from pitch-deck to real deals. Treasuries on-chain, private credit "
        "settlement, even fractional real estate. I'm tracking three major traditional finance firms that are "
        "publicly building these rails. The infrastructure layer is where the next decade's value gets captured.",
    ),
    (
        "us", "en", "crypto",
        "The spot ETF inflow pattern is now the clearest institutional signal we have. Every correction gets bought, "
        "the sell pressure is thinner each time, and the holder base is getting deeper. I'm not calling a top — "
        "I'm just saying the structure has fundamentally changed and it's tilting toward the long side.",
    ),

    # ── Hong Kong — English (4) ───────────────────────────────────────────
    (
        "hk", "en", "politics",
        "The Hang Seng index levels alone tell you how much the market believes in the recovery narrative. "
        "Housing policy, the new tech parks, and the fintech licensing regime are all quietly rebuilding "
        "Hong Kong's position as the bridge between mainland depth and global markets. I'm more optimistic "
        "about the medium term than the 2022 bear would have ever been.",
    ),
    (
        "hk", "en", "tech",
        "The tech corridor along the MTR lines and the new Lantau infrastructure projects are worth watching. "
        "Deep-tech startups in semiconductor packaging and medical AI are getting real funding rounds. "
        "The talent pipeline question remains, but the output is showing up in the data.",
    ),
    (
        "hk", "en", "web3",
        "Hong Kong's virtual-asset fund framework is the real story and I think it's under-covered. "
        "The licensing for retail-facing digital-asset funds opened the door for institutions that were "
        "previously stuck in the compliance wilderness. I've seen two meaningful AUM entries in the last quarter.",
    ),
    (
        "hk", "en", "crypto",
        "The exchange licensing regime is doing exactly what it should — separating the legitimate players from "
        "the grey market. Volume has stabilised and the retail onboarding friction has dropped. For anyone "
        "running a multi-jurisdiction crypto portfolio, Hong Kong is the cleanest on-ramp right now.",
    ),

    # ── Singapore — English (4) ───────────────────────────────────────────
    (
        "sg", "en", "politics",
        "Singapore's approach to tech regulation — pro-innovation, rules-first, no moralising — keeps it ahead "
        "of every other Asian market I track. The new data-privacy framework and the digital identity rollout "
        "mean the platform for everything else is already in place. The question isn't whether Singapore leads, "
        "it's how fast the rest of the region can follow.",
    ),
    (
        "sg", "en", "tech",
        "The SG tech ecosystem is doing something quietly impressive — the deep-tech thesis is finally paying. "
        "Semiconductor packaging, advanced materials, medtech — the funding rounds I'm seeing are less "
        "consumer-app and more infrastructure. That's the sign of a maturing market and it's exactly what "
        "you want to see after a few years of venture froth.",
    ),
    (
        "sg", "en", "web3",
        "MAS is running the most consistent crypto regulatory track in Southeast Asia and it's showing. "
        "Tokenised capital-market products, digital-dollar pilots, the whole suite is moving forward without "
        "the stop-start mess of other jurisdictions. I keep my institutional allocation in Singaporean "
        "protocols and it's the most boring, most reliable part of the portfolio.",
    ),
    (
        "sg", "en", "crypto",
        "Stablecoin infrastructure in Singapore is the sleeper story. The interbank settlement layer built "
        "on top of the new digital-currency framework is exactly the kind of foundational move that makes "
        "everything else possible. I'm watching two of the major banks that are piloting it very closely.",
    ),

    # ── Malaysia — Malay (MS) (4) ─────────────────────────────────────────
    (
        "my", "ms", "politics",
        "Politik Malaysia buat saya nampak satu pola yang konsisten: kestabilan kerajaan bergantung pada "
        "penyelesaian isu kos sara hidup. Subsidi BBM, harga perumahan, dan faedah pinjaman masih top of mind "
        "untuk kebanyakan isi rumah. Apa yang kerajaan buat dalam dua tahun akan datang ni memang akan dinilai "
        "menurut sama ada kelas tengah berhenti lesu ekonomi. Saya perasan perbincangan dalam keluarga saya "
        "pun berubah — dulu semua tentang saham, sekarang semua tentang inflasi dan faedah rumah.",
    ),
    (
        "my", "ms", "tech",
        "Ekosistem teknologi Malaysia sedang bergerak dengan pantas dan saya tak terkejut masa tengok pelaburan "
        "dalam semikonduktor dan AI tempatan. Iskandar, Penang, dan Lembah Silicon di KL semua sedang buildup. "
        "Cabaran utama masih brain drain — tapi output yang keluar sekarang dah tahap yang boleh bersaing "
        "dengan Singapura. Saya personally rasa masa depan teknologi Malaysia cerah, as long as insentif "
        "talent kekal kompetitif.",
    ),
    (
        "my", "ms", "web3",
        "SKMM dan BNM sedang jalankan rangka kawal crypto yang paling jelas di Asia Tenggara. Bila lesen "
        "untuk Exchange tempatan dah stabil, projek yang legit mula setup di sini bukan offshore. Saya "
        "pegang beberapa token MyDeFi dan memang rasa confidence naik bila tengok regulator dah buat kerja "
        "sudah-sudah. Ini penting — crypto tanpa regulatory clarity memang tak dapat scale secara institutional.",
    ),
    (
        "my", "ms", "crypto",
        "Volume Bitcoin di exchange tempatan dah stabil dan saya nampak lebih ramai retail yang masuk dengan "
        "cara yang lebih terurus. Dulu semua FOMO, sekarang ada yang buat DCA, ada yang pegang long-term. "
        "Pergerakan ETF global pun dah mula nampak impact pada harga. Saya tak call top — tapi struktur "
        "market dah berubah dan dia condong ke arah long term.",
    ),

    # ── Indonesia — Indonesian (ID) (4) ───────────────────────────────────
    (
        "id", "id", "politics",
        "Politik Indonesia sedang dalam masa transisi dan saya melihat dua hal penting: komitmen terhadap "
        "infrastruktur dan pengelolaan subsidi energi. Harga BBM dan listrik tetap jadi isu utama bagi "
        "sebagian besar masyarakat. Apa yang pemerintah lakukan dalam 1-2 tahun ke depan akan diukur dari "
        "apakah daya beli kelas menengah bisa stabil. Saya melihat diskusi di keluarga saya pun berubah — "
        "dulu semua tentang investasi, sekarang tentang inflasi dan harga bahan pokok.",
    ),
    (
        "id", "id", "tech",
        "Ekosistem teknologi Indonesia sedang tumbuh dengan cepat dan saya tidak terkejut melihat gelombang "
        "pendanaan untuk semikonduktor, AI, dan fintech. Jakarta dan Bandung jadi hub utama, dan output-nya "
        "sudah bisa bersaing dengan Singapura. Tantangan terbesarnya tetap soal talent dan brain drain — "
        "tapi dengan insentif yang tepat, Indonesia punya potensi jadi pemain utama di kawasan.",
    ),
    (
        "id", "id", "web3",
        "Aturan baru dari Bappebti dan OJK sedang membentuk landasan crypto di Indonesia yang jauh lebih jelas "
        "dibanding beberapa tahun lalu. Exchange lokal yang sudah berlisensi mulai mendapat kepercayaan dari "
        "investor institusional. Saya pegang beberapa token DeFi lokal dan merasa lebih aman sekarang. "
        "Regulatory clarity itu fondasi — tanpa itu, crypto tidak akan bisa scale secara institusional.",
    ),
    (
        "id", "id", "crypto",
        "Volume Bitcoin di exchange lokal sudah stabil dan saya melihat lebih banyak retail yang masuk dengan "
        "cara lebih terukur. Dulu semua FOMO, sekarang banyak yang pakai strategi DCA dan hold jangka panjang. "
        "Pengalaman saya sendiri: masuk di setiap penurunan besar dan hasilnya jauh lebih baik daripada mengejar "
        "puncak. Struktur market global juga mulai bergeser — ETF inflows dan institusi sudah jadi players.",
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
    picked = []
    seen = set(exclude)
    for row in raw_rows[1:]:
        if len(picked) >= n:
            break
        rd = dict(zip(headers, row))
        email = str(rd.get("邮箱", "") or "").strip()
        nick = str(rd.get("昵称", "") or "").strip()
        password = str(rd.get("密码", "") or "").strip()
        pincode = str(rd.get("pincode", "") or "").strip()
        seq = str(rd.get("序号", "") or "").strip()
        if not email or not password or email in seen:
            continue
        seen.add(email)
        picked.append({
            "email": email, "password": password,
            "pincode": pincode, "nickname": nick, "seq": seq,
        })
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="regional_news_20_run")
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
            "_lang": lang, "_source": f"regional_news_{region}_{topic}",
            "_topic": topic, "_dedupe_key": f"r20_{region}_{topic}_{i}",
        })

    moments_csv = wd / f"moments_regional_news_20_{ts}.csv"
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
    print(f"\n[OK] {len(moments)} text-only posts ready  lang_dist={lang_count}")
    for i, m in enumerate(moments):
        acct = accounts[i] if i < len(accounts) else {"nickname": "?"}
        print(f"  [{i+1:2d}] {acct['nickname']:15} [{m['_source']:20}] | {m['content'][:55]}...")

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
    new_keys = {m["_dedupe_key"] for m in moments}
    DEDUPE_FILE.write_text(json.dumps(sorted(old | new_keys), ensure_ascii=False), encoding="utf-8")

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
