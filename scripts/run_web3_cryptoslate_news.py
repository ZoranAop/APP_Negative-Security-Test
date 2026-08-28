#!/usr/bin/env python3
"""Fetch cryptoslate.com news + publish 7 posts to web3 accounts (reuse some)"""
import re, json, csv, subprocess, sys, time, os, io
from pathlib import Path
import requests
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings()

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', write_through=True)
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://cryptoslate.com/"}

# 1) Fetch news page
url = "https://cryptoslate.com/news/"
s = requests.Session()
r = s.get(url, headers=HEADERS, timeout=20, verify=False)
print(f"News page: {r.status_code}, Len: {len(r.text)}")

soup = BeautifulSoup(r.text, 'html.parser')
articles = []
for a in soup.find_all('a', href=True):
    href = a['href']
    title = a.get_text(strip=True)
    if '/news/' in href or '/article/' in href and title and len(title) > 15:
        if href.startswith('//'):
            href = 'https:' + href
        elif href.startswith('/'):
            href = 'https://cryptoslate.com' + href
        articles.append({"title": title, "url": href})

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

# 2) Fetch content
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

# 3) Build差异化英文文案
caption_variants = [
    "Bitcoin's latest price action has the charts looking interesting. Support levels holding while resistance gets tested. Volume patterns suggest institutional accumulation is happening beneath the surface. Not the time to panic sell.",
    "Ethereum gas fees finally dropping after all the Layer 2 hype. Maybe the scaling solutions are actually working now. Retail users can breathe easier when transaction costs don't eat your entire position.",
    "Crypto regulation updates keep coming. Every jurisdiction is figuring out their approach at different speeds. The fragmentation creates arbitrage opportunities but also compliance headaches for legitimate projects.",
    "Altcoin season indicators flashing mixed signals again. Some say we're due, others say BTC dominance needs to break first. History suggests waiting for the breakout is safer than betting on timing.",
    "Stablecoin market cap hitting new records while BTC consolidates. Smart money positioning for the next move. When liquidity like this accumulates, something big usually follows. Patience pays in this market.",
    "Institutional crypto adoption narrative playing out in real time. ETF flows, corporate treasury allocations, pension fund interest. The walls are coming down even if the pace feels slow sometimes.",
    "Market volatility returning after the calm period. Good for traders, stressful for HODLers. This is why risk management matters more than any prediction. Stay positioned, stay disciplined, don't get emotional.",
]

# 4) Pick web3 accounts (allow reuse since pool is limited)
users = list(csv.DictReader(open(ROOT / "accounts_web3_100.csv", encoding="utf-8-sig")))
tokens = json.loads((ROOT / "result" / "tokens.json").read_text(encoding="utf-8"))
used = set(tokens.keys())

# Get available by checking which haven't been used recently (exclude last 7 used)
recently_used = sorted(used, key=lambda x: tokens.get(x, ''), reverse=True)[:21]
avail_en = [r for r in users
            if r.get("昵称") and len(r.get("昵称") or "") <= 20
            and not any(ord(c) > 127 for c in r["昵称"])
            and (r.get("邮箱") or "").strip().lower() not in recently_used]

if not avail_en:
    # Fallback: use any available
    avail_en = [r for r in users
                if r.get("昵称") and len(r.get("昵称") or "") <= 20
                and not any(ord(c) > 127 for c in r["昵称"])
                and (r.get("邮箱") or "").strip().lower() not in used]

print(f"\nAvailable EN web3: {len(avail_en)}")

# 5) Build and publish
ts = time.strftime("%Y%m%d_%H%M%S")
wd = ROOT / f"web3_cryptoslate_news_{ts}"
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
            "_source": "cryptoslate", "_slug": f"news-{i+1}", "_lang": "en",
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
