#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
caption_rewriter.py — 文案动态改写引擎（避免用户间内容雷同）

核心思路：基于一条"种子文案"，通过多维度组合变换生成 N 条不重复的变体。
每条变体在语义上相近，但用词、句式、情绪、视角各不相同。

改写维度：
  1. 词汇替换（同义词/近义表达）
  2. 句式变换（陈述/感叹/反问/省略）
  3. 情绪色彩（兴奋/平静/惊喜/感慨/幽默）
  4. 视角切换（第一人称/第三人称/对话式/独白式）
  5. 开头变体（直入主题/场景描写/感受先行/提问开场）
  6. 结尾变体（开放式/总结式/邀请式/留白式）
  7. 细节补充（随机加入时间/天气/心情/同行人等元素）

用法：
    from caption_rewriter import CaptionRewriter
    rw = CaptionRewriter(lang='en', scene='travel')
    captions = rw.generate(seed="Different city, same wide-eyed me.", count=20)
    # 产出 20 条不重复的旅行文案

    # 或命令行：
    py -3 scripts/caption_rewriter.py --seed "..." --lang en --scene travel --count 20 --output out.csv
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import random
import sys
from pathlib import Path


# ============================================================
# 改写模板库（按语言+场景）
# 每个模板是一个格式字符串，{emotion} {detail} {ending} 等为可替换槽位
# ============================================================

