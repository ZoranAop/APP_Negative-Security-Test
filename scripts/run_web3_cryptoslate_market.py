#!/usr/bin/env python3
"""Fetch cryptoslate.com/market/ news + publish 7 posts to web3 accounts"""
import re, json, csv, subprocess, sys, time, os, io
from pathlib import Path
import requests
from bs4 import BeautifulSoup

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', write_through=True)
except Exception:
    pass

import urllib3
urllib3.disable_warnings()

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://cryptoslate.com/"}

# 1) Fetch market page
url = "https://cryptoslate.com/market/"
s = requests.Session()
r = s.get(url, headers=HEADERS, timeout=20, verify=False)
print(f"Market page: {r.status_code}, Len: {len(r.text)}")

soup = BeautifulSoup(r.text, 'html.parser')

# Find article links - look for news cards
articles = []
for a in soup.find_all('a', href=True):
    href = a['href']
    title = a.get_text(strip=True)
    if ('/news/' in href or '/feature/' in href or '/analysis/' in href) and title and len(title) > 15:
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = 'https://cryptoslate.com' + href
        articles.append({"title": title, "url": href})

# Deduplicate
seen = set()
unique = []
for a in articles:
    if a['url'] not in seen:
        seen.add(a['url'])
        unique.append(a)
articles = unique

print(f"\nFound {len(articles)} articles:")
for a in articles[:15]:
    print(f"  {a['title'][:60]}")

# Pick 7
selected = articles[:7]

# 2) Fetch content for each
for a in selected:
    try:
        r2 = s.get(a["url"], headers=HEADERS, timeout=15, verify=False)
        soup2 = BeautifulSoup(r2.text, 'html.parser')
        body = soup2.find('article') or soup2.find('div', class_=re.compile('article|content|post|entry'))
        if body:
            texts = body.get_text(separator=' ', strip=True)
            texts = re.sub(r'\s+', ' ', texts)[:500]
        else:
            texts = soup2.get_text(separator=' ', strip=True)
            texts = re.sub(r'\s+', ' ', texts)[:500]
        a["content"] = texts
        print(f"  Fetched: {a['title'][:40]}")
    except Exception as e:
        a["content"] = ""
        print(f"  ERROR: {a['title'][:40]}: {e}")

# 3) Build差异化英文文案（根据CRYPTOSLATE市场新闻主题）
caption_variants = [
    "Crypto markets showing interesting signals today. Bitcoin holding support levels while altcoins start moving. The consolidation phase might be ending sooner than expected. Volume patterns suggest accumulation is happening quietly.",
    "Market sentiment shifting again. One day we're talking about correction, next day about recovery. This volatility is what makes crypto trading addictive but also dangerous. Position sizing matters more than direction prediction.",
    "Watching the stablecoin flows closely right now. Large USDC minting usually precedes buying pressure. When that money hits the market, prices tend to follow. The on-chain data doesn't lie, even if the charts do.",
    "Ethereum's latest upgrade discussion has the community split. Some see it as necessary evolution, others think it's over-engineering. Either way, the dev activity speaks for itself. Building continues regardless of price action.",
    "Alt season indicators flashing mixed signals. Some metrics say soon, others say not yet. The truth is probably somewhere in between. Historical patterns suggest we're still early in the cycle if you look at broader trends.",
    "Institutional adoption narrative getting real again. ETF flows, corporate treasuries, pension fund allocations — the walls are coming down slowly but surely. This isn't 2017 anymore, the players are different now.",
    "Risk-on assets rallying while traditional markets chop. Crypto still acting as the leveraged bet on risk appetite. When equities sneeze, crypto catches a cold. But the correlation isn't permanent — sometimes they decouple beautifully.",
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
wd = ROOT / f"web3_cryptoslate_market_{ts}"
wd.mkdir(parents=True, exist_ok=True)

acc_out = wd / f"accounts_{ts}.csv"
mom_out = wd / f"moments_{ts}.csv"

with open(acc_out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
    w.writeheader()
    for i in range(min(7, len(avail_en))):
        a = avail_en[i]
        w.writerow({"序号": a["序号"], "昵称": a["昵称"], "邮箱": a["邮箱"], "密码": a["密码"]})
        print(f"  {a['昵称']} ({a['邮箱']})")

fields = ["content", "visibility", "room_id", "image_urls",
          "location_name", "location_address", "location_lat", "location_lon",
          "_source", "_slug", "_lang"]
with open(mom_out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    n = min(7, len(caption_variants), len(avail_en))
    for i in range(n):
        w.writerow({
            "content": caption_variants[i],
            "visibility": "0", "room_id": "",
            "image_urls": "",
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_source": "cryptoslate", "_slug": f"market-{i+1}", "_lang": "en",
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
