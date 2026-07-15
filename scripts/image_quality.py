#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
image_quality.py — 高质量图片提取模块

提供两级图片获取策略：
  1级：从RSS/列表页获取（快速但可能是缩略图）
  2级：进入文章详情页（二级/三级页面）获取高清图片

详情页图片提取优先级：
  1. og:image meta标签（Open Graph，通常1200x630+）
  2. twitter:image meta标签
  3. article正文中第一张大图（排除广告/logo）
  4. schema.org中的image

URL质量升级：
  - WordPress: 去掉-WxH尺寸后缀获取原图
  - CDN: 调整宽度参数到1200
  - 过滤低质量图（logo/icon/tracking pixel等）
"""
from __future__ import annotations

import re
import time
from typing import Optional

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# 低质量图片过滤模式
_LOW_QUALITY_PATTERNS = re.compile(
    r"logo|icon|favicon|avatar|pixel|1x1|spacer|blank|placeholder|tracking|"
    r"beacon|/ads/|/ad-|doubleclick|googlesyndication|badge|button|widget|"
    r"emoji|smiley|spinner|loading|arrow|chevron", re.I
)

# 最小文件名长度（排除追踪像素）
_MIN_FILENAME_LEN = 8


def upgrade_image_url(url: str) -> str:
    """将图片URL升级到最高质量版本。"""
    if not url:
        return url

    # WordPress 尺寸后缀：-300x200.jpg → .jpg
    url = re.sub(r"-\d{2,4}x\d{2,4}\.(jpg|jpeg|png|webp)", r".\1", url)

    # Conde Nast / Vox Media: w=XXX 参数升级到1200
    if re.search(r"[?&]w=\d+", url):
        url = re.sub(r"([?&])w=\d+", r"\1w=1200", url)

    # 通用 CDN resize/crop 参数清理
    url = re.sub(r"/resize/\d+x\d+/?", "/", url)
    url = re.sub(r"/crop/\d+x\d+/?", "/", url)

    # Cloudinary
    url = re.sub(r"/c_fill,w_\d+,h_\d+", "/c_fill,w_1200", url)
    url = re.sub(r"/c_fill,w_\d+", "/c_fill,w_1200", url)

    # imgix
    if "imgix" in url:
        url = re.sub(r"([?&])w=\d+", r"\1w=1200", url)
        url = re.sub(r"&h=\d+", "", url)

    # Squarespace: ?format=WxH → ?format=original
    url = re.sub(r"\?format=\d+w", "?format=original", url)

    return url


def is_high_quality(url: str) -> bool:
    """判断图片URL是否为高质量（排除低质量图片）。"""
    if not url:
        return False
    if _LOW_QUALITY_PATTERNS.search(url):
        return False
    filename = url.split("/")[-1].split("?")[0]
    if len(filename) < _MIN_FILENAME_LEN:
        return False
    if url.lower().endswith(".svg") or url.lower().endswith(".gif"):
        return False
    return True


def fetch_detail_page_image(article_url: str, timeout: int = 15) -> Optional[str]:
    """进入文章详情页（二级/三级页面），提取最高质量图片。

    优先级：og:image > twitter:image > 正文第一张大图

    Args:
        article_url: 文章详情页URL
        timeout: 请求超时秒数

    Returns:
        高质量图片URL，或None
    """
    try:
        r = requests.get(
            article_url,
            headers={"User-Agent": UA},
            timeout=timeout,
            allow_redirects=True,
        )
        if r.status_code != 200:
            return None
        html = r.text[:100000]  # 只看前100KB，避免过大页面
    except Exception:
        return None

    # 1. og:image（最可靠的高清图来源）
    og = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html)
    if not og:
        og = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', html)
    if og:
        img = og.group(1).strip()
        if is_high_quality(img):
            return upgrade_image_url(img)

    # 2. twitter:image
    tw = re.search(r'<meta[^>]*name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']', html)
    if not tw:
        tw = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']twitter:image["\']', html)
    if tw:
        img = tw.group(1).strip()
        if is_high_quality(img):
            return upgrade_image_url(img)

    # 3. 正文大图：在 article/main/content 区域找第一张合格图片
    # 先尝试定位正文区域
    content_area = html
    for tag in ["<article", "<main", 'class="content"', 'class="post-content"', 'class="entry-content"']:
        idx = html.find(tag)
        if idx > 0:
            content_area = html[idx:]
            break

    # 从正文区域提取所有图片
    imgs = re.findall(
        r'<img[^>]*(?:src|data-src)=["\']([^"\']+\.(?:jpg|jpeg|png|webp))["\']',
        content_area[:50000]
    )
    for img in imgs:
        if is_high_quality(img):
            return upgrade_image_url(img)

    return None


def extract_article_links_from_rss(rss_xml: str, max_items: int = 20) -> list[str]:
    """从RSS XML中提取文章链接列表。"""
    links = []
    items = re.findall(r"<item>(.*?)</item>", rss_xml, re.DOTALL)
    if not items:
        items = re.findall(r"<entry>(.*?)</entry>", rss_xml, re.DOTALL)

    for item in items[:max_items]:
        # RSS link
        link_m = re.search(r"<link>([^<]+)</link>", item)
        if link_m:
            links.append(link_m.group(1).strip())
            continue
        # Atom link
        link_m = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', item)
        if link_m:
            links.append(link_m.group(1).strip())
    return links


def fetch_rss_with_detail_images(
    rss_url: str,
    want: int,
    seen: set,
    delay: float = 0.5,
) -> list[dict]:
    """从RSS获取文章列表，然后逐篇进入详情页获取高清图片。

    完整流程：RSS → 文章链接 → 进入详情页 → og:image/正文大图

    Args:
        rss_url: RSS feed URL
        want: 需要的条数
        seen: 已用标题集合（去重）
        delay: 每次请求间隔秒数

    Returns:
        [{"title": ..., "image": ..., "link": ...}, ...]
    """
    try:
        r = requests.get(rss_url, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
        rss_xml = r.text
    except Exception as e:
        print(f"[warn] RSS fetch failed: {e}")
        return []

    items = re.findall(r"<item>(.*?)</item>", rss_xml, re.DOTALL)
    if not items:
        items = re.findall(r"<entry>(.*?)</entry>", rss_xml, re.DOTALL)

    out = []
    for item in items:
        if len(out) >= want:
            break

        # 提取标题
        title_m = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item) or \
                  re.search(r"<title[^>]*>(.*?)</title>", item)
        if not title_m:
            continue
        title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
        if not title:
            continue
        norm = re.sub(r"\s+", " ", title.lower().strip())
        if norm in seen:
            continue

        # 提取文章链接
        link_m = re.search(r"<link>([^<]+)</link>", item) or \
                 re.search(r'<link[^>]*href=["\']([^"\']+)["\']', item)
        if not link_m:
            continue
        article_url = link_m.group(1).strip()

        # 先尝试RSS中的图片
        rss_img = _extract_rss_inline_image(item)

        # 进入详情页获取高清图（二级页面）
        detail_img = fetch_detail_page_image(article_url)
        time.sleep(delay)

        # 选择最佳图片：详情页 > RSS内联
        img = detail_img or rss_img
        if not img:
            continue

        img = upgrade_image_url(img)
        if not is_high_quality(img):
            continue

        seen.add(norm)
        out.append({"title": title, "image": img, "link": article_url})

    return out


def _extract_rss_inline_image(item_xml: str) -> Optional[str]:
    """从RSS item内联提取图片（作为fallback）。"""
    patterns = [
        r'<media:content[^>]*url="([^"]+)"',
        r'<media:thumbnail[^>]*url="([^"]+)"',
        r'<enclosure[^>]*url="([^"]+\.(?:jpg|jpeg|png|webp))"',
    ]
    for pat in patterns:
        m = re.search(pat, item_xml)
        if m and is_high_quality(m.group(1)):
            return m.group(1)

    for tag in ["description", "content:encoded", "content"]:
        block = re.search(
            rf"<{tag}><!\[CDATA\[(.*?)\]\]></{tag}>", item_xml, re.DOTALL
        ) or re.search(rf"<{tag}>(.*?)</{tag}>", item_xml, re.DOTALL)
        if block:
            img = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))', block.group(1))
            if img and is_high_quality(img.group(1)):
                return img.group(1)
    return None
