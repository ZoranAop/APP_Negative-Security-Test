#!/usr/bin/env python3
"""
run_arab.py — 阿拉伯国家内容一键发布（按国家标签自动匹配阿拉伯语文案+素材）

覆盖迪拜/阿联酋、沙特等阿拉伯国家。选择标签后自动：
    1) 从 Pexels + Pixabay 搜索对应国家图片素材
    2) 用阿拉伯语(ar)生成文案（语言一致性）
    3) 发布图文帖

支持国家标签（--country）：
    uae           阿联酋(迪拜)  → 阿拉伯语 (ar)
    saudi_arabia  沙特阿拉伯    → 阿拉伯语 (ar)
    qatar         卡塔尔        → 阿拉伯语 (ar)
    kuwait        科威特        → 阿拉伯语 (ar)
    oman          阿曼          → 阿拉伯语 (ar)
    bahrain       巴林          → 阿拉伯语 (ar)
    egypt         埃及          → 阿拉伯语 (ar)
    jordan        约旦          → 阿拉伯语 (ar)
    lebanon       黎巴嫩        → 阿拉伯语 (ar)
    morocco       摩洛哥        → 阿拉伯语 (ar)

用法：
    py -3 scripts/run_arab.py --list-countries
    py -3 scripts/run_arab.py --country uae,saudi_arabia --posts 20 --yes
    py -3 scripts/run_arab.py --country uae --accounts-csv accounts.csv --posts 10 --yes
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
# 阿拉伯国家标签注册表
# ============================================================
COUNTRIES = {
    "uae": {
        "name_en": "UAE",
        "name_local": "الإمارات",
        "lang": "ar",
        "query": "dubai burj khalifa skyline abu dhabi mosque desert",
        "hashtags": ["#الإمارات", "#دبي", "#سفر"],
    },
    "saudi_arabia": {
        "name_en": "Saudi Arabia",
        "name_local": "السعودية",
        "lang": "ar",
        "query": "saudi arabia riyadh mecca mosque desert landscape",
        "hashtags": ["#السعودية", "#الرياض", "#سفر"],
    },
    "qatar": {
        "name_en": "Qatar",
        "name_local": "قطر",
        "lang": "ar",
        "query": "qatar doha skyline pearl museum desert",
        "hashtags": ["#قطر", "#الدوحة", "#سفر"],
    },
    "kuwait": {
        "name_en": "Kuwait",
        "name_local": "الكويت",
        "lang": "ar",
        "query": "kuwait city towers skyline mosque landscape",
        "hashtags": ["#الكويت", "#سفر", "#خليج"],
    },
    "oman": {
        "name_en": "Oman",
        "name_local": "عُمان",
        "lang": "ar",
        "query": "oman muscat mosque sultan qaboos landscape",
        "hashtags": ["#عمان", "#مسقط", "#سفر"],
    },
    "bahrain": {
        "name_en": "Bahrain",
        "name_local": "البحرين",
        "lang": "ar",
        "query": "bahrain manama skyline mosque pearl",
        "hashtags": ["#البحرين", "#المنامة", "#سفر"],
    },
    "egypt": {
        "name_en": "Egypt",
        "name_local": "مصر",
        "lang": "ar",
        "query": "egypt cairo pyramid sphinx nile temple landscape",
        "hashtags": ["#مصر", "#القاهرة", "#سفر"],
    },
    "jordan": {
        "name_en": "Jordan",
        "name_local": "الأردن",
        "lang": "ar",
        "query": "jordan petra dead sea amman desert landscape",
        "hashtags": ["#الأردن", "#البتراء", "#سفر"],
    },
    "lebanon": {
        "name_en": "Lebanon",
        "name_local": "لبنان",
        "lang": "ar",
        "query": "lebanon beirut cedar mountain coast landscape",
        "hashtags": ["#لبنان", "#بيروت", "#سفر"],
    },
    "morocco": {
        "name_en": "Morocco",
        "name_local": "المغرب",
        "lang": "ar",
        "query": "morocco marrakech fes medina sahara landscape",
        "hashtags": ["#المغرب", "#مراكش", "#سفر"],
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
        description="Arab countries publisher (country tag → stock photos → Arabic caption → publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--country", default="uae",
                    help="国家标签（逗号分隔可多选）。用 --list-countries 查看全部")
    ap.add_argument("--list-countries", action="store_true", help="列出所有支持的国家标签")
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--posts", type=int, default=20, help="要发布的帖子总数")
    ap.add_argument("--per-source", type=int, default=30, help="每个图库最多取图数")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="arab_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.list_countries:
        print("阿拉伯 国家标签：")
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
        print(f"[{country_key.upper()}] {info['name_en']} ({info['name_local']}) | lang={lang} | posts={n_posts}")
        print(f"{'='*60}")

        raw_csv = wd / f"{country_key}_raw_{ts}.csv"
        moments_csv = wd / f"{country_key}_moments_{ts}.csv"

        # Step 1: 采集
        print(f"\n--- Step 1: fetch photos (query={query}) ---")
        dedupe = state_dir / f"seen_arab_{country_key}.json"
        cmd = PY + [str(HERE / "fetch_stock_my.py"),
                    "--sources", "pexels,pixabay",
                    "--query", query,
                    "--per-source", str(args.per_source),
                    "--dedupe-file", str(dedupe),
                    "--output", str(raw_csv)]
        if _run(cmd) != 0 or not raw_csv.exists():
            print(f"[{country_key}] fetch failed, skip")
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

        # Step 2: 文案改写（阿拉伯语，保证语言一致性）
        print(f"\n--- Step 2: {lang} caption ---")
        cmd = PY + [str(HERE / "caption_multilang.py"),
                    "--input", str(trimmed_csv),
                    "--output", str(moments_csv),
                    "--langs", lang]
        if _run(cmd, env_extra={"DEFAULT_SCENE": "travel"}) != 0 or not moments_csv.exists():
            print(f"[{country_key}] caption failed, skip")
            continue

        all_moments_files.append(moments_csv)
        print(f"[{country_key}] ready: {n_posts} posts | lang={lang}")

    if not all_moments_files:
        print("\n[ERROR] no content ready")
        return 1

    # 合并
    combined = wd / f"arab_combined_{ts}.csv"
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
    print(f"[ARAB] combined: {len(all_rows)} posts -> {combined.name}")
    print(f"{'='*60}")

    # Step 2.5: 文案差异化
    print(f"\n--- Step 2.5: caption diversify ---")
    cmd = PY + [str(HERE / "caption_diversify.py"),
                "--input", str(combined), "--output", str(combined),
                "--lang", "auto", "--scene", "travel"]
    _run(cmd)

    if args.skip_publish:
        print(f"\n--skip-publish set. content: {combined}")
        return 0

    # Step 3: 发布
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[ERROR] accounts CSV not found: {acc}")
        return 2

    if not args.yes:
        if input(f"  publish {len(all_rows)} posts? (y/n): ").strip().lower() not in ("y", "yes"):
            return 0

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc),
                "--csv", str(combined),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print(f"[ARAB] publish returned {rc}")
        return rc

    print(f"\n[ARAB] done! report: result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
