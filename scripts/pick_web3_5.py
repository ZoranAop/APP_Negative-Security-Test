import csv, re, random
random.seed(99)
rows = list(csv.DictReader(open('accounts_web3_100.csv', encoding='utf-8-sig')))
print(f"Total: {len(rows)}")
en_nicks, zh_nicks = [], []
for r in rows:
    nick = r.get('昵称', '')
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in nick)
    has_latin = any('a' <= c.lower() <= 'z' for c in nick)
    if has_latin and not has_cjk:
        en_nicks.append(r)
    elif has_cjk:
        zh_nicks.append(r)
print(f"EN nicks: {len(en_nicks)}, ZH nicks: {len(zh_nicks)}")
pick_en = random.sample(en_nicks, 3)
pick_zh = random.sample(zh_nicks, 2)
pick = pick_en + pick_zh
random.shuffle(pick)
for r in pick:
    print(f"{r['昵称']:25} {r['邮箱']}")
# Write to run directory instead of root
import os
run_dir = os.path.join(os.getcwd(), 'web3_pick_run')
os.makedirs(run_dir, exist_ok=True)
out_path = os.path.join(run_dir, 'accounts_web3_5_pick.csv')
with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['序号','昵称','邮箱','密码'])
    w.writeheader()
    for r in pick:
        w.writerow({'序号':r['序号'],'昵称':r['昵称'],'邮箱':r['邮箱'],'密码':r['密码']})
print(f"written {out_path}")
