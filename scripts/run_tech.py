#!/usr/bin/env python3
"""
run_tech.py — 科技资讯一键发布（多源采集 → 按发帖人角色的第一人称文案 → 纯文本发布）

流程：
    1) 采集   fetch_tech.py    （8 个科技媒体各取 N 条，科技标签，纯文本）
    2) 文案   内置角色文案生成  （发帖人第一人称口吻，融入标题/摘要/来源，带 #科技 标签，全局不重复）
    3) 发布   publish_from_tokens.py （纯文本帖，media_info type=text）

用法：
    # 50 用户，每站 3 条（8 站=24 条），轮询分发
    py -3 scripts/run_tech.py --accounts-csv accounts_test_50.csv --num-accounts 50 --per-site 3 --yes

    # 只采集+文案预演
    py -3 scripts/run_tech.py --skip-publish
"""
from __future__ import annotations

import argparse
import csv
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]
sys.path.insert(0, str(HERE))

from fetch_tech import ALL_SOURCES, SITE_CN, SITE_LANG  # noqa: E402

TAG = "科技"

# ---------------------------------------------------------------------------
# 来源过滤机制（Source Attribution Stripping）
# ---------------------------------------------------------------------------
# 按发帖者角色发布时，过滤掉内容中的来源/出处标注，使文案看起来像是用户
# 自己原创的分享，而非转载。
#
# 需过滤的模式：
#   1. 括号内来源：（來源 36氪）（來源：IT之家）(via TechCrunch)(sumber: 8世界)
#   2. 方括号来源前缀：【36氪快訊】【36氪】【IT之家】
#   3. 行内 via/來源/出典/sumber 片段：來源 36氪、via TechCrunch、出典 Gizmodo日本
#   4. 「摘自」「reported by」「dilaporkan」等引述短语 + 站名
#   5. 清理残留的多余空格、连续标点
# ---------------------------------------------------------------------------
import re as _re

# 所有已知站点中文名（含繁简体变体），用于构建动态正则
_ALL_SITE_NAMES = set(SITE_CN.values())
# 添加可能的繁体变体
try:
    import zhconv as _zhconv
    for _n in list(_ALL_SITE_NAMES):
        _ALL_SITE_NAMES.add(_zhconv.convert(_n, "zh-hant"))
        _ALL_SITE_NAMES.add(_zhconv.convert(_n, "zh-hans"))
except ImportError:
    pass


