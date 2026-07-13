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

# 站点内容语言（文案语言跟随网站语言；中文站统一按繁体中文 zh_hant 发布）
# 支持：zh_hant / en / ja / ms / hi / bn
SITE_LANG = {
    "kr36": "zh_hant", "tmtpost": "zh_hant", "techorange": "zh_hant",
    "mittrchina": "zh_hant", "netease": "zh_hant", "bbc": "zh_hant",
    "nytimes": "zh_hant", "readhub": "zh_hant",
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
    # 麻省理工科技评论：官方 information API，支持大 limit + 分页
    out = []
    for page in range(1, 6):
        try:
            r = _get("https://apii.web.mittrchina.com/information/index?page=%d&limit=%d"
                     % (page, min(max(n, 60), 200)),
                     headers={"Referer": "https://www.mittrchina.com/"})
        except Exception:  # noqa: BLE001
            break
        data = r.json().get("data") or {}
        items = data.get("items") or data.get("list") or []
        if not items:
            break
        for it in items:
            title = _clean(it.get("name") or it.get("title") or "")
            if not title:
                continue
            out.append({"title": title, "brief": _clean(it.get("summary") or ""), "site": "mittrchina"})
            if len(out) >= n:
                return out
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


# ---------------------------------------------------------------------------
# 扩充源（公开 RSS，无需登录）——中/英/日多语覆盖，扩大新鲜内容池
# ---------------------------------------------------------------------------
def fetch_kr36flash(n):
    return _rss_items("https://36kr.com/feed-newsflash", "kr36flash", n)


def fetch_ithome(n):
    return _rss_items("https://www.ithome.com/rss/", "ithome", n)


def fetch_sspai(n):
    return _rss_items("https://sspai.com/feed", "sspai", n)


def fetch_cnbeta(n):
    return _rss_items("https://www.cnbeta.com.tw/backend.php", "cnbeta", n)


def fetch_engadget(n):
    return _rss_items("https://www.engadget.com/rss.xml", "engadget", n)


def fetch_arstechnica(n):
    return _rss_items("https://feeds.arstechnica.com/arstechnica/index", "arstechnica", n)


def fetch_techcrunch(n):
    return _rss_items("https://techcrunch.com/feed/", "techcrunch", n)


def fetch_gizmodojp(n):
    return _rss_items("https://www.gizmodo.jp/index.xml", "gizmodojp", n)


def fetch_itmedia(n):
    return _rss_items("https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", "itmedia", n)


FETCHERS.update({
    "kr36flash": fetch_kr36flash, "ithome": fetch_ithome, "sspai": fetch_sspai,
    "cnbeta": fetch_cnbeta, "engadget": fetch_engadget, "arstechnica": fetch_arstechnica,
    "techcrunch": fetch_techcrunch, "gizmodojp": fetch_gizmodojp, "itmedia": fetch_itmedia,
})
ALL_SOURCES = ALL_SOURCES + ["kr36flash", "ithome", "sspai", "cnbeta",
                             "engadget", "arstechnica", "techcrunch",
                             "gizmodojp", "itmedia"]
SITE_CN.update({
    "kr36flash": "36氪快讯", "ithome": "IT之家", "sspai": "少数派", "cnbeta": "cnBeta",
    "engadget": "Engadget", "arstechnica": "Ars Technica", "techcrunch": "TechCrunch",
    "gizmodojp": "Gizmodo日本", "itmedia": "ITmedia",
})
SITE_LANG.update({
    "kr36flash": "zh_hant", "ithome": "zh_hant", "sspai": "zh_hant", "cnbeta": "zh_hant",
    "engadget": "en", "arstechnica": "en", "techcrunch": "en",
    "gizmodojp": "ja", "itmedia": "ja",
})


# ---------------------------------------------------------------------------
# 第三批扩充源（国际大报 + 港台/日经中文；语言跟随网站，中文站按繁体）
# ---------------------------------------------------------------------------
def fetch_guardian(n):
    return _rss_items("https://www.theguardian.com/technology/rss", "guardian", n)


def fetch_guardianintl(n):
    return _rss_items("https://www.theguardian.com/international/rss", "guardianintl", n)


def fetch_wsj(n):
    return _rss_items("https://feeds.a.dj.com/rss/RSSWSJD.xml", "wsj", n)


def fetch_nyt(n):
    return _rss_items("https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml", "nyt", n)


def fetch_cnn(n):
    out = _rss_items("http://rss.cnn.com/rss/edition_technology.rss", "cnn", n)
    if len(out) < n:
        out += _rss_items("http://rss.cnn.com/rss/edition.rss", "cnn", n - len(out))
    return out


def fetch_technews(n):
    return _rss_items("https://technews.tw/feed/", "technews", n)


def fetch_cna(n):
    return _rss_items("https://feeds.feedburner.com/rsscna/technology", "cna", n)


def fetch_epochtimes(n):
    r = _get("https://www.epochtimes.com/gb/nsc419.htm")
    txt = r.content.decode("utf-8", errors="ignore")
    out, seen = [], set()
    for title in re.findall(
            r'<a[^>]+href="[^"]*\.html?"[^>]*>\s*([\u4e00-\u9fa5][^<]{6,50})\s*</a>', txt):
        t = _clean(title)
        if t and t not in seen:
            seen.add(t)
            out.append({"title": t, "brief": "", "site": "epochtimes"})
        if len(out) >= n:
            break
    return out


def fetch_hket(n):
    r = _get("https://news.hket.com/?mtc=20080")
    txt = r.text
    out, seen = [], set()
    for title in re.findall(
            r'<a[^>]+href="[^"]*/article/\d+[^"]*"[^>]*>\s*([\u4e00-\u9fa5][^<]{8,50})\s*</a>', txt):
        t = _clean(title)
        if t and t not in seen and "訂閱" not in t and "訂閲" not in t:
            seen.add(t)
            out.append({"title": t, "brief": "", "site": "hket"})
        if len(out) >= n:
            break
    return out


_NIKKEI_NAV = ("日经", "日本游", "免费注册", "特朗普的美国", "中日深度观察",
               "日本企业研究", "会员", "订阅")


def fetch_nikkeicn(n):
    r = _get("https://cn.nikkei.com/top/201604-3.html")
    txt = r.content.decode("utf-8", errors="ignore")
    out, seen = [], set()
    for title in re.findall(r'<a[^>]+href="/[^"]+\.html"[^>]*>([^<]{6,60})</a>', txt):
        t = _clean(title)
        if not t or not re.search(r"[\u4e00-\u9fa5]", t):
            continue
        if t in seen or any(k in t for k in _NIKKEI_NAV):
            continue
        seen.add(t)
        out.append({"title": t, "brief": "", "site": "nikkeicn"})
        if len(out) >= n:
            break
    return out


FETCHERS.update({
    "guardian": fetch_guardian, "guardianintl": fetch_guardianintl, "wsj": fetch_wsj,
    "nyt": fetch_nyt, "cnn": fetch_cnn, "technews": fetch_technews, "cna": fetch_cna,
    "epochtimes": fetch_epochtimes, "hket": fetch_hket, "nikkeicn": fetch_nikkeicn,
})
ALL_SOURCES = ALL_SOURCES + ["guardian", "guardianintl", "wsj", "nyt", "cnn",
                             "technews", "cna", "epochtimes", "hket", "nikkeicn"]
SITE_CN.update({
    "guardian": "The Guardian", "guardianintl": "The Guardian", "wsj": "华尔街日报",
    "nyt": "纽约时报", "cnn": "CNN", "technews": "科技新报", "cna": "中央社",
    "epochtimes": "大纪元", "hket": "香港经济日报", "nikkeicn": "日经中文网",
})
SITE_LANG.update({
    "guardian": "en", "guardianintl": "en", "wsj": "en", "nyt": "en", "cnn": "en",
    "technews": "zh_hant", "cna": "zh_hant", "epochtimes": "zh_hant",
    "hket": "zh_hant", "nikkeicn": "zh_hant",  # 日经中文为简体源，按需求统一繁体输出
})


# ---------------------------------------------------------------------------
# 第四批扩充源（2026-07-13 新增：新加坡/港/台/国际金融资讯）
# ---------------------------------------------------------------------------
def fetch_straitstimes(n):
    """The Straits Times Global (RSS)"""
    return _rss_items("https://www.straitstimes.com/news/world/rss.xml", "straitstimes", n)


def fetch_yahoo_intl(n):
    """Yahoo奇摩国际市场 (HTML parse)"""
    r = _get("https://tw.stock.yahoo.com/intl-markets")
    txt = r.text
    out, seen = [], set()
    for m in re.finditer(
            r'<h[2-4][^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>'
            r'([\u4e00-\u9fff][^<]{8,80})</a>', txt, re.S):
        title = _clean(m.group(2))
        if title and title not in seen:
            seen.add(title)
            out.append({"title": title, "brief": "", "site": "yahoo_intl"})
            if len(out) >= n:
                break
    if not out:
        for m in re.finditer(
                r'<a[^>]+href="([^"]+)"[^>]*>\s*'
                r'([\u4e00-\u9fff][^<]{10,80})\s*</a>', txt, re.S):
            title = _clean(m.group(2))
            if title and title not in seen and len(title) > 12 and "Yahoo" not in title:
                seen.add(title)
                out.append({"title": title, "brief": "", "site": "yahoo_intl"})
                if len(out) >= n:
                    break
    return out


def fetch_cnbc_world(n):
    """CNBC World (HTML parse)"""
    r = _get("https://www.cnbc.com/world/?region=world")
    txt = r.text
    out, seen = [], set()
    for m in re.finditer(
            r'<a[^>]+href="(https://www\.cnbc\.com/\d{4}/\d{2}/\d{2}/[^"]+)"[^>]*>'
            r'(.*?)</a>', txt, re.S):
        title = _clean(m.group(2))
        if title and title not in seen and len(title) > 20:
            seen.add(title)
            out.append({"title": title, "brief": "", "site": "cnbc_world"})
            if len(out) >= n:
                break
    return out


def fetch_hket_home(n):
    """香港经济日报首页 (HTML parse)"""
    r = _get("https://www.hket.com/")
    txt = r.text
    out, seen = [], set()
    for m in re.finditer(
            r'<a[^>]+href="([^"]*hket[^"]*article[^"]*)"[^>]*>\s*'
            r'([\u4e00-\u9fff][^<]{8,60})\s*</a>', txt, re.S):
        title = _clean(m.group(2))
        if title and title not in seen and "訂閱" not in title and "訂閲" not in title:
            seen.add(title)
            out.append({"title": title, "brief": "", "site": "hket_home"})
            if len(out) >= n:
                break
    if not out:
        for m in re.finditer(
                r'<a[^>]+href="([^"]+)"[^>]*>\s*'
                r'([\u4e00-\u9fff][^<]{10,60})\s*</a>', txt, re.S):
            title = _clean(m.group(2))
            if title and title not in seen and len(title) > 12 \
                    and "訂閱" not in title and "登入" not in title and "首頁" not in title:
                seen.add(title)
                out.append({"title": title, "brief": "", "site": "hket_home"})
                if len(out) >= n:
                    break
    return out


def fetch_moneydj(n):
    """MoneyDJ理财网 (RSS, verify=False due to SSL cert issue)"""
    import urllib3 as _u3
    _u3.disable_warnings(_u3.exceptions.InsecureRequestWarning)
    r = requests.get(
        "https://www.moneydj.com/KMDJ/RssCenter.aspx?svc=NR&fType=1&arg=MB010000",
        headers={"User-Agent": UA}, timeout=25, verify=False)
    r.raise_for_status()
    txt = r.content.decode("utf-8", errors="ignore")
    out = []
    for it in re.findall(r"<item>(.*?)</item>", txt, re.S):
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        title = _clean(tm.group(1)) if tm else ""
        if not title or "即時新聞" in title:
            continue
        dm = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
        out.append({"title": title, "brief": _clean(dm.group(1)) if dm else "", "site": "moneydj"})
        if len(out) >= n:
            break
    return out


FETCHERS.update({
    "straitstimes": fetch_straitstimes, "yahoo_intl": fetch_yahoo_intl,
    "cnbc_world": fetch_cnbc_world, "hket_home": fetch_hket_home,
    "moneydj": fetch_moneydj,
})
ALL_SOURCES = ALL_SOURCES + ["straitstimes", "yahoo_intl", "cnbc_world",
                             "hket_home", "moneydj"]
SITE_CN.update({
    "straitstimes": "The Straits Times", "yahoo_intl": "Yahoo奇摩",
    "cnbc_world": "CNBC World", "hket_home": "香港经济日报",
    "moneydj": "MoneyDJ理财网",
})
SITE_LANG.update({
    "straitstimes": "en", "yahoo_intl": "zh_hant",
    "cnbc_world": "en", "hket_home": "zh_hant",
    "moneydj": "zh_hant",
})


# ---------------------------------------------------------------------------
# 第五批扩充源（2026-07-13 替代方案解决：RSS/curl_cffi/Google News）
# ---------------------------------------------------------------------------
def fetch_hk_investing_rss(n):
    """Investing.com港股 (RSS，绕过403)"""
    return _rss_items("https://hk.investing.com/rss/news.rss", "hk_investing", n)


def fetch_wealth_tw(n):
    """财讯台湾 (RSS，绕过SPA)"""
    import urllib3 as _u3
    _u3.disable_warnings(_u3.exceptions.InsecureRequestWarning)
    r = requests.get("https://www.wealth.com.tw/rss",
                     headers={"User-Agent": UA}, timeout=25, verify=False)
    r.raise_for_status()
    txt = r.content.decode("utf-8", errors="ignore")
    out = []
    for it in re.findall(r"<item>(.*?)</item>", txt, re.S):
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        title = _clean(tm.group(1)) if tm else ""
        if not title or len(title) < 8:
            continue
        dm = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
        out.append({"title": title, "brief": _clean(dm.group(1)) if dm else "", "site": "wealth_tw"})
        if len(out) >= n:
            break
    return out


def fetch_bloomberg_rss(n):
    """Bloomberg Markets (RSS feed)"""
    return _rss_items("https://feeds.bloomberg.com/markets/news.rss", "bloomberg_jp", n)


def fetch_8world_cffi(n):
    """8世界新加坡 (curl_cffi 绕过403，从title属性提取)"""
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        return []
    r = cffi_requests.get("https://www.8world.com/singapore", impersonate="chrome", timeout=20)
    if r.status_code != 200:
        return []
    txt = r.text
    out, seen = [], set()
    # 8world articles are in title/aria-label attributes
    for title in re.findall(r'(?:title|aria-label)="([\u4e00-\u9fff][^"]{8,80})"', txt):
        t = _clean(title)
        if t and t not in seen and len(t) > 10:
            seen.add(t)
            out.append({"title": t, "brief": "", "site": "8world"})
            if len(out) >= n:
                break
    return out


def fetch_ifnews_gn(n):
    """国际金融报 (Google News RSS代理)"""
    r = _get("https://news.google.com/rss/search?q=site:ifnews.com&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")
    txt = r.content.decode("utf-8", errors="ignore")
    out, seen = [], set()
    for it in re.findall(r"<item>(.*?)</item>", txt, re.S):
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        if not tm:
            continue
        title = _clean(tm.group(1))
        # Google News titles often have " - 国际金融报" suffix
        title = re.sub(r"\s*-\s*国际金融报\s*$", "", title)
        if title and title not in seen and len(title) > 10 and "国际金融报" not in title:
            seen.add(title)
            out.append({"title": title, "brief": "", "site": "ifnews"})
            if len(out) >= n:
                break
    return out


FETCHERS.update({
    "hk_investing": fetch_hk_investing_rss, "wealth_tw": fetch_wealth_tw,
    "bloomberg_jp": fetch_bloomberg_rss, "8world": fetch_8world_cffi,
    "ifnews": fetch_ifnews_gn,
})
ALL_SOURCES = ALL_SOURCES + ["hk_investing", "wealth_tw", "bloomberg_jp",
                             "8world", "ifnews"]
SITE_CN.update({
    "hk_investing": "Investing.com", "wealth_tw": "财讯",
    "bloomberg_jp": "Bloomberg", "8world": "8世界",
    "ifnews": "国际金融报",
})
SITE_LANG.update({
    "hk_investing": "zh_hant", "wealth_tw": "zh_hant",
    "bloomberg_jp": "en", "8world": "zh_hant",
    "ifnews": "zh_hant",
})


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
