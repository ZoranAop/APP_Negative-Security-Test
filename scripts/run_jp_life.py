#!/usr/bin/env python3
"""
run_jp_life.py — 日本生活 標籤一鍵發布

从 grape/hint-pot/Pouch/macaroni/TRILL 采集日本生活图文，
生成日语第一人称配文，发布图文帖。

用法：
    py -3 scripts/run_jp_life.py --accounts-csv accounts.csv --per-site 5 --yes
    py -3 scripts/run_jp_life.py --sources grapee,hintpot,youpouch --per-site 8 --skip-publish
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

# 日本語配文テンプレート（第一人称シェアスタイル）
OPENERS = [
    "これ気になって読んじゃった — ",
    "今日見つけた中で一番テンション上がったやつ。",
    "こういう記事大好きなんだよね。",
    "ちょっとこれ見て！すごく良かった。",
    "暮らしのヒントがまた一つ増えた気がする。",
    "思わずブックマークしちゃった。",
    "今週の「へぇ〜」ポイント。",
    "誰かに教えたくなる系の情報。",
    "こういうの知ると毎日がちょっと楽しくなる。",
    "ネットサーフィンの成果がこちら。",
    "読み物として純粋に面白かった。",
    "日常が少し豊かになるTips。",
]

MIDDLES = [
    "知らなかったことって意外と多いなって実感する。",
    "細かいところにこだわるのって結局大事だよね。",
    "こういう情報、もっと早く知りたかった。",
    "実際にやってみたくなるクオリティ。",
    "日本ならではの感性が詰まってる。",
    "何気ない日常が特別になる瞬間。",
    "丁寧に暮らすってこういうことかも。",
    "季節を感じながら過ごす贅沢。",
    "シンプルだけど、奥が深い。",
    "こういうのを「いい情報」って言うんだろうな。",
]

CLOSERS = [
    "暮らしのアップデート完了 ✨", "また一つ賢くなった気分 📝",
    "週末やってみよう 🌿", "保存して後で読み返す 📌",
    "生活の質、じわじわ上がってる 💫", "こういうの集めるの好き 🎯",
    "明日からちょっと変わりそう 🌟", "いい一日のスタート ☀️",
]

HASHTAGS = [
    "#暮らし #日常 #ライフスタイル", "#生活の知恵 #日本 #情報",
    "#丁寧な暮らし #毎日 #発見", "#ライフハック #日常生活 #おすすめ",
    "#暮らしを楽しむ #日本文化 #季節", "#生活 #インスピレーション #シェア",
    "#今日の一品 #おうち時間 #リラックス", "#日本の暮らし #トレンド #気になる",
]


def _caption(title: str, site_name: str, rng: random.Random, seen: set) -> str:
    for _ in range(40):
        opener = rng.choice(OPENERS)
        middle = rng.choice(MIDDLES)
        closer = rng.choice(CLOSERS)
        hashtags = rng.choice(HASHTAGS)
        cap = f"{opener}「{title[:40]}」\n{middle}\n{closer}\nvia {site_name} {hashtags}"
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
        description="Japan Life one-command publisher (grape/hint-pot/Pouch/macaroni/TRILL)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--sources", default="grapee,hintpot,youpouch")
    ap.add_argument("--per-site", type=int, default=5)
    ap.add_argument("--posts", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="jp_life_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw_csv = wd / f"jp_life_raw_{ts}.csv"
    moments_csv = wd / f"jp_life_moments_{ts}.csv"

    print("\n=== Step 1: 日本生活メディアから図文取得 ===")
    cmd = PY + [str(HERE / "fetch_jp_life.py"),
                "--sources", args.sources,
                "--per-site", str(args.per_site),
                "--output", str(raw_csv)]
    if _run(cmd) != 0 or not raw_csv.exists():
        print("[ERROR] fetch failed"); return 1

    print("\n=== Step 2: 日本語配文生成 ===")
    with open(raw_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if args.posts > 0:
        rows = rows[:args.posts]

    _SITE_NAMES = {"grapee": "grape", "hintpot": "hint-pot", "youpouch": "Pouch",
                   "macaroni": "macaroni", "trilltrill": "TRILL"}
    rng = random.Random(int(ts.replace("_", "")))
    seen_caps: set = set()
    moments = []
    for r in rows:
        site_key = r.get("_site", "")
        site_name = _SITE_NAMES.get(site_key, site_key)
        cap = _caption(r["content"], site_name, rng, seen_caps)
        moments.append({**r, "content": cap, "_lang": "ja"})

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
        if input(f"  {len(moments)}件を発布しますか？ (y/n): ").strip().lower() not in ("y", "yes"):
            return 0

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print(f"[JP_LIFE] publish returned {rc}"); return rc
    print(f"\n[JP_LIFE] 完了！レポート: result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
