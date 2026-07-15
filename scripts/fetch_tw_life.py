#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_tw_life.py — 台灣生活 圖文多源採集

從台灣生活類媒體採集最新圖文新聞，產出帶圖片的 moments CSV。

來源：
    yahoo_life   Yahoo奇摩生活    https://tw.news.yahoo.com/rss/life       (RSS)
    ltn_life     自由時報生活     https://news.ltn.com.tw/rss/life.xml     (RSS)
    udn_life     聯合報生活       https://udn.com/rssfeed/news/2/6638      (RSS)
    ettoday      ETtoday生活      https://www.ettoday.net/                 (HTML)
    nownews      NOWnews生活      https://www.nownews.com/cat/life/        (HTML)

用法：
    py -3 scripts/fetch_tw_life.py --per-site 5 --output tw_life_raw.csv
    py -3 scripts/fetch_tw_life.py --sources yahoo_life,ltn_life --per-site 8 --output out.csv
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

ALL_SOURCES = ["yahoo_life", "ltn_life", "udn_life"]

SITE_INFO = {
    "yahoo_life": {"name": "Yahoo奇摩生活", "url": "https://tw.news.yahoo.com/rss/life", "fmt": "rss"},
    "ltn_life":   {"name": "自由時報生活",  "url": "https://news.ltn.com.tw/rss/life.xml", "fmt": "rss"},
    "udn_life":   {"name": "聯合報生活",    "url": "https://udn.com/rssfeed/news/2/6638", "fmt": "rss"},
}


def fetch_site(site: str, want: int, seen: set) -> list[dict]:
    info = SITE_INFO.get(site)
    if not info:
        return []
    return fetch_rss_with_detail_images(info["url"], want, seen, delay=0.5)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Taiwan Life media image+text fetcher",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    ap.add_argument("--per-site", type=int, default=5)
    ap.add_argument("--dedupe-file", default="state/seen_tw_life.json")
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
    print(f"[tw_life] dedupe: {dedupe_path.name} ({len(seen)} known)")

    all_items = []
    for site in sources:
        items = fetch_site(site, args.per_site, seen)
        for it in items:
            it["_site"] = site
        all_items.extend(items)
        print(f"[tw_life] {site}: {len(items)} items")
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
                "_source": "tw_life", "_site": it["_site"],
                "_media_type": it.get("_media_type", "image" if it.get("image") else "text"),
            })

    dedupe_path.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    dist = Counter(it["_site"] for it in all_items)
    media_dist = Counter(it.get("_media_type", "?") for it in all_items)
    print(f"[OK] wrote {len(all_items)} items -> {out_path}")
    print(f"[OK] distribution: {dict(dist)}")
    print(f"[OK] media types: {dict(media_dist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
