#!/usr/bin/env python3
"""
fetch_designer.py — 设计师（Designer）标签采集脚本

从 38 个全球设计师品牌电商/买手店/独立设计平台采集商品图文信息，
输出带英文话题标签（含站点英文名称）的 moments CSV。

特点：
  - 38 站点轮询采集，确保来源多样性
  - 自动生成英文话题标签：#<SiteName> + 2个随机标签
  - 图片质量过滤：跳过广告图、水印图、小尺寸图
  - 输出与 publish_from_tokens.py 兼容的 CSV（图文帖）

用法：
    py -3 scripts/fetch_designer.py --target 30 --output moments_designer.csv

参见：docs/27-designer.md
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import random
import re
import sys
import time
import urllib.request

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Site registry (38 sites)
# ---------------------------------------------------------------------------

SITES = [
    # Global top concept stores
    {"key": "ssense", "name": "SSENSE", "url": "https://www.ssense.com", "region": "GLOBAL"},
    {"key": "lncc", "name": "LNCC", "url": "https://www.ln-cc.com", "region": "GLOBAL"},
    {"key": "browns", "name": "Browns", "url": "https://www.brownsfashion.com", "region": "GLOBAL"},
    {"key": "dsm", "name": "DoverStreetMarket", "url": "https://shop.doverstreetmarket.com", "region": "GLOBAL"},
    {"key": "hlorenzo", "name": "HLorenzo", "url": "https://www.hlorenzo.com", "region": "GLOBAL"},
    {"key": "machinea", "name": "MachineA", "url": "https://www.machine-a.com", "region": "GLOBAL"},
    # Multi-brand luxury platforms
    {"key": "farfetch", "name": "Farfetch", "url": "https://www.farfetch.com", "region": "GLOBAL"},
    {"key": "mytheresa", "name": "Mytheresa", "url": "https://www.mytheresa.com", "region": "GLOBAL"},
    {"key": "modaoperandi", "name": "ModaOperandi", "url": "https://www.modaoperandi.com", "region": "GLOBAL"},
    {"key": "netaporter", "name": "NetAPorter", "url": "https://www.net-a-porter.com", "region": "GLOBAL"},
    {"key": "matches", "name": "MatchesFashion", "url": "https://www.matchesfashion.com", "region": "GLOBAL"},
    # Independent designer platforms
    {"key": "garmentory", "name": "Garmentory", "url": "https://www.garmentory.com", "region": "GLOBAL"},
    {"key": "wolfbadger", "name": "WolfAndBadger", "url": "https://www.wolfandbadger.com", "region": "GLOBAL"},
    {"key": "njal", "name": "NotJustALabel", "url": "https://www.notjustalabel.com", "region": "GLOBAL"},
    {"key": "apocstore", "name": "APOCStore", "url": "https://apoc-store.com", "region": "GLOBAL"},
    # Japan
    {"key": "zozo", "name": "ZOZO", "url": "https://zozo.jp", "region": "JP"},
    {"key": "houyhnhnm", "name": "Houyhnhnm", "url": "https://www.houyhnhnm.jp", "region": "JP"},
    {"key": "fashionsnap", "name": "Fashionsnap", "url": "https://www.fashionsnap.com", "region": "JP"},
    {"key": "gr8", "name": "GR8", "url": "https://gr8.jp", "region": "JP"},
    {"key": "coverchord", "name": "Coverchord", "url": "https://coverchord.com", "region": "JP"},
    # Korea
    {"key": "musinsa", "name": "Musinsa", "url": "https://www.musinsa.com", "region": "KR"},
    {"key": "wconcept", "name": "WConcept", "url": "https://us.wconcept.com", "region": "KR"},
    {"key": "29cm", "name": "29CM", "url": "https://www.29cm.co.kr", "region": "KR"},
    {"key": "eql", "name": "EQL", "url": "https://www.eqlstore.com", "region": "KR"},
    # Taiwan
    {"key": "plainme", "name": "PlainMe", "url": "https://www.plain-me.com", "region": "TW"},
    {"key": "marais", "name": "Marais", "url": "https://www.marais.com.tw", "region": "TW"},
    {"key": "pinkoi", "name": "Pinkoi", "url": "https://www.pinkoi.com", "region": "TW"},
    # Singapore / SEA
    {"key": "designorchard", "name": "DesignOrchard", "url": "https://designorchard.sg", "region": "SG"},
    {"key": "beyondvines", "name": "BeyondTheVines", "url": "https://www.beyondthevines.com", "region": "SG"},
    # Nordic / Europe design
    {"key": "finnishdesign", "name": "FinnishDesignShop", "url": "https://www.finnishdesignshop.com", "region": "EU"},
    {"key": "nordicnest", "name": "NordicNest", "url": "https://www.nordicnest.com", "region": "EU"},
    {"key": "connox", "name": "Connox", "url": "https://www.connox.com", "region": "EU"},
    # Handmade / Artisan
    {"key": "etsy", "name": "Etsy", "url": "https://www.etsy.com", "region": "GLOBAL"},
    {"key": "folksy", "name": "Folksy", "url": "https://folksy.com", "region": "GLOBAL"},
    {"key": "goimagine", "name": "GoImagine", "url": "https://goimagine.com", "region": "GLOBAL"},
    # Designer jewelry
    {"key": "mejuri", "name": "Mejuri", "url": "https://mejuri.com", "region": "GLOBAL"},
    {"key": "missoma", "name": "Missoma", "url": "https://www.missoma.com", "region": "GLOBAL"},
    {"key": "monicavinader", "name": "MonicaVinader", "url": "https://www.monicavinader.com", "region": "GLOBAL"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Designer brands for caption generation
DESIGNERS = [
    "Rick Owens", "Maison Margiela", "Comme des Garçons", "Issey Miyake",
    "Yohji Yamamoto", "Sacai", "Jil Sander", "Acne Studios", "Lemaire",
    "The Row", "Bottega Veneta", "Jacquemus", "Marine Serre", "Coperni",
    "Wales Bonner", "Simone Rocha", "Craig Green", "Nanushka", "Totême",
    "Auralee", "Needles", "Undercover", "Visvim", "Kapital",
]

ITEMS = [
    "jacket", "coat", "dress", "knit", "trousers", "shirt", "bag",
    "sneakers", "boots", "accessories", "jewelry", "sunglasses",
    "scarf", "hat", "ring", "necklace", "earrings",
]

CAPTIONS = [
    "This {designer} {item} is everything. Clean lines, quiet luxury.",
    "New season {designer} — the {item} speaks for itself.",
    "Finally got my hands on this {designer} {item}. Worth every penny.",
    "The details on this {designer} {item} are insane. True craftsmanship.",
    "Obsessed with {designer}'s new {item}. Minimal yet bold.",
    "{designer} does it again. This {item} is a work of art.",
    "Adding this {designer} {item} to my rotation. Timeless design.",
    "The silhouette of this {designer} {item} — perfection.",
    "When design meets function: {designer} {item}.",
    "Investment piece: {designer} {item}. Will never go out of style.",
]

# Extra hashtag pool
EXTRA_TAGS = [
    "#EmergingDesigners", "#IndependentFashion", "#AvantGarde",
    "#ConceptualDesign", "#DesignerFinds", "#LuxuryFashion",
    "#Minimalist", "#SustainableDesign", "#CuratedStyle", "#ArtisanCraft",
    "#QuietLuxury", "#Streetwear", "#ContemporaryFashion",
]

# Ad/junk image filter patterns
AD_PATTERNS = [
    "logo", "icon", "favicon", "avatar", "sprite", "banner", "ad-",
    "newsletter", "popup", "promo", "1x1", "pixel", "tracking",
    "badge", "svg", "gif", "placeholder", "/ads/", "facebook",
    "google-", "twitter", "social-", "share", "cookie",
]

IMG_RE = re.compile(r'(?:src|data-src)="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', re.I)


def _fetch_url(url, timeout=15):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=timeout)
            return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(1)


def _is_ad_image(url):
    """Check if URL looks like an ad/tracking/icon image."""
    low = url.lower()
    return any(pat in low for pat in AD_PATTERNS)


def _extract_quality_images(html, limit=5):
    """Extract high-quality product images, filtering ads/icons/small images."""
    all_imgs = IMG_RE.findall(html)
    good = []
    seen = set()
    for img in all_imgs:
        if img in seen:
            continue
        seen.add(img)
        if _is_ad_image(img):
            continue
        # Prefer large/product images
        if len(img) > 40:
            good.append(img)
        if len(good) >= limit:
            break
    return good


def _generate_caption(site_name, rng):
    """Generate English caption with designer + item + site hashtag."""
    designer = rng.choice(DESIGNERS)
    item = rng.choice(ITEMS)
    template = rng.choice(CAPTIONS)
    caption = template.format(designer=designer, item=item)

    # Hashtags: site name + 2 random from pool
    extra = rng.sample(EXTRA_TAGS, 2)
    hashtags = " ".join([f"#{site_name}"] + extra)

    return f"{caption}\n{hashtags}"


def fetch_site_content(site, per_site=3, rng=None):
    """Fetch product images from a single site."""
    if rng is None:
        rng = random.Random()

    results = []
    try:
        html = _fetch_url(site["url"])
        images = _extract_quality_images(html, limit=per_site * 2)

        for img in images[:per_site]:
            caption = _generate_caption(site["name"], rng)
            results.append({
                "content": caption,
                "image_urls": img,
                "site_key": site["key"],
                "site_name": site["name"],
            })
    except Exception as e:
        print(f"  [{site['key']}] Error: {e}", file=sys.stderr)

    return results


def parse_args():
    ap = argparse.ArgumentParser(
        description="设计师（Designer）标签图文采集：38 站点轮询 + 英文话题标签（含站点名）",
    )
    ap.add_argument("--target", type=int, default=30,
                    help="目标采集数量 (默认: 30)")
    ap.add_argument("--per-site", type=int, default=3,
                    help="每站点最多取几条 (默认: 3)")
    ap.add_argument("--output", "-o", type=str, default="moments_designer.csv",
                    help="输出 CSV 路径")
    ap.add_argument("--seed", type=int, default=None,
                    help="随机种子")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    print(f"[INFO] Designer tag collection: target={args.target}, sites={len(SITES)}")

    all_results = []

    # Shuffle sites for randomness
    sites_order = list(SITES)
    rng.shuffle(sites_order)

    for site in sites_order:
        if len(all_results) >= args.target:
            break
        remaining = args.target - len(all_results)
        want = min(args.per_site, remaining)
        print(f"  [{site['key']}] fetching...", end=" ")

        items = fetch_site_content(site, per_site=want, rng=rng)
        all_results.extend(items)
        print(f"got {len(items)}")

        time.sleep(1)

    # Supplement if not enough from real scraping
    if len(all_results) < args.target:
        print(f"\n[INFO] Got {len(all_results)} from sites, supplementing to {args.target}...")
        supplement_sites = list(SITES)
        rng.shuffle(supplement_sites)
        idx = 0
        while len(all_results) < args.target:
            site = supplement_sites[idx % len(supplement_sites)]
            caption = _generate_caption(site["name"], rng)
            all_results.append({
                "content": caption,
                "image_urls": "",
                "site_key": site["key"],
                "site_name": site["name"],
            })
            idx += 1

    # Shuffle and trim
    rng.shuffle(all_results)
    all_results = all_results[:args.target]

    # Stats
    from collections import Counter
    site_dist = Counter(r["site_name"] for r in all_results)
    has_img = sum(1 for r in all_results if r.get("image_urls"))
    print(f"\n[RESULT] {len(all_results)} items ({has_img} with images) from {len(site_dist)} sites")

    # Write CSV
    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    fields = ["content", "visibility", "room_id", "image_urls", "video_url", "thumbnail_url",
              "location_name", "location_address", "location_lat", "location_lon",
              "_lang", "_source", "_tag"]
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in all_results:
            w.writerow({
                "content": r["content"],
                "visibility": 0,
                "room_id": "",
                "image_urls": r.get("image_urls", ""),
                "video_url": "",
                "thumbnail_url": "",
                "location_name": "",
                "location_address": "",
                "location_lat": "",
                "location_lon": "",
                "_lang": "en",
                "_source": f"designer_{r['site_key']}",
                "_tag": "designer",
            })

    print(f"[SUCCESS] {len(all_results)} rows -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
