#!/usr/bin/env python3
"""
fetch_tophub.py — Fetch trending topics from tophub.today and write a
text-only moments CSV compatible with ``post_moments.py`` /
``publish_from_tokens.py``.

Source (public, no login required)
    GET https://tophub.today/hot
    -> server-rendered HTML. Each hot entry is rendered inside a repeated
       ``center-item`` card; the first substantive text node of each card is
       the topic title.

Why HTML scraping (not an API)
    tophub does not expose a public JSON API for /hot. The markup uses
    obfuscated class names, but the 100 hot entries are reliably delimited by
    the literal token ``center-item`` (one per entry). We split on it and take
    the first meaningful ``>text<`` node inside each card.

Output CSV columns (identical to the other fetch_* scripts, minus images)
    content,visibility,room_id,image_urls,
    location_name,location_address,location_lat,location_lon

Because hot topics are text, ``image_urls`` is always empty and the resulting
moments are posted as ``media_info={"type":"text"}``.

Language / rewrite
    This script only *collects* raw Chinese topic titles. To turn them into
    multi-language, first-person social captions (EN / 繁中 / 日) run the
    output through ``scripts/caption_multilang.py`` afterwards, exactly like
    the image sources. See docs/14-tophub-source.md for the full recipe.

Filters
    --exclude-ads   drop entries whose title contains ad-marker words
                    (shared spirit with docs/11-anti-ad-filtering.md).
    --dedupe-file   JSON list of already-used topic hashes; new picks merged in.

See docs/14-tophub-source.md for the rationale and the end-to-end runbook.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable

import requests

TOPHUB_HOT_URL = os.getenv("TOPHUB_HOT_URL", "https://tophub.today/hot")
HEADERS = {
    "User-Agent": os.getenv(
        "TOPHUB_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ),
    "Referer": os.getenv("TOPHUB_REFERER", "https://tophub.today/"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Card delimiter observed in the /hot markup: one occurrence per hot entry.
ITEM_DELIMITER = "center-item"

# Tokens that are structural noise, never a real topic title.
NOISE_TEXTS = {"查看更多", "热", "·", "更多", ""}

# Shared spirit with docs/11-anti-ad-filtering.md — drop obvious promo entries.
AD_KEYWORDS = [
    "优惠", "折扣", "促销", "秒杀", "领券", "红包", "推广", "广告",
    "招商", "加盟", "代理", "微商", "刷单", "返现", "免费领",
    "coupon", "discount", "promo", "sponsor", "advertisement",
]


def _clean_candidates(chunk: str) -> list[str]:
    """Return the substantive text nodes inside a single card chunk."""
    texts = re.findall(r">([^<>]+)<", chunk)
    out: list[str] = []
    for t in texts:
        t = t.strip()
        if not t:
            continue
        # pure numbers / ranks / percentages / symbols → skip
        if re.fullmatch(r"[\d\s.,%°+\-]+", t):
            continue
        if t in NOISE_TEXTS:
            continue
        out.append(t)
    return out


def looks_like_ad(title: str) -> bool:
    low = title.lower()
    return any(k.lower() in low for k in AD_KEYWORDS)


def _topic_hash(title: str) -> str:
    return hashlib.md5(title.encode("utf-8")).hexdigest()[:12]


def fetch_hot_html(*, timeout: int = 30) -> str:
    r = requests.get(TOPHUB_HOT_URL, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def parse_topics(html: str) -> list[str]:
    """Extract ordered topic titles from a /hot HTML page."""
    blocks = html.split(ITEM_DELIMITER)
    topics: list[str] = []
    for b in blocks[1:]:
        cand = _clean_candidates(b[:800])
        if cand:
            topics.append(cand[0])
    return topics


def iter_rows(
    limit: int,
    *,
    exclude_ads: bool = False,
    seen_hashes: set[str] | None = None,
    fetched_hashes: set[str] | None = None,
    timeout: int = 30,
) -> Iterable[dict]:
    if seen_hashes is None:
        seen_hashes = set()
    if fetched_hashes is None:
        fetched_hashes = set()

    html = fetch_hot_html(timeout=timeout)
    topics = parse_topics(html)

    yielded = 0
    for title in topics:
        if limit and yielded >= limit:
            return
        h = _topic_hash(title)
        if h in seen_hashes:
            continue
        if exclude_ads and looks_like_ad(title):
            continue
        yield {
            "content": title,
            "visibility": 0,
            "room_id": "",
            "image_urls": "",
            "location_name": "",
            "location_address": "",
            "location_lat": "",
            "location_lon": "",
        }
        seen_hashes.add(h)
        fetched_hashes.add(h)
        yielded += 1


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
        if isinstance(d, dict) and "hashes" in d:
            return {str(x) for x in d["hashes"]}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] dedupe read {path}: {e}", file=sys.stderr)
    return set()


def _save_dedupe(path: str | None, seen: set[str]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch tophub.today/hot topics → CSV")
    ap.add_argument("--limit", type=int, default=100,
                    help="max topics to write (default: 100)")
    ap.add_argument("--exclude-ads", action="store_true",
                    help="drop entries whose title looks like an ad/promo")
    ap.add_argument("--dedupe-file", default=None,
                    help="JSON list of already-used topic hashes; merged back in")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    seen = _load_dedupe(args.dedupe_file)
    picked: set[str] = set()

    rows = list(iter_rows(
        args.limit,
        exclude_ads=args.exclude_ads,
        seen_hashes=seen, fetched_hashes=picked,
    ))
    if not rows:
        print("[warn] no topics produced", file=sys.stderr)
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    _save_dedupe(args.dedupe_file, seen)
    print(f"[OK] wrote {len(rows)} topics → {out}")
    if args.dedupe_file:
        print(f"[OK] dedupe file → {args.dedupe_file} ({len(seen)} hashes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
