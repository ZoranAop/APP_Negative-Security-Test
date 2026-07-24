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
import re as _re
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

# ---------------------------------------------------------------------------
# 来源过滤（与 run_tech.py strip_source_attribution 对齐）
# ---------------------------------------------------------------------------
_KNOWN_SITES = {"BuzzFeed", "USA Today", "Martha Stewart", "buzzfeed", "usatoday", "marthastewart"}


def strip_source_attribution(text: str) -> str:
    """Remove all source/attribution marks so the post looks user-original."""
    if not text:
        return text
    # 1. Parenthesized source
    text = _re.sub(r'[（(]\s*[來来]源\s*[:：]?\s*[^）)]+[）)]', '', text)
    # 2. via/source in parens
    text = _re.sub(r'\(\s*(?:via|source|sumber)\s*[:：]?\s*[^)]+\)', '', text)
    # 3/4. Bracket prefixes with known sites
    _escaped = [_re.escape(n) for n in _KNOWN_SITES if n]
    if _escaped:
        _pat = '|'.join(sorted(_escaped, key=len, reverse=True))
        text = _re.sub(r'\[(?:' + _pat + r')\]\s*', '', text)
        # 5. Inline via + site name
        text = _re.sub(r'(?:via|source|from)\s*[:：]?\s*(?:' + _pat + r')', '', text, flags=_re.IGNORECASE)
        # 6. reported by / courtesy of
        text = _re.sub(r'(?:reported by|courtesy of)\s+(?:' + _pat + r')', '', text, flags=_re.IGNORECASE)
    # 7. Cleanup
    text = _re.sub(r'[ \t]{2,}', ' ', text)
    text = _re.sub(r'[（(]\s*[）)]', '', text)
    text = _re.sub(r'\[\s*\]', '', text)
    text = _re.sub(r'^\s*[,.\-—;:]+\s*', '', text)
    text = _re.sub(r' {2,}', ' ', text)
    return text.strip()


# 语言标签（与 run_tech.py LANG_TAG 对齐）
LANG_TAG = "#Lifestyle"

# English pure-descriptive first-person templates
# ★ Format: {title}, <reaction> {tag} ★
# ★ Forbidden: "title", via, source names, decorative symbols ★
TEMPLATES = [
    "{title}, this popped up in my feed and I couldn't scroll past {tag}",
    "{title}, love stumbling upon content like this {tag}",
    "{title}, adding this to my things-to-try list {tag}",
    "{title}, the internet delivered today {tag}",
    "{title}, this made my day better {tag}",
    "{title}, bookmark-worthy stuff right here {tag}",
    "{title}, sharing because this genuinely made me smile {tag}",
    "{title}, too good not to share {tag}",
    "{title}, my feed just got more interesting {tag}",
    "{title}, lifestyle content done right {tag}",
    "{title}, found my new weekend inspo {tag}",
    "{title}, exactly what I needed to see today {tag}",
    "{title}, sometimes the simplest ideas are the most brilliant {tag}",
    "{title}, the little things that make life feel put together {tag}",
    "{title}, genuinely inspired to try something new {tag}",
    "{title}, quality over quantity always {tag}",
    "{title}, the details here are everything {tag}",
    "{title}, saving this for later {tag}",
]


def _caption(title: str, site_name: str, rng: random.Random, seen: set) -> str:
    # Layer 1: strip source from title itself
    title = strip_source_attribution(title)
    for _ in range(40):
        tpl = rng.choice(TEMPLATES)
        cap = tpl.format(title=title[:60], tag=LANG_TAG)
        # Layer 2: final caption cleanup
        cap = strip_source_attribution(cap)
        if len(cap) > 300:
            cap = tpl.format(title=title[:45], tag=LANG_TAG)
            cap = strip_source_attribution(cap)
        if cap not in seen:
            seen.add(cap)
            return cap
    base = TEMPLATES[0].format(title=title[:50], tag=LANG_TAG)
    return strip_source_attribution(base)


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
