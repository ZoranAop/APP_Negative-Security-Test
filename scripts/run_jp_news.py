#!/usr/bin/env python3
"""
run_jp_news.py — 日本资讯新闻一键发布（科技 / 财经 / 娱乐 三分类，日文文案，纯文本）

流程：
    1) 采集   从日本源 RSS 抓取科技 / 财经 / 娱乐资讯标题
    2) 文案   日文第一人称口吻，按分类打标签（#テクノロジー / #経済 / #エンタメ），全局去重
    3) 发布   publish_from_tokens.py（纯文本帖，media_info type=text）

日本源（均公开、无需登录）：
    科技:   Gizmodo Japan / ITmedia / Yahoo!ニュース IT
    财经:   東洋経済オンライン / Yahoo!ニュース 経済
    娱乐:   Yahoo!ニュース エンタメ

用法：
    # 预览（只采集+生成文案，不发布）
    py -3 scripts/run_jp_news.py --accounts-csv accounts_jp_news_3.csv --skip-publish

    # 正式发布
    py -3 scripts/run_jp_news.py --accounts-csv accounts_jp_news_3.csv --yes
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]
sys.path.insert(0, str(HERE))

from fetch_tech import _rss_items, _clean, _norm, _toks  # noqa: E402
from run_tech import strip_source_attribution  # noqa: E402
from caption_dedupe import load_used_captions, save_used_captions  # noqa: E402

# ---------------------------------------------------------------------------
# 日本源注册：key -> (category, rss_url)
# ---------------------------------------------------------------------------
# category: tech / finance / ent
JP_SOURCES = {
    "gizmodojp":    ("tech",    "https://www.gizmodo.jp/feed/index.xml"),
    "itmedia":      ("tech",    "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml"),
    "yahoo_it":     ("tech",    "https://news.yahoo.co.jp/rss/categories/it.xml"),
    "google_fin":   ("finance", "https://news.google.com/rss/search?q=%E7%B5%8C%E6%B8%88%20OR%20%E6%A0%AA%20OR%20%E9%87%91%E8%9E%8D&hl=ja&gl=JP&ceid=JP:ja"),
    "yahoo_ent":    ("ent",     "https://news.yahoo.co.jp/rss/categories/entertainment.xml"),
}

# Yahoo!ニュース RSS 标题末尾带媒体名（例：タイトル(LIMO)），需按源剥离尾部括注
STRIP_SOURCE_PAREN = {"yahoo_it", "yahoo_ent"}

# Google News RSS 标题末尾带 " - メディア名"，需剥离
STRIP_DASH_SUFFIX = {"google_fin"}

# 累计已用文案账本（跨批次防文案重复）
CAPTION_DEDUPE_FILE = "state/seen_jp_news_captions.json"

# 分类 -> 日文标签（标签语言与正文一致）
CAT_TAG = {
    "tech": "#テクノロジー",
    "finance": "#経済",
    "ent": "#エンタメ",
}

# 分类 -> 发帖人角色 -> 日文第一人称句式骨架（全局去重）
JP_TEMPLATES = {
    "tech": {
        "ガジェット好き": [
            "{title}、これは気になる {tag}",
            "{title}、要チェックだ {tag}",
            "{title}、詳しく読みたい {tag}",
            "{title}、テック好きにはたまらない {tag}",
        ],
        "技術者": [
            "{title}、技術の進化が面白い {tag}",
            "{title}、業界として注目しておきたい {tag}",
            "{title}、現場の人間として興味深い {tag}",
        ],
    },
    "finance": {
        "投資ウォッチャー": [
            "{title}、マーケットの動きとして見逃せない {tag}",
            "{title}、投資目線でチェックしておきたい {tag}",
            "{title}、このニュースは市場に響きそう {tag}",
        ],
        "ビジネス好き": [
            "{title}、経済ニュースとして気になる {tag}",
            "{title}、ビジネスの流れを感じる {tag}",
            "{title}、要チェックの話題だ {tag}",
        ],
    },
    "ent": {
        "エンタメ好き": [
            "{title}、これは嬉しいニュース {tag}",
            "{title}、ファンとして要チェック {tag}",
            "{title}、話題になっているみたい {tag}",
            "{title}、気になる {tag}",
        ],
        "映画音楽ファン": [
            "{title}、これは見逃せない {tag}",
            "{title}、チェックしておこう {tag}",
            "{title}、楽しみな話題だ {tag}",
        ],
    },
}


def _u8():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:  # noqa: BLE001
        pass


def _strip_trailing_attr(t: str) -> str:
    """剥离标题末尾的（来源/媒体名）括注，含嵌套/多个连续括注。"""
    prev = None
    while t != prev:
        prev = t
        t = re.sub(r"\s*\([^()]*\)\s*$", "", t)   # (media)
        t = re.sub(r"\s*（[^（）]*）\s*$", "", t)   # （media）
    return t.strip()


def clean_title(title: str, site: str) -> str:
    """清洗标题：去 HTML、去来源括注、去已知站点前缀。"""
    t = _clean(title)
    # 去除 "标题 | 栏目 | 站点" 形式的尾部管道段
    t = re.sub(r"\s*\|\s*[^|]*$", "", t)
    t = re.sub(r"\s*\|\s*[^|]*$", "", t)
    if site in STRIP_SOURCE_PAREN:
        t = _strip_trailing_attr(t)
    if site in STRIP_DASH_SUFFIX:
        t = re.sub(r"\s*-\s*[^\-]+$", "", t).strip()
    t = re.sub(r"^【[^】]*】\s*", "", t)
    t = re.sub(r"^\[[^\]]*\]\s*", "", t)
    t = strip_source_attribution(t)
    return t.strip()


def fetch_jp(per_category: int, dedupe_file: Path | None, seed_files: list[Path]) -> list[dict]:
    """抓取日本源，去重后按分类各取 per_category 条，返回 [{title, category, site}]。"""
    used_norm: set[str] = set()
    used_tok: list[set] = []
    for sf in seed_files:
        if sf.exists():
            try:
                for t in json.loads(sf.read_text(encoding="utf-8")):
                    used_norm.add(_norm(t))
                    used_tok.append(_toks(t))
            except Exception:  # noqa: BLE001
                pass

    picked_norm: set[str] = set()
    picked_tok: list[set] = []

    def dup(title: str) -> bool:
        n = _norm(title)
        if n in used_norm or n in picked_norm:
            return True
        tt = _toks(title)
        for ot in used_tok + picked_tok:
            if tt and len(tt & ot) / len(tt) >= 0.7:
                return True
        return False

    # 每源多取留足冗余（去重/分类截断后仍够用）
    per_site = max(per_category * 3, per_category + 2)
    raw: dict[str, list[dict]] = {}
    for site, (cat, url) in JP_SOURCES.items():
        try:
            items = _rss_items(url, site, per_site)
        except Exception as e:  # noqa: BLE001
            print(f"[jp_news] {site} ERR: {e}", file=sys.stderr)
            continue
        kept = []
        for it in items:
            if len(kept) >= per_site:
                break
            title = clean_title(it["title"], site)
            if len(title) < 8 or dup(title):
                continue
            picked_norm.add(_norm(title))
            picked_tok.append(_toks(title))
            kept.append({"title": title, "category": cat, "site": site})
        raw[site] = kept
        print(f"[jp_news] {site:12s} ({cat:7s}): {len(kept)} items", file=sys.stderr)

    # 按分类截断到 per_category，源内交错保证站点多样性
    rows: list[dict] = []
    by_cat: dict[str, list[dict]] = {}
    for cat in ("tech", "finance", "ent"):
        cat_items = [r for r in raw.values() for r in r if r["category"] == cat]
        # 同一分类内 round-robin 交错各站点
        per_site_pool: dict[str, list[dict]] = {}
        for r in cat_items:
            per_site_pool.setdefault(r["site"], []).append(r)
        interleaved, si = [], 0
        keys = list(per_site_pool.keys())
        while any(per_site_pool.values()):
            k = keys[si % len(keys)]
            if per_site_pool.get(k):
                interleaved.append(per_site_pool[k].pop(0))
            si += 1
        by_cat[cat] = interleaved[:per_category]

    if dedupe_file is not None:
        merged = sorted(used_norm | picked_norm)
        dedupe_file.parent.mkdir(parents=True, exist_ok=True)
        dedupe_file.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return [r for cat in ("tech", "finance", "ent") for r in by_cat[cat]]


def build_caption(title: str, cat: str, persona: str, seen: set) -> str:
    tag = CAT_TAG[cat]
    templates = JP_TEMPLATES[cat].get(persona) or next(iter(JP_TEMPLATES[cat].values()))
    order = list(range(len(templates)))
    random.shuffle(order)
    for ti in order:
        cap = templates[ti].format(title=title, tag=tag).replace("  ", " ").strip()
        if cap not in seen:
            seen.add(cap)
            return cap
    base = templates[0].format(title=title, tag=tag).strip()
    i, cap = 2, base
    while cap in seen:
        cap = f"{base} ({i})"
        i += 1
    seen.add(cap)
    return cap


def persona_for(cat: str, idx: int) -> str:
    roles = list(JP_TEMPLATES[cat].keys())
    return roles[idx % len(roles)]


def load_accounts(path: Path, n: int) -> list[dict]:
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    accts = []
    for r in rows:
        e = (r.get("邮箱") or r.get("email") or "").strip()
        p = (r.get("密码") or r.get("password") or "").strip()
        nick = (r.get("昵称") or r.get("nickname") or "").strip()
        if e and p:
            accts.append({"email": e, "password": p, "nick": nick})
    if n > 0 and len(accts) > n:
        accts = random.sample(accts, n)
    return accts


def _run(cmd, env_extra=None):
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main() -> int:
    _u8()
    ap = argparse.ArgumentParser(
        description="日本资讯新闻一键发布（科技/财经/娱乐，日文文案，纯文本）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_jp_news_3.csv")
    ap.add_argument("--per-category", type=int, default=3,
                    help="每个分类（科技/财经/娱乐）取几条资讯")
    ap.add_argument("--num-accounts", type=int, default=0, help="0=使用 CSV 内全部账号")
    ap.add_argument("--dedupe-file", default="state/seen_jp_news.json")
    ap.add_argument("--seed-dedupe", default="state/seen_tech_jp.json,state/seen_tech_jp2.json",
                    help="历史去重账本（逗号分隔），避免与旧批次重复")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--login-spacing", type=float, default=2.5)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="jp_news_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    acc_path = ROOT / args.accounts_csv
    if not acc_path.exists():
        print(f"[jp_news] 账号 CSV 不存在: {acc_path}", file=sys.stderr)
        return 2
    accts = load_accounts(acc_path, args.num_accounts)
    if not accts:
        print("[jp_news] 未能加载任何账号", file=sys.stderr)
        return 2

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    moments = wd / f"moments_jp_news_{ts}.csv"

    ded = ROOT / args.dedupe_file
    seeds = [ROOT / s for s in args.seed_dedupe.split(",") if s.strip()]

    # ---- Step 1: 采集 ----
    print(f"=== Step 1/3: 采集日本资讯（科技/财经/娱乐，各 {args.per_category} 条）===")
    rows = fetch_jp(args.per_category, ded, seeds)
    if not rows:
        print("[jp_news] 未采集到任何资讯，终止。", file=sys.stderr)
        return 1
    # 跨分类交错，保证三个分类均衡分配
    by_cat: dict = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    interleaved, ci = [], 0
    cats = ["tech", "finance", "ent"]
    while any(by_cat.values()):
        c = cats[ci % len(cats)]
        if by_cat.get(c):
            interleaved.append(by_cat[c].pop(0))
        ci += 1
    rows = interleaved
    print(f"[jp_news] 采集到 {len(rows)} 条（去重后）")

    # ---- Step 2: 文案 ----
    print("=== Step 2/3: 日文第一人称文案（全局不重复）===")
    seen_caps = load_used_captions(ROOT / CAPTION_DEDUPE_FILE)
    per_cat_idx: Counter = Counter()
    out_rows = []
    for i, r in enumerate(rows):
        cat = r["category"]
        persona = persona_for(cat, per_cat_idx[cat])
        per_cat_idx[cat] += 1
        content = build_caption(r["title"], cat, persona, seen_caps)
        out_rows.append({
            "content": content, "visibility": 0, "room_id": "", "image_urls": "",
            "location_name": "", "location_address": "", "location_lat": "",
            "location_lon": "", "_site": r["site"], "_tag": cat, "_lang": "ja",
        })
        if i < 15:
            acct = accts[i % len(accts)]
            print(f"  #{i+1} [{(acct['nick'] or acct['email'])[:12]} /{cat}/ {persona}] {content[:60]}")
    print(f"[jp_news] 分类分布: {dict(Counter(r['_tag'] for r in out_rows))}")
    save_used_captions(seen_caps, ROOT / CAPTION_DEDUPE_FILE)

    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_site", "_tag", "_lang"]
    with moments.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    print(f"[jp_news] moments 就绪：{len(out_rows)} 条 → {moments}")

    if args.skip_publish:
        print("\n[jp_news] --skip-publish，仅产出素材：", moments)
        return 0

    # ---- Step 3: 发布 ----
    print("\n=== Step 3/3: 发布（纯文本，media_info type=text）===")
    print(f"  账号 CSV : {acc_path}\n  素材条数 : {len(out_rows)}  并发: {args.concurrency}")
    if not args.yes:
        if input("  确认发布真实帖子？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[jp_news] 已取消。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_path), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--login-spacing", str(args.login_spacing),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd, env_extra={"POST_CROP_BOTTOM_HOSTS": ""})
    if rc != 0:
        print("[jp_news] 发布返回非零，请查看 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[jp_news] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
