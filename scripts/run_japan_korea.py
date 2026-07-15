#!/usr/bin/env python3
"""
run_japan_korea.py — 日韩中内容一键发布（按国家标签自动匹配语言+素材）

覆盖日本、韩国与中国。选择标签后自动：
    1) 从 Pexels + Pixabay 搜索对应国家图片素材
    2) 用该国语言生成文案（语言一致性）
    3) 发布图文帖

支持国家标签（--country）：
    japan       日本       → 日语 (ja)
    korea       韩国       → 韩语 (ko)
    china       中国       → 简体中文 (zh)

用法：
    py -3 scripts/run_japan_korea.py --list-countries
    py -3 scripts/run_japan_korea.py --country japan,korea,china --posts 30 --yes
    py -3 scripts/run_japan_korea.py --country china --accounts-csv accounts_eu_test10.csv --posts 10 --yes
"""
from __future__ import annotations

import argparse
import csv
import io
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

# ============================================================
# 日韩中 国家标签注册表
# ============================================================
COUNTRIES = {
    "japan": {
        "name_en": "Japan",
        "name_local": "日本",
        "lang": "ja",
        "query": "japan tokyo kyoto temple cherry blossom landscape",
        "hashtags": ["#Japan", "#Tokyo", "#日本旅行"],
    },
    "korea": {
        "name_en": "South Korea",
        "name_local": "대한민국",
        "lang": "ko",
        "query": "korea seoul busan hanbok palace landscape",
        "hashtags": ["#Korea", "#Seoul", "#한국여행"],
    },
    "china": {
        "name_en": "China",
        "name_local": "中国",
        "lang": "zh",
        "query": "china beijing shanghai great wall temple landscape",
        "hashtags": ["#China", "#中国旅行", "#风景"],
    },
}


def _run(cmd: list[str], *, env_extra: dict | None = None) -> int:
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Japan/Korea/China publisher (country tag → stock photos → local language caption → publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--country", default="japan",
                    help="国家标签（逗号分隔可多选）。用 --list-countries 查看全部")
    ap.add_argument("--list-countries", action="store_true", help="列出所有支持的国家标签")
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--posts", type=int, default=20, help="要发布的帖子总数")
    ap.add_argument("--per-source", type=int, default=30, help="每个图库最多取图数")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="jpkr_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.list_countries:
        print("日韩中 国家标签：")
        print(f"{'标签':<14} {'国家':<16} {'语言':<6} {'搜索关键词'}")
        print("-" * 75)
        for key, info in COUNTRIES.items():
            print(f"{key:<14} {info['name_en']:<16} {info['lang']:<6} {info['query'][:40]}")
        print(f"\n共 {len(COUNTRIES)} 个国家")
        return 0

    country_keys = [c.strip() for c in args.country.split(",") if c.strip()]
    invalid = [c for c in country_keys if c not in COUNTRIES]
    if invalid:
        print(f"[ERROR] 未知国家标签: {invalid}")
        print(f"可用: {list(COUNTRIES.keys())}")
        return 1

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    state_dir = ROOT / "state"
    state_dir.mkdir(exist_ok=True)

    posts_per_country = args.posts // len(country_keys)
    remainder = args.posts % len(country_keys)

    all_moments_files = []

    for idx, country_key in enumerate(country_keys):
        info = COUNTRIES[country_key]
        n_posts = posts_per_country + (1 if idx < remainder else 0)
        lang = info["lang"]
        query = info["query"]

        print(f"\n{'='*60}")
        print(f"[{country_key.upper()}] {info['name_en']} ({info['name_local']}) | 语言={lang} | 帖数={n_posts}")
        print(f"{'='*60}")

        raw_csv = wd / f"{country_key}_raw_{ts}.csv"
        moments_csv = wd / f"{country_key}_moments_{ts}.csv"

        # Step 1: 采集
        print(f"\n--- Step 1: 采集图片 (query={query}) ---")
        dedupe = state_dir / f"seen_jpkr_{country_key}.json"
        cmd = PY + [str(HERE / "fetch_stock_my.py"),
                    "--sources", "pexels,pixabay",
                    "--query", query,
                    "--per-source", str(args.per_source),
                    "--dedupe-file", str(dedupe),
                    "--output", str(raw_csv)]
        if _run(cmd) != 0 or not raw_csv.exists():
            print(f"[{country_key}] 采集失败，跳过")
            continue

        with open(raw_csv, encoding="utf-8-sig") as f:
            raw_rows = list(csv.DictReader(f))
        if len(raw_rows) < n_posts:
            n_posts = len(raw_rows)

        # 截取
        trimmed_csv = wd / f"{country_key}_trimmed_{ts}.csv"
        with open(raw_csv, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames
            rows = list(reader)[:n_posts]
        with open(trimmed_csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                w.writerow(r)

        # Step 2: 文案改写（使用对应国家语言，保证语言一致性）
        print(f"\n--- Step 2: {lang} 文案改写 ---")
        cmd = PY + [str(HERE / "caption_multilang.py"),
                    "--input", str(trimmed_csv),
                    "--output", str(moments_csv),
                    "--langs", lang]
        if _run(cmd, env_extra={"DEFAULT_SCENE": "travel"}) != 0 or not moments_csv.exists():
            print(f"[{country_key}] 文案改写失败，跳过")
            continue

        all_moments_files.append(moments_csv)
        print(f"[{country_key}] 素材就绪: {n_posts} 帖 | 语言={lang}")

    if not all_moments_files:
        print("\n[ERROR] 没有任何国家素材就绪")
        return 1

    # 合并
    combined = wd / f"jpkr_combined_{ts}.csv"
    all_rows = []
    fieldnames = None
    for mf in all_moments_files:
        with open(mf, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if fieldnames is None:
                fieldnames = reader.fieldnames
            all_rows.extend(list(reader))

    with open(combined, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows:
            w.writerow(r)

    print(f"\n{'='*60}")
    print(f"[JPKR] 合并素材: {len(all_rows)} 帖 → {combined.name}")
    print(f"{'='*60}")

    # Step 2.5: 文案差异化（确保每帖内容不重复）
    print(f"\n--- Step 2.5: 文案差异化 (caption_diversify) ---")
    cmd = PY + [str(HERE / "caption_diversify.py"),
                "--input", str(combined), "--output", str(combined),
                "--lang", "auto", "--scene", "travel"]
    _run(cmd)

    if args.skip_publish:
        print(f"\n--skip-publish 已设置。素材: {combined}")
        return 0

    # Step 3: 发布
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[ERROR] 账号 CSV 不存在: {acc}")
        return 2

    if not args.yes:
        if input(f"  确认发布 {len(all_rows)} 帖？(y/n): ").strip().lower() not in ("y", "yes"):
            return 0

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc),
                "--csv", str(combined),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print(f"[JPKR] 发布返回 {rc}")
        return rc

    print(f"\n[JPKR] 完成！发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
