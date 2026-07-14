#!/usr/bin/env python3
"""
run_gulf.py — 海湾国家(GCC)内容一键发布（按国家标签自动匹配语言+素材）

覆盖海湾阿拉伯国家合作委员会(GCC) 6 国 + 周边海湾地区国家，共 10 国。
选择标签后自动：
    1) 从 Pexels + Pixabay 搜索对应国家图片素材（清真寺/天际线/沙漠/市集等）
    2) 用该国语言生成文案（语言一致性）
    3) 每条帖子文案独立改写，避免用户间内容雷同
    4) 发布图文帖

海湾国家标签（--country）：
    GCC六国：
      saudi_arabia  沙特阿拉伯 → 英语 (en)
      uae           阿联酋     → 英语 (en)
      qatar         卡塔尔     → 英语 (en)
      kuwait        科威特     → 英语 (en)
      oman          阿曼       → 英语 (en)
      bahrain       巴林       → 英语 (en)
    周边海湾地区：
      iraq          伊拉克     → 英语 (en)
      iran          伊朗       → 英语 (en)
      yemen         也门       → 英语 (en)
      jordan        约旦       → 英语 (en)

用法：
    py -3 scripts/run_gulf.py --list-countries
    py -3 scripts/run_gulf.py --country uae,saudi_arabia,qatar --posts 20 --yes
    py -3 scripts/run_gulf.py --country all --accounts-csv accounts_10.csv --posts 20 --yes
"""
from __future__ import annotations

import argparse
import csv
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

