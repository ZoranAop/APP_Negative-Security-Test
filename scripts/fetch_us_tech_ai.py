#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_us_tech_ai.py — 科技&AI&美国 图文多源采集（13个科技/AI/国家实验室媒体）

从顶级科技媒体和美国国家实验室采集最新图文新闻，产出带图片的 moments CSV。

来源（--sources，逗号分隔；默认全部可稳定RSS的9源）：
  techcrunch    TechCrunch          https://techcrunch.com/feed/
  theverge      The Verge           https://www.theverge.com/rss/index.xml
  wired         WIRED               https://www.wired.com/feed/rss
  arstechnica   Ars Technica        https://feeds.arstechnica.com/arstechnica/index
  mittr         MIT Tech Review     https://www.technologyreview.com/feed/
  ieee_spectrum IEEE Spectrum        https://spectrum.ieee.org/feeds/feed.rss
  venturebeat   VentureBeat         https://venturebeat.com/feed/
  anl           Argonne Nat'l Lab   https://www.anl.gov/rss.xml
  jpl           NASA JPL            https://www.jpl.nasa.gov/feeds/news

HTML解析源（需额外处理）：
  ai_news       AI News             https://www.artificialintelligence-news.com/
  llnl          LLNL                https://www.llnl.gov/news/lab-report
  lanl          LANL                https://www.lanl.gov/media/news
  ornl          ORNL                https://www.ornl.gov/

用法：
    py -3 scripts/fetch_us_tech_ai.py --per-site 3 --output tech_ai_raw.csv
    py -3 scripts/fetch_us_tech_ai.py --sources techcrunch,wired,arstechnica --per-site 5 --output out.csv
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
    upgrade_image_url,
    is_high_quality,
)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

ALL_SOURCES = ["techcrunch", "theverge", "wired", "arstechnica", "mittr",
               "ieee_spectrum", "venturebeat", "anl", "jpl"]

SITE_INFO = {
    "techcrunch":    {"name": "TechCrunch",       "url": "https://techcrunch.com/feed/"},
    "theverge":      {"name": "The Verge",        "url": "https://www.theverge.com/rss/index.xml"},
    "wired":         {"name": "WIRED",            "url": "https://www.wired.com/feed/rss"},
    "arstechnica":   {"name": "Ars Technica",     "url": "https://feeds.arstechnica.com/arstechnica/index"},
    "mittr":         {"name": "MIT Tech Review",  "url": "https://www.technologyreview.com/feed/"},
    "ieee_spectrum": {"name": "IEEE Spectrum",    "url": "https://spectrum.ieee.org/feeds/feed.rss"},
    "venturebeat":   {"name": "VentureBeat",     "url": "https://venturebeat.com/feed/"},
    "anl":           {"name": "Argonne Nat'l Lab","url": "https://www.anl.gov/rss.xml"},
    "jpl":           {"name": "NASA JPL",         "url": "https://www.jpl.nasa.gov/feeds/news"},
}


def _get(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text


def _extract_image(item_xml: str) -> str:
    """从RSS item中提取图片URL（多种格式兼容）。"""
    patterns = [
        r'<media:content[^>]*url="([^"]+)"',
        r'<media:thumbnail[^>]*url="([^"]+)"',
        r'<enclosure[^>]*url="([^"]+\.(?:jpg|jpeg|png|webp|gif))"',
        r'<image>[^<]*<url>([^<]+)</url>',
    ]
    for pat in patterns:
        m = re.search(pat, item_xml)
        if m:
            return m.group(1)

    # 从 description/content 中的 img src 提取
    for tag in ["description", "content:encoded", "content"]:
        block = re.search(
            rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", item_xml, re.DOTALL
        ) or re.search(rf"<{tag}>(.*?)</{tag}>", item_xml, re.DOTALL)
        if block:
            img = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', block.group(1))
            if img:
                return img.group(1)

    # fallback: 任何 url 属性含图片扩展名
    m = re.search(r'(?:src|url|href)="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', item_xml)
    if m:
        return m.group(1)
    return ""


def _parse_rss(xml: str, want: int, seen: set) -> list[dict]:
    """解析RSS/Atom feed，提取标题+图片。"""
    # RSS items
    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    # Atom entries
    if not items:
        items = re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL)

    out = []
    for item in items:
        if len(out) >= want:
            break
        # 标题
        title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item) or \
                  re.search(r"<title[^>]*>(.*?)</title>", item)
        if not title_m:
            continue
        title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
        if not title:
            continue

        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen:
            continue

        img = _extract_image(item)
        if not img:
            continue  # 只要有图片的

        seen.add(norm)
        out.append({"title": title, "image": img})
    return out


def fetch_site(site: str, want: int, seen: set) -> list[dict]:
    """从指定站点采集图文（进入详情页获取高清图片）。"""
    info = SITE_INFO.get(site)
    if not info:
        return []
    try:
        # 进入文章详情页获取高清图（二级/三级页面 og:image）
        items = fetch_rss_with_detail_images(info["url"], want, seen, delay=0.5)
        return items
    except Exception as e:
        print(f"[warn] {site} failed: {e}")
        return []


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Tech & AI & US media image+text fetcher",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--sources", default=",".join(ALL_SOURCES),
                    help="逗号分隔来源")
    ap.add_argument("--per-site", type=int, default=3, help="每站取多少条")
    ap.add_argument("--dedupe-file", default="state/seen_us_tech_ai.json")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    # 加载去重档
    dedupe_path = ROOT / args.dedupe_file
    dedupe_path.parent.mkdir(parents=True, exist_ok=True)
    seen: set = set()
    if dedupe_path.exists():
        try:
            data = json.loads(dedupe_path.read_text(encoding="utf-8"))
            seen = set(data) if isinstance(data, list) else set(data.get("used", []))
        except Exception:
            pass
    print(f"[tech_ai] dedupe: {dedupe_path.name} ({len(seen)} known)")

    all_items = []
    for site in sources:
        items = fetch_site(site, args.per_site, seen)
        for it in items:
            it["_site"] = site
        all_items.extend(items)
        print(f"[tech_ai] {site}: {len(items)} items")
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
                "content": it["title"], "visibility": "0", "room_id": "",
                "image_urls": it["image"],
                "location_name": "", "location_address": "",
                "location_lat": "", "location_lon": "",
                "_source": "us_tech_ai", "_site": it["_site"],
            })

    # 保存去重档
    dedupe_path.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    dist = Counter(it["_site"] for it in all_items)
    print(f"[OK] wrote {len(all_items)} items -> {out_path}")
    print(f"[OK] distribution: {dict(dist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
