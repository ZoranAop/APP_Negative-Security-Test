#!/usr/bin/env python3
"""
Publish 7 opennana images using English-nickname photographer accounts.
All captions in English photographer voice, except yae-miko which is Japanese.
"""
import argparse, csv, io, json, os, re, subprocess, sys, time
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

POSTS = [
    ("hotel-room-camisole-double-v-gesture-condom-wrapper", "en",
     "Hotel room portraiture has this raw, unposed energy I really connect with. The double V gesture against that soft interior light -- it feels like a moment caught between laughter and something more. Camisole details always add such a nice texture contrast in frame."),
    ("summer-street-orange-bikini-sns-snapshot", "en",
     "Orange against charcoal brick -- that is the kind of color contrast I chase in street photography. The wide-angle proximity gives it this playful intimacy, like a snapshot you would send to a friend. The V-sign and fruit repetition really ties the composition together."),
    ("university-club-room-sportswear-woman-snapshot", "en",
     "There is something quietly honest about club room photography. The sportswear texture, the natural side angle, the background members living their own moments -- it all creates this documentary feel that staged shoots never capture. Navy blue on natural light is timeless."),
    ("blonde-woman-camden-street-punk-portrait", "en",
     "Camden punk energy captured perfectly. The brick corner, the scattered leaf-shadow light, the confident squat -- this is exactly the kind of street portrait I aim for. Yuki Aoyama influence is unmistakable in that transparent Japanese portrait grading."),
    ("cinematic-realistic-portrait-woman-red-dress", "en",
     "Crimson red against charcoal black -- bold but restrained. The theater sofa setting gives it this cinematic depth, and the off-shoulder jacket adds just enough edge. Realistic skin texture here is key; no plastic smoothing, just honest light on honest features."),
    ("yae-miko-rainy-shrine-selfie-sailor-suit", "ja",
     "雨の神社参道、透明な傘と水手服の組み合わせが幻想的。雨粒の粒感と朱色の鳥居の対比、まるで浮世絵の現代版のような美しさ。"),
    ("hotel-room-girl-double-v-gesture-condom-wrapper", "en",
     "The framing here is intriguing -- foreground hands holding the packaging like a curtain being drawn, the subject framed between them. It plays with intimacy and distance in a way that feels more conceptual than casual. Strong compositional statement."),
    ("urban-japanese-woman-balcony-rattan-chair-portrait", "en",
     "Rattan texture against urban balconies -- I love how this image balances domestic comfort with city geometry. The ribbed knit, the subtle head tilt, the greenery softening the concrete backdrop. It feels like a quiet afternoon that somehow became a perfect frame."),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="photographer_opennana_8_run")
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

    # Use centralized photographer account pool
    accounts = pick_photographer_accounts(len(images))
    print(f"[accounts] {len(accounts)} photographers: {[a['昵称'] for a in accounts]}")

    n = len(images)
    moments = []
    for i in range(n):
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
            "_dedupe_key": f"onana_pho8_{slug}",
        })

    moments_csv = wd / f"moments_photographer_opennana_{ts}.csv"
    fields = ["content","visibility","room_id","image_urls","location_name","location_address","location_lat","location_lon","_lang","_source","_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow(m)

    print(f"\n[OK] {len(moments)} posts ready")
    lang_count = {}
    for m in moments:
        lang_count[m["_lang"]] = lang_count.get(m["_lang"], 0) + 1
    print(f"[OK] lang dist: {lang_count}")
    for i, m in enumerate(moments):
        acct = accounts[i] if i < len(accounts) else {"昵称": "?"}
        preview = m["content"][:70].replace("\n", " ")
        print(f"  [{i+1:2d}] {acct['昵称']:20} lang={m['_lang']} | {preview}...")

    if args.skip_publish:
        print(f"\n--skip-publish. Content at: {moments_csv}")
        return 0

    if not args.yes:
        if input("\nConfirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    dedupe_file = ROOT / "state" / "seen_photographer_opennana_8.json"
    used = set()
    if dedupe_file.exists():
        try:
            used = set(json.loads(dedupe_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    new_slugs = {slug for _, _, _, slug in images}
    dedupe_file.write_text(json.dumps(sorted(used | new_slugs), ensure_ascii=False), encoding="utf-8")

    merged_acc = wd / f"accounts_merged_{ts}.csv"
    tokens_path = ROOT / args.tokens
    tokens_path.parent.mkdir(parents=True, exist_ok=True)
    with merged_acc.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号","昵称","邮箱","密码"])
        w.writeheader()
        for a in accounts:
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
