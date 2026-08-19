#!/usr/bin/env python3
"""
fetch_web3_img.py — Web3/Crypto 图文采集器（CoinDesk / CoinTelegraph RSS，带封面图）

与 fetch_web3.py（纯文本）不同，本脚本从全球 Crypto 媒体 RSS 提取
「标题 + 摘要 + 封面图」，产出带 ``image_urls`` 的 moments CSV（图文帖），
模拟 Binance App timeline 的资讯卡片样式（每条资讯配一张封面图，图文天然匹配）。

来源（公开 RSS，无需登录）：
  coindesk       CoinDesk        https://www.coindesk.com/arc/outboundfeeds/rss/  (media:content)
  cointelegraph  CoinTelegraph   https://cointelegraph.com/rss                    (enclosure)

用法：
  py -3 scripts/fetch_web3_img.py --sources coindesk,cointelegraph --per-site 5 `
      --dedupe-file state/seen_web3_img.json --output web3_img_raw.csv

去重：--dedupe-file 记录已用消息（归一化标题），跨批次自动跳过、不重复发。
所有来源均公开、无需登录；请勿在仓库或 .env 写入任何账号密码。
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

SOURCES = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
}


def _u8():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


def _clean(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _norm(t: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[^\w\u4e00-\u9fff]", "", (t or "").lower()))


def _get(url: str) -> requests.Response:
    last = None
    for _ in range(4):
        try:
            r = requests.get(url, timeout=25, headers={"User-Agent": UA})
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def _rss_items(url: str, n: int) -> list[dict]:
    """通用 RSS 解析，提取 title/brief/image（media:content 或 enclosure）。"""
    txt = _get(url).content.decode("utf-8", errors="ignore")
    out: list[dict] = []
    for it in re.findall(r"<item>(.*?)</item>", txt, re.S):
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        d = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
        m = re.search(r'<media:content[^>]*url="([^"]+)"', it)
        e = re.search(r'<enclosure[^>]*url="([^"]+)"', it)
        title = _clean(t.group(1)) if t else ""
        brief = _clean(d.group(1)) if d else ""
        img = (m.group(1) if m else (e.group(1) if e else ""))
        if title and img:
            out.append({"title": title, "brief": brief, "image_urls": img})
            if len(out) >= n:
                break
    return out


def _load_dedupe(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        return {str(x) for x in json.loads(p.read_text(encoding="utf-8"))}
    except Exception:
        return set()


def _save_dedupe(path: str | None, norms: set[str]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(norms), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    _u8()
    ap = argparse.ArgumentParser(description="Web3/Crypto 图文采集（CoinDesk/CoinTelegraph RSS + 封面图）")
    ap.add_argument("--sources", default="coindesk,cointelegraph",
                    help="逗号分隔来源 key：" + ",".join(SOURCES))
    ap.add_argument("--per-site", type=int, default=5, help="每个来源取多少条")
    ap.add_argument("--dedupe-file", default=None, help="去重档（记录归一化标题）")
    ap.add_argument("--img-url-dedupe-file", default=None,
                    help="图片 URL 去重档（记录已用封面图 URL，避免重复图片）")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    used = _load_dedupe(args.dedupe_file)
    used_img_urls = _load_dedupe(args.img_url_dedupe_file)
    sources = [s.strip() for s in args.sources.split(",") if s.strip() in SOURCES]

    rows: list[dict] = []
    picked: set[str] = set()
    picked_img_urls: set[str] = set()
    for site in sources:
        try:
            items = _rss_items(SOURCES[site], args.per_site * 2)
        except Exception as e:  # noqa: BLE001
            print(f"[web3_img] {site} ERR: {e}", file=sys.stderr)
            continue
        kept = 0
        for it in items:
            if kept >= args.per_site:
                break
            n = _norm(it["title"])
            if n in used or n in picked:
                continue
            img_url = (it["image_urls"] or "").strip()
            if img_url and (img_url in used_img_urls or img_url in picked_img_urls):
                print(f"[web3_img] {site} skip dup-image: {img_url[:60]}", file=sys.stderr)
                continue
            picked.add(n)
            picked_img_urls.add(img_url)
            rows.append({"title": it["title"], "brief": it["brief"],
                         "image_urls": it["image_urls"], "site": site})
            kept += 1
        print(f"[web3_img] {site}: {kept}/{args.per_site} items", file=sys.stderr)

    if not rows:
        print("[web3_img] no items", file=sys.stderr)
        return 1

    if args.dedupe_file:
        _save_dedupe(args.dedupe_file, used | picked)
    if args.img_url_dedupe_file:
        _save_dedupe(args.img_url_dedupe_file, used_img_urls | picked_img_urls)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_brief"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for it in rows:
            w.writerow({"content": it["title"], "visibility": 0, "room_id": "",
                        "image_urls": it["image_urls"],
                        "location_name": "", "location_address": "",
                        "location_lat": "", "location_lon": "",
                        "_source": "web3img", "_site": it["site"], "_brief": it["brief"]})
    print(f"[OK] wrote {len(rows)} web3 image posts ({len(sources)} sites) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
