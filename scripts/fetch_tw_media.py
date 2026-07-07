#!/usr/bin/env python3
"""
fetch_tw_media.py — Fetch Taiwan editorial media (photography / design / culture)
from three Taiwan sites and write a moments CSV where each ARTICLE becomes ONE
MULTI-IMAGE post. Playwright-based (all three are JS-rendered).

Sources (public)
    shoppingdesign  home -> /post/view/<id>     imgs: image-cdn.learnin.tw/...
    gq              /article/<slug> list+detail imgs: media.gq.com.tw/photos/...
    sony            home -> /article/<id>        imgs: alphauniverse.sony.com.tw/files/images/...

Ad / non-content filtering
    - skip logos / banners / share-cards / doubleclick / avatars (w_90 thumbs)
    - skip articles whose title hits AD_KEYWORDS (贊助/廣告/開箱抽獎/限時優惠/購買 ...)
    - keep only real content-image hosts per source

Each qualifying article (>= --min-imgs photos) -> one moments row whose
``image_urls`` is a comma-joined list of up to --imgs-per-post images.
``content`` is the article title (a scene/topic hint); rewrite later with
caption_multilang.py --langs zh_hant for 繁體中文 / Taiwan captions.

NOTE: these are watermark-free editorial photos; no bottom-crop is applied
(the taiwan branch disables cropping entirely — see docs/19-taiwan.md).
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

AD_KEYWORDS = [
    "贊助", "廣告", "業配", "抽獎", "優惠", "折扣", "促銷", "限時", "特價", "團購",
    "開箱抽", "購買", "選購", "預購", "下單", "商店", "購物車", "加入會員",
    "sponsored", "promotion", "sale", "coupon", "shop now",
]

# per-source content-image host + junk patterns
SD_HOST = "image-cdn.learnin.tw"
GQ_HOST = "media.gq.com.tw/photos/"
SONY_HOST = "alphauniverse.sony.com.tw/files/images/"

JUNK = ["logo", "banner", "avatar", "icon", "sprite", "placeholder", "share",
        "doubleclick", "/ad/", "_ad_", "advert", "sd_share"]


def _ensure_utf8_stdout():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


def looks_like_ad(title: str) -> bool:
    low = (title or "").lower()
    return any(k.lower() in low for k in AD_KEYWORDS)


def _is_junk(url: str) -> bool:
    low = url.lower()
    return any(j in low for j in JUNK)


def _gq_ok(url: str) -> bool:
    # drop tiny author avatars like .../1:1/w_90,c_limit/...
    if GQ_HOST not in url:
        return False
    m = re.search(r"/w_(\d+)", url)
    if m and int(m.group(1)) < 600:
        return False
    return not _is_junk(url)


def _scroll(pg, rounds=4, pause=1200):
    for _ in range(rounds):
        pg.mouse.wheel(0, 4200)
        pg.wait_for_timeout(pause)


def _imgs_on(pg) -> list[str]:
    return pg.eval_on_selector_all(
        "img",
        "els => els.map(e => e.src || e.getAttribute('data-src') || e.getAttribute('data-original') || '').filter(Boolean)")


def _title(pg) -> str:
    t = (pg.title() or "").split("|")[0].split("｜")[0].strip()
    return t


# ---- source: article link discovery ----

def sd_article_links(pg) -> list[str]:
    out, seen = [], set()
    for path in ["/", "/post/category/design", "/post/category/style",
                 "/post/category/travel", "/post/category/entertainment"]:
        try:
            pg.goto("https://www.shoppingdesign.com.tw" + path,
                    wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(3000)
            _scroll(pg, 2)
        except Exception:
            continue
        links = pg.eval_on_selector_all("a", "els=>els.map(e=>e.href||'').filter(Boolean)")
        for l in links:
            if re.search(r"/post/view/\d+", l) and l not in seen:
                seen.add(l)
                out.append(l)
    return out


def gq_article_links(pg) -> list[str]:
    out, seen = [], set()
    for path in ["/", "/life", "/fashion", "/lifestyle",
                 "/article/名人-台灣感性-地圖"]:
        try:
            pg.goto("https://www.gq.com.tw" + path,
                    wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_timeout(3000)
            _scroll(pg, 2)
        except Exception:
            continue
        links = pg.eval_on_selector_all("a", "els=>els.map(e=>e.href||'').filter(Boolean)")
        for l in links:
            if "/article/" in l and l not in seen:
                seen.add(l)
                out.append(l)
    return out


def sony_article_links(pg) -> list[str]:
    out, seen = [], set()
    try:
        pg.goto("https://alphauniverse.sony.com.tw/",
                wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(6000)
        _scroll(pg, 6)
    except Exception:
        return out
    links = pg.eval_on_selector_all("a", "els=>els.map(e=>e.href||'').filter(Boolean)")
    for l in links:
        if re.search(r"/article/\d+", l) and l not in seen:
            seen.add(l)
            out.append(l)
    return out


def article_photos(pg, url: str, source: str) -> tuple[str, list[str], str]:
    """Open the article page and extract, from the ARTICLE BODY only:
      - the content images (NOT the first-screen / hero KV image, NOT header/logo)
      - a text excerpt (title + first meaningful paragraphs) for caption matching

    Returns (title, [content_image_urls], excerpt).
    """
    pg.goto(url, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(3000)
    _scroll(pg, 5)
    title = _title(pg)

    host = {"shoppingdesign": SD_HOST, "gq": "media.gq.com.tw/photos",
            "sony": "files/images"}[source]

    data = pg.evaluate(
        """(host) => {
            // article body container (falls back to main/document)
            const art = document.querySelector('article, .article__body, [itemprop=articleBody]')
                        || document.querySelector('main') || document.body;
            const imgs = Array.from(art.querySelectorAll('img'))
                .map(i => i.currentSrc || i.src || i.getAttribute('data-src') || '')
                .filter(u => u && u.includes(host));
            const paras = Array.from(art.querySelectorAll('p,h2,h3,li,figcaption'))
                .map(e => (e.innerText || '').trim())
                .filter(t => t.length >= 15);
            return {imgs, paras};
        }""", host)

    raw_imgs = data.get("imgs", [])
    paras = data.get("paras", [])

    # de-dup + per-source cleanup, keeping order
    urls, seen = [], set()
    for s in raw_imgs:
        if source == "gq":
            if not _gq_ok(s):
                continue
            u = s  # keep sizing query
        else:
            if _is_junk(s):
                continue
            u = s.split("?")[0]
        key = u.split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        urls.append(u)

    # SKIP the first-screen / hero (KV) image = first image in the article body.
    if len(urls) > 1:
        urls = urls[1:]

    # build a text excerpt from title + first paragraphs (deduped, trimmed)
    seen_p, picked = set(), []
    for t in paras:
        t = re.sub(r"\s+", " ", t).strip()
        if len(t) < 15 or t in seen_p:
            continue
        seen_p.add(t)
        picked.append(t)
        if len(picked) >= 4:
            break
    excerpt = " ".join(picked)[:400]
    return title, urls, excerpt


DISCOVER = {
    "shoppingdesign": sd_article_links,
    "gq": gq_article_links,
    "sony": sony_article_links,
}


def iter_posts(pg, source: str, *, want_posts, imgs_per_post, min_imgs,
               exclude_ads, seen_articles):
    links = DISCOVER[source](pg)
    print(f"[{source}] {len(links)} article links", file=sys.stderr)
    yielded = 0
    for url in links:
        if yielded >= want_posts:
            return
        if url in seen_articles:
            continue
        try:
            title, photos, excerpt = article_photos(pg, url, source)
        except Exception as e:  # noqa: BLE001
            print(f"[{source}] {url[:50]} err: {e}", file=sys.stderr)
            continue
        if exclude_ads and looks_like_ad(title):
            print(f"[{source}] skip ad-like: {title[:26]}", file=sys.stderr)
            continue
        if len(photos) < min_imgs:
            continue
        seen_articles.add(url)
        yield {
            "content": (title or "台灣分享").strip(),
            "visibility": 0, "room_id": "",
            "image_urls": ",".join(photos[:imgs_per_post]),
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_source": source,
            "_excerpt": excerpt,
            "_url": url,
        }
        yielded += 1
        print(f"[{source}] + ({len(photos[:imgs_per_post])} imgs, body-only, no-hero) {title[:34]}", file=sys.stderr)
        time.sleep(0.3)


def _load_dedupe(path):
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, list):
            return {str(x) for x in d}
    except Exception:
        pass
    return set()


def _save_dedupe(path, seen):
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="Fetch Taiwan media (shoppingdesign/gq/sony) → multi-image moments CSV")
    ap.add_argument("--sources", default="shoppingdesign,gq,sony",
                    help="comma list: shoppingdesign,gq,sony")
    ap.add_argument("--posts", type=int, default=15, help="total posts across sources")
    ap.add_argument("--imgs-per-post", type=int, default=9)
    ap.add_argument("--min-imgs", type=int, default=3)
    ap.add_argument("--include-ads", dest="exclude_ads", action="store_false")
    ap.add_argument("--dedupe-file", default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    sources = [s.strip() for s in args.sources.split(",") if s.strip() in DISCOVER]
    seen = _load_dedupe(args.dedupe_file)
    # even split across sources
    base, rem = divmod(args.posts, len(sources))
    budget = {s: base + (1 if i < rem else 0) for i, s in enumerate(sources)}
    rows: list[dict] = []

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(user_agent=UA, locale="zh-TW", ignore_https_errors=True,
                            viewport={"width": 1366, "height": 900})
        pg = ctx.new_page()
        for src in sources:
            want = budget[src]
            got = list(iter_posts(pg, src, want_posts=want, imgs_per_post=args.imgs_per_post,
                                  min_imgs=args.min_imgs, exclude_ads=args.exclude_ads,
                                  seen_articles=seen))
            rows.extend(got)
            print(f"[{src}] produced {len(got)}/{want}", file=sys.stderr)
        b.close()

    if not rows:
        print("[warn] no posts produced", file=sys.stderr)
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_excerpt", "_url"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    _save_dedupe(args.dedupe_file, seen)
    from collections import Counter
    dist = Counter(r["_source"] for r in rows)
    total = sum(len(r["image_urls"].split(",")) for r in rows)
    print(f"[OK] wrote {len(rows)} posts ({total} imgs) → {out}")
    print(f"[OK] source distribution: {dict(dist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
