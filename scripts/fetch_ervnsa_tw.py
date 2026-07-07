#!/usr/bin/env python3
"""
fetch_ervnsa_tw.py — Fetch Taiwan tourism album photos from the government
scenic-area photo site erv-nsa.gov.tw (交通部觀光署 相簿分享) and write a moments
CSV where each ALBUM becomes ONE MULTI-IMAGE post.

Source (public, JS-rendered, self-signed-ish cert -> ignore_https_errors)
    Album list:   https://www.erv-nsa.gov.tw/zh-tw/service/albumlist?page=N
    Album detail: https://www.erv-nsa.gov.tw/zh-tw/service/album/<id>
    Photos:       https://www.erv-nsa.gov.tw/image/<imgid>/<WxH>
                  (size segment is swappable; we request /1024x768 for a larger,
                   watermark-light copy. The publisher can still crop the bottom
                   strip via POST_CROP_BOTTOM_HOSTS including erv-nsa.gov.tw.)

Each qualifying album (>= --min-imgs photos) becomes a single moments row whose
``image_urls`` is a comma-joined list of up to --imgs-per-post full photos.
``content`` is the album title (a scene hint); rewrite later with
caption_multilang.py --langs zh_hant for 繁體中文 / Taiwan captions.

Output CSV columns (compatible with publish_from_tokens.py, +_source)
    content,visibility,room_id,image_urls,
    location_name,location_address,location_lat,location_lon,_source

Watermark
    Handled the same way as Xiaohongshu / backpackers: publish_from_tokens.py
    crops the bottom strip for hosts in POST_CROP_BOTTOM_HOSTS (add
    erv-nsa.gov.tw). Tune with POST_CROP_BOTTOM_PCT.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

BASE = "https://www.erv-nsa.gov.tw"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

AD_KEYWORDS = ["廣告", "推廣", "徵求", "問卷", "調查", "報名", "得獎名單", "名單公布"]

IMG_SIZE = "1024x768"   # request a larger variant than the 480x360 / 640x480 thumbs


def _ensure_utf8_stdout():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


def looks_like_ad(title: str) -> bool:
    low = (title or "")
    return any(k in low for k in AD_KEYWORDS)


def _upsize(url: str) -> str:
    # https://www.erv-nsa.gov.tw/image/<id>/480x360 -> /1024x768
    return re.sub(r"(/image/\d+)/\d+x\d+", rf"\1/{IMG_SIZE}", url)


def list_albums(pg, pages: int) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for pg_no in range(1, pages + 1):
        try:
            pg.goto(f"{BASE}/zh-tw/service/albumlist?page={pg_no}",
                    wait_until="networkidle", timeout=45000)
            pg.wait_for_timeout(2500)
        except Exception as e:  # noqa: BLE001
            print(f"[erv] list page {pg_no} err: {e}", file=sys.stderr)
            continue
        hrefs = pg.eval_on_selector_all("a", "els=>els.map(e=>e.href||'').filter(Boolean)")
        for h in hrefs:
            m = re.search(r"/service/album/(\d+)", h)
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                ids.append(m.group(1))
        time.sleep(0.3)
    return ids


def album_photos(pg, aid: str) -> tuple[str, list[str]]:
    pg.goto(f"{BASE}/zh-tw/service/album/{aid}", wait_until="networkidle", timeout=45000)
    pg.wait_for_timeout(2000)
    title = (pg.title() or "").split(":")[-1].strip()
    srcs = pg.eval_on_selector_all("img", "els=>els.map(e=>e.src||'').filter(Boolean)")
    urls, seen = [], set()
    for s in srcs:
        if "/image/" not in s:
            continue
        u = _upsize(s)
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return title, urls


def iter_posts(pg, *, want_posts: int, imgs_per_post: int, min_imgs: int,
               exclude_ads: bool, seen_albums: set[str], listing_pages: int):
    albums = list_albums(pg, listing_pages)
    print(f"[erv] {len(albums)} albums listed", file=sys.stderr)
    yielded = 0
    for aid in albums:
        if yielded >= want_posts:
            return
        if aid in seen_albums:
            continue
        try:
            title, photos = album_photos(pg, aid)
        except Exception as e:  # noqa: BLE001
            print(f"[erv] album {aid} err: {e}", file=sys.stderr)
            continue
        if exclude_ads and looks_like_ad(title):
            print(f"[erv] skip ad-like {aid}: {title[:30]}", file=sys.stderr)
            continue
        if len(photos) < min_imgs:
            continue
        chosen = photos[:imgs_per_post]
        seen_albums.add(aid)
        yield {
            "content": (title or "台灣風景").strip(),
            "visibility": 0, "room_id": "",
            "image_urls": ",".join(chosen),
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_source": "ervnsa",
        }
        yielded += 1
        print(f"[erv] + album {aid} ({len(chosen)} imgs) {title[:36]}", file=sys.stderr)
        time.sleep(0.3)


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
    except Exception:  # noqa: BLE001
        pass
    return set()


def _save_dedupe(path: str | None, seen: set[str]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="Fetch erv-nsa.gov.tw Taiwan album photos → multi-image moments CSV")
    ap.add_argument("--posts", type=int, default=10, help="number of posts (albums) to produce")
    ap.add_argument("--imgs-per-post", type=int, default=9, help="max images per post (backend cap 9)")
    ap.add_argument("--min-imgs", type=int, default=3, help="skip albums with fewer than N photos")
    ap.add_argument("--listing-pages", type=int, default=6, help="how many album-list pages to scan")
    ap.add_argument("--include-ads", dest="exclude_ads", action="store_false")
    ap.add_argument("--dedupe-file", default=None, help="JSON of already-used album ids")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    seen = _load_dedupe(args.dedupe_file)
    rows: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent=UA, locale="zh-TW",
                            ignore_https_errors=True,
                            viewport={"width": 1366, "height": 900})
        pg = ctx.new_page()
        rows = list(iter_posts(
            pg, want_posts=args.posts, imgs_per_post=args.imgs_per_post,
            min_imgs=args.min_imgs, exclude_ads=args.exclude_ads,
            seen_albums=seen, listing_pages=args.listing_pages))
        b.close()

    if not rows:
        print("[warn] no posts produced", file=sys.stderr)
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    _save_dedupe(args.dedupe_file, seen)
    total = sum(len(r["image_urls"].split(",")) for r in rows)
    print(f"[OK] wrote {len(rows)} albums ({total} imgs) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
