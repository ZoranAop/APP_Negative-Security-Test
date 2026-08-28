#!/usr/bin/env python3
"""
run_web3_5_new.py — 5 new web3 accounts, each posts 1 web3/crypto news item in English.
No blank lines between paragraphs. Uses existing token pool.
"""
from __future__ import annotations

import argparse, csv, io, json, random, subprocess, sys, time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]
API = "https://api.xxai.com"
HEADERS = {"Content-Type": "application/json"}
ACCOUNTS_CSV = ROOT / "accounts_web3_100.csv"
DEDUPE_FILE = ROOT / "state" / "seen_web3.json"


def load_tokens() -> dict:
    return json.load(open(ROOT / "result/tokens.json", encoding="utf-8"))


def load_raw_news(n: int = 20) -> list[dict]:
    """Load raw web3 news from the latest fetch."""
    import glob
    files = sorted(glob.glob(str(ROOT / "web3_run" / "web3_raw_*.csv")))
    if not files:
        print("[ERROR] No web3_raw CSV found. Run fetch_web3.py first.", file=sys.stderr)
        sys.exit(1)
    latest = files[-1]
    rows = list(csv.DictReader(open(latest, encoding="utf-8-sig")))
    # Return rows not yet used (by title normalization)
    seen = set()
    if DEDUPE_FILE.exists():
        try:
            seen = set(json.loads(DEDUPE_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    random.seed(7)
    random.shuffle(rows)
    picked = []
    for r in rows:
        if len(picked) >= n:
            break
        title = (r.get("content") or "").strip().lower()
        # normalize for dedupe check
        norm = "".join(title.split())
        if norm not in seen:
            picked.append(r)
    return picked


def make_caption(row: dict, idx: int, seed: int) -> str:
    """Generate a unique English caption from the raw news row."""
    title = row.get("content", "")
    site = row.get("_site", "")
    brief = row.get("_brief", "")
    # Build a varied caption from the title + brief
    templates = [
        f"Interesting read on {site}: {title}. The implications are worth paying attention to.\n#web3 #{site.title()}",
        f"Been following developments like this closely — {title}. This could shift the landscape.\n#web3 #{site.title()}",
        f"Good timing on this one: {title}. Markets move fast and it pays to stay informed.\n#web3 #{site.title()}",
        f"Caught this from {site}: {title}. Not every headline matters, but this one does.\n#web3 #{site.title()}",
        f"Quick take on {title} — {site} broke it first. Always value the early read.\n#web3 #{site.title()}",
        f"The market always moves on these stories. {title} is no exception.\n#web3 #{site.title()}",
        f"Sharing this from {site}: {title}. Staying ahead of the curve matters more than ever.\n#web3 #{site.title()}",
        f"{title} — reading this made me reconsider my positioning. Always good to have fresh data.\n#web3 #{site.title()}",
    ]
    # Use seed to pick template, rotate based on idx
    tmpl = templates[(idx + seed) % len(templates)]
    return tmpl.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="web3_5_new_run")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    tokens = load_tokens()
    print(f"[tokens] {len(tokens)} available")

    # Load 5 news items
    raw = load_raw_news(5)
    print(f"[news] loaded {len(raw)} raw items")
    for i, r in enumerate(raw):
        print(f"  [{i+1}] {r.get('_site','')}: {(r.get('content','') or '')[:60]}")

    # Load accounts
    accounts = list(csv.DictReader(open(ACCOUNTS_CSV, encoding="utf-8-sig")))
    print(f"[accounts] {len(accounts)} loaded")
    for a in accounts:
        print(f"  {a.get('昵称','?')} {a.get('邮箱','?')}")

    # Build moments: 1 per account, round-robin news
    moments = []
    for i, acct in enumerate(accounts):
        news = raw[i % len(raw)]
        cap = make_caption(news, i, seed=7)
        moments.append({
            "content": cap,
            "visibility": "0",
            "room_id": "",
            "image_urls": "",  # text-only
            "location_name": "", "location_address": "", "location_lat": "", "location_lon": "",
            "_lang": "en",
            "_source": news.get("_site", ""),
            "_dedupe_key": f"web3:{news.get('content','').strip().lower()}",
        })

    moments_csv = wd / f"moments_web3_5_new_{ts}.csv"
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_lang", "_source", "_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow(m)

    print(f"\n[OK] {len(moments)} posts ready")
    for i, m in enumerate(moments):
        acct = accounts[i]
        print(f"  [{i+1}] {acct.get('昵称','?'):20} | {m['content'][:80]}")

    if not args.yes:
        if input("\n  Confirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    # Update dedupe
    dedupe_keys = set()
    for m in moments:
        dk = m.get("_dedupe_key", "")
        if dk.startswith("web3:"):
            dedupe_keys.add(dk[len("web3:"):])
    all_keys = set()
    if DEDUPE_FILE.exists():
        try:
            all_keys = set(json.loads(DEDUPE_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    all_keys |= dedupe_keys
    DEDUPE_FILE.write_text(json.dumps(sorted(all_keys), ensure_ascii=False), encoding="utf-8")

    # Publish
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(ACCOUNTS_CSV),
                "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "2.0",
                "--record-dedupe",
                "--web3-dedupe-file", str(DEDUPE_FILE),
                "--img-dedupe-file", str(ROOT / "data" / "used_slugs.json"),
                "--tokens-out", str(ROOT / args.tokens)]
    if (ROOT / args.tokens).exists():
        cmd += ["--tokens-in", str(ROOT / args.tokens)]

    print("\n=== Publishing ===")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    print(f"Exit code: {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
