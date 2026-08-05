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
import re
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
    ("beach",    ["beach", "海边", "海滩", "seaside", "surf", "island", "pulau", "pantai", "redang", "langkawi", "perhentian", "sea", "ocean", "bali", "kuta", "seminyak", "nusa", "gili", "lombok", "raja ampat", "bunaken", "峇里", "巴厘", "海島", "墾丁", "墾丁", "海邊", "澎湖", "小琉球", "綠島", "蘭嶼", "北海岸", "東北角", "福隆", "外澳"]),
    ("goldenhour", ["golden hour", "sunset", "夕阳", "落日", "黄金时刻", "senja", "sunrise", "matahari terbenam", "夕陽", "日落", "黃昏", "高美濕地"]),
    ("winter",   ["snow", "雪", "winter", "冬", "cameron", "highlands", "genting", "mountain", "kinabalu", "gunung", "bukit", "神山", "云顶", "雲頂", "高原", "金馬倫", "金马仑", "bromo", "dieng", "ijen", "rinjani", "merapi", "火山", "合歡山", "玉山", "阿里山", "雪山", "太平山", "高山", "雪景"]),
    ("rain",     ["rain", "雨", "hujan"]),
    ("cafe",     ["cafe", "coffee", "咖啡", "kopi", "food", "makan", "makanan", "restoran", "餐廳", "餐厅", "美食", "小吃", "夜市", "白咖啡", "warung", "kuliner", "sate", "nasi", "手沖", "甜點", "咖啡廳"]),
    ("night",    ["night", "midnight", "夜", "neon", "霓虹", "malam", "petronas", "klcc", "skyline", "tower", "menara", "夜景", "雙子星", "双子星", "地標", "地标", "jakarta", "雅加達", "雅加达", "台北101", "101", "夜市", "饒河", "士林", "逢甲"]),
    ("street",   ["street", "sidewalk", "街", "urban", "city", "bandar", "town", "market", "pasar", "lorong", "heritage", "melaka", "penang", "georgetown", "檳城", "槟城", "怡保", "喬治市", "乔治市", "老街", "壁畫", "壁画", "馬六甲", "马六甲", "kota tua", "yogyakarta", "jogja", "malioboro", "bandung", "solo", "borobudur", "prambanan", "candi", "日惹", "九份", "台南", "鹿港", "大稻埕", "迪化街", "老屋", "古都", "巷弄"]),
    ("gym",      ["gym", "yoga", "workout", "健身", "瑜伽"]),
    ("running",  ["running", "run", "runner", "跑步"]),
    ("swim",     ["swim", "pool", "泳装", "bikini", "比基尼"]),
    ("dance",    ["dance", "dancer", "舞", "ballet"]),
    ("selfie",   ["selfie", "mirror", "自拍"]),
    ("ootd",     ["outfit", "fashion", "ootd", "streetwear", "穿搭", "editorial"]),
    ("bedroom",  ["bedroom", "居家", "宅", "at home"]),
    ("flower",   ["flower", "bouquet", "花束", "花藝", "賞花", "花海", "花季", "花田", "bunga"]),
    ("travel",   ["travel", "旅行", "tokyo", "paris", "london", "new york", "malaysia", "asia", "kuala lumpur", "sabah", "sarawak", "borneo", "temple", "kuil", "mosque", "masjid", "batu caves", "landmark", "nature", "landscape", "waterfall", "air terjun", "lake", "tasik", "bridge", "jambatan", "馬來西亞", "马来西亚", "吉隆坡", "沙巴", "砂拉越", "自由行", "自助", "旅遊", "旅游", "遊", "转机", "轉機", "攻略", "假期", "開齋節", "开斋节", "神山", "indonesia", "印尼", "印度尼西亞", "印度尼西亚", "wonderful indonesia", "danau", "air terjun", "curug", "wisata", "jalan-jalan", "liburan", "komodo", "toba", "sumatra", "sulawesi", "jawa", "flores", "labuan bajo", "taiwan", "台灣", "台湾", "台北", "花蓮", "台東", "南投", "宜蘭", "日月潭", "太魯閣", "縱谷", "風景區", "國家公園", "秘境", "環島", "部落", "客家"]),
    ("cinema",   ["cinematic", "editorial", "film", "vogue", "campaign"]),
    ("portrait", ["portrait", "肖像", "人像", "close-up", "写真"]),
]


