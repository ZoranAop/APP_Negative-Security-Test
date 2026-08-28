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
    ("prompt-1787832920497-o459nm20z", "en",
     "Sometimes the most compelling portraits come from the most unexpected prompts — there is a raw authenticity here that over-planned shoots never achieve. The lighting, the framing, the unguarded moment all converge into something that feels genuinely discovered rather than constructed."),
    ("futuristic-spaceship-cabin-japanese-model-mirror-selfie", "en",
     "Futuristic cabin interiors and mirror selfies — it is a pairing I did not know I needed until now. The Japanese model's composure against that sci-fi backdrop creates this surreal tension between the mundane act of self-portraiture and an alien environment."),
    ("photorealistic-mirror-selfie-modern-dressing-room", "en",
     "Dressing room mirror selfies have this intimate quality that external portraits lack. You are seeing the subject through their own lens, literally and figuratively. The photorealistic rendering here makes every detail — fabric folds, hair strands, the reflection's slight distortion — feel tactile."),
    ("pale-pearl-pink-ruffle-bikini-design", "en",
     "Pearl pink ruffles against bare skin — this is the kind of color palette that photographs beautifully without any post-processing. The design details are intricate but the overall impression is light, airy, and effortlessly feminine."),
    ("minimalist-doodle-city-travel-poster-prompt", "en",
     "Minimalist travel poster aesthetics with a doodle sensibility. There is something charming about reducing a city to its essential lines and letting the negative space tell the story. This approach to visual communication feels both retro and refreshingly modern."),
    ("cozy-bedroom-girl-pink-camisole-selfie", "en",
     "Bedroom selfies in pink camisoles are a genre I could study forever. The coziness of the setting, the casual intimacy of the pose, the soft lighting — it all combines to create images that feel like private moments shared willingly rather than staged performances."),
    ("summer-mountain-river-portrait-japanese-woman-bikini", "en",
     "Mountain river backdrops with summer bikinis — the contrast between rugged natural terrain and soft human forms is endlessly captivating. The Japanese subject here reads as both at peace with and slightly apart from the wild landscape around her."),
    ("japanese-korean-woman-red-bikini-angel-wings-bed-portrait", "ja",
     "赤いビキニと天使の翼、ベッドの上のポートレート。韓国と日本の美しさが融合したような雰囲気が素敵。幻想的でセクシーな組み合わせが好き。"),
    ("squatting-with-bamboo-sword-in-bedroom", "ja",
     "寝室での竹刀持ちスクワットポーズ。日常空間と非日常の要素が交錯する瞬間、こういう矛盾した構図が好みです。"),
    ("post-rain-european-square-japanese-woman-fashion-portrait", "ja",
     "ヨーロッパの広場の雨上がり、日本女性のファッションポートレート。反射する水面と石畳の質感、移民的な美の対比が印象的。"),
    ("ultra-realistic-indoor-bedroom-portrait-y2k-lace-top", "ja",
     "Y2Kレーストップの室内ベッドルームポートレート。超写実的な質感が素晴らしい。2000年代のノスタルジーと現代の写真技術が融合した一枚。"),
    ("japanese-woman-fashion-studio-triptych-prompt", "en",
     "Triptych fashion portraits in studio settings — the three-panel format naturally creates narrative progression. Each frame tells part of a story, and together they form something more complex than any single image could achieve."),
    ("vintage-cartoon-travel-poster-prompt", "zh_hant",
     "復古卡通風格的旅行海報設計，色彩飽和卻不失溫柔。這種插畫與攝影結合的形式，讓人想起舊時報紙的廣告，卻又有現代的清新感。"),
    ("beach-bikini-afternoon-backlight-summer-portrait", "en",
     "Backlit beach portraits in bikinis during afternoon golden hour — this is summer photography in its purest form. The silhouette effect, the warm rim light, the sand texture underfoot — every element conspires to create an image that smells like sunscreen and salt air."),
    ("japanese-woman-white-waffle-knit-bikini-bob-haircut", "en",
     "White waffle-knit texture against tan skin with a clean bob haircut — the simplicity of this composition is its strength. No elaborate staging, just a subject who looks perfectly at home in her own skin, the fabric texture adding tactile interest without competing for attention."),
    ("young-east-asian-woman-indoor-selfie-natural-makeup", "zh_hant",
     "室內自拍的天然妝感很迷人，東亞女性的肌膚質感在自然光下顯得格外透明。不用過度修圖，真實的細節反而最有感染力。"),
    ("playful-east-asian-woman-restaurant-dining-portrait", "en",
     "Restaurant dining portraits capture people at their most animated. The playful energy here — mid-laugh, mid-conversation, genuinely present — is what makes this genre so much more alive than posed studio work ever could be."),
    ("summer-beach-white-swimsuit-ponytail-backview", "en",
     "Back views in white swimsuits with ponytails at the beach — there is a particular poetry in showing a subject from behind, inviting the viewer to imagine what they are looking at. The ocean horizon, the wind in the hair, the bare shoulders — it is a composition that trusts the viewer's imagination."),
    ("seductive-japanese-korean-woman-british-vintage-interior", "en",
     "British vintage interiors and East Asian beauty — the cultural collision here is fascinating. Dark wood paneling, period furniture, and the subject's composed sensuality create this timeless quality that transcends any single era or locale."),
    ("japanese-model-evening-bedroom-fashion-photography", "en",
     "Evening bedroom fashion photography has this warm, lamplit quality that daylight never replicates. The Japanese model's presence in this domestic twilight space feels both vulnerable and entirely in control — a rare balance in portraiture."),
    ("lace-corset-top-wrap-skirt-knee-high-boots", "en",
     "Lace corsets, wrap skirts, knee-high boots — this outfit combination walks the line between romantic and rebellious perfectly. The textures play against each other: soft lace against structured leather, flowing fabric against rigid boots. Fashion photography at its most visually interesting."),
    ("outdoor-stadium-vibrant-sports-east-asian-woman-portrait", "en",
     "Stadium sports portraits bring an energy that studio work cannot replicate. The vibrant colors of the seating, the architectural lines, the subject's athletic poise — all of it combines into an image that feels alive with movement even in stillness."),
    ("victorian-mansion-white-leather-corset-squatting-portrait", "en",
     "Victorian mansion interiors with white leather corsets and squatting poses — the juxtaposition of classical architecture with contemporary fashion creates visual tension that is incredibly compelling. The high ceiling, the ornate details, the raw confidence of the pose."),
    ("charming-korean-street-style-gingham-dress-portrait", "en",
     "Gingham dresses on Korean streets — there is a timeless charm to this combination. The checkered pattern adds visual rhythm to the urban backdrop, and the subject's natural charisma elevates what could be a simple outfit into a full editorial statement."),
    ("young-woman-white-dress-tropical-beach-prompt", "en",
     "White dresses on tropical beaches are a photography cliché for a reason — they work. The contrast of pristine white against blue water and golden sand is visually irresistible. What matters is the subject's presence, and here it feels effortless and genuine."),
    ("realistic-nighttime-outdoor-selfie-east-asian-women", "en",
     "Nighttime outdoor selfies by East Asian women — the artificial lighting, the urban reflections, the casual intimacy of the gesture — all of it creates this distinctly contemporary aesthetic that documents modern Asian urban life in a way that feels both personal and universal."),
    ("photorealistic-luxury-studio-portuguese-woman-fashion-photography", "en",
     "Luxury studio photography with Portuguese subjects brings a warmth that northern European shoots often miss. The photorealistic rendering here is remarkable — you can almost feel the texture of the clothing and the quality of the studio light on skin."),
    ("ultra-photorealistic-woman-restaurant-black-satin-outfit", "en",
     "Black satin in restaurant settings — the fabric catches ambient light in ways that photographs beautifully. Ultra-photorealistic rendering makes every fold and sheen tactile, creating an image that feels almost three-dimensional in its specificity."),
    ("japanese-class-reunion-pov-necktie-tugging-snapshot", "en",
     "POV class reunion snapshots with necktie tugging — this is documentary photography at its most engaging. The first-person perspective pulls you into the moment, making you feel like a participant rather than an observer. The Japanese setting adds cultural specificity that enriches the narrative."),
    ("orchid-and-mirror-flower-gallery-realistic-portrait", "en",
     "Orchids and mirrors in realistic portrait settings — the floral elements add organic softness while the mirrors introduce complexity through reflection and fragmentation. The gallery context elevates this from casual portrait to considered artistic statement."),
    ("y2k-pink-plaid-outfit-girl-fashion-photography", "en",
     "Y2K pink plaid is having its moment, and this fashion photography captures exactly why. The nostalgic color palette, the early-2000s silhouette, the confident posing — it all comes together to create an image that is both period-specific and timelessly cool."),
    ("white-morning-window-side-selfie-realistic-photography", "en",
     "Morning window selfies in white — the natural light from a east-facing window at dawn is photography's gift. Soft, diffused, and uniformly flattering. The realistic rendering here honors that gift by resisting the urge to over-process what is already perfect."),
    ("ultra-realistic-y2k-luxury-fashion-hotel-editorial", "en",
     "Y2K luxury fashion in hotel editorial settings — the marble bathrooms, the floor-to-ceiling windows, the carefully arranged minibar. Ultra-realistic rendering makes every surface tangible, from the cold tile to the warm fabric draping over chairs."),
    ("tropical-afternoon-hammock-nap-east-asian-beauty-lifestyle", "en",
     "Hammock naps in tropical afternoons — this is the lifestyle photography ideal that most images fail to capture authentically. Here the East Asian subject looks genuinely relaxed rather than performing relaxation, and that honesty is what makes the image work."),
    ("fashionable-east-asian-woman-modern-cafe-portrait", "en",
     "Modern cafe portraits of fashionable East Asian women — the glass, the industrial lighting, the carefully curated menu boards in the background. This is contemporary urban photography that documents how style and space interact in the 21st century."),
    ("low-angle-east-european-woman-white-linen-shirt-editorial", "en",
     "Low-angle editorial shots in white linen — the upward perspective elongates the figure and gives the subject an almost monumental presence. East European features against the crisp linen create this Northern European chic that feels both accessible and aspirational."),
    ("mid-summer-seaside-rest-japanese-woman-beer-snapshot", "en",
     "Mid-summer seaside rest with a beer in hand — this is the snapshot genre at its most honest. The Japanese subject's relaxed posture, the condensation on the can, the blurred ocean background — it all combines into an image that feels like a memory you have not yet made."),
    ("realistic-monochrome-female-portrait-prompt", "en",
     "Monochrome female portraits strip away distraction and force you to focus on form, light, and expression. This realistic approach avoids the pitfall of looking like a photograph of a painting — the skin textures and natural poses keep it grounded in reality."),
    ("dreamy-pastel-neighborhood-young-woman-portrait", "zh_hant",
     "夢幻的粉彩調街區肖像，年輕女孩的溫柔氛圍。柔和的色彩讓整個畫面像是一幅水彩畫，卻又有照片的真實感。這種風格最適合捕捉青春的甜美與純真。"),
    ("east-asian-woman-pink-lace-babydoll-nightgown", "en",
     "Pink lace babydoll nightgowns in East Asian portraiture — there is a delicate vulnerability in this combination of intimate clothing and natural beauty. The lace details catch light in complex ways, and the subject's composed expression adds dignity to what could easily become purely decorative."),
    ("korean-convenience-store-cashier-candid-photography", "en",
     "Korean convenience store cashier candid photography — these brightly lit, neon-soaked spaces are among the most visually rich environments in modern Asia. The cashier's expression, the product displays, the fluorescent glow — it is a genre that documents contemporary life with both empathy and aesthetic rigor."),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="photographer_opennana_42_run")
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
            "_dedupe_key": f"onana_pho42_{slug}_{i}",
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

    dedupe_file = ROOT / "state" / "seen_photographer_opennana_42.json"
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
