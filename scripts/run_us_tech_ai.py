#!/usr/bin/env python3
"""
run_us_tech_ai.py — 科技&AI&美国 标签一键发布

从 TechCrunch/The Verge/WIRED/Ars Technica/MIT Tech Review/IEEE Spectrum/
VentureBeat/Argonne/JPL 等9个科技AI媒体采集图文，生成英文配文并发布。

用法：
    py -3 scripts/run_us_tech_ai.py --accounts-csv accounts.csv --per-site 3 --yes
    py -3 scripts/run_us_tech_ai.py --sources techcrunch,wired,mittr --per-site 5 --skip-publish
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

# 英文科技/AI配文模板池
OPENERS = [
    "This is exactly the kind of tech story I live for — ",
    "The AI space is moving faster than ever. ",
    "Another big move in the tech world: ",
    "This development has huge implications for the industry. ",
    "Reading this and trying to wrap my head around what's next. ",
    "Every week there's a new breakthrough that rewrites the playbook. ",
    "The pace of innovation right now is unreal. ",
    "This caught my eye on my morning feed — ",
    "Hard to overstate how significant this could be. ",
    "The intersection of AI and real-world applications keeps expanding. ",
    "Just when you think you've caught up, the landscape shifts again. ",
    "Bookmarking this one — the implications run deep. ",
]

MIDDLES = [
    "The way {source} framed this really puts the impact in perspective. ",
    "What strikes me most is how quickly we went from concept to deployment. ",
    "This is where theory meets practice in the most exciting way. ",
    "The ripple effects of this will be felt across multiple industries. ",
    "It's not just about the tech itself — it's about what it enables next. ",
    "The talent and resources being poured into this space are unprecedented. ",
    "We're witnessing a paradigm shift happening in real time. ",
    "The competitive dynamics here are fascinating to watch unfold. ",
    "What makes this different is the scale and speed of adoption. ",
    "The engineering behind this deserves more appreciation. ",
]

CLOSERS = [
    "The future is being built right now 🚀",
    "Staying sharp in this space means never stopping learning 🧠",
    "Innovation at this pace demands attention 💡",
    "This is why tech remains the most exciting sector 📱",
    "More of this energy in 2026 please ⚡",
    "The builders are winning 🔧",
    "Can't wait to see where this goes next 🎯",
    "Technology as a force multiplier — we're living it 🌐",
]

HASHTAGS = [
    "#Tech #AI #Innovation", "#TechNews #Startup #Future",
    "#ArtificialIntelligence #MachineLearning #DeepTech",
    "#Technology #Engineering #Science", "#AI #Research #Breakthrough",
    "#Innovation #Silicon #Valley", "#TechIndustry #Digital #Transformation",
    "#FutureTech #Computing #Data",
]


def _caption(title: str, site: str, rng: random.Random, seen: set) -> str:
    for _ in range(40):
        opener = rng.choice(OPENERS)
        middle = rng.choice(MIDDLES).format(source=site)
        closer = rng.choice(CLOSERS)
        hashtags = rng.choice(HASHTAGS)
        cap = f"{opener}\"{title}\"\n{middle}{closer}\n#{site.replace(' ','')  } {hashtags}"
        if len(cap) > 300:
            cap = f"{opener}\"{title[:50]}...\"\n{closer}\n#{site.replace(' ','')} {hashtags}"
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
        description="Tech & AI & US one-command publisher",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--sources", default="techcrunch,theverge,wired,arstechnica,mittr,ieee_spectrum,venturebeat,anl,jpl")
    ap.add_argument("--per-site", type=int, default=3)
    ap.add_argument("--posts", type=int, default=0, help="限制帖数（0=全部）")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="us_tech_ai_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw_csv = wd / f"tech_ai_raw_{ts}.csv"
    moments_csv = wd / f"tech_ai_moments_{ts}.csv"

    # Step 1: 采集
    print("\n=== Step 1: Fetch Tech & AI news with images ===")
    cmd = PY + [str(HERE / "fetch_us_tech_ai.py"),
                "--sources", args.sources,
                "--per-site", str(args.per_site),
                "--output", str(raw_csv)]
    if _run(cmd) != 0 or not raw_csv.exists():
        print("[ERROR] fetch failed"); return 1

    # Step 2: 生成配文
    print("\n=== Step 2: Generate English captions ===")
    with open(raw_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if args.posts > 0:
        rows = rows[:args.posts]

    rng = random.Random(int(ts.replace("_", "")))
    seen_caps: set = set()
    # 读取 SITE_INFO 从本地定义避免 import 副作用
    _SITE_NAMES = {
        "techcrunch": "TechCrunch", "theverge": "The Verge", "wired": "WIRED",
        "arstechnica": "Ars Technica", "mittr": "MIT Tech Review",
        "ieee_spectrum": "IEEE Spectrum", "venturebeat": "VentureBeat",
        "anl": "Argonne Nat'l Lab", "jpl": "NASA JPL",
    }
    moments = []
    for r in rows:
        site_key = r.get("_site", "")
        site_name = _SITE_NAMES.get(site_key, site_key)
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
    print(f"[OK] captions unique: {len(seen_caps)}/{len(moments)}")

    if args.skip_publish:
        print(f"\n--skip-publish. Content: {moments_csv}"); return 0

    # Step 3: 发布
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
        print(f"[US_TECH_AI] publish returned {rc}"); return rc
    print(f"\n[US_TECH_AI] Done! Report: result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
