#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_beauty_category.py — 美女图片多源统一采集（turismo六栏目 + opennana + tuzi + yituyu + aituitu 轮询）

从 sources/categories.json 中「美女」类下的所有站点轮流采集图片，
同时混合 opennana beauty 主题素材，避免图片来源单一。

输出 CSV 格式与 multi_source_fetch.py 兼容，可直接供 assemble_mixed.py 消费：
    content,visibility,room_id,image_urls,location_name,location_address,
    location_lat,location_lon,_source,_slug

多源轮询策略：
    1) turismo.cc: xiuren/cosplay/rosi/youmi/mygirl/tuigirl 六栏目轮流
    2) opennana: beauty 主题真人图片
    3) tuzi/yituyu/aituitu: 各站轮流补充
    去重：--dedupe-file 跨批次记录已用 ID/URL，自动跳过

用法：
    py -3 scripts/fetch_beauty_category.py --limit 40 --dedupe-file state/seen_beauty.json --output beauty_raw.csv
    py -3 scripts/fetch_beauty_category.py --limit 60 --include-opennana --output beauty_mix.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from pathlib import Path

import requests

# Ensure UTF-8 stdout on Windows
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from sources import collect_category, load_categories  # noqa: E402

OPENNANA_API_BASE = os.getenv("OPENNANA_API_BASE", "https://api.opennana.com")
OPENNANA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://opennana.com/",
    "Accept": "application/json",
}


def _fetch_opennana_beauty(want: int, seen_urls: set) -> list[dict]:
    """从 opennana 的 beauty 主题拉取图片素材。"""
    out = []
    page = 1
    while len(out) < want and page <= 20:
        try:
            r = requests.get(
                f"{OPENNANA_API_BASE}/api/prompts",
                params={"page": page, "size": 20, "mediaType": "image"},
                headers=OPENNANA_HEADERS, timeout=20)
            r.raise_for_status()
            items = r.json().get("data", {}).get("list", [])
        except Exception as e:
            print(f"[warn] opennana page {page}: {e}")
            break
        if not items:
            break
        for it in items:
            if len(out) >= want:
                break
            img = (it.get("imageUrl") or it.get("coverUrl") or "").strip()
            if not img or img in seen_urls:
                continue
            # 简单 beauty 过滤
            title = (it.get("title") or "").lower()
            prompt = (it.get("prompt") or "").lower()
            combined = title + " " + prompt
            beauty_kw = ["woman", "girl", "beauty", "model", "portrait", "fashion",
                         "美女", "少女", "女生", "写真", "模特", "性感", "甜美"]
            if not any(k in combined for k in beauty_kw):
                page += 1
                continue
            seen_urls.add(img)
            content = (it.get("title") or "").strip()
            tags = " ".join(f"#{t}" for t in (it.get("tags") or [])[:3])
            if tags:
                content = f"{content} {tags}" if content else tags
            slug = it.get("id") or img.split("/")[-1].split("?")[0]
            out.append({
                "content": content,
                "image_urls": img,
                "_source": "opennana",
                "_slug": f"opennana:{slug}",
            })
        page += 1
        time.sleep(0.3)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="美女图片多源统一采集（turismo六栏目+opennana+tuzi+yituyu+aituitu轮询）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--limit", type=int, default=40, help="总共需要的图片数量")
    ap.add_argument("--opennana-ratio", type=float, default=0.4,
                    help="opennana 占比（0-1之间），其余从 category 站点轮询")
    ap.add_argument("--include-opennana", action="store_true", default=True,
                    help="是否包含 opennana（默认包含）")
    ap.add_argument("--no-opennana", action="store_true",
                    help="不使用 opennana，仅从 turismo/tuzi/yituyu/aituitu 采集")
    ap.add_argument("--dedupe-file", default="state/seen_beauty.json",
                    help="去重档路径（跨批次防重复）")
    ap.add_argument("--output", required=True, help="输出 CSV 路径")
    args = ap.parse_args()

    # 加载去重档
    dedupe_path = ROOT / args.dedupe_file
    dedupe_path.parent.mkdir(parents=True, exist_ok=True)
    seen_ids: set = set()
    seen_urls: set = set()
    if dedupe_path.exists():
        data = json.loads(dedupe_path.read_text(encoding="utf-8"))
        seen_ids = set(data.get("ids", []))
        seen_urls = set(data.get("urls", []))
    print(f"[beauty] 去重档: {dedupe_path.name} (ids={len(seen_ids)}, urls={len(seen_urls)})")

    use_opennana = not args.no_opennana
    total = args.limit

    # 分配采集数量
    if use_opennana:
        opennana_want = int(total * args.opennana_ratio)
        category_want = total - opennana_want
    else:
        opennana_want = 0
        category_want = total

    all_rows = []

    # Step 1: 从 categories.json「美女」类采集（turismo/tuzi/yituyu/aituitu 轮询）
    if category_want > 0:
        print(f"[beauty] 从「美女」类站点轮询采集 {category_want} 张...")
        try:
            cat_items = collect_category(
                "美女", category_want,
                has_id=lambda x: x in seen_ids,
                has_url=lambda x: x in seen_urls,
            )
            for item in cat_items:
                url = item["url"]
                uid = item["id"]
                site = item.get("site", "unknown")
                seen_ids.add(uid)
                seen_urls.add(url)
                all_rows.append({
                    "content": f"{site} beauty photo",
                    "image_urls": url,
                    "_source": site,
                    "_slug": uid,
                })
            print(f"[beauty] 类别站点获取: {len(cat_items)} 张")
        except Exception as e:
            print(f"[warn] 类别采集失败: {e}")

    # Step 2: 从 opennana 采集
    if use_opennana and opennana_want > 0:
        print(f"[beauty] 从 opennana beauty 采集 {opennana_want} 张...")
        opennana_items = _fetch_opennana_beauty(opennana_want, seen_urls)
        for item in opennana_items:
            seen_ids.add(item["_slug"])
        all_rows.extend(opennana_items)
        print(f"[beauty] opennana 获取: {len(opennana_items)} 张")

    if not all_rows:
        print("[ERROR] 未采集到任何图片")
        return 1

    # 打乱顺序（多源混合）
    import random
    random.shuffle(all_rows)

    # 写出 CSV
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_slug"]
    out_path = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in all_rows:
            w.writerow({
                "content": r.get("content", ""),
                "visibility": "0",
                "room_id": "",
                "image_urls": r.get("image_urls", ""),
                "location_name": "", "location_address": "",
                "location_lat": "", "location_lon": "",
                "_source": r.get("_source", ""),
                "_slug": r.get("_slug", ""),
            })

    # 保存去重档
    dedupe_data = {"ids": list(seen_ids), "urls": list(seen_urls)}
    dedupe_path.write_text(json.dumps(dedupe_data, ensure_ascii=False), encoding="utf-8")

    # 统计
    from collections import Counter
    dist = Counter(r.get("_source", "?") for r in all_rows)
    print(f"[OK] wrote {len(all_rows)} photos → {out_path}")
    print(f"[OK] source distribution: {dict(dist)}")
    print(f"[OK] dedupe file → {dedupe_path.name} (ids={len(seen_ids)}, urls={len(seen_urls)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