def strip_source_attribution(text: str) -> str:
    """从发帖文案中移除所有来源/出处标注，完全消除广告宣传属性。

    设计原则：按发帖人角色发布时，文本中不应出现任何来源媒体信息，
    使内容完全呈现为用户原创分享，避免广告宣传属性。

    过滤规则（共 7 层）：
      1. 中文圆括号来源：（來源 XX）（來源：XX）
      2. 英文圆括号来源：(via XX)(source: XX)(sumber: XX)
      3. 中文方括号来源前缀：【XX快訊】【XX】（仅当 XX 是已知站名时）
      4. 英文方括号来源前缀：[TechCrunch] [BBC] 等（仅当内容是已知站名时）
      5. 行内"via/來源/出典/sumber"+站名片段（句中或句尾）
      6. 引述短语：摘自XX、reported by XX、XX報導、XX消息
      7. 清理多余空白和残留标点
    """
    if not text:
        return text

    # --- 规则 1: 中文圆括号内来源 ---
    # （來源 36氪）（來源：IT之家）（来源 XX）（来源：XX）
    text = _re.sub(r'[（(]\s*[來来]源\s*[:：]?\s*[^）)]+[）)]', '', text)

    # --- 规则 2: 英文圆括号内 via/source/sumber ---
    # (via TechCrunch) (via: XX) (source: XX) (sumber: XX) (sumber XX)
    text = _re.sub(r'\(\s*(?:via|source|sumber|出典|स्रोत|সূত্র)\s*[:：]?\s*[^)]+\)', '', text)

    # --- 规则 3: 中文方括号来源前缀 ---
    # 【36氪快訊】【IT之家】【BBC中文】等（仅匹配已知站名或"站名+快訊/快讯/消息"）
    _site_names_escaped = [_re.escape(n) for n in _ALL_SITE_NAMES if n]
    if _site_names_escaped:
        _site_pattern = '|'.join(sorted(_site_names_escaped, key=len, reverse=True))
        # 匹配【站名】或【站名+快訊/快讯/消息/报道/報導】
        text = _re.sub(
            r'【(?:' + _site_pattern + r')(?:快訊|快讯|消息|报道|報導)?】',
            '', text
        )

    # --- 规则 4: 英文方括号来源前缀 ---
    # [TechCrunch] [BBC] [Engadget] 等（仅匹配已知站名）
    if _site_names_escaped:
        text = _re.sub(
            r'\[(?:' + _site_pattern + r')\]\s*',
            '', text
        )

    # --- 规则 5: 行内 via/來源/出典/sumber + 站名 ---
    # "來源 36氪" "via TechCrunch" "出典 Gizmodo日本" 等（不在括号内的）
    if _site_names_escaped:
        text = _re.sub(
            r'(?:來源|来源|via|出典|sumber|स्रोत|সূত্র)\s*[:：]?\s*(?:' + _site_pattern + r')',
            '', text
        )

    # --- 规则 6: 引述短语及站名独立出现 ---
    # "摘自XX" "reported by XX" "dilaporkan (oleh) XX" "——XX報導/报道"
    if _site_names_escaped:
        text = _re.sub(r'摘自\s*(?:' + _site_pattern + r')', '', text)
        text = _re.sub(
            r'(?:reported by|dilaporkan(?:\s+oleh)?)\s+(?:' + _site_pattern + r')',
            '', text, flags=_re.IGNORECASE
        )
        # "——XX報導" / "——XX报道" / "— XX's coverage"
        text = _re.sub(
            r'[—\-]+\s*(?:' + _site_pattern + r')\s*(?:報導|报道|的報導|的报道|coverage)',
            '', text
        )
        # "{site}報導" "{site}消息" "{site}的報導" 等独立出现（前面可能有标点）
        text = _re.sub(
            r'(?:' + _site_pattern + r')\s*(?:報導|报道|的報導|的报道|消息|lapor(?:an)?|reports?)',
            '', text
        )
        # 句首 "站名：" / "站名 报道：" 前缀（如"36氪報導：XXX"）
        text = _re.sub(
            r'^(?:' + _site_pattern + r')\s*(?:報導|报道)?[:：]\s*',
            '', text
        )
        # "据XX报道，" / "據XX報導，" （如"据IT之家报道，XXX"）
        text = _re.sub(
            r'[据據]\s*(?:' + _site_pattern + r')\s*(?:報導|报道|消息)?[,，、]?\s*',
            '', text
        )

    # --- 规则 7: 清理残留 ---
    # 多余空格
    text = _re.sub(r'[ \t]{2,}', ' ', text)
    # 残留的空括号 ()（）【】[]
    text = _re.sub(r'[（(]\s*[）)]', '', text)
    text = _re.sub(r'【\s*】', '', text)
    text = _re.sub(r'\[\s*\]', '', text)
    # 残留的孤立标点组合：连续的 "——" "。。" "，，" 或句首标点
    text = _re.sub(r'(?:^|\s)[—\-]{2,}\s*', ' ', text)
    text = _re.sub(r'[，,]\s*[，,]', '，', text)
    text = _re.sub(r'[。.]\s*[。.]', '。', text)
    # 句首/段首多余空格和标点
    text = _re.sub(r'^\s*[，,。.、；;：:—\-]+\s*', '', text)
    # 连续空格归一
    text = _re.sub(r' {2,}', ' ', text)
    return text.strip()

# 各语言里 #科技 标签的对应写法
# ★ 核心规则：标签语言必须与正文文案语言保持一致 ★
# 繁体中文正文 → #科技；英文正文 → #Tech；马来语正文 → #Teknologi …
# 避免出现"英文正文 + #科技"或"繁体正文 + #Tech"的混搭
LANG_TAG = {
    "zh_hant": "#科技", "en": "#Tech", "ja": "#テクノロジー",
    "ms": "#Teknologi", "id": "#Teknologi", "hi": "#टेक्नोलॉजी", "bn": "#প্রযুক্তি",
}
# 各语言「来源/via」用词
LANG_VIA = {
    "zh_hant": "來源", "en": "via", "ja": "出典",
    "ms": "sumber", "id": "sumber", "hi": "स्रोत", "bn": "সূত্র",
}

