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
# zh_hant = traditional Chinese
POSTS = [
    ("chinese-woman-washing-pink-scooter-with-maltipoo-cinematic", "en",
     "There is a quiet joy in watching someone care for their scooter like it is a living thing. The pink paint, the maltipoo curled at her feet, the cinematic framing — it feels like a frame pulled straight from an indie film about ordinary afternoons."),
    ("realistic-east-asian-woman-bedroom-knitwear-pantyhose-portrait", "en",
     "Bedroom portraits have this intimate honesty that studio work can never replicate. The knit texture, the soft pantyhose sheen, the natural window light — everything about this shot speaks to the comfort of being alone in your own space."),
    ("realistic-east-asian-woman-bedroom-knitwear-pantyhose-portrait", "en",
     "Another look at this same scene from a different angle — the bedroom light catches the knitwear differently, and the mood shifts just enough to feel like a new story. Same room, same girl, a different breath."),
    ("midsummer-night-camp-tent-quadruped-pose", "en",
     "Midsummer nights and camping gear — there is something primal about shooting in tents. The constrained space forces creative angles, and that quadruped pose adds a playful energy that breaks the usual portrait formula."),
    ("adult-korean-woman-voluptuous-upper-body-close-up", "en",
     "Close-up portraiture is all about the eyes and the light. This one nails both — the Korean beauty standard meets honest, unretouched skin texture. The upper-body framing keeps everything focused on expression."),
    ("seoul-university-campus-cherry-blossom-fujifilm-portrait", "ja",
     "ソウル大学の桜、フジフィルムの色彩が素晴らしい。春の campus ライフを切り取った一枚。"),
    ("japanese-women-hotel-snapshot-maid-catgirl-qipao", "ja",
     "ホテルのスナップ、メイドと猫耳とqipaoの組み合わせが面白い。コスプレ写真だけど、自然な瞬間切り取りが魅力。"),
    ("ccd-lifestyle-out-of-focus-lace-lingerie-east-asian-beauty-sofa", "en",
     "Lace against a soft sofa, out-of-focus bokeh wrapping around an East Asian silhouette — this is the kind of lifestyle portrait that makes you slow down and look twice. The CCD color grading adds that nostalgic warmth."),
    ("dark-oriental-mysterious-female-character-photography", "en",
     "Mystery in monochrome. The dark oriental aesthetic here is bold but restrained — shadows do most of the storytelling while the subject stays just visible enough to keep you wondering."),
    ("seoul-han-river-winter-japanese-korean-portrait", "en",
     "Han River in winter, Japanese and Korean features blended in a single frame. The cold light, the river reflection, the layered clothing — it is a portrait that feels like a season rather than a person."),
    ("adult-japanese-woman-teal-cardigan-airplane-seat", "en",
     "Airplane seat portraits are underrated. The confined space, the teal cardigan against airline upholstery, the tired-but-composed expression — this is travel photography at its most honest."),
    ("luxury-poolside-summer-portrait-1787237518145", "en",
     "Poolside luxury captured with natural summer light. The composition leans into horizontals — the waterline, the lounge chair, the horizon — creating a sense of endless lazy afternoon."),
    ("pov-indoor-night-japanese-woman-snapshot", "zh_hant",
     "夜間的室內 snapshots 總是有一種特别的氛圍。柔和的燈光和隨意擺放的物品，讓這張照片看起來像是一段記憶的一部分。"),
    ("cool-white-skin-taiwanese-girl-duck-pout-selfie", "zh_hant",
     "台灣女孩的自拍有一種天然的可愛，duck pout 表情配上白皙肌膚，整個畫面充滿青春活力。這是那種讓人一看就心情變好的照片。"),
    ("light-blue-bikini-low-angle-sky-view", "en",
     "Low-angle sky views are my favorite composition exercise. The light blue bikini against an open sky creates this clean, minimalist palette that feels like summer itself captured in a single frame."),
    ("candid-summer-beach-changing-into-swimwear-japanese-woman", "en",
     "Candid beach moments are where photography feels most alive. The act of changing into swimwear, caught off-guard in golden hour light — it is natural, unposed, and quietly beautiful."),
    ("japanese-woman-park-path-cropped-white-shirt-polka-dot-skirt", "ja",
     "公園の小道、白シャツとドットスカートの組み合わせが春夏らしい。自然光の中の日常ポートレート、好きです。"),
    ("ancient-style-realistic-korean-woman-hanfu-portrait", "en",
     "Hanfu portraiture with a realistic twist — the ancient Korean aesthetic meets modern photographic honesty. The fabric textures, the composed posture, the subtle colors all come together to create something timeless."),
    ("retro-ccd-black-suv-street-portrait", "zh_hant",
     "街頭隨拍的一種質感，黑色 SUV 的背景讓整張照片更有都市感。柔和的光線和自然的構圖，呈現出城市生活中的靜謐時刻。"),
    ("luxury-hotel-mirror-loose-bathrobe-selfie", "en",
     "Mirror selfies in luxury hotel rooms have this effortless chic quality. The loose bathrobe, the reflection play, the hotel lighting — it is the kind of image that says more by saying less."),
    ("woman-browsing-pleasure-products-side-view", "en",
     "Side-view compositions add narrative depth. The browsing gesture, the product display, the natural stance — it feels like a documentary frame more than a posed portrait. Everyday moments are worth photographing."),
    ("realistic-vertical-portrait-woman-styling-hair-by-window", "en",
     "Hair-styling by the window — there is something universally relatable about this. The vertical frame captures the full gesture, the natural light from the side, and the quiet focus of a personal grooming moment."),
    ("bright-pink-v-string-swimsuit-product-photography", "en",
     "Product photography with a human element. The bright pink V-string against a clean background is bold, but the realistic lighting keeps it grounded. Fashion and commerce meeting in a single frame."),
    ("seaside-bikini-woman-peace-gesture-realistic-photography", "en",
     "Peace gesture at the seaside — simple, joyful, and absolutely authentic. The realistic photography style means no heavy retouching, just natural light, real texture, and a genuine smile. That is what makes seaside portraits work."),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="photographer_opennana_23_run")
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

    # Select fresh EN-nick photographer accounts
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
            "_dedupe_key": f"onana_pho23_{slug}_{i}",
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

    dedupe_file = ROOT / "state" / "seen_photographer_opennana_23.json"
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
