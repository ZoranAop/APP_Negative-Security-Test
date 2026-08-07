"""Fetch turismo images and create publish-ready CSVs."""
import csv, re, time, requests
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

COLUMNS = ["cosplay"]
BASE = "https://www.turismo.cc"

def _get(url, ref):
    r = requests.get(url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": ref})
    r.raise_for_status()
    return r.text

images = []
seen_slugs = set()
for col in COLUMNS:
    try:
        txt = _get(f"{BASE}/{col}/", f"{BASE}/")
        slugs = re.findall(r'href="/([A-Za-z0-9]{5,8})\.html"', txt)
        for slug in slugs[:3]:
            if slug in seen_slugs: continue
            seen_slugs.add(slug)
            try:
                detail = _get(f"{BASE}/{slug}.html", f"{BASE}/")
                i = detail.find('id="post_content"')
                if i < 0: continue
                end = detail.find('class="related', i)
                if end < 0: end = detail.find('id="footer"', i)
                seg = detail[i: end if end > 0 else len(detail)]
                urls = re.findall(r'(?:data-original|src)="(//img\.youwushow\.top/[^"]+\.(?:jpg|jpeg|png|webp))"', seg, re.I)
                for u in urls:
                    full = "https:" + u
                    if "/dy_img_" not in full and full not in [im for im in images]:
                        images.append(full)
                        print(f"  + [{len(images)}] {col}: {full[:70]}...")
                        break
            except Exception as e:
                print(f"  warn {slug}: {e}")
            if len(images) >= 5:
                break
        if len(images) >= 5:
            break
    except Exception as e:
        print(f"  err {col}: {e}")

print(f"\nGot {len(images)} images")

# Accounts (5 Chinese users, no 星/月, from 1720)
accts = [
    ("李晚霞", "u_dal8fpft@xxai.com", "MeLGdghdbE6d"),
    ("赵流年", "u_3xpisunq@xxai.com", "HWYrLF51NRnZ"),
    ("范竹风", "u_ayvyepx7@xxai.com", "KBvSUWuMazdA"),
    ("万初晴", "u_10g69xve@xxai.com", "NYf1S3rKii1E"),
    ("邓清风", "u_2d0ypcd1@xxai.com", "SWHqUm29nvki"),
]
with open(ROOT / "accounts_turismo_5.csv", "w", encoding="utf-8-sig", newline="") as f:
    f.write("序号,昵称,邮箱,密码\n")
    for i, (n, e, p) in enumerate(accts, 1):
        f.write(f"{i},{n},{e},{p}\n")

# Moments (Traditional Chinese, each with one image)
captions = [
    "下午的陽光穿過行道樹，灑在人行道上剛剛好。路過的人都成了我的模特，按下快門的那一刻，時間好像停住了。📷 #街拍 #午後光影 #城市漫步",
    "鬧市區的十字路口是最佳觀景台，每個擦肩而過的人都有自己的故事。今天運氣不錯，捕捉到一個完美的回眸瞬間。✨ #街拍日常 #都市寫真 #隨手拍",
    "咖啡店的落地窗倒映著街景，裡面的客人和外面的行人重疊在一起，像一幅流動的畫。這種構圖可遇不可求。☕ #街拍攝影 #城市角落 #生活美學",
    "傍晚的商業街開始熱鬧起來，霓虹燈一盞盞亮起。站在天橋上往下看，車流和人群交織成這座城市最真實的脈搏。🌆 #暮色街拍 #城市夜景 #街頭風格",
    "一整天的拍攝結束了，翻看記憶卡裡的畫面，最喜歡的還是那張不經意拍到的背影。有時候最好的照片，就是最自然的那一瞬間。📸 #街拍日記 #城市隨筆 #記錄生活",
]

fields = ["content", "visibility", "room_id", "image_urls",
          "location_name", "location_address", "location_lat", "location_lon",
          "_source", "_lang", "_scene"]
with open(ROOT / "turismo_moments.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for i in range(min(5, len(images))):
        w.writerow({
            "content": captions[i], "visibility": "0", "room_id": "",
            "image_urls": images[i],
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_source": f"turismo_{COLUMNS[i] if i < len(COLUMNS) else 'other'}",
            "_lang": "zh_hant", "_scene": "street",
        })

print(f"Accounts: {[a[0] for a in accts]}")
print("Done. Run: py -3 scripts/publish_from_tokens.py --accounts-csv accounts_turismo_5.csv --csv turismo_moments.csv")
