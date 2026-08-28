#!/usr/bin/env python3
"""Fetch wublockchain.xyz circle tag + publish 7 posts to web3 accounts"""
import re, json, csv, subprocess, sys, time, os, io
from pathlib import Path
import requests

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', write_through=True)
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://www.wublockchain.xyz/"}

# 1) Fetch tag page
url = "https://www.wublockchain.xyz/tag/circle"
s = requests.Session()
r = s.get(url, headers=HEADERS, timeout=20)
print(f"Tag page: {r.status_code}, Len: {len(r.text)}")

# Extract articles from HTML
articles = []
# Look for article links
for href_m in re.finditer(r'href="(https://www\.wublockchain\.xyz/[^"]+)"', r.text):
    href = href_m.group(1)
    if '/article/' in href or '/news/' in href or '/post/' in href:
        start = max(0, href_m.start() - 300)
        ctx = r.text[start:href_m.start()]
        title_m = re.search(r'>([^<]{8,})<', ctx)
        title = title_m.group(1).strip() if title_m else ""
        if title and len(title) > 5:
            articles.append({"title": title, "url": href})

print(f"\nFound {len(articles)} articles:")
for a in articles[:10]:
    print(f"  {a['title'][:60]} -> {a['url']}")

# 2) Fetch each article content
for a in articles[:10]:
    try:
        r2 = s.get(a["url"], headers=HEADERS, timeout=15)
        body = r2.text
        # Extract text content
        texts = re.findall(r'<[^>]+>([^<]{15,})</[^>]+>', body)
        content = " ".join(t.strip() for t in texts if not t.startswith("{@"))[:500]
        a["content"] = content
        print(f"  Fetched: {a['title'][:40]}")
    except Exception as e:
        a["content"] = ""
        print(f"  ERROR: {a['title'][:40]}: {e}")

# 3) Filter circle-related
circle_kws = ["circle", "usdc", "stablecoin", "cristy", "sei", "blockchain"]
circle_articles = [a for a in articles if any(kw in (a["title"] + " " + a.get("content", "")).lower() for kw in circle_kws)]
print(f"\nCircle-related: {len(circle_articles)}")

# Pick 7
selected = circle_articles[:7] if len(circle_articles) >= 7 else articles[:7]

# 4) Build差异化英文文案（不同语气）
caption_variants = [
    # 1. 感慨式
    "Circle's expansion into multi-chain stablecoins is actually kind of brilliant. USDC on Sei? Finally, someone's making stablecoins useful beyond just trading pairs. The question is whether this momentum can sustain as the market gets more competitive.",
    # 2. 反问式
    "So Circle just dropped another integration and now USDC is everywhere? What's next, on the moon? 🚀 Honestly though, the utility narrative is finally catching up to the hype. Anyone else watching this space closely?",
    # 3. 抱怨式
    "Everyone's talking about Circle's latest moves but nobody's mentioning the regulatory cloud hanging over stablecoins. Sure, USDC is everywhere, but at what cost? Compliance is expensive and it's eating into margins. Hope they can balance this.",
    # 4. 兴奋式
    "Circle x Sei integration is exactly what the DeFi space needed! More chains, more liquidity, more options for yield seekers. This is how you build infrastructure that actually scales. Bullish on stablecoin utility right now.",
    # 5. 冷静分析式
    "Looking at Circle's recent announcements, the pattern is clear: they're building a multi-chain stablecoin backbone. USDC isn't just a token anymore, it's becoming infrastructure. That's a longer-term play than most give credit for.",
    # 6. 怀疑式
    "Another Circle partnership, another chain. Is this differentiation or just sprawl? I get the multi-chain strategy, but are we solving a real problem or just chasing TVL across every L2 that launches? Time will tell.",
    # 7. 实用主义式
    "Circle keeps shipping and honestly that's what matters. While other stablecoin projects are stuck in regulatory limbo, USDC just keeps getting more accessible. Practical utility beats theoretical superiority every time.",
]

# 5) Pick web3 accounts
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

# 6) Build and publish
ts = time.strftime("%Y%m%d_%H%M%S")
wd = ROOT / f"web3_circle_{ts}"
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
            "_source": "wublockchain", "_slug": f"circle-{i+1}", "_lang": "en",
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
