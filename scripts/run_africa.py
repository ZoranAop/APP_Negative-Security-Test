#!/usr/bin/env python3
"""
run_africa.py — 非洲内容一键发布（按国家标签自动匹配语言+素材）

覆盖非洲主要国家，共 20 国。选择标签后自动：
    1) 从 Pexels + Pixabay 搜索对应国家图片素材
    2) 用该国语言生成文案（语言一致性）
    3) 发布图文帖

支持国家标签（--country）：
    south_africa  南非       → 英语 (en)
    egypt         埃及       → 英语 (en)*
    morocco       摩洛哥     → 法语 (fr)
    kenya         肯尼亚     → 英语 (en)
    tanzania      坦桑尼亚   → 英语 (en)
    nigeria       尼日利亚   → 英语 (en)
    ghana         加纳       → 英语 (en)
    ethiopia      埃塞俄比亚 → 英语 (en)
    senegal       塞内加尔   → 法语 (fr)
    tunisia       突尼斯     → 法语 (fr)
    algeria       阿尔及利亚 → 法语 (fr)
    ivory_coast   科特迪瓦   → 法语 (fr)
    cameroon      喀麦隆     → 法语 (fr)
    madagascar    马达加斯加 → 法语 (fr)
    mozambique    莫桑比克   → 葡萄牙语 (pt)
    angola        安哥拉     → 葡萄牙语 (pt)
    namibia       纳米比亚   → 英语 (en)
    zimbabwe      津巴布韦   → 英语 (en)
    uganda        乌干达     → 英语 (en)
    rwanda        卢旺达     → 英语 (en)

    * 阿拉伯语暂无模板，回退英语

用法：
    py -3 scripts/run_africa.py --list-countries
    py -3 scripts/run_africa.py --country kenya,tanzania,south_africa --posts 30 --yes
    py -3 scripts/run_africa.py --country morocco,senegal,tunisia --posts 20 --yes
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
# 非洲国家标签注册表
# ============================================================
COUNTRIES = {
    # 英语系（东非+南非+西非英语区）
    "south_africa": {
        "name_en": "South Africa",
        "name_local": "South Africa",
        "lang": "en",
        "query": "south africa cape town safari landscape table mountain",
        "hashtags": ["#SouthAfrica", "#CapeTown", "#AfricaTravel"],
    },
    "kenya": {
        "name_en": "Kenya",
        "name_local": "Kenya",
        "lang": "en",
        "query": "kenya safari nairobi masai mara wildlife",
        "hashtags": ["#Kenya", "#Safari", "#AfricaTravel"],
    },
    "tanzania": {
        "name_en": "Tanzania",
        "name_local": "Tanzania",
        "lang": "en",
        "query": "tanzania serengeti kilimanjaro zanzibar safari",
        "hashtags": ["#Tanzania", "#Serengeti", "#AfricaTravel"],
    },
    "nigeria": {
        "name_en": "Nigeria",
        "name_local": "Nigeria",
        "lang": "en",
        "query": "nigeria lagos city market culture",
        "hashtags": ["#Nigeria", "#Lagos", "#AfricaTravel"],
    },
    "ghana": {
        "name_en": "Ghana",
        "name_local": "Ghana",
        "lang": "en",
        "query": "ghana accra cape coast castle beach",
        "hashtags": ["#Ghana", "#Accra", "#AfricaTravel"],
    },
    "ethiopia": {
        "name_en": "Ethiopia",
        "name_local": "ኢትዮጵያ",
        "lang": "en",
        "query": "ethiopia addis ababa lalibela church landscape",
        "hashtags": ["#Ethiopia", "#Lalibela", "#AfricaTravel"],
    },
    "namibia": {
        "name_en": "Namibia",
        "name_local": "Namibia",
        "lang": "en",
        "query": "namibia desert dunes sossusvlei safari",
        "hashtags": ["#Namibia", "#Sossusvlei", "#AfricaTravel"],
    },
    "zimbabwe": {
        "name_en": "Zimbabwe",
        "name_local": "Zimbabwe",
        "lang": "en",
        "query": "zimbabwe victoria falls landscape safari",
        "hashtags": ["#Zimbabwe", "#VictoriaFalls", "#AfricaTravel"],
    },
    "uganda": {
        "name_en": "Uganda",
        "name_local": "Uganda",
        "lang": "en",
        "query": "uganda gorilla kampala lake victoria nature",
        "hashtags": ["#Uganda", "#Gorilla", "#AfricaTravel"],
    },
    "rwanda": {
        "name_en": "Rwanda",
        "name_local": "Rwanda",
        "lang": "en",
        "query": "rwanda kigali gorilla trekking green hills",
        "hashtags": ["#Rwanda", "#Kigali", "#AfricaTravel"],
    },
    "egypt": {
        "name_en": "Egypt",
        "name_local": "مصر",
        "lang": "en",  # 阿拉伯语回退英语
        "query": "egypt pyramids cairo nile temple sphinx",
        "hashtags": ["#Egypt", "#Pyramids", "#AfricaTravel"],
    },
    # 法语系（北非+西非法语区）
    "morocco": {
        "name_en": "Morocco",
        "name_local": "المغرب / Maroc",
        "lang": "fr",
        "query": "morocco marrakech sahara desert medina fes",
        "hashtags": ["#Maroc", "#Marrakech", "#AfricaTravel"],
    },
    "senegal": {
        "name_en": "Senegal",
        "name_local": "Sénégal",
        "lang": "fr",
        "query": "senegal dakar beach gorée island baobab",
        "hashtags": ["#Sénégal", "#Dakar", "#AfricaTravel"],
    },
    "tunisia": {
        "name_en": "Tunisia",
        "name_local": "Tunisie",
        "lang": "fr",
        "query": "tunisia tunis carthage sahara sidi bou said",
        "hashtags": ["#Tunisie", "#Tunis", "#AfricaTravel"],
    },
    "algeria": {
        "name_en": "Algeria",
        "name_local": "Algérie",
        "lang": "fr",
        "query": "algeria sahara casbah tassili landscape",
        "hashtags": ["#Algérie", "#Sahara", "#AfricaTravel"],
    },
    "ivory_coast": {
        "name_en": "Ivory Coast",
        "name_local": "Côte d'Ivoire",
        "lang": "fr",
        "query": "ivory coast abidjan basilica yamoussoukro beach",
        "hashtags": ["#CôtedIvoire", "#Abidjan", "#AfricaTravel"],
    },
    "cameroon": {
        "name_en": "Cameroon",
        "name_local": "Cameroun",
        "lang": "fr",
        "query": "cameroon douala yaoundé mount cameroon nature",
        "hashtags": ["#Cameroun", "#Douala", "#AfricaTravel"],
    },
    "madagascar": {
        "name_en": "Madagascar",
        "name_local": "Madagascar",
        "lang": "fr",
        "query": "madagascar lemur baobab rainforest island beach",
        "hashtags": ["#Madagascar", "#Baobab", "#AfricaTravel"],
    },
    # 葡萄牙语系
    "mozambique": {
        "name_en": "Mozambique",
        "name_local": "Moçambique",
        "lang": "pt",
        "query": "mozambique maputo beach island bazaruto",
        "hashtags": ["#Moçambique", "#Maputo", "#AfricaTravel"],
    },
    "angola": {
        "name_en": "Angola",
        "name_local": "Angola",
        "lang": "pt",
        "query": "angola luanda kalandula falls coast landscape",
        "hashtags": ["#Angola", "#Luanda", "#AfricaTravel"],
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
        description="Africa publisher (country tag → stock photos → local language caption → publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--country", default="south_africa",
                    help="国家标签（逗号分隔可多选）。用 --list-countries 查看全部")
    ap.add_argument("--list-countries", action="store_true", help="列出所有支持的国家标签")
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--posts", type=int, default=20, help="要发布的帖子总数")
    ap.add_argument("--per-source", type=int, default=30, help="每个图库最多取图数")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="africa_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.list_countries:
        print("非洲国家标签：")
        print(f"{'标签':<14} {'国家':<16} {'语言':<6} {'搜索关键词'}")
        print("-" * 75)
        for key, info in COUNTRIES.items():
            print(f"{key:<14} {info['name_en']:<16} {info['lang']:<6} {info['query'][:40]}")
        print(f"\n共 {len(COUNTRIES)} 个国家")
        print(f"\n语言分布: 英语(en)={sum(1 for v in COUNTRIES.values() if v['lang']=='en')}, "
              f"法语(fr)={sum(1 for v in COUNTRIES.values() if v['lang']=='fr')}, "
              f"葡萄牙语(pt)={sum(1 for v in COUNTRIES.values() if v['lang']=='pt')}")
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
        print(f"\n--- Step 1: 采集图片 (query={query[:50]}) ---")
        dedupe = state_dir / f"seen_af_{country_key}.json"
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
    combined = wd / f"africa_combined_{ts}.csv"
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
    print(f"[AFRICA] 合并素材: {len(all_rows)} 帖 → {combined.name}")
    print(f"{'='*60}")

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
        print(f"[AFRICA] 发布返回 {rc}")
        return rc

    print(f"\n[AFRICA] 完成！发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
