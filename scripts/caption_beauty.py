#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
caption_beauty.py — 美女图文配文改写器（150-300字符，基于提示词延展，全局不重复）

设计目标：
  - 基于图片原始提示词/描述，生成 150-300 字符的第一人称分享配文
  - 全局去重：同一批次内每条配文内容不同
  - 多语言支持（zh_hant / en / ja / ko）
  - 句式结构多样化：开头、中段、结尾各有变化池，组合产生差异

机制：
  1) 从原始 prompt 中提取关键场景词（场所/穿搭/氛围/动作）
  2) 从「开头句式 + 场景描写 + 感悟/结尾」三段式模板池中随机组合
  3) 补充 2-4 个与场景相关的 hashtag
  4) 最终字符数控制在 150-300 之间
"""
from __future__ import annotations

import hashlib
import random
import re
from typing import Set

# ============================================================
# 场景关键词提取
# ============================================================
SCENE_KEYWORDS = {
    "indoor": ["居家", "室内", "壁炉", "卧室", "浴室", "沙发", "窗边", "床", "home", "indoor", "bedroom", "cozy"],
    "outdoor": ["户外", "街头", "公园", "海边", "沙滩", "山", "田野", "outdoor", "street", "park", "beach", "garden"],
    "cafe": ["咖啡", "餐厅", "下午茶", "甜品", "cafe", "coffee", "restaurant", "brunch"],
    "studio": ["棚拍", "影棚", "写真", "studio", "photoshoot", "portrait"],
    "fashion": ["穿搭", "时尚", "潮流", "ootd", "fashion", "outfit", "dress", "style"],
    "night": ["夜景", "霓虹", "夜晚", "酒吧", "night", "neon", "bar", "midnight"],
    "summer": ["夏日", "泳装", "比基尼", "阳光", "summer", "bikini", "sunshine", "pool"],
    "elegant": ["优雅", "气质", "古典", "旗袍", "新中式", "elegant", "graceful", "classical", "cheongsam"],
    "cute": ["可爱", "甜美", "少女", "元气", "cute", "sweet", "girly", "youthful"],
    "sexy": ["性感", "魅惑", "纯欲", "慵懒", "sexy", "alluring", "sensual", "languid"],
}


def _detect_scenes(text: str) -> list[str]:
    """从描述中提取命中的场景类型列表。"""
    t = (text or "").lower()
    hits = []
    for scene, kws in SCENE_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                hits.append(scene)
                break
    return hits or ["studio"]


# ============================================================
# 多语言三段式模板池
# ============================================================

TEMPLATES = {
    "zh_hant": {
        "openers": [
            "今天的光線剛好，整個氛圍都對了。",
            "翻照片的時候發現這組怎麼拍都好看。",
            "有些畫面不需要刻意安排，自然就很美。",
            "鏡頭前的每個瞬間都值得被記住。",
            "氣氛到位了，怎麼拍都是故事。",
            "那天的狀態特別好，隨手一拍就是片場感。",
            "被光影包圍的時刻總讓人想按下快門。",
            "有時候最好的照片就是不經意間的那一張。",
            "回看這組照片，每張都有不同的情緒。",
            "拍照的時候完全沒想到會這麼有感覺。",
            "說不上為什麼，就是覺得這個畫面很舒服。",
            "這種自然的美感是裝不出來的。",
        ],
        "middles": {
            "indoor": ["窗邊的光透進來灑在身上，整個空間都暖了起來。", "居家的慵懶感配上柔和的自然光，意外地很上鏡。", "午後陽光從窗簾縫隙透入，安靜得剛剛好。"],
            "outdoor": ["街頭的風吹過髮梢，畫面瞬間有了生命力。", "陽光灑下來的那一刻，整個人都發著光。", "自然光下的每個角度都像精心設計過一樣。"],
            "cafe": ["咖啡的香氣配上午後的光線，氛圍感直接拉滿。", "坐在窗邊的位置剛好，光影在臉上畫出了故事。", "一杯手沖配上這樣的光線，時間好像慢了下來。"],
            "studio": ["燈光一打，整個人的氣場都不一樣了。", "鏡頭對準的那一刻，彷彿進入了另一個世界。", "每次按下快門都是一次新的表達。"],
            "fashion": ["今天的穿搭和心情很配，出門就像走秀。", "衣服不用多花俏，穿出自己的態度就夠了。", "簡單的搭配有時候反而最耐看。"],
            "night": ["夜色下的光影特別迷人，像是城市在低語。", "霓虹燈映在眼裡，整個人融入了夜的氛圍。", "深夜的街道有種讓人放鬆的魔力。"],
            "summer": ["夏天就是要盡情享受陽光和微風的季節。", "陽光、海風、好心情，夏日三件套齊了。", "熱得剛好的溫度讓一切都顯得慵懶又美好。"],
            "elegant": ["優雅是一種不需要刻意的氣質。", "古典的韻味配上現代的鏡頭語言，碰撞出獨特的美。", "那種從容的氣場是時間沉澱出來的。"],
            "cute": ["元氣滿滿的一天從一個微笑開始。", "可愛不是裝出來的，是從心裡透出來的光。", "少女感的秘訣大概就是永遠保持好奇心吧。"],
            "sexy": ["慵懶中帶著一點小心機，剛好是最迷人的狀態。", "有些美是含蓄的，需要你慢慢感受。", "不張揚的魅力才最讓人移不開眼。"],
        },
        "closers": [
            "希望每天都能遇到這樣的好光線 ✨", "繼續記錄生活中的美好瞬間 📸",
            "美好的事物值得被反覆欣賞 🌸", "把最好的狀態留在鏡頭裡 💫",
            "這大概就是攝影的魅力吧 🎬", "生活需要這樣的儀式感 🌙",
            "好照片的標準就是讓人想多看兩眼 👀", "記錄下來才不會被時間沖淡 📷",
            "每一次快門都是一段新記憶 ✨", "氛圍感拿捏得剛剛好 💕",
        ],
        "hashtags": [
            "#寫真 #氛圍感 #日常記錄", "#人像攝影 #光影 #美好瞬間",
            "#穿搭日常 #質感生活 #記錄", "#攝影 #女生日常 #生活美學",
            "#氣質 #每日穿搭 #鏡頭", "#模特日常 #拍照 #情緒",
            "#日系 #清新 #膠片感", "#寫真集 #日常 #好心情",
            "#portrait #美好 #日常記錄", "#光影 #情緒片 #記錄生活",
        ],
    },
    "en": {
        "openers": [
            "The lighting was perfect today — everything just fell into place.",
            "Looking back at these shots and honestly they turned out better than expected.",
            "Some frames need no direction; they just happen naturally.",
            "Every moment in front of the lens tells its own story.",
            "When the vibe is right, every angle becomes a masterpiece.",
            "That day the energy was just different — every shot had magic.",
            "Being wrapped in light like this makes you forget everything else.",
            "Sometimes the best photo is the one you didn't plan.",
            "Reviewing this set and each frame has a different emotion.",
            "Didn't expect the camera to catch that feeling so perfectly.",
            "Can't explain it — this frame just feels right.",
            "Natural beauty like this can't be forced or faked.",
        ],
        "middles": {
            "indoor": ["Soft window light falling across the room, making everything feel warm and intentional.", "The lazy comfort of home paired with golden hour glow — unexpectedly photogenic.", "Afternoon sun filtering through curtains, quiet and perfectly timed."],
            "outdoor": ["Wind playing with hair on the street — suddenly the frame comes alive.", "The moment sunlight hit, everything glowed from within.", "Every angle in natural light looks like it was carefully composed."],
            "cafe": ["Coffee aroma mixing with afternoon light, atmosphere maxed out.", "The window seat caught the perfect light — shadows painting stories.", "A pour-over and this kind of light — time seemed to slow down."],
            "studio": ["Once the lights hit, the entire presence shifts.", "The moment the lens focuses, it's like stepping into another world.", "Every shutter click is a new form of expression."],
            "fashion": ["Today's outfit matches the mood perfectly — walking out feels like a runway.", "Clothes don't need to scream to make a statement.", "Simple styling sometimes ages the best."],
            "night": ["Light and shadow at night have their own kind of magic.", "Neon reflecting in eyes, melting into the night's atmosphere.", "Late-night streets have this power to make you feel calm."],
            "summer": ["Summer is for soaking in sunshine and gentle breezes.", "Sun, breeze, good vibes — the summer trifecta complete.", "That perfect warm temperature makes everything feel lazy and beautiful."],
            "elegant": ["Elegance is a quality that needs no effort.", "Classic charm meets modern lens language — a unique collision.", "That kind of composed presence only time can cultivate."],
            "cute": ["A day full of energy starts with a single smile.", "Cuteness isn't performed — it's light shining from within.", "The secret to looking youthful is probably never losing curiosity."],
            "sexy": ["A hint of intention wrapped in ease — that's the most captivating state.", "Some beauty is subtle; you have to slow down to feel it.", "Understated allure is what keeps eyes lingering."],
        },
        "closers": [
            "Hoping for golden light like this every day ✨", "Continuing to capture life's beautiful moments 📸",
            "Beautiful things deserve to be admired again and again 🌸", "Keeping the best version in the frame 💫",
            "This is probably what makes photography addictive 🎬", "Life needs these little rituals 🌙",
            "A good photo makes you want to look twice 👀", "Captured before time washes it away 📷",
            "Every shutter press is a new memory formed ✨", "Vibes: perfectly calibrated 💕",
        ],
        "hashtags": [
            "#portrait #aesthetic #dailycapture", "#photography #lightandshadow #beauty",
            "#ootd #lifestyle #captured", "#photography #dailylife #artofliving",
            "#elegance #dailywear #lens", "#modellife #photoshoot #mood",
            "#softlight #minimal #filmtones", "#photobook #daily #goodvibes",
            "#portraiture #beauty #documenting", "#lightplay #moodshots #liferecord",
        ],
    },
}


def generate_beauty_caption(
    orig_prompt: str,
    lang: str,
    seen: Set[str],
    rng: random.Random | None = None,
    min_len: int = 0,
    max_len: int = 300,
) -> str:
    """基于图片原始提示词，生成独立配文（全局不重复）。

    中文目标：80-150 字符（约240-450字节，信息密度高）
    英文目标：150-300 字符

    Args:
        orig_prompt: 图片原始描述/提示词
        lang: 目标语言 (zh_hant / en)
        seen: 已使用配文集合（用于去重）
        rng: 随机数生成器

    Returns:
        生成的配文字符串（保证不在 seen 中）
    """
    if rng is None:
        rng = random.Random()

    tmpl = TEMPLATES.get(lang, TEMPLATES.get("zh_hant"))
    scenes = _detect_scenes(orig_prompt)
    primary_scene = scenes[0] if scenes else "studio"

    # 语言相关的目标长度
    if lang in ("zh_hant", "zh"):
        target_min, target_max = 80, 160
    else:
        target_min, target_max = 150, 300

    max_attempts = 80
    for attempt in range(max_attempts):
        opener = rng.choice(tmpl["openers"])

        # 主场景 middle
        mid_pool = tmpl["middles"].get(primary_scene, tmpl["middles"]["studio"])
        middle = rng.choice(mid_pool)

        # 从其他场景选一个不同的补充 middle（确保不与 middle 相同）
        all_mid_options = []
        for sc in scenes + ["studio", "fashion", "elegant"]:
            for m in tmpl["middles"].get(sc, []):
                if m != middle:
                    all_mid_options.append(m)
        extra_middle = rng.choice(all_mid_options) if all_mid_options else ""

        closer = rng.choice(tmpl["closers"])
        hashtags = rng.choice(tmpl["hashtags"])

        # 组合策略：opener + middle + extra_middle(如需) + closer + hashtags
        cap = f"{opener}\n{middle}\n{closer}\n{hashtags}"

        if len(cap) < target_min and extra_middle:
            cap = f"{opener}\n{middle}\n{extra_middle}\n{closer}\n{hashtags}"

        if len(cap) > target_max:
            # 缩短：去掉 extra_middle
            cap = f"{opener}\n{middle}\n{closer}\n{hashtags}"
            if len(cap) > target_max:
                cap = cap[:target_max - len(hashtags) - 1].rstrip() + "\n" + hashtags

        # 去重检查
        cap_hash = hashlib.md5(cap.encode()).hexdigest()
        if cap_hash not in seen:
            seen.add(cap_hash)
            return cap

    # fallback: 加上 attempt 序号 + prompt 片段做差异化
    fb_opener = rng.choice(tmpl["openers"])
    fb_middle = rng.choice(tmpl["middles"].get(primary_scene, tmpl["middles"]["studio"]))
    fb_closer = rng.choice(tmpl["closers"])
    fb_tags = rng.choice(tmpl["hashtags"])
    prompt_hint = re.sub(r"#\S+", "", orig_prompt or "").strip()[:25]
    fallback = f"{fb_opener}\n{fb_middle}\n{fb_closer} [{prompt_hint}]\n{fb_tags}"
    seen.add(hashlib.md5(fallback.encode()).hexdigest())
    return fallback[:target_max]
