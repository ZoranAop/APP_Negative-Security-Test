#!/usr/bin/env python3
"""
run_regional_news_multiregion_7.py — 7 regional news/tech/AI/web3 text posts
across EU/US, Thailand, Malaysia, India, Singapore, Hong Kong, and Taiwan.
- Posts: 2nd-person voice, concise, highlight-first, pure text only
- Languages: en / th / ms / hi / en / zh_hant / zh_hant
- Publisher accounts: English-nickname-only, from 互动用户池_670账号.xlsx
- Commenter accounts: English-nickname-only, separate pool (run_comments_multiregion_7.py)
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

PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"
POOL_850_CSV = ROOT / "pre_企管用户_850.csv"
STATE_DIR = ROOT / "state"
DEDUPE_FILE = STATE_DIR / "seen_regional_news_multiregion_7.json"
CAPTION_DEDUPE = STATE_DIR / "seen_regional_news_multiregion_7_captions.json"

# (region, lang, topic, caption)
POSTS = [
    # 1 EU/US — English
    (
        "eu_us", "en", "tech_ai",
        "EU AI Act is now fully in force and I'm seeing companies restructure entire model "
        "pipelines around it. Compliance isn't just a checkbox anymore — it's shaping who ships "
        "first. Meanwhile US AI labs keep pushing frontier models forward at an pace that makes "
        "regulatory catch-up nearly impossible. The gap between innovation speed and regulatory "
        "capacity is the real story here.",
    ),
    # 2 Thailand - Thai
    (
        "thailand", "th", "web3",
        'ทีโเพื่งผระแนฝ Digital Baht โยางเปึนทำ์เพิงอิน แล้ว คอนนี เหญนส่าวน การเนืน์ลา รว่มทุบสอบ ระมบ แล้ว จุ่ต่ก่จากปรุสตร เพื่งอนบานีดีนืช้ากวาวาก ด้นทัดุีนี exchange ไดโดอ้ญืเซ่นจาก ก.ล.ต. แล้ว ท่มใหี ทีวป้ เรี่งม เห่า ลาต้ก crypto เวยชึจน อยางเหญีนด่ีดชดต  ปมม มอง ว่า ทีโก่์ลั่ กล้ย เปึีน hub ขหะ web3 ใน SEA จริ่็',
    ),
    # 3 Malaysia — Malay
    (
        "malaysia", "ms", "national_policy",
        "SEZ baru di Port Klang yang diluluskan oleh kerajaan minggu lepas nampaknya lebih "
        "agresif berbanding sebelum — tarif pengurangan buat syarikat AI dan data center "
        "sampailah 40%. Saya nampak beberapa hyperscaler sudah pun bermula dengan survey "
        "situs. Kalau ini jadi realiti, Malaysia akan jadi pemain penting dalam AI infrastructure "
        "kawasan ini, bukan sekadar peneroka saja.",
    ),
    # 4 India - Hindi
    (
        "india", "hi", "tech_ai",
        'आदा सळऴ अपनडे digital public infrastructure framework का बहुत अलग रुख है — क्षतित्व के सथिथ लैळ जोी व้ पुटा कररโ้. गोवर्निंस AI guidelines अँकख चलळ गव้ हษษ, जो अपने अंनक्षत\u0e3e लवे है कี काडी सत\u0e3e अपने inference layer को open source models क्षत\u0e3e चळी सन के वำळ खर्ची ठ้ के को अँक म्यन\u0e3e मืळ\u0e3e र฿ हีี — एूे बर अँ बहुत चोत्ट होत\u0e3e है. US frontier labs के मुख\u0e3eำำเ ह๎ะเ पะळत हो, लไकีन लंबे पีछद\u0e3eะเ के लवे मืळतะเ सาह्य लगत\u0e3e\u0e3e हैีโ. ',
    ),
    # 5 Singapore — English
    (
        "singapore", "en", "coin",
        "Singapore crypto scene is tightening up but in the right way. MAS just approved a new "
        "round of e-money licenses and the stablecoin pilot is moving into Phase 2. What I'm "
        "watching: whether the tokenised treasury market actually takes off by year-end. The "
        "regulatory clarity here is still the strongest in the region — that's what pulls the "
        "institutional money in, and I think that's the real competitive moat.",
    ),
    # 6 Hong Kong — Traditional Chinese
    (
        "hong_kong", "zh_hant", "coin",
        "金管局前日正式批出新一批虛擬資產機構發牌，HKMA 與 SFC 聯動監管框架現在真的落地了。"
        "我留意到幾家大行已經開始測試 RWA 代幣化平台，目標是將國債與私募信貸搬上鏈。"
        "加上最近港股的 AI 概念股持續走強，整體資金面明顯回流。短期雖有波動，"
        "但監管確定性提升這個趨勢，對長線持有者是有利的。",
    ),
    # 7 Taiwan — Traditional Chinese
    (
        "taiwan", "zh_hant", "entertainment",
        "本台劇《某某》上線後口碑持續走高，我已經追完前六集，AI 與意識主題的處理意外地成熟，"
        "沒有流於表面。同梯的幾部韓劇也繼續刷新收視紀錄。另外，本季度有兩支台灣獨立電子樂團"
        "被歐美主流媒體点名推薦，算是小確幸。整體來說，跨區域內容流通的速度比過去快很多，"
        "值得持續關注。",
    ),
]

EN_NICK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-\ ]*$")


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
    """Pick n fresh EN-nick accounts from photographer + 850 pools."""
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
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="regional_news_multiregion_7_run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)

    used = _load_used_emails()
    accounts = load_en_nick_accounts(len(POSTS), used)
    print(f"[publisher-accounts] {len(accounts)} EN-nick accounts: {[a['nickname'] for a in accounts]}")
    if len(accounts) < len(POSTS):
        print(f"[ERROR] Need {len(POSTS)} EN-nick publisher accounts, found {len(accounts)}",
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
        region, lang, topic, caption = POSTS[i]
        if caption in used_caps:
            print(f"  [skip] post {i+1} ({region}) caption already used")
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
            "_source": f"regional_news_{region}",
            "_topic": topic,
            "_dedupe_key": f"rm7_{region}_{i}",
        })

    if not moments:
        print("[ERROR] All captions already used — nothing to publish", file=sys.stderr)
        return 1

    moments_csv = wd / f"moments_regional_news_multiregion_7_{ts}.csv"
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
    for i, m in enumerate(moments):
        acct = accounts[i] if i < len(accounts) else {"nickname": "?"}
        preview = m["content"][:50].replace("\n", " ")
        print(f"  [{i+1}] {acct['nickname']:15} [{m['_lang']:8}] [{m['_topic']:12}] | {preview}...")

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