# 语言 → 发帖人角色 → 第一人称句式骨架。用 {title}{tag} 组合，全局去重。
# ★ 来源过滤机制：模板中不再显式包含 {site}/{via}，避免暴露转载来源 ★
# 6 语言：繁体中文 zh_hant / 英文 en / 日文 ja / 马来语 ms / 印地语 hi / 孟加拉语 bn
LANG_TEMPLATES = {
    "zh_hant": {
        "科技从業者": [
            "{title}——以從業者角度看，這條資訊值得關注，行業風向又變了 {tag}",
            "剛看到一則報導：{title}。身為業內人，我覺得這透露出不少訊號 {tag}",
            "{title}。這類進展對我們做技術的來說很有參考價值 {tag}",
        ],
        "科技愛好者": [
            "科技快訊｜{title}。身為數碼控，這個我必須先收藏 {tag}",
            "看到這條：{title}，越看越入迷，科技迷狂喜 {tag}",
            "{title}。這波技術演進真的很有意思，分享給同好 {tag}",
        ],
        "投資觀察者": [
            "【風向】{title}。從投資角度看，這裡面藏著機會與變數 {tag}",
            "{title}。盯賽道的朋友可以留意一下這條 {tag}",
            "值得記一筆｜{title}，資本市場大概率會有反應 {tag}",
        ],
        "媒體觀察員": [
            "今日科技｜{title}。這條報導資訊量不小，轉來一起看 {tag}",
            "幫大家劃重點：{title} {tag}",
            "{title}。一句話看懂今天的科技熱點 {tag}",
        ],
    },
    "en": {
        "Tech Insider": [
            "{title} — from an industry insider's view, this one's worth watching. {tag}",
            "Just read this report: {title}. As someone in the field, I see real signals here. {tag}",
            "{title}. Genuinely useful reference for those of us building tech. {tag}",
        ],
        "Tech Enthusiast": [
            "Tech brief | {title}. As a gadget nerd, bookmarking this one. {tag}",
            "Saw this: {title} — the more I read, the more hooked I am. {tag}",
            "{title}. This wave of tech is genuinely fascinating. {tag}",
        ],
        "Market Watcher": [
            "[Signal] {title}. From an investing angle, there's opportunity hidden here. {tag}",
            "{title}. Worth a look if you track this space. {tag}",
            "Noting this | {title} — markets will likely react. {tag}",
        ],
        "Media Observer": [
            "Today in tech | {title}. This coverage carries real weight — sharing it. {tag}",
            "Key takeaway: {title} {tag}",
            "{title}. Today's tech headline in one line. {tag}",
        ],
    },
    "ja": {
        "技術者": [
            "{title}——技術者の視点では、これは注目に値するニュースです {tag}",
            "この報道を読みました：{title}。業界人として、いくつものシグナルを感じます {tag}",
            "{title}。技術に携わる自分にとって参考になる進展です {tag}",
        ],
        "ガジェット好き": [
            "テック速報｜{title}。ガジェット好きとして、まず保存 {tag}",
            "見つけた：{title}、読むほどに引き込まれます {tag}",
            "{title}。この技術の進化は本当に面白い、共有します {tag}",
        ],
        "投資ウォッチャー": [
            "【風向き】{title}。投資目線だと、ここにチャンスが潜んでいます {tag}",
            "{title}。この分野を追う人は要チェック {tag}",
            "メモ｜{title}、市場は反応しそうです {tag}",
        ],
        "メディア観察者": [
            "今日のテック｜{title}。この報道は情報量が多い、共有します {tag}",
            "要点だけ：{title} {tag}",
            "{title}。今日のテックの見出しを一言で {tag}",
        ],
    },
    "ms": {
        "Orang Dalam Teknologi": [
            "{title} — dari sudut orang dalam industri, ini wajar diberi perhatian. {tag}",
            "Baru baca laporan ini: {title}. Sebagai orang dalam bidang, saya nampak isyarat penting. {tag}",
            "{title}. Perkembangan berguna buat kami yang membina teknologi. {tag}",
        ],
        "Peminat Teknologi": [
            "Ringkasan teknologi | {title}. Sebagai peminat gajet, saya simpan dulu. {tag}",
            "Terjumpa berita ini: {title} — makin dibaca makin menarik. {tag}",
            "{title}. Gelombang teknologi ini sangat menarik, kongsi sini. {tag}",
        ],
        "Pemerhati Pasaran": [
            "[Isyarat] {title}. Dari sudut pelaburan, ada peluang tersembunyi di sini. {tag}",
            "{title}. Patut diberi perhatian jika anda ikut bidang ini. {tag}",
            "Catat ini | {title} — pasaran mungkin bertindak balas. {tag}",
        ],
        "Pemerhati Media": [
            "Teknologi hari ini | {title}. Liputan ini padat maklumat — saya kongsikan. {tag}",
            "Intipati: {title} {tag}",
            "{title}. Tajuk teknologi hari ini dalam satu ayat. {tag}",
        ],
    },
    "hi": {
        "टेक विशेषज्ञ": [
            "{title} — इंडस्ट्री के नज़रिये से यह खबर ध्यान देने लायक है। {tag}",
            "अभी यह रिपोर्ट पढ़ी: {title}। एक जानकार के तौर पर मुझे इसमें अहम संकेत दिखते हैं। {tag}",
            "{title}। तकनीक में काम करने वालों के लिए यह उपयोगी जानकारी है। {tag}",
        ],
        "टेक प्रेमी": [
            "टेक ख़बर | {title}। गैजेट प्रेमी होने के नाते इसे सहेज रहा हूँ। {tag}",
            "यह देखा: {title} — जितना पढ़ो उतना दिलचस्प। {tag}",
            "{title}। तकनीक की यह लहर वाकई रोचक है, साझा कर रहा हूँ। {tag}",
        ],
        "बाज़ार पर्यवेक्षक": [
            "[संकेत] {title}। निवेश के नज़रिये से इसमें अवसर छिपा है। {tag}",
            "{title}। अगर आप इस क्षेत्र पर नज़र रखते हैं तो देखिए। {tag}",
            "नोट करें | {title} — बाज़ार प्रतिक्रिया दे सकता है। {tag}",
        ],
        "मीडिया पर्यवेक्षक": [
            "आज की तकनीक | {title}। यह रिपोर्ट जानकारी से भरी है — साझा कर रहा हूँ। {tag}",
            "मुख्य बात: {title} {tag}",
            "{title}। आज की टेक सुर्खी एक लाइन में। {tag}",
        ],
    },
    "bn": {
        "প্রযুক্তি বিশেষজ্ঞ": [
            "{title} — ইন্ডাস্ট্রির দৃষ্টিতে এই খবরটি নজর দেওয়ার মতো। {tag}",
            "এইমাত্র এই প্রতিবেদন পড়লাম: {title}। মাঠের মানুষ হিসেবে আমি এতে গুরুত্বপূর্ণ ইঙ্গিত দেখি। {tag}",
            "{title}। প্রযুক্তিতে যারা কাজ করি তাদের জন্য কাজের তথ্য। {tag}",
        ],
        "প্রযুক্তিপ্রেমী": [
            "টেক সংবাদ | {title}। গ্যাজেটপ্রেমী হিসেবে এটি সংরক্ষণ করছি। {tag}",
            "এটি দেখলাম: {title} — যত পড়ি তত আগ্রহ বাড়ে। {tag}",
            "{title}। প্রযুক্তির এই ঢেউ সত্যিই চমৎকার, শেয়ার করছি। {tag}",
        ],
        "বাজার পর্যবেক্ষক": [
            "[সংকেত] {title}। বিনিয়োগের দৃষ্টিতে এখানে সুযোগ লুকিয়ে আছে। {tag}",
            "{title}। এই খাত অনুসরণ করলে দেখে নিন। {tag}",
            "টুকে রাখুন | {title} — বাজার সাড়া দিতে পারে। {tag}",
        ],
        "মিডিয়া পর্যবেক্ষক": [
            "আজকের প্রযুক্তি | {title}। এই প্রতিবেদন তথ্যবহুল — শেয়ার করছি। {tag}",
            "মূল কথা: {title} {tag}",
            "{title}। আজকের টেক শিরোনাম এক লাইনে। {tag}",
        ],
    },
}

