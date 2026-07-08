#!/usr/bin/env python3
"""
opennana_fetch.py — Fetch prompt-gallery materials from OpenNana and write a
CSV that ``post_moments.py`` can consume directly.

API
    GET https://api.opennana.com/api/prompts?media_type=image|video&page=N[&model=X]
    GET https://api.opennana.com/api/prompts/{slug}

CSV columns (default)
    content,visibility,room_id,image_urls,
    location_name,location_address,location_lat,location_lon,_slug
    (+ _video_url,_cover_url when --media-type=video)

    ``_slug`` traces each row back to its OpenNana prompt so already-sent
    images can be recorded into the dedupe file after publishing
    (see scripts/record_sent_slugs.py).

Options added in v0.2 (2026-07-04)
    --model           filter by generation model (e.g. ChatGPT, "Nano banana pro")
    --theme           subject filter based on title + prompt keywords
                      choices: beauty, portrait, sport, travel, food, all
    --exclude-ads     drop items whose title/tags/prompt look like ads/commercials
    --dedupe-file     JSON list of already-used slugs to skip
                      (also written back with newly picked slugs merged in)
    --max-pages       cap on how many pages we scan before giving up (default 30)

References
    - docs/04-content-pipeline.md §4.1 for API contract
    - docs/11-anti-ad-filtering.md for ad-filter rules
    - docs/12-multi-source.md for the multi-source workflow
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Iterable

import requests

OPENNANA_API_BASE = os.getenv("OPENNANA_API_BASE", "https://api.opennana.com")
HEADERS = {
    "User-Agent": os.getenv(
        "OPENNANA_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ),
    "Referer": os.getenv("OPENNANA_REFERER", "https://opennana.com/"),
    "Accept": "application/json",
}

# ---------------------------------------------------------------------------
# theme / ad-filter keyword tables (kept in Python for zero-runtime-dep)
# ---------------------------------------------------------------------------

# NOTE: use lowercase substrings; matched against title + description + prompt.
THEME_KEYWORDS = {
    "beauty": [
        "woman", "girl", "female", "lady", "portrait", "model", "fashion",
        "写真", "少女", "女性", "美女", "肖像", "人像", "美人", "美少女",
        "beauty", "editorial",
    ],
    "portrait": [
        "portrait", "close-up", "面部", "肖像", "人像", "写真",
    ],
    "sport": [
        "sport", "运动", "gym", "yoga", "healthy", "健身", "跑步", "running",
        "soccer", "football", "basketball", "volleyball", "cycling",
    ],
    "travel": [
        "travel", "旅行", "beach", "海边", "mountain", "vacation", "resort",
        "tokyo", "paris", "london", "new york",
    ],
    "food": [
        "food", "美食", "料理", "recipe", "cooking", "咖啡", "cafe",
    ],
    "all": [],  # no filter
}

# Words / tag values that strongly indicate advertising / commercial creatives.
AD_KEYWORDS = [
    " ad ", " ad.", " ad,", "advertisement", "advert ", "advertising",
    "commercial", "sponsor", "brand-", "brand ", "brand:", "campaign",
    "promo", "promotion", "logo", "packaging", "billboard",
    # Chinese ad / commercial-creative keywords (title & prompt are often zh)
    "海报", "广告", "宣传", "促销", "包装", "logo设计", "品牌", "封面",
    "banner", "poster",
]

# Tag values (case-insensitive) that mean "graphic design / marketing collateral"
# more than a shareable social photo.  Filtered out with --exclude-ads.
AD_TAGS = {
    "poster", "typography", "infographic", "diagram", "web design",
    "app ui", "social media post", "product mockup",
}

# Categories on open-prompts.com; here just for reference (see fetch_openprompts.py).
AD_CATEGORIES = {
    "productcommercial", "commercial", "advertising", "product", "brand",
}


def _s(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " ".join(x for x in v if isinstance(x, str))
    return ""


def looks_like_ad(item: dict) -> bool:
    """Return True if the item looks like an ad / marketing creative."""
    tags = [t.lower() for t in (item.get("tags") or []) if isinstance(t, str)]
    if any(t in AD_TAGS for t in tags):
        return True
    text = " ".join([
        _s(item.get("category")),
        _s(item.get("title")),
        _s(item.get("description"))[:400],
        _s(item.get("tags")),
    ]).lower()
    if (item.get("category") or "").lower() in AD_CATEGORIES:
        return True
    return any(k in text for k in AD_KEYWORDS)


def matches_theme(item: dict, theme: str) -> bool:
    if theme == "all":
        return True
    kws = THEME_KEYWORDS.get(theme, [])
    if not kws:
        return True
    title = (item.get("title") or "")
    desc = (item.get("description") or "")[:400]
    tags = _s(item.get("tags"))
    prompt = ""
    for p in item.get("prompts") or []:
        prompt += _s(p.get("text") if isinstance(p, dict) else p) + " "
        if len(prompt) > 400:
            break
    text = (title + " " + desc + " " + tags + " " + prompt).lower()
    return any(kw.lower() in text for kw in kws)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def list_prompts(media_type: str, page: int, model: str | None = None) -> list[dict]:
    url = f"{OPENNANA_API_BASE}/api/prompts"
    params = {"media_type": media_type, "page": page}
    if model:
        params["model"] = model
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    j = r.json()
    # opennana returns {"data": {"items":[...], "pagination":{...}}}
    data = j.get("data")
    if isinstance(data, dict):
        return data.get("items") or []
    if isinstance(data, list):
        return data
    return j.get("results") or j.get("items") or []


def get_detail(slug: str) -> dict:
    url = f"{OPENNANA_API_BASE}/api/prompts/{slug}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("data") or r.json()


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------


def build_caption(detail: dict) -> str:
    """Simple placeholder caption — title + hashtags.
    Downstream LLM should rewrite this into a first-person share caption
    (see docs/04-content-pipeline.md §4.2 and docs/13-multilang-captions.md)."""
    title = (detail.get("title") or "").strip()
    tags = [f"#{t}" for t in (detail.get("tags") or []) if isinstance(t, str)]
    parts = [p for p in [title, " ".join(tags)] if p]
    return " ".join(parts) or "今日分享"


def iter_rows(
    media_type: str,
    pages: Iterable[int],
    limit: int,
    *,
    model: str | None = None,
    theme: str = "all",
    exclude_ads: bool = False,
    seen_slugs: set[str] | None = None,
    fetched_slugs: set[str] | None = None,
    shuffle_pages: bool = False,
) -> Iterable[dict]:
    """Yield CSV row dicts.

    ``seen_slugs`` — already-used slug set (from --dedupe-file); we never yield those.
    ``fetched_slugs`` — collector for slugs we actually did yield (caller writes back).
    """
    if seen_slugs is None:
        seen_slugs = set()
    if fetched_slugs is None:
        fetched_slugs = set()

    ordered = list(pages)
    if shuffle_pages:
        random.shuffle(ordered)

    yielded = 0
    for page in ordered:
        try:
            items = list_prompts(media_type, page, model=model)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] page {page} list failed: {e}", file=sys.stderr)
            continue
        for item in items:
            if limit and yielded >= limit:
                return
            slug = item.get("slug") or item.get("id")
            if not slug or slug in seen_slugs:
                continue
            try:
                detail = get_detail(str(slug))
            except Exception as e:  # noqa: BLE001
                print(f"[warn] detail {slug} failed: {e}", file=sys.stderr)
                continue

            # Post-filter by model (server-side model= is honoured but be defensive)
            if model and (detail.get("model") or "").lower() != model.lower():
                continue

            if exclude_ads and looks_like_ad(detail):
                continue
            if not matches_theme(detail, theme):
                continue

            if media_type == "image":
                images = detail.get("images") or []
                if not images:
                    continue
                yield {
                    "content": build_caption(detail),
                    "visibility": 0,
                    "room_id": "",
                    "image_urls": ",".join(images[:9]),
                    "location_name": "",
                    "location_address": "",
                    "location_lat": "",
                    "location_lon": "",
                    # _slug lets the post step trace each row back to its OpenNana
                    # prompt, so already-sent images can be recorded into the
                    # dedupe file after publishing (see record_sent_slugs.py).
                    "_slug": str(slug),
                }
            else:  # video
                videos = detail.get("video_urls") or []
                images = detail.get("images") or []
                if not videos:
                    continue
                yield {
                    "content": build_caption(detail),
                    "visibility": 0,
                    "room_id": "",
                    "image_urls": "",
                    "location_name": "",
                    "location_address": "",
                    "location_lat": "",
                    "location_lon": "",
                    "_video_url": videos[0],
                    "_cover_url": images[0] if images else "",
                    "_slug": str(slug),
                }

            fetched_slugs.add(str(slug))
            seen_slugs.add(str(slug))
            yielded += 1
            time.sleep(0.15)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_dedupe_file(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x) for x in data}
        if isinstance(data, dict) and "slugs" in data:
            return {str(x) for x in data["slugs"]}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] cannot read dedupe file {path}: {e}", file=sys.stderr)
    return set()


def _save_dedupe_file(path: str | None, seen: set[str]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(sorted(seen), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch OpenNana prompts → CSV")
    ap.add_argument("--media-type", choices=("image", "video"), default="image")
    ap.add_argument("--page", type=int, default=1, help="starting page")
    ap.add_argument("--pages", type=int, default=1, help="how many consecutive pages to scan")
    ap.add_argument("--max-pages", type=int, default=30,
                    help="cap on total pages scanned (implicit when --pages < --max-pages)")
    ap.add_argument("--limit", type=int, default=10, help="max rows to write")
    ap.add_argument("--model", default=None,
                    help='filter by opennana model, e.g. "ChatGPT" / "Nano banana pro"')
    ap.add_argument("--theme", choices=list(THEME_KEYWORDS.keys()), default="all",
                    help="subject-based theme filter (default: all)")
    ap.add_argument("--exclude-ads", action="store_true",
                    help="drop items whose tags/title/prompt look like ads")
    ap.add_argument("--dedupe-file", default=None,
                    help="JSON of already-used slugs; new picks are merged back in")
    ap.add_argument("--shuffle-pages", action="store_true",
                    help="shuffle page order for a more diverse sample")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    seen = _load_dedupe_file(args.dedupe_file)
    picked: set[str] = set()

    total_pages = min(max(args.pages, 1), args.max_pages)
    pages = range(args.page, args.page + total_pages)

    rows = list(iter_rows(
        args.media_type, pages, args.limit,
        model=args.model,
        theme=args.theme,
        exclude_ads=args.exclude_ads,
        seen_slugs=seen,
        fetched_slugs=picked,
        shuffle_pages=args.shuffle_pages,
    ))
    if not rows:
        print("[warn] no rows produced", file=sys.stderr)
        return 1

    base_fields = [
        "content", "visibility", "room_id", "image_urls",
        "location_name", "location_address", "location_lat", "location_lon",
    ]
    extra_fields = [k for k in rows[0] if k.startswith("_")]
    fields = base_fields + extra_fields

    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})

    _save_dedupe_file(args.dedupe_file, seen)

    print(f"[OK] wrote {len(rows)} rows → {out}")
    if args.dedupe_file:
        print(f"[OK] dedupe file now has {len(seen)} slugs → {args.dedupe_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
