#!/usr/bin/env python3
"""
fetch_openprompts.py — Fetch materials from open-prompts.com and write a
CSV compatible with ``post_moments.py``.

API (unofficial, discovered via network inspection)
    GET https://www.open-prompts.com/api/prompts?page=N
    -> {"prompts":[{id,title,description,prompt,model,category,tags,images,sourceUrl,authorHandle,createdAt}, ...], "source":"..."}

Per-item schema
    id            string (slug-like)
    title         string
    description   string
    prompt        long text (usually English, sometimes with 中文 blocks)
    model         e.g. "GPT Image 2", "Nano banana pro", "ChatGPT"
    category      portraitPhoto / artStyles / scenes / gameFantasy / designUi /
                  productCommercial / styleEra / ...
    tags          list[str] — includes UX-marker tags like "Poster", "Infographic"
    images        list[str] — direct hot-linkable URLs (Twitter CDN, etc.)

Filters
    --theme       subject filter (beauty / portrait / sport / travel / food / all)
    --exclude-ads drop items whose category ∈ AD_CATEGORIES,
                  or whose tags ∈ AD_TAGS,
                  or whose title/description/prompt contains ad-marker words.

Output CSV columns
    content,visibility,room_id,image_urls,
    location_name,location_address,location_lat,location_lon

See docs/11-anti-ad-filtering.md for the full rule table.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterable

import requests

OP_API_BASE = os.getenv("OPENPROMPTS_API_BASE", "https://www.open-prompts.com/api")
HEADERS = {
    "User-Agent": os.getenv(
        "OPENPROMPTS_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ),
    "Referer": os.getenv("OPENPROMPTS_REFERER", "https://www.open-prompts.com/"),
    "Accept": "application/json",
}

THEME_KEYWORDS = {
    "beauty": [
        "woman", "girl", "female", "lady", "portrait", "model", "fashion",
        "写真", "少女", "女性", "美女", "肖像", "人像", "beauty", "editorial",
    ],
    "portrait": ["portrait", "close-up", "肖像", "人像", "写真"],
    "sport": [
        "sport", "运动", "gym", "yoga", "健身", "跑步", "running",
        "soccer", "football", "basketball", "volleyball", "cycling",
    ],
    "travel": ["travel", "旅行", "beach", "海边", "mountain", "vacation",
               "tokyo", "paris", "london", "new york"],
    "food": ["food", "美食", "料理", "recipe", "cooking", "咖啡", "cafe"],
    "all": [],
}

AD_CATEGORIES = {
    "productcommercial", "commercial", "advertising", "product", "brand",
}
AD_TAGS_LOWER = {
    "poster", "typography", "infographic", "diagram", "web design",
    "app ui", "social media post", "product mockup",
}
AD_KEYWORDS = [
    " ad ", " ad.", " ad,", "advertisement", "advert ", "advertising",
    "commercial", "sponsor", "brand-", "brand:", "campaign",
    "promo", "promotion", "logo", "packaging", "billboard",
]


def _s(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " ".join(x for x in v if isinstance(x, str))
    return ""


def looks_like_ad(item: dict) -> bool:
    if (item.get("category") or "").lower() in AD_CATEGORIES:
        return True
    tags_l = [t.lower() for t in (item.get("tags") or []) if isinstance(t, str)]
    if any(t in AD_TAGS_LOWER for t in tags_l):
        return True
    text = " ".join([
        _s(item.get("title")),
        _s(item.get("description"))[:400],
        _s(item.get("tags")),
        _s(item.get("prompt"))[:400],
    ]).lower()
    return any(k in text for k in AD_KEYWORDS)


def matches_theme(item: dict, theme: str) -> bool:
    if theme == "all" or not theme:
        return True
    if theme == "beauty" and (item.get("category") or "").lower() == "portraitphoto":
        return True
    kws = THEME_KEYWORDS.get(theme, [])
    text = " ".join([
        _s(item.get("title")),
        _s(item.get("description"))[:400],
        _s(item.get("tags")),
        _s(item.get("prompt"))[:600],
    ]).lower()
    return any(kw.lower() in text for kw in kws)


def list_page(page: int) -> list[dict]:
    r = requests.get(f"{OP_API_BASE}/prompts", params={"page": page},
                     headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json().get("prompts") or []


def build_caption(item: dict) -> str:
    title = (item.get("title") or "").strip()
    tags = [f"#{t}" for t in (item.get("tags") or []) if isinstance(t, str)]
    parts = [p for p in [title, " ".join(tags)] if p]
    return " ".join(parts) or "今日分享"


def iter_rows(
    pages: Iterable[int], limit: int,
    *,
    model: str | None = None,
    theme: str = "all",
    exclude_ads: bool = False,
    seen_slugs: set[str] | None = None,
    fetched_slugs: set[str] | None = None,
) -> Iterable[dict]:
    if seen_slugs is None:
        seen_slugs = set()
    if fetched_slugs is None:
        fetched_slugs = set()

    yielded = 0
    for page in pages:
        try:
            items = list_page(page)
        except Exception as e:
            print(f"[warn] page {page} failed: {e}", file=sys.stderr)
            continue
        for it in items:
            if limit and yielded >= limit:
                return
            slug = it.get("id") or it.get("slug")
            if not slug or slug in seen_slugs:
                continue
            if model and (it.get("model") or "").lower() != model.lower():
                continue
            if exclude_ads and looks_like_ad(it):
                continue
            if not matches_theme(it, theme):
                continue
            images = [u for u in (it.get("images") or []) if isinstance(u, str) and u.startswith("http")]
            if not images:
                continue
            yield {
                "content": build_caption(it),
                "visibility": 0,
                "room_id": "",
                "image_urls": ",".join(images[:9]),
                "location_name": "",
                "location_address": "",
                "location_lat": "",
                "location_lon": "",
            }
            fetched_slugs.add(str(slug))
            seen_slugs.add(str(slug))
            yielded += 1
            time.sleep(0.05)


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
    ap = argparse.ArgumentParser(description="Fetch open-prompts.com prompts → CSV")
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--model", default=None,
                    help='filter by generation model (e.g. "GPT Image 2", "Nano banana pro")')
    ap.add_argument("--theme", choices=list(THEME_KEYWORDS.keys()), default="all")
    ap.add_argument("--exclude-ads", action="store_true")
    ap.add_argument("--dedupe-file", default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    seen = _load_dedupe(args.dedupe_file)
    picked: set[str] = set()

    pages = range(args.page, args.page + args.pages)
    rows = list(iter_rows(
        pages, args.limit,
        model=args.model, theme=args.theme,
        exclude_ads=args.exclude_ads,
        seen_slugs=seen, fetched_slugs=picked,
    ))
    if not rows:
        print("[warn] no rows produced", file=sys.stderr)
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
    print(f"[OK] wrote {len(rows)} rows → {out}")
    if args.dedupe_file:
        print(f"[OK] dedupe file → {args.dedupe_file} ({len(seen)} slugs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