# 印尼语模板（与马来语类似但有本地化差异）
# ★ 来源过滤：模板中不再包含 {site}/{via}，保持角色口吻原创感 ★
LANG_TEMPLATES["id"] = {
    "Pakar Teknologi": [
        "{title} — dari sudut pandang industri, ini layak diperhatikan. {tag}",
        "Baru baca laporan ini: {title}. Sebagai orang di bidang ini, saya melihat sinyal penting. {tag}",
        "{title}. Perkembangan yang berguna bagi kami yang membangun teknologi. {tag}",
    ],
    "Penggemar Teknologi": [
        "Ringkasan teknologi | {title}. Sebagai penggemar gadget, saya simpan ini. {tag}",
        "Menemukan berita ini: {title} — semakin dibaca semakin menarik. {tag}",
        "{title}. Gelombang teknologi ini sangat menarik, berbagi di sini. {tag}",
    ],
    "Pengamat Pasar": [
        "[Sinyal] {title}. Dari sudut investasi, ada peluang tersembunyi di sini. {tag}",
        "{title}. Patut diperhatikan jika Anda mengikuti bidang ini. {tag}",
        "Catat ini | {title} — pasar mungkin akan bereaksi. {tag}",
    ],
    "Pengamat Media": [
        "Teknologi hari ini | {title}. Liputan ini padat informasi — saya bagikan. {tag}",
        "Intisari: {title} {tag}",
        "{title}. Judul teknologi hari ini dalam satu baris. {tag}",
    ],
}

