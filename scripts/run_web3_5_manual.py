# Run web3 news: 5 accounts (EN nick -> en, ZH nick -> zh_hant), 1 post each
import subprocess, sys, csv, random
from pathlib import Path

ROOT = Path(r"D:\程序\xxai-square-publisher")
PY = [sys.executable]
SCRIPTS = ROOT / "scripts"

# Step 1: fetch raw news
cmd = PY + [str(SCRIPTS / "fetch_web3.py"),
            "--sources", "techflow,foresight,menews,panews,bingx,blockweeks,wublock",
            "--per-site", "2",
            "--tag", "web3",
            "--output", str(ROOT / "web3_run" / "web3_raw_5.csv")]
print("Step1 fetch:", " ".join(str(c) for c in cmd))
rc = subprocess.call(cmd, cwd=str(ROOT))
if rc != 0:
    print("[ERROR] fetch failed"); sys.exit(1)

# Step 2: caption with auto-nick lang
cmd = PY + [str(SCRIPTS / "web3_caption_by_role.py"),
            "--input", str(ROOT / "web3_run" / "web3_raw_5.csv"),
            "--output", str(ROOT / "web3_run" / "moments_5.csv"),
            "--accounts-csv", str(ROOT / "accounts_web3_100.csv"),
            "--lang", "auto-nick",
            "--min-len", "0", "--max-len", "280",
            "--tone", "neutral"]
print("Step2 caption:", " ".join(str(c) for c in cmd))
rc = subprocess.call(cmd, cwd=str(ROOT))
if rc != 0:
    print("[ERROR] caption failed"); sys.exit(1)

# Step 3: take exactly 5 rows (1 per account, round-robin)
rows = list(csv.DictReader(open(ROOT / "web3_run" / "moments_5.csv", encoding="utf-8-sig")))
accounts = list(csv.DictReader(open(ROOT / "accounts_web3_100.csv", encoding="utf-8-sig")))
n = len(accounts)
picked = [rows[i % len(rows)] for i in range(n)]
with open(ROOT / "web3_run" / "moments_5_final.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(picked[0].keys()))
    w.writeheader()
    for r in picked:
        w.writerow(r)
print(f"Picked {len(picked)} posts (1 per account)")
for i, r in enumerate(picked):
    acct = accounts[i]
    print(f"  [{i+1}] {acct['昵称']:15} lang={r.get('_lang','?')}  {str(r['content'])[:60]}...")

# Step 4: publish
cmd = PY + [str(SCRIPTS / "publish_from_tokens.py"),
            "--accounts-csv", str(ROOT / "accounts_web3_100.csv"),
            "--csv", str(ROOT / "web3_run" / "moments_5_final.csv"),
            "--concurrency", "2",
            "--tokens-in", str(ROOT / "result" / "tokens.json"),
            "--tokens-out", str(ROOT / "result" / "tokens.json")]
print("Step4 publish:", " ".join(str(c) for c in cmd))
rc = subprocess.call(cmd, cwd=str(ROOT))
print(f"Exit code: {rc}")