def detect_scene(text: str) -> str:
    t = (text or "").lower()
    for s, kws in SCENE_RULES:
        for kw in kws:
            if kw in t:
                return s
    return os.getenv("DEFAULT_SCENE", "portrait")


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
        "beach":     ["把煩惱交給浪，人交給沙灘。☀️ #海邊 #夏日 #放空",
                        "海邊的浪聲一來，煩惱都被沖走了。🌊 #海邊 #旅行 #放鬆",
                        "藍天白沙的午後，整個人都被治癒了。🏝️ #海岸 #旅行隨筆 #放空"],
        "goldenhour":["黃昏那一刻，什麼平常的畫面都會變得像回憶。🌅 #黃金時刻 #生活記錄 #好心情",
                        "夕陽把天空染成橘紅，這種傍晚百看不膩。🌇 #夕陽 #旅行之美 #放鬆"],
        "winter":    ["終於承認冬天也有它自己的浪漫，帽子圍巾一戴就是儀式感。🧣 #冬天 #穿搭 #好心情",
                        "山上的清晨冷得值得，早起真的沒白費。🧣 #高山 #旅行 #冬日"],
        "rain":      ["撐傘、耳機、慢步調，沒目的地才是雨天的享受。☔ #雨天 #城市漫步 #好心情"],
        "cafe":      ["點了太多甜點，但完全沒有後悔。🥐 #咖啡日常 #週末小確幸 #好心情",
                        "巷弄裡的咖啡館，配一杯手沖剛剛好。☕ #咖啡 #巷弄漫遊 #小確幸"],
        "night":     ["夜裡的霓虹和安靜的街，最適合我這種深夜遊蕩者。🌃 #夜景 #城市漫遊 #好心情",
                        "城市點燈的夜晚，怎麼拍都好看。🌆 #夜景 #城市之美 #旅行",
                        "逛夜市的煙火氣，才是城市的靈魂。🏮 #夜市 #美食 #夜生活"],
        "street":    ["漫無目的走在街上，反而收穫最多。 #街拍 #城市 #生活記錄",
                        "老街的燈籠一亮，整條街都有故事。🏮 #老城 #街拍 #旅行",
                        "巷弄裡到處是驚喜，走走停停最舒服。🚶 #城市漫步 #探索 #旅行"],
        "gym":       ["每一組舉起來的重量，都是昨天沒說出口的堅持。💪 #健身 #自律 #生活記錄"],
        "running":   ["傍晚的風剛好，跑一跑心情就整個亮起來。🏃 #跑步日常 #運動 #好心情"],
        "swim":      ["泳池裡來回幾趟，整個人都鬆了下來。💦 #泳池日常 #夏日 #好心情"],
        "dance":     ["跳起舞來的時候，好像全世界都跟著安靜了。💃 #舞蹈日常 #熱愛 #好心情"],
        "selfie":    ["跟鏡子和解了一天，這算是小小的勝利吧。🪞 #自拍 #日常 #好心情"],
        "ootd":      ["安安靜靜的一套，穿起來也能有一整天的好心情。👗 #今日穿搭 #穿搭分享 #生活"],
        "bedroom":   ["睡衣、暖被、零計畫的星期天，就是這個氛圍。🛌 #宅家 #週末 #好心情"],
        "flower":    ["買了牡丹花給自己，覺得像宇宙輕輕點頭。🌷 #花藝 #生活記錄 #好心情"],
        "travel":    ["不同的城市，一樣好奇的我。✈️ #旅行日常 #走走停停 #好心情",
                        "每個角落都有驚喜，怎麼玩都玩不膩。✨ #旅行隨筆 #探索 #走走停停",
                        "從北到南，每個地方都有自己的味道。🧳 #旅行 #探索 #生活記錄",
                        "又發現一個秘境，這種美只有親眼看到才懂。📸 #秘境 #旅行之美 #旅行"],
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
    "ko": {
        "kimono":    ["기모노 입은 주말, 차 한 잔 들고 — 시간이 천천히 흐르는 느낌. 🍵 #기모노 #일상 #힐링"],
        "hanfu":     ["한복의 소매가 바람에 흩날리니 마음까지 가벼워지는 기분. 🌸 #한복 #전통의상 #데일리"],
        "bride":     ["드레스 입어본 순간, 생각보다 감정이 복잡해졌다. 🤍 #웨딩준비 #설렘 #사랑"],
        "beach":     ["선크림 바르고, 폰 끄고, 머리 비우기. 바다 모드 온. ☀️ #바다 #여름 #힐링",
                       "파도 소리에 고민이 다 씻겨 나가는 기분. 🌊 #해변 #바캉스 #쉼"],
        "goldenhour":["골든아워의 그 순간, 평범한 풍경도 추억이 된다. 🌅 #골든아워 #일상기록 #감성"],
        "winter":    ["드디어 인정했다. 겨울에도 겨울만의 낭만이 있다는 걸. 🧣 #겨울 #따뜻하게 #무드"],
        "rain":      ["우산 쓰고, 이어폰 끼고, 목적지 없이 걷기. 비 오는 날의 사치. ☔ #비오는날 #산책 #감성"],
        "cafe":      ["디저트를 너무 많이 시켰다. 후회는 전혀 없음. 🥐 #카페 #일상 #소확행"],
        "night":     ["네온사인과 조용한 거리 — 내가 좋아하는 종류의 밤. 🌃 #야경 #도시 #무드"],
        "street":    ["지도 없이 걷는 도시가 주는 자유로움이 좋다. #스트릿 #도시산책 #일상"],
        "gym":       ["오늘 든 무게가 어제의 변명보다 무거웠다. 💪 #운동 #자기관리 #꾸준히"],
        "running":   ["저녁 바람 맞으며 달리니 기분이 확 밝아졌다. 🏃 #러닝 #운동일기 #일상"],
        "swim":      ["수영장에서 몇 바퀴 돌고 나면 몸도 마음도 풀린다. 💦 #수영 #여름 #리프레시"],
        "dance":     ["춤출 때만큼은 세상이 조용해지는 순간이 있다. 💃 #댄스 #열정 #자유"],
        "selfie":    ["오늘 거울이랑 화해한 날. 작은 승리지만 뿌듯. 🪞 #셀카 #일상 #나만의시간"],
        "ootd":      ["화려하지 않아도 기분 좋은 옷차림. 오늘의 정답. 👗 #오오티디 #데일리룩 #심플"],
        "bedroom":   ["파자마, 이불, 아무 계획 없는 일요일. 이게 바로 행복. 🛌 #집순이 #휴식 #힐링"],
        "flower":    ["나를 위해 꽃을 사는 날은 우주가 살짝 고개 끄덕이는 느낌. 🌷 #꽃 #일상기록 #힐링"],
        "travel":    ["다른 도시, 같은 설레는 나. 작은 것에도 눈이 반짝. ✈️ #여행 #일상 #감성",
                       "여행은 늘 세상이 크면서도 작다는 걸 가르쳐준다. 🧳 #여행스타그램 #떠나자 #추억",
                       "새로운 곳에서 또 한 번 설렘을 발견했다. 📸 #여행기록 #일상 #감성여행"],
        "cinema":    ["아직 개봉 안 한 영화의 한 장면 같은 순간. 🎬 #시네마틱 #무드 #감성"],
        "portrait":  ["어떤 사진은 이야기 없이 분위기만으로 충분하다. 📷 #인물사진 #감성 #일상",
                       "역광에 불현듯 찍힌 한 컷이 마음에 든다. #포트레이트 #자연광 #감성",
                       "조용히 남겨두고 싶었던 한 순간. #일상 #인물사진 #무드"],
    },
    "ms": {
        "kimono":    ["Hujung minggu pakai kimono, secawan teh di tangan — rasa macam masa berjalan perlahan. 🍵 #kimono #gayaharian #tenang"],
        "hanfu":     ["Hari beraya budaya, lengan baju berkibar, hati pun rasa ringan. 🌸 #busanatradisi #gayaharian #budaya"],
        "bride":     ["Cuba baju pengantin ni buat hati sebak tak sangka. 🤍 #bakalpengantin #detikmanis #cinta"],
        "winter":    ["Sejuk Cameron Highlands pagi ni, berbaloi bangun awal. 🧣 #cameronhighlands #cutimalaysia #sejukmanja"],
        "rain":      ["Hujan renyai, payung terkembang, jalan-jalan tanpa hala tuju. ☔ #hujan #santai #jomjalan"],
        "cafe":      ["Order kopi tiga lapis dengan kuih — memang tak menyesal. ☕ #kopimalaysia #jomlepak #harianku"],
        "night":     ["Lampu KLCC waktu malam memang tak pernah gagal buat terpukau. 🌃 #kualalumpur #malamKL #jelajahmalaysia",
                       "Menara berkembar bergemerlapan, malam KL memang ada auranya. ✨ #petronas #malamKL #malaysiaindah",
                       "Skyline bandar waktu malam — pemandangan yang tak pernah jemu. 🌆 #cityscape #malamKL #jelajahmalaysia"],
        "street":    ["Sesat-sesat di lorong bandar tua ni pun satu keseronokan. 🚶 #bandartua #jelajahmalaysia #harianku",
                       "Warna-warni rumah kedai di Melaka memang buat hati ceria. 🏘️ #melaka #warisan #jelajahmalaysia",
                       "Jalan-jalan di George Town, setiap dinding ada seni tersendiri. 🎨 #penang #georgetown #cutimalaysia"],
        "gym":       ["Setiap set hari ni lagi kuat daripada alasan semalam. 💪 #jomgym #konsisten #sihatselalu"],
        "running":   ["Berlari petang tepi tasik, hati terus cerah. 🏃 #lariharian #cergas #rutinku"],
        "swim":      ["Berendam kejap dalam kolam terus rasa segar semula. 💦 #cutimalaysia #musimpanas #santai"],
        "dance":     ["Bila menari, dunia rasa senyap seketika. 💃 #menari #minat #gembira"],
        "selfie":    ["Hari ni berdamai dengan cermin. Kemenangan kecil, tapi cukup. 🤳 #swafoto #harianku #tenang"],
        "ootd":      ["Baju tak perlu menyerlah pun boleh rasa selesa. Gaya simple hari ni. 👗 #ootd #gayaharian #simple"],
        "bedroom":   ["Baju tidur selesa, selimut tebal, dan tiada rancangan. Inilah mood hujung minggu. 🛌 #santai #hariberehat #selesa"],
        "flower":    ["Bunga raya berkembang penuh — macam alam ucap selamat pagi. 🌺 #bungaraya #alammalaysia #tenang"],
        "travel":    ["Jelajah Malaysia memang tak pernah kekurangan tempat cantik. ✈️ #cutimalaysia #jomjalan #malaysiaindah",
                       "Dari Melaka ke Sabah, setiap tempat ada cerita sendiri. 🧳 #jelajahmalaysia #jomcuti #harianku",
                       "Malaysia ni kecil, tapi keindahannya tak terhingga. 🇲🇾 #malaysiaindah #cutimalaysia #jomjalan",
                       "Setiap kali melancong, mesti jumpa sudut baru yang buat terpegun. 📸 #jelajahmalaysia #jomjalan #kembara"],
        "goldenhour":["Waktu senja di sini buat benda biasa jadi kenangan. 🌅 #senja #jelajahmalaysia #tenang",
                       "Langit jingga waktu maghrib memang hadiah percuma paling cantik. 🌇 #senja #malaysiaindah #tenang"],
        "beach":     ["Angin laut, kaki atas pasir, fikiran terus lapang. Mod pantai penuh! ☀️ #pantai #cutimalaysia #santai",
                       "Ombak Pulau Redang memang tak pernah mengecewakan. 🌊 #pulaumalaysia #jomcuti #santai",
                       "Air laut jernih macam kaca, terus rasa nak lompat masuk. 🏝️ #pulaumalaysia #cutimalaysia #santai"],
        "cinema":    ["Rasa macam satu babak dalam filem yang belum ditayang. 🎬 #sinematik #mood #fotografi"],
        "portrait":  ["Sesetengah gambar tak perlu cerita — cukup dengan suasana. 📷 #potret #harianku #tenang",
                       "Cahaya senja tangkap saat ni, terus jatuh cinta. #potret #cahayasemulajadi #mood",
                       "Sekadar satu detik tenang yang ingin ku simpan. #harianku #potret #malaysiaindah"],
    },
    "id": {
        "kimono":    ["Akhir pekan pakai baju tradisional, secangkir teh di tangan — rasanya waktu jadi pelan. 🍵 #tradisi #gayaharian #tenang"],
        "hanfu":     ["Hari pakai busana tradisional, lengannya melambai, hati pun ikut ringan. 🌸 #busanatradisi #ootd #budaya"],
        "bride":     ["Coba gaun pengantin bikin hati haru nggak nyangka. 🤍 #calonpengantin #momenmanis #cinta"],
        "beach":     ["Angin laut, kaki di pasir, pikiran langsung plong. Mode pantai aktif! ☀️ #pantai #liburanindonesia #santai",
                       "Ombak Bali emang nggak pernah bikin kecewa. 🌊 #bali #pesonaindonesia #santai",
                       "Air lautnya bening banget, pengen langsung nyebur. 🏝️ #rajaampat #wonderfulindonesia #santai"],
        "goldenhour":["Senja di sini bikin hal biasa jadi kenangan. 🌅 #senja #pesonaindonesia #tenang",
                       "Langit jingga waktu magrib emang hadiah paling cantik. 🌇 #sunset #wonderfulindonesia #tenang"],
        "winter":    ["Dinginnya pagi di dataran tinggi, worth it bangun subuh. 🧣 #dieng #liburanindonesia #sejuk"],
        "rain":      ["Gerimis, payung kebuka, jalan-jalan tanpa tujuan. ☔ #hujan #santai #jalanjalan"],
        "cafe":      ["Pesan kopi susu sama gorengan — nggak ada nyesel sama sekali. ☕ #kopiindonesia #ngopi #harianku"],
        "night":     ["Lampu kota malam hari emang nggak pernah gagal bikin terpukau. 🌃 #jakarta #malamkota #pesonaindonesia",
                       "Skyline kota waktu malam, pemandangan yang nggak ada bosennya. 🌆 #cityscape #malamkota #wonderfulindonesia",
                       "Gemerlap lampu malam, suasananya beda banget. ✨ #malamkota #jalanjalan #pesonaindonesia"],
        "street":    ["Nyasar-nyasar di gang kota tua malah jadi seru sendiri. 🚶 #kotatua #jalanjalan #harianku",
                       "Warna-warni bangunan tua di sini bikin hati senang. 🏘️ #kotatua #wisatabudaya #pesonaindonesia",
                       "Jalan kaki keliling kota, tiap sudut punya cerita. 🎨 #jalanjalan #wisatakota #liburanindonesia"],
        "gym":       ["Tiap set hari ini lebih kuat dari alasan kemarin. 💪 #ndolahraga #konsisten #sehatselalu"],
        "running":   ["Lari sore di tepi danau, hati langsung cerah. 🏃 #lariharian #sehat #rutinku"],
        "swim":      ["Berendam sebentar di kolam langsung berasa segar lagi. 💦 #liburan #musimpanas #santai"],
        "dance":     ["Pas nari, dunia rasanya hening sejenak. 💃 #nari #hobi #bahagia"],
        "selfie":    ["Hari ini berdamai sama cermin. Kemenangan kecil, tapi cukup. 🤳 #swafoto #harianku #tenang"],
        "ootd":      ["Baju nggak perlu mencolok buat berasa nyaman. Gaya simpel hari ini. 👗 #ootd #gayaharian #simpel"],
        "bedroom":   ["Piyama nyaman, selimut tebal, dan nggak ada rencana. Ini baru mood akhir pekan. 🛌 #santai #harilibur #nyaman"],
        "flower":    ["Bunga mekar penuh — kayak alam bilang selamat pagi. 🌺 #bunga #alamindonesia #tenang"],
        "travel":    ["Jelajah Indonesia emang nggak pernah kehabisan tempat cantik. ✈️ #wonderfulindonesia #jalanjalan #pesonaindonesia",
                       "Dari Bali sampai Raja Ampat, tiap tempat punya cerita sendiri. 🧳 #jelajahindonesia #liburan #harianku",
                       "Indonesia itu luas, keindahannya nggak ada habisnya. 🇮🇩 #pesonaindonesia #wonderfulindonesia #jalanjalan",
                       "Tiap kali traveling, selalu nemu sudut baru yang bikin terpukau. 📸 #jelajahindonesia #jalanjalan #petualangan"],
        "cinema":    ["Berasa kayak satu adegan dari film yang belum tayang. 🎬 #sinematik #mood #fotografi"],
        "portrait":  ["Beberapa foto nggak butuh cerita — cukup sama suasananya. 📷 #potret #harianku #tenang",
                       "Cahaya senja nangkep momen ini, langsung jatuh cinta. #potret #cahayaalami #mood",
                       "Sekadar satu momen tenang yang pengen ku simpan. #harianku #potret #pesonaindonesia"],
    },
    "de": {
        "kimono":    ["Ein Stück Japan im Alltag — Tee in der Hand, die Welt steht still. 🍵 #tradition #japan #ruhe"],
        "hanfu":     ["Traditionelle Kleidung, ein Hauch von Geschichte. 🌸 #kultur #ootd #tradition"],
        "bride":     ["Das Kleid anprobiert — emotionaler als gedacht. 🤍 #hochzeit #liebe #braut"],
        "beach":     ["Salzluft, Wellenrauschen, Gedanken abschalten. Strandmodus an. ☀️ #strand #urlaub #sommer",
                       "Füße im Sand ist quasi Therapie. 🌊 #meer #entspannung #reiselust"],
        "goldenhour":["Goldene Stunde verwandelt alles Gewöhnliche in Erinnerungen. 🌅 #goldenhour #sonnenuntergang #reise"],
        "winter":    ["Eingepackt und endlich zugeben: Winter hat seinen eigenen Zauber. 🧣 #winter #schnee #gemütlich"],
        "rain":      ["Regenschirm auf, Playlist an, ziellos unterwegs. ☔ #regen #stadtleben #entspannt"],
        "cafe":      ["Zu viele Croissants bestellt. Null Reue. 🥐 #café #genuss #reiselust"],
        "night":     ["Neonlichter und stille Straßen — meine Art von Mitternacht. 🌃 #nacht #stadtleben #stimmung"],
        "street":    ["Ohne Plan durch die Stadt — die beste Art von Freiheit. 🚶 #streetstyle #stadtleben #reise",
                       "Jede Gasse erzählt eine Geschichte. Einfach weitergehen und staunen. 🏘️ #altstadt #europa #entdecken"],
        "gym":       ["Jede Wiederholung war heute lauter als die Ausreden von gestern. 💪 #fitness #stärke #routine"],
        "running":   ["Nur ich, meine Playlist und ein schweißtreibendes Finish. 🏃 #laufen #sport #alltag"],
        "swim":      ["Pool-Tage sind die beste Art von Reset. 💦 #pool #sommer #entspannung"],
        "dance":     ["Beim Tanzen wird die ganze Welt still. 💃 #tanz #freude #freiheit"],
        "selfie":    ["Heute Frieden mit dem Spiegel geschlossen. Kleiner Sieg. 🪞 #selfie #alltag #ichzeit"],
        "ootd":      ["Das Outfit muss nicht laut sein, um sich gut anzufühlen. 👗 #ootd #stil #schlicht"],
        "bedroom":   ["Gemütlicher Pyjama, Gewichtsdecke, absolut keine Pläne. 🛌 #wochenende #ruhetag #gemütlich"],
        "flower":    ["Blumen fühlen sich immer wie ein leises Ja vom Universum an. 🌷 #blumen #frühling #ruhe"],
        "travel":    ["Neue Stadt, dieselben großen Augen. Aufgeregt über die kleinsten Dinge. ✈️ #reise #fernweh #europa",
                       "Reisen lehrt dich, dass die Welt gleichzeitig riesig und klein ist. 🧳 #reiselust #europa #entdecken",
                       "Jeder Ort hat seine eigene Magie — man muss nur hinschauen. 📸 #travel #europa #abenteuer"],
        "cinema":    ["Fühlt sich an wie eine Szene aus einem Film, der noch nicht erschienen ist. 🎬 #filmisch #stimmung"],
        "portrait":  ["Manche Bilder brauchen keine Geschichte — nur Stimmung. 📷 #portrait #natürlich #moment"],
    },
    "fr": {
        "kimono":    ["Un week-end en kimono, thé à la main — comme un pas dans une autre époque. 🍵 #tradition #japon #sérénité"],
        "hanfu":     ["Journée en tenue traditionnelle, les manches virevoltent, l'esprit s'envole. 🌸 #culture #ootd #rêverie"],
        "bride":     ["Essayer la robe était plus émouvant que prévu. 🤍 #mariage #amour #moments"],
        "beach":     ["Crème solaire, téléphone éteint, cerveau au repos. Mode plage activé. ☀️ #plage #été #détente",
                       "Les pieds dans le sable, c'est ma thérapie. 🌊 #mer #vacances #tranquille"],
        "goldenhour":["L'heure dorée transforme tout ce qui est ordinaire en souvenir. 🌅 #coucherdesoleil #lumière #voyage"],
        "winter":    ["Emmitouflé et enfin prêt à admettre que l'hiver a sa propre magie. 🧣 #hiver #neige #cocooning"],
        "rain":      ["Parapluie ouvert, playlist lancée, direction nulle part. ☔ #pluie #ville #douceur"],
        "cafe":      ["Trop de pâtisseries commandées. Zéro regret. 🥐 #café #gourmandise #bonheur"],
        "night":     ["Néons et rues silencieuses — mon genre de minuit. 🌃 #nuit #ville #ambiance"],
        "street":    ["Flâner dans la ville sans carte, ma liberté préférée. 🚶 #rues #ville #voyage",
                       "Chaque ruelle raconte une histoire ici. 🏘️ #vieilleville #europe #découverte"],
        "gym":       ["Chaque répétition plus forte que les excuses d'hier. 💪 #sport #force #routine"],
        "running":   ["Juste moi, ma playlist et une arrivée en sueur. 🏃 #course #cardio #quotidien"],
        "swim":      ["Les jours de piscine sont mon reset préféré. 💦 #piscine #été #détente"],
        "dance":     ["Quand je danse, le monde entier se tait. 💃 #danse #joie #liberté"],
        "selfie":    ["Fait la paix avec le miroir aujourd'hui. Petite victoire. 🪞 #selfie #douceur #quotidien"],
        "ootd":      ["La tenue n'a pas besoin d'être voyante pour faire du bien. 👗 #ootd #style #minimaliste"],
        "bedroom":   ["Pyjama douillet, couverture lestée, absolument aucun plan. 🛌 #dimanche #repos #cocooning"],
        "flower":    ["Les pivoines, c'est toujours un petit oui de l'univers. 🌷 #fleurs #printemps #calme"],
        "travel":    ["Nouvelle ville, mêmes yeux émerveillés. Excité par les moindres détails. ✈️ #voyage #europe #découverte",
                       "Voyager m'apprend que le monde est à la fois immense et tout petit. 🧳 #voyager #europe #aventure",
                       "Chaque lieu a sa propre magie — il suffit de regarder. 📸 #travel #europe #exploration"],
        "cinema":    ["On dirait une scène d'un film pas encore sorti. 🎬 #cinématique #ambiance"],
        "portrait":  ["Certaines photos n'ont pas besoin d'histoire — juste d'une ambiance. 📷 #portrait #naturel #moment"],
    },
    "it": {
        "kimono":    ["Un fine settimana in kimono, tè in mano — sembra un passo in un'altra epoca. 🍵 #tradizione #giappone #calma"],
        "hanfu":     ["Giornata in abito tradizionale, le maniche danzano, lo spirito vola. 🌸 #cultura #ootd #sogno"],
        "bride":     ["Provare l'abito è stato più emozionante del previsto. 🤍 #matrimonio #amore #momenti"],
        "beach":     ["Crema solare, telefono spento, mente in pausa. Modalità spiaggia attivata. ☀️ #spiaggia #estate #relax",
                       "Piedi nella sabbia, praticamente terapia a questo punto. 🌊 #mare #vacanze #tranquillo"],
        "goldenhour":["L'ora d'oro trasforma tutto l'ordinario in un ricordo. 🌅 #tramonto #luce #viaggio"],
        "winter":    ["Imbacuccato e finalmente pronto ad ammettere che l'inverno ha la sua magia. 🧣 #inverno #neve #accogliente"],
        "rain":      ["Ombrello aperto, playlist accesa, direzione nessuna. ☔ #pioggia #città #dolcezza"],
        "cafe":      ["Troppe paste ordinate. Zero rimpianti. 🥐 #caffè #dolcezza #felicità"],
        "night":     ["Neon e strade silenziose — il mio tipo di mezzanotte. 🌃 #notte #città #atmosfera"],
        "street":    ["Vagare per la città senza mappa — la mia libertà preferita. 🚶 #strade #città #viaggio",
                       "Ogni vicolo racconta una storia qui. 🏘️ #centrostorico #europa #scoperta"],
        "gym":       ["Ogni ripetizione oggi più forte delle scuse di ieri. 💪 #fitness #forza #costanza"],
        "running":   ["Solo io, la mia playlist e un arrivo sudato. 🏃 #corsa #cardio #routine"],
        "swim":      ["I giorni in piscina sono il mio reset preferito. 💦 #piscina #estate #relax"],
        "dance":     ["Quando ballo, tutto il mondo fa silenzio. 💃 #danza #gioia #libertà"],
        "selfie":    ["Fatto pace con lo specchio oggi. Piccola vittoria. 🪞 #selfie #dolcezza #quotidiano"],
        "ootd":      ["L'outfit non deve essere appariscente per stare bene. 👗 #ootd #stile #minimal"],
        "bedroom":   ["Pigiama comodo, coperta pesante, assolutamente nessun piano. 🛌 #domenica #riposo #relax"],
        "flower":    ["I fiori sembrano sempre un piccolo sì dall'universo. 🌷 #fiori #primavera #calma"],
        "travel":    ["Nuova città, stessi occhi spalancati. Entusiasta per le cose più piccole. ✈️ #viaggio #europa #scoperta",
                       "Viaggiare insegna che il mondo è immenso e piccolo allo stesso tempo. 🧳 #viaggiare #europa #avventura",
                       "Ogni posto ha la sua magia — basta guardare. 📸 #travel #italia #bellezza"],
        "cinema":    ["Sembra una scena di un film non ancora uscito. 🎬 #cinematico #atmosfera"],
        "portrait":  ["Alcune foto non hanno bisogno di una storia — basta l'atmosfera. 📷 #ritratto #naturale #momento"],
    },
    "es": {
        "kimono":    ["Un fin de semana en kimono, té en mano — como un paso a otra época. 🍵 #tradición #japón #calma"],
        "hanfu":     ["Día de traje tradicional, las mangas danzan, el espíritu vuela. 🌸 #cultura #ootd #sueño"],
        "bride":     ["Probarse el vestido fue más emotivo de lo esperado. 🤍 #boda #amor #momentos"],
        "beach":     ["Protector solar, teléfono apagado, mente en pausa. Modo playa activado. ☀️ #playa #verano #relax",
                       "Pies en la arena, básicamente terapia. 🌊 #mar #vacaciones #tranquilo"],
        "goldenhour":["La hora dorada transforma lo ordinario en recuerdo. 🌅 #atardecer #luz #viaje"],
        "winter":    ["Abrigado y listo para admitir que el invierno tiene su propia magia. 🧣 #invierno #nieve #acogedor"],
        "rain":      ["Paraguas abierto, playlist puesta, dirección ninguna. ☔ #lluvia #ciudad #tranquilidad"],
        "cafe":      ["Demasiados cruasanes pedidos. Cero arrepentimientos. 🥐 #café #dulzura #felicidad"],
        "night":     ["Neones y calles silenciosas — mi tipo de medianoche. 🌃 #noche #ciudad #ambiente"],
        "street":    ["Callejear sin mapa por la ciudad — mi libertad favorita. 🚶 #calles #ciudad #viaje",
                       "Cada callejón cuenta una historia aquí. 🏘️ #centrohistórico #europa #descubrimiento"],
        "gym":       ["Cada repetición hoy más fuerte que las excusas de ayer. 💪 #fitness #fuerza #constancia"],
        "running":   ["Solo yo, mi playlist y una llegada sudorosa. 🏃 #correr #cardio #rutina"],
        "swim":      ["Los días de piscina son mi reset favorito. 💦 #piscina #verano #relax"],
        "dance":     ["Cuando bailo, el mundo entero se calla. 💃 #baile #alegría #libertad"],
        "selfie":    ["Hice las paces con el espejo hoy. Pequeña victoria. 🪞 #selfie #tranquilidad #diario"],
        "ootd":      ["El outfit no necesita ser llamativo para sentirse bien. 👗 #ootd #estilo #minimalista"],
        "bedroom":   ["Pijama cómodo, manta pesada, absolutamente ningún plan. 🛌 #domingo #descanso #relax"],
        "flower":    ["Las flores siempre se sienten como un pequeño sí del universo. 🌷 #flores #primavera #calma"],
        "travel":    ["Nueva ciudad, mismos ojos bien abiertos. Emocionado por las cosas más pequeñas. ✈️ #viaje #europa #descubrir",
                       "Viajar enseña que el mundo es inmenso y pequeño a la vez. 🧳 #viajar #europa #aventura",
                       "Cada lugar tiene su propia magia — solo hay que mirar. 📸 #travel #españa #belleza"],
        "cinema":    ["Parece una escena de una película que aún no se ha estrenado. 🎬 #cinematográfico #ambiente"],
        "portrait":  ["Algunas fotos no necesitan historia — solo atmósfera. 📷 #retrato #natural #momento"],
    },
    "pt": {
        "kimono":    ["Um fim de semana de kimono, chá na mão — parece um passo noutra época. 🍵 #tradição #japão #calma"],
        "hanfu":     ["Dia de roupa tradicional, as mangas dançam, o espírito voa. 🌸 #cultura #ootd #sonho"],
        "bride":     ["Experimentar o vestido foi mais emocionante do que esperava. 🤍 #casamento #amor #momentos"],
        "beach":     ["Protetor solar, telemóvel desligado, mente em pausa. Modo praia ativado. ☀️ #praia #verão #relax",
                       "Pés na areia, basicamente terapia. 🌊 #mar #férias #tranquilo"],
        "goldenhour":["A hora dourada transforma tudo o que é comum em memória. 🌅 #pôrdosol #luz #viagem"],
        "winter":    ["Agasalhado e finalmente pronto para admitir que o inverno tem a sua magia. 🧣 #inverno #neve #acolhedor"],
        "rain":      ["Guarda-chuva aberto, playlist ligada, direção nenhuma. ☔ #chuva #cidade #tranquilidade"],
        "cafe":      ["Croissants a mais encomendados. Zero arrependimentos. 🥐 #café #doçura #felicidade"],
        "night":     ["Néons e ruas silenciosas — o meu tipo de meia-noite. 🌃 #noite #cidade #ambiente"],
        "street":    ["Passear pela cidade sem mapa — a minha liberdade preferida. 🚶 #ruas #cidade #viagem",
                       "Cada ruela conta uma história aqui. 🏘️ #centrohistórico #europa #descoberta"],
        "gym":       ["Cada repetição hoje mais forte que as desculpas de ontem. 💪 #fitness #força #constância"],
        "running":   ["Só eu, a minha playlist e uma chegada suada. 🏃 #corrida #cardio #rotina"],
        "swim":      ["Dias de piscina são o meu reset favorito. 💦 #piscina #verão #relax"],
        "dance":     ["Quando danço, o mundo inteiro fica em silêncio. 💃 #dança #alegria #liberdade"],
        "selfie":    ["Fiz as pazes com o espelho hoje. Pequena vitória. 🪞 #selfie #tranquilidade #diário"],
        "ootd":      ["O outfit não precisa de ser chamativo para nos fazer sentir bem. 👗 #ootd #estilo #minimalista"],
        "bedroom":   ["Pijama confortável, cobertor pesado, absolutamente nenhum plano. 🛌 #domingo #descanso #relax"],
        "flower":    ["As flores parecem sempre um pequeno sim do universo. 🌷 #flores #primavera #calma"],
        "travel":    ["Nova cidade, mesmos olhos arregalados. Entusiasmado com as coisas mais pequenas. ✈️ #viagem #europa #descobrir",
                       "Viajar ensina que o mundo é imenso e pequeno ao mesmo tempo. 🧳 #viajar #europa #aventura",
                       "Cada lugar tem a sua própria magia — basta olhar. 📸 #travel #portugal #beleza"],
        "cinema":    ["Parece uma cena de um filme que ainda não estreou. 🎬 #cinematográfico #ambiente"],
        "portrait":  ["Algumas fotos não precisam de história — basta a atmosfera. 📷 #retrato #natural #momento"],
    },
    "nl": {
        "kimono":    ["Een weekend in kimono, thee in de hand — voelt als een stap in een ander tijdperk. 🍵 #traditie #japan #rust"],
        "hanfu":     ["Dag in traditionele kleding, de mouwen dansen, de geest vliegt. 🌸 #cultuur #ootd #droom"],
        "bride":     ["De jurk passen was emotioneler dan verwacht. 🤍 #bruiloft #liefde #momenten"],
        "beach":     ["Zonnebrand, telefoon uit, hoofd leeg. Strandmodus aan. ☀️ #strand #zomer #ontspanning",
                       "Voeten in het zand is eigenlijk therapie. 🌊 #zee #vakantie #rustig"],
        "goldenhour":["Het gouden uur maakt alles gewoons tot een herinnering. 🌅 #zonsondergang #licht #reizen"],
        "winter":    ["Ingepakt en eindelijk toegeven: winter heeft zijn eigen magie. 🧣 #winter #sneeuw #gezellig"],
        "rain":      ["Paraplu open, playlist aan, nergens naartoe. ☔ #regen #stadsleven #rustig"],
        "cafe":      ["Te veel gebak besteld. Nul spijt. 🥐 #café #genieten #geluk"],
        "night":     ["Neonlichten en stille straten — mijn soort middernacht. 🌃 #nacht #stad #sfeer"],
        "street":    ["Zonder kaart door de stad — mijn favoriete soort vrijheid. 🚶 #straten #stad #reizen",
                       "Elk steegje vertelt hier een verhaal. 🏘️ #oudestad #europa #ontdekken"],
        "gym":       ["Elke herhaling vandaag luider dan de excuses van gisteren. 💪 #fitness #kracht #routine"],
        "running":   ["Alleen ik, mijn playlist en een bezwete finish. 🏃 #hardlopen #cardio #dagelijks"],
        "swim":      ["Zwembaddagen zijn mijn favoriete reset. 💦 #zwembad #zomer #ontspanning"],
        "dance":     ["Als ik dans, wordt de hele wereld stil. 💃 #dans #vreugde #vrijheid"],
        "selfie":    ["Vandaag vrede gesloten met de spiegel. Kleine overwinning. 🪞 #selfie #rustig #dagelijks"],
        "ootd":      ["De outfit hoeft niet luid te zijn om goed te voelen. 👗 #ootd #stijl #minimalistisch"],
        "bedroom":   ["Gezellige pyjama, verzwaringsdeken, absoluut geen plannen. 🛌 #weekend #rustdag #gezellig"],
        "flower":    ["Bloemen voelen altijd als een zacht ja van het universum. 🌷 #bloemen #lente #rust"],
        "travel":    ["Nieuwe stad, dezelfde grote ogen. Enthousiast over de kleinste dingen. ✈️ #reizen #europa #ontdekken",
                       "Reizen leert je dat de wereld tegelijk enorm en klein is. 🧳 #reislust #europa #avontuur",
                       "Elke plek heeft zijn eigen magie — je hoeft alleen maar te kijken. 📸 #travel #nederland #mooi"],
        "cinema":    ["Voelt als een scène uit een film die nog niet uit is. 🎬 #filmisch #sfeer"],
        "portrait":  ["Sommige foto's hebben geen verhaal nodig — alleen sfeer. 📷 #portret #natuurlijk #moment"],
    },
    "ar": {
        "kimono":    ["يوم بالكيمونو، فنجان شاي بيدي — شعور وكأن الوقت توقف. 🍵 #كيمونو #يوميات #سكينة"],
        "hanfu":     ["الأكمام تتراقص مع الريح والروح تحلّق. 🌸 #تراث #أزياء #يوميات"],
        "bride":     ["لحظة تجربة الفستان كانت أكثر عاطفية مما توقعت. 🤍 #عروس #حب #لحظات"],
        "beach":     ["واقي شمس، هاتف مغلق، ذهن فارغ. وضع الشاطئ مفعّل. ☀️ #بحر #صيف #استرخاء",
                       "رمل تحت القدمين، هذا هو العلاج الحقيقي. 🌊 #شاطئ #إجازة #هدوء"],
        "goldenhour":["الساعة الذهبية تحوّل كل شيء عادي إلى ذكرى. 🌅 #غروب #ذكريات #سفر"],
        "winter":    ["أخيراً اعترفت أن للشتاء سحره الخاص. 🧣 #شتاء #دفء #يوميات"],
        "rain":      ["مظلة مفتوحة، موسيقى، ولا وجهة محددة. متعة يوم ماطر. ☔ #مطر #تأمل #هدوء"],
        "cafe":      ["طلبت حلويات أكثر من اللازم. لا ندم أبداً. 🥐 #قهوة #يوميات #سعادة"],
        "night":     ["أضواء النيون والشوارع الهادئة — هذا نوع الليل الذي أحبه. 🌃 #ليل #مدينة #أجواء"],
        "street":    ["المشي بلا خريطة في المدينة هو حريتي المفضلة. #شوارع #تجوال #يوميات"],
        "gym":       ["كل تكرار اليوم كان أقوى من أعذار الأمس. 💪 #رياضة #قوة #انضباط"],
        "running":   ["ركضت مع نسيم المساء وانتعشت روحي. 🏃 #جري #رياضة #يوميات"],
        "swim":      ["بعد بضع لفات في المسبح، الجسم والروح يرتاحان. 💦 #سباحة #صيف #انتعاش"],
        "dance":     ["حين أرقص، العالم كله يصمت للحظة. 💃 #رقص #شغف #حرية"],
        "selfie":    ["تصالحت مع المرآة اليوم. انتصار صغير لكنه يكفي. 🪞 #سيلفي #يوميات #أنا"],
        "ootd":      ["لا يحتاج اللبس أن يكون صاخباً ليمنحك شعوراً جيداً. 👗 #اليوم_لبست #ستايل #بساطة"],
        "bedroom":   ["بيجاما، بطانية ثقيلة، ولا أي خطة. هذا هو الجو. 🛌 #راحة #عطلة #هدوء"],
        "flower":    ["الورود دائماً تشعرني بأن الكون يومئ بالموافقة. 🌷 #ورد #جمال #سكينة"],
        "travel":    ["مدينة مختلفة، نفس العيون المندهشة. متحمس لأبسط الأشياء. ✈️ #سفر #ترحال #يوميات",
                       "السفر يعلّمك أن العالم واسع وصغير في نفس الوقت. 🧳 #سفر #استكشاف #مغامرة",
                       "كل مكان له سحره الخاص — فقط عليك أن تنظر. 📸 #سفر #جمال #ذكريات"],
        "cinema":    ["يبدو وكأنه مشهد من فيلم لم يُعرض بعد. 🎬 #سينمائي #أجواء #فن"],
        "portrait":  ["بعض الصور لا تحتاج قصة — يكفيها الأجواء. 📷 #بورتريه #يوميات #فن",
                       "الضوء الخلفي فاجأني وأحببت النتيجة. #بورتريه #إضاءة_طبيعية #لحظات",
                       "مجرد لحظة هادئة أردت الاحتفاظ بها. #يوميات #بورتريه #أجواء"],
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
        "ms": "Tulis satu kapsyen ringkas dalam Bahasa Melayu (maksimum 3 baris) dengan gaya "
              "orang Malaysia berkongsi gambar sendiri di media sosial. Sertakan 2-4 hashtag "
              "dan 1-2 emoji. Jangan sebut ini janaan AI atau prompt. Gunakan nada santai dan "
              f"mesra Malaysia. Petunjuk suasana: {scene}. Penerangan asal: {raw}",
        "id": "Tulis satu caption singkat dalam Bahasa Indonesia (maksimal 3 baris) dengan gaya "
              "orang Indonesia yang membagikan fotonya sendiri di media sosial. Sertakan 2-4 hashtag "
              "dan 1-2 emoji. Jangan menyebut ini buatan AI atau prompt. Pakai nada santai dan "
              f"akrab khas Indonesia. Petunjuk suasana: {scene}. Deskripsi asli: {raw}",
        "ko": "젊은 사용자가 직접 올리는 것처럼 한국어 1인칭 짧은 글(3줄 이내)을 작성하세요. "
              "2-4개의 해시태그와 1-2개의 이모지를 포함하세요. AI나 프롬프트에 대해서는 언급하지 마세요. "
              f"장면 힌트: {scene}. 원본 설명: {raw}",
        "ar": "اكتب تعليقاً قصيراً بالعربية (3 أسطر كحد أقصى) بأسلوب شخص شاب يشارك صوره على وسائل التواصل. "
              "أضف 2-4 هاشتاقات و1-2 إيموجي. لا تذكر أنه مولّد بالذكاء الاصطناعي. "
              f"تلميح المشهد: {scene}. الوصف الأصلي: {raw}",
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
# content-aware captions (differentiated, built from the article's own
# title + excerpt) — avoids the homogeneous template output for TW media.
# ---------------------------------------------------------------------------

_STOPWORDS = set("的了是在也和與及並而或但很更最都會就把讓從對於這那些一個我們你他她它"
                 "台灣台湾之美日常分享推薦介紹如何為何什麼怎麼可以已經還有這樣那樣")


def _zh_hashtags_from(text: str, scene: str, source: str) -> list[str]:
    """Derive up to 3 topical hashtags — universal strategy for all content types.

    Priority:
    1. Extract existing #hashtags from original content (e.g. XHS native tags)
    2. Scene-aware keyword derivation (varies by content topic)
    3. Randomized fallback pool (avoids all posts using same defaults)

    Designed to avoid repetition: uses text hash as seed for fallback selection,
    ensuring different content gets different fallback tags.
    """
    tags: list[str] = []

    # Step 1: Extract existing hashtags from original content (highest priority)
    existing_tags = re.findall(r"#[\w\u4e00-\u9fff\u3400-\u4dbf]+", text or "")
    for t in existing_tags:
        if t not in tags and 2 <= len(t) <= 20:
            tags.append(t)
        if len(tags) >= 3:
            return tags[:3]

    # Step 2: Scene + keyword-based derivation (broad coverage)
    SCENE_KEYWORDS = {
        "food": ["美食", "料理", "食譜", "烘焙", "甜點", "咖啡", "探店", "餐廳",
                 "夜市", "小吃", "做饭", "下厨", "食材", "早餐", "晚餐", "火锅"],
        "travel": ["旅行", "旅遊", "出遊", "風景", "海邊", "山", "露營", "民宿",
                   "打卡", "景點", "自由行", "度假", "海岛", "古镇", "公路旅行"],
        "fashion": ["穿搭", "時尚", "球鞋", "包包", "配飾", "潮流", "新品", "搭配",
                    "ootd", "look", "风格", "复古", "极简", "vintage"],
        "beauty": ["護膚", "彩妝", "防曬", "底妝", "眼妝", "唇膏", "美甲", "髮型",
                   "护肤", "化妆", "面膜", "精华", "素颜", "变美"],
        "fitness": ["健身", "減肥", "瑜伽", "跑步", "運動", "增肌", "体态", "塑形",
                    "拉伸", "有氧", "力量", "打卡"],
        "life": ["日常", "生活", "記錄", "分享", "心情", "感悟", "日記", "碎片",
                 "plog", "vlog", "宅家", "独居"],
        "work": ["職場", "工作", "創業", "副業", "面試", "辭職", "自由職業", "远程",
                 "升职", "离职", "求职", "简历", "考研", "学习"],
        "pet": ["寵物", "貓", "狗", "猫咪", "狗狗", "萌宠", "铲屎官", "养猫", "养狗"],
        "home": ["家居", "裝修", "收納", "佈置", "居家", "改造", "租房", "好物"],
        "tech": ["數碼", "手機", "電腦", "app", "开箱", "测评", "科技", "AI", "编程"],
        "parent": ["育兒", "寶寶", "早教", "輔食", "孕期", "母婴", "带娃", "亲子"],
        "drama": ["追劇", "影評", "電影", "電視劇", "動漫", "剧荒", "综艺", "推荐"],
    }

    low = (text or "").lower()
    # Detect which scenes match the content
    matched_scenes = []
    for sc, keywords in SCENE_KEYWORDS.items():
        if any(k.lower() in low for k in keywords):
            matched_scenes.append(sc)

    # Pick keywords from matched scenes
    for sc in matched_scenes:
        for k in SCENE_KEYWORDS[sc]:
            if k.lower() in low and f"#{k}" not in tags:
                tags.append(f"#{k}")
            if len(tags) >= 3:
                return tags[:3]

    # Step 3: Randomized fallback (seeded by text content to avoid all-same defaults)
    seed = sum(ord(c) for c in (text or "")[:100]) if text else 0

    # Scene-based fallback pools
    FALLBACK_POOLS = {
        "food": ["#美食分享", "#今日美食", "#吃货日常", "#探店打卡", "#自制美食", "#下厨房"],
        "travel": ["#旅行日记", "#出发吧", "#风景这边独好", "#周末出游", "#一路风景", "#说走就走"],
        "fashion": ["#今日穿搭", "#每日look", "#风格穿搭", "#时尚灵感", "#衣橱分享", "#好看推荐"],
        "beauty": ["#护肤心得", "#今日妆容", "#美妆分享", "#变美日记", "#好物安利", "#素颜日记"],
        "fitness": ["#运动打卡", "#健身日常", "#自律生活", "#每日运动", "#身材管理", "#健康生活"],
        "life": ["#生活碎片", "#日常记录", "#今日份", "#随手拍", "#平凡生活", "#小确幸"],
        "work": ["#职场日常", "#工作心得", "#成长记录", "#学习笔记", "#效率提升", "#干货分享"],
        "pet": ["#萌宠日常", "#猫咪日常", "#铲屎官", "#宠物日记", "#毛孩子", "#吸猫"],
        "home": ["#家居灵感", "#居家日常", "#收纳整理", "#租房改造", "#生活好物", "#温馨小窝"],
        "tech": ["#数码好物", "#科技控", "#开箱分享", "#好物推荐", "#效率工具", "#极客"],
        "parent": ["#育儿日常", "#宝宝成长", "#带娃记录", "#新手妈妈", "#亲子时光", "#早教"],
        "drama": ["#追剧日常", "#好剧推荐", "#影视推荐", "#剧荒救星", "#周末追剧", "#必看好剧"],
    }
    GENERIC_FALLBACK = [
        "#生活记录", "#好心情", "#日常", "#每日分享", "#今日份",
        "#随手记录", "#灵感", "#笔记", "#推荐", "#分享日常",
        "#值得记录", "#小确幸", "#好物分享", "#打卡",
    ]

    # Use matched scene pool or generic
    if matched_scenes:
        pool = FALLBACK_POOLS.get(matched_scenes[0], GENERIC_FALLBACK)
    else:
        pool = GENERIC_FALLBACK

    # Source-specific override
    source_pools = {
        "gq": ["#GQ品味", "#男性时尚", "#精致生活"],
        "sony": ["#摄影日常", "#镜头记录", "#光影"],
        "shoppingdesign": ["#设计生活", "#美学日常", "#创意灵感"],
    }
    if source in source_pools:
        pool = source_pools[source]

    # Seeded selection from pool (different text → different tags)
    import random as _rng
    r = _rng.Random(seed)
    remaining_needed = 3 - len(tags)
    available = [t for t in pool if t not in tags]
    if len(available) >= remaining_needed:
        picks = r.sample(available, remaining_needed)
    else:
        picks = available
    tags.extend(picks)

    return tags[:3]


# ---- title semantics → rewritten caption (no fixed opener/closer template) ----

# strip site suffix / decorative marks, keep the meaningful topic phrase
def _clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "")).strip()
    t = re.split(r"[|｜\-–—]{1,}\s*(?:GQ|Shopping ?Design|SONY|Alpha).*$", t)[0].strip()
    # strip decorative interview marks ❰ ❱ and leading brackets/labels
    t = t.replace("❰", "").replace("❱", "")
    t = re.sub(r"^[【】\[\]（）()、，,\s]+", "", t)
    # drop trailing "feat. …" credit tails and dangling separators
    t = re.split(r"\s*feat\.\s*", t, flags=re.I)[0].strip()
    return t.strip("｜|-–—、，, ").strip()


