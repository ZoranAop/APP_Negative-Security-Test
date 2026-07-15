#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_us_science.py — 美国科学机构图文多源采集（NASA/NSF/NIST/NOAA/NIH/Energy）

从6个美国官方科学机构采集最新图文新闻，产出带图片的 moments CSV。
支持图文发帖（每帖1张图片+英文配文）。

来源：
    nasa     NASA                 https://www.nasa.gov/feed/           (RSS)
    nsf      NSF                  https://www.nsf.gov/rss/rss_www_news.xml (RSS)
    nist     NIST                 https://www.nist.gov/news-events/news/rss.xml (RSS)
    energy   Dept. of Energy      https://www.energy.gov/rss.xml       (RSS)
    noaa     NOAA                 https://www.noaa.gov/news            (HTML)
    nih      NIH                  https://www.nih.gov/news-events/news-releases (HTML)

去重：--dedupe-file 跨批次记录已采集标题，自动跳过不重复。

用法：
    py -3 scripts/fetch_us_science.py --per-site 3 --output us_science_raw.csv
    py -3 scripts/fetch_us_science.py --sources nasa,nsf,nist --per-site 5 --output out.csv
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

# Ensure UTF-8 stdout on Windows
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
    upgrade_image_url,
    is_high_quality,
    fetch_detail_page_image,
)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

ALL_SOURCES = ["nasa", "nsf", "nist", "energy", "noaa", "nih"]

SITE_INFO = {
    "nasa": {"name": "NASA", "url": "https://www.nasa.gov/feed/", "fmt": "rss"},
    "nsf": {"name": "NSF", "url": "https://www.nsf.gov/rss/rss_www_news.xml", "fmt": "rss"},
    "nist": {"name": "NIST", "url": "https://www.nist.gov/news-events/news/rss.xml", "fmt": "rss"},
    "energy": {"name": "Dept. of Energy", "url": "https://www.energy.gov/rss.xml", "fmt": "rss"},
    "noaa": {"name": "NOAA", "url": "https://www.noaa.gov/news", "fmt": "html"},
    "nih": {"name": "NIH", "url": "https://www.nih.gov/news-events/news-releases", "fmt": "html"},
}


def _get(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text


def _extract_rss_image(item_xml: str) -> str:
    """从RSS item中提取图片URL。"""
    # media:content
    m = re.search(r'<media:content[^>]*url="([^"]+)"', item_xml)
    if m:
        return m.group(1)
    # media:thumbnail
    m = re.search(r'<media:thumbnail[^>]*url="([^"]+)"', item_xml)
    if m:
        return m.group(1)
    # enclosure (image type)
    m = re.search(r'<enclosure[^>]*url="([^"]+)"[^>]*type="image', item_xml)
    if m:
        return m.group(1)
    # enclosure (any)
    m = re.search(r'<enclosure[^>]*url="([^"]+)"', item_xml)
    if m and re.search(r'\.(jpg|jpeg|png|webp|gif)', m.group(1), re.I):
        return m.group(1)
    # img src in description CDATA
    desc = re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>", item_xml, re.DOTALL)
    if desc:
        img = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp|gif))', desc.group(1))
        if img:
            return img.group(1)
    # img src in content:encoded CDATA
    content = re.search(r"<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>", item_xml, re.DOTALL)
    if content:
        img = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp|gif))', content.group(1))
        if img:
            return img.group(1)
    # img src anywhere in the item (fallback)
    img = re.search(r'(?:src|url)="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', item_xml)
    if img:
        return img.group(1)
    return ""


def _parse_rss(xml: str, want: int, seen: set) -> list[dict]:
    """解析RSS feed，提取标题+图片。"""
    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    out = []
    for item in items:
        if len(out) >= want:
            break
        title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item) or \
                  re.search(r"<title>(.*?)</title>", item)
        if not title_m:
            continue
        title = title_m.group(1).strip()
        # 去重
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen:
            continue
        img = _extract_rss_image(item)
        if not img:
            continue  # 只要有图片的
        seen.add(norm)
        out.append({"title": title, "image": img})
    return out


