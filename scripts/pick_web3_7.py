import csv, re, random, os
random.seed(77)
rows = list(csv.DictReader(open('accounts_web3_100.csv', encoding='utf-8-sig')))
en = [r for r in rows if re.match(r'^[A-Za-z][A-Za-z0-9]*$', r.get('昵称', ''))]
zh = [r for r in rows if any('\u4e00' <= c <= '\u9fff' for c in r.get('昵称', ''))]
print(f'Total EN: {len(en)}, ZH: {len(zh)}')
pick_en = random.sample(en, 5)
pick_zh = random.sample(zh, 2)
for r in pick_en:
    print(f"EN   {r['昵称']:20} {r['邮箱']}")
for r in pick_zh:
    print(f"ZH   {r['昵称']:20} {r['邮箱']}")
run_dir = os.path.join(os.getcwd(), 'web3_pick_run')
os.makedirs(run_dir, exist_ok=True)
out_path = os.path.join(run_dir, 'accounts_web3_7_pick.csv')
with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['序号', '昵称', '邮箱', '密码'])
    w.writeheader()
    for r in pick_en + pick_zh:
        w.writerow({'序号': r['序号'], '昵称': r['昵称'], '邮箱': r['邮箱'], '密码': r['密码']})
print(f'written {out_path}')