# intent classification from title keywords → varied comment sentence banks.
# Each bank has many options; a title-seeded pick keeps posts differentiated.
_COMMENT_BANKS = {
    "interview": [
        "聽他們聊創作的心路，收穫比想像中多。",
        "這場對談把幕後的堅持都講透了。",
        "專訪裡的每句話都很有份量。",
        "看完更懂一件作品背後要花多少功夫。",
    ],
    "gear": [
        "器材的細節決定成品的質感，這篇講得很到位。",
        "看完對這組配置更有感覺了。",
        "規格之外，實拍的手感才是重點。",
        "工欲善其事，這些眉角值得記下來。",
    ],
    "exhibition": [
        "光是看展場照就想親自跑一趟。",
        "策展的巧思藏在每個角落。",
        "這種把生活變成展覽的做法太迷人。",
        "展期內一定要找時間去朝聖。",
    ],
    "travel": [
        "這個地方被拍得讓人很想立刻出發。",
        "台灣的風景總是不經意就驚豔到你。",
        "把這裡加進口袋名單了。",
        "旅途中最迷人的往往是這些日常畫面。",
    ],
    "food": [
        "光看照片就餓了，這間必須排進口袋名單。",
        "在地的味道最能打動人。",
        "這一桌看起來就很療癒。",
        "美食配上這種氛圍，誰能抵擋。",
    ],
    "design": [
        "好的設計會讓日常變得更有溫度。",
        "細節裡的美學最耐看。",
        "這種質感的東西總讓人多看兩眼。",
        "設計把功能與美感揉在一起，很加分。",
    ],
    "culture": [
        "在地文化的故事總是特別動人。",
        "這些畫面藏著台灣的生活感。",
        "把台灣感性拍得恰到好處。",
        "越熟悉的日常，越值得被記錄。",
    ],
    "generic": [
        "這篇的視角很對我的味。",
        "把細節拍得很有感覺。",
        "看完心情都變好了。",
        "這種內容百看不膩。",
    ],
}


