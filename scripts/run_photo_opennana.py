# Post from photographer accounts (EN nicks only) using opennana images
# 4 accounts, each posts a mix of JP/KO/EN captions based on image source language
import subprocess, sys, csv, random, time, io, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from opennana_api import fetch_opennana_image  # noqa: E402
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
except Exception:
    pass

ROOT = Path(r"D:\程序\xxai-square-publisher")
SCRIPTS = ROOT / "scripts"
PY = [sys.executable]
random.seed(303)


def _extract_slug(url: str) -> str:
    """Extract slug from any opennana gallery URL."""
    m = re.search(r'gallery/([^/?#]+)', url)
    return m.group(1) if m else url


def _resolve(img_tuple: tuple) -> tuple:
    """(url, lang, caption) -> (resolved_img_url, lang, caption)."""
    url, lang, caption = img_tuple
    if "img.opennana.com" in url:
        return (url, lang, caption)
    slug = _extract_slug(url)
    try:
        real_url = fetch_opennana_image(slug)
        return (real_url, lang, caption)
    except Exception as e:
        print(f"  [WARN] failed to resolve {slug}: {e}", file=sys.stderr)
        return (url, lang, caption)  # fallback to original (will fail at publish)

# Read photographer accounts (EN nick only)
rows = list(csv.DictReader(open(ROOT / "pre_企管用户_街拍摄影师.csv", encoding="utf-8-sig")))
en_rows = [r for r in rows if __import__('re').match(r'^[A-Za-z][A-Za-z0-9]*$', r.get('昵称',''))]
pick = random.sample(en_rows, 4)
print(f"Selected 4 EN-nick photographers: {[r['昵称'] for r in pick]}")

# Image data: (url, lang, caption_text)
_raw_images = [
    # JP
    ("https://opennana.com/awesome-prompt-gallery/realistic-japanese-woman-staircase-portrait", "ja",
     "灰色の階段、柔らかな光。こんな瞬間を切り取るのが好きだ。"),
    ("https://opennana.com/awesome-prompt-gallery/solo-dweller-hallway-carrying-blanket-iphone-photo", "ja",
     "独り暮らしの廊下、毛布を抱えて。静かな日常の一コマ。"),
    ("https://opennana.com/awesome-prompt-gallery/luxury-lounge-seated-portrait-japanese-woman", "ja",
     "ラウンジの隅、紅茶色の髪と深紅のドレス。夜景と似合う雰囲気。"),
    ("https://opennana.com/awesome-prompt-gallery/realistic-9-16-photographed-portrait-woman-pedestal", "ja",
     "コンクリートの台座、硬い光。ストリートポートレートの醍醐味。"),
    ("https://opennana.com/awesome-prompt-gallery/japanese-school-uniform-woman-urban-portrait", "ja",
     "緑のシェードと制服、都会の隅。若さと静けさが交差する瞬間。"),
    ("https://opennana.com/awesome-prompt-gallery/black-pearl-ink-gold-ccd-night-shot-hourglass-female", "ja",
     "ネオンの夜、黒真珠の輝き。CCDフィルムのような色合いが好き。"),
    # KO
    ("https://opennana.com/awesome-prompt-gallery/luxury-tropical-resort-korean-woman-y2k-style", "ko",
     "열대 리조트의 오후, Y2K 스타일의 여유. 자연광이 만들어내는 그림자가 매력적이야."),
    ("https://opennana.com/awesome-prompt-gallery/realistic-korean-woman-pink-leather-corset-qipao-candid-photo", "ko",
     "중식당에서의 스냅, 펑크와 전통의 조화. 플래시 촬영의 생생함이 좋아."),
    ("https://opennana.com/awesome-prompt-gallery/realistic-korean-woman-pink-leather-corset-qipao-candid-photo", "ko",
     "꽃잎 같은 빛, 한국적 감성의 포트레이트. 자연스러운 표현이 핵심이야."),
    # EN
    ("https://opennana.com/awesome-prompt-gallery/photorealistic-high-angle-portrait-east-asian-woman-lounge-jumpsuit", "en",
     "High-angle bedroom portrait — the light hitting the jumpsuit texture is everything. Love these intimate home shots."),
    ("https://opennana.com/awesome-prompt-gallery/east-asian-woman-black-jumpsuit-studio-portrait", "en",
     "Clean studio lighting, black jumpsuit silhouette. Sometimes the simplest outfits make the strongest portraits."),
    ("https://opennana.com/awesome-prompt-gallery/adult-korean-woman-upper-body-wide-angle", "en",
     "Wide-angle upper body study — the perspective distortion adds character. Great composition exercise."),
    ("https://opennana.com/awesome-prompt-gallery/japanese-style-portrait-brooklyn-bridge-woman-white-cardigan", "en",
     "Brooklyn Bridge morning mist, white cardigan layered over dark tones. That Japanese photobook aesthetic never gets old."),
]
# Resolve all gallery URLs to real image URLs
images = [_resolve(img) for img in _raw_images]

# Distribute images across 4 accounts (3 each)
random.shuffle(images)
accounts = list(csv.DictReader(open(ROOT / "pre_企管用户_街拍摄影师.csv", encoding='utf-8-sig')))
n_per_acc = 3
moments = []
for i, acct in enumerate(accounts):
    start = i * n_per_acc
    for j in range(n_per_acc):
        img = images[(start + j) % len(images)]
        moments.append({
            'content': img[2],
            'visibility': 0, 'room_id': '',
            'image_urls': img[0],
            'location_name': '', 'location_address': '',
            'location_lat': '', 'location_lon': '',
            '_lang': img[1], '_source': 'opennana'
        })

out_csv = ROOT / "moments_photo_lang.csv"
fields = ['content','visibility','room_id','image_urls','location_name','location_address','location_lat','location_lon','_lang','_source']
with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for m in moments:
        w.writerow(m)

print(f"\nMoments ready: {len(moments)}")
for i, m in enumerate(moments):
    print(f"  [{i+1}] lang={m['_lang']} | {m['content'][:55]}")

# Publish
cmd = PY + [str(SCRIPTS / "publish_from_tokens.py"),
            "--accounts-csv", str(ROOT / "pre_企管用户_街拍摄影师.csv"),
            "--csv", str(out_csv),
            "--concurrency", "2",
            "--tokens-in", str(ROOT / "result" / "tokens.json"),
            "--tokens-out", str(ROOT / "result" / "tokens.json")]
print("\nPublishing...")
rc = subprocess.call(cmd, cwd=str(ROOT))
print(f"Exit code: {rc}")
