#!/usr/bin/env python3
"""
run_us_life.py — 美国生活 标签一键发布（USA Today / BuzzFeed / Martha Stewart 图文）

用法：
    py -3 scripts/run_us_life.py --accounts-csv accounts.csv --per-site 5 --yes
    py -3 scripts/run_us_life.py --sources buzzfeed --per-site 10 --skip-publish
"""
from __future__ import annotations

import argparse
import csv
import io
import random
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

OPENERS = [
    "This popped up in my feed and I couldn't scroll past — ",
    "Love stumbling upon content like this. ",
    "Adding this to my \"things to try\" list immediately. ",
    "The internet delivered today. ",
    "This is the kind of content that makes my day better. ",
    "Bookmark-worthy stuff right here — ",
    "Sharing because this genuinely made me smile. ",
    "Okay this is too good not to share. ",
    "My feed just got a whole lot more interesting. ",
    "Lifestyle content done right — ",
    "Found my new weekend inspo. ",
    "This is exactly what I needed to see today. ",
]

MIDDLES = [
    "Sometimes the simplest ideas are the most brilliant. ",
    "It's the little things that make life feel put together. ",
    "Always on the lookout for content that's actually useful. ",
    "The kind of thing you save and actually come back to later. ",
    "Practical, beautiful, and well-timed — what more could you want? ",
    "Life's too short not to enjoy the small pleasures. ",
    "This is giving main character energy in the best way. ",
    "Quality over quantity, always. ",
    "The details here are everything. ",
    "Genuinely inspired to try something new this weekend. ",
]

CLOSERS = [
    "Living my best life, one bookmark at a time ✨",
    "Good vibes only 🌿",
    "Weekend mood activated 🏡",
    "Saving this for later 📌",
    "Life is in the details 💫",
    "Inspired and ready to go 🌟",
    "This is the content I signed up for 👏",
    "Adding to the vision board 🎯",
]

HASHTAGS = [
    "#Lifestyle #Inspo #Daily", "#USLife #Trending #GoodVibes",
    "#Wellness #Living #Aesthetic", "#HomeLife #Tips #MoodBoard",
    "#AmericanLife #Culture #Trending", "#LifeHacks #Style #Weekend",
    "#Inspiration #Content #Living", "#DailyLife #Discover #Vibes",
]


def _caption(title: str, site_name: str, rng: random.Random, seen: set) -> str:
    for _ in range(40):
        opener = rng.choice(OPENERS)
        middle = rng.choice(MIDDLES)
        closer = rng.choice(CLOSERS)
        hashtags = rng.choice(HASHTAGS)
        cap = f"{opener}\"{title}\"\n{middle}{closer}\nvia {site_name} {hashtags}"
        if len(cap) > 300:
            cap = f"{opener}\"{title[:50]}...\"\n{closer}\nvia {site_name} {hashtags}"
        if cap not in seen:
            seen.add(cap)
            return cap
    return f"{rng.choice(OPENERS)}\"{title[:55]}\"\n{rng.choice(CLOSERS)}\n{rng.choice(HASHTAGS)}"


def _run(cmd):
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="US Life one-command publisher (BuzzFeed/USA Today/Martha Stewart)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--sources", default="buzzfeed,usatoday,marthastewart")
    ap.add_argument("--per-site", type=int, default=5)
    ap.add_argument("--posts", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="us_life_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw_csv = wd / f"us_life_raw_{ts}.csv"
    moments_csv = wd / f"us_life_moments_{ts}.csv"

    print("\n=== Step 1: Fetch US Life content ===")
    cmd = PY + [str(HERE / "fetch_us_life.py"),
                "--sources", args.sources,
                "--per-site", str(args.per_site),
                "--output", str(raw_csv)]
    if _run(cmd) != 0 or not raw_csv.exists():
        print("[ERROR] fetch failed"); return 1

    print("\n=== Step 2: Generate English captions ===")
    with open(raw_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if args.posts > 0:
        rows = rows[:args.posts]

    from fetch_us_life import SITE_INFO
    rng = random.Random(int(ts.replace("_", "")))
    seen_caps: set = set()
    moments = []
    for r in rows:
        site_key = r.get("_site", "")
        site_name = SITE_INFO.get(site_key, {}).get("name", site_key)
        cap = _caption(r["content"], site_name, rng, seen_caps)
        moments.append({**r, "content": cap, "_lang": "en"})

    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_lang"]
    with open(moments_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow({k: m.get(k, "") for k in fields})

    print(f"[OK] {len(moments)} posts ready -> {moments_csv.name}")

    if args.skip_publish:
        print(f"\n--skip-publish. Content: {moments_csv}"); return 0

    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[ERROR] accounts not found: {acc}"); return 2
    if not args.yes:
        if input(f"  Publish {len(moments)} posts? (y/n): ").strip().lower() not in ("y", "yes"):
            return 0

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print(f"[US_LIFE] publish returned {rc}"); return rc
    print(f"\n[US_LIFE] Done! Report: result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