DEFAULT_LANGS = ["zh_hant", "en", "ja", "ms", "id", "hi", "bn"]


def _run(cmd, *, env_extra=None):
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def load_accounts(path: Path, n: int):
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))

    def pick(r, keys):
        for k in keys:
            if r.get(k):
                return r[k]
        return ""
    accts = []
    for r in rows:
        email = pick(r, ["邮箱", "email", "用户邮箱", "Email", "username"])
        pw = pick(r, ["密码", "password", "用户密码", "Password"])
        nick = pick(r, ["昵称", "用户昵称", "nickname", "nick"])
        if email and pw:
            accts.append({"email": email, "password": pw, "nick": nick})
    if n > 0 and len(accts) > n:
        accts = random.sample(accts, n)
    return accts


def persona_for(idx: int, lang: str) -> str:
    """按语言返回该语言下的一个角色（轮询），保证角色与文案语言一致。"""
    roles = list(LANG_TEMPLATES.get(lang, LANG_TEMPLATES["en"]).keys())
    return roles[idx % len(roles)]


def _to_hant(s: str) -> str:
    """简体→繁体（zh_hant）转换；zhconv 可用则用，否则原样返回。"""
    try:
        import zhconv
        return zhconv.convert(s, "zh-hant")
    except Exception:  # noqa: BLE001
        return s


