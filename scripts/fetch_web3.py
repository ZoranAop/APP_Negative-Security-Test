#!/usr/bin/env python3
"""
fetch_web3.py — 统一 Web3 资讯多源采集器：从 14 个 Web3/Crypto/Tech 媒体各取 N 条最新消息，
统一打上 web3 标签，产出纯文本 moments CSV（image_urls 空 → media_info type=text）。

支持来源（--sources，逗号分隔；默认全部）：
  techflow    深潮 TechFlow      https://www.techflowpost.com/api/client/common/rss   (JSON)
  web3bbs     Web3BBS            https://www.web3bbs.net/column_7.html                (HTML)
  foresight   ForesightNews      https://api.foresightnews.pro/v1/news                (JSON, list=base64+zlib)
  menews      ME News            https://api.me.news/aimpact/articles                 (JSON POST)
  web3caff    Web3Caff Research  https://research.web3caff.com/wp-json/wp/v2/posts    (WordPress JSON)
  panews      PANews             https://www.panewslab.com/zh/newsflash               (HTML SSR)
  bingx       BingX News         https://bingx.com/zh-tc/news/web3                    (HTML SSR)
  blockweeks  BlockWeeks         https://blockweeks.com/feed/                         (RSS)
  wublock     吴说 WuBlock        https://www.wublock123.com/                          (HTML + Aliyun WAF cookie)
  e27         e27.co             https://e27.co/feed/                                 (RSS, 东南亚创投/科技)
  techinasia  Tech in Asia       https://www.techinasia.com/feed                      (RSS, 亚洲科技/创业)
  coinlive    CoinLive           https://www.coinlive.com/news                        (HTML, Crypto 新闻)
  superteam   Superteam SG       https://superteam.sg/                                (HTML, Solana 生态/Web3 社区)
  blockhead   Blockhead          https://www.blockhead.co/                            (HTML, 东南亚 Crypto/Web3)
  theblock    The Block          https://www.theblock.co/rss.xml                      (RSS)
  decrypt     Decrypt            https://decrypt.co/feed                              (RSS)
  thedefiant  The Defiant        https://thedefiant.io/feed                           (RSS)
  bitcoinmagazine Bitcoin Magazine https://bitcoinmagazine.com/feed                  (RSS)
  beincrypto  BeInCrypto         https://beincrypto.com/feed/                         (RSS)
  odaily      Odaily 星球日报     https://www.odaily.news/                            (HTML SSR, 中文 Web3 资讯)
  bloomberg   Bloomberg          https://feeds.bloomberg.com/markets/news.rss          (RSS, 美股)
  cnbc        CNBC               https://www.cnbc.com/id/100003114/device/rss/rss.html (RSS, 美股)
  wsj         WSJ 华尔街日报      https://feeds.a.dj.com/rss/RSSWSJD.xml               (RSS, 美股)
  reuters     Reuters 路透社      (Google News RSS 兜底)                              (RSS, 美股)
  marketwatch MarketWatch        https://feeds.content.dowjones.io/public/rss/mw_topstories (RSS, 美股)
  yahoo_finance Yahoo Finance    https://finance.yahoo.com/news/rssindex                (RSS, 美股)
  benzinga    Benzinga           https://www.benzinga.com/                             (HTML, 美股)
  ft          FT 金融时报         https://www.ft.com/rss/home                          (RSS, 美股)
  barrons     Barron's           https://www.barrons.com/market-data                    (HTML, 美股)
  thestreet   TheStreet          https://www.thestreet.com/.rss/full/                  (RSS, 美股)

用法：
  py -3 scripts/fetch_web3.py --sources techflow,foresight,menews,web3caff,panews,bingx,blockweeks,wublock,web3bbs,e27,techinasia,coinlive,superteam,blockhead `
     --per-site 10 --dedupe-file state/seen_web3.json --output web3_raw.csv

去重：--dedupe-file 记录已用消息（归一化标题），跨批次自动跳过、不重复发。
所有来源均公开、无需登录；请勿在仓库或 .env 写入任何账号密码。
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import re
import sys
import zlib
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# web3bbs 首页/栏目混有非 Web3 内容，用关键词判定
WEB3_KW = ["btc", "bitcoin", "比特", "eth", "以太", "币", "crypto", "加密", "web3",
           "defi", "nft", "dao", "depin", "gamefi", "链", "chain", "token", "代币",
           "etf", "稳定币", "stablecoin", "钱包", "wallet", "meme", "solana", "sol",
           "layer", "rollup", "l2", "质押", "staking", "空投", "airdrop", "rwa",
           "币安", "binance", "okx", "bybit", "交易所", "usdt", "usdc", "perp", "dex",
           "巨鲸", "链上", "on-chain", "挖矿", "矿", "公链", "波场", "tron", "bnb"]


def _u8():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


def _get(url, **kw):
    last = None
    for _ in range(4):
        try:
            r = requests.get(url, timeout=25, **kw)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


def _is_web3(t: str) -> bool:
    low = t.lower()
    return any(k in low for k in WEB3_KW)


# ---------------------------------------------------------------------------
# per-source fetchers → list[{"title","brief","site"}]
# ---------------------------------------------------------------------------

def fetch_techflow(n):
    r = _get("https://www.techflowpost.com/api/client/common/rss", headers={"User-Agent": UA})
    out = []
    for it in r.json().get("data", []):
        t = (it.get("title") or "").strip()
        if not t:
            continue
        out.append({"title": t, "brief": re.sub(r"<[^>]+>", "", it.get("description") or "").strip(),
                    "site": "techflow"})
        if len(out) >= n:
            break
    return out


def fetch_web3bbs(n):
    r = _get("https://www.web3bbs.net/column_7.html",
             headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    pairs = re.findall(r'<a[^>]+href="([^"]*article_\d+\.html)"[^>]*>\s*([^<]{8,90})\s*</a>', r.text)
    out, seen = [], set()
    for _u, ti in pairs:
        ti = html.unescape(ti).strip()
        if ti in seen or not _is_web3(ti):
            continue
        seen.add(ti)
        out.append({"title": ti, "brief": "", "site": "web3bbs"})
        if len(out) >= n:
            break
    return out


def fetch_foresight(n):
    r = _get("https://api.foresightnews.pro/v1/news", params={"page": 1, "size": max(n, 20)},
             headers={"User-Agent": UA, "Referer": "https://foresightnews.pro/"})
    data = r.json().get("data")
    lst = data.get("list") if isinstance(data, dict) else data
    if isinstance(lst, str):
        lst = json.loads(zlib.decompress(base64.b64decode(lst)))
    out = []
    for it in lst or []:
        t = (it.get("title") or "").strip()
        if not t:
            continue
        out.append({"title": t, "brief": re.sub(r"<[^>]+>", "", it.get("brief") or "").strip(),
                    "site": "foresight"})
        if len(out) >= n:
            break
    return out


def fetch_menews(n):
    r = requests.post("https://api.me.news/aimpact/articles", json={"page": 1, "page_size": max(n, 20)},
                      headers={"User-Agent": UA, "Origin": "https://www.me.news",
                               "Referer": "https://www.me.news/", "Content-Type": "application/json"},
                      timeout=25)
    r.raise_for_status()
    lst = (r.json().get("data") or {}).get("list") or []
    out = []
    for it in lst:
        t = (it.get("title") or "").strip()
        if not t:
            continue
        out.append({"title": t, "brief": (it.get("summary") or it.get("content") or "").strip()[:200],
                    "site": "menews"})
        if len(out) >= n:
            break
    return out


def fetch_web3caff(n):
    r = _get("https://research.web3caff.com/wp-json/wp/v2/posts",
             params={"per_page": max(n, 10), "_fields": "id,title,link,date,excerpt"},
             headers={"User-Agent": UA})
    out = []
    for it in r.json():
        t = html.unescape(re.sub(r"<[^>]+>", "", (it.get("title") or {}).get("rendered", ""))).strip()
        if not t:
            continue
        brief = html.unescape(re.sub(r"<[^>]+>", "", (it.get("excerpt") or {}).get("rendered", ""))).strip()
        out.append({"title": t, "brief": brief[:200], "site": "web3caff"})
        if len(out) >= n:
            break
    return out


def fetch_panews(n):
    r = _get("https://www.panewslab.com/zh/newsflash", headers={"User-Agent": UA})
    t = r.text
    out, seen = [], set()
    for link, inner in re.findall(r'href="(/zh/articles/[0-9a-f-]{36})"[^>]*>(.*?)</a>', t, re.S):
        txt = re.sub(r"<[^>]+>", "", inner).replace("\u300c", "").replace("\u300d", "")
        txt = html.unescape(txt).strip()
        txt = re.sub(r"^\w+ \d+", "", txt).strip()
        if len(txt) >= 5 and link not in seen:
            seen.add(link)
            out.append({"title": txt, "brief": "", "site": "panews"})
        if len(out) >= n:
            break
    return out


def fetch_bingx(n):
    r = _get("https://bingx.com/zh-tc/news/web3", headers={"User-Agent": UA})
    titles = [html.unescape(x) for x in re.findall(r'\\?"headline\\?":\\?"([^"\\]{6,120})', r.text)]
    out, seen = [], set()
    for t in titles:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            out.append({"title": t, "brief": "", "site": "bingx"})
        if len(out) >= n:
            break
    return out


def fetch_blockweeks(n):
    r = _get("https://blockweeks.com/feed/", headers={"User-Agent": UA})
    r.encoding = "utf-8"
    out = []
    for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        if not m:
            continue
        t = html.unescape(m.group(1).strip())
        out.append({"title": t, "brief": "", "site": "blockweeks"})
        if len(out) >= n:
            break
    return out


def _wublock_solve(arg1: str) -> str:
    order = [0xf, 0x23, 0x1d, 0x18, 0x21, 0x10, 0x1, 0x26, 0xa, 0x9, 0x13, 0x1f, 0x28, 0x1b,
             0x16, 0x17, 0x19, 0xd, 0x6, 0xb, 0x27, 0x12, 0x14, 0x8, 0xe, 0x15, 0x20, 0x1a,
             0x2, 0x1e, 0x7, 0x4, 0x11, 0x5, 0x3, 0x1c, 0x22, 0x25, 0xc, 0x24]
    key = "3000176000856006061501533003690027800375"
    q = [None] * len(order)
    for x in range(len(arg1)):
        for z in range(len(order)):
            if order[z] == x + 1:
                q[z] = arg1[x]
    u = "".join(c for c in q if c)
    v = ""
    for x in range(0, min(len(u), len(key)), 2):
        a = int(u[x:x + 2], 16) ^ int(key[x:x + 2], 16)
        h = format(a, "x")
        v += ("0" + h) if len(h) == 1 else h
    return v


def fetch_wublock(n):
    s = requests.Session()
    r = s.get("https://www.wublock123.com/", headers={"User-Agent": UA}, timeout=20)
    m = re.search(r"arg1='([0-9A-F]+)'", r.text)
    if m:
        s.cookies.set("acw_sc__v2", _wublock_solve(m.group(1)), domain="www.wublock123.com")
        r = s.get("https://www.wublock123.com/", headers={"User-Agent": UA}, timeout=20)
    t = r.text
    out, seen = [], set()
    pat = r'href="(/articles/[a-z0-9]+(?:-[a-z0-9]+)*-\d+)"[^>]*>(.*?)</a>'
    for link, inner in re.findall(pat, t, re.S):
        txt = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        if len(txt) >= 6 and link not in seen:
            seen.add(link)
            out.append({"title": txt, "brief": "", "site": "wublock"})
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------------------
# Southeast Asia Web3 / Tech / Crypto sources
# ---------------------------------------------------------------------------

def fetch_e27(n):
    """e27.co — Southeast Asia startup & tech news (RSS feed)."""
    r = _get("https://e27.co/feed/", headers={"User-Agent": UA})
    r.encoding = "utf-8"
    out = []
    for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        if not m:
            continue
        t = html.unescape(m.group(1).strip())
        # Extract description/brief
        dm = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
        brief = ""
        if dm:
            brief = re.sub(r"<[^>]+>", "", html.unescape(dm.group(1))).strip()[:200]
        if t and len(t) >= 6:
            out.append({"title": t, "brief": brief, "site": "e27"})
        if len(out) >= n:
            break
    return out


def fetch_techinasia(n):
    """techinasia.com — Asia tech & startup news (RSS feed)."""
    r = _get("https://www.techinasia.com/feed", headers={"User-Agent": UA})
    r.encoding = "utf-8"
    out = []
    for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        if not m:
            continue
        t = html.unescape(m.group(1).strip())
        dm = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
        brief = ""
        if dm:
            brief = re.sub(r"<[^>]+>", "", html.unescape(dm.group(1))).strip()[:200]
        if t and len(t) >= 6:
            out.append({"title": t, "brief": brief, "site": "techinasia"})
        if len(out) >= n:
            break
    return out


def fetch_coinlive(n):
    """coinlive.com — Crypto & Web3 news (HTML scraping)."""
    r = _get("https://www.coinlive.com/news",
             headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    out, seen = [], set()
    # Try extracting article titles from common patterns
    titles = re.findall(r'<h[234][^>]*>(.*?)</h[234]>', r.text, re.DOTALL)
    for raw in titles:
        t = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
        if t and len(t) >= 8 and t not in seen:
            seen.add(t)
            out.append({"title": t, "brief": "", "site": "coinlive"})
        if len(out) >= n:
            break
    return out


def fetch_superteam(n):
    """superteam.sg — Singapore Web3 community / Solana ecosystem."""
    r = _get("https://superteam.sg/",
             headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    out, seen = [], set()
    # Extract headings and project titles
    titles = re.findall(r'<h[234][^>]*>(.*?)</h[234]>', r.text, re.DOTALL)
    for raw in titles:
        t = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
        if t and len(t) >= 6 and t not in seen:
            seen.add(t)
            out.append({"title": t, "brief": "", "site": "superteam"})
        if len(out) >= n:
            break
    return out


def fetch_blockhead(n):
    """blockhead.co — Southeast Asia crypto & Web3 news."""
    r = _get("https://www.blockhead.co/",
             headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    out, seen = [], set()
    titles = re.findall(r'<h[234][^>]*>(.*?)</h[234]>', r.text, re.DOTALL)
    for raw in titles:
        t = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
        if t and len(t) >= 8 and t not in seen:
            seen.add(t)
            out.append({"title": t, "brief": "", "site": "blockhead"})
        if len(out) >= n:
            break
    return out


def _fetch_rss(url: str, site: str, n: int) -> list[dict]:
    """通用 RSS 采集：提取 <item> 的 title + description 摘要。"""
    r = _get(url, headers={"User-Agent": UA})
    r.encoding = "utf-8"
    out = []
    for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        if not tm:
            continue
        title = html.unescape(tm.group(1).strip())
        if not title:
            continue
        dm = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", it, re.S)
        brief = ""
        if dm:
            brief = re.sub(r"<[^>]+>", "", html.unescape(dm.group(1))).strip()[:200]
        out.append({"title": title, "brief": brief, "site": site})
        if len(out) >= n:
            break
    return out


def _make_rss_fetcher(url: str, site: str):
    def _f(n: int) -> list[dict]:
        return _fetch_rss(url, site, n)
    return _f


def fetch_odaily(n):
    """odaily.news（Odaily 星球日报）— 中文 Web3 资讯（服务端渲染，抽取文章卡片）。"""
    r = _get("https://www.odaily.news/", headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    txt = r.text
    out, seen = [], set()
    # 文章卡片：<a href="/zh-CN/post/ID" ...><img alt="标题" ...> 或直接文本标题
    for m in re.finditer(r'href="/zh-CN/post/\d+"[^>]*>(.*?)</a>', txt, re.S):
        inner = m.group(1)
        alt = re.search(r'alt="([^"]+)"', inner)
        title = html.unescape(alt.group(1)).strip() if alt else ""
        if not title:
            title = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        if title and len(title) >= 6 and title not in seen:
            seen.add(title)
            out.append({"title": title, "brief": "", "site": "odaily"})
        if len(out) >= n:
            break
    return out


def _fetch_html_headlines(url: str, site: str, n: int) -> list[dict]:
    """通用 HTML 标题抽取：取 h2/h3 中的新闻标题（过滤导航/短文本/全大写/CSS 片段）。"""
    r = _get(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    out, seen = [], set()
    for raw in re.findall(r"<h[234][^>]*>(.*?)</h[234]>", r.text, re.S):
        t = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
        if (t and len(t) >= 15 and not t.isupper() and not t.startswith(".")
                and t not in seen):
            seen.add(t)
            out.append({"title": t, "brief": "", "site": site})
        if len(out) >= n:
            break
    return out


def fetch_benzinga(n):
    """benzinga.com — 美股财经资讯（HTML 标题抽取）。"""
    return _fetch_html_headlines("https://www.benzinga.com/", "benzinga", n)


def fetch_barrons(n):
    """barrons.com — Barron's 美股市场（HTML 标题抽取，付费墙外摘要）。"""
    return _fetch_html_headlines("https://www.barrons.com/market-data", "barrons", n)


