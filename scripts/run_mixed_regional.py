#!/usr/bin/env python3
"""
run_mixed_regional.py — 通用混合区域发帖脚本（科技 + 生活混合，支持预设与自定义组合）

设计目的：
    替代一次性定制脚本（如 run_hk_tw.py），提供可复用的多区域混合发帖能力。
    支持预设配置（--preset）和完全自定义（--tech-sources / --life-script 等）。

预设清单（可扩展）：
    hk_tw   — 香港科技（繁中+英文） + 台湾生活（繁中）
    us_eu   — 国际科技（英文）       + 美国生活（英文）
    jp_kr   — 日本科技（日文）       + 日本生活（日文）
    sea     — 东南亚科技（英文）     + 新加坡生活（英文）

用法：
    # 预设模式
    py -3 scripts/run_mixed_regional.py --accounts-csv accounts.csv --preset hk_tw --posts 10 --yes

    # 自定义模式
    py -3 scripts/run_mixed_regional.py \\
        --accounts-csv accounts.csv \\
        --tech-sources hket,hket_home,cnbc_world \\
        --life-script fetch_tw_life.py \\
        --life-sources yahoo_life,ltn_life \\
        --life-lang zh_hant \\
        --posts 10 \\
        --langs zh_hant:50,en:50 \\
        --yes
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
sys.path.insert(0, str(HERE))

# ---------------------------------------------------------------------------
# 预设配置（可扩展）
# ---------------------------------------------------------------------------
PRESETS = {
    "hk_tw": {
        "description": "香港科技（繁中+英文）+ 台湾生活（繁中）",
        "tech_sources": "hket,hket_home,cnbc_world,bloomberg_jp,guardian",
        "life_script": "fetch_tw_life.py",
        "life_sources": "yahoo_life,ltn_life,udn_life",
        "life_lang": "zh_hant",
        "langs": "zh_hant:50,en:50",
    },
    "us_eu": {
        "description": "国际科技（英文）+ 美国生活（英文）",
        "tech_sources": "techcrunch,theverge,wired",
        "life_script": "fetch_us_life.py",
        "life_sources": "buzzfeed,usatoday",
        "life_lang": "en",
        "langs": "en:100",
    },
    "jp_kr": {
        "description": "日本科技（日文）+ 日本生活（日文）",
        "tech_sources": "gizmodo_jp",
        "life_script": "fetch_jp_life.py",
        "life_sources": "grapee,hintpot",
        "life_lang": "ja",
        "langs": "ja:100",
    },
    "sea": {
        "description": "东南亚科技（英文）+ 新加坡生活（英文）",
        "tech_sources": "straitstimes,cnbc_world",
        "life_script": "fetch_sg_life.py",
        "life_sources": "herworld,eatbook",
        "life_lang": "en",
        "langs": "en:100",
    },
}

# ---------------------------------------------------------------------------
# 来源过滤（与 run_tech.py strip_source_attribution 对齐，通用版本）
# ---------------------------------------------------------------------------


def strip_source_attribution(text: str) -> str:
    """移除所有来源/出处标注，使文案呈现为用户原创分享。"""
    if not text:
        return text
    # 1. 中文圆括号来源
    text = _re.sub(r'[（(]\s*[來来]源\s*[:：]?\s*[^）)]+[）)]', '', text)
    # 2. 英文/日文圆括号 via/source/出典
    text = _re.sub(r'\(\s*(?:via|source|sumber|出典)\s*[:：]?\s*[^)]+\)', '', text)
    # 3. 行内 via/來源/出典 + 任意非标点词
    text = _re.sub(r'(?:via|來源|来源|出典|sumber)\s*[:：]?\s*\S+', '', text)
    # 4. 清理残留
    text = _re.sub(r'[ \t]{2,}', ' ', text)
    text = _re.sub(r'[（(]\s*[）)]', '', text)
    text = _re.sub(r'【\s*】', '', text)
    text = _re.sub(r'\[\s*\]', '', text)
    text = _re.sub(r'^\s*[，,。.、；;：:—\-]+\s*', '', text)
    text = _re.sub(r' {2,}', ' ', text)
    return text.strip()


# ---------------------------------------------------------------------------
# 语言标签与模板
# ---------------------------------------------------------------------------
LANG_TAG = {
    "zh_hant": "#科技生活",
    "en": "#TechLife",
    "ja": "#テクノロジー生活",
    "ms": "#TeknologiHidup",
}

# 科技内容模板（按语言）
TECH_TEMPLATES = {
    "zh_hant": [
        "{title}，行業風向又變了 {tag}",
        "{title}，這波技術進展值得關注 {tag}",
        "{title}，科技圈今天的大事 {tag}",
        "{title}，身為業內人覺得這很有參考價值 {tag}",
        "{title}，越看越覺得有意思 {tag}",
        "{title}，這類資訊先收藏 {tag}",
    ],
    "en": [
        "{title}, this one's worth watching {tag}",
        "{title}, genuinely fascinating development {tag}",
        "{title}, bookmarking this {tag}",
        "{title}, the more I read the more hooked I am {tag}",
        "{title}, real signals here {tag}",
        "{title}, paying attention to this one {tag}",
    ],
    "ja": [
        "{title}、注目に値する展開 {tag}",
        "{title}、技術の進化は本当に面白い {tag}",
        "{title}、ブックマークした {tag}",
        "{title}、業界人として気になる {tag}",
        "{title}、要チェック {tag}",
        "{title}、共有しておく {tag}",
    ],
    "ms": [
        "{title}, perkembangan menarik {tag}",
        "{title}, layak diberi perhatian {tag}",
        "{title}, saya simpan ini {tag}",
        "{title}, makin dibaca makin menarik {tag}",
        "{title}, patut diperhatikan {tag}",
        "{title}, saya kongsikan di sini {tag}",
    ],
}

# 生活内容模板（按语言）
LIFE_TEMPLATES = {
    "zh_hant": [
        "{title}，生活中的小發現 {tag}",
        "{title}，覺得蠻實用的 {tag}",
        "{title}，台灣日常總是充滿驚喜 {tag}",
        "{title}，看到忍不住想分享 {tag}",
        "{title}，這種內容就是要分享出來的 {tag}",
        "{title}，又學到新東西了 {tag}",
    ],
    "en": [
        "{title}, love stumbling upon content like this {tag}",
        "{title}, this made my day better {tag}",
        "{title}, bookmark-worthy stuff {tag}",
        "{title}, sharing because this genuinely made me smile {tag}",
        "{title}, exactly what I needed to see today {tag}",
        "{title}, the little things that make life feel put together {tag}",
    ],
    "ja": [
        "{title}、暮らしのヒントがまた増えた {tag}",
        "{title}、こういう記事大好き {tag}",
        "{title}、誰かに教えたくなる情報 {tag}",
        "{title}、日常が少し豊かになる {tag}",
        "{title}、実際にやってみたくなる {tag}",
        "{title}、シンプルだけど奥が深い {tag}",
    ],
    "ms": [
        "{title}, tips harian yang berguna {tag}",
        "{title}, hidup jadi lebih mudah dengan ini {tag}",
        "{title}, perlu simpan untuk kemudian {tag}",
        "{title}, menarik untuk dicuba {tag}",
        "{title}, saya kongsikan di sini {tag}",
        "{title}, kehidupan harian jadi lebih baik {tag}",
    ],
}


def _build_caption(title: str, lang: str, is_tech: bool,
                   rng: random.Random, seen: set) -> str:
    """生成纯描述第一人称文案，无来源标注。"""
    title = strip_source_attribution(title)
    tag = LANG_TAG.get(lang, "#TechLife")
    templates = (TECH_TEMPLATES if is_tech else LIFE_TEMPLATES).get(lang)
    if not templates:
        templates = (TECH_TEMPLATES if is_tech else LIFE_TEMPLATES).get("en", ["{title} {tag}"])

    max_title_len = 50 if lang == "en" else 35
    for _ in range(40):
        tpl = rng.choice(templates)
        cap = tpl.format(title=title[:max_title_len], tag=tag)
        cap = strip_source_attribution(cap)
        if len(cap) > 300:
            cap = tpl.format(title=title[:max_title_len - 15], tag=tag)
            cap = strip_source_attribution(cap)
        if cap not in seen:
            seen.add(cap)
            return cap
    base = templates[0].format(title=title[:max_title_len - 5], tag=tag)
    return strip_source_attribution(base)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _run(cmd):
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _parse_langs(lang_str: str) -> list[tuple[str, int]]:
    """解析 'zh_hant:50,en:50' → [('zh_hant', 50), ('en', 50)]"""
    result = []
    for part in lang_str.split(","):
        part = part.strip()
        if ":" in part:
            lang, weight = part.rsplit(":", 1)
            result.append((lang.strip(), int(weight)))
        else:
            result.append((part, 100))
    return result


def _weighted_lang_pick(langs_weights: list[tuple[str, int]], rng: random.Random) -> str:
    """按权重随机选择语言。"""
    total = sum(w for _, w in langs_weights)
    r = rng.randint(1, total)
    cumulative = 0
    for lang, weight in langs_weights:
        cumulative += weight
        if r <= cumulative:
            return lang
    return langs_weights[0][0]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="通用混合区域发帖（科技+生活，预设或自定义）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="预设列表:\n" + "\n".join(
            f"  {k:10s} — {v['description']}" for k, v in PRESETS.items()
        ),
    )
    ap.add_argument("--accounts-csv", default="accounts_20.csv")
    ap.add_argument("--preset", choices=list(PRESETS.keys()),
                    help="使用预设配置（可被其他参数覆盖）")
    ap.add_argument("--tech-sources", default="",
                    help="科技源（逗号分隔，如 hket,cnbc_world）")
    ap.add_argument("--life-script", default="",
                    help="生活采集脚本（如 fetch_tw_life.py）")
    ap.add_argument("--life-sources", default="",
                    help="生活源（逗号分隔，如 yahoo_life,ltn_life）")
    ap.add_argument("--life-lang", default="",
                    help="生活内容的语言标记（如 zh_hant, en, ja）")
    ap.add_argument("--langs", default="",
                    help="语言比例，如 zh_hant:50,en:50")
    ap.add_argument("--posts", type=int, default=10,
                    help="总发帖数")
    ap.add_argument("--per-site", type=int, default=5,
                    help="每个源采集条数")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="mixed_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    # --- 解析配置（预设 + 自定义覆盖）---
    cfg = {}
    if args.preset:
        cfg = dict(PRESETS[args.preset])
        print(f"[mixed] 使用预设: {args.preset} — {cfg['description']}")
    # 自定义覆盖
    tech_sources = args.tech_sources or cfg.get("tech_sources", "")
    life_script = args.life_script or cfg.get("life_script", "")
    life_sources = args.life_sources or cfg.get("life_sources", "")
    life_lang = args.life_lang or cfg.get("life_lang", "en")
    langs_str = args.langs or cfg.get("langs", "en:100")

    if not tech_sources and not life_script:
        print("[ERROR] 至少需要 --tech-sources 或 --life-script（或使用 --preset）")
        return 1

    langs_weights = _parse_langs(langs_str)
    print(f"[mixed] 科技源: {tech_sources or '(无)'}")
    print(f"[mixed] 生活源: {life_script} → {life_sources or '(默认)'}")
    print(f"[mixed] 语言比例: {langs_weights}")
    print(f"[mixed] 目标帖数: {args.posts}")

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    all_items = []  # [(title, is_tech, site_key, lang), ...]

    # --- Step 1: 采集科技内容 ---
    if tech_sources:
        tech_csv = wd / f"mixed_tech_raw_{ts}.csv"
        print(f"\n=== Step 1a: 采集科技内容 ({tech_sources}) ===")
        cmd = PY + [str(HERE / "fetch_tech.py"),
                    "--sources", tech_sources,
                    "--per-site", str(args.per_site),
                    "--output", str(tech_csv)]
        if _run(cmd) != 0 or not tech_csv.exists():
            print("[WARN] 科技采集失败，跳过科技部分")
        else:
            with open(tech_csv, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    all_items.append({
                        "title": r.get("content", ""),
                        "is_tech": True,
                        "site": r.get("_site", ""),
                        "source": r.get("_source", ""),
                        "image_urls": r.get("image_urls", ""),
                    })
            print(f"[mixed] 科技采集: {len([i for i in all_items if i['is_tech']])} 条")

    # --- Step 1b: 采集生活内容 ---
    if life_script:
        life_csv = wd / f"mixed_life_raw_{ts}.csv"
        print(f"\n=== Step 1b: 采集生活内容 ({life_script} → {life_sources}) ===")
        life_cmd = PY + [str(HERE / life_script)]
        if life_sources:
            life_cmd += ["--sources", life_sources]
        life_cmd += ["--per-site", str(args.per_site), "--output", str(life_csv)]
        if _run(life_cmd) != 0 or not life_csv.exists():
            print("[WARN] 生活采集失败，跳过生活部分")
        else:
            with open(life_csv, encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    all_items.append({
                        "title": r.get("content", ""),
                        "is_tech": False,
                        "site": r.get("_site", ""),
                        "source": r.get("_source", ""),
                        "image_urls": r.get("image_urls", ""),
                    })
            life_count = len([i for i in all_items if not i["is_tech"]])
            print(f"[mixed] 生活采集: {life_count} 条")

    if not all_items:
        print("[ERROR] 无任何采集内容"); return 1

    # --- Step 2: 混合 & 生成文案 ---
    print(f"\n=== Step 2: 混合分配 + 生成文案（共 {len(all_items)} 条素材，目标 {args.posts} 帖）===")
    rng = random.Random(int(ts.replace("_", "")))
    rng.shuffle(all_items)

    # 截断到目标帖数
    items = all_items[:args.posts]
    seen_caps: set = set()
    moments = []

    for item in items:
        # 按权重选语言（科技内容可多语，生活内容用指定语言）
        if item["is_tech"]:
            lang = _weighted_lang_pick(langs_weights, rng)
        else:
            lang = life_lang

        cap = _build_caption(item["title"], lang, item["is_tech"], rng, seen_caps)
        moments.append({
            "content": cap,
            "visibility": "0",
            "room_id": "",
            "image_urls": item.get("image_urls", ""),
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_source": item.get("source", ""),
            "_site": item.get("site", ""),
            "_lang": lang,
        })

    # 输出 moments CSV
    moments_csv = wd / f"mixed_moments_{ts}.csv"
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_lang"]
    with open(moments_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow({k: m.get(k, "") for k in fields})

    # 统计
    from collections import Counter
    lang_dist = Counter(m["_lang"] for m in moments)
    tech_count = sum(1 for i in items if i["is_tech"])
    life_count = len(items) - tech_count
    print(f"[mixed] 文案生成完毕: {len(moments)} 帖（科技 {tech_count} / 生活 {life_count}）")
    print(f"[mixed] 语言分布: {dict(lang_dist)}")
    print(f"[mixed] 输出: {moments_csv}")

    # 预览前 5 条
    for i, m in enumerate(moments[:5]):
        print(f"  #{i+1} [{m['_lang']}] {m['content'][:60]}...")

    if args.skip_publish:
        print(f"\n--skip-publish. 素材: {moments_csv}")
        return 0

    # --- Step 3: 发布 ---
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[ERROR] 账号文件不存在: {acc}"); return 2
    if not args.yes:
        ans = input(f"  发布 {len(moments)} 帖？(y/n): ").strip().lower()
        if ans not in ("y", "yes"):
            print("[mixed] 已取消。"); return 0

    print(f"\n=== Step 3: 发布（{len(moments)} 帖）===")
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print(f"[mixed] 发布返回 {rc}"); return rc
    print(f"\n[mixed] 完成！报告: result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
