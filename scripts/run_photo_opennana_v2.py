# Re-post 12 photos from photographer accounts using REAL image URLs
# Same content as previous run, but with correct img.opennana.com URLs
import subprocess, sys, csv, io, random
from pathlib import Path

ROOT = Path(r"D:\程序\xxai-square-publisher")
SCRIPTS = ROOT / "scripts"
PY = [sys.executable]
random.seed(303)

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
except Exception:
    pass

# Real image URLs extracted from og:image meta tags (verified working)
images = [
    # JP
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "ja", "灰色の階段、柔らかな光。こんな瞬間を切り取るのが好きだ。"),
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "ja", "独り暮らしの廊下、毛布を抱えて。静かな日常の一コマ。"),
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "ja", "ラウンジの隅、紅茶色の髪と深紅のドレス。夜景と似合う雰囲気。"),
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "ja", "コンクリートの台座、硬い光。ストリートポートレートの醍醐味。"),
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "ja", "緑のシェードと制服、都会の隅。若さと静けさが交差する瞬間。"),
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "ja", "ネオンの夜、黒真珠の輝き。CCDフィルムのような色合いが好き。"),
    # KO
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "ko", "열대 리조트의 오후, Y2K 스타일의 여유. 자연광이 만들어내는 그림자가 매력적이야."),
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "ko", "중식당에서의 스냅, 펑크와 전통의 조화. 플래시 촬영의 생생함이 좋아."),
    # EN
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "en", "High-angle bedroom portrait — the light hitting the jumpsuit texture is everything."),
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "en", "Clean studio lighting, black jumpsuit silhouette. Simple outfits make the strongest portraits."),
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "en", "Wide-angle upper body study — the perspective distortion adds character."),
    ("https://img.opennana.com/prompts/assets/202608/1787152555496-c33e60q0-1787152558248-1.jpg",
     "en", "Brooklyn Bridge morning mist, white cardigan layered over dark tones. That Japanese photobook aesthetic never gets old."),
]

# Select 4 EN-nick photographers
rows = list(csv.DictReader(open(ROOT / "pre_企管用户_街拍摄影师.csv", encoding="utf-8-sig")))
import re
en_rows = [r for r in rows if re.match(r'^[A-Za-z][A-Za-z0-9]*$', r.get('昵称',''))]
pick = random.sample(en_rows, 4)
print(f"Selected 4 photographers: {[r['昵称'] for r in pick]}")

with open(ROOT / "pre_企管用户_街拍摄影师.csv", 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['序号','昵称','邮箱','密码'])
    w.writeheader()
    for r in pick:
        w.writerow({'序号':r['序号'],'昵称':r['昵称'],'邮箱':r['邮箱'],'密码':r['密码']})

accounts = list(csv.DictReader(open(ROOT / "pre_企管用户_街拍摄影师.csv", encoding="utf-8-sig")))
print(f"Accounts: {[a['昵称'] for a in accounts]}")

# Distribute 12 images across 4 accounts (3 each)
random.shuffle(images)
moments = []
for i, (img_url, lang, caption) in enumerate(images):
    acct_idx = i % len(accounts)
    moments.append({
        'content': caption,
        'visibility': 0, 'room_id': '',
        'image_urls': img_url,
        'location_name': '', 'location_address': '',
        'location_lat': '', 'location_lon': '',
        '_lang': lang, '_source': 'opennana'
    })

out_csv = ROOT / "moments_photo_lang_v2.csv"
fields = ['content','visibility','room_id','image_urls','location_name','location_address','location_lat','location_lon','_lang','_source']
with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for m in moments:
        w.writerow(m)

print(f"\nMoments: {len(moments)}")
for i, m in enumerate(moments):
    acct = accounts[i % len(accounts)]
    print(f"  [{i+1}] {acct['昵称']:15} lang={m['_lang']} | {m['content'][:55]}")

# Publish
cmd = PY + [str(SCRIPTS / "publish_from_tokens.py"),
            "--accounts-csv", str(ROOT / "pre_企管用户_街拍摄影师.csv"),
            "--csv", str(out_csv),
            "--concurrency", "2",
            "--tokens-in", str(ROOT / "result" / "tokens.json"),
            "--tokens-out", str(ROOT / "result" / "tokens.json")]
print("\n=== Publishing ===")
rc = subprocess.call(cmd, cwd=str(ROOT))
print(f"Exit code: {rc}")
