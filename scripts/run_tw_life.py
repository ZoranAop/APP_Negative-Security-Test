#!/usr/bin/env python3
"""
run_tw_life.py — 台灣生活 標籤一鍵發布

從 Yahoo奇摩/自由時報/聯合報 採集台灣生活圖文，
生成繁體中文第一人稱配文，發布圖文帖。

用法：
    py -3 scripts/run_tw_life.py --accounts-csv accounts.csv --per-site 5 --yes
    py -3 scripts/run_tw_life.py --sources yahoo_life,ltn_life --per-site 8 --skip-publish
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

# 繁體中文台灣生活配文模板
OPENERS = [
    "剛看到這則，覺得很有意思 — ",
    "今天的生活資訊收穫又+1。",
    "這種內容就是要分享出來的！",
    "滑手機看到的，忍不住按了收藏。",
    "台灣的日常總是充滿驚喜。",
    "生活中的小發現，記錄一下。",
    "又學到新東西了，趕緊記下來。",
    "這個話題最近蠻熱的，來聊聊。",
    "看到這個忍不住想分享給大家。",
    "每天都有新鮮事，今天的是這個。",
    "身邊的朋友都在討論這件事。",
    "覺得這個蠻實用的，先存起來。",
]

MIDDLES = [
    "生活就是要多留意這些細節。",
    "有些事情不看新聞還真不知道。",
    "台灣真的什麼有趣的事都有。",
    "這種資訊對日常生活很有幫助。",
    "知道越多，生活品質越高。",
    "有時候一則小新聞就能讓心情變好。",
    "這就是台灣生活的魅力所在。",
    "跟上時事才不會跟社會脫節。",
    "簡單的事情往往最值得關注。",
    "日常中的美好就藏在這些地方。",
]

CLOSERS = [
    "繼續關注生活大小事 ✨", "又是充實的一天 📝",
    "台灣加油 🇹🇼", "分享給需要的人 💫",
    "生活處處是學問 🌟", "保持好奇心最重要 🌿",
    "明天見 ☀️", "一起來討論吧 💬",
]

HASHTAGS = [
    "#台灣 #生活 #日常", "#台灣生活 #資訊 #分享",
    "#生活大小事 #台灣日常 #記錄", "#今日話題 #生活 #台灣",
    "#日常生活 #實用 #台灣人", "#生活情報 #分享日常 #台灣",
    "#台灣新聞 #生活資訊 #有趣", "#每日分享 #台灣 #生活記錄",
]


def _caption(title: str, site_name: str, rng: random.Random, seen: set) -> str:
    for _ in range(40):
        opener = rng.choice(OPENERS)
        middle = rng.choice(MIDDLES)
        closer = rng.choice(CLOSERS)
        hashtags = rng.choice(HASHTAGS)
        cap = f"{opener}「{title[:35]}」\n{middle}\n{closer}\nvia {site_name} {hashtags}"
        if len(cap) > 280:
            cap = f"{opener}「{title[:25]}…」\n{closer}\nvia {site_name} {hashtags}"
        if cap not in seen:
            seen.add(cap)
            return cap
    return f"{rng.choice(OPENERS)}「{title[:30]}」\n{rng.choice(CLOSERS)}\n{rng.choice(HASHTAGS)}"


def _run(cmd):
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Taiwan Life one-command publisher",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--sources", default="yahoo_life,ltn_life,udn_life")
    ap.add_argument("--per-site", type=int, default=5)
    ap.add_argument("--posts", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="tw_life_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw_csv = wd / f"tw_life_raw_{ts}.csv"
    moments_csv = wd / f"tw_life_moments_{ts}.csv"

    print("\n=== Step 1: 採集台灣生活圖文 ===")
    cmd = PY + [str(HERE / "fetch_tw_life.py"),
                "--sources", args.sources,
                "--per-site", str(args.per_site),
                "--output", str(raw_csv)]
    if _run(cmd) != 0 or not raw_csv.exists():
        print("[ERROR] fetch failed"); return 1

    print("\n=== Step 2: 生成繁體中文配文 ===")
    with open(raw_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if args.posts > 0:
        rows = rows[:args.posts]

    _SITE_NAMES = {"yahoo_life": "Yahoo奇摩", "ltn_life": "自由時報", "udn_life": "聯合報"}
    rng = random.Random(int(ts.replace("_", "")))
    seen_caps: set = set()
    moments = []
    for r in rows:
        site_key = r.get("_site", "")
        site_name = _SITE_NAMES.get(site_key, site_key)
        cap = _caption(r["content"], site_name, rng, seen_caps)
        moments.append({**r, "content": cap, "_lang": "zh_hant"})

    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_lang", "_media_type"]
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
        if input(f"  發布 {len(moments)} 帖？(y/n): ").strip().lower() not in ("y", "yes"):
            return 0

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print(f"[TW_LIFE] publish returned {rc}"); return rc
    print(f"\n[TW_LIFE] 完成！報告: result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
