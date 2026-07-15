#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_us_life.py — 美国生活 图文多源采集（USA Today / BuzzFeed / Martha Stewart）

从3个美国生活类媒体采集最新图文内容，产出带图片的 moments CSV。

来源：
    buzzfeed        BuzzFeed          https://www.buzzfeed.com/index.xml       (Atom)
    usatoday        USA Today         https://www.usatoday.com/               (HTML)
    marthastewart   Martha Stewart    https://www.marthastewart.com/          (HTML)

用法：
    py -3 scripts/fetch_us_life.py --per-site 5 --output us_life_raw.csv
    py -3 scripts/fetch_us_life.py --sources buzzfeed --per-site 10 --output out.csv
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

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

ALL_SOURCES = ["refinery29", "theeverygirl", "gq", "esquire", "buzzfeed", "usatoday", "marthastewart", "thrillist"]

SITE_INFO = {
    "refinery29":    {"name": "Refinery29",     "url": "https://www.refinery29.com/en-us/rss.xml", "fmt": "rss"},
    "theeverygirl":  {"name": "The Everygirl",  "url": "https://theeverygirl.com/feed/", "fmt": "rss"},
    "gq":            {"name": "GQ",             "url": "https://www.gq.com/feed/rss", "fmt": "rss"},
    "esquire":       {"name": "Esquire",        "url": "https://www.esquire.com/rss/all.xml/", "fmt": "rss"},
    "buzzfeed":      {"name": "BuzzFeed",       "url": "https://www.buzzfeed.com/us.xml", "fmt": "atom"},
    "usatoday":      {"name": "USA Today",      "url": "https://www.usatoday.com/", "fmt": "html"},
    "marthastewart": {"name": "Martha Stewart", "url": "https://www.marthastewart.com/", "fmt": "html"},
    "thrillist":     {"name": "Thrillist",      "url": "https://www.thrillist.com/", "fmt": "html"},
}


def _get(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text


def _fetch_buzzfeed(want: int, seen: set) -> list[dict]:
    """从BuzzFeed Atom feed采集图文。"""
    try:
        xml = _get("https://www.buzzfeed.com/index.xml")
    except Exception as e:
        print(f"[warn] buzzfeed fetch failed: {e}")
        return []
    entries = re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL)
    out = []
    for entry in entries:
        if len(out) >= want:
            break
        title_m = re.search(r"<title[^>]*>(.*?)</title>", entry)
        if not title_m:
            continue
        title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen or not title:
            continue
        # 图片从content或media中提取
        img = ""
        content_m = re.search(r"<content[^>]*>(.*?)</content>", entry, re.DOTALL)
        if content_m:
            decoded = content_m.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            img_m = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', decoded)
            if img_m:
                img = img_m.group(1)
        if not img:
            img_m = re.search(r'<media:thumbnail[^>]*url="([^"]+)"', entry)
            if img_m:
                img = img_m.group(1)
        if not img:
            img_m = re.search(r'(https?://(?:img\.buzzfeed|www\.buzzfeed)[^"<>\s]+\.(?:jpg|jpeg|png|webp))', entry)
            if img_m:
                img = img_m.group(1)
        if not img:
            continue
        seen.add(norm)
        out.append({"title": title, "image": img})
    return out


