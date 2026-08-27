#!/usr/bin/env python3
"""
fetch_firecrawl.py — Firecrawl 新闻采集器

用 Firecrawl Scrape API 抓取新闻网站，提取标题和正文摘要。
适用于需要完整页面内容的新闻源（RSS/API 无法满足的场景）。

用法：
    py -3 scripts/fetch_firecrawl.py --url https://www.coindesk.com --limit 10 --output coindesk.csv
    py -3 scripts/fetch_firecrawl.py --urls-file urls.txt --limit 5 --tag crypto --output news_raw.csv
    py -3 scripts/fetch_firecrawl.py --search "crypto news" --limit 10 --output search_results.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _get_api_key() -> str:
    """从环境变量或 .api_key 文件读取 Firecrawl API Key。"""
    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if key:
        return key
    key_file = Path.home() / ".workbuddy" / "skills" / "firecrawl" / ".api_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        "FIRECRAWL_API_KEY not found. "
        "Set env var or put key in ~/.workbuddy/skills/firecrawl/.api_key"
    )


API_KEY = _get_api_key()
BASE_URL = "https://api.firecrawl.dev"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def scrape_url(url: str, formats: list[str] | None = None) -> dict:
    """抓取单个 URL，返回 Markdown 内容。"""
    payload = {
        "url": url,
        "formats": formats or ["markdown"],
        "onlyMainContent": True,
    }
    resp = requests.post(f"{BASE_URL}/v2/scrape", headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def search_web(query: str, limit: int = 5) -> dict:
    """搜索互联网，返回结果列表。"""
    payload = {"query": query, "limit": limit}
    resp = requests.post(f"{BASE_URL}/v2/search", headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        return {}
    return data.get("data", {})


def extract_title_and_summary(markdown: str) -> tuple[str, str]:
    """从 Markdown 提取标题和前 200 字符作为摘要。"""
    lines = [l.strip() for l in markdown.split("\n") if l.strip()]
    title = lines[0].lstrip("#").strip() if lines else ""
    # 去掉标题行，取下一段作为摘要
    summary_parts = []
    skipped_title = False
    for line in lines:
        if not skipped_title:
            skipped_title = True
            continue
        if line.startswith("#"):
            continue
        summary_parts.append(line)
        if len(" ".join(summary_parts)) >= 200:
            break
    summary = " ".join(summary_parts)[:200]
    return title, summary


def fetch_from_url(url: str, tag: str = "") -> dict | None:
    """从单个 URL 抓取，返回结构化结果。"""
    try:
        result = scrape_url(url)
        if not result.get("success"):
            print(f"  [ERR] {url}: {result.get('error', 'unknown')}", file=sys.stderr)
            return None
        md = result.get("data", {}).get("markdown", "")
        if not md:
            return None
        title, summary = extract_title_and_summary(md)
        if not title:
            return None
        return {
            "title": title,
            "brief": summary,
            "url": url,
            "site": _extract_domain(url),
            "tag": tag,
        }
    except Exception as e:
        print(f"  [ERR] {url}: {e}", file=sys.stderr)
        return None


def _extract_domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else url


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch news via Firecrawl → CSV")
    ap.add_argument("--url", help="Single URL to scrape")
    ap.add_argument("--urls-file", help="File with one URL per line")
    ap.add_argument("--search", help="Search query (uses Firecrawl Search)")
    ap.add_argument("--limit", type=int, default=10, help="Max items per source")
    ap.add_argument("--tag", default="news", help="Tag for output CSV")
    ap.add_argument("--output", required=True, help="Output CSV path")
    args = ap.parse_args()

    rows = []

    if args.search:
        print(f"[firecrawl] Searching: {args.search}", file=sys.stderr)
        results = search_web(args.search, limit=args.limit)
        # Search API returns nested structure: data.web[...]
        if isinstance(results, dict):
            items = results.get("web", [])
        else:
            items = results
        for r in items:
            if isinstance(r, str):
                continue
            rows.append({
                "title": r.get("title", ""),
                "brief": r.get("description", "")[:200],
                "url": r.get("url", ""),
                "site": _extract_domain(r.get("url", "")),
                "tag": args.tag,
            })
    elif args.url:
        print(f"[firecrawl] Scraping: {args.url}", file=sys.stderr)
        item = fetch_from_url(args.url, args.tag)
        if item:
            rows.append(item)
    elif args.urls_file:
        urls = [l.strip() for l in Path(args.urls_file).read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"[firecrawl] Scraping {len(urls)} URLs from {args.urls_file}", file=sys.stderr)
        for url in urls[:args.limit]:
            item = fetch_from_url(url, args.tag)
            if item:
                rows.append(item)
    else:
        print("[ERR] Need --url, --urls-file, or --search", file=sys.stderr)
        return 1

    if not rows:
        print("[warn] no items fetched", file=sys.stderr)
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_tag", "_brief"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for it in rows:
            w.writerow({
                "content": it["title"],
                "visibility": 0,
                "room_id": "",
                "image_urls": "",
                "location_name": "",
                "location_address": "",
                "location_lat": "",
                "location_lon": "",
                "_source": "firecrawl",
                "_site": it["site"],
                "_tag": it["tag"],
                "_brief": it["brief"],
            })

    print(f"[OK] wrote {len(rows)} items → {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
