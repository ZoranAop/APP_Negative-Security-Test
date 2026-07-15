#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_jp_life.py — 日本生活 図文多源採集（macaroni/TRILL/hint-pot/grape/Pouch）

日本のライフスタイルメディアから最新記事を採集し、画像付き moments CSV を出力。

来源：
    grapee      grape(グレイプ)    https://grapee.jp/feed          (RSS)
    hintpot     hint-pot          https://hint-pot.jp/feed         (RSS)
    youpouch    Pouch(ポーチ)     https://youpouch.com/feed        (RSS)
    macaroni    macaroni          https://macaro-ni.jp/            (HTML)
    trilltrill  TRILL             https://trilltrill.jp/           (HTML)

用法：
    py -3 scripts/fetch_jp_life.py --per-site 5 --output jp_life_raw.csv
    py -3 scripts/fetch_jp_life.py --sources grapee,hintpot,youpouch --per-site 8 --output out.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
from pathlib import Path

import requests

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from image_quality import (  # noqa: E402
    fetch_rss_with_detail_images,
    fetch_detail_page_image,
    upgrade_image_url,
    is_high_quality,
)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

ALL_SOURCES = ["grapee", "hintpot", "youpouch", "macaroni", "trilltrill"]

SITE_INFO = {
    "grapee":     {"name": "grape",     "url": "https://grapee.jp/feed", "fmt": "rss"},
    "hintpot":    {"name": "hint-pot",  "url": "https://hint-pot.jp/feed", "fmt": "rss"},
    "youpouch":   {"name": "Pouch",     "url": "https://youpouch.com/feed", "fmt": "rss"},
    "macaroni":   {"name": "macaroni",  "url": "https://macaro-ni.jp/", "fmt": "html"},
    "trilltrill": {"name": "TRILL",     "url": "https://trilltrill.jp/", "fmt": "html"},
}


def _get(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text


def _fetch_html_site(base_url: str, want: int, seen: set) -> list[dict]:
    """从HTML首页解析文章列表，再进入详情页获取高清图。"""
    try:
        html = _get(base_url)
    except Exception as e:
        print(f"[warn] HTML fetch {base_url} failed: {e}")
        return []
    out = []
    # 提取文章链接+标题
    links = re.findall(r'<a[^>]*href="(' + re.escape(base_url.rstrip("/")) + r'/[^"]+)"[^>]*>', html)
    # 去重链接
    seen_links = set()
    unique_links = []
    for lk in links:
        if lk not in seen_links and "/tag/" not in lk and "/category/" not in lk:
            seen_links.add(lk)
            unique_links.append(lk)

    for link in unique_links[:want * 3]:  # 多取一些以防部分无图
        if len(out) >= want:
            break
        # 进入详情页获取图片和标题
        img = fetch_detail_page_image(link)
        if not img:
            continue
        # 从详情页获取标题
        try:
            detail_html = _get(link)
            title_m = re.search(r"<title[^>]*>(.*?)</title>", detail_html)
            title = title_m.group(1).strip() if title_m else ""
            # 清理标题后缀
            title = re.split(r"\s*[|｜\-–—]\s*", title)[0].strip()
        except Exception:
            title = link.split("/")[-1]
        if not title:
            continue
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen:
            continue
        seen.add(norm)
        out.append({"title": title, "image": upgrade_image_url(img)})
        time.sleep(0.5)
    return out


def fetch_site(site: str, want: int, seen: set) -> list[dict]:
    info = SITE_INFO.get(site)
    if not info:
        return []
    if info["fmt"] == "rss":
        return fetch_rss_with_detail_images(info["url"], want, seen, delay=0.5)
    else:
        return _fetch_html_site(info["url"], want, seen)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Japan Life media image+text fetcher (grape/hint-pot/Pouch/macaroni/TRILL)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    ap.add_argument("--per-site", type=int, default=5)
    ap.add_argument("--dedupe-file", default="state/seen_jp_life.json")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    dedupe_path = ROOT / args.dedupe_file
    dedupe_path.parent.mkdir(parents=True, exist_ok=True)
    seen: set = set()
    if dedupe_path.exists():
        try:
            data = json.loads(dedupe_path.read_text(encoding="utf-8"))
            seen = set(data) if isinstance(data, list) else set(data.get("used", []))
        except Exception:
            pass
    print(f"[jp_life] dedupe: {dedupe_path.name} ({len(seen)} known)")

    all_items = []
    for site in sources:
        items = fetch_site(site, args.per_site, seen)
        for it in items:
            it["_site"] = site
        all_items.extend(items)
        print(f"[jp_life] {site}: {len(items)} items")
        time.sleep(0.3)

    if not all_items:
        print("[ERROR] no items fetched")
        return 1

    out_path = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_media_type"]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for it in all_items:
            w.writerow({
                "content": it["title"], "visibility": "0", "room_id": "",
                "image_urls": it.get("image", ""),
                "location_name": "", "location_address": "",
                "location_lat": "", "location_lon": "",
                "_source": "jp_life", "_site": it["_site"],
                "_media_type": it.get("_media_type", "image" if it.get("image") else "text"),
            })

    dedupe_path.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    dist = Counter(it["_site"] for it in all_items)
    print(f"[OK] wrote {len(all_items)} items -> {out_path}")
    print(f"[OK] distribution: {dict(dist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
