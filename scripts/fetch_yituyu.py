#!/usr/bin/env python3
"""
fetch_yituyu.py — Fetch HIGH-RESOLUTION gallery photos from yituyu.com and write
a moments CSV compatible with ``post_moments.py`` / ``publish_from_tokens.py``.

Source (public, no login)
    Listing pages seed gallery ids:
        https://www.yituyu.com/            (home)
        https://www.yituyu.com/gallery/    (gallery index)
        https://www.yituyu.com/rank/       (rank)
    Each gallery detail page:
        https://www.yituyu.com/gallery/<gid>/
    exposes its HD photos at:
        https://img.yituyu.com/pic/<gid>/NN_<hash>.jpg   (e.g. 3600x2400, ~600KB)

Why this is "HD"
    The listing thumbnails live under img.yituyu.com/grapher/*.jpg and are small.
    The real per-gallery photos under /pic/<gid>/NN_* are full resolution — this
    script deliberately takes those, not the thumbnails.

Filters
    --theme       subject filter (beauty / portrait / all ...), matched on title
    --exclude-ads drop galleries whose title contains ad-marker words
    --min-side    require min(width,height) >= N by probing the JPEG header
                  (default 0 = skip the check; set e.g. 1000 to force HD)
    --imgs-per-gallery   how many photos to take from each gallery (default 3)
    --dedupe-file JSON of already-used image urls; new picks merged back in

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

BASE = os.getenv("YITUYU_BASE", "https://www.yituyu.com")
IMG_HOST = "img.yituyu.com"
HEADERS = {
    "User-Agent": os.getenv(
        "YITUYU_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ),
    "Referer": os.getenv("YITUYU_REFERER", "https://www.yituyu.com/"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

SEED_PAGES = ["/", "/gallery/", "/rank/"]

THEME_KEYWORDS = {
    "beauty": ["写真", "美图", "少女", "女神", "女生", "小姐姐", "人像", "写实", "portrait", "girl"],
    "portrait": ["写真", "人像", "肖像", "portrait", "写实"],
    "ootd": ["穿搭", "时尚", "写真", "ootd", "fashion"],
    "all": [],
}

AD_KEYWORDS = [
    "广告", "推广", "优惠", "折扣", "促销", "招商", "加盟", "代理", "vip", "付费",
    "扫码", "关注公众", "私信", "商务合作", "微信", "qq群", "下载app", "破解", "福利群",
    "coupon", "discount", "promo", "sponsor", "advertisement",
]


def _get(url: str, timeout: int = 30) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def looks_like_ad(title: str) -> bool:
    low = (title or "").lower()
    return any(k.lower() in low for k in AD_KEYWORDS)


def matches_theme(title: str, theme: str) -> bool:
    if theme == "all" or not theme:
        return True
    kws = THEME_KEYWORDS.get(theme, [])
    if not kws:
        return True
    low = (title or "").lower()
    return any(kw.lower() in low for kw in kws)


def _jpeg_min_side(data: bytes) -> int | None:
    """Return min(width,height) of a JPEG, or None if not parseable."""
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


def seed_gallery_ids() -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for path in SEED_PAGES:
        try:
            txt = _get(BASE + path).content.decode("utf-8", errors="ignore")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] seed {path}: {e}", file=sys.stderr)
            continue
        for gid in re.findall(r"/gallery/(\d+)/", txt):
            if gid not in seen:
                seen.add(gid)
                ids.append(gid)
        time.sleep(0.2)
    return ids


def gallery_photos(gid: str) -> tuple[str, list[str]]:
    """Return (title, [hd_image_urls]) for a gallery."""
    txt = _get(f"{BASE}/gallery/{gid}/").content.decode("utf-8", errors="ignore")
    m = re.search(r"<title>([^<]+)</title>", txt)
    title = (m.group(1).strip() if m else "").split("|")[0].strip()
    pics = sorted(set(re.findall(
        rf"(https?://{re.escape(IMG_HOST)}/pic/{gid}/\d+_[^\s\"\\]+\.(?:jpg|jpeg|png|webp))",
        txt, re.I)))
    return title, pics


def build_caption(title: str) -> str:
    # keep the human title portion; captions can be rewritten later by caption_multilang.py
    return (title or "今日分享").strip()


def iter_rows(
    limit: int,
    *,
    theme: str = "all",
    exclude_ads: bool = False,
    imgs_per_gallery: int = 3,
    min_side: int = 0,
    seen_urls: set[str] | None = None,
    fetched_urls: set[str] | None = None,
    timeout: int = 30,
) -> Iterable[dict]:
    if seen_urls is None:
        seen_urls = set()
    if fetched_urls is None:
        fetched_urls = set()

    gids = seed_gallery_ids()
    print(f"[yituyu] seeded {len(gids)} galleries", file=sys.stderr)

    yielded = 0
    for gid in gids:
        if limit and yielded >= limit:
            return
        try:
            title, pics = gallery_photos(gid)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] gallery {gid}: {e}", file=sys.stderr)
            continue
        if exclude_ads and looks_like_ad(title):
            continue
        if not matches_theme(title, theme):
            continue
        taken = 0
        for u in pics:
            if limit and yielded >= limit:
                return
            if taken >= imgs_per_gallery:
                break
            if u in seen_urls:
                continue
            if min_side > 0:
                try:
                    data = requests.get(u, headers={"User-Agent": HEADERS["User-Agent"],
                                                    "Referer": HEADERS["Referer"]},
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
    ap = argparse.ArgumentParser(description="Fetch yituyu.com HD gallery photos → CSV")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--theme", choices=list(THEME_KEYWORDS.keys()), default="all")
    ap.add_argument("--exclude-ads", action="store_true")
    ap.add_argument("--imgs-per-gallery", type=int, default=3)
    ap.add_argument("--min-side", type=int, default=0,
                    help="require min(w,h) >= N (probes JPEG header); 0 = skip")
    ap.add_argument("--dedupe-file", default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    seen = _load_dedupe(args.dedupe_file)
    picked: set[str] = set()

    rows = list(iter_rows(
        args.limit, theme=args.theme, exclude_ads=args.exclude_ads,
        imgs_per_gallery=args.imgs_per_gallery, min_side=args.min_side,
        seen_urls=seen, fetched_urls=picked,
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
