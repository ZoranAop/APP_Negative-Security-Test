#!/usr/bin/env python3
"""
opennana_fetch.py — 从 OpenNana 提示词图库拉取素材，输出可直接喂给 post_moments.py 的 CSV。

API：
    GET https://api.opennana.com/api/prompts?media_type=image|video&page=N
    GET https://api.opennana.com/api/prompts/{slug}

输出 CSV 列：
    content,visibility,room_id,image_urls,location_name,location_address,location_lat,location_lon

注意：
    - 抓取必须带 Referer: https://opennana.com/ 和正常 User-Agent，否则 403。
    - 这里只做最朴素的「英文标题 + 标签拼接」作为 content；建议后续通过 LLM 改写为用户口吻。
      详见 docs/04-content-pipeline.md §4.2。
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from typing import Iterable

import requests

OPENNANA_API_BASE = os.getenv("OPENNANA_API_BASE", "https://api.opennana.com")
HEADERS = {
    "User-Agent": os.getenv(
        "OPENNANA_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ),
    "Referer": os.getenv("OPENNANA_REFERER", "https://opennana.com/"),
    "Accept": "application/json",
}


def list_prompts(media_type: str, page: int) -> list[dict]:
    url = f"{OPENNANA_API_BASE}/api/prompts"
    r = requests.get(url, params={"media_type": media_type, "page": page}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("data") or data.get("results") or data.get("items") or []


def get_detail(slug: str) -> dict:
    url = f"{OPENNANA_API_BASE}/api/prompts/{slug}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json().get("data") or r.json()


def build_caption(detail: dict) -> str:
    title = (detail.get("title") or "").strip()
    tags = [f"#{t}" for t in (detail.get("tags") or []) if isinstance(t, str)]
    parts = [p for p in [title, " ".join(tags)] if p]
    return " ".join(parts) or "今日分享"


def iter_rows(media_type: str, pages: Iterable[int], limit: int) -> Iterable[dict]:
    count = 0
    for page in pages:
        items = list_prompts(media_type, page)
        for item in items:
            if limit and count >= limit:
                return
            slug = item.get("slug") or item.get("id")
            if not slug:
                continue
            try:
                detail = get_detail(str(slug))
            except Exception as e:  # noqa: BLE001
                print(f"[warn] detail fail slug={slug}: {e}", file=sys.stderr)
                continue
            caption = build_caption(detail)
            if media_type == "image":
                images = detail.get("images") or []
                if not images:
                    continue
                yield {
                    "content": caption,
                    "visibility": 0,
                    "room_id": "",
                    "image_urls": ",".join(images[:9]),
                    "location_name": "",
                    "location_address": "",
                    "location_lat": "",
                    "location_lon": "",
                }
            else:  # video
                videos = detail.get("video_urls") or []
                images = detail.get("images") or []
                if not videos:
                    continue
                yield {
                    "content": caption,
                    "visibility": 0,
                    "room_id": "",
                    "image_urls": "",
                    "location_name": "",
                    "location_address": "",
                    "location_lat": "",
                    "location_lon": "",
                    "_video_url": videos[0],
                    "_cover_url": images[0] if images else "",
                }
            count += 1
            time.sleep(0.5)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch OpenNana prompts → CSV")
    ap.add_argument("--media-type", choices=("image", "video"), default="image")
    ap.add_argument("--page", type=int, default=1)
    ap.add_argument("--pages", type=int, default=1, help="共抓 N 页")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    pages = range(args.page, args.page + args.pages)
    rows = list(iter_rows(args.media_type, pages, args.limit))
    if not rows:
        print("[warn] no rows produced", file=sys.stderr)
        return 1

    base_fields = [
        "content", "visibility", "room_id", "image_urls",
        "location_name", "location_address", "location_lat", "location_lon",
    ]
    extra_fields = [k for k in rows[0] if k.startswith("_")]
    fields = base_fields + extra_fields

    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})

    print(f"[OK] wrote {len(rows)} rows → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
