#!/usr/bin/env python3
"""
fetch_vn_life.py — Fetch Vietnamese lifestyle content from five sources and write
a moments CSV where each ARTICLE becomes ONE MULTI-IMAGE post.
Playwright-based (JS-rendered sites).

Sources (public)
    baomoi       https://baomoi.com (Vietnamese news aggregator - lifestyle/food)
                 imgs: photo-baomoi.bmcdn.me, photo-baomoi.zadn.vn or similar CDN
    tuoitre      https://tuoitre.vn/cuoc-song.htm (Tuổi Trẻ - life section)
                 imgs: cdn.tuoitre.vn, static.tuoitre.vn
    vietnamnews  https://vietnamnews.vn/life-style (English-language Vietnam news)
                 imgs: image.vietnamnews.vn
    timeout      https://www.timeout.com/hanoi (Time Out Hanoi)
                 imgs: media.timeout.com, imagekit.io
    saigoneer    https://saigoneer.com (English-language Saigon lifestyle)
                 imgs: media.urbanistnetwork.com

Ad / non-content filtering
    - skip logos / banners / share-cards / doubleclick / avatars / tiny icons
    - skip articles whose title hits AD_KEYWORDS (Vietnamese + English)
    - keep only real content-image hosts per source

Each qualifying article (>= --min-imgs photos) -> one moments row whose
``image_urls`` is a comma-joined list of body-only images (variable count,
capped at --imgs-per-post).
``content`` is the article title (a scene/topic hint); rewrite later with
caption_multilang.py --langs vi for Vietnamese captions.

NOTE: these are editorial photos; no bottom-crop needed (Vietnam branch
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
    # Vietnamese
    "quảng cáo", "tài trợ", "khuyến mãi", "giảm giá", "ưu đãi",
    "mua ngay", "đặt hàng", "flash sale", "voucher", "coupon",
    # English
    "sponsored", "promotion", "advertisement", "advertorial", "PR:",
    "partner content", "paid partnership", "giveaway", "sale",
    "discount", "affiliate", "shop now", "buy now", "limited time",
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

def fetch_baomoi(pg, want: int, dedupe_set: set) -> list[dict]:
    """Fetch from baomoi.com lifestyle/food category."""
    print(f"[baomoi] Fetching up to {want} articles from baomoi.com ...")
    articles = []
    pg.goto("https://baomoi.com/suc-khoe-doi-song.epi", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)

    # Scroll to load more articles
    for _ in range(3):
        pg.mouse.wheel(0, 3000)
        pg.wait_for_timeout(2000)

    # Get article links
    links = pg.eval_on_selector_all(
        "a[href*='/']",
        """els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))
        .filter(o => o.href.includes('baomoi.com/')
                  && o.text.length > 10
                  && o.href.match(/\\.epi$|\\/[a-z0-9-]+\\.html$|\\/c\\/\\d+/)
                  && !o.href.includes('/tag/')
                  && !o.href.includes('/search'))"""
    )
    # Deduplicate links
    seen_hrefs = set()
    unique_links = []
    for lk in links:
        href = lk["href"].split("?")[0]
        if href not in seen_hrefs and href not in dedupe_set:
            seen_hrefs.add(href)
            unique_links.append(lk)

    print(f"[baomoi] Found {len(unique_links)} article links")
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
            for _ in range(2):
                pg.mouse.wheel(0, 2000)
                pg.wait_for_timeout(1000)
            imgs = pg.eval_on_selector_all(
                "img",
                "els => els.map(e => e.src || e.dataset?.src || '')"
                ".filter(u => u.startsWith('http') && (u.includes('photo-baomoi') || u.includes('bmcdn.me') || u.includes('zadn.vn')))"
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
                                 "url": href, "source": "baomoi"})
                print(f"  [baomoi] +1 article: {title[:40]}... ({len(clean)} imgs)")
        except Exception as e:
            print(f"  [baomoi] skip {href}: {e}")
        time.sleep(0.5)
    return articles


def fetch_tuoitre(pg, want: int, dedupe_set: set) -> list[dict]:
    """Fetch from tuoitre.vn life section."""
    print(f"[tuoitre] Fetching up to {want} articles from tuoitre.vn ...")
    articles = []
    pg.goto("https://tuoitre.vn/cuoc-song.htm", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)

    for _ in range(3):
        pg.mouse.wheel(0, 3000)
        pg.wait_for_timeout(2000)

    # Get article links
    links = pg.eval_on_selector_all(
        "a[href*='.htm']",
        """els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))
        .filter(o => o.href.includes('tuoitre.vn/')
                  && o.href.endsWith('.htm')
                  && o.text.length > 10
                  && !o.href.includes('/cuoc-song.htm')
                  && !o.href.includes('/tag/')
                  && !o.href.includes('/search'))"""
    )
    seen_hrefs = set()
    unique_links = []
    for lk in links:
        href = lk["href"].split("?")[0]
        if href not in seen_hrefs and href not in dedupe_set:
            seen_hrefs.add(href)
            unique_links.append(lk)

    print(f"[tuoitre] Found {len(unique_links)} article links")
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
            for _ in range(3):
                pg.mouse.wheel(0, 2000)
                pg.wait_for_timeout(1000)
            imgs = pg.eval_on_selector_all(
                "img",
                "els => els.map(e => e.src || e.dataset?.src || '')"
                ".filter(u => u.startsWith('http') && (u.includes('cdn.tuoitre.vn') || u.includes('static.tuoitre.vn')))"
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
                                 "url": href, "source": "tuoitre"})
                print(f"  [tuoitre] +1 article: {title[:40]}... ({len(clean)} imgs)")
        except Exception as e:
            print(f"  [tuoitre] skip {href}: {e}")
        time.sleep(0.5)
    return articles


def fetch_vietnamnews(pg, want: int, dedupe_set: set) -> list[dict]:
    """Fetch from vietnamnews.vn/life-style section."""
    print(f"[vietnamnews] Fetching up to {want} articles from vietnamnews.vn/life-style ...")
    articles = []
    pg.goto("https://vietnamnews.vn/life-style", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)

    for _ in range(3):
        pg.mouse.wheel(0, 3000)
        pg.wait_for_timeout(2000)

    links = pg.eval_on_selector_all(
        "a[href*='/life-style/']",
        """els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))
        .filter(o => o.href.includes('/life-style/')
                  && o.text.length > 10
                  && o.href.match(/\\d+\\.html$|\\/\\d+$/)
                  && !o.href.includes('/search')
                  && !o.href.includes('/tag/'))"""
    )
    seen_hrefs = set()
    unique_links = []
    for lk in links:
        href = lk["href"].split("?")[0]
        if href not in seen_hrefs and href not in dedupe_set:
            seen_hrefs.add(href)
            unique_links.append(lk)

    print(f"[vietnamnews] Found {len(unique_links)} article links")
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
                ".filter(u => u.startsWith('http') && (u.includes('image.vietnamnews.vn') || u.includes('vietnamnews.vn/')))"
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
                                 "url": href, "source": "vietnamnews"})
                print(f"  [vietnamnews] +1 article: {title[:40]}... ({len(clean)} imgs)")
        except Exception as e:
            print(f"  [vietnamnews] skip {href}: {e}")
        time.sleep(0.5)
    return articles


def fetch_timeout_hanoi(pg, want: int, dedupe_set: set) -> list[dict]:
    """Fetch from timeout.com/hanoi."""
    print(f"[timeout] Fetching up to {want} articles from timeout.com/hanoi ...")
    articles = []
    pg.goto("https://www.timeout.com/hanoi", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)

    for _ in range(3):
        pg.mouse.wheel(0, 3000)
        pg.wait_for_timeout(2000)

    links = pg.eval_on_selector_all(
        "a[href*='/hanoi/']",
        """els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))
        .filter(o => o.href.includes('/hanoi/')
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
                ".filter(u => u.startsWith('http') && (u.includes('imagekit.io') || u.includes('media.timeout.com') || u.includes('timeout.com')))"
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


def fetch_saigoneer(pg, want: int, dedupe_set: set) -> list[dict]:
    """Fetch from saigoneer.com (English-language Saigon lifestyle)."""
    print(f"[saigoneer] Fetching up to {want} articles from saigoneer.com ...")
    articles = []
    pg.goto("https://saigoneer.com", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(5000)

    for _ in range(4):
        pg.mouse.wheel(0, 3000)
        pg.wait_for_timeout(2000)

    links = pg.eval_on_selector_all(
        "a[href*='saigoneer.com/']",
        """els => els.map(e => ({href: e.href, text: (e.textContent||'').trim()}))
        .filter(o => o.text.length > 10
                  && !o.href.includes('/tag/')
                  && !o.href.includes('/category/')
                  && !o.href.includes('/page/')
                  && !o.href.includes('/author/')
                  && !o.href.includes('/search')
                  && o.href.match(/saigoneer\\.com\\/.+\\/.+/))"""
    )
    seen_hrefs = set()
    unique_links = []
    for lk in links:
        href = lk["href"].split("?")[0]
        if href not in seen_hrefs and href not in dedupe_set:
            seen_hrefs.add(href)
            unique_links.append(lk)

    print(f"[saigoneer] Found {len(unique_links)} article links")
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
            for _ in range(3):
                pg.mouse.wheel(0, 2000)
                pg.wait_for_timeout(1000)
            imgs = pg.eval_on_selector_all(
                "img",
                "els => els.map(e => e.src || e.dataset?.src || '')"
                ".filter(u => u.startsWith('http') && (u.includes('media.urbanistnetwork.com') || u.includes('saigoneer.com')))"
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
                                 "url": href, "source": "saigoneer"})
                print(f"  [saigoneer] +1 article: {title[:40]}... ({len(clean)} imgs)")
        except Exception as e:
            print(f"  [saigoneer] skip {href}: {e}")
        time.sleep(0.5)
    return articles


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    _ensure_utf8_stdout()
    ap = argparse.ArgumentParser(
        description="Fetch Vietnamese lifestyle articles (multi-image) from 5 sources",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--sources", default="baomoi,tuoitre,vietnamnews,timeout,saigoneer",
                    help="Comma-separated sources to fetch from")
    ap.add_argument("--posts", type=int, default=10,
                    help="Total number of articles to fetch (split across sources)")
    ap.add_argument("--imgs-per-post", type=int, default=9,
                    help="Max images per post")
    ap.add_argument("--min-imgs", type=int, default=2,
                    help="Minimum images for an article to qualify")
    ap.add_argument("--dedupe-file", default=None,
                    help="JSON file with previously used article URLs")
    ap.add_argument("--output", default="vn_raw.csv",
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
            "baomoi": fetch_baomoi,
            "tuoitre": fetch_tuoitre,
            "vietnamnews": fetch_vietnamnews,
            "timeout": fetch_timeout_hanoi,
            "saigoneer": fetch_saigoneer,
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
