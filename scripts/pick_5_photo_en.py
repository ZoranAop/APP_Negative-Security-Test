import csv,re,random,os
random.seed(42)
rows=list(csv.DictReader(open('pre_企管用户_街拍摄影师.csv',encoding='utf-8-sig')))
en=[r for r in rows if re.match(r'^[A-Za-z]+[A-Za-z0-9]*$',r.get('昵称',''))]
pick=random.sample(en,5)
for r in pick:
    print(f"{r['昵称']:20} {r['邮箱']} {r['密码']}")
run_dir = os.path.join(os.getcwd(), 'photo_pick_run')
os.makedirs(run_dir, exist_ok=True)
out_path = os.path.join(run_dir, 'accounts_photo_pick.csv')
with open(out_path,'w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=['序号','昵称','邮箱','密码'])
    w.writeheader()
    for r in pick:
        w.writerow({'序号':r['序号'],'昵称':r['昵称'],'邮箱':r['邮箱'],'密码':r['密码']})
print(f'written {out_path}')
