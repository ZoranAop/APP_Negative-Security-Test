#!/usr/bin/env python3
"""
run_multi_reg_en_12.py — 12 English text posts across India, EU/US, Malaysia,
Germany, and UK on web3/AI/finance/economics/policy/social.
All EN, first-person, diverse voice per poster.
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
DEDUPE_FILE = STATE_DIR / "seen_multi_reg_en_12.json"
CAPTION_DEDUPE = STATE_DIR / "seen_multi_reg_en_12_captions.json"
EN_NICK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-\ ]*$")

# (region, topic, voice_style, caption)
# voice_style hints: analytic, casual, data-driven, narrative, contrarian
POSTS = [
    # India — web3
    (
        "india", "web3", "analytic",
        "Been tracking India's stablecoin pilot carefully — the RBI's "
        "framework is tighter than most, which is honestly a good thing "
        "for institutional adoption. The on-chain data shows activity "
        "isn't slowing despite regulatory friction. That resilience "
        "is the real signal I'm watching, not the token prices.",
    ),
    # EU/US — AI
    (
        "eu_us", "ai", "data_driven",
        "The model benchmark gap between US and EU labs is compressing "
        "faster than anyone expected. Three EU research groups just "
        "published results within 5% of frontier US models. The "
        "regulatory burden is clearly creating an engineering "
        "incentive, and I think that's underrated in most analysis.",
    ),
    # Malaysia — finance
    (
        "malaysia", "finance", "casual",
        "Just saw the BNM's new liquidity framework drop and honestly, "
        "this is a smart move. They're basically saying 'here's how we "
        "keep banks funded without the usual panic' — and the markets "
        "are reacting calm, not scared. That's what good policy looks "
        "like when it lands right.",
    ),
    # Germany — economics
    (
        "germany", "economics", "narrative",
        "Germany's manufacturing PMI has been in contraction for four "
        "straight months. The dominant narrative is production "
        "relocation to the EU east and North America, but I keep "
        "coming back to the energy cost angle — the structural gap "
        "isn't closing fast enough for that story to hold. Numbers "
        "are starting to support that view.",
    ),
    # UK — policy
    (
        "uk", "policy", "contrarian",
        "Everyone's writing off the UK's stablecoin sandbox as "
        "over-engineered, but I think they're missing the point. The "
        "FCA is building the compliance rails now so that when the "
        "actual demand hits — and it will — there's no scrambling. "
        "That's patient policy-making, and it's rare. Give it two "
        "years.",
    ),
    # India — military
    (
        "india", "military", "data_driven",
        "India's integrated air defense modernization just crossed a "
        "threshold: the S-400 integration data shared with NATO "
        "partners is now part of a shared warning network. That's not "
        "just hardware — it's an institutional commitment that changes "
        "the regional calculus. The numbers on response time and "
        "layered coverage have improved measurably since 2023.",
    ),
    # EU/US — oil
    (
        "eu_us", "oil", "analytic",
        "Front-month Brent is now trading in contango for the first "
        "time in eight weeks. That's a structural shift, not a "
        "blip — it means the market is pricing in demand weakness "
        "that extends past Q2. The inventory build at Cushing plus "
        "OPEC+ discipline is creating a squeeze that won't relieve "
        "until the new supply vintages come online. Watch the "
        "forward curve, not the spot.",
    ),
    # Malaysia — social
    (
        "malaysia", "social", "casual",
        "The new national digital skills program just hit 500,000 "
        "enrollees in its first quarter — that's faster than the "
        "government's own target. I was skeptical at launch, but the "
        "regional training hubs are actually working. The question "
        "now is whether the hiring pipeline can absorb this talent "
        "wave without a correction.",
    ),
    # Germany — web3
    (
        "germany", "web3", "narrative",
        "Germany's BaFin just cleared its first two institutional "
        "crypto custody licenses, and the timing tells you something: "
        "they moved on the same day the EU's final stablecoin "
        "directive language was confirmed. That's not coincidence — "
        "the regulatory architecture is landing in sequence now, and "
        "the institutional on-ramp is about to open for real.",
    ),
    # UK — social
    (
        "uk", "social", "contrarian",
        "The UK's housing affordability crisis narrative is getting "
        "complicated. New build starts are up 14% YoY, and the "
        "planning reform in the South East is actually moving "
        "permits faster than predicted. I don't think that fixes "
        "the affordability math, but it does break the 'nothing is "
        "changing' story that's been running for a decade.",
    ),
    # India — public_policy
    (
        "india", "public_policy", "data_driven",
        "The PM-KISAN disbursement data for this quarter shows a "
        "7.2% increase in average transfer amount per farmer, which "
        "is the first real uplift since the scheme launched. Rural "
        "consumption recovery is no longer just anecotal — the data "
        "is now showing it in two consecutive quarters.",
    ),
    # EU/US — social
    (
        "eu_us", "social", "narrative",
        "The remote-work migration to southern Europe is hitting a "
        "critical mass. I was in Portugal last month and the "
        "digital nomad communities in Lisbon and Porto are now "
        "substantial enough to be showing up in local business "
        "demographics. That's not tourism anymore — that's a new "
        "population segment with different spending patterns and "
        "longer stays.",
    ),
]

assert len(POSTS) == 12, f"Expected 12, got {len(POSTS)}"


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
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="multi_reg_en_12_run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)

    used = _load_used_emails()
    accounts = load_en_nick_accounts(len(POSTS), used)
    print(f"[publisher-accounts] {len(accounts)} EN-nick: "
          f"{[a['nickname'] for a in accounts]}")
    if len(accounts) < len(POSTS):
        print(f"[ERROR] Need {len(POSTS)}, found {len(accounts)}", file=sys.stderr)
        return 1

    used_caps = set()
    if CAPTION_DEDUPE.exists():
        try:
            used_caps = set(json.loads(CAPTION_DEDUPE.read_text(encoding="utf-8")))
        except Exception:
            pass

    moments = []
    for i, (region, topic, style, caption) in enumerate(POSTS):
        if caption in used_caps:
            continue
        used_caps.add(caption)
        moments.append({
            "content": caption,
            "visibility": "0", "room_id": "", "image_urls": "",
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_lang": "en",
            "_source": f"multi_reg_{region}",
            "_topic": topic,
            "_dedupe_key": f"mre12_{region}_{topic}_{i}",
        })

    moments_csv = wd / f"moments_multi_reg_en_12_{ts}.csv"
    fields = ["content","visibility","room_id","image_urls","location_name",
              "location_address","location_lat","location_lon",
              "_lang","_source","_topic","_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow(m)

    print(f"\n[OK] {len(moments)} text-only posts ready")
    for i, m in enumerate(moments):
        acct = accounts[i]
        preview = m["content"][:55].replace("\n"," ")
        print(f"  [{i+1}] {acct['nickname']:15} [{m['_topic']:12}] | {preview}...")

    if args.dry_run:
        print("\n[dry-run] Stopping")
        return 0

    if not args.yes:
        if input("Confirm publish? (y/n): ").strip().lower() not in ("y","yes"):
            print("Cancelled.")
            return 0

    CAPTION_DEDUPE.write_text(json.dumps(sorted(used_caps), ensure_ascii=False), encoding="utf-8")
    old = set()
    if DEDUPE_FILE.exists():
        try: old = set(json.loads(DEDUPE_FILE.read_text(encoding="utf-8")))
        except Exception: pass
    new_keys = {m["_dedupe_key"] for m in moments}
    DEDUPE_FILE.write_text(json.dumps(sorted(old | new_keys), ensure_ascii=False), encoding="utf-8")

    merged_acc = wd / f"accounts_merged_{ts}.csv"
    tokens_path = ROOT / args.tokens
    tokens_path.parent.mkdir(parents=True, exist_ok=True)
    with merged_acc.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号","昵称","邮箱","密码","pincode"])
        w.writeheader()
        for a in accounts[:len(moments)]:
            w.writerow({"序号": a["seq"], "昵称": a["nickname"],
                        "邮箱": a["email"], "密码": a["password"], "pincode": a["pincode"]})

    cmd = PY + [str(HERE/"publish_from_tokens.py"),
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
