#!/usr/bin/env python3
"""
run_mideast_12_en.py — 12 English text-only posts on Middle East
military / oil / social news.
- Publisher accounts: EN-nick, separate pool (excludes econ_policy_3country_20 publishers)
- All posts: English, first-person voice, concise
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
DEDUPE_FILE = STATE_DIR / "seen_mideast_12_en.json"
CAPTION_DEDUPE = STATE_DIR / "seen_mideast_12_en_captions.json"
EN_NICK_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-\ ]*$")

POSTS = [
    # 1 — military
    (
        "mideast_military",
        "The latest joint naval exercise in the Strait of Hormuz involved "
        "seven fleets — the largest multinational deployment there in a "
        "decade. Oil tanker traffic through the Strait dropped 12% this "
        "week, and I'm seeing freight rates spike immediately. The "
        "geopolitical premium on energy is back, and I don't think "
        "it's going away quickly.",
    ),
    # 2 — oil
    (
        "mideast_oil",
        "OPEC+ just confirmed the Q4 production hold — no incremental "
        "output even as US inventories build. Brent is holding near "
        "$82, but I'm watching the forward curve: the front month is "
        "inverted again, which historically precedes a pullback. "
        "Supply discipline is working, but demand-side weakness is "
        "starting to show.",
    ),
    # 3 — social
    (
        "mideast_social",
        "The Riyadh season tourism numbers just posted record Q3 — "
        "4.2 million visitors, up 38% YoY. The city is genuinely "
        "repositioning itself as a cultural hub, not just a petro-economy. "
        "I'm seeing a lot of new hospitality investment, and the "
        "talent pipeline for service industries is the next bottleneck "
        "they need to solve.",
    ),
    # 4 — military
    (
        "mideast_military",
        "The new air defense procurement cycle in the Gulf is shifting "
        "toward layered defense — short-range interceptors paired with "
        "long-range systems. Two countries in the region are now "
        "reportedly in talks for integrated radar networks. This "
        "change in doctrine signals a more serious long-term "
        "posture, not just reactive buys.",
    ),
    # 5 — oil
    (
        "mideast_oil",
        "Saudi Aramco's Q3 dividend surprise pushed the stock up 3% "
        "overnight and dragged the whole energy complex with it. "
        "Production held at 9.5M bpd despite the maintenance window. "
        "The market is pricing in a 2025 demand plateau — that's "
        "the real story here, not the dividend.",
    ),
    # 6 — social
    (
        "mideast_social",
        "The new women's employment mandate in Saudi Arabia is now "
        "enforced, and the private sector compliance numbers are "
        "mixed. I'm seeing strong uptake in fintech and healthcare, "
        "but construction and logistics still lag. The cultural "
        "shift is real but uneven — and that's going to define the "
        "next decade's labor market.",
    ),
    # 7 — military
    (
        "mideast_military",
        "Israel's new counter-drone program is now in operational "
        "trial in the southern sector. The system combines directed "
        "energy with traditional kinetic interceptors — a first for "
        "this region. The cost per interception is dropping fast, "
        "which changes the economics of asymmetric threats "
        "fundamentally.",
    ),
    # 8 — oil
    (
        "mideast_oil",
        "Iran's crude exports have quietly recovered to 1.8M bpd "
        "despite the sanctions regime — most of it heading to "
        "Asia via shadow fleet tankers. The gap between declared "
        "production and actual exports is the metric I'm watching. "
        "Global oil inventory data is telling a more complex story "
        "than the headlines suggest.",
    ),
    # 9 — social
    (
        "mideast_social",
        "The UAE's new free health insurance mandate for all "
        "residents regardless of nationality is now in effect. "
        "The employer-side contribution was a sticking point "
        "for a while, but the rollout is smoother than I "
        "expected. Healthcare access is a quiet but powerful "
        "competitiveness lever that this move strengthens "
        "significantly.",
    ),
    # 10 — military
    (
        "mideast_military",
        "The recent joint cyber defense drill between Qatar, "
        "Oman, and Bahrain was the first trilateral exercise "
        "of its kind in the Gulf. The focus was on critical "
        "infrastructure protection — power grids, water "
        "systems, financial nodes. That's a sign of real "
        "institutional coordination, not just symbolic "
        "cooperation.",
    ),
    # 11 — oil
    (
        "mideast_oil",
        "The new deepwater gas project off Qatar's coast just "
        "started pre-production and is on schedule for 2027 "
        "commercial operation. LNG export capacity is expanding "
        "into a market that's already tightening. The race for "
        "long-term offtake contracts is intensifying — and "
        "Asia is the clear winner right now.",
    ),
    # 12 — social
    (
        "mideast_social",
        "Cairo's new smart-city district is opening its first "
        "phase, and the tech talent pipeline from the university "
        "sectors is finally catching up to demand. I'm seeing "
        "local AI and data science firms growing at 40%+ YoY. "
        "The question now is infrastructure — fiber coverage "
        "and power redundancy in the new district are the "
        "real tests of execution.",
    ),
]

assert len(POSTS) == 12


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
    ap.add_argument("--workdir", default="mideast_12_en_run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)

    # Exclude all previous run accounts (tokens + all run dirs)
    used = _load_used_emails()
    accounts = load_en_nick_accounts(len(POSTS), used)
    print(f"[publisher-accounts] {len(accounts)} EN-nick accounts: "
          f"{[a['nickname'] for a in accounts[:8]]}...")
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
        source, caption = POSTS[i]
        if caption in used_caps:
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
            "_lang": "en",
            "_source": source,
            "_topic": source.replace("mideast_", ""),
            "_dedupe_key": f"me12_{i}",
        })

    moments_csv = wd / f"moments_mideast_12_en_{ts}.csv"
    fields = ["content", "visibility", "room_id", "image_urls", "location_name",
              "location_address", "location_lat", "location_lon",
              "_lang", "_source", "_topic", "_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow(m)

    print(f"\n[OK] {len(moments)} text-only posts ready")
    for i, m in enumerate(moments):
        acct = accounts[i] if i < len(accounts) else {"nickname": "?"}
        preview = m["content"][:50].replace("\n", " ")
        print(f"  [{i+1}] {acct['nickname']:15} [{m['_topic']:12}] | {preview}...")

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
