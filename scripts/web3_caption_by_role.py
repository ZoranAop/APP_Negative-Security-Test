#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web3_caption_by_role.py — 针对 web3/科技资讯的第一人称文案改写器。

区别于仓库自带 caption_multilang.py（其点评库/标签是为台湾摄影生活媒体设计的），
本脚本：
  - 基于真实新闻标题 + 摘要（_brief）生成第一人称口语点评（不照抄标题、非提示词）；
  - 按新闻意图（涨跌/ETF/监管/交易所/AI/稳定币/安全/研报…）挑选贴题的点评；
  - 配 web3 相关 hashtag（#web3 + 主题标签 + 来源标签）；
  - 按“发帖者角色”决定语气：轮询映射 i%20 -> accounts_20.csv 的昵称语言，
    英文昵称 -> 英文口吻，日文昵称 -> 日文口吻，其余 -> 繁体中文口吻；
  - 单条 <= 280 字符。

输出与 publish_from_tokens.py 兼容的 moments CSV（content 就地改写）。
"""
from __future__ import annotations
import argparse, csv, re, sys, unicodedata
from pathlib import Path

# ---- 新闻意图分类（关键词 → 意图桶）----
INTENTS = [
    ("regulation", ["工信部", "四部门", "监管", "監管", "SEC", "合规", "合規", "FBI", "诈骗", "詐騙", "犯罪", "国会", "國會", "作证", "作證", "诉讼", "訴訟", "立法", "政策"]),
    ("etf",        ["ETF", "资金流出", "資金流出", "资金流入", "資金流入", "IBIT", "现货", "現貨", "信托", "信託"]),
    ("exchange",   ["币安", "幣安", "火币", "火幣", "HTX", "Upbit", "Gate", "交易所", "上线", "上線", "永续", "永續", "合约", "合約", "清算", "赔偿", "賠償"]),
    ("ai",         ["AI", "OpenAI", "Anthropic", "Claude", "芯片", "晶圆", "晶圓", "Intel", "xAI", "算力", "具身智能", "人工智能", "代理", "Agent"]),
    ("stablecoin", ["稳定币", "穩定幣", "USD", "USDT", "JPYSC", "Circle", "借贷", "借貸", "收益"]),
    ("security",   ["安全", "漏洞", "黑客", "被盗", "被盜", "钓鱼", "釣魚", "签名", "簽名", "风控", "風控"]),
    ("bitcoin",    ["比特币", "比特幣", "BTC", "Saylor", "Bitcoin", "矿企", "礦企", "休眠", "储备", "儲備"]),
    ("ethereum",   ["以太坊", "ETH", "L2", "Rollup", "Layer2", "唯链", "VeChain"]),
    ("market",     ["股市", "熔断", "熔斷", "海力士", "KOSPI", "纳斯达克", "納斯達克", "暴跌", "重挫", "浮亏", "浮虧", "行情", "流动性", "流動性", "宏观", "宏觀", "降息"]),
    ("research",   ["研报", "研報", "周报", "週報", "报告", "報告", "盘点", "盤點", "前瞻", "解读", "解讀", "展望"]),
]

# ---- 每意图的第一人称点评库（繁中 / 英 / 日）----
BANKS = {
 "zh_hant": {
  "regulation": ["監管這塊終於有更清楚的方向了，長期是好事。", "合規往前走一步，市場信心也會跟著回來。", "這種政策訊號值得持續關注，影響不會只是一天。", "監管落地才是行業成熟的開始，該看的還是基本面。"],
  "etf":        ["ETF 的資金動向最能反映機構的真實態度。", "資金進出這麼明顯，短線情緒還是很重。", "ETF 這條線持續發酵，傳統資金入場是趨勢。", "看 ETF 的流向比看單日漲跌更有參考價值。"],
  "exchange":   ["交易所這波動作不少，上新和活動都要留意風險。", "永續合約槓桿高，玩之前先想好自己的倉位。", "交易所公告直接影響盤面，資訊差就是機會差。", "上新幣種先做功課，別追高。"],
  "ai":         ["AI 和 Web3 的結合越來越實際，這方向我看好。", "AI 賽道燒錢也燒得凶，估值要理性看。", "芯片和算力才是這輪 AI 的底層戰場。", "當主體從人變成 Agent，整個規則都要重寫。"],
  "stablecoin": ["穩定幣的收益模式越來越多，合規是關鍵。", "穩定幣借貸這條線值得追，實用性擺在那。", "誰能打破現有穩定幣的壟斷，才是看點。", "穩定幣是鏈上金融的地基，慢慢會標準化。"],
  "security":   ["鏈上安全永遠是第一位，別為了收益忽略風險。", "簽名主體變 Agent 之後，安全邊界確實要重新想。", "這類安全事件提醒大家，私鑰和授權都要謹慎。", "防禦性安全越來越重要，這篇講得很到位。"],
  "bitcoin":    ["比特幣還是要看長線，耐心的人通常笑到最後。", "巨鯨的動作值得參考，但別盲目跟單。", "比特幣的敘事在變，但底層邏輯沒變。", "持有比特幣拚的是心態，不是手速。"],
  "ethereum":   ["以太坊生態還是最豐富的，L2 這條路走對了。", "原生 Rollup 這種技術升級才是真功夫。", "以太坊從基礎設施走向生態中心，還有很長的路。", "L2 的競爭會決定下一輪的格局。"],
  "market":     ["這波行情夠刺激，風險控制比什麼都重要。", "大跌大漲都熔斷，情緒面已經很極端了。", "浮虧提醒大家，止盈止損的紀律不能少。", "市場越癲狂越要冷靜，別被情緒帶著走。"],
  "research":   ["這份研報資訊量很大，值得收藏慢慢看。", "深度內容比追熱點實在，這篇很有料。", "把趨勢講清楚的報告不多，這篇算一個。", "看完對整個賽道的脈絡更清楚了。"],
 },
 "en": {
  "regulation": ["Clearer rules are ultimately good for the whole space — worth watching.", "Regulation catching up is a sign the industry is maturing.", "This kind of policy signal tends to have lasting impact, not just a one-day move.", "Compliance moving forward is how confidence comes back."],
  "etf":        ["ETF flows tell you far more about institutions than daily price action.", "The flow direction here is the real story, not the headline number.", "Institutional money via ETFs is clearly a trend now.", "I watch ETF flows more than I watch candles."],
  "exchange":   ["Plenty of exchange moves this week — mind the risk on listings and events.", "High leverage on perps: size your position before you touch it.", "Exchange announcements move the market; information edge is everything.", "Do your homework before chasing a fresh listing."],
  "ai":         ["The AI x Web3 overlap keeps getting more real — I'm bullish on this.", "AI valuations need a reality check even as the tech races ahead.", "Chips and compute are the real battleground of this AI cycle.", "When the actor shifts from human to agent, the rules get rewritten."],
  "stablecoin": ["Stablecoin yield models are multiplying — compliance is the key.", "Stablecoin lending is a line worth following; the utility is real.", "The interesting question is who breaks the current stablecoin monopoly.", "Stablecoins are the base layer of on-chain finance."],
  "security":   ["On-chain security always comes first — don't chase yield blindly.", "Once agents sign transactions, the security perimeter has to be rethought.", "Incidents like this are a reminder to guard keys and approvals.", "Defensive security is only getting more important."],
  "bitcoin":    ["Bitcoin is a long game — patience usually wins.", "Whale moves are worth noting, but don't copy-trade blindly.", "The narrative shifts, but Bitcoin's base logic doesn't.", "Holding BTC is about mindset, not speed."],
  "ethereum":   ["Ethereum still has the richest ecosystem — L2 was the right call.", "Native rollups are the kind of upgrade that actually matters.", "From infrastructure to ecosystem hub — Ethereum still has a way to go.", "The L2 race will define the next cycle."],
  "market":     ["Wild session — risk control matters more than anything.", "Circuit breakers both ways; sentiment is at an extreme.", "Unrealized losses are a reminder: keep your exit discipline.", "The crazier the market, the calmer you should be."],
  "research":   ["Dense report — bookmarking this one to read slowly.", "Depth beats chasing hype; this piece is solid.", "Not many reports map the trend this clearly.", "Much clearer on the whole sector after reading this."],
 },
 "ja": {
  "regulation": ["規制が明確になるのは長期的にプラス。注視したい。", "規制が追いつくのは業界が成熟してきた証拠。", "この政策シグナルは一日で終わらない影響がありそう。", "コンプライアンスが前に進むと信頼も戻ってくる。"],
  "etf":        ["ETFの資金フローは日々の値動きより機関の本音が見える。", "数字より流れの向きが本当の話。", "ETF経由の機関マネーはもう明確なトレンド。", "ローソク足よりETFフローを見ている。"],
  "exchange":   ["取引所の動きが多い週。上場やイベントはリスクに注意。", "無期限のレバは高い。触る前にポジション管理を。", "取引所の告知は相場を動かす。情報差が勝負。", "新規上場は下調べしてから、高値追いは禁物。"],
  "ai":         ["AI×Web3はどんどん実用的に。この方向は強気。", "技術は先行しても、AIのバリュエーションは冷静に。", "チップと計算資源が今回のAIの本当の戦場。", "主体が人からエージェントに変わるとルールも書き換わる。"],
  "stablecoin": ["ステーブルの利回りモデルが増加中。鍵はコンプライアンス。", "ステーブルのレンディングは追う価値あり。実用性が高い。", "既存の寡占を誰が崩すかが見どころ。", "ステーブルはオンチェーン金融の土台。"],
  "security":   ["オンチェーンの安全は最優先。利回りだけを追わない。", "署名主体がエージェントになると安全境界の再考が必要。", "こういう事案は鍵と承認の管理を思い出させる。", "防御的セキュリティの重要性は増すばかり。"],
  "bitcoin":    ["ビットコインは長期戦。忍耐する人が勝つ。", "クジラの動きは参考に、でも盲目的な追随はNG。", "物語は変わっても、BTCの根本ロジックは変わらない。", "BTC保有はスピードより心構え。"],
  "ethereum":   ["イーサはやはり生態系が最も豊か。L2は正解だった。", "ネイティブRollupこそ本当に効くアップグレード。", "インフラから生態系の中心へ、まだ道は長い。", "L2の競争が次のサイクルを決める。"],
  "market":     ["荒い相場。何よりリスク管理が大事。", "両方向でサーキットブレーカー、センチメントは極端。", "含み損は損切り規律を思い出させてくれる。", "相場が荒れるほど冷静に。"],
  "research":   ["情報量の多いレポート。じっくり読みたい。", "ハヤリを追うより深掘りが実になる。良記事。", "トレンドをここまで整理した報告は貴重。", "読後、セクター全体の流れがクリアになった。"],
 },
}

TAGS = {
  "regulation": ["#web3", "#加密監管", "#合規"],
  "etf": ["#web3", "#加密ETF", "#機構資金"],
  "exchange": ["#web3", "#交易所", "#合約交易"],
  "ai": ["#web3", "#AI", "#科技"],
  "stablecoin": ["#web3", "#穩定幣", "#DeFi"],
  "security": ["#web3", "#鏈上安全", "#資安"],
  "bitcoin": ["#web3", "#比特幣", "#BTC"],
  "ethereum": ["#web3", "#以太坊", "#Layer2"],
  "market": ["#web3", "#加密行情", "#市場"],
  "research": ["#web3", "#研究報告", "#產業趨勢"],
}
TAGS_EN = {
  "regulation": ["#web3", "#CryptoRegulation", "#Compliance"],
  "etf": ["#web3", "#CryptoETF", "#Institutional"],
  "exchange": ["#web3", "#Exchange", "#Derivatives"],
  "ai": ["#web3", "#AI", "#Tech"],
  "stablecoin": ["#web3", "#Stablecoin", "#DeFi"],
  "security": ["#web3", "#OnchainSecurity", "#Infosec"],
  "bitcoin": ["#web3", "#Bitcoin", "#BTC"],
  "ethereum": ["#web3", "#Ethereum", "#Layer2"],
  "market": ["#web3", "#CryptoMarket", "#Markets"],
  "research": ["#web3", "#Research", "#Trends"],
}
SITE_TAG = {"techflow": "#TechFlow", "web3bbs": "#Web3BBS", "foresight": "#ForesightNews",
            "menews": "#MENews", "web3caff": "#Web3Caff", "panews": "#PANews", "bingx": "#BingX"}

def detect_intent(text: str) -> str:
    t = text or ""
    for name, kws in INTENTS:
        for kw in kws:
            if kw in t:
                return name
    return "market"

def clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "")).strip()
    t = re.split(r"\s*[\|｜]\s*(?:PA日報|PA日报|會員週報|会员周报).*$", t)[0].strip()
    return t.strip("｜|-–— 、，,").strip()

def role_lang(nick: str) -> str:
    """按昵称的文字系统判断发帖者角色语言口吻。"""
    if not nick:
        return "zh_hant"
    has_jp = any('\u3040' <= c <= '\u30ff' for c in nick)  # 平/片假名
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in nick)
    has_latin = any('a' <= c.lower() <= 'z' for c in nick)
    if has_jp:
        return "ja"
    if has_cjk:
        return "zh_hant"
    if has_latin:
        return "en"
    return "zh_hant"  # 泰文/阿拉伯文等 → 繁中兜底

def make_caption(title: str, brief: str, site: str, lang: str, idx: int) -> str:
    ct = clean_title(title)
    text_for_intent = ct + " " + (brief or "")
    intent = detect_intent(text_for_intent)
    bank = BANKS[lang][intent]
    seed = sum(ord(c) for c in ct) + idx
    comment = bank[seed % len(bank)]
    tags = (TAGS_EN if lang == "en" else TAGS)[intent][:]
    st = SITE_TAG.get(site)
    if st and st not in tags:
        tags.append(st)
    # 组织正文：真实标题（可验证）+ 第一人称点评 + 标签
    if lang == "en":
        # 英文用户：标题保留原文（多为中文新闻），加英文点评
        body = f"{comment}\n\n{ct}"
    elif lang == "ja":
        body = f"{comment}\n\n{ct}"
    else:
        body = f"{ct}\n{comment}"
    tagline = " ".join(tags)
    out = f"{body}\n{tagline}"
    # 限长 280 字符
    if len(out) > 280:
        keep = 280 - len(tagline) - len(comment) - 4
        ct2 = ct[:max(keep, 20)]
        body = (f"{comment}\n\n{ct2}" if lang in ("en", "ja") else f"{ct2}\n{comment}")
        out = f"{body}\n{tagline}"
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--accounts-csv", required=True)
    args = ap.parse_args()

    # 载入 20 账号昵称（轮询顺序）
    with open(args.accounts_csv, encoding="utf-8-sig") as fh:
        accts = list(csv.DictReader(fh))
    nicks = [(a.get("昵称") or a.get("nickname") or "").strip() for a in accts]
    n_acc = len(nicks)

    with open(args.input, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    fields = list(rows[0].keys())
    for extra in ("_lang", "_role_nick"):
        if extra not in fields:
            fields.append(extra)

    with open(args.output, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for i, row in enumerate(rows):
            nick = nicks[i % n_acc] if n_acc else ""
            lang = role_lang(nick)
            row["content"] = make_caption(row.get("content", ""), row.get("_brief", ""),
                                          row.get("_site", ""), lang, i)
            row["_lang"] = lang
            row["_role_nick"] = nick
            w.writerow(row)
    print(f"[OK] wrote {len(rows)} role-based web3 captions -> {args.output}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
