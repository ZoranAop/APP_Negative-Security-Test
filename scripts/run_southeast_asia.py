#!/usr/bin/env python3
"""
run_southeast_asia.py — 东南亚内容一键发布（按国家标签自动匹配语言+素材）

东南亚 11 国标签体系，选择标签后自动：
    1) 从 Pexels + Pixabay 搜索对应国家图片素材
    2) 用该国语言生成文案（语言一致性）
    3) 发布图文帖（自动裁切水印 + S3 上传）

支持国家标签（--country）：
    malaysia    马来西亚   → 马来语 (ms)
    singapore   新加坡     → 英语 (en)
    indonesia   印度尼西亚 → 印尼语 (id)
    thailand    泰国       → 泰语 (th) → 回退英语
    vietnam     越南       → 越南语 (vi) → 回退英语
    philippines 菲律宾     → 菲律宾语/他加禄语 (tl) → 回退英语
    cambodia    柬埔寨     → 高棉语 (km) → 回退英语
    laos        老挝       → 老挝语 (lo) → 回退英语
    myanmar     缅甸       → 缅甸语 (my) → 回退英语
    brunei      文莱       → 马来语 (ms)
    timor_leste 东帝汶     → 葡萄牙语 (pt) → 回退英语

快速上手：
    # 发布柬埔寨旅游图文帖（20用户×2帖=40帖，英语文案）
    py -3 scripts/run_southeast_asia.py --country cambodia --accounts-csv accounts_20.csv --posts 40 --yes

    # 马来西亚（马来语）
    py -3 scripts/run_southeast_asia.py --country malaysia --posts 20 --yes

    # 多国混合（每国5帖）
    py -3 scripts/run_southeast_asia.py --country malaysia,singapore,indonesia,thailand --posts 20 --yes

    # 只采集+文案，不发布
    py -3 scripts/run_southeast_asia.py --country vietnam --posts 10 --skip-publish

    # 列出所有支持的国家
    py -3 scripts/run_southeast_asia.py --list-countries

泰国 (Thailand) 本地内容源站点：
    - https://www.beartai.com/          — 泰国科技/数码/生活方式媒体
    - https://www.blognone.com/         — 泰国科技新闻/创业资讯
    - https://www.timeout.com/bangkok   — 曼谷生活/美食/活动/旅游指南
    - https://worldcup.readthecloud.co/ — 世界杯专题内容（泰国视角）
    - https://www.kapook.com/           — 泰国综合生活门户（娱乐/星座/美食/旅游）
    - https://www.sanook.com/           — 泰国综合娱乐/新闻/体育门户
    以上站点已注册在 COUNTRIES["thailand"]["local_sources"]，
    后续可配合 fetch_th_life.py 实现本地内容采集（RSS / HTML 解析）。
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
# 东南亚国家标签注册表
# ============================================================
COUNTRIES = {
    "malaysia": {
        "name_en": "Malaysia",
        "name_local": "Malaysia",
        "lang": "ms",
        "query": "malaysia travel landscape",
        "hashtags": ["#Malaysia", "#Jelajah", "#AseanTravel"],
        "fallback_lang": "ms",
    },
    "singapore": {
        "name_en": "Singapore",
        "name_local": "Singapore",
        "lang": "en",
        "query": "singapore city skyline marina",
        "hashtags": ["#Singapore", "#LionCity", "#AseanTravel"],
        "fallback_lang": "en",
    },
    "indonesia": {
        "name_en": "Indonesia",
        "name_local": "Indonesia",
        "lang": "id",
        "query": "indonesia bali temple travel",
        "hashtags": ["#Indonesia", "#WonderfulIndonesia", "#AseanTravel"],
        "fallback_lang": "id",
    },
    "thailand": {
        "name_en": "Thailand",
        "name_local": "ประเทศไทย",
        "lang": "en",  # 泰语文案回退英语（caption_multilang 暂不支持 th）
        "query": "thailand bangkok temple beach",
        "hashtags": ["#Thailand", "#AmazingThailand", "#AseanTravel"],
        "fallback_lang": "en",
        "local_sources": [
            "https://www.beartai.com/",          # 泰国科技/生活媒体
            "https://www.blognone.com/",          # 泰国科技新闻
            "https://www.timeout.com/bangkok",    # 曼谷生活/餐饮/活动
            "https://worldcup.readthecloud.co/",  # 世界杯专题（泰国视角）
            "https://www.kapook.com/",            # 泰国综合生活门户
            "https://www.sanook.com/",            # 泰国综合娱乐/新闻
        ],
    },
    "vietnam": {
        "name_en": "Vietnam",
        "name_local": "Việt Nam",
        "lang": "en",  # 越南语回退英语
        "query": "vietnam hanoi hoian landscape",
        "hashtags": ["#Vietnam", "#VisitVietnam", "#AseanTravel"],
        "fallback_lang": "en",
    },
    "philippines": {
        "name_en": "Philippines",
        "name_local": "Pilipinas",
        "lang": "en",  # 菲律宾语回退英语
        "query": "philippines beach island palawan",
        "hashtags": ["#Philippines", "#ItsMoreFun", "#AseanTravel"],
        "fallback_lang": "en",
    },
    "cambodia": {
        "name_en": "Cambodia",
        "name_local": "កម្ពុជា",
        "lang": "en",  # 高棉语回退英语
        "query": "cambodia angkor wat temple siem reap",
        "hashtags": ["#Cambodia", "#AngkorWat", "#AseanTravel"],
        "fallback_lang": "en",
    },
    "laos": {
        "name_en": "Laos",
        "name_local": "ລາວ",
        "lang": "en",  # 老挝语回退英语
        "query": "laos luang prabang mekong temple",
        "hashtags": ["#Laos", "#LuangPrabang", "#AseanTravel"],
        "fallback_lang": "en",
    },
    "myanmar": {
        "name_en": "Myanmar",
        "name_local": "မြန်မာ",
        "lang": "en",  # 缅甸语回退英语
        "query": "myanmar bagan pagoda temple",
        "hashtags": ["#Myanmar", "#Bagan", "#AseanTravel"],
        "fallback_lang": "en",
    },
    "brunei": {
        "name_en": "Brunei",
        "name_local": "Brunei Darussalam",
        "lang": "ms",  # 文莱用马来语
        "query": "brunei mosque palace",
        "hashtags": ["#Brunei", "#BruneiDarussalam", "#AseanTravel"],
        "fallback_lang": "ms",
    },
    "timor_leste": {
        "name_en": "Timor-Leste",
        "name_local": "Timor-Leste",
        "lang": "en",  # 葡萄牙语回退英语
        "query": "timor leste dili beach",
        "hashtags": ["#TimorLeste", "#Dili", "#AseanTravel"],
        "fallback_lang": "en",
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
        description="Southeast Asia one-command publisher (country tag → stock photos → local language caption → publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--country", default="malaysia",
                    help="国家标签（逗号分隔可多选）。用 --list-countries 查看全部")
    ap.add_argument("--list-countries", action="store_true", help="列出所有支持的国家标签")
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--posts", type=int, default=20, help="要发布的帖子总数")
    ap.add_argument("--per-source", type=int, default=30, help="每个图库最多取图数")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--crop-pct", default="0.08")
    ap.add_argument("--workdir", default="sea_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.list_countries:
        print("东南亚国家标签：")
        print(f"{'标签':<14} {'国家':<14} {'语言':<6} {'搜索关键词'}")
        print("-" * 70)
        for key, info in COUNTRIES.items():
            print(f"{key:<14} {info['name_en']:<14} {info['lang']:<6} {info['query']}")
        return 0

    # 解析国家列表
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

    # 计算每个国家分配多少帖
    posts_per_country = args.posts // len(country_keys)
    remainder = args.posts % len(country_keys)

    all_moments_files = []

    for idx, country_key in enumerate(country_keys):
        info = COUNTRIES[country_key]
        n_posts = posts_per_country + (1 if idx < remainder else 0)
        lang = info["lang"]
        query = info["query"]
        hashtags = " ".join(info["hashtags"])

        print(f"\n{'='*60}")
        print(f"[{country_key.upper()}] {info['name_en']} | 语言={lang} | 帖数={n_posts}")
        print(f"{'='*60}")

        raw_csv = wd / f"{country_key}_raw_{ts}.csv"
        moments_csv = wd / f"{country_key}_moments_{ts}.csv"

        # Step 1: 采集
        print(f"\n--- Step 1: 采集图片 (query={query}) ---")
        dedupe = state_dir / f"seen_sea_{country_key}.json"
        cmd = PY + [str(HERE / "fetch_stock_my.py"),
                    "--sources", "pexels,pixabay",
                    "--query", query,
                    "--per-source", str(args.per_source),
                    "--dedupe-file", str(dedupe),
                    "--output", str(raw_csv)]
        if _run(cmd) != 0 or not raw_csv.exists():
            print(f"[{country_key}] 采集失败，跳过")
            continue

        # 检查采集数量
        with open(raw_csv, encoding="utf-8-sig") as f:
            raw_rows = list(csv.DictReader(f))
        if len(raw_rows) < n_posts:
            print(f"[{country_key}] 采集 {len(raw_rows)} 条 < 需要 {n_posts}，使用全部")
            n_posts = len(raw_rows)

        # 截取需要的行数
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

        # Step 2: 文案改写（对应语言）
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

    # 合并所有国家的 moments CSV
    combined = wd / f"sea_combined_{ts}.csv"
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
    print(f"[SEA] 合并素材: {len(all_rows)} 帖 → {combined.name}")
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
    print(f"\n--- Step 3: 发布 ({len(all_rows)} 帖) ---")
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[ERROR] 账号 CSV 不存在: {acc}")
        return 2

    if not args.yes:
        print(f"  账号: {acc}")
        print(f"  素材: {len(all_rows)} 帖")
        if input("  确认发布？(y/n): ").strip().lower() not in ("y", "yes"):
            print("已取消")
            return 0

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc),
                "--csv", str(combined),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd, env_extra={"POST_CROP_BOTTOM_PCT": args.crop_pct})
    if rc != 0:
        print(f"[SEA] 发布返回 {rc}，请查看日志")
        return rc

    print(f"\n[SEA] 完成！发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
