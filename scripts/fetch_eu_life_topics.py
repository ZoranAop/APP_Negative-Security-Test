#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_eu_life_topics.py — European/Western lifestyle image+text fetcher
covering 4 topics: Life, Art, Travel, Cars.

Sources (all English-language RSS/Atom feeds):
    life:
        refinery29    Refinery29       https://www.refinery29.com/en-us/rss.xml
        theeverygirl  The Everygirl    https://theeverygirl.com/feed/
        buzzfeed      BuzzFeed         https://www.buzzfeed.com/index.xml
    art:
        artnews       ArtNews           https://www.artnews.com/feed/
        hyperallergic Hyperallergic    https://hyperallergic.com/feed/
        artforum      Artforum          https://www.artforum.com/rss.xml
    travel:
        lonelyplanet  Lonely Planet     https://www.lonelyplanet.com/rss/articles.xml
        conde_nast_t  Condé Nast Traveler https://www.cntraveler.com/feed/rss
        travel_leisure Travel + Leisure  https://www.travelandleisure.com/feeds/rss/all
    cars:
        motor1        Motor1            https://www.motor1.com/rss/
        topgear       Top Gear          https://www.topgear.com/feed
        caranddriver  Car and Driver    https://www.caranddriver.com/feed/

Usage:
    py -3 scripts/fetch_eu_life_topics.py --per-site 3 --output eu_life_raw.csv
    py -3 scripts/fetch_eu_life_topics.py --topics life,travel --per-site 5 --output out.csv
"""
from __future__ import annotations

import argparse
import csv
import html
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

TOPIC_SOURCES = {
    "life": ["refinery29", "theeverygirl", "buzzfeed", "apartments"],
    "art": ["artnews", "hyperallergic", "designboom"],
    "travel": ["conde_nast_t", "outside_travel", "travel_aol"],
    "cars": ["carscoops", "motor_trend", "roadshow"],
}

SITE_INFO = {
    "refinery29":     {"name": "Refinery29",          "url": "https://www.refinery29.com/en-us/rss.xml"},
    "theeverygirl":   {"name": "The Everygirl",       "url": "https://theeverygirl.com/feed/"},
    "buzzfeed":       {"name": "BuzzFeed",            "url": "https://www.buzzfeed.com/index.xml"},
    "apartments":     {"name": "Apartment Therapy",   "url": "https://www.apartmenttherapy.com/feed"},
    "artnews":        {"name": "ArtNews",             "url": "https://www.artnews.com/feed/"},
    "hyperallergic":  {"name": "Hyperallergic",       "url": "https://hyperallergic.com/feed/"},
    "designboom":     {"name": "Designboom",          "url": "https://www.designboom.com/feed/"},
    "conde_nast_t":   {"name": "Condé Nast Traveler", "url": "https://www.cntraveler.com/feed/rss"},
    "outside_travel": {"name": "Outside",             "url": "https://www.outsideonline.com/feed/"},
    "travel_aol":     {"name": "AOL Travel",          "url": "https://www.aol.com/travel/feed/"},
    "carscoops":      {"name": "Carscoops",           "url": "https://www.carscoops.com/feed/"},
    "motor_trend":    {"name": "Motor Trend",         "url": "https://www.motortrend.com/feed/"},
    "roadshow":       {"name": "Roadshow",            "url": "https://www.cnet.com/roadshow/rss/"},
}


def _get(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text


def _extract_image(item_xml: str) -> str:
    """Extract image URL from RSS/Atom item XML."""
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

    for tag in ["description", "content:encoded", "content", "summary"]:
        block = re.search(
            rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", item_xml, re.DOTALL
        ) or re.search(rf"<{tag}>(.*?)</{tag}>", item_xml, re.DOTALL)
        if block:
            img = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', block.group(1))
            if img:
                return img.group(1)

    m = re.search(r'(?:src|url|href)="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', item_xml)
    if m:
        return m.group(1)
    return ""


def _is_english(text: str) -> bool:
    """Return True if text is predominantly English (no CJK characters)."""
    if not text:
        return False
    cjk = len(re.findall(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\u3400-\u4dbf]", text))
    return cjk == 0


def _parse_rss(xml: str, want: int, seen: set) -> list[dict]:
    """Parse RSS/Atom feed, extract title + image."""
    items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
    if not items:
        items = re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL)

    out = []
    for item in items:
        if len(out) >= want:
            break
        title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item) or \
                  re.search(r"<title[^>]*>(.*?)</title>", item)
        if not title_m:
            continue
        title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
        title = html.unescape(title)
        if not title:
            continue
        # Skip non-English titles (CJK contamination)
        if not _is_english(title):
            continue
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen:
            continue
        img = _extract_image(item)
        if not img:
            continue
        seen.add(norm)
        out.append({"title": title, "image": img})
    return out


def fetch_site(site: str, want: int, seen: set) -> list[dict]:
    """Fetch from a site using detail-page image extraction."""
    info = SITE_INFO.get(site)
    if not info:
        return []
    try:
        items = fetch_rss_with_detail_images(info["url"], want, seen, delay=0.5)
        # Post-process: decode HTML entities and filter non-English titles
        cleaned = []
        for it in items:
            title = html.unescape(it.get("title", ""))
            if not _is_english(title):
                continue
            it["title"] = title
            cleaned.append(it)
        return cleaned
    except Exception as e:
        print(f"[warn] {site} failed: {e}")
        return []


def main() -> int:
    ap = argparse.ArgumentParser(
        description="EU Life Topics fetcher (Life/Art/Travel/Cars)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--topics", default="life,art,travel,cars",
                    help="Comma-separated topics")
    ap.add_argument("--per-site", type=int, default=3, help="Items per site")
    ap.add_argument("--dedupe-file", default="state/seen_eu_life_topics.json")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    topics = [t.strip() for t in args.topics.split(",") if t.strip()]

    dedupe_path = ROOT / args.dedupe_file
    dedupe_path.parent.mkdir(parents=True, exist_ok=True)
    seen: set = set()
    if dedupe_path.exists():
        try:
            data = json.loads(dedupe_path.read_text(encoding="utf-8"))
            seen = set(data) if isinstance(data, list) else set(data.get("used", []))
        except Exception:
            pass
    print(f"[eu_life_topics] dedupe: {dedupe_path.name} ({len(seen)} known)")

    all_items = []
    for topic in topics:
        sites = TOPIC_SOURCES.get(topic, [])
        for site in sites:
            items = fetch_site(site, args.per_site, seen)
            for it in items:
                it["_site"] = site
                it["_topic"] = topic
            all_items.extend(items)
            print(f"[eu_life_topics] {topic}/{site}: {len(items)} items")
            time.sleep(0.3)

    if not all_items:
        print("[ERROR] no items fetched")
        return 1

    out_path = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_topic", "_media_type"]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for it in all_items:
            w.writerow({
                "content": it["title"], "visibility": "0", "room_id": "",
                "image_urls": it.get("image", ""),
                "location_name": "", "location_address": "",
                "location_lat": "", "location_lon": "",
                "_source": "eu_life_topics", "_site": it["_site"],
                "_topic": it["_topic"],
                "_media_type": it.get("_media_type", "image" if it.get("image") else "text"),
            })

    dedupe_path.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    topic_dist = Counter(it["_topic"] for it in all_items)
    site_dist = Counter(it["_site"] for it in all_items)
    print(f"[OK] wrote {len(all_items)} items -> {out_path}")
    print(f"[OK] topic distribution: {dict(topic_dist)}")
    print(f"[OK] site distribution: {dict(site_dist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
