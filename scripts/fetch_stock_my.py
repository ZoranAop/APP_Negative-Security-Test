#!/usr/bin/env python3
"""
fetch_stock_my.py — Fetch watermark-free stock photos from 5 free sites
using a real (Playwright) browser, and write a moments CSV compatible with
``post_moments.py`` / ``publish_from_tokens.py``.

Why Playwright
    Pexels / Pixabay / Kaboompics sit behind a Cloudflare JS challenge; a plain
    HTTP GET returns 403 ("Just a moment..."). A headless real browser passes the
    challenge, renders the grid, and exposes the *original* CDN image urls. Those
    originals carry NO watermark (unlike Shutterstock / iStock comps), which is
    exactly the "open the detail / save the original" behaviour requested.

Sources (public, no API key)
    pexels       -> https://www.pexels.com/search/<q>/        img: images.pexels.com/photos/<id>/...
    pixabay      -> https://pixabay.com/photos/search/<q>/    img: cdn.pixabay.com/photo/....jpg
    unsplash     -> https://unsplash.com/s/photos/<q>         img: images.unsplash.com/photo-...
    kaboompics   -> https://kaboompics.com/gallery?search=<q> img: kaboompics.com/cache_1/<...>/<hash>.jpeg
    gratisography-> https://gratisography.com/?s=<q>          img: gratisography.com/wp-content/uploads/...jpg

Output CSV columns (identical to the other fetch_* scripts, plus _source)
    content,visibility,room_id,image_urls,
    location_name,location_address,location_lat,location_lon,_source

The ``content`` here is the photo's alt/title text (used only as a scene hint);
run caption_multilang.py afterwards to rewrite it (e.g. into Malay).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")


def _ensure_utf8_stdout():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


def _scroll(pg, rounds: int, pause_ms: int = 1500):
    for _ in range(rounds):
        pg.mouse.wheel(0, 4200)
        pg.wait_for_timeout(pause_ms)


def _pixabay_upgrade(url: str) -> str:
    # cdn.pixabay.com/photo/..._640.jpg -> _1280.jpg (larger, still free)
    return re.sub(r"_(\d{2,4})\.(jpg|jpeg|png)$", r"_1280.\2", url)


def fetch_pexels(pg, query: str, want: int) -> list[dict]:
    pg.goto(f"https://www.pexels.com/search/{query}/",
            wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(7000)
    _scroll(pg, rounds=max(3, want // 12 + 2))
    items = pg.eval_on_selector_all(
        "img",
        "els => els.map(e => ({src: e.src||'', alt: e.alt||''}))"
        ".filter(o => o.src.includes('images.pexels.com/photos/'))",
    )
    out, seen = [], set()
    for it in items:
        clean = it["src"].split("?")[0]
        if clean in seen:
            continue
        seen.add(clean)
        # request a reasonable size via query (w=1260) — original is watermark free
        url = clean + "?auto=compress&cs=tinysrgb&w=1260"
        out.append({"image_urls": url, "content": (it.get("alt") or "").strip(),
                    "_source": "pexels"})
        if len(out) >= want:
            break
    return out


def fetch_pixabay(pg, query: str, want: int) -> list[dict]:
    pg.goto(f"https://pixabay.com/photos/search/{query}/",
            wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(7000)
    _scroll(pg, rounds=max(3, want // 12 + 2))
    items = pg.eval_on_selector_all(
        "img",
        "els => els.map(e => ({src: e.src||e.getAttribute('data-src')||'', alt: e.alt||''}))"
        ".filter(o => o.src.includes('cdn.pixabay.com/photo'))",
    )
    out, seen = [], set()
    for it in items:
        url = _pixabay_upgrade(it["src"].split("?")[0])
        if url in seen:
            continue
        seen.add(url)
        out.append({"image_urls": url, "content": (it.get("alt") or "").strip(),
                    "_source": "pixabay"})
        if len(out) >= want:
            break
    return out


def fetch_unsplash(pg, query: str, want: int) -> list[dict]:
    pg.goto(f"https://unsplash.com/s/photos/{query}",
            wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(7000)
    _scroll(pg, rounds=max(4, want // 10 + 2))
    items = pg.eval_on_selector_all(
        "img",
        "els => els.map(e => ({src: e.src||'', alt: e.alt||''}))"
        ".filter(o => o.src.includes('images.unsplash.com/photo-'))",
    )
    out, seen = [], set()
    for it in items:
        clean = it["src"].split("?")[0]
        if clean in seen:
            continue
        seen.add(clean)
        # request a reasonable download size; original is watermark free
        url = clean + "?fm=jpg&q=80&w=1440&fit=max"
        out.append({"image_urls": url, "content": (it.get("alt") or "").strip(),
                    "_source": "unsplash"})
        if len(out) >= want:
            break
    return out


def fetch_kaboompics(pg, query: str, want: int) -> list[dict]:
    import urllib.parse
    q = urllib.parse.quote(query or "")
    url = f"https://kaboompics.com/gallery?search={q}"
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(9000)
    _scroll(pg, rounds=max(4, want // 12 + 3))
    items = pg.eval_on_selector_all(
        "img",
        "els => els.map(e => e.src||'').filter(o => o.includes('cache'))",
    )
    out, seen = [], set()
    for it in items:
        clean = it.split("?")[0]
        if clean in seen:
            continue
        seen.add(clean)
        out.append({"image_urls": clean, "content": "", "_source": "kaboompics"})
        if len(out) >= want:
            break
    return out


def fetch_gratisography(pg, query: str, want: int) -> list[dict]:
    import urllib.parse
    q = urllib.parse.quote(query or "")
    url = f"https://gratisography.com/?s={q}"
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)
    _scroll(pg, rounds=max(3, want // 10 + 2))
    items = pg.eval_on_selector_all(
        "img",
        "els => els.map(e => e.src||'').filter(o => o.includes('wp-content/uploads'))",
    )
    out, seen = [], set()
    for it in items:
        clean = it.split("?")[0]
        if clean in seen:
            continue
        seen.add(clean)
        out.append({"image_urls": clean, "content": "", "_source": "gratisography"})
        if len(out) >= want:
            break
    return out


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
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="Fetch watermark-free Malaysia photos (Pexels+Pixabay) → CSV")
    ap.add_argument("--sources", default="pexels,pixabay",
                    help="comma list: pexels,pixabay,unsplash,kaboompics,gratisography")
    ap.add_argument("--query", default="malaysia")
    ap.add_argument("--per-source", type=int, default=30,
                    help="max images to take from each source")
    ap.add_argument("--dedupe-file", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--locale", default="ms-MY",
                    help="browser locale (e.g. ms-MY for Malaysia, id-ID for Indonesia)")
    ap.add_argument("--headful", action="store_true", help="show browser (debug)")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    seen = _load_dedupe(args.dedupe_file)
    rows: list[dict] = []

    with sync_playwright() as p:
        b = p.chromium.launch(headless=not args.headful)
        ctx = b.new_context(user_agent=UA, locale=args.locale,
                            viewport={"width": 1366, "height": 900})
        pg = ctx.new_page()
        for src in sources:
            try:
                if src == "pexels":
                    got = fetch_pexels(pg, args.query, args.per_source)
                elif src == "pixabay":
                    got = fetch_pixabay(pg, args.query, args.per_source)
                elif src == "unsplash":
                    got = fetch_unsplash(pg, args.query, args.per_source)
                elif src == "kaboompics":
                    got = fetch_kaboompics(pg, args.query, args.per_source)
                elif src == "gratisography":
                    got = fetch_gratisography(pg, args.query, args.per_source)
                else:
                    print(f"[warn] unknown source {src}", file=sys.stderr)
                    continue
            except Exception as e:  # noqa: BLE001
                print(f"[warn] {src} fetch failed: {e}", file=sys.stderr)
                continue
            kept = 0
            for r in got:
                if r["image_urls"] in seen:
                    continue
                seen.add(r["image_urls"])
                rows.append({
                    "content": r["content"] or "Malaysia",
                    "visibility": 0, "room_id": "",
                    "image_urls": r["image_urls"],
                    "location_name": "", "location_address": "",
                    "location_lat": "", "location_lon": "",
                    "_source": r["_source"],
                })
                kept += 1
            print(f"[{src}] kept {kept}", file=sys.stderr)
            time.sleep(1.0)
        b.close()

    if not rows:
        print("[warn] no rows produced", file=sys.stderr)
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
    from collections import Counter
    dist = Counter(r["_source"] for r in rows)
    print(f"[OK] wrote {len(rows)} photos → {out}")
    print(f"[OK] source distribution: {dict(dist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
