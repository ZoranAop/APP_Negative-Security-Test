#!/usr/bin/env python3
"""
crawl_xhs_multiimg.py — 小红书多图 CDN 直链采集脚本

从 explore 推荐流获取笔记列表，逐一请求详情页提取完整 imageList
（所有图片 CDN 直链），输出与 publish_from_tokens.py 兼容的 moments CSV。

特点：
  - 多图采集：从详情页的 imageList 提取全部图片（非仅封面）
  - CDN 直链：不下载到本地，直接输出 xhscdn CDN URL
  - 广告过滤：按标题关键词过滤广告/带货/种草等条目
  - 仅图文：跳过视频笔记
  - 正文清洗：自动清理话题标签、表情、@提及格式
  - 无需登录：基于 explore 公开页面 + 详情页免登录

用法：
    py -3 scripts/crawl_xhs_multiimg.py --target 25 --delay 1.5 --output moments_multi.csv

产出 CSV 的 image_urls 字段为逗号分隔的多张 CDN 直链，可直接被
publish_from_tokens.py 消费（自动执行 Referer 映射 / 水印裁切 / 多图质量管线）。

参见：docs/16-xiaohongshu-square.md §16.3C 与 §16.7
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import urllib.request

# Windows GBK console fix
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_XHS_EXPLORE_URL = "https://www.xiaohongshu.com/explore"
_XHS_NOTE_URL = "https://www.xiaohongshu.com/explore/{note_id}"

_HEADERS = {
    "User-Agent": os.getenv(
        "XHS_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.xiaohongshu.com/",
}

# Ad-marker words (same as crawl_xhs.py)
_AD_KEYWORDS = [
    "广告", "推广", "优惠", "折扣", "促销", "招商", "加盟", "代理", "vip", "付费",
    "扫码", "关注公众", "私信", "商务合作", "微信", "qq群", "下载app", "破解", "福利群",
    "团购", "拼单", "带货", "种草", "下单", "coupon", "discount", "promo",
    "sponsor", "advertisement",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _looks_like_ad(title: str) -> bool:
    low = (title or "").lower()
    return any(k.lower() in low for k in _AD_KEYWORDS)


def _extract_initial_state(html: str):
    """Extract window.__INITIAL_STATE__ JSON from HTML."""
    start_str = "window.__INITIAL_STATE__="
    start_idx = html.find(start_str)
    if start_idx == -1:
        return None
    json_start = start_idx + len(start_str)
    brace_count = 0
    json_end = json_start
    for i in range(json_start, len(html)):
        c = html[i]
        if c == "{":
            brace_count += 1
        elif c == "}":
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break
    raw = html[json_start:json_end]
    raw = raw.replace(":undefined", ":null").replace(": undefined", ": null")
    return json.loads(raw)


def _clean_content(title: str, desc: str) -> str:
    """Clean XHS content: merge title+desc, strip tags/emoji/@mentions."""
    content = title
    if desc:
        content = f"{title}\n{desc}" if title else desc
    # 话题标签: #话题[话题]# → #话题
    content = re.sub(r'#([^#\[]+)\[话题\]#', r'#\1', content)
    # 小红书表情: [xxxR]
    content = re.sub(r'\[[^\]]+R\]', '', content)
    # @提及
    content = re.sub(r'@[\w\u4e00-\u9fff]+', '', content)
    # 多余空白
    content = re.sub(r' +', ' ', content)
    content = re.sub(r'\n+', '\n', content)
    return content.strip()


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_explore_briefs(timeout: int = 15) -> list[dict]:
    """Fetch note briefs from XHS explore page (no login required)."""
    req = urllib.request.Request(_XHS_EXPLORE_URL, headers=_HEADERS)
    resp = urllib.request.urlopen(req, timeout=timeout)
    html = resp.read().decode("utf-8")
    state = _extract_initial_state(html)
    if not state:
        return []

    feeds = state.get("feed", {}).get("feeds", [])
    results = []
    for feed in feeds:
        note_id = feed.get("id", "")
        xsec_token = feed.get("xsecToken", "")
        nc = feed.get("noteCard", {})
        note_type = nc.get("type", "").lower()
        title = nc.get("displayTitle", "").strip()

        if note_type == "video":
            continue
        if not note_id:
            continue

        results.append({
            "note_id": note_id,
            "xsec_token": xsec_token,
            "title": title,
        })
    return results


def fetch_note_detail(note_id: str, xsec_token: str, timeout: int = 15) -> dict | None:
    """Fetch note detail page and extract full content + all image URLs.

    Returns dict with keys: content, image_urls (list), image_count.
    Returns None if note is unavailable or has no images."""
    url = _XHS_NOTE_URL.format(note_id=note_id)
    if xsec_token:
        url += f"?xsec_token={xsec_token}&xsec_source=pc_feed"

    req = urllib.request.Request(url, headers=_HEADERS)
    resp = urllib.request.urlopen(req, timeout=timeout)
    html = resp.read().decode("utf-8")
    state = _extract_initial_state(html)
    if not state:
        return None

    note_detail = (
        state.get("note", {})
        .get("noteDetailMap", {})
        .get(note_id, {})
        .get("note", {})
    )
    if not note_detail:
        return None

    # Skip video notes
    if note_detail.get("type", "").lower() == "video":
        return None

    # Extract title + description
    title = note_detail.get("title", "").strip()
    desc = note_detail.get("desc", "").strip()
    content = _clean_content(title, desc)

    # Extract ALL image URLs from imageList
    images = note_detail.get("imageList", [])
    img_urls = []
    for img in images:
        url_str = img.get("urlDefault") or img.get("urlPre") or img.get("url", "")
        if url_str:
            url_str = url_str.strip()
            if not url_str.startswith("http"):
                url_str = "https:" + url_str if url_str.startswith("//") else ""
            if url_str:
                img_urls.append(url_str)

    if not content and not img_urls:
        return None

    return {
        "content": content or "小红书分享",
        "image_urls": img_urls,
        "image_count": len(img_urls),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    ap = argparse.ArgumentParser(
        description="小红书多图 CDN 直链采集（explore 推荐流 + 详情页 imageList）",
    )
    ap.add_argument(
        "--target", type=int, default=25,
        help="目标采集的图文笔记数量 (默认: 25)",
    )
    ap.add_argument(
        "--max-explore-requests", type=int, default=8,
        help="explore 列表页最大请求次数 (默认: 8)",
    )
    ap.add_argument(
        "--delay", type=float, default=1.5,
        help="详情页请求间隔秒数，防频控 (默认: 1.5)",
    )
    ap.add_argument(
        "--timeout", type=int, default=15,
        help="HTTP 请求超时秒数 (默认: 15)",
    )
    ap.add_argument(
        "--exclude-ads", action="store_true", default=True,
        help="过滤广告/带货/种草帖 (默认: 开启)",
    )
    ap.add_argument(
        "--include-ads", dest="exclude_ads", action="store_false",
        help="关闭广告过滤",
    )
    ap.add_argument(
        "--output", "-o", type=str, default="moments_xhs_multi.csv",
        help="输出 CSV 文件路径 (默认: moments_xhs_multi.csv)",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    print("[INFO] 小红书多图 CDN 直链采集启动")
    print(f"[INFO] 目标: {args.target} 条 | 间隔: {args.delay}s | 输出: {args.output}")
    print()

    # Phase 1: Collect note briefs from explore page
    all_briefs: list[dict] = []
    seen_ids: set[str] = set()

    print("=== Phase 1: 获取 explore 推荐流笔记列表 ===")
    for attempt in range(1, args.max_explore_requests + 1):
        print(f"[{attempt}/{args.max_explore_requests}] 请求 explore...", end=" ")
        try:
            items = fetch_explore_briefs(timeout=args.timeout)
            # Filter ads at brief level
            if args.exclude_ads:
                items = [it for it in items if not _looks_like_ad(it["title"])]
            new_count = 0
            for item in items:
                if item["note_id"] not in seen_ids:
                    seen_ids.add(item["note_id"])
                    all_briefs.append(item)
                    new_count += 1
            print(f"{len(items)} 条, 新增 {new_count}, 累计 {len(all_briefs)}")
        except Exception as e:
            print(f"失败: {e}")

        # Get 2x target for buffer (some details may fail)
        if len(all_briefs) >= args.target * 2:
            break
        time.sleep(2)

    print(f"\n[INFO] 列表完成: {len(all_briefs)} 条候选")

    # Phase 2: Fetch detail pages for full imageList
    print("\n=== Phase 2: 逐一请求详情页提取全部图片 ===")
    collected: list[dict] = []
    for i, brief in enumerate(all_briefs):
        if len(collected) >= args.target:
            break

        note_id = brief["note_id"]
        xsec_token = brief["xsec_token"]
        print(f"[{i+1}/{len(all_briefs)}] {note_id}...", end=" ")

        try:
            detail = fetch_note_detail(note_id, xsec_token, timeout=args.timeout)
            if detail and detail["image_urls"]:
                collected.append(detail)
                print(f"OK {detail['image_count']}图 | {detail['content'][:30]}")
            else:
                print("跳过")
        except Exception as e:
            print(f"失败: {e}")

        time.sleep(args.delay)

    # Stats
    if not collected:
        print("\n[ERROR] 没有采集到有效数据")
        return 1

    multi_count = sum(1 for r in collected if r["image_count"] > 1)
    total_images = sum(r["image_count"] for r in collected)
    print(f"\n[RESULT] 采集 {len(collected)} 条素材")
    print(f"  多图: {multi_count} 条 | 单图: {len(collected) - multi_count} 条")
    print(f"  总图: {total_images} 张 | 平均: {total_images / len(collected):.1f} 张/帖")

    # Phase 3: Write CSV
    out_path = args.output
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    fields = [
        "content", "visibility", "room_id", "image_urls",
        "video_url", "thumbnail_url",
        "location_name", "location_address", "location_lat", "location_lon",
    ]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in collected:
            w.writerow({
                "content": r["content"],
                "visibility": 0,
                "room_id": "",
                "image_urls": ",".join(r["image_urls"]),
                "video_url": "",
                "thumbnail_url": "",
                "location_name": "",
                "location_address": "",
                "location_lat": "",
                "location_lon": "",
            })

    print(f"\n[SUCCESS] 写入 {len(collected)} 条 → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