def _fetch_usatoday_html(want: int, seen: set) -> list[dict]:
    """从USA Today首页HTML解析图文。"""
    try:
        html = _get("https://www.usatoday.com/")
    except Exception as e:
        print(f"[warn] usatoday HTML failed: {e}")
        return []
    out = []
    # 寻找文章卡片（标题+图片组合）
    # USA Today 使用 data-ss-t 属性存标题，img用 srcset/src
    cards = re.findall(r'<a[^>]*href="(/story/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
    for href, inner in cards:
        if len(out) >= want:
            break
        # 提取标题文本
        title_parts = re.findall(r'>([^<]{10,})<', inner)
        title = title_parts[0].strip() if title_parts else ""
        if not title:
            continue
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen:
            continue
        # 提取图片
        img_m = re.search(r'(?:src|srcset)="(https?://[^"\s]+\.(?:jpg|jpeg|png|webp))', inner)
        if not img_m:
            continue
        img = img_m.group(1).split(" ")[0]  # srcset 取第一个
        seen.add(norm)
        out.append({"title": title, "image": img})
    return out


def _fetch_martha_html(want: int, seen: set) -> list[dict]:
    """从Martha Stewart首页HTML解析图文。"""
    try:
        html = _get("https://www.marthastewart.com/")
    except Exception as e:
        print(f"[warn] marthastewart HTML failed: {e}")
        return []
    out = []
    # Martha Stewart 文章卡片
    # 查找包含图片和标题的链接块
    blocks = re.findall(r'<a[^>]*href="(https://www\.marthastewart\.com/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
    for href, inner in blocks:
        if len(out) >= want:
            break
        img_m = re.search(r'(?:src|data-src)="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', inner)
        title_m = re.search(r'<span[^>]*>([^<]{10,})</span>', inner) or \
                  re.search(r'>([^<]{15,})<', inner)
        if not img_m or not title_m:
            continue
        title = title_m.group(1).strip()
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen:
            continue
        seen.add(norm)
        out.append({"title": title, "image": img_m.group(1)})
    return out


def _extract_rss_image(item_xml: str) -> str:
    """从RSS item中提取图片URL。"""
    patterns = [
        r'<media:content[^>]*url="([^"]+)"',
        r'<media:thumbnail[^>]*url="([^"]+)"',
        r'<enclosure[^>]*url="([^"]+\.(?:jpg|jpeg|png|webp|gif))"',
    ]
    for pat in patterns:
        m = re.search(pat, item_xml)
        if m:
            return m.group(1)
    for tag in ["description", "content:encoded", "content"]:
        block = re.search(
            rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", item_xml, re.DOTALL
        ) or re.search(rf"<{tag}>(.*?)</{tag}>", item_xml, re.DOTALL)
        if block:
            img = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', block.group(1))
            if img:
                return img.group(1)
    m = re.search(r'(?:src|url)="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', item_xml)
    if m:
        return m.group(1)
    return ""


def _parse_rss_feed(xml: str, want: int, seen: set) -> list[dict]:
    """解析RSS/Atom feed，提取标题+图片。"""
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
        if not title:
            continue
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen:
            continue
        img = _extract_rss_image(item)
        if not img:
            continue
        seen.add(norm)
        out.append({"title": title, "image": img})
    return out


def fetch_site(site: str, want: int, seen: set) -> list[dict]:
    info = SITE_INFO.get(site)
    if not info:
        return []
    fmt = info.get("fmt", "html")
    if fmt in ("rss", "atom"):
        try:
            xml = _get(info["url"])
            return _parse_rss_feed(xml, want, seen)
        except Exception as e:
            print(f"[warn] {site} RSS failed: {e}")
            return []
    elif site == "buzzfeed":
        return _fetch_buzzfeed(want, seen)
    elif site == "usatoday":
        return _fetch_usatoday_html(want, seen)
    elif site == "marthastewart":
        return _fetch_martha_html(want, seen)
    elif site == "thrillist":
        return _fetch_thrillist_html(want, seen)
    return []


def _fetch_thrillist_html(want: int, seen: set) -> list[dict]:
    """从Thrillist首页HTML解析图文。"""
    try:
        html = _get("https://www.thrillist.com/")
    except Exception as e:
        print(f"[warn] thrillist HTML failed: {e}")
        return []
    out = []
    blocks = re.findall(r'<a[^>]*href="(https://www\.thrillist\.com/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
    for href, inner in blocks:
        if len(out) >= want:
            break
        img_m = re.search(r'(?:src|data-src)="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', inner)
        title_parts = re.findall(r'>([^<]{15,})<', inner)
        title = title_parts[0].strip() if title_parts else ""
        if not img_m or not title:
            continue
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen:
            continue
        seen.add(norm)
        out.append({"title": title, "image": img_m.group(1)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="US Life media image+text fetcher (BuzzFeed/USA Today/Martha Stewart)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    ap.add_argument("--per-site", type=int, default=5)
    ap.add_argument("--dedupe-file", default="state/seen_us_life.json")
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
    print(f"[us_life] dedupe: {dedupe_path.name} ({len(seen)} known)")

    all_items = []
    for site in sources:
        items = fetch_site(site, args.per_site, seen)
        for it in items:
            it["_site"] = site
        all_items.extend(items)
        print(f"[us_life] {site}: {len(items)} items")
        time.sleep(0.3)

    if not all_items:
        print("[ERROR] no items fetched")
        return 1

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
                "_source": "us_life", "_site": it["_site"],
            })

    dedupe_path.write_text(json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    dist = Counter(it["_site"] for it in all_items)
    print(f"[OK] wrote {len(all_items)} items -> {out_path}")
    print(f"[OK] distribution: {dict(dist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
