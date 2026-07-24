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
_KNOWN_SITES = {"grape", "hint-pot", "Pouch", "macaroni", "TRILL",
                "grapee", "hintpot", "youpouch", "trilltrill"}


def strip_source_attribution(text: str) -> str:
    """来源/出処標記をすべて除去し、ユーザーオリジナル投稿に見せる。"""
    if not text:
        return text
    # 1. 中文圆括号来源（万一标题带中文来源）
    text = _re.sub(r'[（(]\s*[來来]源\s*[:：]?\s*[^）)]+[）)]', '', text)
    # 2. 英文/日文圆括号 via/source/出典
    text = _re.sub(r'\(\s*(?:via|source|出典)\s*[:：]?\s*[^)]+\)', '', text)
    # 3/4. 方括号前缀
    _escaped = [_re.escape(n) for n in _KNOWN_SITES if n]
    if _escaped:
        _pat = '|'.join(sorted(_escaped, key=len, reverse=True))
        text = _re.sub(r'【(?:' + _pat + r')(?:速報|ニュース)?】', '', text)
        text = _re.sub(r'\[(?:' + _pat + r')\]\s*', '', text)
        # 5. 行内 via/出典 + 站名
        text = _re.sub(r'(?:出典|via|來源|来源)\s*[:：]?\s*(?:' + _pat + r')', '', text)
        # 6. 引述
        text = _re.sub(r'(?:' + _pat + r')\s*(?:より|から|報道|レポート)', '', text)
    # 7. 清理残留
    text = _re.sub(r'[ \t]{2,}', ' ', text)
    text = _re.sub(r'[（(]\s*[）)]', '', text)
    text = _re.sub(r'【\s*】', '', text)
    text = _re.sub(r'\[\s*\]', '', text)
    text = _re.sub(r'^\s*[，,。.、；;：:—\-]+\s*', '', text)
    text = _re.sub(r' {2,}', ' ', text)
    return text.strip()


# 語言標籤（與 run_tech.py LANG_TAG 對齊）
LANG_TAG = "#暮らし"

# 日本語純描述第一人称テンプレート
# ★ 形式：{title}、<感想> {tag} ★
# ★ 禁止：「」【】via 出典 サイト名 等の装飾/出典マーク ★
TEMPLATES = [
    "{title}、気になって読んじゃった {tag}",
    "{title}、今日見つけた中で一番テンション上がった {tag}",
    "{title}、こういう記事大好き {tag}",
    "{title}、すごく良かったので共有 {tag}",
    "{title}、暮らしのヒントがまた増えた {tag}",
    "{title}、思わずブックマークした {tag}",
    "{title}、今週のへぇポイント {tag}",
    "{title}、誰かに教えたくなる情報 {tag}",
    "{title}、知ると毎日がちょっと楽しくなる {tag}",
    "{title}、ネットサーフィンの成果 {tag}",
    "{title}、読み物として純粋に面白い {tag}",
    "{title}、日常が少し豊かになるヒント {tag}",
    "{title}、知らなかったことって意外と多い {tag}",
    "{title}、実際にやってみたくなる {tag}",
    "{title}、日本ならではの感性が詰まってる {tag}",
    "{title}、何気ない日常が特別になる瞬間 {tag}",
    "{title}、丁寧に暮らすってこういうことかも {tag}",
    "{title}、シンプルだけど奥が深い {tag}",
]


def _caption(title: str, site_name: str, rng: random.Random, seen: set) -> str:
    # 第1層：タイトル自体の出典除去
    title = strip_source_attribution(title)
    for _ in range(40):
        tpl = rng.choice(TEMPLATES)
        cap = tpl.format(title=title[:40], tag=LANG_TAG)
        # 第2層：最終キャプション兜底フィルタ
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