def _title_intent(title: str, source: str) -> str:
    t = title or ""
    if any(k in t for k in ["專訪", "訪談", "對談", "專欄", "人物", "封面"]):
        return "interview"
    if any(k in t for k in ["鏡頭", "相機", "麥克風", "α", "拍攝", "攝影", "收音", "GM", "F1", "F2", "mm"]):
        return "gear"
    if any(k in t for k in ["展", "博覽", "美術館", "特展", "策展"]):
        return "exhibition"
    if any(k in t for k in ["咖啡", "美食", "餐", "吃", "料理", "甜點", "小吃"]):
        return "food"
    if any(k in t for k in ["設計", "選物", "品牌", "家具", "文創", "工藝"]):
        return "design"
    if any(k in t for k in ["旅", "遊", "景點", "秘境", "住宿", "旅宿", "步道", "小鎮", "地圖"]):
        return "travel"
    if any(k in t for k in ["台灣感性", "文化", "在地", "部落", "祭"]):
        return "culture"
    if source == "sony":
        return "gear"
    if source == "shoppingdesign":
        return "design"
    return "generic"


def content_aware_caption(title: str, excerpt: str, scene: str, source: str,
                          idx: int) -> str:
    """Rewrite a differentiated zh_hant caption based on the TITLE's semantics.

    Strategy (no LLM): take the article's own topic phrase from the title, add a
    freshly-composed comment chosen from an intent-specific bank, seeded by the
    title so different titles yield different phrasing (avoids homogeneity)."""
    ct = _clean_title(title)
    topic = ct[:38] if ct else _first_sentence(excerpt, 34) or "台灣的日常風景"
    intent = _title_intent(ct + " " + (excerpt or ""), source)
    bank = _COMMENT_BANKS.get(intent, _COMMENT_BANKS["generic"])
    # seed choice by the title text so it's deterministic yet varied per article
    seed = sum(ord(c) for c in ct) if ct else idx
    comment = bank[(seed + idx) % len(bank)]

    # vary the sentence structure by a title-seeded pattern (not a fixed opener)
    patterns = [
        "{topic}｜{comment}",
        "{topic}。{comment}",
        "分享一篇：{topic}——{comment}",
        "{comment}《{topic}》",
        "最近在看《{topic}》，{comment}",
    ]
    pat = patterns[seed % len(patterns)]
    body = pat.format(topic=topic, comment=comment)
    body = body[:120]
    # Deduplicate: don't append hashtags already present in the body
    existing_in_body = set(re.findall(r"#[\w\u4e00-\u9fff\u3400-\u4dbf]+", body))
    all_tags = _zh_hashtags_from((ct + " " + (excerpt or "")), scene, source)
    deduped_tags = [t for t in all_tags if t not in existing_in_body]
    if deduped_tags:
        return f"{body} {' '.join(deduped_tags)}"
    return body


