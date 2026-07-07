#!/usr/bin/env python3
"""
fetch_backpackers_my.py — Fetch Malaysia travel trip-report photos from the
backpackers.com.tw forum (f=111, "馬來西亞") and write a moments CSV where each
row is ONE thread turned into a MULTI-IMAGE post.

Source (public, no login, plain HTTP — no Cloudflare)
    Forum listing:  https://www.backpackers.com.tw/forum/forumdisplay.php?f=<fid>
    Thread page:    https://www.backpackers.com.tw/forum/showthread.php?t=<tid>
    Attachments:    https://sa[1].bbkz.net/forum/attachment.php?attachmentid=<id>&d=<d>
                    (the &thumb=1 variant is a thumbnail; dropping it gives full size;
                     works without the session `s=` param and without Referer.)

Each qualifying thread (>= --min-imgs photos) becomes a single moments row whose
``image_urls`` is a comma-joined list of up to --imgs-per-post FULL-SIZE photos.
``content`` is the thread title (a scene hint); rewrite later with
caption_multilang.py --langs ms for Malay captions.

Output CSV columns (compatible with post_moments.py / publish_from_tokens.py, +_source)
    content,visibility,room_id,image_urls,
    location_name,location_address,location_lat,location_lon,_source

Watermark
    Forum attachment photos carry a bottom/bottom-right forum watermark. It is
    removed the same way as Xiaohongshu: publish_from_tokens.py crops off the
    bottom strip before upload for any host in POST_CROP_BOTTOM_HOSTS (which now
    includes ``bbkz.net`` by default). Tune with POST_CROP_BOTTOM_PCT (default 0.08).
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://www.backpackers.com.tw/forum"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9,ms;q=0.8,en;q=0.7"}

AD_KEYWORDS = [
    "廣告", "推廣", "代購", "代辦", "優惠", "折扣", "促銷", "招商", "加盟", "代理",
    "徵求", "換匯", "賣", "售", "轉讓", "團購", "揪團", "問卷", "調查",
    "line", "微信", "wechat", "whatsapp", "旅行社", "包車", "客服",
    "coupon", "discount", "promo", "sponsor", "advertisement",
]


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


def _clean_attachment_url(raw: str) -> str:
    """Normalise an attachment img src to a stable full-size URL:
    - unescape &amp;
    - drop the session `s=` param and the `thumb=1` param
    """
    u = html.unescape(raw)
    aid = re.search(r"attachmentid=(\d+)", u)
    d = re.search(r"[?&]d=(\d+)", u)
    host = re.match(r"(https?://[^/]+)/", u)
    if not (aid and host):
        return ""
    base = f"{host.group(1)}/forum/attachment.php?attachmentid={aid.group(1)}"
    if d:
        base += f"&d={d.group(1)}"
    return base


def list_threads(session: requests.Session, fid: int, timeout: int, pages: int = 1) -> list[tuple[str, str]]:
    """Return [(thread_id, title)] for the forum listing across ``pages`` pages."""
    out, seen = [], set()
    for pg in range(1, pages + 1):
        url = f"{BASE}/forumdisplay.php?f={fid}&order=desc&page={pg}"
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"[bp] listing page {pg} err: {e}", file=sys.stderr)
            continue
        pairs = re.findall(
            r'href="showthread\.php\?[^"]*?t=(\d+)"[^>]*id="thread_title_\d+"[^>]*>([^<]+)</a>',
            r.text,
        )
        for tid, title in pairs:
            if tid in seen:
                continue
            seen.add(tid)
            out.append((tid, html.unescape(title).strip()))
        time.sleep(0.3)
    return out


def thread_photos(session: requests.Session, tid: str, timeout: int) -> tuple[str, list[str]]:
    """Return (title, [full-size attachment urls]) for a thread's first page."""
    r = session.get(f"{BASE}/showthread.php?t={tid}", headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    t = r.text
    m = re.search(r"<title>([^<]+)</title>", t)
    title = html.unescape(m.group(1)).split("-")[0].strip() if m else ""
    raw_imgs = re.findall(r'<img[^>]+src="(https?://sa1?\.bbkz\.net/forum/attachment\.php[^"]+)"', t)
    urls, seen = [], set()
    for raw in raw_imgs:
        u = _clean_attachment_url(raw)
        if u and u not in seen:
            seen.add(u)
            urls.append(u)
    return title, urls


def iter_posts(
    fid: int,
    *,
    want_posts: int,
    imgs_per_post: int = 9,
    min_imgs: int = 3,
    exclude_ads: bool = True,
    seen_threads: set[str] | None = None,
    timeout: int = 30,
    listing_pages: int = 3,
):
    """Yield moments rows (one per qualifying thread) as multi-image posts."""
    if seen_threads is None:
        seen_threads = set()
    session = requests.Session()
    threads = list_threads(session, fid, timeout, pages=listing_pages)
    print(f"[bp] forum f={fid}: {len(threads)} threads listed", file=sys.stderr)

    yielded = 0
    for tid, title in threads:
        if yielded >= want_posts:
            return
        if tid in seen_threads:
            continue
        if exclude_ads and looks_like_ad(title):
            print(f"[bp] skip ad-like t={tid}: {title[:30]}", file=sys.stderr)
            continue
        try:
            real_title, photos = thread_photos(session, tid, timeout)
        except Exception as e:  # noqa: BLE001
            print(f"[bp] thread {tid} err: {e}", file=sys.stderr)
            continue
        if len(photos) < min_imgs:
            continue
        chosen = photos[:imgs_per_post]
        seen_threads.add(tid)
        yield {
            "content": (real_title or title or "Malaysia").strip(),
            "visibility": 0,
            "room_id": "",
            "image_urls": ",".join(chosen),
            "location_name": "",
            "location_address": "",
            "location_lat": "",
            "location_lon": "",
            "_source": "backpackers",
        }
        yielded += 1
        print(f"[bp] + t={tid} ({len(chosen)} imgs) {real_title[:36]}", file=sys.stderr)
        time.sleep(0.4)


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
    ap = argparse.ArgumentParser(description="Fetch backpackers.com.tw Malaysia trip photos → multi-image moments CSV")
    ap.add_argument("--fid", type=int, default=111, help="forum id (111 = 馬來西亞)")
    ap.add_argument("--posts", type=int, default=10, help="number of posts (threads) to produce")
    ap.add_argument("--imgs-per-post", type=int, default=9, help="max images per post (backend cap is 9)")
    ap.add_argument("--min-imgs", type=int, default=3, help="skip threads with fewer than N photos")
    ap.add_argument("--listing-pages", type=int, default=3, help="how many forum listing pages to scan")
    ap.add_argument("--include-ads", dest="exclude_ads", action="store_false")
    ap.add_argument("--dedupe-file", default=None, help="JSON of already-used thread ids")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    seen = _load_dedupe(args.dedupe_file)
    rows = list(iter_posts(
        args.fid,
        want_posts=args.posts,
        imgs_per_post=args.imgs_per_post,
        min_imgs=args.min_imgs,
        exclude_ads=args.exclude_ads,
        seen_threads=seen,
        listing_pages=args.listing_pages,
    ))
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
    total_imgs = sum(len(r["image_urls"].split(",")) for r in rows)
    print(f"[OK] wrote {len(rows)} multi-image posts ({total_imgs} imgs total) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