def build_caption(item: dict, lang: str, persona: str, *, seen: set) -> str:
    """按语言 + 发帖人角色生成第一人称纯文本文案；与 seen 去重。

    ★ 来源过滤原则：文本中完全不呈现来源信息，避免广告宣传属性 ★
    - 标题本身先过滤来源标注（如标题带"36氪快讯"前缀）
    - 最终文案再做一轮过滤（双保险）

    ★ 文案语言与 #标签语言保持一致规则 ★
    lang 参数决定：
      1. 正文文案使用的语言（从 LANG_TEMPLATES[lang] 选模板）
      2. #话题标签使用的语言（从 LANG_TAG[lang] 取对应标签）
    二者始终匹配：繁体正文 → #科技；英文正文 → #Tech；马来/印尼正文 → #Teknologi
    """
    title = (item.get("_title") or item.get("content") or "").strip()
    site = SITE_CN.get(item.get("_site", ""), item.get("_site", ""))
    tag = LANG_TAG.get(lang, "#Tech")
    via = LANG_VIA.get(lang, "via")
    # 中文站按繁体中文发布：把标题与来源名一并转繁体
    if lang == "zh_hant":
        title = _to_hant(title)
        site = _to_hant(site)

    # ★ 第一层过滤：标题本身的来源标注（如 RSS 标题带"36氪快讯｜"前缀）
    title = strip_source_attribution(title)

    lang_map = LANG_TEMPLATES.get(lang) or LANG_TEMPLATES["en"]
    templates = lang_map.get(persona) or next(iter(lang_map.values()))

    order = list(range(len(templates)))
    random.shuffle(order)
    for ti in order:
        cap = templates[ti].format(title=title, site=site, tag=tag, via=via)
        # ★ 第二层过滤：最终文案兜底过滤（防止任何残留来源泄漏）
        cap = strip_source_attribution(cap)
        cap = cap.replace("  ", " ").strip()
        if cap not in seen:
            seen.add(cap)
            return cap
    # 兜底：加序号
    base = templates[0].format(title=title, site=site, tag=tag, via=via)
    base = strip_source_attribution(base)
    i, cap = 2, base
    while cap in seen:
        cap = f"{base} ({i})"
        i += 1
    seen.add(cap)
    return cap