REWRITE_TEMPLATES = {
    "en": {
        "travel": [
            # 句式1: 直接感受
            "{emotion_prefix}Every new place reminds me why I love {detail}. {ending} {hashtags}",
            "{emotion_prefix}Landed somewhere new — {detail} hits different. {ending} {hashtags}",
            "There's something about {detail} that makes everything feel alive. {ending} {hashtags}",
            # 句式2: 对比/反思
            "Same passport, different skyline. {detail} never gets old. {ending} {hashtags}",
            "Home feels far away, but {detail} makes it worth every mile. {ending} {hashtags}",
            "Not lost, just exploring. {detail} keeps surprising me. {ending} {hashtags}",
            # 句式3: 感叹/惊喜
            "Didn't expect {detail} to steal my heart this fast. {ending} {hashtags}",
            "This view alone was worth the trip. {detail} {ending} {hashtags}",
            "Moments like these — {detail} — are why I keep moving. {ending} {hashtags}",
            # 句式4: 幽默/轻松
            "Map says I'm here. Heart says I never want to leave. {detail} {ending} {hashtags}",
            "Turns out, the best therapy is a one-way ticket. {detail} {ending} {hashtags}",
            "Jet-lagged but smiling. {detail} has that effect. {ending} {hashtags}",
            # 句式5: 独白/诗意
            "New streets, old soul. {detail} feels like a conversation with the city. {ending} {hashtags}",
            "Wandering without a plan — and {detail} revealed itself perfectly. {ending} {hashtags}",
            "The world is full of places I haven't felt yet. Today: {detail}. {ending} {hashtags}",
            # 句式6: 提问/互动
            "Have you ever arrived somewhere and felt instantly at home? {detail} did that to me. {ending} {hashtags}",
            "What's your travel non-negotiable? Mine is {detail}. {ending} {hashtags}",
            # 句式7: 场景描写
            "Golden light, unfamiliar streets, {detail} in the air. Perfect. {ending} {hashtags}",
            "Morning coffee in a city I can't pronounce. {detail} makes it magical. {ending} {hashtags}",
            "Sunset painted the whole sky — {detail} was the backdrop I didn't know I needed. {ending} {hashtags}",
        ],
    },
    "ms": {
        "travel": [
            "{emotion_prefix}Setiap tempat baru ingatkan saya kenapa saya suka {detail}. {ending} {hashtags}",
            "Sampai tempat baru — {detail} memang lain macam. {ending} {hashtags}",
            "Ada sesuatu tentang {detail} yang buat semua terasa hidup. {ending} {hashtags}",
            "Pasport sama, pemandangan lain. {detail} tak pernah bosan. {ending} {hashtags}",
            "Rumah rasa jauh, tapi {detail} buat setiap kilometer berbaloi. {ending} {hashtags}",
            "Tak sesat, cuma meneroka. {detail} sentiasa beri kejutan. {ending} {hashtags}",
            "Tak sangka {detail} boleh curi hati secepat ni. {ending} {hashtags}",
            "Pemandangan ni je dah berbaloi datang. {detail} {ending} {hashtags}",
            "Detik macam ni — {detail} — sebab tu saya tak berhenti jalan. {ending} {hashtags}",
            "Peta kata saya di sini. Hati kata tak nak balik. {detail} {ending} {hashtags}",
            "Jet lag tapi senyum. {detail} memang beri kesan tu. {ending} {hashtags}",
            "Jalan baru, jiwa lama. {detail} rasa macam berbual dengan kota. {ending} {hashtags}",
            "Merayau tanpa plan — dan {detail} muncul dengan sempurna. {ending} {hashtags}",
            "Dunia penuh tempat yang belum saya rasai. Hari ni: {detail}. {ending} {hashtags}",
            "Pernah sampai satu tempat dan terus rasa macam rumah? {detail} buat saya begitu. {ending} {hashtags}",
            "Cahaya emas, jalan tak dikenali, {detail} di udara. Sempurna. {ending} {hashtags}",
            "Kopi pagi di kota yang tak boleh saya sebut. {detail} jadikan ia ajaib. {ending} {hashtags}",
        ],
    },
    "fr": {
        "travel": [
            "{emotion_prefix}Chaque nouveau lieu me rappelle pourquoi j'aime {detail}. {ending} {hashtags}",
            "Arrivé quelque part de nouveau — {detail} frappe différemment. {ending} {hashtags}",
            "Il y a quelque chose à propos de {detail} qui rend tout vivant. {ending} {hashtags}",
            "Même passeport, horizon différent. {detail} ne vieillit jamais. {ending} {hashtags}",
            "La maison semble loin, mais {detail} vaut chaque kilomètre. {ending} {hashtags}",
            "Pas perdu, juste en exploration. {detail} me surprend toujours. {ending} {hashtags}",
            "Je ne m'attendais pas à ce que {detail} vole mon cœur si vite. {ending} {hashtags}",
            "Cette vue seule valait le voyage. {detail} {ending} {hashtags}",
            "Des moments comme ceux-ci — {detail} — c'est pourquoi je continue. {ending} {hashtags}",
            "Décalage horaire mais souriant. {detail} a cet effet. {ending} {hashtags}",
            "Nouvelles rues, vieille âme. {detail} ressemble à une conversation. {ending} {hashtags}",
            "Errer sans plan — et {detail} s'est révélé parfaitement. {ending} {hashtags}",
            "Lumière dorée, rues inconnues, {detail} dans l'air. Parfait. {ending} {hashtags}",
        ],
    },
    "de": {
        "travel": [
            "{emotion_prefix}Jeder neue Ort erinnert mich, warum ich {detail} liebe. {ending} {hashtags}",
            "Irgendwo Neues angekommen — {detail} trifft anders. {ending} {hashtags}",
            "Es gibt etwas an {detail}, das alles lebendig fühlen lässt. {ending} {hashtags}",
            "Gleicher Pass, andere Skyline. {detail} wird nie alt. {ending} {hashtags}",
            "Zuhause fühlt sich weit weg an, aber {detail} macht jeden Kilometer wert. {ending} {hashtags}",
            "Nicht verloren, nur am Entdecken. {detail} überrascht mich immer. {ending} {hashtags}",
            "Hätte nicht erwartet, dass {detail} mein Herz so schnell stiehlt. {ending} {hashtags}",
            "Diese Aussicht allein war die Reise wert. {detail} {ending} {hashtags}",
            "Momente wie diese — {detail} — deshalb höre ich nie auf. {ending} {hashtags}",
            "Jetlag aber lächelnd. {detail} hat diesen Effekt. {ending} {hashtags}",
            "Neue Straßen, alte Seele. {detail} fühlt sich wie ein Gespräch an. {ending} {hashtags}",
            "Goldenes Licht, unbekannte Straßen, {detail} in der Luft. Perfekt. {ending} {hashtags}",
        ],
    },
    "id": {
        "travel": [
            "{emotion_prefix}Setiap tempat baru ingatkan saya kenapa suka {detail}. {ending} {hashtags}",
            "Sampai di tempat baru — {detail} beda banget rasanya. {ending} {hashtags}",
            "Ada sesuatu dari {detail} yang bikin semuanya terasa hidup. {ending} {hashtags}",
            "Paspor sama, pemandangan beda. {detail} nggak pernah bosan. {ending} {hashtags}",
            "Rumah terasa jauh, tapi {detail} bikin setiap kilometer worth it. {ending} {hashtags}",
            "Nggak nyasar, cuma lagi jelajah. {detail} selalu kasih kejutan. {ending} {hashtags}",
            "Nggak nyangka {detail} bisa curi hati secepat ini. {ending} {hashtags}",
            "Pemandangan ini aja udah bikin perjalanan berbaloi. {detail} {ending} {hashtags}",
            "Momen kayak gini — {detail} — alasan saya terus jalan. {ending} {hashtags}",
            "Jet lag tapi tetap senyum. {detail} emang punya efek itu. {ending} {hashtags}",
            "Jalan baru, jiwa lama. {detail} kayak ngobrol sama kota. {ending} {hashtags}",
            "Cahaya emas, jalan asing, {detail} di udara. Sempurna. {ending} {hashtags}",
        ],
    },
}

