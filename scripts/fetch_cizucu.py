#!/usr/bin/env python3
"""
fetch_cizucu.py — Fetch photos from cizucu.com (刺猬社区, a photography
community) and write a moments CSV where each THEME chunk becomes ONE
MULTI-IMAGE post. Playwright-based (the site is a JS-rendered Next.js SPA).

Source (public, no login)
    Home / module tag pages:  https://www.cizucu.com/zh-cn/explore/tags/<主题>
        e.g. .../tags/人像  .../tags/街拍  .../tags/风光  .../tags/城市 ...
    Photo detail (二级页):     https://www.cizucu.com/zh-cn/photos/<photoId>
    Full-size image (直链):    https://cdn.cizucu.com/images/photos/<photoId>.jpg
        (public CDN, no Referer needed — verified.)

How it works ("在模块中选 → 进二级/三级页面")
    1. Open each theme/module tag page (二级页).
    2. Scroll to lazy-load more photos (三级/更多), collecting photoId in order.
    3. Map photoId -> CDN full-size URL, de-dupe globally, and pack every
       ``--imgs-per-post`` photos into one multi-image moments row per theme.

Each row's ``content`` is the theme's Chinese label (a scene/topic hint) — rewrite
later with ``caption_multilang.py`` for subject-first captions. The extra
``_theme`` column records which module the photos came from.

Watermark
    cizucu photos are photographers' own works with no burned-in watermark, so
    NO bottom-crop is applied (cizucu is not in POST_CROP_BOTTOM_HOSTS).

Output CSV columns (compatible with post_moments.py / publish_from_tokens.py)
    content,visibility,room_id,image_urls,
    location_name,location_address,location_lat,location_lon,_source,_theme
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

BASE = os.getenv("CIZUCU_BASE", "https://www.cizucu.com")
CDN = os.getenv("CIZUCU_CDN", "https://cdn.cizucu.com") + "/images/photos/{}.jpg"
UA = os.getenv("CIZUCU_USER_AGENT",
               "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# 网站模块 / 主题标签（explore tags）-> 中文标签（用于 URL 与场景提示）
# key 为稳定的英文别名（供 --themes 使用），value 为站点上的中文 tag。
THEME_TAGS = {
    "portrait": "人像",
    "street": "街拍",
    "scenery": "风光",
    "city": "城市",
    "nature": "自然",
    "architecture": "建筑",
    "travel": "旅行摄影",
    "bw": "黑白",
    "film": "胶片",
    "daily": "日常",
    "humanity": "人文",
    "light": "光影",
    "sky": "天空",
    "mobile": "手机摄影",
    "casual": "随手拍",
    "snap": "扫街",
    "china": "中国",
}

_ID_RE = re.compile(r'/zh-cn/photos/([A-Za-z0-9]{18,24})')
_CDN_RE = re.compile(r'images/photos/([A-Za-z0-9]{18,24})')


def _ensure_utf8_stdout():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


def collect_theme_ids(page, tag_cn: str, target: int, scrolls: int, settle_ms: int = 1400) -> list[str]:
    """Open a theme tag page (二级页), scroll to lazy-load (三级/更多), collect
    photoId preserving order and de-duplicating."""
    url = f"{BASE}/zh-cn/explore/tags/{quote(tag_cn)}"
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3500)
    # 等首屏图片渲染（懒加载站点首屏可能慢）
    for _ in range(6):
        if _CDN_RE.search(page.content()) or _ID_RE.search(page.content()):
            break
        page.mouse.wheel(0, 1500)
        page.wait_for_timeout(1800)

    seen: list[str] = []
    seen_set: set[str] = set()

    def harvest():
        html = page.content()
        for m in (_ID_RE, _CDN_RE):
            for pid in m.findall(html):
                if pid not in seen_set:
                    seen_set.add(pid)
                    seen.append(pid)

    harvest()
    for _ in range(scrolls):
        if len(seen) >= target:
            break
        page.mouse.wheel(0, 5000)
        page.wait_for_timeout(settle_ms)
        harvest()
    return seen[:target]


def _load_dedupe(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, list):
            return {str(x) for x in d}
    except Exception:
        pass
    return set()


def _save_dedupe(path: str | None, seen: set[str]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(
        description="Fetch cizucu.com themed photos → multi-image moments CSV (Playwright)")
    ap.add_argument("--themes",
                    default="portrait,street,scenery,city,nature,architecture,film,daily",
                    help="逗号分隔的主题 key（见 THEME_TAGS），每个主题=一个网站模块")
    ap.add_argument("--posts", type=int, default=0,
                    help="总帖数上限（0=不限，按主题产满为止）")
    ap.add_argument("--posts-per-theme", type=int, default=3, help="每个主题产出的帖子数")
    ap.add_argument("--imgs-per-post", type=int, default=6, help="每帖图片数（后端上限 9）")
    ap.add_argument("--min-imgs", type=int, default=4, help="少于 N 张图的主题块跳过")
    ap.add_argument("--scrolls", type=int, default=10, help="每个主题页滚动次数（懒加载深度）")
    ap.add_argument("--dedupe-file", default=None,
                    help="累计已用 photoId JSON（跨批次防重复=已发布过的不再选）")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[cizucu] 需要 Playwright：pip install playwright ; python -m playwright install chromium",
              file=sys.stderr)
        return 2

    used = _load_dedupe(args.dedupe_file)
    print(f"[cizucu] 已用 photoId 记录: {len(used)}", file=sys.stderr)

    themes = [t.strip() for t in args.themes.split(",") if t.strip()]
    rows: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(user_agent=UA, viewport={"width": 1440, "height": 1000})
        for tk in themes:
            if args.posts and len(rows) >= args.posts:
                break
            tag_cn = THEME_TAGS.get(tk)
            if not tag_cn:
                print(f"[cizucu] 未知主题 {tk}，跳过（可选：{','.join(THEME_TAGS)}）", file=sys.stderr)
                continue
            need = args.posts_per_theme * args.imgs_per_post + 8
            try:
                ids = collect_theme_ids(pg, tag_cn, need, args.scrolls)
            except Exception as e:
                print(f"[cizucu] {tk}({tag_cn}) 采集异常: {e}", file=sys.stderr)
                continue
            fresh = [i for i in ids if i not in used]
            print(f"[cizucu] {tk}({tag_cn}): 收集 {len(ids)} / 去重后可用 {len(fresh)}", file=sys.stderr)
            made = 0
            while made < args.posts_per_theme and len(fresh) >= args.min_imgs:
                if args.posts and len(rows) >= args.posts:
                    break
                chunk = fresh[:args.imgs_per_post]
                fresh = fresh[args.imgs_per_post:]
                for i in chunk:
                    used.add(i)
                rows.append({
                    "content": tag_cn,  # 场景/主题提示，稍后 caption_multilang 改写
                    "visibility": 0,
                    "room_id": "",
                    "image_urls": ",".join(CDN.format(i) for i in chunk),
                    "location_name": "", "location_address": "",
                    "location_lat": "", "location_lon": "",
                    "_source": "cizucu",
                    "_theme": tk,
                })
                made += 1
                print(f"[cizucu]  + {tk} post#{made} imgs={len(chunk)}", file=sys.stderr)
            time.sleep(0.4)
        b.close()

    if not rows:
        print("[warn] no posts produced", file=sys.stderr)
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_theme"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    _save_dedupe(args.dedupe_file, used)
    total = sum(len(r["image_urls"].split(",")) for r in rows)
    print(f"[OK] wrote {len(rows)} multi-image posts ({total} imgs, all unique) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
