#!/usr/bin/env python3
"""
caption_multilang.py — Rewrite the ``content`` column of a moments CSV into
subject-first / first-person share-style captions across multiple languages.

Given a moments CSV produced by ``opennana_fetch.py`` / ``multi_source_fetch.py``,
where ``content`` is often just an English title + hashtags, this script:

1. Detects a *scene* from the original ``content`` (portrait / ootd / beach / …).
2. Picks a fresh caption from a rules-based multilingual template pool.
3. Balances the requested language mix across the whole file
   (e.g. ``--langs en,zh_hant,ja`` with even split by default).

If ``LLM_TEXT_API_BASE`` + ``LLM_TEXT_API_KEY`` are configured (see .env.example),
you can instead use ``--use-llm`` and it will call the OpenAI-compatible endpoint
to generate a caption for each row. Otherwise the built-in templates are used
(no external dependency).

Output: same CSV schema, ``content`` column rewritten in-place, other columns
preserved verbatim.

See docs/13-multilang-captions.md for details.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# scene detection (from title text)
# ---------------------------------------------------------------------------

SCENE_RULES = [
    ("kimono",   ["kimono", "yukata", "和服", "浴衣"]),
    ("hanfu",    ["hanfu", "汉服", "国风", "chinese traditional"]),
    ("bride",    ["bride", "wedding", "新娘", "婚"]),
    ("beach",    ["beach", "海边", "海滩", "seaside", "surf"]),
    ("goldenhour", ["golden hour", "sunset", "夕阳", "落日", "黄金时刻"]),
    ("winter",   ["snow", "雪", "winter", "冬"]),
    ("rain",     ["rain", "雨"]),
    ("cafe",     ["cafe", "coffee", "咖啡"]),
    ("night",    ["night", "midnight", "夜", "neon", "霓虹"]),
    ("street",   ["street", "sidewalk", "街", "urban"]),
    ("gym",      ["gym", "yoga", "workout", "健身", "瑜伽"]),
    ("running",  ["running", "run", "runner", "跑步"]),
    ("swim",     ["swim", "pool", "泳装", "bikini", "比基尼"]),
    ("dance",    ["dance", "dancer", "舞", "ballet"]),
    ("selfie",   ["selfie", "mirror", "自拍"]),
    ("ootd",     ["outfit", "fashion", "ootd", "streetwear", "穿搭", "editorial"]),
    ("bedroom",  ["bedroom", "居家", "宅", "at home"]),
    ("flower",   ["flower", "bouquet", "花"]),
    ("travel",   ["travel", "旅行", "tokyo", "paris", "london", "new york"]),
    ("cinema",   ["cinematic", "editorial", "film", "vogue", "campaign"]),
    ("portrait", ["portrait", "肖像", "人像", "close-up", "写真"]),
]


def detect_scene(text: str) -> str:
    t = (text or "").lower()
    for s, kws in SCENE_RULES:
        for kw in kws:
            if kw in t:
                return s
    return "portrait"


# ---------------------------------------------------------------------------
# Template pools per language (subject-first / user voice, no AI markers)
# Keep expandable: to add a language, add another dict with the same scene keys.
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, dict[str, list[str]]] = {
    "en": {
        "kimono":    ["Kimono weekend, tea in hand — feels like stepping into a slower era. 🍵 #kimono #japantrip #dailyjoy"],
        "hanfu":     ["Hanfu day out. The sleeves are dramatic, the mood is dreamy. 🌸 #hanfu #chineseculture #ootd"],
        "bride":     ["Trying on the dress felt more emotional than I expected. 🤍 #brideessentials #softmoments #forever"],
        "beach":     ["Sunscreen on, phone off, brain quiet. Beach mode fully activated. ☀️ #beachlife #summertime #chill",
                       "Wet sand under my feet is basically therapy at this point. 🌊 #seaside #unwind #softlife"],
        "goldenhour":["Golden hour turns everything ordinary into a memory. 🌅 #dailyframe #warmtones #simplejoy"],
        "winter":    ["Bundled up and finally admitting winter has its own kind of magic. 🧣 #snowday #cozy #wintermood"],
        "rain":      ["Umbrella out, playlist on, headed nowhere in particular. ☔ #rainwalk #cityvibes #softday"],
        "cafe":      ["Ordered too many pastries. Zero regrets. 🥐 #cafehop #weekendtreat #dailyjoy"],
        "night":     ["Neon signs and quiet streets — my kind of midnight. 🌃 #nightgram #urban #mood"],
        "street":    ["Wandering the city without a map is my favourite kind of freedom. #streetstyle #urbanexplorer #dailylife"],
        "gym":       ["Every rep whispered a little louder than yesterday's excuses. 💪 #gymgirl #stronger #consistency"],
        "running":   ["Just me, my playlist, and one sweaty finish. 🏃 #runningdiary #cardio #dailyroutine"],
        "swim":      ["Pool days are basically my favourite kind of reset. 💦 #poolday #summervibes #chill"],
        "dance":     ["When I'm dancing, the whole world goes quiet. 💃 #dance #joy #freedom"],
        "selfie":    ["Made peace with the mirror today. Small win but I'll take it. 🪞 #selfie #softera #dailylife"],
        "ootd":      ["Outfit didn't need to be loud to feel good. Quiet luxury kind of day. 👗 #ootd #minimalstyle #dailywear"],
        "bedroom":   ["Cozy pyjamas, weighted blanket, absolutely no plans. This is the vibe. 🛌 #softsunday #restday #cozycore"],
        "flower":    ["Peonies always feel like a soft yes from the universe. 🌷 #flowersoftheday #bloom #calm"],
        "travel":    ["Different city, same wide-eyed me. Excited by the tiniest things. ✈️ #travellog #wanderlust #daily"],
        "cinema":    ["Feels like a still from a film I haven't seen yet. 🎬 #cinematic #moody #editorialstyle"],
        "portrait":  ["Some frames don't need a story — just a mood. 📷 #portrait #softaesthetic #daily",
                       "Backlight caught me off guard and I loved it. #portrait #naturallight #moodygrams",
                       "Just a quiet moment I felt like keeping. #dailyframe #portrait #vibes"],
    },
    "zh": {
        "kimono":    ["穿上和服的一天，连走路的节奏都放慢了。🍵 #和服 #日常穿搭 #好心情"],
        "hanfu":     ["汉服的袖子一扬，整个心情都跟着飘起来。🌸 #汉服 #国风 #穿搭日常"],
        "bride":     ["试婚纱的那一刻，情绪比想象中复杂得多。🤍 #婚纱日记 #心情记录 #期待"],
        "beach":     ["把烦恼交给浪，人交给沙滩。☀️ #海边 #夏日 #放空"],
        "goldenhour":["黄昏那一刻，什么平常的画面都会变得像回忆。🌅 #黄金时刻 #生活记录 #好心情"],
        "winter":    ["终于承认冬天也有它自己的浪漫，帽子围巾一戴就是仪式感。🧣 #冬天 #穿搭 #好心情"],
        "rain":      ["撑伞、耳机、慢步调，没目的地才是雨天的享受。☔ #雨天 #城市漫步 #好心情"],
        "cafe":      ["点了太多甜点，但完全没有后悔。🥐 #咖啡日常 #周末小确幸 #好心情"],
        "night":     ["夜里的霓虹和安静的街，最适合我这种深夜游荡者。🌃 #夜景 #城市漫游 #好心情"],
        "street":    ["漫无目的走在街上，反而收获最多。 #街拍 #城市 #生活记录"],
        "gym":       ["每一组举起来的重量，都是昨天没说出口的坚持。💪 #健身 #自律 #生活记录"],
        "running":   ["傍晚的风刚好，跑一跑心情就整个亮起来。🏃 #跑步日常 #运动 #好心情"],
        "swim":      ["泳池里来回几趟，整个人都松了下来。💦 #泳池日常 #夏日 #好心情"],
        "dance":     ["跳起舞来的时候，好像全世界都跟着安静了。💃 #舞蹈日常 #热爱 #好心情"],
        "selfie":    ["跟镜子和解了一天，这算是小小的胜利吧。🪞 #自拍 #日常 #好心情"],
        "ootd":      ["安安静静的一套，穿起来也能有一整天的好心情。👗 #今日穿搭 #穿搭分享 #生活"],
        "bedroom":   ["睡衣、暖被、零计划的星期天，就是这个氛围。🛌 #宅家 #周末 #好心情"],
        "flower":    ["买了牡丹花给自己，觉得像宇宙轻轻点头。🌷 #花艺 #生活记录 #好心情"],
        "travel":    ["不同的城市，一样好奇的我。✈️ #旅行日常 #走走停停 #好心情"],
        "cinema":    ["感觉像是还没上映的电影里的一格。🎬 #电影感 #人像 #好心情"],
        "portrait":  ["有些画面不需要故事，一个氛围就够了。📷 #人像 #生活记录 #好心情",
                       "被逆光突然打到的一瞬间，太喜欢了。 #人像 #自然光 #生活随拍",
                       "只是一个想留下来的小片段。 #日常 #人像 #好心情"],
    },
    "zh_hant": {
        "kimono":    ["穿上和服的一天，連走路的節奏都放慢了。🍵 #和服 #日常穿搭 #好心情"],
        "hanfu":     ["漢服的袖子一揚，整個心情都跟著飄起來。🌸 #漢服 #國風 #穿搭日常"],
        "bride":     ["試婚紗的那一刻，情緒比想像中複雜得多。🤍 #婚紗日記 #心情記錄 #期待"],
        "beach":     ["把煩惱交給浪，人交給沙灘。☀️ #海邊 #夏日 #放空"],
        "goldenhour":["黃昏那一刻，什麼平常的畫面都會變得像回憶。🌅 #黃金時刻 #生活記錄 #好心情"],
        "winter":    ["終於承認冬天也有它自己的浪漫，帽子圍巾一戴就是儀式感。🧣 #冬天 #穿搭 #好心情"],
        "rain":      ["撐傘、耳機、慢步調，沒目的地才是雨天的享受。☔ #雨天 #城市漫步 #好心情"],
        "cafe":      ["點了太多甜點，但完全沒有後悔。🥐 #咖啡日常 #週末小確幸 #好心情"],
        "night":     ["夜裡的霓虹和安靜的街，最適合我這種深夜遊蕩者。🌃 #夜景 #城市漫遊 #好心情"],
        "street":    ["漫無目的走在街上，反而收穫最多。 #街拍 #城市 #生活記錄"],
        "gym":       ["每一組舉起來的重量，都是昨天沒說出口的堅持。💪 #健身 #自律 #生活記錄"],
        "running":   ["傍晚的風剛好，跑一跑心情就整個亮起來。🏃 #跑步日常 #運動 #好心情"],
        "swim":      ["泳池裡來回幾趟，整個人都鬆了下來。💦 #泳池日常 #夏日 #好心情"],
        "dance":     ["跳起舞來的時候，好像全世界都跟著安靜了。💃 #舞蹈日常 #熱愛 #好心情"],
        "selfie":    ["跟鏡子和解了一天，這算是小小的勝利吧。🪞 #自拍 #日常 #好心情"],
        "ootd":      ["安安靜靜的一套，穿起來也能有一整天的好心情。👗 #今日穿搭 #穿搭分享 #生活"],
        "bedroom":   ["睡衣、暖被、零計畫的星期天，就是這個氛圍。🛌 #宅家 #週末 #好心情"],
        "flower":    ["買了牡丹花給自己，覺得像宇宙輕輕點頭。🌷 #花藝 #生活記錄 #好心情"],
        "travel":    ["不同的城市，一樣好奇的我。✈️ #旅行日常 #走走停停 #好心情"],
        "cinema":    ["感覺像是還沒上映的電影裡的一格。🎬 #電影感 #人像 #好心情"],
        "portrait":  ["有些畫面不需要故事，一個氛圍就夠了。📷 #人像 #生活記錄 #好心情",
                       "被逆光突然打到的一瞬間，太喜歡了。 #人像 #自然光 #生活隨拍",
                       "只是一個想留下來的小片段。 #日常 #人像 #好心情"],
    },
    "ja": {
        "kimono":    ["着物を着ると、歩き方まで少しゆっくりになる気がする。🍵 #着物 #和装 #日常"],
        "hanfu":     ["漢服の袖がふわっと揺れるだけで、気分まで軽くなる。🌸 #漢服 #和装 #文化"],
        "bride":     ["ドレスを試着した瞬間、思ってた以上に胸がいっぱいになった。🤍 #結婚準備 #花嫁日記 #愛"],
        "beach":     ["日焼け止め塗って、スマホ切って、頭は真っ白。ビーチモード。☀️ #海 #夏の日 #解放"],
        "goldenhour":["夕方のこの一瞬だけで、なんでもない一日が思い出になる。🌅 #夕焼け #日常 #癒し"],
        "winter":    ["やっと冬にもロマンがあるって認めた。手袋とマフラーで儀式感。🧣 #冬の日常 #コーデ #ぬくもり"],
        "rain":      ["傘、音楽、ゆっくりの歩幅。目的地がないほど雨の日は楽しい。☔ #雨の日 #街歩き #気分"],
        "cafe":      ["スイーツ買いすぎたけど、後悔してないやつ。🥐 #カフェ #ご褒美 #日常"],
        "night":     ["ネオンと静かな道、私の深夜ぴったり。🌃 #夜景 #街 #日常"],
        "street":    ["目的なく歩く街が、いちばんの解放感。 #ストリート #散歩 #日常"],
        "gym":       ["1回1回の重さが、昨日の言い訳より少し大きい。💪 #ジム女子 #自分磨き #継続"],
        "running":   ["夕方の風に押されるように走った。ちょっと心が軽い。🏃 #ランニング #ラン日記 #日常"],
        "swim":      ["プールに入ると全部リセットされる感じがする。💦 #プール #夏 #日常"],
        "dance":     ["踊っていると、世界が全部静かになる瞬間がある。💃 #ダンス #好きなもの #日常"],
        "selfie":    ["鏡と仲直りできた日って、小さな勝利。🪞 #自撮り #日常 #気分"],
        "ootd":      ["派手じゃなくても、しっくりくる服が最強って気づく日。👗 #ootd #シンプルコーデ #日常"],
        "bedroom":   ["パジャマ、重い毛布、予定ゼロの日曜日。この空気感が好き。🛌 #おうち時間 #休日 #癒し"],
        "flower":    ["自分に牡丹を買った。宇宙にそっと肯定された気がする。🌷 #お花 #日常 #癒し"],
        "travel":    ["違う街でも、同じくらいワクワクする自分がいる。✈️ #旅の記録 #日常 #おでかけ"],
        "cinema":    ["まだ上映されてない映画の一コマみたい。🎬 #シネマ #ポートレート #日常"],
        "portrait":  ["物語がなくても、雰囲気だけで残したいコマってある。📷 #ポートレート #日常 #気分",
                       "逆光にふと切り取られて、思わずお気に入りになった。 #ポートレート #自然光 #日常",
                       "ただ残しておきたかった、静かな一瞬。 #日常 #ポートレート #気分"],
    },
}

SUPPORTED_LANGS = tuple(TEMPLATES.keys())


# ---------------------------------------------------------------------------
# picker
# ---------------------------------------------------------------------------

def pick_template(scene: str, lang: str, used: dict[tuple[str, str], int]) -> str:
    pool = TEMPLATES.get(lang, {}).get(scene) or TEMPLATES[lang]["portrait"]
    counts = [(used.get((lang, c), 0), i, c) for i, c in enumerate(pool)]
    counts.sort()
    m = counts[0][0]
    candidates = [c for u, _, c in counts if u == m]
    caption = random.choice(candidates)
    used[(lang, caption)] = used.get((lang, caption), 0) + 1
    return caption


# ---------------------------------------------------------------------------
# optional: LLM path (OpenAI-compatible /v1/chat/completions)
# ---------------------------------------------------------------------------

def llm_caption(raw: str, scene: str, lang: str) -> str | None:
    api_base = os.getenv("LLM_TEXT_API_BASE") or os.getenv("LLM_API_BASE")
    api_key = os.getenv("LLM_TEXT_API_KEY") or os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_TEXT_MODEL") or os.getenv("LLM_MODEL")
    if not (api_base and api_key and model):
        return None
    import requests  # local import so template-only mode has zero deps
    prompts = {
        "en": "Write a short first-person English caption (max 3 lines) that a young "
              "woman would post about the following image, with 2-4 hashtags + 1-2 emojis. "
              "Rewrite in a share-style voice, do NOT mention it's AI-generated. "
              f"Scene hint: {scene}. Raw description: {raw}",
        "zh": "以年轻用户第一人称口吻写一段简短中文分享文案（不超过3行），带2-4个话题标签和1-2个emoji。"
              f"不要提到AI/生成/提示词。场景提示：{scene}。原始描述：{raw}",
        "zh_hant": "以年輕用戶第一人稱口吻寫一段簡短繁體中文分享文案（不超過3行），帶2-4個話題標籤和1-2個emoji。"
                   f"不要提到AI/生成/提示詞。場景提示：{scene}。原始描述：{raw}",
        "ja": "若い女性が自分で投稿するような日本語の一人称短文（3行以内）を書いてください。"
              "2-4個のハッシュタグと1-2個の絵文字を含めて。AIやプロンプトについては触れないで。"
              f"シーン: {scene}。元説明: {raw}",
    }
    user_msg = prompts.get(lang, prompts["en"])
    try:
        r = requests.post(
            api_base.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You produce short social-media captions. Respond with the caption text only."},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.8,
                "max_tokens": 200,
            },
            timeout=30,
        )
        if r.status_code == 200:
            j = r.json()
            return j["choices"][0]["message"]["content"].strip()
        print(f"[warn] LLM {r.status_code} {r.text[:200]}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] LLM err {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _lang_plan(langs: list[str], n: int, seed: int) -> list[str]:
    """Even round-robin plan across the requested languages, then shuffled."""
    rng = random.Random(seed)
    base, rem = divmod(n, len(langs))
    plan: list[str] = []
    for i, lg in enumerate(langs):
        plan.extend([lg] * (base + (1 if i < rem else 0)))
    rng.shuffle(plan)
    return plan


def rewrite_csv(
    src: Path, dst: Path,
    *,
    langs: list[str],
    use_llm: bool,
    seed: int,
    use_existing_lang: bool = False,
) -> tuple[int, dict[str, int]]:
    """Rewrite ``content`` column into subject-voice captions.

    Returns (rows_written, {lang: count}).

    When ``use_existing_lang`` is True, each row's language is taken from its
    existing ``_lang`` column (e.g. produced by ``plan_lang_ratio.py`` for an
    exact ratio); rows without a valid ``_lang`` fall back to the even plan.
    """
    from collections import Counter

    with src.open("r", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return 0, {}

    plan = _lang_plan(langs, len(rows), seed)
    if use_existing_lang:
        # keep the pre-assigned _lang where present & supported
        plan = [
            (row.get("_lang") or "").strip()
            if (row.get("_lang") or "").strip() in SUPPORTED_LANGS
            else plan[i]
            for i, row in enumerate(rows)
        ]
    used_counts: dict[tuple[str, str], int] = {}
    lang_stats: Counter = Counter()

    fields = list(rows[0].keys())
    if "_lang" not in fields:
        fields.append("_lang")
    if "_scene" not in fields:
        fields.append("_scene")

    with dst.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for i, row in enumerate(rows):
            lang = plan[i]
            scene = detect_scene(row.get("content", "") or "")
            caption: str | None = None
            if use_llm:
                caption = llm_caption(row.get("content", ""), scene, lang)
            if not caption:
                caption = pick_template(scene, lang, used_counts)
            row["content"] = caption
            row["_lang"] = lang
            row["_scene"] = scene
            writer.writerow(row)
            lang_stats[lang] += 1

    return len(rows), dict(lang_stats)


def main() -> int:
    ap = argparse.ArgumentParser(description="Rewrite CSV captions into subject-voice, multi-lingual")
    ap.add_argument("--input", required=True, help="input CSV")
    ap.add_argument("--output", required=True, help="output CSV")
    ap.add_argument("--langs", default="en,zh_hant,ja",
                    help=f"comma list; supported: {','.join(SUPPORTED_LANGS)}")
    ap.add_argument("--use-llm", action="store_true",
                    help="use LLM_TEXT_* / LLM_* env vars if configured")
    ap.add_argument("--use-existing-lang", action="store_true",
                    help="respect a pre-assigned _lang column (e.g. from "
                         "plan_lang_ratio.py) instead of the even split")
    ap.add_argument("--seed", type=int, default=20260703)
    args = ap.parse_args()

    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    unknown = [l for l in langs if l not in SUPPORTED_LANGS]
    if unknown:
        print(f"[error] unknown languages: {unknown}. supported: {SUPPORTED_LANGS}",
              file=sys.stderr)
        return 2

    n, stats = rewrite_csv(
        Path(args.input), Path(args.output),
        langs=langs, use_llm=args.use_llm, seed=args.seed,
        use_existing_lang=args.use_existing_lang,
    )
    print(f"[OK] rewrote {n} rows → {args.output}")
    print(f"[OK] language stats: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