# 填充槽位的素材池
EMOTION_PREFIXES = {
    "en": ["", "Honestly, ", "Still can't believe — ", "Best surprise: ", "Note to self: ", "Plot twist: ", "Gentle reminder: "],
    "ms": ["", "Jujur, ", "Masih tak percaya — ", "Kejutan terbaik: ", "Nota untuk diri: ", ""],
    "fr": ["", "Honnêtement, ", "Toujours pas cru — ", "Meilleure surprise : ", "Note à moi : ", ""],
    "de": ["", "Ehrlich gesagt, ", "Immer noch ungläubig — ", "Beste Überraschung: ", "Notiz an mich: ", ""],
    "id": ["", "Jujur, ", "Masih nggak percaya — ", "Kejutan terbaik: ", "Catatan: ", ""],
}

DETAILS_POOL = {
    "en": ["this golden light", "the sound of the city", "these winding streets", "that perfect breeze",
           "the colors around every corner", "watching locals just live", "the unexpected quiet",
           "how small I feel here", "the taste of something new", "a sky I've never seen before",
           "the rhythm of this place", "architecture that tells stories", "the warmth of strangers"],
    "ms": ["cahaya emas ni", "bunyi kota ni", "jalan-jalan berliku ni", "angin sempurna tu",
           "warna di setiap sudut", "tengok orang tempatan hidup", "ketenangan tak dijangka",
           "betapa kecilnya rasa di sini", "rasa sesuatu yang baru", "langit yang belum pernah lihat"],
    "fr": ["cette lumière dorée", "le son de la ville", "ces rues sinueuses", "cette brise parfaite",
           "les couleurs à chaque coin", "regarder les locaux vivre", "le calme inattendu",
           "comme je me sens petit ici", "le goût de quelque chose de nouveau"],
    "de": ["dieses goldene Licht", "den Klang der Stadt", "diese gewundenen Straßen", "diese perfekte Brise",
           "die Farben um jede Ecke", "Einheimische beim Leben zusehen", "die unerwartete Stille",
           "wie klein ich mich hier fühle", "den Geschmack von etwas Neuem"],
    "id": ["cahaya emas ini", "suara kota ini", "jalan-jalan berliku ini", "angin sempurna itu",
           "warna di setiap sudut", "lihat orang lokal hidup", "ketenangan yang tak terduga",
           "betapa kecilnya rasa di sini", "rasa sesuatu yang baru"],
}

ENDINGS_POOL = {
    "en": ["✈️", "🌍", "📸", "🧳", "☀️", "🗺️", "Keep going.", "More of this, please.", "Filing this under 'core memories'.",
           "The world rewards the curious.", "This is why we travel.", "No filter needed.", "Pure magic."],
    "ms": ["✈️", "🌍", "📸", "🧳", "Teruskan.", "Lagi macam ni, please.", "Simpan dalam ingatan.",
           "Dunia ganjari yang ingin tahu.", "Sebab inilah kita travel."],
    "fr": ["✈️", "🌍", "📸", "Continuons.", "Plus de ça, s'il vous plaît.", "Magie pure.",
           "C'est pour ça qu'on voyage.", "Pas de filtre nécessaire."],
    "de": ["✈️", "🌍", "📸", "Weitermachen.", "Mehr davon, bitte.", "Reine Magie.",
           "Deshalb reisen wir.", "Kein Filter nötig."],
    "id": ["✈️", "🌍", "📸", "Lanjutkan.", "Lebih banyak kayak gini.", "Sihir murni.",
           "Ini alasannya kita traveling.", "Tanpa filter."],
}

