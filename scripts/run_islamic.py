#!/usr/bin/env python3
"""
run_islamic.py — 伊斯兰国家内容一键发布（按国家标签自动匹配语言+素材）

覆盖主要伊斯兰国家，共 20 国。选择标签后自动：
    1) 从 Pexels + Pixabay 搜索对应国家图片素材
    2) 用该国语言生成文案（语言一致性）
    3) 发布图文帖

支持国家标签（--country）：
    中东地区：
      saudi_arabia  沙特阿拉伯 → 英语 (en)*
      uae           阿联酋     → 英语 (en)*
      qatar         卡塔尔     → 英语 (en)*
      kuwait        科威特     → 英语 (en)*
      oman          阿曼       → 英语 (en)*
      bahrain       巴林       → 英语 (en)*
      jordan        约旦       → 英语 (en)*
      iraq          伊拉克     → 英语 (en)*
      iran          伊朗       → 英语 (en)*
      yemen         也门       → 英语 (en)*
    中亚/南亚：
      pakistan      巴基斯坦   → 英语 (en)
      bangladesh    孟加拉国   → 英语 (en)
      afghanistan   阿富汗     → 英语 (en)*
      uzbekistan    乌兹别克   → 英语 (en)*
      turkey        土耳其     → 英语 (en)*
    东南亚/非洲伊斯兰：
      malaysia_i    马来西亚   → 马来语 (ms)
      indonesia_i   印度尼西亚 → 印尼语 (id)
      egypt_i       埃及       → 英语 (en)*
      morocco_i     摩洛哥     → 法语 (fr)
      tunisia_i     突尼斯     → 法语 (fr)

    * 阿拉伯语/波斯语/土耳其语/乌尔都语暂无模板，使用英语

用法：
    py -3 scripts/run_islamic.py --list-countries
    py -3 scripts/run_islamic.py --country saudi_arabia,uae,qatar --posts 30 --yes
    py -3 scripts/run_islamic.py --country turkey,iran,pakistan --posts 20 --yes
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
# 伊斯兰国家标签注册表
# ============================================================
COUNTRIES = {
    # 中东（阿拉伯语区 → 英语回退）
    "saudi_arabia": {
        "name_en": "Saudi Arabia",
        "name_local": "المملكة العربية السعودية",
        "lang": "en",
        "query": "saudi arabia mecca riyadh mosque desert",
        "hashtags": ["#SaudiArabia", "#Mecca", "#IslamicTravel"],
    },
    "uae": {
        "name_en": "UAE",
        "name_local": "الإمارات العربية المتحدة",
        "lang": "en",
        "query": "dubai abu dhabi uae mosque skyline desert",
        "hashtags": ["#UAE", "#Dubai", "#IslamicTravel"],
    },
    "qatar": {
        "name_en": "Qatar",
        "name_local": "قطر",
        "lang": "en",
        "query": "qatar doha mosque pearl skyline",
        "hashtags": ["#Qatar", "#Doha", "#IslamicTravel"],
    },
    "kuwait": {
        "name_en": "Kuwait",
        "name_local": "الكويت",
        "lang": "en",
        "query": "kuwait city mosque towers skyline",
        "hashtags": ["#Kuwait", "#KuwaitCity", "#IslamicTravel"],
    },
    "oman": {
        "name_en": "Oman",
        "name_local": "عمان",
        "lang": "en",
        "query": "oman muscat mosque sultan qaboos desert",
        "hashtags": ["#Oman", "#Muscat", "#IslamicTravel"],
    },
    "bahrain": {
        "name_en": "Bahrain",
        "name_local": "البحرين",
        "lang": "en",
        "query": "bahrain manama mosque pearl island",
        "hashtags": ["#Bahrain", "#Manama", "#IslamicTravel"],
    },
    "jordan": {
        "name_en": "Jordan",
        "name_local": "الأردن",
        "lang": "en",
        "query": "jordan petra amman dead sea wadi rum desert",
        "hashtags": ["#Jordan", "#Petra", "#IslamicTravel"],
    },
    "iraq": {
        "name_en": "Iraq",
        "name_local": "العراق",
        "lang": "en",
        "query": "iraq baghdad mosque babylon ancient",
        "hashtags": ["#Iraq", "#Baghdad", "#IslamicTravel"],
    },
    "iran": {
        "name_en": "Iran",
        "name_local": "ایران",
        "lang": "en",  # 波斯语回退英语
        "query": "iran isfahan mosque persian architecture tehran",
        "hashtags": ["#Iran", "#Isfahan", "#IslamicTravel"],
    },
    "yemen": {
        "name_en": "Yemen",
        "name_local": "اليمن",
        "lang": "en",
        "query": "yemen sanaa old city architecture mosque",
        "hashtags": ["#Yemen", "#Sanaa", "#IslamicTravel"],
    },
    # 中亚/南亚
    "turkey": {
        "name_en": "Turkey",
        "name_local": "Türkiye",
        "lang": "en",  # 土耳其语回退英语
        "query": "turkey istanbul mosque blue mosque cappadocia",
        "hashtags": ["#Turkey", "#Istanbul", "#IslamicTravel"],
    },
    "pakistan": {
        "name_en": "Pakistan",
        "name_local": "پاکستان",
        "lang": "en",
        "query": "pakistan lahore mosque badshahi islamabad hunza",
        "hashtags": ["#Pakistan", "#Lahore", "#IslamicTravel"],
    },
    "bangladesh": {
        "name_en": "Bangladesh",
        "name_local": "বাংলাদেশ",
        "lang": "en",
        "query": "bangladesh dhaka mosque river landscape",
        "hashtags": ["#Bangladesh", "#Dhaka", "#IslamicTravel"],
    },
    "afghanistan": {
        "name_en": "Afghanistan",
        "name_local": "افغانستان",
        "lang": "en",
        "query": "afghanistan mosque blue mosque mountain landscape",
        "hashtags": ["#Afghanistan", "#BlueMosque", "#IslamicTravel"],
    },
    "uzbekistan": {
        "name_en": "Uzbekistan",
        "name_local": "Oʻzbekiston",
        "lang": "en",
        "query": "uzbekistan samarkand registan mosque silk road",
        "hashtags": ["#Uzbekistan", "#Samarkand", "#IslamicTravel"],
    },
    # 东南亚伊斯兰
    "malaysia_i": {
        "name_en": "Malaysia",
        "name_local": "Malaysia",
        "lang": "ms",
        "query": "malaysia mosque putrajaya kuala lumpur islamic",
        "hashtags": ["#Malaysia", "#MasjidPutrajaya", "#IslamicTravel"],
    },
    "indonesia_i": {
        "name_en": "Indonesia",
        "name_local": "Indonesia",
        "lang": "id",
        "query": "indonesia mosque istiqlal java islamic architecture",
        "hashtags": ["#Indonesia", "#Istiqlal", "#IslamicTravel"],
    },
    # 北非伊斯兰
    "egypt_i": {
        "name_en": "Egypt",
        "name_local": "مصر",
        "lang": "en",
        "query": "egypt cairo mosque al azhar islamic architecture",
        "hashtags": ["#Egypt", "#Cairo", "#IslamicTravel"],
    },
    "morocco_i": {
        "name_en": "Morocco",
        "name_local": "المغرب",
        "lang": "fr",
        "query": "morocco casablanca hassan mosque fes medina",
        "hashtags": ["#Maroc", "#Casablanca", "#IslamicTravel"],
    },
    "tunisia_i": {
        "name_en": "Tunisia",
        "name_local": "تونس",
        "lang": "fr",
        "query": "tunisia kairouan mosque medina islamic",
        "hashtags": ["#Tunisie", "#Kairouan", "#IslamicTravel"],
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
        description="Islamic countries publisher (country tag → stock photos → local language caption → publish)",
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
    ap.add_argument("--workdir", default="islamic_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.list_countries:
        print("伊斯兰国家标签：")
        print(f"{'标签':<14} {'国家':<16} {'语言':<6} {'本地名':<20} {'搜索关键词'}")
        print("-" * 90)
        for key, info in COUNTRIES.items():
            print(f"{key:<14} {info['name_en']:<16} {info['lang']:<6} {info['name_local']:<20} {info['query'][:30]}")
        print(f"\n共 {len(COUNTRIES)} 个国家")
        # 语言分布
        from collections import Counter
        lang_dist = Counter(v['lang'] for v in COUNTRIES.values())
        print(f"语言分布: {dict(lang_dist)}")
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
        print(f"\n--- Step 1: 采集图片 ---")
        dedupe = state_dir / f"seen_is_{country_key}.json"
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
    combined = wd / f"islamic_combined_{ts}.csv"
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
    print(f"[ISLAMIC] 合并素材: {len(all_rows)} 帖 → {combined.name}")
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
        print(f"[ISLAMIC] 发布返回 {rc}")
        return rc

    print(f"\n[ISLAMIC] 完成！发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
