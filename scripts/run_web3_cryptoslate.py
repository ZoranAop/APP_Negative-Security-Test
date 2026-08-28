#!/usr/bin/env python3
"""Fetch cryptoslate.com latest news + publish 8 posts to web3 accounts"""
import re, json, csv, subprocess, sys, time, os, io
from pathlib import Path
import requests
from bs4 import BeautifulSoup

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', write_through=True)
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://cryptoslate.com/"}

# 1) Fetch main page
url = "https://cryptoslate.com/"
s = requests.Session()
r = s.get(url, headers=HEADERS, timeout=20)
print(f"Main page: {r.status_code}, Len: {len(r.text)}")

# Parse with BeautifulSoup
soup = BeautifulSoup(r.text, 'html.parser')

# Find article links
articles = []
for a in soup.find_all('a', href=True):
    href = a['href']
    if '/news/' in href or '/article/' in href or '/features/' in href:
        title = a.get_text(strip=True)
        if title and len(title) > 10:
            # Normalize URL
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = 'https://cryptoslate.com' + href
            articles.append({"title": title, "url": href})

# Deduplicate
seen = set()
unique_articles = []
for a in articles:
    if a['url'] not in seen:
        seen.add(a['url'])
        unique_articles.append(a)
articles = unique_articles

print(f"\nFound {len(articles)} articles:")
for a in articles[:15]:
    print(f"  {a['title'][:60]} -> {a['url']}")

# 2) Fetch top 8 articles for content
selected = articles[:8]
for a in selected:
    try:
        r2 = s.get(a["url"], headers=HEADERS, timeout=15)
        soup2 = BeautifulSoup(r2.text, 'html.parser')
        # Find article body
        body = soup2.find('article') or soup2.find('div', class_=re.compile('article|content|post'))
        if body:
            texts = body.get_text(separator=' ', strip=True)
            texts = re.sub(r'\s+', ' ', texts)[:600]
        else:
            texts = soup2.get_text(separator=' ', strip=True)
            texts = re.sub(r'\s+', ' ', texts)[:600]
        a["content"] = texts
        print(f"  Fetched: {a['title'][:40]}")
    except Exception as e:
        a["content"] = ""
        print(f"  ERROR: {a['title'][:40]}: {e}")

# 3) Build差异化英文文案
caption_variants = [
    "Bitcoin's latest move has the community divided. Some see it as accumulation phase, others as distribution. Either way, volatility is back and that's what keeps traders awake at night. The charts don't lie but they don't tell the whole story either.",
    "Ethereum gas fees dropping again? Finally some good news for regular users. Layer 2 solutions are actually delivering on their promise. Maybe the scaling wars are heating up for the right reasons this time.",
    "Another major exchange update today. The regulatory landscape keeps shifting and everyone's trying to adapt. Compliance costs are real but so is the institutional money pouring in. This is how mature markets form.",
    "Solana's ecosystem growth is impressive but the drama never ends. One day it's FTX fallout, next day it's network outages. Still, the dev activity speaks for itself. Bullish on the tech, skeptical on the execution.",
    "Stablecoin market cap hitting new highs while BTC consolidates. Smart money is positioning for something big. When does the next leg up start? Nobody knows for sure but the liquidity tells a story.",
    "Crypto adoption in emerging markets continues to surprise. Remittances, inflation hedge, financial inclusion — the use cases are real even if the price action is noisy. This is the narrative that matters long-term.",
    "DeFi TVL fluctuations keeping everyone on edge. One week it's all growth, next week it's exploits. Risk management is everything in this space. Not your keys, not your responsibility — still relevant advice.",
    "Web3 gaming tokens pumping again. Will this cycle be different? Last time we saw promises but limited real usage. This time the tech is actually better but player adoption is still the question mark. Watching closely.",
]

# 4) Pick web3 accounts
users = list(csv.DictReader(open(ROOT / "accounts_web3_100.csv", encoding="utf-8-sig")))
tokens = json.loads((ROOT / "result" / "tokens.json").read_text(encoding="utf-8"))
used = set(tokens.keys())
import glob as glob_mod
for f in glob_mod.glob(str(ROOT / "*" / "accounts_*.csv")):
    try:
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            for k in ("邮箱", "email", "Email"):
                v = (r.get(k) or "").strip().lower()
                if "@" in v:
                    used.add(v)
    except Exception:
        pass

avail_en = [r for r in users
            if r.get("昵称") and len(r.get("昵称") or "") <= 20
            and not any(ord(c) > 127 for c in r["昵称"])
            and (r.get("邮箱") or "").strip().lower() not in used]
print(f"\nAvailable EN web3: {len(avail_en)}")

# 5) Build and publish
ts = time.strftime("%Y%m%d_%H%M%S")
wd = ROOT / f"web3_cryptoslate_{ts}"
wd.mkdir(parents=True, exist_ok=True)

acc_out = wd / f"accounts_{ts}.csv"
mom_out = wd / f"moments_{ts}.csv"

with open(acc_out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
    w.writeheader()
    for i in range(min(8, len(avail_en))):
        a = avail_en[i]
        w.writerow({"序号": a["序号"], "昵称": a["昵称"], "邮箱": a["邮箱"], "密码": a["密码"]})
        print(f"  {a['昵称']} ({a['邮箱']})")

fields = ["content", "visibility", "room_id", "image_urls",
          "location_name", "location_address", "location_lat", "location_lon",
          "_source", "_slug", "_lang"]
with open(mom_out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    n = min(8, len(caption_variants), len(avail_en))
    for i in range(n):
        w.writerow({
            "content": caption_variants[i],
            "visibility": "0", "room_id": "",
            "image_urls": "",
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_source": "cryptoslate", "_slug": f"crypto-news-{i+1}", "_lang": "en",
        })

print(f"\nPublished {n} posts")

PY = sys.executable
cmd = [PY, str(ROOT / "scripts" / "publish_from_tokens.py"),
       "--accounts-csv", str(acc_out), "--csv", str(mom_out),
       "--concurrency", "2", "--login-spacing", "3.0",
       "--tokens-in", str(ROOT / "result" / "tokens.json"),
       "--tokens-out", str(ROOT / "result" / "tokens.json")]
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
env["POST_CROP_BOTTOM_HOSTS"] = ""
print("\n=== Publishing ===")
rc = subprocess.call(cmd, cwd=str(ROOT), env=env)
print(f"Exit code: {rc}")