def _first_sentence(excerpt: str, limit: int = 46) -> str:
    if not excerpt:
        return ""
    parts = re.split(r"[。！？!?；;\n]", excerpt)
    for p in parts:
        p = p.strip()
        if len(p) >= 10:
            if len(p) <= limit:
                return p
            head = p[:limit]
            m = max(head.rfind("，"), head.rfind("、"), head.rfind("："), head.rfind(" "))
            return head[:m] if m >= 12 else head
    return excerpt[:limit].strip()


def llm_rewrite_from_title(title: str, excerpt: str, source: str) -> str | None:
    """If an OpenAI-compatible text LLM is configured, rewrite a fresh, natural
    繁體中文（台灣語境）first-person caption from the article's TITLE semantics
    (paraphrase — do NOT copy the title verbatim). Returns None if no LLM."""
    api_base = os.getenv("LLM_TEXT_API_BASE") or os.getenv("LLM_API_BASE")
    api_key = os.getenv("LLM_TEXT_API_KEY") or os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_TEXT_MODEL") or os.getenv("LLM_MODEL")
    if not (api_base and api_key and model):
        return None
    import requests
    ct = _clean_title(title)
    prompt = (
        "你是台灣在地的社群小編。根據以下文章標題（與摘要）的語意，"
        "用『繁體中文、台灣語氣』重新改寫一段第一人稱分享文案（1~2 句，不超過 3 行）。"
        "要求：不要照抄標題原句、用自己的話重新表達；語氣自然口語、每則都要不一樣；"
        "帶 2-3 個貼近主題的 hashtag、最多 1 個 emoji；不要提到 AI/生成/提示詞。\n"
        f"來源：{source}\n標題：{ct}\n摘要：{(excerpt or '')[:200]}"
    )
    try:
        r = requests.post(
            api_base.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model,
                  "messages": [
                      {"role": "system", "content": "只輸出文案本身，使用繁體中文。"},
                      {"role": "user", "content": prompt}],
                  "temperature": 0.9, "max_tokens": 160},
            timeout=30)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"].strip()
        print(f"[warn] LLM rewrite {r.status_code} {r.text[:150]}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] LLM rewrite err {e}", file=sys.stderr)
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
    content_aware: bool = False,
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
            orig_title = row.get("content", "") or ""
            excerpt = row.get("_excerpt", "") or ""
            scene = detect_scene((orig_title + " " + excerpt))
            caption: str | None = None
            if content_aware:
                # 1) prefer an LLM rewrite from the title semantics if configured
                if use_llm:
                    caption = llm_rewrite_from_title(
                        orig_title, excerpt, row.get("_source", ""))
                # 2) else deterministic semantic rewriter (title-driven, varied)
                if not caption:
                    caption = content_aware_caption(
                        orig_title, excerpt, scene, row.get("_source", ""), i)
            if not caption and use_llm:
                caption = llm_caption(orig_title, scene, lang)
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
    ap.add_argument("--content-aware", action="store_true",
                    help="build differentiated captions from each row's own "
                         "title + _excerpt (avoids template homogeneity; TW media)")
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
        content_aware=args.content_aware,
    )
    print(f"[OK] rewrote {n} rows → {args.output}")
    print(f"[OK] language stats: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