# ============================================================
# 海湾国家标签注册表
# ============================================================
COUNTRIES = {
    "saudi_arabia": {
        "name_en": "Saudi Arabia",
        "name_local": "المملكة العربية السعودية",
        "lang": "en",
        "queries": [
            "saudi arabia mecca mosque night",
            "riyadh skyline modern city",
            "saudi desert landscape golden",
            "medina mosque islamic architecture",
            "jeddah corniche waterfront",
        ],
        "hashtags": ["#SaudiArabia", "#Riyadh", "#GulfTravel"],
    },
    "uae": {
        "name_en": "UAE",
        "name_local": "الإمارات",
        "lang": "en",
        "queries": [
            "dubai burj khalifa skyline night",
            "abu dhabi grand mosque white",
            "dubai marina yacht luxury",
            "dubai desert safari sunset",
            "palm jumeirah aerial view",
        ],
        "hashtags": ["#UAE", "#Dubai", "#GulfTravel"],
    },
    "qatar": {
        "name_en": "Qatar",
        "name_local": "قطر",
        "lang": "en",
        "queries": [
            "qatar doha skyline pearl",
            "doha museum islamic art",
            "qatar desert landscape camel",
            "qatar lusail stadium",
        ],
        "hashtags": ["#Qatar", "#Doha", "#GulfTravel"],
    },
    "kuwait": {
        "name_en": "Kuwait",
        "name_local": "الكويت",
        "lang": "en",
        "queries": [
            "kuwait towers city skyline",
            "kuwait grand mosque",
            "kuwait city modern architecture",
        ],
        "hashtags": ["#Kuwait", "#KuwaitCity", "#GulfTravel"],
    },
    "oman": {
        "name_en": "Oman",
        "name_local": "عمان",
        "lang": "en",
        "queries": [
            "oman muscat sultan qaboos mosque",
            "oman wadi landscape nature",
            "oman desert sand dunes",
            "muscat corniche old town",
        ],
        "hashtags": ["#Oman", "#Muscat", "#GulfTravel"],
    },
    "bahrain": {
        "name_en": "Bahrain",
        "name_local": "البحرين",
        "lang": "en",
        "queries": [
            "bahrain skyline city",
            "bahrain world trade center",
            "bahrain fort ancient",
        ],
        "hashtags": ["#Bahrain", "#Manama", "#GulfTravel"],
    },
    "iraq": {
        "name_en": "Iraq",
        "name_local": "العراق",
        "lang": "en",
        "queries": [
            "iraq baghdad mosque golden",
            "iraq babylon ancient ruins",
            "iraq kurdistan mountain landscape",
        ],
        "hashtags": ["#Iraq", "#Baghdad", "#GulfTravel"],
    },
    "iran": {
        "name_en": "Iran",
        "name_local": "ایران",
        "lang": "en",
        "queries": [
            "iran isfahan mosque tile blue",
            "iran persepolis ancient",
            "tehran city mountain landscape",
            "iran shiraz pink mosque",
        ],
        "hashtags": ["#Iran", "#Isfahan", "#GulfTravel"],
    },
    "yemen": {
        "name_en": "Yemen",
        "name_local": "اليمن",
        "lang": "en",
        "queries": [
            "yemen sanaa old city architecture",
            "yemen socotra island tree",
        ],
        "hashtags": ["#Yemen", "#Sanaa", "#GulfTravel"],
    },
    "jordan": {
        "name_en": "Jordan",
        "name_local": "الأردن",
        "lang": "en",
        "queries": [
            "jordan petra treasury ancient",
            "jordan wadi rum desert mars",
            "jordan dead sea landscape",
            "amman citadel ancient",
        ],
        "hashtags": ["#Jordan", "#Petra", "#GulfTravel"],
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
        description="Gulf countries (GCC+) publisher — diversified content per user",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--country", default="uae",
                    help="国家标签（逗号分隔 或 'all'）")
    ap.add_argument("--list-countries", action="store_true")
    ap.add_argument("--accounts-csv", default="accounts_10.csv")
    ap.add_argument("--posts", type=int, default=20)
    ap.add_argument("--per-source", type=int, default=15)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="gulf_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.list_countries:
        print("海湾国家(GCC+)标签：")
        print(f"{'标签':<14} {'国家':<16} {'语言':<6} {'本地名':<14} {'搜索关键词组数'}")
        print("-" * 75)
        for key, info in COUNTRIES.items():
            print(f"{key:<14} {info['name_en']:<16} {info['lang']:<6} {info['name_local']:<14} {len(info['queries'])} 组")
        print(f"\n共 {len(COUNTRIES)} 个国家")
        print("特点: 每国多组搜索关键词，轮询使用确保图片多样性")
        return 0

    if args.country.lower() == "all":
        country_keys = list(COUNTRIES.keys())
    else:
        country_keys = [c.strip() for c in args.country.split(",") if c.strip()]
    invalid = [c for c in country_keys if c not in COUNTRIES]
    if invalid:
        print(f"[ERROR] 未知: {invalid}, 可用: {list(COUNTRIES.keys())}"); return 1

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
        # 从多组关键词中轮询选择，确保多样性
        query = info["queries"][idx % len(info["queries"])]

        print(f"\n{'='*60}")
        print(f"[{country_key.upper()}] {info['name_en']} ({info['name_local']}) | 语言={lang} | 帖数={n_posts}")
        print(f"  搜索: {query}")
        print(f"{'='*60}")

        raw_csv = wd / f"{country_key}_raw_{ts}.csv"
        moments_csv = wd / f"{country_key}_moments_{ts}.csv"

        # Step 1: 采集
        dedupe = state_dir / f"seen_gulf_{country_key}.json"
        cmd = PY + [str(HERE / "fetch_stock_my.py"),
                    "--sources", "pexels,pixabay",
                    "--query", query,
                    "--per-source", str(args.per_source),
                    "--dedupe-file", str(dedupe),
                    "--output", str(raw_csv)]
        if _run(cmd) != 0 or not raw_csv.exists():
            print(f"[{country_key}] 采集失败，跳过"); continue

        with open(raw_csv, encoding="utf-8-sig") as f:
            raw_rows = list(csv.DictReader(f))
        if len(raw_rows) < n_posts:
            n_posts = len(raw_rows)
        if n_posts == 0:
            print(f"[{country_key}] 无素材，跳过"); continue

        # 随机打散顺序确保不雷同
        random.shuffle(raw_rows)
        trimmed_csv = wd / f"{country_key}_trimmed_{ts}.csv"
        with open(raw_csv, encoding="utf-8-sig") as f:
            fields = csv.DictReader(f).fieldnames
        with open(trimmed_csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in raw_rows[:n_posts]:
                w.writerow(r)

        # Step 2: 文案改写
        cmd = PY + [str(HERE / "caption_multilang.py"),
                    "--input", str(trimmed_csv),
                    "--output", str(moments_csv),
                    "--langs", lang]
        if _run(cmd, env_extra={"DEFAULT_SCENE": "travel"}) != 0 or not moments_csv.exists():
            print(f"[{country_key}] 文案失败，跳过"); continue

        all_moments_files.append(moments_csv)
        print(f"[{country_key}] OK: {n_posts} 帖 | {lang}")

    if not all_moments_files:
        print("[ERROR] 无素材"); return 1

    # 合并并随机打散（确保同一用户连续帖子来自不同国家）
    combined = wd / f"gulf_combined_{ts}.csv"
    all_rows = []
    fieldnames = None
    for mf in all_moments_files:
        with open(mf, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if fieldnames is None:
                fieldnames = reader.fieldnames
            all_rows.extend(list(reader))
    random.shuffle(all_rows)

    with open(combined, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows:
            w.writerow(r)

    print(f"\n{'='*60}")
    print(f"[GULF] 合并+打散: {len(all_rows)} 帖 → {combined.name}")
    print(f"{'='*60}")

    # Step 2.5: 文案差异化（确保每帖内容不重复）
    print(f"\n--- Step 2.5: 文案差异化 (caption_diversify) ---")
    cmd = PY + [str(HERE / "caption_diversify.py"),
                "--input", str(combined), "--output", str(combined),
                "--lang", "en", "--scene", "travel"]
    _run(cmd)

    if args.skip_publish:
        print(f"\n--skip-publish. 素材: {combined}"); return 0

    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[ERROR] {acc} 不存在"); return 2
    if not args.yes:
        if input(f"  发布 {len(all_rows)} 帖？(y/n): ").strip().lower() not in ("y", "yes"):
            return 0

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(combined),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print(f"[GULF] 发布返回 {rc}"); return rc
    print(f"\n[GULF] 完成! result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