def main() -> int:
    ap = argparse.ArgumentParser(
        description="tech news one-command publisher (fetch → role caption → text publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_test_50.csv")
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    ap.add_argument("--per-site", type=int, default=3, help="每个网站取几条资讯（0=按 posts-per-user 自动推算）")
    ap.add_argument("--num-accounts", type=int, default=50, help="选择的用户数量")
    ap.add_argument("--posts-per-user", type=int, default=0,
                    help="每个用户发几条（>0 时总量=用户数×此值，并据此自动推算 per-site）")
    ap.add_argument("--dedupe-file", default="state/seen_tech.json",
                    help="去重档（跨批次防重复资讯）")
    ap.add_argument("--reset-dedupe", action="store_true")
    ap.add_argument("--langs", default=",".join(DEFAULT_LANGS),
                    help="文案语言（逗号分隔）；支持 " + ",".join(LANG_TEMPLATES.keys()))
    ap.add_argument("--lang-mode", default="site", choices=["site", "rotate"],
                    help="site=语言跟随网站(中文站→繁体); rotate=多语言轮询")
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--login-spacing", type=float, default=2.5)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="tech_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw = wd / f"tech_raw_{ts}.csv"
    moments = wd / f"moments_tech_{ts}.csv"

    acc_path = ROOT / args.accounts_csv
    if not acc_path.exists():
        print(f"[run_tech] 账号 CSV 不存在: {acc_path}", file=sys.stderr)
        return 2
    accts = load_accounts(acc_path, args.num_accounts)
    if not accts:
        print("[run_tech] 未能加载任何账号", file=sys.stderr)
        return 2
    n_sites = len([s for s in args.sources.split(",") if s.strip()])
    # 若指定每人发帖数，则总量=用户数×每人数，反推每站取数（多取一点，后面截断）
    total_needed = args.num_accounts * args.posts_per_user if args.posts_per_user > 0 else 0
    if total_needed > 0:
        # 每站取数留足冗余：部分源可能已被历史去重掏空(0 新鲜)，用 ×3 系数补偿
        per_site = min(60, -(-total_needed // max(1, n_sites)) * 3 + 2)
    else:
        per_site = args.per_site
    if total_needed > 0:
        print(f"[run_tech] 选定 {len(accts)} 个用户 × 每人 {args.posts_per_user} 条 = "
              f"目标 {total_needed} 条；{n_sites} 站 × 每站 ~{per_site} 条（纯文本，#{TAG}）")
    else:
        print(f"[run_tech] 选定 {len(accts)} 个用户；{n_sites} 个网站 × 每站 {per_site} 条 "
              f"= 目标 {n_sites * per_site} 条资讯（纯文本，#{TAG}）")

    # ---- Step 1: 采集 ----
    print("\n=== Step 1/3: 多源采集（科技媒体 → 标题/摘要，科技标签，纯文本）===")
    ded = ROOT / args.dedupe_file
    if args.reset_dedupe and ded.exists():
        ded.unlink()
        print(f"[run_tech] 已重置去重档：{ded.name}")
    cmd = PY + [str(HERE / "fetch_tech.py"),
                "--sources", args.sources, "--per-site", str(per_site),
                "--tag", TAG, "--dedupe-file", str(ded), "--output", str(raw)]
    if _run(cmd) != 0 or not raw.exists():
        print("[run_tech] 采集失败，终止。", file=sys.stderr)
        return 1

    items = list(csv.DictReader(raw.open(encoding="utf-8-sig")))
    # fetch_tech 用 content=title；补一个 _title 字段供文案用
    for it in items:
        it["_title"] = it.get("content", "")
    if not items:
        print("[run_tech] 未采集到任何资讯，终止。", file=sys.stderr)
        return 1
    # 跨站交错（round-robin），保证截断后各站/各语言均衡，而非全来自前几个站
    by_site: dict = {}
    for it in items:
        by_site.setdefault(it.get("_site", ""), []).append(it)
    interleaved, si = [], 0
    site_keys = list(by_site.keys())
    while any(by_site.values()):
        s = site_keys[si % len(site_keys)]
        if by_site[s]:
            interleaved.append(by_site[s].pop(0))
        si += 1
    items = interleaved
    # 若指定每人发帖数：截断到恰好 total_needed，保证每人正好 posts-per-user 条
    if total_needed > 0:
        if len(items) < total_needed:
            print(f"[run_tech] 提示：仅采集到 {len(items)}/{total_needed} 条去重资讯"
                  f"（可增大 --per-site 或减少 --posts-per-user）", file=sys.stderr)
        else:
            items = items[:total_needed]
    print(f"[run_tech] 采集到 {len(items)} 条资讯")

    # ---- Step 2: 按语言 + 发帖人角色生成文案（语言跟随网站，全局不重复）----
    langs = [l.strip() for l in args.langs.split(",") if l.strip() in LANG_TEMPLATES]
    if not langs:
        langs = DEFAULT_LANGS
    mode = args.lang_mode
    print(f"\n=== Step 2/3: 多语言角色文案（语言模式={mode}；候选 {'/'.join(langs)}，不重复）===")
    seen_caps: set[str] = set()
    rows = []
    from collections import Counter
    lang_count: Counter = Counter()
    for i, it in enumerate(items):
        if mode == "site":
            # 语言跟随网站：中文站 → 繁体中文，英文站 → 英文，日文站 → 日文…
            lang = SITE_LANG.get(it.get("_site", ""), "en")
        else:
            lang = langs[i % len(langs)]    # rotate：各语言轮询
        persona = persona_for(i, lang)      # 角色与语言一致
        content = build_caption(it, lang, persona, seen=seen_caps)
        lang_count[lang] += 1
        rows.append({
            "content": content, "visibility": 0, "room_id": "", "image_urls": "",
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_site": it.get("_site", ""), "_tag": TAG, "_lang": lang,
            "_source": it.get("_source", ""),
        })
        if i < 15:
            acct = accts[i % len(accts)]
            print(f"  #{i+1} [{(acct['nick'] or acct['email'])[:12]} /{lang}/ {persona}] {content[:56]}")
    print(f"[run_tech] 语言分布: {dict(lang_count)}")

    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_site", "_tag", "_lang", "_source"]
    with moments.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[run_tech] moments 就绪：{len(rows)} 条 → {moments}")

    if args.skip_publish:
        print("\n[run_tech] --skip-publish，仅产出素材：", moments)
        return 0

    # ---- Step 3: 纯文本发布 ----
    print("\n=== Step 3/3: 发布（纯文本，media_info type=text）===")
    print(f"  账号 CSV : {acc_path}\n  素材条数 : {len(rows)}  并发: {args.concurrency}")
    if not args.yes:
        if input("  确认发布真实帖子？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[run_tech] 已取消。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_path), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--login-spacing", str(args.login_spacing),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd, env_extra={"POST_CROP_BOTTOM_HOSTS": ""})  # 纯文本无图，关闭裁切
    if rc != 0:
        print("[run_tech] 发布返回非零，请查看 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[run_tech] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