def fetch_reuters(n):
    """reuters.com — 路透社市场/美股资讯（Google News RSS 兜底，直连 feeds.reuters.com 常被墙）。"""
    url = "https://news.google.com/rss/search?q=site:reuters.com%20markets&hl=en-US&gl=US&ceid=US:en"
    r = _get(url, headers={"User-Agent": UA})
    r.encoding = "utf-8"
    out, seen = [], set()
    for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        if not tm:
            continue
        t = html.unescape(tm.group(1).strip())
        t = re.sub(r"\s+-\s+Reuters\s*$", "", t).strip()  # 去掉 Google News 的来源后缀
        if t and t not in seen:
            seen.add(t)
            out.append({"title": t, "brief": "", "site": "reuters"})
        if len(out) >= n:
            break
    return out


FETCHERS = {
    "techflow": fetch_techflow, "web3bbs": fetch_web3bbs, "foresight": fetch_foresight,
    "menews": fetch_menews, "web3caff": fetch_web3caff, "panews": fetch_panews,
    "bingx": fetch_bingx, "blockweeks": fetch_blockweeks, "wublock": fetch_wublock,
    "e27": fetch_e27, "techinasia": fetch_techinasia, "coinlive": fetch_coinlive,
    "superteam": fetch_superteam, "blockhead": fetch_blockhead,
    "theblock": _make_rss_fetcher("https://www.theblock.co/rss.xml", "theblock"),
    "decrypt": _make_rss_fetcher("https://decrypt.co/feed", "decrypt"),
    "thedefiant": _make_rss_fetcher("https://thedefiant.io/feed", "thedefiant"),
    "bitcoinmagazine": _make_rss_fetcher("https://bitcoinmagazine.com/feed", "bitcoinmagazine"),
    "beincrypto": _make_rss_fetcher("https://beincrypto.com/feed/", "beincrypto"),
    "odaily": fetch_odaily,
    "bloomberg": _make_rss_fetcher("https://feeds.bloomberg.com/markets/news.rss", "bloomberg"),
    "cnbc": _make_rss_fetcher("https://www.cnbc.com/id/100003114/device/rss/rss.html", "cnbc"),
    "wsj": _make_rss_fetcher("https://feeds.a.dj.com/rss/RSSWSJD.xml", "wsj"),
    "reuters": fetch_reuters,
    "marketwatch": _make_rss_fetcher("https://feeds.content.dowjones.io/public/rss/mw_topstories", "marketwatch"),
    "yahoo_finance": _make_rss_fetcher("https://finance.yahoo.com/news/rssindex", "yahoo_finance"),
    "benzinga": fetch_benzinga,
    "ft": _make_rss_fetcher("https://www.ft.com/rss/home", "ft"),
    "barrons": fetch_barrons,
    "thestreet": _make_rss_fetcher("https://www.thestreet.com/.rss/full/", "thestreet"),
}
ALL_SOURCES = list(FETCHERS.keys())


