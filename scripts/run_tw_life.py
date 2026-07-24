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
_KNOWN_SITES = {"Yahoo奇摩", "自由時報", "聯合報", "yahoo_life", "ltn_life", "udn_life"}


def strip_source_attribution(text: str) -> str:
    """移除所有来源/出处标注，使文案呈现为用户原创分享。"""
    if not text:
        return text
    # 1. 中文圆括号来源
    text = _re.sub(r'[（(]\s*[來来]源\s*[:：]?\s*[^）)]+[）)]', '', text)
    # 2. 英文圆括号 via/source
    text = _re.sub(r'\(\s*(?:via|source|sumber)\s*[:：]?\s*[^)]+\)', '', text)
    # 3. 中文方括号前缀
    _escaped = [_re.escape(n) for n in _KNOWN_SITES if n]
    if _escaped:
        _pat = '|'.join(sorted(_escaped, key=len, reverse=True))
        text = _re.sub(r'【(?:' + _pat + r')(?:快訊|快讯|消息)?】', '', text)
        text = _re.sub(r'\[(?:' + _pat + r')\]\s*', '', text)
        # 5. 行内 via/來源 + 站名
        text = _re.sub(r'(?:來源|来源|via)\s*[:：]?\s*(?:' + _pat + r')', '', text)
        # 6. 引述短语
        text = _re.sub(r'摘自\s*(?:' + _pat + r')', '', text)
        text = _re.sub(r'(?:' + _pat + r')\s*(?:報導|报道|消息)', '', text)
        text = _re.sub(r'[据據]\s*(?:' + _pat + r')\s*(?:報導|报道|消息)?[,，]?\s*', '', text)
    # 7. 清理残留
    text = _re.sub(r'[ \t]{2,}', ' ', text)
    text = _re.sub(r'[（(]\s*[）)]', '', text)
    text = _re.sub(r'【\s*】', '', text)
    text = _re.sub(r'\[\s*\]', '', text)
    text = _re.sub(r'^\s*[，,。.、；;：:—\-]+\s*', '', text)
    text = _re.sub(r' {2,}', ' ', text)
    return text.strip()


# 語言標籤（與 run_tech.py LANG_TAG 對齊）
LANG_TAG = "#台灣生活"

# 繁體中文純描述第一人稱模板
# ★ 格式：{title}，<感受> {tag} ★
# ★ 禁止：「」【】via 來源 站名 等裝飾性/來源標記 ★
TEMPLATES = [
    "{title}，剛看到覺得很有意思 {tag}",
    "{title}，今天的生活資訊收穫又多了一條 {tag}",
    "{title}，這種內容就是要分享出來的 {tag}",
    "{title}，滑手機看到忍不住存下來 {tag}",
    "{title}，台灣的日常總是充滿驚喜 {tag}",
    "{title}，生活中的小發現值得記錄 {tag}",
    "{title}，又學到新東西了 {tag}",
    "{title}，這話題最近蠻熱的 {tag}",
    "{title}，看到忍不住想分享給大家 {tag}",
    "{title}，每天都有新鮮事 {tag}",
    "{title}，身邊朋友都在討論 {tag}",
    "{title}，覺得蠻實用的先存起來 {tag}",
    "{title}，生活就是要多留意這些細節 {tag}",
    "{title}，有些事不看真不知道 {tag}",
    "{title}，這對日常生活很有幫助 {tag}",
    "{title}，知道越多生活品質越高 {tag}",
    "{title}，簡單的事往往最值得關注 {tag}",
    "{title}，日常中的美好就藏在這些地方 {tag}",
]


def _caption(title: str, site_name: str, rng: random.Random, seen: set) -> str:
    # 第一層過濾：標題本身的來源標註
    title = strip_source_attribution(title)
    for _ in range(40):
        tpl = rng.choice(TEMPLATES)
        cap = tpl.format(title=title[:40], tag=LANG_TAG)
        # 第二層過濾：最終文案兜底
        cap = strip_source_attribution(cap)
        if len(cap) > 280:
            cap = tpl.format(title=title[:25], tag=LANG_TAG)
            cap = strip_source_attribution(cap)
        if cap not in seen:
            seen.add(cap)
            return cap
    base = TEMPLATES[0].format(title=title[:30], tag=LANG_TAG)
    return strip_source_attribution(base)


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
