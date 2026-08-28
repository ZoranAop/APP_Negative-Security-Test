#!/usr/bin/env python3
"""
Publish a batch of opennana images using fresh English-nickname photographer accounts.
Languages: en / ja / zh_hant as specified per item.
"""
import argparse, csv, io, json, os, random, re, subprocess, sys, time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

sys.path.insert(0, str(HERE))
from opennana_api import fetch_opennana_image
from account_pool import pick_photographer_accounts

# (slug, lang, caption)
POSTS = [
    ("izakaya-pov-food-stealing-snapshot", "en",
     "Izakaya POV food-stealing snapshots capture this specific joy that restaurant photography often misses. The first-person perspective, the steam rising from shared dishes, the slight blur of motion — it feels like you are actually sitting at that tiny wooden counter surrounded by friends."),
    ("y2k-japanese-woman-hotel-hallway-low-angle-photo", "ja",
     "ホテルホールの低アングル、Y2K日本の女性。廊下の照明と反射する床、幻想的な雰囲気が好き。"),
    ("20s-seductive-japanese-korean-woman-tokyo-tower-portrait", "ja",
     "東京タワーを背景にした20代韓国日本女性。近未来的な街並みと伝統的な美の融合が素晴らしい一枚。"),
    ("japanese-woman-leaning-down-outdoor-stairs-smartphone-style", "ja",
     "屋外の階段で前傾ポーズ、スマートフォン撮影風。日常の瞬間を切り取ったような自然さが魅力。"),
    ("realistic-east-asian-woman-black-halter-top-portrait", "en",
     "Black halter tops on East Asian subjects create this striking contrast that photographs beautifully. The realistic rendering here honors the subject's natural features rather than over-processing them into something generic."),
    ("ultra-realistic-smartphone-selfie-east-asian-woman-stairwell", "en",
     "Stairwell selfies are an underappreciated genre. The geometric lines, the acoustic reflections, the way natural light filters down from above — it turns an ordinary architectural space into a compelling portrait setting."),
    ("rooftop-terrace-double-v-sign-sunny-girl", "en",
     "Rooftop terrace double V-signs on sunny days — this is summer photography in its most unguarded form. The sky blue, the casual pose, the genuine smile — it all combines into an image that radiates pure joy without trying too hard."),
    ("iphone-shot-warm-bedroom-silk-nightgown-asian-woman-tipsy-vibe", "en",
     "iPhone bedroom shots in silk nightgowns with a tipsy vibe — there is something intoxicating about images that feel this intimate. The warm lighting, the luxurious fabric texture, the slightly blurred edges from a casual hand hold — it all contributes to this sense of stolen late-night moments."),
    ("japanese-woman-poolside-denim-overalls-iphone-photography", "en",
     "Denim overalls by the pool with Japanese subjects — the unexpected combination of casual workwear and swimside relaxation creates visual interest. The iPhone photography aesthetic keeps it grounded and immediate rather than polished and distant."),
    ("korean-late-night-video-call-webcam-style", "en",
     "Late-night video call aesthetics in Korean portraiture — the blue screen glow, the messy hair, the half-present expression. This webcam realism captures a distinctly contemporary form of intimacy that traditional photography struggles to replicate."),
    ("japanese-woman-leaning-forward-car-interior-snapshot", "en",
     "Car interior snapshots with Japanese subjects leaning forward — the confined space forces creative composition, and the reflected dashboard lights add this cinematic quality that outdoor shoots rarely achieve."),
    ("late-night-reading-woman", "en",
     "Late-night reading portraits have this quiet intensity that daytime equivalents lack. The single lamp, the open book, the slight squint against the dim light — it is a moment of genuine intellectual intimacy that photographs beautifully when caught honestly."),
    ("floral-lace-dress-dim-doorway-low-angle", "en",
     "Floral lace dresses in dim doorways with low-angle composition — the interplay of shadow and delicate pattern creates visual richness. The low angle adds a sculptural quality to the subject while the dim lighting preserves mystery."),
    ("lingerie-store-fitting-room-japanese-woman", "ja",
     "下着店の試着室、日本女性のポートレート。鏡越しの視点と柔らかな照明、プライベートな瞬間を切り取ったような雰囲気。"),
    ("outdoor-casual-street-fashion-smartphone-snapshot", "en",
     "Casual street fashion smartphone snapshots — the beauty of this genre lies in its accessibility. Anyone with a phone can capture these moments, which means the best ones feel genuinely discovered rather than meticulously staged."),
    ("ultra-realistic-night-hotel-cat-ear-girl-selfie", "en",
     "Night hotel cat-ear selfies in ultra-realistic style — the artificial lighting, the playful accessory, the candid expression. It is a juxtaposition of manufactured environment and genuine personality that defines contemporary self-portraiture."),
    ("ultra-realistic-indoor-woman-selfie-vintage-film", "en",
     "Vintage film aesthetics in indoor selfie photography — the grain, the color shift, the slight imperfections. Ultra-realistic rendering here means honoring the medium's limitations rather than correcting them, creating images that feel warm and aged without losing clarity."),
    ("south-korean-woman-convenience-store-y2k-smartphone-photo", "en",
     "Convenience store Y2K photography with Korean women — those fluorescent-lit, neon-signed spaces are among the most visually rich environments in East Asia. The smartphone aesthetic keeps it immediate and personal rather than documentary."),
    ("realistic-bedroom-close-up-portrait-flash-photography", "en",
     "Bedroom close-ups with flash photography — the harsh direct light, the slightly blown highlights, the intimate proximity. Realistic rendering here means preserving the raw quality of flash rather than softening it into something more conventional."),
    ("hyper-realistic-indoor-gaming-room-lifestyle-portrait", "zh_hant",
     "遊戲室的室內生活寫真，超寫實風格呈現出當代年輕人的日常空間。螢幕光線、收納架上的手辦、舒適的座椅，每一個細節都充滿生活感。"),
    ("japanese-woman-hotel-bedside-close-up-selfie", "zh_hant",
     "飯店床頭櫃旁的特寫自拍，日本女性的溫柔氛圍。柔和的夜燈和慵懶的神情，讓這張照片散發著睡前獨处的寧靜感。"),
    ("dinner-with-rabbit-and-lamps-realistic-portrait", "en",
     "Dinner portraits featuring rabbits and lamps — the surreal combination of living creature, household object, and human subject creates a narrative richness that straightforward portraiture cannot match. The realistic rendering grounds the whimsy in tangible reality."),
    ("1990s-hong-kong-royal-police-night-snapshot", "en",
     "1990s Hong Kong royal police night snapshots — the period specificity, the neon reflections on wet pavement, the authoritative yet human presence. This is documentary photography that serves as both artistic statement and historical record."),
    ("minimalist-indoor-full-body-mirror-selfie-realistic-woman", "en",
     "Minimalist full-body mirror selfies in indoor settings — the clean lines, the reflective surfaces, the deliberate composition. Realistic rendering here means resisting the urge to over-edit, letting the architecture and the subject speak for themselves through honest light and proportion."),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="photographer_opennana_24_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    (ROOT / "state").mkdir(exist_ok=True)

    print("=== Resolving image URLs ===")
    images = []
    for slug, lang, caption in POSTS:
        try:
            url = fetch_opennana_image(slug)
            images.append((url, lang, caption, slug))
            print(f"  OK   {slug[:55]}")
        except Exception as e:
            print(f"  FAIL {slug}: {e}")

    print(f"\nResolved {len(images)}/{len(POSTS)} images")
    if len(images) < 3:
        print("[ERROR] Not enough images resolved")
        return 1

    accounts = pick_photographer_accounts(len(images))
    print(f"[accounts] {len(accounts)} users: {[a['昵称'] for a in accounts]}")

    moments = []
    for i in range(min(len(images), len(accounts))):
        url, lang, caption, slug = images[i]
        moments.append({
            "content": caption,
            "visibility": "0",
            "room_id": "",
            "image_urls": url,
            "location_name": "",
            "location_address": "",
            "location_lat": "",
            "location_lon": "",
            "_lang": lang,
            "_source": "opennana",
            "_dedupe_key": f"onana_pho24_{slug}_{i}",
        })

    moments_csv = wd / f"moments_photographer_opennana_{ts}.csv"
    fields = ["content","visibility","room_id","image_urls","location_name","location_address","location_lat","location_lon","_lang","_source","_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow(m)

    lang_count = {}
    for m in moments:
        lang_count[m["_lang"]] = lang_count.get(m["_lang"], 0) + 1
    print(f"\n[OK] {len(moments)} posts ready")
    print(f"[OK] lang dist: {lang_count}")
    for i, m in enumerate(moments):
        acct = accounts[i] if i < len(accounts) else {"昵称": "?"}
        preview = m["content"][:65].replace("\n", " ")
        print(f"  [{i+1:2d}] {acct['昵称']:20} lang={m['_lang']} | {preview}...")

    if args.skip_publish:
        print(f"\n--skip-publish. Content at: {moments_csv}")
        return 0

    if not args.yes:
        if input("\nConfirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    dedupe_file = ROOT / "state" / "seen_photographer_opennana_24.json"
    used = set()
    if dedupe_file.exists():
        try:
            used = set(json.loads(dedupe_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    new_keys = {m["_dedupe_key"] for m in moments}
    dedupe_file.write_text(json.dumps(sorted(used | new_keys), ensure_ascii=False), encoding="utf-8")

    merged_acc = wd / f"accounts_merged_{ts}.csv"
    tokens_path = ROOT / args.tokens
    tokens_path.parent.mkdir(parents=True, exist_ok=True)
    with merged_acc.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号","昵称","邮箱","密码"])
        w.writeheader()
        for a in accounts[:len(moments)]:
            w.writerow({"序号": a.get("序号",""), "昵称": a["昵称"],
                        "邮箱": a["邮箱"], "密码": a.get("密码","")})

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(merged_acc),
                "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "2.0",
                "--record-dedupe",
                "--web3-dedupe-file", str(dedupe_file),
                "--img-dedupe-file", str(ROOT / "data" / "used_slugs.json"),
                "--tokens-out", str(tokens_path)]
    if tokens_path.exists():
        cmd += ["--tokens-in", str(tokens_path)]

    print(f"\n=== publishing {len(moments)} posts ===")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    print(f"Exit code: {rc}")
    return rc

if __name__ == "__main__":
    sys.exit(main())
