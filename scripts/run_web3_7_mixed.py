# Run web3 news: 7 accounts
# - 5 EN-nick accounts -> English captions
# - 2 ZH-nick accounts -> Russian captions (forced --lang ru)
# Each account posts 1-2 random posts, all unique content and tone.
import subprocess, sys, csv, random
from pathlib import Path

ROOT = Path(r"D:\程序\xxai-square-publisher")
SCRIPTS = ROOT / "scripts"
PY = [sys.executable]
random.seed(202)

accounts = list(csv.DictReader(open(ROOT / "accounts_web3_100.csv", encoding="utf-8-sig")))

# Determine lang per account based on nick
def lang_for_nick(nick):
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in nick)
    has_latin = any('a' <= c.lower() <= 'z' for c in nick)
    if has_cjk:
        return "ru"  # Use RU captions for ZH-nick accounts
    if has_latin:
        return "en"
    return "en"

for a in accounts:
    a['_lang'] = lang_for_nick(a.get('昵称', ''))
    print(f"  {a['昵称']:20} -> {a['_lang']}")

# Step 1: fetch
cmd = PY + [str(SCRIPTS / "fetch_web3.py"),
            "--sources", "techflow,foresight,menews,panews,bingx,blockweeks,theblock,decrypt,beincrypto,e27",
            "--per-site", "4",
            "--tag", "web3",
            "--output", str(ROOT / "web3_run" / "web3_raw_7b.csv")]
print("\nStep1 fetch:", " ".join(str(c) for c in cmd))
rc = subprocess.call(cmd, cwd=str(ROOT))
if rc != 0:
    print("[ERROR] fetch failed"); sys.exit(1)

rows = list(csv.DictReader(open(ROOT / "web3_run" / "web3_raw_7b.csv", encoding="utf-8-sig")))
print(f"Raw news: {len(rows)} items")

# Step 2: generate EN captions (for EN-nick accounts)
cmd_en = PY + [str(SCRIPTS / "web3_caption_by_role.py"),
               "--input", str(ROOT / "web3_run" / "web3_raw_7b.csv"),
               "--output", str(ROOT / "web3_run" / "moments_en2.csv"),
               "--accounts-csv", str(ROOT / "accounts_web3_100.csv"),
               "--lang", "en",
               "--min-len", "0", "--max-len", "280",
               "--tone", "neutral"]
print("Step2 caption en:", " ".join(str(c) for c in cmd_en))
subprocess.call(cmd_en, cwd=str(ROOT))

# Step 3: generate RU captions (for ZH-nick accounts)
cmd_ru = PY + [str(SCRIPTS / "web3_caption_by_role.py"),
               "--input", str(ROOT / "web3_run" / "web3_raw_7b.csv"),
               "--output", str(ROOT / "web3_run" / "moments_ru2.csv"),
               "--accounts-csv", str(ROOT / "accounts_web3_100.csv"),
               "--lang", "ru",
               "--min-len", "0", "--max-len", "280",
               "--tone", "neutral"]
print("Step3 caption ru:", " ".join(str(c) for c in cmd_ru))
subprocess.call(cmd_ru, cwd=str(ROOT))

rows_en = list(csv.DictReader(open(ROOT / "web3_run" / "moments_en2.csv", encoding="utf-8-sig")))
rows_ru = list(csv.DictReader(open(ROOT / "web3_run" / "moments_ru2.csv", encoding="utf-8-sig")))
print(f"EN captions: {len(rows_en)}, RU captions: {len(rows_ru)}")

# Step 4: assign 1-2 posts per account
posts_per_acc = [random.choice([1, 2]) for _ in range(len(accounts))]
total_needed = sum(posts_per_acc)
print(f"Posts per acc: {posts_per_acc}, total: {total_needed}")

# Build per-language pools (separate to avoid cross-contamination)
en_pool = rows_en[:]; ru_pool = rows_ru[:]
random.shuffle(en_pool)
random.shuffle(ru_pool)

final_rows = []
for i, acct in enumerate(accounts):
    n = posts_per_acc[i]
    target_lang = acct['_lang']
    pool = ru_pool if target_lang == "ru" else en_pool
    for j in range(n):
        if pool:
            row = pool.pop(0)
            row['_lang'] = target_lang
            row['_role_nick'] = acct.get('昵称', '')
            final_rows.append(row)

fields = list(final_rows[0].keys()) if final_rows else []
out_path = ROOT / "web3_run" / "moments_7b_final.csv"
with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in final_rows:
        w.writerow(r)

print(f"\nFinal: {len(final_rows)} posts")
for i, acct in enumerate(accounts):
    nick = (acct.get('昵称') or '')[:15]
    start = sum(posts_per_acc[:i])
    end = start + posts_per_acc[i]
    for k in range(start, min(end, len(final_rows))):
        content = str(final_rows[k].get('content', ''))[:65]
        lang = final_rows[k].get('_lang', '?')
        print(f"  [{i+1}] {nick:15} lang={lang} | {content}")

# Step 5: publish
cmd_pub = PY + [str(SCRIPTS / "publish_from_tokens.py"),
                "--accounts-csv", str(ROOT / "accounts_web3_100.csv"),
                "--csv", str(out_path),
                "--concurrency", "2",
                "--tokens-in", str(ROOT / "result" / "tokens.json"),
                "--tokens-out", str(ROOT / "result" / "tokens.json")]
print("\nStep5 publish:", " ".join(str(c) for c in cmd_pub))
rc = subprocess.call(cmd_pub, cwd=str(ROOT))
print(f"Exit code: {rc}")
