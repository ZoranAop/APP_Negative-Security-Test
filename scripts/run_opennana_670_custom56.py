#!/usr/bin/env python3
"""
run_opennana_670_custom56.py — 指定56个OpenNana画廊，互动用户池(670账号)发布
语言标注：en / ja / zh_hant（繁体中文）
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
import urllib3
urllib3.disable_warnings()
import openpyxl

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

OPENNANA_API_BASE = "https://api.opennana.com"
OPENNANA_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://opennana.com/",
    "Accept": "application/json",
}

ACCOUNT_POOL_XLSX = ROOT / "互动用户池_670账号.xlsx"
STATE_DIR = ROOT / "state"
DEDUPE_SLUG = STATE_DIR / "seen_opennana_670_custom56.json"

# slug, lang (en / ja / zh_hant), caption
GALLERIES = [
    ("realistic-outdoor-terrace-portrait-black-mini-dress-bob", "en",
     "Terrace afternoon, black mini dress and a bob cut that finally feels like me. The city buzz is right there but I\'m stuck in this quiet moment — black coffee, warm sun, no plans. Days like this reset everything."),
    ("natural-beachside-gravure-japanese-idol-tanuki-face-white-bikini", "zh_hant",
     "沙灘上的一張，白色比基尼配上隨意的妝，沒有刻意擺 pose，就是那一刻的光正好。海風吹亂頭髮也沒關係，這種隨意的感覺才是夏天的味道。"),
    ("morning-kitchen-ecru-apron-mini-dress-woman", "zh_hant",
     "清晨廚房裡，繫上米色圍裙，迷你裙還穿在身上就開始忙了。陽光剛好灑在料理台上，做了份早餐，邊吃邊看窗外，整個上午都是從容的節奏。"),
    ("summer-sky-mirror-selfie-portrait-east-asian-woman", "zh_hant",
     "夏天空格那麼藍，站在鏡前隨手拍了一張。妝很淡，頭髮被風吹得有點亂，反而喜歡這種不修飾的感覺。夏天的自拍就是要這種透亮感。"),
    ("japanese-woman-kitchen-refrigerator-night-snapshot", "ja",
     "夜中、冷蔵庫の前でふと立ち止まった。明日の献立を考えながら、冷たい飲み物を取り出して、その一瞬が写真的になった。台所の灯りがやわらかくて、少し疲れ切った一日の終わりが少しだけ楽になる時間。"),
    ("minimalist-black-and-white-childrens-book-split-poster", "en",
     "A split-frame piece inspired by an old children\'s book — two panels, black and white, nothing extra. I\'ve been playing with composition lately and this felt like the cleanest answer. Sometimes the simplest structure tells the story."),
    ("japanese-woman-shopping-supermarket-freezer-advertisement", "ja",
     "スーパーの冷凍庫の前で、何を切らしてたっけと少し迷った。夜間の買い物って、こういう静かな時間が逆に好き。レジ帰りに一息ついて、家に帰るのが少し楽しみになる、そんな日常。"),
    ("strapless-gown-dressing-table-candlelight-soft-silhouette", "zh_hant",
     "燭光下，無肩帶長裙隨意披著，妝台鏡裡映出的輪廓剛剛好。沒有開大燈，就留了幾根燭火，氛围感全在了。這種安靜的夜晚，適合什麼也不做，就坐著看光線。"),
    ("candid-lifestyle-east-asian-beauty-black-lace", "en",
     "Candid shot, black lace, no filter — just a moment where I didn\'t pose and the light did all the work. My favourite kind of photo is always the one I didn\'t plan. Lived-in, a little undone, genuinely me."),
    ("photorealistic-cinematic-woman-taiwanese-eatery-portrait", "ja",
     "台湾の屋台で撮ったポートレート。明かりがやわらかくて、背景の食器と人混みの感じが、ただの一枚じゃなくて映画のワンシーンみたいに見えた。現地の空気がそのまま写っているのが好き。"),
    ("japanese-woman-train-low-angle-realistic-i-cup", "ja",
     "電車の中で撮った一枚。下からのアングルがふいに決まって、窓の光と衣類の質感が写った。日常の風景なのに、なぜか一枚残しておきたくなるカットだった。"),
    ("high-fashion-japanese-woman-tokyo-street-portrait", "zh_hant",
     "東京街頭，穿了一整套高質感 outfit，走在鬧區裡被隨手拍到。背景車水馬龍，但那一瞬間好像整條街都屬於自己。東京街拍一直是靈感來源，今天的狀態也剛好。"),
    ("ancient-chinese-scholarly-noble-lady-portrait", "zh_hant",
     "漢服造型，古風場景裡的一張肖像。妝髮都是慢工細活，最後成像的那一刻，覺得這套衣服的故事感真的被拍出來了。這種穿越時光的感覺，拍一次少一次。"),
    ("east-asian-youth-japanese-aesthetic-school-lookbook", "ja",
     "学校ロケットブックの一枚。制服の季節って、撮り方ひとつで全然印象が変わることに気づいた。今日は光の角度が良くて、ふとした一瞬がそのまま残った。青春って、こういうカットで思い出すんだと思う。"),
    ("japanese-woman-urban-park-street-fashion-snapshot", "ja",
     "街の公園で撮ったストリートスナップ。コーデのバランスが気になって撮った一枚だけど、背景の緑と光の加減が全部うまくいって、いい仕上がりになった。散歩のついでに撮る写真って、いつも一番好き。"),
    ("surreal-smartphone-selfie-japanese-friends", "en",
     "Got a surreal phone selfie with my friends — the kind of shot that looks like a glitch but was just real life at exactly the right angle. Some moments are too weird to explain, you just save them and move on. No filter, no edit, just a frame from that day."),
    ("high-fashion-editorial-ivory-satin-portrait-prompt", "en",
     "Ivory satin, editorial light, no frills — this shoot felt like stepping into a different era for an afternoon. The fabric did half the work. Sometimes the most powerful look is the one with the least decoration."),
    ("sheer-crossed-top-backless-slit-skirt-incense", "en",
     "Layered, sheer, a little backless — incense smoke in the background and the whole frame felt like a still from a quiet, cinematic afternoon. I\'ve been into this kind of layered, ethereal styling lately. No rush, no noise, just texture and light."),
    ("pink-shell-beach-aurora-selfie", "zh_hant",
     "粉殼色的沙灘，天空泛著極光般的紫粉色，手機自拍的時候完全沒預期到這種色彩。夏天的海邊光線真的什麼都可能發生，這張就是那天最驚喜的一幀。"),
    ("smoky-purple-velvet-midnight-snapshot", "en",
     "Midnight, smoky purple velvet, and a light that made everything feel like a dream sequence. I\'ve been drawn to moody, low-light portraits lately — the less detail, the more mood. This one captured exactly that."),
    ("cream-mist-blue-dream-bedroom", "zh_hant",
     "醒來後房間裡的藍調霧氣，奶油色的光混在一起，整個空間像一場還沒醒完的夢。在床上坐了很久沒動，只拍了一張。這種半夢半醒的畫面，特別適合留下來。"),
    ("morning-korean-idol-girlfriend-snapshot", "zh_hant",
     "早起後隨手拍的日常，妝很淡，頭髮還亂著，就是那種「剛醒來被拍到」的真實感。這種不刻意的瞬間，反而最像日常生活的溫度。"),
    ("lavender-dream-korean-beauty-macro", "en",
     "Close-up macro shot, lavender tones, soft focus — the kind of detail you only notice when you\'re looking very carefully. I\'ve been into delicate, intimate framing lately. Small things, seen up close, hit different."),
    ("ultra-realistic-mcdonalds-street-photography-east-asian-women", "en",
     "A McDonald\'s corner, two friends, a bag of fries and a camera that doesn\'t care if the light is perfect. Some of the best photos are just… life, captured at the exact moment. No setup, no script — just a quick sit-down and a laugh that turned into a frame."),
    ("retro-indoor-maid-cosplay-portrait-photography", "en",
     "Retro indoor cosplay portrait — maid outfit, vintage lighting, a whole mood before the flash even hit. Cosplay photography is about the energy, not just the costume. When the character and the room agree, the shot writes itself."),
    ("outdoor-stone-shower-goddess", "en",
     "Found this stone shower setup outdoors and just had to shoot it — water, stone, a bit of goddess energy, and a light that made it look like a scene straight from a myth. Nature provides the set, you just show up and let it work."),
    ("wet-street-east-asian-coser-ccd-style", "en",
     "Wet streets, CCD camera, cosplay — the kind of shot that looks like a memory you\'re not even sure is real. The rain gave the whole frame a texture that no filter could fake. Sometimes the weather writes the shot for you."),
    ("japanese-fashion-editorial-silver-bob-woman-dressing-room", "zh_hant",
     "銀色bob cut，在試衣間裡拍了一組編輯級別的造型。鏡子的反射剛好把整個空間分成兩半，一側是日常，一側是舞台。這種雙重感，一直是我最喜歡拍的角度。"),
    ("realistic-photography-portrait-no-ai-beautification", "en",
     "No AI beautification, no heavy retouch — just honest light and a face that\'s actually mine. I\'m done with the fake-clean aesthetic. Real texture, real skin, real day. That\'s what makes a photo feel true."),
    ("japanese-beach-swimsuit-korean-influencer-kodak-film-look", "ja",
     "ビーチで撮った一枚。Kodakフィルム的な色味が好きで、スマホ撮りなのに映画館のポスターみたいに見えた。水着のスタイルと光の加減がうまく合って、この夏ベストのカットに。"),
    ("iphone-original-camera-summer-travel-snapshot", "ja",
     "iPhoneそのまま、サマートラベルの一枚。編集なし、フィルターなし、光が勝手にいい方向に決まった。旅先ではこういう「そのまま」が一番残したい風景だと思っていて、今日はまさにその瞬間が来た。"),
    ("japanese-woman-escalator-fashion-snapshot", "ja",
     "エスカレーターの上で撮ったストリートカット。移動中のふとした一瞬が、コーデのバランスを決めてくれた。日常の中に入っているファッション写真って、一番自然に出るタイプだと思う。"),
    ("night-street-ocean-goddess-selfie-cosplay", "en",
     "Night street, ocean backdrop, cosplay — the kind of shot that makes the whole frame feel like a scene from a movie nobody made yet. The light from the city and the water just worked together and I didn\'t have to ask for much."),
    ("retro-wasteland-girl-pink-clouds-dreamcore-photography", "en",
     "Retro wasteland, pink clouds, dreamcore — a shot that looks like a memory from a film you almost watched. The color grading did all the talking. I\'ve been into this surreal, soft-apocalypse aesthetic lately. It just feels like a dream you can\'t quite shake."),
    ("moody-girl-gray-wall", "en",
     "Gray wall, moody light, one girl looking like she\'s halfway into a thought. No location, no context — just a frame that says everything without explaining anything. Sometimes the emptiest background makes the strongest statement."),
    ("high-angle-bus-selfie-east-asian-woman-low-res-texture", "en",
     "High-angle bus selfie, a little low-res by design — the texture adds to it, not taking away. I\'ve been keeping my phone camera settings minimal lately. Less processing, more mood. This one captured exactly what the ride felt like."),
    ("iphone-snapshot-university-female-teacher-lecture", "zh_hant",
     "教室裡隨手拍的，講台上的一刻，光從側面打過來，整個畫面特別有故事感。上課的時候被拍到，反而留下了一張很真實的片段。"),
    ("east-asian-woman-fairytale-castle-travel-photo", "en",
     "Fairy-tale castle, travel day, and a frame that looks like I wandered into a picture book. The whole place was built for this kind of shot. No posing needed — just stand still and let the architecture do the work."),
    ("y2k-style-japanese-woman-triple-vertical-collage", "ja",
     "Y2Kスタイルのトリプル縦型コラージュ。90年代末のあの光と色を、今のコーデで再解釈してみた。写真一枚を三つに分けて見ると、全体のデザインまで楽しめるのが好き。"),
    ("indoor-mirror-selfie-blue-swimsuit-east-asian-woman", "en",
     "Indoor mirror selfie, blue swimsuit, no extra effort — just the lighting happened to be good and I was in the mood. Mirror selfies have a certain honesty to them. You see exactly what you\'re looking at, no angle tricks, no second chances."),
    ("punk-editorial-blonde-woman-abandoned-park", "en",
     "Punk editorial, blonde hair, abandoned park — the whole thing shot like a magazine spread nobody commissioned. I\'ve been doing these off-grid, high-contrast looks lately. The emptier the set, the louder the statement."),
    ("ccd-snapshot-east-asian-beauty-lace-outfit-bed", "en",
     "CCD camera, lace outfit, shot on the bed with no particular reason other than the light looked good. The whole frame has that soft, slightly hazy quality that CCD cameras do so well. No retouch, no filter — just the camera and the moment."),
    ("photorealistic-cinematic-smartphone-selfie-young-woman", "en",
     "Shot on my phone, edited on my phone, looks like a frame from a film. The kind of candid selfie where you\'re not looking at the camera and the light catches your face just right. Sometimes the best shots are the ones you almost forgot you took."),
    ("close-up-side-profile-smiling-east-asian-woman-plush-headband", "zh_hant",
     "側臉特寫，戴著絨毛髮帶，笑了一下就拍下了。妝很淡，就是剛醒來那種鬆鬆的感覺。這種近距離的畫面，反而比全景更能傳達當時的心情。"),
]


def _fetch_detail(slug: str) -> dict:
    for attempt in range(4):
        try:
            r = requests.get(f"{OPENNANA_API_BASE}/api/prompts/{slug}",
                             headers=OPENNANA_HEADERS, timeout=30, verify=False)
            r.raise_for_status()
            return r.json().get("data") or r.json()
        except Exception:
            if attempt < 3:
                time.sleep(2 * (attempt + 1))
            else:
                raise


def main() -> int:
    ap = argparse.ArgumentParser(description="發布指定56個OpenNana畫廊到互動用戶池(670账号)")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--login-spacing", type=float, default=3.0)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="opennana_670_custom56_run")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    # Load 670-account pool
    wb = openpyxl.load_workbook(str(ACCOUNT_POOL_XLSX), read_only=True)
    ws = wb.active
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    all_accounts = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        d = dict(zip(headers, row))
        all_accounts.append(d)

    # Already-used emails
    used_emails: set = set()
    if (ROOT / "result" / "tokens.json").exists():
        try:
            used_emails = set(json.loads((ROOT / "result" / "tokens.json").read_text(encoding="utf-8")).keys())
        except Exception:
            pass

    # Dedupe slugs
    seen_slugs: set = set()
    if DEDUPE_SLUG.exists():
        try:
            seen_slugs = set(json.loads(DEDUPE_SLUG.read_text(encoding="utf-8")))
        except Exception:
            pass

    fresh_accounts = [a for a in all_accounts
                      if str(a.get("邮箱", "")).strip() not in used_emails]
    print(f"[run_opennana_670_custom56] 池={len(all_accounts)}  未用={len(fresh_accounts)}  已用={len(used_emails)}")

    n_posts = len(GALLERIES)
    # Assign one distinct account per post, round-robin
    if len(fresh_accounts) < n_posts:
        print(f"[warn] 未用账号 ({len(fresh_accounts)}) < 帖子数 ({n_posts})，將含已用账号分配", file=sys.stderr)
        fresh_accounts = all_accounts

    moments = []
    account_assignments = []
    for i, (slug, lang, caption) in enumerate(GALLERIES):
        if slug in seen_slugs:
            print(f"[skip] {slug[:50]} 已發送過")
            continue
        detail = _fetch_detail(slug)
        images = [u for u in (detail.get("images") or []) if str(u).startswith("http")]
        if not images:
            print(f"[warn] {slug[:50]} 無圖片，跳過", file=sys.stderr)
            continue
        acc = fresh_accounts[i % len(fresh_accounts)]
        account_assignments.append(acc)
        moments.append({
            "content": caption,
            "image_urls": ",".join(images[:9]),
            "_slug": slug,
            "_lang": lang,
        })
        seen_slugs.add(slug)
        print(f"  [{lang}] {slug[:45]:45} -> {acc.get('昵称','?')} ({acc.get('邮箱','?')})")

    # Write out CSVs
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_slug", "_lang"]
    mom_csv = wd / f"moments_opennana_670_custom56_{ts}.csv"
    with mom_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow({k: m.get(k, "") for k in fields})

    acc_fields = ["序号", "昵称", "邮箱", "密码"]
    acc_csv = wd / f"accounts_opennana_670_custom56_{ts}.csv"
    with acc_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=acc_fields)
        w.writeheader()
        for a in account_assignments:
            w.writerow({k: a.get(k, "") for k in acc_fields})

    DEDUPE_SLUG.write_text(json.dumps(sorted(seen_slugs), ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[run_opennana_670_custom56] 素材已保存: {mom_csv.name}  账号: {acc_csv.name}")
    print(f"共 {len(moments)} 帖待發布。")

    if args.skip_publish:
        print("[skip-publish] 僅產出素材。")
        return 0

    if not args.yes:
        if input(f"  確認發布 {len(moments)} 帖？（y/n）：").strip().lower() not in ("y", "yes"):
            print("已取消。")
            return 0

    print("\n=== 發布 ===")
    cmd = [sys.executable, str(HERE / "publish_from_tokens.py"),
           "--accounts-csv", str(acc_csv),
           "--csv", str(mom_csv),
           "--concurrency", str(args.concurrency),
           "--login-spacing", str(args.login_spacing),
           "--tokens-out", str(ROOT / args.tokens)]
    if (ROOT / args.tokens).exists():
        cmd += ["--tokens-in", str(ROOT / args.tokens)]
    e = os.environ.copy()
    e.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(ROOT), env=e)
    if rc != 0:
        print("[run_opennana_670_custom56] 發布返回非零。", file=sys.stderr)
        return rc
    print("\n[run_opennana_670_custom56] 完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
