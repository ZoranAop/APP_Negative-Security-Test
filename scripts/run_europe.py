#!/usr/bin/env python3
"""
run_europe.py — 欧洲/英美澳内容一键发布（按国家标签自动匹配语言+素材）

覆盖欧洲主要国家 + 英美澳，共 20 国。选择标签后自动：
    1) 从 Pexels + Pixabay 搜索对应国家图片素材
    2) 用该国语言生成文案（语言一致性）
    3) 发布图文帖

支持国家标签（--country）：
    uk          英国       → 英语 (en)
    usa         美国       → 英语 (en)
    australia   澳大利亚  → 英语 (en)
    germany     德国       → 德语 (de)
    france      法国       → 法语 (fr)
    italy       意大利     → 意大利语 (it)
    spain       西班牙     → 西班牙语 (es)
    portugal    葡萄牙     → 葡萄牙语 (pt)
    netherlands 荷兰       → 荷兰语 (nl)
    switzerland 瑞士       → 德语 (de)
    austria     奥地利     → 德语 (de)
    belgium     比利时     → 法语 (fr)
    sweden      瑞典       → 英语 (en)*
    norway      挪威       → 英语 (en)*
    denmark     丹麦       → 英语 (en)*
    finland     芬兰       → 英语 (en)*
    ireland     爱尔兰     → 英语 (en)
    greece      希腊       → 英语 (en)*
    poland      波兰       → 英语 (en)*
    czechia     捷克       → 英语 (en)*

    * 文案系统暂无该语言模板，使用英语

用法：
    py -3 scripts/run_europe.py --list-countries
    py -3 scripts/run_europe.py --country france,italy,spain --posts 30 --yes
    py -3 scripts/run_europe.py --country germany --accounts-csv accounts_20.csv --posts 20 --yes
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

# ============================================================
# 欧洲 + 英美澳 国家标签注册表
# ============================================================
COUNTRIES = {
    # 英语系
    "uk": {
        "name_en": "United Kingdom",
        "name_local": "United Kingdom",
        "lang": "en",
        "query": "london uk england castle landscape",
        "hashtags": ["#UK", "#London", "#EuropeTravel"],
    },
    "usa": {
        "name_en": "United States",
        "name_local": "United States",
        "lang": "en",
        "query": "new york usa america city landscape",
        "hashtags": ["#USA", "#America", "#Travel"],
    },
    "australia": {
        "name_en": "Australia",
        "name_local": "Australia",
        "lang": "en",
        "query": "australia sydney opera house beach outback",
        "hashtags": ["#Australia", "#Sydney", "#DownUnder"],
    },
    "ireland": {
        "name_en": "Ireland",
        "name_local": "Ireland",
        "lang": "en",
        "query": "ireland dublin green cliff coast",
        "hashtags": ["#Ireland", "#Dublin", "#EuropeTravel"],
    },
    # 德语系
    "germany": {
        "name_en": "Germany",
        "name_local": "Deutschland",
        "lang": "de",
        "query": "germany berlin munich castle landscape",
        "hashtags": ["#Deutschland", "#Germany", "#EuropeTravel"],
    },
    "austria": {
        "name_en": "Austria",
        "name_local": "Österreich",
        "lang": "de",
        "query": "austria vienna alps salzburg landscape",
        "hashtags": ["#Austria", "#Wien", "#EuropeTravel"],
    },
    "switzerland": {
        "name_en": "Switzerland",
        "name_local": "Schweiz",
        "lang": "de",
        "query": "switzerland alps zurich lake mountain",
        "hashtags": ["#Switzerland", "#Schweiz", "#EuropeTravel"],
    },
    # 法语系
    "france": {
        "name_en": "France",
        "name_local": "France",
        "lang": "fr",
        "query": "france paris eiffel tower provence landscape",
        "hashtags": ["#France", "#Paris", "#EuropeTravel"],
    },
    "belgium": {
        "name_en": "Belgium",
        "name_local": "Belgique",
        "lang": "fr",
        "query": "belgium brussels bruges chocolate",
        "hashtags": ["#Belgium", "#Bruxelles", "#EuropeTravel"],
    },
    # 意大利语
    "italy": {
        "name_en": "Italy",
        "name_local": "Italia",
        "lang": "it",
        "query": "italy rome venice florence tuscany",
        "hashtags": ["#Italia", "#Italy", "#EuropeTravel"],
    },
    # 西班牙语
    "spain": {
        "name_en": "Spain",
        "name_local": "España",
        "lang": "es",
        "query": "spain barcelona madrid beach architecture",
        "hashtags": ["#España", "#Spain", "#EuropeTravel"],
    },
    # 葡萄牙语
    "portugal": {
        "name_en": "Portugal",
        "name_local": "Portugal",
        "lang": "pt",
        "query": "portugal lisbon porto beach coast",
        "hashtags": ["#Portugal", "#Lisboa", "#EuropeTravel"],
    },
    # 荷兰语
    "netherlands": {
        "name_en": "Netherlands",
        "name_local": "Nederland",
        "lang": "nl",
        "query": "netherlands amsterdam tulip windmill canal",
        "hashtags": ["#Netherlands", "#Amsterdam", "#EuropeTravel"],
    },
    # 北欧（英语回退）
    "sweden": {
        "name_en": "Sweden",
        "name_local": "Sverige",
        "lang": "en",
        "query": "sweden stockholm northern lights landscape",
        "hashtags": ["#Sweden", "#Stockholm", "#EuropeTravel"],
    },
    "norway": {
        "name_en": "Norway",
        "name_local": "Norge",
        "lang": "en",
        "query": "norway fjord bergen aurora landscape",
        "hashtags": ["#Norway", "#Fjords", "#EuropeTravel"],
    },
    "denmark": {
        "name_en": "Denmark",
        "name_local": "Danmark",
        "lang": "en",
        "query": "denmark copenhagen castle colorful houses",
        "hashtags": ["#Denmark", "#Copenhagen", "#EuropeTravel"],
    },
    "finland": {
        "name_en": "Finland",
        "name_local": "Suomi",
        "lang": "en",
        "query": "finland helsinki aurora lapland snow",
        "hashtags": ["#Finland", "#Helsinki", "#EuropeTravel"],
    },
    # 东欧（英语回退）
    "greece": {
        "name_en": "Greece",
        "name_local": "Ελλάδα",
        "lang": "en",
        "query": "greece santorini athens parthenon island",
        "hashtags": ["#Greece", "#Santorini", "#EuropeTravel"],
    },
    "poland": {
        "name_en": "Poland",
        "name_local": "Polska",
        "lang": "en",
        "query": "poland krakow warsaw old town castle",
        "hashtags": ["#Poland", "#Krakow", "#EuropeTravel"],
    },
    "czechia": {
        "name_en": "Czechia",
        "name_local": "Česko",
        "lang": "en",
        "query": "czech prague castle bridge old town",
        "hashtags": ["#Czechia", "#Prague", "#EuropeTravel"],
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
        description="Europe/Americas/Oceania publisher (country tag → stock photos → local language caption → publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--country", default="france",
                    help="国家标签（逗号分隔可多选）。用 --list-countries 查看全部")
    ap.add_argument("--list-countries", action="store_true", help="列出所有支持的国家标签")
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--posts", type=int, default=20, help="要发布的帖子总数")
    ap.add_argument("--per-source", type=int, default=30, help="每个图库最多取图数")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="europe_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.list_countries:
        print("欧洲/英美澳 国家标签：")
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
        dedupe = state_dir / f"seen_eu_{country_key}.json"
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

        # Step 2: 文案改写
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
    combined = wd / f"europe_combined_{ts}.csv"
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
    print(f"[EUROPE] 合并素材: {len(all_rows)} 帖 → {combined.name}")
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
        print(f"[EUROPE] 发布返回 {rc}")
        return rc

    print(f"\n[EUROPE] 完成！发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