def _norm(t):
    return re.sub(r"[\s\u3000，,。.：:！!？?、\"'()（）\[\]\-]+", "", t.lower())


def _toks(t):
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2}", t.lower()))


def main() -> int:
    _u8()
    ap = argparse.ArgumentParser(description="Fetch Web3 news from up to 9 sites → text moments CSV")
    ap.add_argument("--sources", default=",".join(ALL_SOURCES),
                    help="comma keys: " + ",".join(ALL_SOURCES))
    ap.add_argument("--per-site", type=int, default=10)
    ap.add_argument("--tag", default="web3", help="标签，写入 _tag 列（默认 web3）")
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
        except Exception:
            pass
    print(f"[web3] 已用标题记录: {len(used_norm)}", file=sys.stderr)

    picked_tok = []
    picked_norm = set()

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
            items = FETCHERS[name](args.per_site * 3)  # 多取，去重后截断
        except Exception as e:  # noqa: BLE001
            print(f"[web3] {name} ERR: {e}", file=sys.stderr)
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
        print(f"[web3] {name}: {kept} items", file=sys.stderr)

    if not rows:
        print("[warn] no items", file=sys.stderr)
        return 1

    if args.dedupe_file:
        merged = sorted(used_norm | {_norm(it["title"]) for it in rows})
        Path(args.dedupe_file).parent.mkdir(parents=True, exist_ok=True)
        Path(args.dedupe_file).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

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
                        "location_name": "", "location_address": "", "location_lat": "", "location_lon": "",
                        "_source": "web3news", "_site": it["site"], "_tag": args.tag, "_brief": it["brief"]})
    print(f"[OK] wrote {len(rows)} web3 news ({len(sources)} sites) → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
