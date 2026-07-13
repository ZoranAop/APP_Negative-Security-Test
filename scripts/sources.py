#!/usr/bin/env python3
"""
sources.py — 图片源分类注册与统一抓取。

把不同图片站按**标签(类别)**归组, 例如类别「美女」下含:
    tuziyouwang.com  (EmpireCMS 栏目, 每篇详情页 1 张原图 /d/file/*)
    yituyu.com       (画廊, 每个画廊多张 /pic/<gid>/NN_* 原图)

配置见 sources/categories.json。发帖脚本 post_room_moments.py 用
`--category 美女` 即可从该类下**各站点轮流**抓「未用过」的新图(共享去重账本)。

要新增网站: 在 categories.json 里给对应类别加一个 source, 并在本文件
实现/复用一个 `iter_<type>` 抓取器即可。返回统一的图片记录:
    {"url": 原始图片URL, "id": 站内唯一标记(aid/gid+idx), "site": 站名}
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "sources" / "categories.json"


def load_categories(path: Path | None = None) -> dict:
    p = path or _CONFIG_PATH
    return json.loads(p.read_text(encoding="utf-8")).get("categories", {})


def _get(url: str, referer: str, timeout: int = 30) -> str:
    r = requests.get(url, headers={"User-Agent": UA, "Referer": referer,
                                   "Accept-Language": "zh-CN,zh;q=0.9"}, timeout=timeout)
    r.raise_for_status()
    return r.content.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# tuziyouwang.com — EmpireCMS 栏目; 每篇详情页取第一张 /d/file/* 原图
#   站内唯一标记 id = "tuzi:<column>:<aid>"
# ---------------------------------------------------------------------------
def _tuzi_list_ids(base: str, column: str, want: int, has_id) -> list[str]:
    ids, seen = [], set()
    page = 1
    while len(ids) < want and page <= 13:
        url = f"{base}/{column}/" if page == 1 else f"{base}/{column}/index_{page}.html"
        try:
            txt = _get(url, f"{base}/{column}/")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] tuzi list {url}: {e}")
            break
        for aid in re.findall(rf"/{column}/(\d+)\.html", txt):
            if aid in seen:
                continue
            seen.add(aid)
            if has_id(f"tuzi:{column}:{aid}"):
                continue
            ids.append(aid)
        page += 1
        time.sleep(0.25)
    return ids


def _tuzi_first_photo(base: str, column: str, aid: str) -> str | None:
    txt = _get(f"{base}/{column}/{aid}.html", f"{base}/{column}/")
    for u in re.findall(r'(?:src|data-original)="(/d/file/[^"]+\.(?:jpg|jpeg|png|webp))"', txt, re.I):
        return u if u.startswith("http") else base + u
    return None


def iter_tuzi(source: dict, need: int, has_id, has_url):
    """从 tuzi 的多个栏目轮流取 need 张未用过的图。"""
    base = source.get("base", "http://tuziyouwang.com")
    columns = source.get("columns") or ["meitui"]
    col_ids = {c: _tuzi_list_ids(base, c, need + 15, has_id) for c in columns}
    ptr = {c: 0 for c in columns}
    out = []
    while len(out) < need:
        progressed = False
        for c in columns:
            if len(out) >= need:
                break
            ids = col_ids[c]
            while ptr[c] < len(ids):
                aid = ids[ptr[c]]
                ptr[c] += 1
                progressed = True
                try:
                    u = _tuzi_first_photo(base, c, aid)
                except Exception as e:  # noqa: BLE001
                    print(f"[warn] tuzi {c}/{aid}: {e}")
                    continue
                if not u or has_url(u):
                    continue
                out.append({"url": u, "id": f"tuzi:{c}:{aid}", "site": "tuziyouwang"})
                break
        if not progressed:
            break
    return out


# ---------------------------------------------------------------------------
# yituyu.com — 画廊; 每个画廊多张 /pic/<gid>/NN_* 原图
#   站内唯一标记 id = "yituyu:<gid>:<basename>"
# ---------------------------------------------------------------------------
def _yituyu_seed_gids(base: str, seed_pages: list[str]) -> list[str]:
    gids, seen = [], set()
    for path in seed_pages:
        try:
            txt = _get(base + path, base + "/")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] yituyu seed {path}: {e}")
            continue
        for gid in re.findall(r"/gallery/(\d+)/", txt):
            if gid not in seen:
                seen.add(gid)
                gids.append(gid)
        time.sleep(0.2)
    return gids


def _yituyu_gallery_photos(base: str, img_host: str, gid: str) -> list[str]:
    txt = _get(f"{base}/gallery/{gid}/", base + "/")
    return sorted(set(re.findall(
        rf"(https?://{re.escape(img_host)}/pic/{gid}/\d+_[^\s\"\\]+\.(?:jpg|jpeg|png|webp))",
        txt, re.I)))


def iter_yituyu(source: dict, need: int, has_id, has_url):
    """从 yituyu 画廊取 need 张未用过的图(每画廊最多取几张再换下一个)。"""
    base = source.get("base", "https://www.yituyu.com")
    img_host = source.get("img_host", "img.yituyu.com")
    seed_pages = source.get("seed_pages") or ["/", "/gallery/", "/rank/"]
    per_gallery = int(source.get("imgs_per_gallery", 3))
    gids = _yituyu_seed_gids(base, seed_pages)
    out = []
    for gid in gids:
        if len(out) >= need:
            break
        try:
            pics = _yituyu_gallery_photos(base, img_host, gid)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] yituyu gallery {gid}: {e}")
            continue
        taken = 0
        for u in pics:
            if len(out) >= need or taken >= per_gallery:
                break
            uid = f"yituyu:{gid}:{u.rsplit('/', 1)[-1]}"
            if has_id(uid) or has_url(u):
                continue
            out.append({"url": u, "id": uid, "site": "yituyu"})
            taken += 1
        time.sleep(0.2)
    return out


# ---------------------------------------------------------------------------
# turismo.cc (爱尤物) — WordPress 图站; 一级栏目列文章, 二级详情页正文区高清图
#   一级: /<column>/ (如 /xiuren/ /cosplay/ /rosi/), 含文章链接 /<slug>.html
#   二级: /<slug>.html, 正文 <div id="post_content"> 内 <img> 为高清原图
#   站内唯一标记 id = "turismo:<slug>:<basename>"
# ---------------------------------------------------------------------------
def _turismo_list_slugs(base: str, column: str, want: int, has_id) -> list[str]:
    slugs, seenset = [], set()
    page = 1
    while len(slugs) < want and page <= 15:
        url = f"{base}/{column}/" if page == 1 else f"{base}/{column}/index_{page}.html"
        try:
            txt = _get(url, f"{base}/{column}/")
        except Exception as e:  # noqa: BLE001
            print(f"[warn] turismo list {url}: {e}")
            break
        found = re.findall(r'href="/([A-Za-z0-9]{5,8})\.html"', txt)
        new = [s for s in found if s not in seenset]
        for s in found:
            seenset.add(s)
        if not new:
            break
        slugs.extend(new)
        page += 1
        time.sleep(0.25)
    return list(dict.fromkeys(slugs))


def _turismo_content_photos(base: str, slug: str) -> list[str]:
    txt = _get(f"{base}/{slug}.html", f"{base}/")
    i = txt.find('id="post_content"')
    if i < 0:
        return []
    end = txt.find('class="related', i)
    if end < 0:
        end = txt.find('id="footer"', i)
    seg = txt[i: end if end > 0 else len(txt)]
    urls = re.findall(
        r'(?:data-original|src)="(//img\.youwushow\.top/[^"]+\.(?:jpg|jpeg|png|webp))"',
        seg, re.I)
    return ["https:" + u for u in urls if "/dy_img_" not in u]


def iter_turismo(source: dict, need: int, has_id, has_url):
    """从 turismo.cc 的多个栏目轮流进二级详情页, 取正文高清图。"""
    base = source.get("base", "https://www.turismo.cc")
    columns = source.get("columns") or ["xiuren"]
    per_post = int(source.get("imgs_per_post", 4))
    col_slugs = {c: _turismo_list_slugs(base, c, need + 10, has_id) for c in columns}
    ptr = {c: 0 for c in columns}
    out = []
    while len(out) < need:
        progressed = False
        for c in columns:
            if len(out) >= need:
                break
            slugs = col_slugs[c]
            while ptr[c] < len(slugs):
                slug = slugs[ptr[c]]
                ptr[c] += 1
                progressed = True
                try:
                    pics = _turismo_content_photos(base, slug)
                except Exception as e:  # noqa: BLE001
                    print(f"[warn] turismo {c}/{slug}: {e}")
                    continue
                if not pics:
                    continue
                taken = 0
                for u in pics:
                    if len(out) >= need or taken >= per_post:
                        break
                    uid = f"turismo:{slug}:{u.rsplit('/', 1)[-1]}"
                    if has_id(uid) or has_url(u):
                        continue
                    out.append({"url": u, "id": uid, "site": "turismo"})
                    taken += 1
                if taken > 0:
                    break  # 取到了新图, 轮到下个栏目
                # 这篇全部图片都已用过，继续尝试下一篇
        if not progressed:
            break
    return out


_ITER = {"tuzi": iter_tuzi, "yituyu": iter_yituyu, "turismo": iter_turismo}


def collect_category(category: str, need: int, has_id, has_url,
                     categories: dict | None = None) -> list[dict]:
    """从某类别下**各站点轮流**抓 need 张未用过的图。

    has_id(id)  -> bool : 该站内标记是否已用过(去重账本)
    has_url(url)-> bool : 该图片URL是否已用过
    返回 [{"url","id","site"}, ...]
    """
    cats = categories or load_categories()
    if category not in cats:
        raise KeyError(f"未知类别 '{category}', 可选: {list(cats)}")
    sources = cats[category].get("sources", [])
    if not sources:
        return []
    # 每站先各抓一批, 再全局轮流合并, 保证多站混合
    per = max(1, need // len(sources) + need)  # 抓足量, 后面按 need 截断
    pools = []
    for s in sources:
        fn = _ITER.get(s.get("type"))
        if not fn:
            print(f"[warn] 未实现的源类型: {s.get('type')}")
            pools.append([])
            continue
        try:
            pools.append(fn(s, per, has_id, has_url))
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 抓取 {s.get('site')} 失败: {e}")
            pools.append([])
    # round-robin 合并
    out, ptr = [], [0] * len(pools)
    while len(out) < need and any(ptr[i] < len(pools[i]) for i in range(len(pools))):
        for i in range(len(pools)):
            if len(out) >= need:
                break
            if ptr[i] < len(pools[i]):
                out.append(pools[i][ptr[i]])
                ptr[i] += 1
    return out