def _fetch_noaa_html(want: int, seen: set) -> list[dict]:
    """从NOAA新闻页HTML解析图文。"""
    try:
        html = _get("https://www.noaa.gov/news")
    except Exception as e:
        print(f"[warn] noaa HTML fetch failed: {e}")
        return []
    # 解析文章卡片：标题+图片
    out = []
    # 查找文章块
    cards = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
    for card in cards:
        if len(out) >= want:
            break
        title_m = re.search(r'<h[23][^>]*>(.*?)</h[23]>', card, re.DOTALL)
        img_m = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', card)
        if not title_m or not img_m:
            continue
        title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen or not title:
            continue
        seen.add(norm)
        out.append({"title": title, "image": img_m.group(1)})
    return out


def _fetch_nih_html(want: int, seen: set) -> list[dict]:
    """从NIH新闻页HTML解析图文。"""
    try:
        html = _get("https://www.nih.gov/news-events/news-releases")
    except Exception as e:
        print(f"[warn] nih HTML fetch failed: {e}")
        return []
    out = []
    # NIH新闻列表
    items = re.findall(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html)
    for link, title in items:
        if len(out) >= want:
            break
        title = re.sub(r"<[^>]+>", "", title).strip()
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen or not title:
            continue
        # NIH文章通常无缩略图，用NIH logo作为占位
        seen.add(norm)
        out.append({
            "title": title,
            "image": "https://www.nih.gov/sites/default/files/styles/featured_media_breakpoint-large/public/about-nih/2012-logo-design-contest-702x395.jpg",
        })
    return out


def fetch_site(site: str, want: int, seen: set) -> list[dict]:
    """从指定站点采集图文（RSS源进入详情页获取高清图）。"""
    info = SITE_INFO[site]
    if info["fmt"] == "rss":
        # 进入文章详情页获取高清图（二级页面 og:image）
        items = fetch_rss_with_detail_images(info["url"], want, seen, delay=0.5)
        return items
    elif site == "noaa":
        return _fetch_noaa_html(want, seen)
    elif site == "nih":
        return _fetch_nih_html(want, seen)
    return []


def main() -> int:
    ap = argparse.ArgumentParser(
        description="US Science agencies image+text fetcher (NASA/NSF/NIST/NOAA/NIH/Energy)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--sources", default=",".join(ALL_SOURCES),
                    help="逗号分隔来源（可选: nasa,nsf,nist,energy,noaa,nih）")
    ap.add_argument("--per-site", type=int, default=3, help="每站取多少条")
    ap.add_argument("--dedupe-file", default="state/seen_us_science.json",
                    help="去重档路径")
    ap.add_argument("--output", required=True, help="输出CSV路径")
    args = ap.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    invalid = [s for s in sources if s not in SITE_INFO]
    if invalid:
        print(f"[ERROR] unknown sources: {invalid}. Available: {list(SITE_INFO.keys())}")
        return 1

    # 加载去重档
    dedupe_path = ROOT / args.dedupe_file
    dedupe_path.parent.mkdir(parents=True, exist_ok=True)
    seen: set = set()
    if dedupe_path.exists():
        try:
            data = json.loads(dedupe_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                seen = set(data)
            elif isinstance(data, dict):
                seen = set(data.get("used", data.get("titles", [])))
        except Exception:
            pass
    print(f"[us_science] dedupe: {dedupe_path.name} ({len(seen)} known)")

    all_items = []
    for site in sources:
        items = fetch_site(site, args.per_site, seen)
        for it in items:
            it["_site"] = site
        all_items.extend(items)
        print(f"[us_science] {site}: {len(items)} items with images")
        time.sleep(0.3)

    if not all_items:
        print("[ERROR] no items fetched")
        return 1

    # 写CSV
    out_path = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site"]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for it in all_items:
            w.writerow({
                "content": it["title"],
                "visibility": "0", "room_id": "",
                "image_urls": it["image"],
                "location_name": "", "location_address": "",
                "location_lat": "", "location_lon": "",
                "_source": "us_science",
                "_site": it["_site"],
            })

    # 保存去重档
    dedupe_path.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    dist = Counter(it["_site"] for it in all_items)
    print(f"[OK] wrote {len(all_items)} items → {out_path}")
    print(f"[OK] source distribution: {dict(dist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
