#!/usr/bin/env python3
"""
fetch_sg_life.py — Fetch Singapore lifestyle content from four sources and write
a moments CSV where each ARTICLE becomes ONE MULTI-IMAGE post.
Playwright-based (JS-rendered sites).

Sources (public)
    herworld     https://www.herworld.com/life          imgs: cassette.sphdigital.com.sg/image/...
    tripzilla    https://www.tripzilla.com/.../singapore imgs: various CDN
    timeout      https://www.timeout.com/singapore      imgs: various CDN
    eatbook      https://eatbook.sg/                    imgs: eatbook.sg/wp-content/uploads/...

Ad / non-content filtering
    - skip logos / banners / share-cards / doubleclick / avatars / tiny icons
    - skip articles whose title hits AD_KEYWORDS (sponsored/promotion/giveaway/sale...)
    - keep only real content-image hosts per source

Each qualifying article (>= --min-imgs photos) -> one moments row whose
``image_urls`` is a comma-joined list of body-only images (variable count,
capped at --imgs-per-post).
``content`` is the article title (a scene/topic hint); rewrite later with
caption_multilang.py --langs en for English / Singapore captions.

NOTE: these are editorial photos; no bottom-crop needed (Singapore branch
disables cropping entirely).
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
    "sponsored", "promotion", "giveaway", "sale", "coupon", "promo code",
    "discount", "affiliate", "advertisement", "advertorial", "paid partnership",
    "shop now", "buy now", "limited time", "flash sale",
    "赞助", "广告", "优惠", "折扣", "促销",
]

JUNK = ["logo", "banner", "avatar", "icon", "sprite", "placeholder", "share",
        "doubleclick", "/ad/", "_ad_", "advert", "favicon", "author", "profile",
        "gravatar", "wp-emoji", "1x1", "pixel"]

# Known watermarked image hosts — skip these entirely (post will be text-only)
WATERMARK_HOSTS = ["500px.com", "dpreview.com", "gettyimages.com",
                   "shutterstock.com", "istockphoto.com", "alamy.com",
                   "dreamstime.com", "depositphotos.com", "123rf.com"]


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
    if any(j in low for j in JUNK):
        return True
    # Skip known watermarked image hosts
    if any(wh in low for wh in WATERMARK_HOSTS):
        return True
    return False


def _is_small_image(url: str) -> bool:
    """Detect small/thumbnail images from URL patterns."""
    # width/height < 200 in URL path segments
    m = re.search(r"[/\-_](\d{1,3})x(\d{1,3})[/\-_.]", url)
    if m and int(m.group(1)) < 200 and int(m.group(2)) < 200:
        return True
    # WordPress thumbnail suffixes like -150x150.jpg or -300x200.jpg
    if re.search(r"-\d{2,3}x\d{2,3}\.(jpg|jpeg|png|webp)", url, re.I):
        return True
    # URL query params indicating small size: w=300, width=200, size=thumb etc.
    if re.search(r"[?&](w|width|size)=(1\d{2}|2\d{2}|3[0-4]\d|thumb)", url, re.I):
        return True
    # Common thumbnail path segments
    if re.search(r"/(thumb|thumbnail|small|mini|icon|avatar|s\d{2,3})/", url, re.I):
        return True
    return False


def _photo_id(url: str) -> str:
    """Return a stable identity for dedup within one article."""
    u = url.split("?")[0]
    # strip size/crop variants
    u = re.sub(r"-\d+x\d+\.(jpg|jpeg|png|webp)$", r".\1", u, flags=re.I)
    u = re.sub(r"/w_\d+[^/]*/", "/", u)
    return u


# ---------------------------------------------------------------------------
# Source fetchers
# ---------------------------------------------------------------------------

def fetch_herworld(pg, want: int, dedupe_set: set) -> list[dict]:
    """Fetch from herworld.com/life category page."""
    print(f"[herworld] Fetching up to {want} articles from herworld.com/life ...")
    articles = []
    pg.goto("https://www.herworld.com/life", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)

    # Scroll to load more articles
    for _ in range(3):
        pg.mouse.wheel(0, 3000)
        pg.wait_for_timeout(2000)

    # Get article links
    links = pg.eval_on_selector_all(
        "a[href*='/life/']",
        "els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))"
        ".filter(o => o.href.includes('/life/') && o.text.length > 10)"
    )
    # Deduplicate links
    seen_hrefs = set()
    unique_links = []
    for lk in links:
        href = lk["href"].split("?")[0]
        if href not in seen_hrefs and href not in dedupe_set:
            seen_hrefs.add(href)
            unique_links.append(lk)

    print(f"[herworld] Found {len(unique_links)} article links")
    for lk in unique_links[:want * 2]:
        if len(articles) >= want:
            break
        href = lk["href"]
        title = lk["text"][:80]
        if looks_like_ad(title):
            continue
        try:
            pg.goto(href, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            imgs = pg.eval_on_selector_all(
                "img",
                "els => els.map(e => e.src || e.dataset?.src || '')"
                ".filter(u => u.startsWith('http') && (u.includes('cassette.sphdigital') || u.includes('herworld')))"
            )
            # Filter
            clean = []
            ids_seen = set()
            for u in imgs:
                if _is_junk(u) or _is_small_image(u):
                    continue
                pid = _photo_id(u)
                if pid in ids_seen:
                    continue
                ids_seen.add(pid)
                clean.append(u)
            if len(clean) >= 2:
                articles.append({"title": title, "images": clean[:9],
                                 "url": href, "source": "herworld"})
                print(f"  [herworld] +1 article: {title[:40]}... ({len(clean)} imgs)")
        except Exception as e:
            print(f"  [herworld] skip {href}: {e}")
        time.sleep(0.5)
    return articles


def fetch_eatbook(pg, want: int, dedupe_set: set) -> list[dict]:
    """Fetch from eatbook.sg homepage (food blog)."""
    print(f"[eatbook] Fetching up to {want} articles from eatbook.sg ...")
    articles = []
    pg.goto("https://eatbook.sg/", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)

    for _ in range(4):
        pg.mouse.wheel(0, 3000)
        pg.wait_for_timeout(2000)

    # Get article links
    links = pg.eval_on_selector_all(
        "a[href*='eatbook.sg/']",
        """els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))
        .filter(o => o.href.match(/eatbook\\.sg\\/[a-z0-9-]+\\/?$/)
                  && !o.href.includes('/category/')
                  && !o.href.includes('/tag/')
                  && !o.href.includes('/page/')
                  && !o.href.includes('/author/')
                  && o.text.length > 10)"""
    )
    seen_hrefs = set()
    unique_links = []
    for lk in links:
        href = lk["href"].split("?")[0].rstrip("/")
        if href not in seen_hrefs and href not in dedupe_set:
            seen_hrefs.add(href)
            unique_links.append(lk)

    print(f"[eatbook] Found {len(unique_links)} article links")
    for lk in unique_links[:want * 2]:
        if len(articles) >= want:
            break
        href = lk["href"]
        title = lk["text"][:80]
        if looks_like_ad(title):
            continue
        try:
            pg.goto(href, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            # Scroll to load lazy images
            for _ in range(3):
                pg.mouse.wheel(0, 2000)
                pg.wait_for_timeout(1000)
            imgs = pg.eval_on_selector_all(
                "img",
                "els => els.map(e => e.src || e.dataset?.lazySrc || e.dataset?.src || '')"
                ".filter(u => u.startsWith('http') && u.includes('eatbook.sg/wp-content/uploads'))"
            )
            clean = []
            ids_seen = set()
            for u in imgs:
                if _is_junk(u) or _is_small_image(u):
                    continue
                pid = _photo_id(u)
                if pid in ids_seen:
                    continue
                ids_seen.add(pid)
                clean.append(u)
            if len(clean) >= 2:
                articles.append({"title": title, "images": clean[:9],
                                 "url": href, "source": "eatbook"})
                print(f"  [eatbook] +1 article: {title[:40]}... ({len(clean)} imgs)")
        except Exception as e:
            print(f"  [eatbook] skip {href}: {e}")
        time.sleep(0.5)
    return articles


def fetch_timeout_sg(pg, want: int, dedupe_set: set) -> list[dict]:
    """Fetch from timeout.com/singapore."""
    print(f"[timeout] Fetching up to {want} articles from timeout.com/singapore ...")
    articles = []
    pg.goto("https://www.timeout.com/singapore", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)

    for _ in range(3):
        pg.mouse.wheel(0, 3000)
        pg.wait_for_timeout(2000)

    links = pg.eval_on_selector_all(
        "a[href*='/singapore/']",
        """els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))
        .filter(o => o.href.includes('/singapore/')
                  && o.text.length > 10
                  && !o.href.includes('/search')
                  && !o.href.includes('/profile'))"""
    )
    seen_hrefs = set()
    unique_links = []
    for lk in links:
        href = lk["href"].split("?")[0]
        if href not in seen_hrefs and href not in dedupe_set:
            seen_hrefs.add(href)
            unique_links.append(lk)

    print(f"[timeout] Found {len(unique_links)} article links")
    for lk in unique_links[:want * 2]:
        if len(articles) >= want:
            break
        href = lk["href"]
        title = lk["text"][:80]
        if looks_like_ad(title):
            continue
        try:
            pg.goto(href, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            imgs = pg.eval_on_selector_all(
                "img",
                "els => els.map(e => e.src || e.dataset?.src || '')"
                ".filter(u => u.startsWith('http') && (u.includes('imagekit.io') || u.includes('timeout.com') || u.includes('cdn.')))"
            )
            clean = []
            ids_seen = set()
            for u in imgs:
                if _is_junk(u) or _is_small_image(u):
                    continue
                pid = _photo_id(u)
                if pid in ids_seen:
                    continue
                ids_seen.add(pid)
                clean.append(u)
            if len(clean) >= 2:
                articles.append({"title": title, "images": clean[:9],
                                 "url": href, "source": "timeout"})
                print(f"  [timeout] +1 article: {title[:40]}... ({len(clean)} imgs)")
        except Exception as e:
            print(f"  [timeout] skip {href}: {e}")
        time.sleep(0.5)
    return articles


def fetch_tripzilla(pg, want: int, dedupe_set: set) -> list[dict]:
    """Fetch from tripzilla.com Singapore section."""
    print(f"[tripzilla] Fetching up to {want} articles from tripzilla.com ...")
    articles = []
    pg.goto("https://www.tripzilla.com/category/destinations/asia/southeast-asia/singapore",
            wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)

    for _ in range(3):
        pg.mouse.wheel(0, 3000)
        pg.wait_for_timeout(2000)

    links = pg.eval_on_selector_all(
        "a[href*='tripzilla.com/']",
        """els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))
        .filter(o => o.text.length > 10
                  && !o.href.includes('/category/')
                  && !o.href.includes('/tag/')
                  && !o.href.includes('/page/')
                  && !o.href.includes('/author/'))"""
    )
    seen_hrefs = set()
    unique_links = []
    for lk in links:
        href = lk["href"].split("?")[0]
        if href not in seen_hrefs and href not in dedupe_set:
            seen_hrefs.add(href)
            unique_links.append(lk)

    print(f"[tripzilla] Found {len(unique_links)} article links")
    for lk in unique_links[:want * 2]:
        if len(articles) >= want:
            break
        href = lk["href"]
        title = lk["text"][:80]
        if looks_like_ad(title):
            continue
        try:
            pg.goto(href, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            for _ in range(2):
                pg.mouse.wheel(0, 2000)
                pg.wait_for_timeout(1000)
            imgs = pg.eval_on_selector_all(
                "img",
                "els => els.map(e => e.src || e.dataset?.src || '')"
                ".filter(u => u.startsWith('http') && (u.includes('tripzilla') || u.includes('cdn') || u.includes('wp-content')))"
            )
            clean = []
            ids_seen = set()
            for u in imgs:
                if _is_junk(u) or _is_small_image(u):
                    continue
                pid = _photo_id(u)
                if pid in ids_seen:
                    continue
                ids_seen.add(pid)
                clean.append(u)
            if len(clean) >= 2:
                articles.append({"title": title, "images": clean[:9],
                                 "url": href, "source": "tripzilla"})
                print(f"  [tripzilla] +1 article: {title[:40]}... ({len(clean)} imgs)")
        except Exception as e:
            print(f"  [tripzilla] skip {href}: {e}")
        time.sleep(0.5)
    return articles


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(
        description="Fetch Singapore lifestyle articles (multi-image) from 4 sources",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--sources", default="herworld,eatbook,timeout,tripzilla",
                    help="Comma-separated sources to fetch from")
    ap.add_argument("--posts", type=int, default=10,
                    help="Total number of articles to fetch (split across sources)")
    ap.add_argument("--imgs-per-post", type=int, default=9,
                    help="Max images per post")
    ap.add_argument("--min-imgs", type=int, default=2,
                    help="Minimum images for an article to qualify")
    ap.add_argument("--dedupe-file", default=None,
                    help="JSON file with previously used article URLs")
    ap.add_argument("--output", default="sg_raw.csv",
                    help="Output CSV path")
    args = ap.parse_args()

    # Load dedupe set
    dedupe_set: set = set()
    if args.dedupe_file and Path(args.dedupe_file).exists():
        try:
            dedupe_set = set(json.loads(Path(args.dedupe_file).read_text(encoding="utf-8")))
            print(f"[dedupe] Loaded {len(dedupe_set)} seen URLs")
        except Exception as e:
            print(f"[dedupe] Warning loading {args.dedupe_file}: {e}")

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    per_source = max(1, args.posts // len(sources) + 1)

    # Launch Playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[error] playwright not installed. Run: pip install playwright && python -m playwright install chromium")
        return 1

    all_articles = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()

        fetchers = {
            "herworld": fetch_herworld,
            "eatbook": fetch_eatbook,
            "timeout": fetch_timeout_sg,
            "tripzilla": fetch_tripzilla,
        }

        for src in sources:
            fn = fetchers.get(src)
            if not fn:
                print(f"[warn] Unknown source: {src}")
                continue
            try:
                arts = fn(pg, per_source, dedupe_set)
                all_articles.extend(arts)
            except Exception as e:
                print(f"[warn] {src} failed: {e}")

        browser.close()

    # Trim to requested count
    all_articles = all_articles[:args.posts]

    if not all_articles:
        print("[warn] No articles fetched")
        return 1

    # Write CSV
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_lang", "_scene"]
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for art in all_articles:
            imgs = art["images"][:args.imgs_per_post]
            w.writerow({
                "content": art["title"],
                "visibility": 0,
                "room_id": "",
                "image_urls": ",".join(imgs),
                "location_name": "",
                "location_address": "",
                "location_lat": "",
                "location_lon": "",
                "_source": art["source"],
                "_lang": "",
                "_scene": "",
            })

    print(f"\n[done] Wrote {len(all_articles)} articles to {out}")
    print(f"  Sources: {', '.join(set(a['source'] for a in all_articles))}")

    # Update dedupe file
    if args.dedupe_file:
        new_urls = [a["url"] for a in all_articles]
        dedupe_set.update(new_urls)
        Path(args.dedupe_file).parent.mkdir(parents=True, exist_ok=True)
        Path(args.dedupe_file).write_text(
            json.dumps(sorted(dedupe_set), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[dedupe] Updated {args.dedupe_file} ({len(dedupe_set)} total)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
