#!/usr/bin/env python3
"""
fetch_tech.py — 统一「科技资讯」多源采集器：从多个科技媒体各取 N 条最新资讯，
统一打上 科技 标签，产出纯文本 moments CSV（image_urls 空 → media_info type=text）。

支持来源（--sources，逗号分隔；默认全部可稳定抓取的 8 源）：
  kr36       36氪              https://36kr.com/feed                       (RSS)
  tmtpost    钛媒体            https://www.tmtpost.com/rss.xml             (RSS)
  techorange TechOrange 科技報橘 https://buzzorange.com/techorange/feed    (RSS, 繁中)
  mittrchina MIT科技评论中文    https://apii.web.mittrchina.com/information/index (JSON)
  netease    网易科技          https://tech.163.com/.../tech_datalist.js   (JSONP)
  bbc        BBC中文·科技      https://www.bbc.com/zhongwen/topics/...     (HTML SSR, 繁中)
  nytimes    纽约时报中文·科技  https://m.cn.nytimes.com/technology/zh-hant/(HTML SSR, 繁中)
  readhub    Readhub           https://readhub.cn/daily                    (SSR JSON)

暂不可用（curl 抓不到，保留待 Playwright 补齐）：
  myzaker    ZAKER 频道13       长亭 WAF JS 验证
  wsj        华尔街日报中文·科技 401 付费墙
  stdaily    科技日报          首页标题 JS 渲染

用法：
  py -3 scripts/fetch_tech.py --sources kr36,tmtpost,techorange,mittrchina,netease,bbc,nytimes,readhub `
     --per-site 3 --dedupe-file state/seen_tech.json --output tech_raw.csv

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

ALL_SOURCES = ["kr36", "tmtpost", "techorange", "mittrchina",
               "netease", "bbc", "nytimes", "readhub"]

# 站点中文名（用于文案里标注来源）
SITE_CN = {
    "kr36": "36氪", "tmtpost": "钛媒体", "techorange": "科技报橘",
    "mittrchina": "麻省理工科技评论", "netease": "网易科技",
    "bbc": "BBC中文", "nytimes": "纽约时报中文网", "readhub": "Readhub",
}


def _u8():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:  # noqa: BLE001
        pass


def _get(url, **kw):
    kw.setdefault("timeout", 25)
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    headers.update(kw.pop("headers", {}))
    last = None
    for _ in range(4):
        try:
            r = requests.get(url, headers=headers, **kw)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def _clean(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _rss_items(url, site, n, *, headers=None):
    """通用 RSS/Atom 解析：返回 [{title, brief, site}]。"""
    r = _get(url, headers=headers or {})
    txt = r.content.decode("utf-8", errors="ignore")
    out = []
    for it in re.findall(r"<item>(.*?)</item>", txt, re.S) or \
            re.findall(r"<entry>(.*?)</entry>", txt, re.S):
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        dm = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S) \
            or re.search(r"<summary[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</summary>", it, re.S)
        title = _clean(tm.group(1)) if tm else ""
        if not title:
            continue
        out.append({"title": title, "brief": _clean(dm.group(1)) if dm else "", "site": site})
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------------------
# per-source fetchers → list[{"title","brief","site"}]
# ---------------------------------------------------------------------------
def fetch_kr36(n):
    return _rss_items("https://36kr.com/feed", "kr36", n)


def fetch_tmtpost(n):
    return _rss_items("https://www.tmtpost.com/rss.xml", "tmtpost", n)


def fetch_techorange(n):
    return _rss_items("https://buzzorange.com/techorange/feed", "techorange", n)


def fetch_mittrchina(n):
    r = _get("https://apii.web.mittrchina.com/information/index?page=1&limit=%d" % max(n * 3, 10),
             headers={"Referer": "https://www.mittrchina.com/"})
    j = r.json()
    data = j.get("data") or {}
    items = data.get("items") or data.get("list") or []
    out = []
    for it in items:
        title = _clean(it.get("name") or it.get("title") or "")
        if not title:
            continue
        out.append({"title": title, "brief": _clean(it.get("summary") or ""), "site": "mittrchina"})
        if len(out) >= n:
            break
    return out


def fetch_netease(n):
    r = _get("https://tech.163.com/special/00097UHL/tech_datalist.js")
    txt = r.content.decode("utf-8", errors="ignore")
    m = re.search(r"data_callback\((.*)\)\s*", txt.strip(), re.S)
    out = []
    if m:
        body = m.group(1)
        try:
            arr = json.loads(body)
        except Exception:  # noqa: BLE001
            arr = json.loads(body[:body.rfind("]") + 1]) if "]" in body else []
        for it in arr:
            title = _clean(it.get("title") or "")
            if not title:
                continue
            out.append({"title": title, "brief": _clean(it.get("digest") or ""), "site": "netease"})
            if len(out) >= n:
                break
    return out


def fetch_bbc(n):
    r = _get("https://www.bbc.com/zhongwen/topics/cd6qem06yq0t/trad")
    txt = r.text
    out, seen = [], set()
    # <h2 ...><a href="/zhongwen/articles/...">标题</a></h2>
    for href, title in re.findall(
            r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>', txt, re.S):
        if "/zhongwen/articles/" not in href:
            continue
        title = _clean(title)
        if title and title not in seen and not title.startswith("視頻"):
            seen.add(title)
            out.append({"title": title, "brief": "", "site": "bbc"})
        if len(out) >= n:
            break
    return out


def fetch_nytimes(n):
    r = _get("https://m.cn.nytimes.com/technology/zh-hant/")
    txt = r.text
    out, seen = [], set()
    for title in re.findall(r"<h2[^>]*>(.*?)</h2>", txt, re.S):
        title = _clean(title)
        if title and 6 <= len(title) <= 60 and title not in seen:
            seen.add(title)
            out.append({"title": title, "brief": "", "site": "nytimes"})
        if len(out) >= n:
            break
    return out


def fetch_readhub(n):
    # readhub 官方话题 JSON API（比 SSR HTML 稳定）
    r = _get("https://api.readhub.cn/topic/list?pageSize=%d" % max(n * 4, 20),
             headers={"Referer": "https://readhub.cn/"})
    out = []
    data = (r.json().get("data") or {})
    for it in data.get("items") or []:
        title = _clean(it.get("title") or "")
        if not title:
            continue
        out.append({"title": title, "brief": _clean(it.get("summary") or ""), "site": "readhub"})
        if len(out) >= n:
            break
    return out


FETCHERS = {
    "kr36": fetch_kr36, "tmtpost": fetch_tmtpost, "techorange": fetch_techorange,
    "mittrchina": fetch_mittrchina, "netease": fetch_netease,
    "bbc": fetch_bbc, "nytimes": fetch_nytimes, "readhub": fetch_readhub,
}


def _norm(t: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[^\w\u4e00-\u9fff]", "", (t or "").lower()))


def _toks(t):
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2}", (t or "").lower()))


def main() -> int:
    _u8()
    ap = argparse.ArgumentParser(description="Fetch tech news from multiple sites → text moments CSV")
    ap.add_argument("--sources", default=",".join(ALL_SOURCES),
                    help="comma keys: " + ",".join(ALL_SOURCES))
    ap.add_argument("--per-site", type=int, default=3)
    ap.add_argument("--tag", default="科技", help="标签，写入 _tag 列（默认 科技）")
    ap.add_argument("--dedupe-file", default=None,
                    help="JSON list of already-used normalized titles; skip & merge")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    used_norm, used_tok = set(), []
    if args.dedupe_file and Path(args.dedupe_file).exists():
        try:
            for t in json.loads(Path(args.dedupe_file).read_text(encoding="utf-8")):
                used_norm.add(t)
                used_tok.append(_toks(t))
        except Exception:  # noqa: BLE001
            pass
    print(f"[tech] 已用标题记录: {len(used_norm)}", file=sys.stderr)

    picked_tok, picked_norm = [], set()

    def seen_or_dup(title):
        n = _norm(title)
        if n in used_norm or n in picked_norm:
            return True
        tt = _toks(title)
        for ot in used_tok + picked_tok:
            if tt and len(tt & ot) / len(tt) >= 0.7:
                return True
        return False

    sources = [s.strip() for s in args.sources.split(",") if s.strip() in FETCHERS]
    rows = []
    for name in sources:
        try:
            items = FETCHERS[name](args.per_site * 4)  # 多取，去重后截断
        except Exception as e:  # noqa: BLE001
            print(f"[tech] {name} ERR: {e}", file=sys.stderr)
            continue
        kept = 0
        for it in items:
            if kept >= args.per_site:
                break
            if seen_or_dup(it["title"]):
                continue
            picked_norm.add(_norm(it["title"]))
            picked_tok.append(_toks(it["title"]))
            rows.append(it)
            kept += 1
        print(f"[tech] {name}: {kept}/{args.per_site} items", file=sys.stderr)

    if not rows:
        print("[warn] no items", file=sys.stderr)
        return 1

    if args.dedupe_file:
        merged = sorted(used_norm | {_norm(it["title"]) for it in rows})
        Path(args.dedupe_file).parent.mkdir(parents=True, exist_ok=True)
        Path(args.dedupe_file).write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                                          encoding="utf-8")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_tag", "_brief"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for it in rows:
            w.writerow({"content": it["title"], "visibility": 0, "room_id": "", "image_urls": "",
                        "location_name": "", "location_address": "", "location_lat": "",
                        "location_lon": "", "_source": "technews", "_site": it["site"],
                        "_tag": args.tag, "_brief": it["brief"]})
    print(f"[OK] wrote {len(rows)} tech news ({len(sources)} sites) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
