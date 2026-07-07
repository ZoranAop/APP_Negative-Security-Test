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
                       "墾丁的海也太療癒，整個人瞬間放空。🌊 #墾丁 #台灣旅遊 #海邊",
                       "東北角的浪聲一來，煩惱都被沖走了。🏝️ #東北角 #台灣景點 #放空"],
        "goldenhour":["黃昏那一刻，什麼平常的畫面都會變得像回憶。🌅 #黃金時刻 #生活記錄 #好心情",
                       "夕陽把天空染成橘紅，這種台灣的傍晚百看不膩。🌇 #夕陽 #台灣之美 #放鬆"],
        "winter":    ["終於承認冬天也有它自己的浪漫，帽子圍巾一戴就是儀式感。🧣 #冬天 #穿搭 #好心情",
                       "合歡山的清晨冷得值得，早起真的沒白費。🧣 #合歡山 #台灣旅遊 #高山"],
        "rain":      ["撐傘、耳機、慢步調，沒目的地才是雨天的享受。☔ #雨天 #城市漫步 #好心情"],
        "cafe":      ["點了太多甜點，但完全沒有後悔。🥐 #咖啡日常 #週末小確幸 #好心情",
                       "巷弄裡的老宅咖啡，配一杯手沖剛剛好。☕ #台灣咖啡 #巷弄美食 #小確幸"],
        "night":     ["夜裡的霓虹和安靜的街，最適合我這種深夜遊蕩者。🌃 #夜景 #城市漫遊 #好心情",
                       "台北101點燈的夜晚，怎麼拍都好看。🌆 #台北101 #台北夜景 #台灣之美",
                       "逛夜市的煙火氣，才是台灣的靈魂。🏮 #夜市 #台灣美食 #夜生活"],
        "street":    ["漫無目的走在街上，反而收穫最多。 #街拍 #城市 #生活記錄",
                       "九份老街的紅燈籠一亮，整條街都有故事。🏮 #九份 #台灣景點 #老街",
                       "台南巷弄裡到處是驚喜，走走停停最舒服。🚶 #台南 #古都漫遊 #台灣旅遊"],
        "gym":       ["每一組舉起來的重量，都是昨天沒說出口的堅持。💪 #健身 #自律 #生活記錄"],
        "running":   ["傍晚的風剛好，跑一跑心情就整個亮起來。🏃 #跑步日常 #運動 #好心情"],
        "swim":      ["泳池裡來回幾趟，整個人都鬆了下來。💦 #泳池日常 #夏日 #好心情"],
        "dance":     ["跳起舞來的時候，好像全世界都跟著安靜了。💃 #舞蹈日常 #熱愛 #好心情"],
        "selfie":    ["跟鏡子和解了一天，這算是小小的勝利吧。🪞 #自拍 #日常 #好心情"],
        "ootd":      ["安安靜靜的一套，穿起來也能有一整天的好心情。👗 #今日穿搭 #穿搭分享 #生活"],
        "bedroom":   ["睡衣、暖被、零計畫的星期天，就是這個氛圍。🛌 #宅家 #週末 #好心情"],
        "flower":    ["買了牡丹花給自己，覺得像宇宙輕輕點頭。🌷 #花藝 #生活記錄 #好心情"],
        "travel":    ["不同的城市，一樣好奇的我。✈️ #旅行日常 #走走停停 #好心情",
                       "台灣真的怎麼玩都玩不膩，每個角落都有驚喜。🇹🇼 #台灣旅遊 #台灣之美 #走走停停",
                       "從北到南，每個地方都有自己的味道。🧳 #環島 #台灣景點 #旅行日常",
                       "又發現一個台灣秘境，這種美只有親眼看到才懂。📸 #台灣秘境 #台灣之美 #旅行"],
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
    """Derive up to 3 topical hashtags from the article's own words."""
    tags: list[str] = []
    base = {"gq": "#GQ品味", "sony": "#攝影日常", "shoppingdesign": "#設計生活"}.get(source, "#台灣")
    tags.append(base)
    KEY = ["台北", "台南", "高雄", "台中", "花蓮", "台東", "宜蘭", "九份", "墾丁",
           "阿里山", "合歡山", "日月潭", "太魯閣", "淡水", "北投", "夜市", "老街",
           "咖啡", "美食", "設計", "展覽", "攝影", "鏡頭", "人像", "風景", "旅行",
           "建築", "文創", "海邊", "山", "祭典", "部落", "小旅行", "電影", "音樂",
           "時尚", "穿搭", "球鞋", "手錶", "旅宿", "選物"]
    low = text or ""
    for k in KEY:
        if k in low and ("#" + k) not in tags:
            tags.append("#" + k)
        if len(tags) >= 3:
            break
    if len(tags) < 3:
        for extra in ["#台灣", "#生活記錄", "#編輯精選"]:
            if extra not in tags:
                tags.append(extra)
            if len(tags) >= 3:
                break
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
    tags = " ".join(_zh_hashtags_from((ct + " " + (excerpt or "")), scene, source))
    return f"{body} {tags}"


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
