#!/usr/bin/env python3
"""
fetch_tuzi.py — Fetch HIGH-RESOLUTION photos from tuziyouwang.com and write a
moments CSV compatible with ``post_moments.py`` / ``publish_from_tokens.py``.

Source (public, no login)
    tuziyouwang runs EmpireCMS. A column listing paginates as:
        http://tuziyouwang.com/<column>/            (page 1)
        http://tuziyouwang.com/<column>/index_N.html (page N)
    where <column> is e.g. "meitui" (美腿) or "gengduo" (更多).
    Each article detail page:
        http://tuziyouwang.com/<column>/<aid>.html
    embeds its HD photo(s) under:
        http://tuziyouwang.com/d/file/<date>/<hash>.jpg   (e.g. 800x1200, real photo)

Why this is "HD"
    The listing only shows small titlepic thumbnails
    (/e/data/tmp/titlepic/*.jpg). The article body's /d/file/* image is the
    full photo — this script takes the /d/file/* image, not the thumbnail.

Filters
    --column       EmpireCMS column slug (default: meitui)
    --pages        how many listing pages to crawl (index_2.html ...)
    --exclude-ads  drop articles whose title contains ad-marker words
    --min-side     require min(width,height) >= N via JPEG-header probe (0 = skip)
    --imgs-per-article  max photos per article (default 3)
    --dedupe-file  JSON of already-used image urls; merged back in

Output CSV columns (identical to the other fetch_* scripts)
    content,visibility,room_id,image_urls,
    location_name,location_address,location_lat,location_lon

See docs/15-image-hd-sources.md for the rationale and end-to-end runbook.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import struct
import sys
import time
from pathlib import Path
from typing import Iterable

import requests

BASE = os.getenv("TUZI_BASE", "http://tuziyouwang.com")
HEADERS = {
    "User-Agent": os.getenv(
        "TUZI_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

AD_KEYWORDS = [
    "广告", "推广", "优惠", "折扣", "促销", "招商", "加盟", "代理", "vip", "付费",
    "扫码", "关注公众", "私信", "商务合作", "微信", "qq群", "下载app", "破解", "福利群",
    "coupon", "discount", "promo", "sponsor", "advertisement",
]


def _get(url: str, referer: str, timeout: int = 30) -> str:
    r = requests.get(url, headers={**HEADERS, "Referer": referer}, timeout=timeout)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="ignore")


def looks_like_ad(title: str) -> bool:
    low = (title or "").lower()
    return any(k.lower() in low for k in AD_KEYWORDS)


def _jpeg_min_side(data: bytes) -> int | None:
    try:
        if data[:2] != b"\xff\xd8":
            return None
        i = 2
        n = len(data)
        while i < n:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                h = struct.unpack(">H", data[i + 5:i + 7])[0]
                w = struct.unpack(">H", data[i + 7:i + 9])[0]
                return min(w, h)
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
    except Exception:  # noqa: BLE001
        return None
    return None


def list_article_ids(column: str, pages: int) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for p in range(1, pages + 1):
        url = f"{BASE}/{column}/" if p == 1 else f"{BASE}/{column}/index_{p}.html"
        try:
            txt = _get(url, f"{BASE}/{column}/")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] list {url}: {e}", file=sys.stderr)
            continue
        for aid in re.findall(rf"/{column}/(\d+)\.html", txt):
            if aid not in seen:
                seen.add(aid)
                ids.append(aid)
        time.sleep(0.3)
    return ids


def article_photos(column: str, aid: str) -> tuple[str, list[str]]:
    txt = _get(f"{BASE}/{column}/{aid}.html", f"{BASE}/{column}/")
    m = re.search(r"<title>([^<]+)</title>", txt)
    title = (m.group(1).strip() if m else "").split("-")[0].split("_")[0].strip() or "图自由分享"
    hd = []
    for u in re.findall(r'(?:src|data-original)="(/d/file/[^"]+\.(?:jpg|jpeg|png|webp))"', txt, re.I):
        full = u if u.startswith("http") else BASE + u
        if full not in hd:
            hd.append(full)
    return title, hd


def build_caption(title: str) -> str:
    return (title or "今日分享").strip()


def iter_rows(
    limit: int,
    *,
    column: str = "meitui",
    pages: int = 5,
    exclude_ads: bool = False,
    imgs_per_article: int = 3,
    min_side: int = 0,
    seen_urls: set[str] | None = None,
    fetched_urls: set[str] | None = None,
    timeout: int = 30,
) -> Iterable[dict]:
    if seen_urls is None:
        seen_urls = set()
    if fetched_urls is None:
        fetched_urls = set()

    aids = list_article_ids(column, pages)
    print(f"[tuzi] column={column} found {len(aids)} articles", file=sys.stderr)

    yielded = 0
    for aid in aids:
        if limit and yielded >= limit:
            return
        try:
            title, pics = article_photos(column, aid)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] article {aid}: {e}", file=sys.stderr)
            continue
        if exclude_ads and looks_like_ad(title):
            continue
        if not pics:
            continue
        taken = 0
        for u in pics:
            if limit and yielded >= limit:
                return
            if taken >= imgs_per_article:
                break
            if u in seen_urls:
                continue
            if min_side > 0:
                try:
                    data = requests.get(u, headers={**HEADERS, "Referer": f"{BASE}/{column}/{aid}.html"},
                                        timeout=timeout).content
                    if (_jpeg_min_side(data) or 0) < min_side:
                        continue
                except Exception:  # noqa: BLE001
                    continue
            yield {
                "content": build_caption(title),
                "visibility": 0,
                "room_id": "",
                "image_urls": u,
                "location_name": "",
                "location_address": "",
                "location_lat": "",
                "location_lon": "",
            }
            seen_urls.add(u)
            fetched_urls.add(u)
            yielded += 1
            taken += 1
        time.sleep(0.2)


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
    ap = argparse.ArgumentParser(description="Fetch tuziyouwang.com HD photos → CSV")
    ap.add_argument("--column", default="meitui",
                    help="EmpireCMS column slug (e.g. meitui / gengduo)")
    ap.add_argument("--pages", type=int, default=5, help="listing pages to crawl")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--exclude-ads", action="store_true")
    ap.add_argument("--imgs-per-article", type=int, default=3)
    ap.add_argument("--min-side", type=int, default=0,
                    help="require min(w,h) >= N (probes JPEG header); 0 = skip")
    ap.add_argument("--dedupe-file", default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    seen = _load_dedupe(args.dedupe_file)
    picked: set[str] = set()

    rows = list(iter_rows(
        args.limit, column=args.column, pages=args.pages,
        exclude_ads=args.exclude_ads, imgs_per_article=args.imgs_per_article,
        min_side=args.min_side, seen_urls=seen, fetched_urls=picked,
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
    print(f"[OK] wrote {len(rows)} HD photos → {out}")
    if args.dedupe_file:
        print(f"[OK] dedupe file → {args.dedupe_file} ({len(seen)} urls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