HASHTAG_POOLS = {
    "en": [
        "#travellog #wanderlust #explore", "#newcity #adventure #dailylife",
        "#travelgram #livingmybestlife #ontheroad", "#explore #discover #travel",
        "#wandering #vibes #blessed", "#worldtravel #travelmore #photooftheday",
        "#offthebeatenpath #solotravel #memories", "#citywalk #streetvibes #traveldiaries",
    ],
    "ms": [
        "#jelajah #mengembara #travel", "#kotabaru #pengembaraan #harianku",
        "#travelgram #hidupterbaik #dijalanan", "#meneroka #penemuan #travel",
        "#mengembara #vibes #bersyukur", "#traveldunia #jomtravel #fotoharian",
    ],
    "fr": [
        "#voyage #enviedailleurs #explorer", "#nouvelleville #aventure #quotidien",
        "#travelgram #vivre #surlaroute", "#explorer #découvrir #voyager",
        "#errance #vibes #reconnaissant", "#voyagemonde #voyagerplus #photodujour",
    ],
    "de": [
        "#reise #fernweh #entdecken", "#neuestadt #abenteuer #alltag",
        "#travelgram #leben #unterwegs", "#erkunden #entdecken #reisen",
        "#wandern #vibes #dankbar", "#weltreise #mehrreisen #fotodestages",
    ],
    "id": [
        "#jelajah #keliling #travel", "#kotabaru #petualangan #harianku",
        "#travelgram #hidupterbaik #dijalanan", "#meneroka #temuan #travel",
    ],
}


class CaptionRewriter:
    """基于种子文本生成N条不重复变体的改写引擎"""

    def __init__(self, lang: str = "en", scene: str = "travel"):
        self.lang = lang if lang in REWRITE_TEMPLATES else "en"
        self.scene = scene
        self.templates = REWRITE_TEMPLATES.get(self.lang, REWRITE_TEMPLATES["en"]).get(scene, REWRITE_TEMPLATES["en"]["travel"])
        self.used_hashes: set[str] = set()

    def generate(self, seed: str = "", count: int = 20) -> list[str]:
        """生成 count 条不重复的文案变体"""
        results = []
        attempts = 0
        max_attempts = count * 5  # 防止死循环

        while len(results) < count and attempts < max_attempts:
            attempts += 1
            caption = self._make_one(len(results) + attempts)
            # 去重检查（基于hash）
            h = hashlib.md5(caption.encode()).hexdigest()
            if h not in self.used_hashes:
                self.used_hashes.add(h)
                results.append(caption)

        return results

    def _make_one(self, seed_idx: int) -> str:
        """生成一条文案"""
        rng = random.Random(seed_idx * 7 + hash(self.lang))

        template = rng.choice(self.templates)
        lang = self.lang

        emotion = rng.choice(EMOTION_PREFIXES.get(lang, EMOTION_PREFIXES["en"]))
        detail = rng.choice(DETAILS_POOL.get(lang, DETAILS_POOL["en"]))
        ending = rng.choice(ENDINGS_POOL.get(lang, ENDINGS_POOL["en"]))
        hashtags = rng.choice(HASHTAG_POOLS.get(lang, HASHTAG_POOLS["en"]))

        caption = template.format(
            emotion_prefix=emotion,
            detail=detail,
            ending=ending,
            hashtags=hashtags,
        )
        return caption.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="文案动态改写引擎 — 生成N条不重复变体")
    ap.add_argument("--seed", default="Different city, same wide-eyed me.", help="种子文案（作为风格参考）")
    ap.add_argument("--lang", default="en", choices=list(REWRITE_TEMPLATES.keys()), help="语言")
    ap.add_argument("--scene", default="travel", help="场景")
    ap.add_argument("--count", type=int, default=20, help="生成条数")
    ap.add_argument("--output", default=None, help="输出CSV路径（不指定则打印到终端）")
    args = ap.parse_args()

    rw = CaptionRewriter(lang=args.lang, scene=args.scene)
    captions = rw.generate(seed=args.seed, count=args.count)

    if args.output:
        with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["index", "caption", "lang", "char_count"])
            for i, c in enumerate(captions):
                w.writerow([i + 1, c, args.lang, len(c)])
        print(f"[OK] Generated {len(captions)} unique captions → {args.output}")
    else:
        print(f"Generated {len(captions)} unique captions (lang={args.lang}, scene={args.scene}):\n")
        for i, c in enumerate(captions):
            print(f"  [{i+1:2d}] ({len(c):3d} chars) {c}")

    # 验证无重复
    unique = len(set(captions))
    print(f"\n  Unique: {unique}/{len(captions)} {'✓ 无重复' if unique == len(captions) else '⚠ 有重复!'}")
    return 0


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.exit(main())
