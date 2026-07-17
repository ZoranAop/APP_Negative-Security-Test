#!/usr/bin/env python3
"""
fetch_vintage_luxury.py — 中古轻奢（Vintage Luxury）标签采集脚本

从 15 个东南亚/港台中古奢侈品平台采集商品图文信息，
输出带英文话题标签（含站点英文名称）的 moments CSV。

特点：
  - 15 站点轮询采集，确保来源多样性
  - 自动生成英文话题标签：#VintageLuxury #PreLoved #<SiteName>
  - 输出与 publish_from_tokens.py 兼容的 CSV（图文帖）
  - 仅选择中古轻奢标签内容时，话题带网站英文名称，均为英文

用法：
    py -3 scripts/fetch_vintage_luxury.py --target 30 --output moments_vintage_luxury.csv

参见：docs/26-vintage-luxury.md
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
# Site registry
# ---------------------------------------------------------------------------

SITES = [
    # Global top platforms
    {"key": "vestiaire", "name": "VestiaireCollective", "url": "https://www.vestiairecollective.com", "region": "GLOBAL"},
    {"key": "therealreal", "name": "TheRealReal", "url": "https://www.therealreal.com", "region": "GLOBAL"},
    {"key": "fashionphile", "name": "Fashionphile", "url": "https://www.fashionphile.com", "region": "GLOBAL"},
    {"key": "rebag", "name": "Rebag", "url": "https://www.rebag.com", "region": "GLOBAL"},
    {"key": "theluxurycloset", "name": "TheLuxuryCloset", "url": "https://www.theluxurycloset.com", "region": "GLOBAL"},
    {"key": "collectorsquare", "name": "CollectorSquare", "url": "https://www.collectorsquare.com", "region": "GLOBAL"},
    {"key": "wpdiamonds", "name": "WPDiamonds", "url": "https://www.wpdiamonds.com", "region": "GLOBAL"},
    # Japan
    {"key": "komehyo", "name": "Komehyo", "url": "https://komehyo.jp", "region": "JP"},
    {"key": "brandoff_jp", "name": "BrandOffJP", "url": "https://www.brandoff.co.jp", "region": "JP"},
    {"key": "allu", "name": "ALLU", "url": "https://allu-official.com", "region": "JP"},
    {"key": "reclo", "name": "Reclo", "url": "https://reclo.jp", "region": "JP"},
    {"key": "ragtag", "name": "RAGTAG", "url": "https://www.ragtag.jp", "region": "JP"},
    {"key": "2ndstreet", "name": "2ndStreet", "url": "https://www.2ndstreet.jp", "region": "JP"},
    {"key": "daikokuya", "name": "Daikokuya", "url": "https://www.daikokuya78.com", "region": "JP"},
    {"key": "otakaraya", "name": "Otakaraya", "url": "https://ec.otakaraya.jp", "region": "JP"},
    # Singapore / Southeast Asia
    {"key": "huntstreet", "name": "HuntStreet", "url": "https://www.huntstreet.com", "region": "SG"},
    {"key": "styletribute", "name": "StyleTribute", "url": "https://www.styletribute.com", "region": "SG"},
    {"key": "ecoring_sg", "name": "EcoRingSG", "url": "https://eco-ring.com.sg", "region": "SG"},
    {"key": "carousell", "name": "Carousell", "url": "https://www.carousell.com", "region": "SG"},
    {"key": "chadiluxury", "name": "ChadiLuxury", "url": "https://chadiluxury.com", "region": "SG"},
    {"key": "hulaluxe", "name": "HulaLuxe", "url": "https://www.hulaluxe.com", "region": "SG"},
    {"key": "belluxestore", "name": "BelluxeStore", "url": "https://www.belluxestore.com", "region": "SG"},
    {"key": "luxee", "name": "Luxee", "url": "https://luxee.me", "region": "SG"},
    {"key": "brandoff", "name": "BrandOff", "url": "https://www.brandoff.com.hk", "region": "HK"},
    # Taiwan
    {"key": "popchill", "name": "PopChill", "url": "https://www.popchill.com", "region": "TW"},
    {"key": "carousell_tw", "name": "CarousellTW", "url": "https://www.carousell.com.tw", "region": "TW"},
    {"key": "luxuryvalley", "name": "LuxuryValley", "url": "https://www.luxuryvalley.asia", "region": "TW"},
    # Malaysia
    {"key": "luxeavenue", "name": "LuxeAvenue", "url": "https://luxeavenue.com.my", "region": "MY"},
    {"key": "carousell_my", "name": "CarousellMY", "url": "https://www.carousell.com.my", "region": "MY"},
    # Thailand
    {"key": "sfbrandname", "name": "SFBrandName", "url": "https://www.sfbrandname.com", "region": "TH"},
    {"key": "brandnamemoney", "name": "BrandNameMoney", "url": "https://www.brandnamemoney.com", "region": "TH"},
    {"key": "ecoring_th", "name": "EcoRingTH", "url": "https://eco-ring.co.th", "region": "TH"},
    {"key": "zalind", "name": "Zalind", "url": "https://www.zalind.com", "region": "TH"},
    # Korea
    {"key": "kream", "name": "KREAM", "url": "https://kream.co.kr", "region": "KR"},
    {"key": "mustit", "name": "MUSTIT", "url": "https://mustit.co.kr", "region": "KR"},
    {"key": "balaan", "name": "Balaan", "url": "https://www.balaan.co.kr", "region": "KR"},
    {"key": "bunjang", "name": "Bunjang", "url": "https://m.bunjang.co.kr", "region": "KR"},
    {"key": "soldout", "name": "SoldOut", "url": "https://soldout.co.kr", "region": "KR"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Common luxury brand keywords for content generation
BRANDS = [
    "Chanel", "Louis Vuitton", "Hermès", "Gucci", "Prada", "Dior", "Celine",
    "Bottega Veneta", "Saint Laurent", "Balenciaga", "Fendi", "Loewe",
    "Burberry", "Coach", "Michael Kors", "Tory Burch", "Kate Spade",
    "Valentino", "Givenchy", "Miu Miu", "Cartier", "Rolex", "Omega",
]

ITEM_TYPES = [
    "bag", "handbag", "tote", "clutch", "wallet", "crossbody",
    "shoulder bag", "backpack", "watch", "jewelry", "scarf", "belt",
    "sunglasses", "shoes", "sneakers", "heels",
]

CONDITIONS = [
    "Excellent condition", "Like new", "Gently used", "Mint condition",
    "Well maintained", "Pristine", "Barely used", "Great condition",
]

CAPTIONS_TEMPLATES = [
    "Found this stunning {brand} {item} — {condition}. The craftsmanship is unmatched.",
    "Pre-loved {brand} {item} in {condition}. Sustainable luxury at its finest.",
    "This {brand} {item} just came in — {condition}. A timeless classic.",
    "Obsessed with this {brand} {item}! {condition}, ready for a new home.",
    "Luxury finds: {brand} {item}. {condition} — looks brand new.",
    "Why buy new when vintage is this good? {brand} {item}, {condition}.",
    "Adding this {brand} {item} to the collection. {condition}!",
    "The beauty of pre-owned luxury — {brand} {item}. {condition}.",
    "Authenticated {brand} {item} — {condition}. Investment piece.",
    "Score of the day: {brand} {item}. {condition}, unbelievable find.",
]

IMG_RE = re.compile(r'(?:src|data-src)="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', re.I)
OG_IMG_RE = re.compile(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', re.I)

# Ad/junk image filter patterns (comprehensive)
AD_PATTERNS = [
    "logo", "icon", "favicon", "avatar", "sprite", "banner", "ad-", "ads/",
    "newsletter", "popup", "promo", "1x1", "pixel", "tracking", "badge",
    "svg", "gif", "placeholder", "facebook", "google", "twitter", "social",
    "share", "cookie", "cart", "payment", "visa", "mastercard", "apple-pay",
    "footer", "header-", "nav-", "menu", "flag", "loading", "spinner",
    "klarna", "paypal", "afterpay", "atome", "grab-pay", "applepay",
    "country", "lang-", "locale", "currency",
]


def _fetch_url(url, timeout=15):
    """Fetch URL with retry."""
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
    """Check if URL looks like an ad/tracking/icon/payment image."""
    low = url.lower()
    return any(pat in low for pat in AD_PATTERNS)


def _is_large_image_url(url):
    """Heuristic: URL suggests a large/product image (not thumbnail)."""
    low = url.lower()
    # Positive signals
    if any(s in low for s in ["product", "large", "1200", "1000", "800", "original",
                               "master", "grande", "1024", "2048", "hero", "main",
                               "upload", "catalog", "/p/", "/item/"]):
        return True
    # Negative signals
    if any(s in low for s in ["thumb", "small", "tiny", "50x", "100x", "150x",
                               "200x", "icon", "mini", "_s.", "_xs.", "_t.",
                               "40x", "24x", "30x", "60x"]):
        return False
    return len(url) > 70


def _extract_product_links(html):
    """Extract product/item detail page links from a listing page."""
    links = []
    patterns = [
        r'href="(/products/[^"#?]+)"',
        r'href="(/collections/[^"]+/products/[^"#?]+)"',
        r'href="(/p/[^"#?]+)"',
        r'href="(/item/[^"#?]+)"',
        r'href="(/shop/[^"#?]+)"',
        r'href="(/en[^"]*/products?/[^"#?]+)"',
        r'href="(/catalog/product/[^"#?]+)"',
        r'href="(/goods/[^"#?]+)"',
    ]
    for pat in patterns:
        found = re.findall(pat, html)
        for link in found:
            if link not in links and not _is_ad_image(link):
                links.append(link)
    return links[:10]


def _extract_quality_images(html, limit=5):
    """Extract high-quality product images, filtering ads/icons/small images.

    Strategy:
    1. og:image (usually the hero product image, guaranteed large)
    2. Large product images from page content
    3. Filter all ad/payment/tracking images
    """
    images = []
    seen = set()

    # Priority 1: og:image
    og_imgs = OG_IMG_RE.findall(html)
    for img in og_imgs:
        if img not in seen and not _is_ad_image(img):
            seen.add(img)
            images.append(img)

    # Priority 2: large product images
    all_imgs = IMG_RE.findall(html)
    for img in all_imgs:
        if img in seen:
            continue
        seen.add(img)
        if _is_ad_image(img):
            continue
        if _is_large_image_url(img):
            images.append(img)
        if len(images) >= limit:
            break

    return images


def _extract_product_images(html, limit=5):
    """Legacy wrapper — now delegates to quality-aware extraction."""
    return _extract_quality_images(html, limit)


def _generate_caption(site_name, rng):
    """Generate an English caption with brand + item + site hashtag."""
    brand = rng.choice(BRANDS)
    item = rng.choice(ITEM_TYPES)
    condition = rng.choice(CONDITIONS)
    template = rng.choice(CAPTIONS_TEMPLATES)
    caption = template.format(brand=brand, item=item, condition=condition.lower())

    # Generate hashtags: site name + 2 random from pool
    base_tags = [f"#{site_name}"]
    extra_tags = rng.sample([
        "#AuthenticLuxury", "#DesignerBags", "#LuxuryFinds",
        "#SecondHandLuxury", "#SustainableFashion", "#PreOwned",
        f"#{brand.replace(' ', '')}", "#TimelessStyle", "#LuxuryForLess",
    ], 2)
    hashtags = " ".join(base_tags + extra_tags)

    return f"{caption}\n{hashtags}"


def fetch_site_images(site, per_site=3, rng=None):
    """Fetch product images from a site using deep crawl (listing → product page).

    Strategy:
    1. Fetch listing/homepage
    2. Extract product detail page links (二级页面)
    3. Visit product pages to get og:image / large product images (三级页面)
    4. Fallback: extract images directly from listing page
    """
    if rng is None:
        rng = random.Random()

    results = []
    try:
        html = _fetch_url(site["url"])

        # Step 1: Try deep crawl — find product links
        product_links = _extract_product_links(html)

        if product_links:
            # Step 2: Visit product detail pages for high-quality images
            base_url = site["url"].rstrip("/")
            for link in product_links[:per_site + 2]:
                if len(results) >= per_site:
                    break
                full_url = base_url + link if link.startswith("/") else link
                try:
                    product_html = _fetch_url(full_url)
                    imgs = _extract_quality_images(product_html, limit=2)
                    if imgs:
                        caption = _generate_caption(site["name"], rng)
                        results.append({
                            "content": caption,
                            "image_urls": imgs[0],
                            "site_key": site["key"],
                            "site_name": site["name"],
                        })
                except Exception:
                    pass
                time.sleep(0.5)
        else:
            # Fallback: extract from listing page directly
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


def main() -> int:
    ap = argparse.ArgumentParser(
        description="中古轻奢（Vintage Luxury）图文采集：15 站点轮询 + 英文话题标签（含站点名）",
    )
    ap.add_argument("--target", type=int, default=30,
                    help="目标采集数量 (默认: 30)")
    ap.add_argument("--per-site", type=int, default=3,
                    help="每站点最多取几条 (默认: 3)")
    ap.add_argument("--output", "-o", type=str, default="moments_vintage_luxury.csv",
                    help="输出 CSV 路径")
    ap.add_argument("--seed", type=int, default=None,
                    help="随机种子（可复现）")
    args = ap.parse_args()

    rng = random.Random(args.seed)

    print(f"[INFO] 中古轻奢采集启动: target={args.target}, per_site={args.per_site}")
    print(f"[INFO] 站点数: {len(SITES)}")

    all_results = []

    # Shuffle sites for randomness
    sites_order = list(SITES)
    rng.shuffle(sites_order)

    for site in sites_order:
        if len(all_results) >= args.target:
            break
        remaining = args.target - len(all_results)
        want = min(args.per_site, remaining)
        print(f"  [{site['key']}] fetching (want={want})...", end=" ")

        items = fetch_site_images(site, per_site=want, rng=rng)
        all_results.extend(items)
        print(f"got {len(items)}")

        time.sleep(1)  # Polite delay

    # If not enough from real scraping, supplement with generated content
    if len(all_results) < args.target:
        print(f"\n[INFO] Got {len(all_results)} from scraping, supplementing to {args.target}...")
        supplement_sites = list(SITES)
        rng.shuffle(supplement_sites)
        idx = 0
        while len(all_results) < args.target:
            site = supplement_sites[idx % len(supplement_sites)]
            caption = _generate_caption(site["name"], rng)
            # Use a placeholder high-quality luxury image from the site
            all_results.append({
                "content": caption,
                "image_urls": "",  # Will be text-only if no image
                "site_key": site["key"],
                "site_name": site["name"],
            })
            idx += 1

    # Shuffle final results for mixed sources
    rng.shuffle(all_results)
    all_results = all_results[:args.target]

    # Stats
    from collections import Counter
    site_dist = Counter(r["site_name"] for r in all_results)
    print(f"\n[RESULT] {len(all_results)} items from {len(site_dist)} sites")
    for site, cnt in site_dist.most_common():
        print(f"  {site}: {cnt}")

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
                "_source": f"vintage_luxury_{r['site_key']}",
                "_tag": "vintage_luxury",
            })

    print(f"\n[SUCCESS] Wrote {len(all_results)} rows -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
