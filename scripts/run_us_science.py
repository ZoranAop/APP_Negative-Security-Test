#!/usr/bin/env python3
"""
run_us_science.py — 科学&美国 标签一键发布（6个美国科学机构图文）

从 NASA/NSF/NIST/Energy/NOAA/NIH 采集最新科学图文新闻，
生成英文第一人称配文（150-300字符），发布图文帖。

用法：
    py -3 scripts/run_us_science.py --accounts-csv accounts.csv --posts 10 --yes
    py -3 scripts/run_us_science.py --per-site 5 --skip-publish
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

# Ensure UTF-8 stdout on Windows
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

# 英文科学配文模板（第一人称分享风格，150-300字符）
OPENERS = [
    "Just came across this and had to share — ",
    "Science never stops surprising me. ",
    "This caught my attention today: ",
    "Another reminder of how much we're still discovering. ",
    "Fascinating development from the scientific community: ",
    "The more I read about this, the more impressed I am. ",
    "Always amazed by what researchers are uncovering. ",
    "This is exactly the kind of progress that matters. ",
    "Reading about this made my day a little more hopeful. ",
    "Can't help but share this — pure science at its best. ",
]

MIDDLES = [
    "The implications of this research could reshape how we understand {topic}. ",
    "It's incredible to think about the years of work behind a discovery like this. ",
    "This kind of work reminds us that curiosity is humanity's greatest asset. ",
    "Every breakthrough starts with a question someone refused to stop asking. ",
    "The dedication of these researchers deserves more recognition. ",
    "Science moves forward one discovery at a time, and this is a big one. ",
    "What excites me most is the potential applications down the road. ",
    "The intersection of technology and science keeps producing incredible results. ",
    "Moments like these make you appreciate the scientific method even more. ",
    "This perfectly illustrates why continued investment in research matters. ",
]

CLOSERS = [
    "The future is being built in labs and observatories right now ✨",
    "Keep pushing boundaries 🔬",
    "Science — always worth paying attention to 📡",
    "Grateful for the minds working on this 🧬",
    "One step closer to understanding our universe 🌍",
    "This is why I love following science news 🚀",
]

HASHTAGS = [
    "#Science #Research #Discovery", "#NASA #Space #Innovation",
    "#ScienceMatters #Technology #Future", "#Research #Breakthrough #STEM",
    "#USScience #Innovation #Progress", "#SciComm #Discovery #Knowledge",
]


def _generate_caption(title: str, site: str, rng: random.Random, seen: set) -> str:
    """基于标题生成独立英文配文（150-300字符）。"""
    # 提取topic关键词
    topic = title[:40].lower().rstrip(".")

    for _ in range(30):
        opener = rng.choice(OPENERS)
        middle = rng.choice(MIDDLES).format(topic=topic)
        closer = rng.choice(CLOSERS)
        hashtags = rng.choice(HASHTAGS)

        cap = f"{opener}\"{title}\"\n{middle}{closer}\n#{site.upper()} {hashtags}"

        if len(cap) > 300:
            cap = f"{opener}\"{title[:50]}...\"\n{closer}\n#{site.upper()} {hashtags}"

        if cap not in seen:
            seen.add(cap)
            return cap

    return f"{rng.choice(OPENERS)}\"{title[:60]}\"\n{rng.choice(CLOSERS)}\n#{site.upper()} {rng.choice(HASHTAGS)}"


def _run(cmd: list[str]) -> int:
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="US Science publisher (NASA/NSF/NIST/Energy/NOAA/NIH → English image+text posts)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--sources", default="nasa,nsf,nist,energy",
                    help="采集来源（逗号分隔）")
    ap.add_argument("--per-site", type=int, default=3)
    ap.add_argument("--posts", type=int, default=0, help="发布帖数（0=全部）")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="us_science_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    raw_csv = wd / f"us_science_raw_{ts}.csv"
    moments_csv = wd / f"us_science_moments_{ts}.csv"

    # Step 1: 采集
    print("\n=== Step 1: 采集美国科学机构图文 ===")
    cmd = PY + [str(HERE / "fetch_us_science.py"),
                "--sources", args.sources,
                "--per-site", str(args.per_site),
                "--output", str(raw_csv)]
    if _run(cmd) != 0 or not raw_csv.exists():
        print("[ERROR] 采集失败")
        return 1

    # Step 2: 生成配文
    print("\n=== Step 2: 生成英文配文 ===")
    with open(raw_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if args.posts > 0:
        rows = rows[:args.posts]

    rng = random.Random(int(ts.replace("_", "")))
    seen_caps: set = set()
    moments = []
    for r in rows:
        cap = _generate_caption(r["content"], r.get("_site", "science"), rng, seen_caps)
        moments.append({
            "content": cap,
            "image_urls": r["image_urls"],
            "_source": r.get("_source", "us_science"),
            "_site": r.get("_site", ""),
            "_lang": "en",
        })

    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_lang"]
    with open(moments_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow({
                "content": m["content"], "visibility": "0", "room_id": "",
                "image_urls": m["image_urls"],
                "location_name": "", "location_address": "",
                "location_lat": "", "location_lon": "",
                "_source": m["_source"], "_site": m["_site"], "_lang": m["_lang"],
            })

    print(f"[OK] {len(moments)} posts ready → {moments_csv.name}")
    print(f"[OK] captions unique: {len(seen_caps)}/{len(moments)}")

    if args.skip_publish:
        print(f"\n--skip-publish. Content: {moments_csv}")
        return 0

    # Step 3: 发布
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[ERROR] accounts CSV not found: {acc}")
        return 2

    if not args.yes:
        if input(f"  Publish {len(moments)} posts? (y/n): ").strip().lower() not in ("y", "yes"):
            return 0

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc),
                "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print(f"[US_SCIENCE] publish returned {rc}")
        return rc

    print(f"\n[US_SCIENCE] Done! Report: result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
