#!/usr/bin/env python3
"""
fetch_lovimg.py — Fetch materials from lovimg.com and write a CSV compatible
with ``post_moments.py``.

lovimg.com is a TanStack Start SSR site. There's no clean REST endpoint;
the payload is inlined into the HTML as ``$R[...]`` JS objects. This module
parses those blobs.

Per-item schema (best-effort)
    id            numeric string
    slug          url slug
    imageUrl      primary image url
    imageUrls[]   full image list (may reference $R[N])
    title         scene / prompt description (mostly English)

Category examples
    people-characters, animals-nature, food-drink, architecture-interior,
    art-style, futuristic-scifi, ...

References
    - scripts/legacy origin: harvest_lovimg.py (from tester/auto-poster)
    - Filter table: docs/11-anti-ad-filtering.md
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
from typing import Iterable

import requests

BASE = "https://lovimg.com"
UA = os.getenv(
    "LOVIMG_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36",
)
HEADERS = {
    "User-Agent": UA,
    "Referer": os.getenv("LOVIMG_REFERER", "https://lovimg.com/zh"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,*/*",
}

# ---------------------------------------------------------------------------
# HTML/JS blob parsing
# ---------------------------------------------------------------------------

ITEM_RE = re.compile(
    r'\{id:"(?P<id>\d+)",'
    r'slug:"(?P<slug>[^"]+)",'
    r'imageUrl:"(?P<imageUrl>[^"]+)",'
    r'imageUrls:(?:\$R\[\d+\]=)?\[(?P<imageUrls>[^\]]*)\],'
    r'.*?'
    r'title:"(?P<title>(?:[^"\\]|\\.)*)"',
    re.S,
)
URL_RE = re.compile(r'"(https://static\.lovimg\.com/[^"]+)"')
CURSOR_RE = re.compile(r'nextCursor:"([^"]+)"')


def _unesc(s: str) -> str:
    try:
        return bytes(s, "utf-8").decode("unicode_escape")
    except Exception:
        return s


def parse_items(html: str) -> list[dict]:
    items: list[dict] = []
    for m in ITEM_RE.finditer(html):
        imgs = URL_RE.findall(m.group("imageUrls"))
        if not imgs:
            single = m.group("imageUrl")
            if single.startswith("http"):
                imgs = [single]
        items.append({
            "id": m.group("id"),
            "slug": m.group("slug"),
            "title": _unesc(m.group("title")),
            "images": imgs,
        })
    return items


def next_cursor(html: str) -> str | None:
    m = CURSOR_RE.search(html)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# theme / ad filter (same tables as opennana_fetch/openprompts)
# ---------------------------------------------------------------------------

THEME_KEYWORDS = {
    "beauty": [
        "woman", "girl", "female", "lady", "portrait", "model", "fashion",
        "写真", "少女", "女性", "美女", "肖像", "人像", "beauty", "editorial",
        "asian", "chinese", "japanese", "korean",
    ],
    "portrait": ["portrait", "close-up", "肖像", "人像", "写真"],
    "sport": ["sport", "运动", "gym", "yoga", "健身", "跑步", "running"],
    "travel": ["travel", "旅行", "beach", "海边", "mountain", "vacation"],
    "food": ["food", "美食", "料理", "recipe", "cooking"],
    "all": [],
}

AD_KEYWORDS = [
    " ad ", " ad.", " ad,", "advertisement", "advert ", "commercial",
    "sponsor", "brand-", "campaign", "promo", "logo", "packaging",
    "billboard", "poster", "product"
]


def looks_like_ad(item: dict) -> bool:
    t = (item.get("title") or "").lower()
    return any(k in t for k in AD_KEYWORDS)


def matches_theme(item: dict, theme: str) -> bool:
    if theme == "all" or not theme:
        return True
    kws = THEME_KEYWORDS.get(theme, [])
    text = (item.get("title") or "").lower()
    return any(kw.lower() in text for kw in kws)


# ---------------------------------------------------------------------------
# fetch loop
# ---------------------------------------------------------------------------


def build_caption(item: dict) -> str:
    title = (item.get("title") or "").strip()
    return title or "今日分享"


def fetch(
    category: str, *,
    max_pages: int = 20,
    limit: int = 100,
    theme: str = "all",
    exclude_ads: bool = False,
    seen_slugs: set[str] | None = None,
    fetched_slugs: set[str] | None = None,
) -> list[dict]:
    if seen_slugs is None:
        seen_slugs = set()
    if fetched_slugs is None:
        fetched_slugs = set()

    session = requests.Session()
    session.headers.update(HEADERS)

    url = f"{BASE}/zh?category={category}"
    cursor = None
    out: list[dict] = []
    for page in range(max_pages):
        full = url if cursor is None else f"{url}&cursor={cursor}"
        try:
            r = session.get(full, timeout=45)
            r.encoding = "utf-8"
            if r.status_code != 200:
                print(f"[warn] page {page} HTTP {r.status_code}", file=sys.stderr)
                break
            html = r.text
        except Exception as e:
            print(f"[warn] page {page} err {e}", file=sys.stderr)
            break

        items = parse_items(html)
        new = 0
        for it in items:
            if limit and len(out) >= limit:
                break
            slug = it["slug"]
            if slug in seen_slugs:
                continue
            if exclude_ads and looks_like_ad(it):
                continue
            if not matches_theme(it, theme):
                continue
            if not it["images"]:
                continue
            out.append(it)
            seen_slugs.add(slug)
            fetched_slugs.add(slug)
            new += 1
        nxt = next_cursor(html)
        print(f"[page {page}] fetched={len(items)} new={new} total={len(out)}",
              file=sys.stderr)
        if not nxt or nxt == cursor or new == 0:
            break
        cursor = nxt
        time.sleep(1.0)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


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
        if isinstance(d, dict) and "slugs" in d:
            return {str(x) for x in d["slugs"]}
    except Exception as e:
        print(f"[warn] dedupe read {path}: {e}", file=sys.stderr)
    return set()


def _save_dedupe(path: str | None, seen: set[str]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch lovimg.com prompts → CSV")
    ap.add_argument("--category", default="people-characters",
                    help="lovimg category slug (default: people-characters)")
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--theme", choices=list(THEME_KEYWORDS.keys()), default="all")
    ap.add_argument("--exclude-ads", action="store_true")
    ap.add_argument("--dedupe-file", default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    seen = _load_dedupe(args.dedupe_file)
    picked: set[str] = set()

    items = fetch(
        args.category,
        max_pages=args.max_pages, limit=args.limit,
        theme=args.theme, exclude_ads=args.exclude_ads,
        seen_slugs=seen, fetched_slugs=picked,
    )
    if not items:
        print("[warn] no items produced", file=sys.stderr)
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for it in items:
            w.writerow({
                "content": build_caption(it),
                "visibility": 0,
                "room_id": "",
                "image_urls": ",".join(it["images"][:9]),
                "location_name": "",
                "location_address": "",
                "location_lat": "",
                "location_lon": "",
            })

    _save_dedupe(args.dedupe_file, seen)
    print(f"[OK] wrote {len(items)} rows → {out}")
    if args.dedupe_file:
        print(f"[OK] dedupe file → {args.dedupe_file} ({len(seen)} slugs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
