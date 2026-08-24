#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web3_caption_by_role.py — 针对 web3/科技资讯的第一人称文案改写器（语言统一化）。

区别于仓库自带 caption_multilang.py（其点评库/标签是为台湾摄影生活媒体设计的），
本脚本：
  - 基于真实新闻标题 + 摘要（_brief）生成第一人称口语点评（不照抄标题、非提示词）；
  - 按新闻意图（涨跌/ETF/监管/交易所/AI/稳定币/安全/研报…）挑选贴题的点评；
  - 配 web3 相关 hashtag（#web3 + 主题标签 + 来源标签）；
  - **语言统一化**：整条帖子（正文+标签）保证同一语言，不会出现中英混杂。
    英文/马来语帖不嵌入中文原标题，而是纯用对应语言的评论内容；
  - 支持 5 种语言：zh_hant（繁体中文）/ en（英文）/ ja（日文）/ ms（马来语）；
  - 支持 --lang 多种策略：
    * content   — 按原始标题语言自动判断（中文→繁中，英文→英文）
    * zh_hant / en / ja / ms — 强制统一某种语言
    * mixed_en_ms — 50%英文 + 50%马来语交替分配
    * auto-nick — 按账号昵称文字系统判断（旧逻辑）
  - 支持 --min-len / --max-len 控制输出字符数（默认 0~280）。

输出与 publish_from_tokens.py 兼容的 moments CSV（content 就地改写）。

用法示例：
    # 50% 英文 + 50% 马来语，150-300 字符，语言统一
    py -3 scripts/web3_caption_by_role.py \\
        --input web3_raw.csv --output moments.csv \\
        --accounts-csv accounts.csv \\
        --lang mixed_en_ms --min-len 150 --max-len 300

    # 全部繁体中文
    py -3 scripts/web3_caption_by_role.py \\
        --input web3_raw.csv --output moments.csv \\
        --accounts-csv accounts.csv --lang zh_hant

    # 按内容语言自动判断
    py -3 scripts/web3_caption_by_role.py \\
        --input web3_raw.csv --output moments.csv \\
        --accounts-csv accounts.csv --lang content
"""
from __future__ import annotations
import argparse, csv, re, sys, unicodedata
from pathlib import Path

try:
    from opencc import OpenCC
    _CC_S2T = OpenCC("s2t")
except Exception:  # noqa: BLE001
    _CC_S2T = None


def _to_hant(s: str) -> str:
    """简体→繁体（opencc s2t）；不可用或异常时原样返回。"""
    if not s or _CC_S2T is None:
        return s
    try:
        return _CC_S2T.convert(s)
    except Exception:  # noqa: BLE001
        return s


# ---- 新闻意图分类（关键词 → 意图桶）----
INTENTS = [
    ("regulation", ["工信部", "四部门", "监管", "監管", "SEC", "合规", "合規", "FBI", "诈骗", "詐騙", "犯罪", "国会", "國會", "作证", "作證", "诉讼", "訴訟", "立法", "政策",
                    "regulation", "regulator", "regulatory", "CFTC", "Congress", "rules", "law", "policy", "compliance", "lawsuit"]),
    ("etf",        ["ETF", "资金流出", "資金流出", "资金流入", "資金流入", "IBIT", "现货", "現貨", "信托", "信託"]),
    ("exchange",   ["币安", "幣安", "火币", "火幣", "HTX", "Upbit", "Gate", "交易所", "上线", "上線", "永续", "永續", "合约", "合約", "清算", "赔偿", "賠償",
                    "exchange", "Binance", "perps", "perpetual", "futures", "derivatives", "listing", "liquidation"]),
    ("ai",         ["AI", "OpenAI", "Anthropic", "Claude", "芯片", "晶圆", "晶圓", "Intel", "xAI", "算力", "具身智能", "人工智能", "代理", "Agent", "machine learning"]),
    ("stablecoin", ["稳定币", "穩定幣", "USD", "USDT", "JPYSC", "Circle", "借贷", "借貸", "收益", "stablecoin", "Tether"]),
    ("security",   ["安全", "漏洞", "黑客", "被盗", "被盜", "钓鱼", "釣魚", "签名", "簽名", "风控", "風控",
                    "exploit", "hack", "hacked", "vulnerability", "breach", "attack", "stolen", "phishing", "theft"]),
    ("bitcoin",    ["比特币", "比特幣", "BTC", "Saylor", "Bitcoin", "矿企", "礦企", "休眠", "储备", "儲備", "mining", "miner", "halving"]),
    ("ethereum",   ["以太坊", "ETH", "L2", "Rollup", "Layer2", "唯链", "VeChain", "AMM", "DeFi", "Uniswap", "rollups", "Ethereum", "Solana"]),
    ("market",     ["股市", "熔断", "熔斷", "海力士", "KOSPI", "纳斯达克", "納斯達克", "暴跌", "重挫", "浮亏", "浮虧", "行情", "流动性", "流動性", "宏观", "宏觀", "降息",
                    "stock", "stocks", "IPO", "shares", "equity", "earnings", "Fed", "index", "S&P", "Nasdaq", "Dow", "rally", "fell", "surge", "plunge", "slump"]),
    ("research",   ["研报", "研報", "周报", "週報", "报告", "報告", "盘点", "盤點", "前瞻", "解读", "解讀", "展望", "report", "analysis", "research", "outlook"]),
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
  "ru": {
   "regulation": ["Новые правила — это шаг в сторону зрелости рынка, долгосрочно только плюс.", "Чёткие регуляторные рамки дают уверенность институциям, это медленно, но верно.", "Если регулирование движется вперёд, доверие к отрасли тоже растёт.", "Комплаенс — это не враг Web3, а фундамент для массового принятия."],
   "etf":        ["Потоки ETF говорят о институциональном интересе больше, чем дневные свечки.", "Деньги через ETF — это уже тренд, игнорировать его нельзя.", "Спотовые ETF открывают двери для традиционного капитала в крипто.", "Следить за ETF-флуами важнее, чем ловить каждую свечу."],
   "exchange":   ["Активности на биржах много, но нужно помнить про риски на листингах.", "Высокое плечо на перпетуалах — сначала управляй позицией, потом торгуй.", "Анонсы бирж двигают рынок, информационное преимущество решает.", "Делай домашнюю работу перед тем как гнаться за новым листингом."],
   "ai":           ["Слияние AI и Web3 становится всё более реальным — я бытоварищ к этому направлению.", "Оценка AI-проектов требует здравой критики, даже когда технологии бегут вперёд.", "Чипы и вычислительные мощности — это настоящая битва этого AI-цикла.", "Когда агент меняет человека, правила переписываются заново."],
   "stablecoin":  ["Модели доходности стейблкоинов умножаются — комплаенс остаётся ключом.", "Стейблкоин-лендинг — перспективное направление с реальной полезностью.", "Интересный вопрос: кто разобьёт текущую монополию стейблкоинов?", "Стейблкоины — это базовый слой ончейн-финансов, стандарты будут расти."],
   "security":   ["Ончейн-безопасность всегда на первом месте, не гонитесь за доходностью слепо.", "Когда агенты подписывают транзакции, периметр безопасности нужно переосмыслить.", "Такие инциденты напоминают: осторожно с ключами и разрешениями.", "Проактивная безопасность становится только важнее с каждым днём."],
   "bitcoin":    ["Биткоин — это длинная игра, терпение обычно побеждает.", "Движения китов стоит замечать, но не копировать вслепую.", "Нарратив меняется, но базовая логика BTC остаётся прежней.", "Холдить BTC — это про mindset, а не про скорость."],
   "ethereum":   ["Экосистема Ethereum всё ещё самая богатая, L2 был верным решением.", "Нативные роллапы — это тот тип обновления, который действительно важен.", "От инфраструктуры к хабу экосистемы — Ethereum ещё далеко прошёл.", "Гонка L2 определит следующий цикл."],
   "market":     ["Дикая сессия — контроль рисков важнее всего.", "Колхозные брейкеры в обе стороны; sentiment на экстремуме.", "Нереализованные убытки напоминают: дисциплина выхода критична.", "Чем безумнее рынок, тем спокойнее ты должен быть."],
   "research":   ["Плотный отчёт — стоит bookmark, чтобы прочитать спокойно.", "Глубина лучше, чем погоня за хайпом; эта статья крепкая.", "Немногие отчёты так чётко картуют тренд.", "После прочтения картина по сектору стала гораздо яснее."],
  },
 "ms": {
  "regulation": ["Regulasi makin jelas — ini bagus untuk jangka panjang. Pasaran perlukan kepastian, dan langkah ini menunjukkan industri crypto sedang matang.", "Pematuhan melangkah ke hadapan, keyakinan pasaran akan kembali. Peraturan yang jelas bukan musuh, malah ia asas kepada pertumbuhan yang sihat.", "Isyarat polisi macam ni bukan sehari dua kesan dia. Kita patut pantau perkembangan ni dengan teliti dan lihat bagaimana ia akan bentuk masa depan industri.", "Regulasi yang jatuh adalah permulaan kematangan industri — fundamentals tetap penting dan fokus kita patut kekal di situ."],
  "etf":        ["Aliran dana ETF lebih menggambarkan sikap institusi berbanding harga harian. Pergerakan masuk dan keluar ini memberi gambaran sebenar sentimen pasaran.", "Arah aliran di sini lebih bermakna daripada angka tajuk utama. Kita kena lihat trend besar, bukan turun naik satu hari.", "Wang institusi melalui ETF dah jadi trend yang tak boleh diabaikan. Ini petanda bahawa pemain besar semakin yakin dengan crypto.", "Saya pantau aliran ETF lebih dari carta candlestick. Data aliran ini beri gambaran yang lebih tepat tentang ke mana pasaran sebenarnya menuju."],
  "exchange":   ["Banyak pergerakan pertukaran minggu ini — berhati-hati dengan risiko penyenaraian dan acara. Jangan terburu-buru masuk tanpa buat kajian terlebih dahulu.", "Leveraj tinggi pada perpetual: pastikan saiz posisi anda sebelum sentuh. Disiplin pengurusan risiko adalah kunci untuk bertahan dalam pasaran ini.", "Pengumuman pertukaran menggerakkan pasaran secara langsung — kelebihan maklumat adalah segalanya. Siapa yang dapat berita dulu, dia yang untung.", "Buat kerja rumah sebelum kejar penyenaraian baru. Token baru bukan jaminan untung, dan FOMO boleh jadi musuh paling besar anda."],
  "ai":         ["Pertindihan AI dan Web3 semakin nyata — saya optimis tentang arah ini. Gabungan dua teknologi ni boleh ubah cara kita berinteraksi dengan dunia digital.", "Penilaian AI perlu semakan realiti walaupun teknologi berlumba ke hadapan. Valuasi yang melambung tanpa fundamentals kukuh akan jadi masalah nanti.", "Cip dan pengiraan adalah medan perang sebenar kitaran AI ini. Siapa yang kawal infrastruktur, dia yang menang dalam jangka panjang.", "Apabila pelaku bertukar dari manusia ke ejen, peraturan perlu ditulis semula. Kita sedang menyaksikan perubahan paradigma yang besar dalam teknologi."],
  "stablecoin": ["Model hasil stablecoin semakin banyak — pematuhan adalah kunci. Projek yang boleh seimbangkan inovasi dengan regulasi akan menang dalam jangka masa panjang.", "Pinjaman stablecoin memang berbaloi untuk diikuti — kegunaannya jelas. Ini salah satu sektor yang memberi nilai sebenar dalam ekosistem DeFi.", "Soalan menarik ialah siapa yang akan pecahkan monopoli stablecoin semasa. Persaingan dalam ruang ini akan bawa inovasi yang lebih baik untuk pengguna.", "Stablecoin adalah lapisan asas kewangan on-chain dan ia akan terus berkembang. Piawaian dan interoperabiliti akan jadi fokus utama ke depan."],
  "security":   ["Keselamatan on-chain sentiasa diutamakan — jangan kejar hasil secara membuta. Satu kesilapan kecil boleh mengakibatkan kerugian yang tidak boleh dipulihkan.", "Apabila ejen menandatangani transaksi, perimeter keselamatan perlu difikirkan semula. Automasi membawa risiko baru yang perlu diurus dengan berhati-hati.", "Insiden macam ni ingatkan kita untuk jaga kunci dan kelulusan dengan teliti. Keselamatan digital bukan pilihan, ia keperluan mutlak dalam dunia Web3.", "Keselamatan defensif semakin penting hari demi hari. Pelaburan dalam audit dan perlindungan smart contract bukan kos, ia adalah pelaburan masa depan."],
  "bitcoin":    ["Bitcoin adalah permainan jangka panjang — kesabaran biasanya menang. Sejarah telah buktikan bahawa mereka yang hold dengan yakin akan untung pada akhirnya.", "Pergerakan whale patut diperhatikan, tapi jangan salin dagangan secara membabi buta. Buat analisis sendiri dan fahami konteks sebelum ambil keputusan.", "Naratif BTC berubah mengikut zaman, tapi logik asasnya tidak pernah berubah. Kelangkaan, desentralisasi dan ketahanan terhadap sensor kekal relevan.", "Pegang Bitcoin lebih tentang minda daripada kelajuan. Volatiliti jangka pendek tidak bermakna jika anda faham tesis pelaburan jangka panjang anda."],
  "ethereum":   ["Ethereum masih mempunyai ekosistem paling kaya — L2 adalah keputusan yang betul. Skala dan kelajuan transaksi bertambah baik tanpa korbankan keselamatan.", "Rollup natif adalah jenis peningkatan yang benar-benar berkesan untuk ekosistem. Ini bukan sekadar penambahbaikan kecil, ia perubahan fundamental.", "Dari infrastruktur ke hab ekosistem — Ethereum masih ada perjalanan panjang. Tapi arah tujunya jelas dan komuniti pembangunannya tetap yang paling aktif.", "Perlumbaan L2 akan menentukan kitaran seterusnya. Siapa yang boleh tawarkan pengalaman terbaik dengan kos terendah, dia yang akan dominasi."],
  "market":     ["Sesi yang liar — kawalan risiko lebih penting daripada apa-apa. Dalam keadaan pasaran macam ni, lindungi modal anda dulu sebelum fikir tentang untung.", "Circuit breaker dua arah menunjukkan sentimen sudah di tahap ekstrem. Apabila pasaran jadi begini, ia biasanya petanda bahawa perubahan besar akan datang.", "Kerugian belum direalisasi mengingatkan kita supaya disiplin dalam ambil untung dan potong rugi. Jangan biar emosi kawal keputusan pelaburan anda.", "Makin gila pasaran, makin tenang kita kena jadi. Panik selling dan FOMO buying adalah dua musuh utama pelabur dalam keadaan volatil macam sekarang."],
  "research":   ["Laporan yang padat dengan maklumat — saya akan simpan ni untuk baca perlahan-lahan. Analisis mendalam macam ni sukar dijumpai dan memang berbaloi masa untuk hadam.", "Kandungan mendalam lebih bernilai dari kejar hype semata-mata. Artikel ni bagi perspektif yang lebih luas tentang ke mana industri sedang menuju.", "Tidak banyak laporan yang memetakan trend dengan begitu jelas dan terperinci. Kerja penyelidikan yang solid membantu kita buat keputusan yang lebih baik.", "Lebih jelas tentang keseluruhan sektor selepas baca laporan ini. Konteks dan data yang disajikan membantu memahami gambaran besar pasaran."],
  },
}

# ---- 正向口吻点评库（侧重描述 Web3 资源的优势，正向发展视角）----
POSITIVE_BANKS = {
 "zh_hant": {
  "regulation": ["監管走向清晰，長期是行業成熟的標誌，Web3 的合規優勢會越來越明顯。", "規則明確讓更多人敢進場，這是 Web3 走向主流的必經之路。", "合規穩定幣正在爲機構資金開門，這是最強勁的順風。", "監管機構站到這一邊，整個生態的信任度都上了一個臺階。"],
  "etf":        ["ETF 讓傳統資金能低門檻配置加密資產，Web3 與傳統金融的融合正在加速。", "機構資金持續流入，說明市場對 Web3 資產的認可度在提升。"],
  "exchange":   ["交易所創新不斷，用戶體驗和流動性都在變好，行業基礎設施越來越扎實。", "新產品的推出讓更多場景落地，Web3 的可用性越來越強。"],
  "ai":         ["AI 與 Web3 的結合打開了全新的想像空間，這是技術趨勢的交匯點。", "算力和智能合約的結合，正在重塑價值創造的範式。"],
  "stablecoin": ["穩定幣讓跨境支付更高效，Web3 的金融基礎設施正被更多人使用。", "穩定幣是 Web3 與現實世界的橋樑，普及度只會越來越高。"],
  "security":   ["安全能力的提升讓行業更成熟，鏈上資產的保護越來越完善。", "每一次安全加固，都讓 Web3 的基礎更可靠。"],
  "bitcoin":    ["比特幣作為價值存儲的敘事越來越被認可，長線價值持續凸顯。", "比特幣的稀缺性和去中心化，是其長期價值的核心支撐。"],
  "ethereum":   ["以太坊生態最繁榮，Layer2 讓可擴展性大幅提升，發展空間巨大。", "以太坊的創新活力是 Web3 最大的引擎。"],
  "market":     ["市場的波動只是短期，Web3 的長期趨勢依然向上。", "每一次回調都是長期佈局的機會，行業基本面持續向好。"],
  "research":   ["深度研究讓行業認知不斷提升，Web3 的敘事越來越扎實。", "優質內容的湧現，說明行業正在從炒作走向價值。"],
 },
 "en": {
  "regulation": ["Clearer rules mean more confidence — this is Web3 maturing in the right direction.", "Regulatory clarity is what brings mainstream adoption; the outlook keeps improving.", "Compliant stablecoins are opening the door for institutional money — a huge tailwind.", "When regulators lean in, the whole ecosystem gets a credibility boost."],
  "etf":        ["ETF inflows show traditional capital finally recognizing Web3's value.", "The bridge between TradFi and crypto keeps getting stronger."],
  "exchange":   ["Better products and liquidity — the infrastructure keeps getting more solid.", "Every new launch expands Web3's real-world use cases."],
  "ai":         ["AI and Web3 are converging into something much bigger.", "Compute plus smart contracts is reshaping how value is created."],
  "stablecoin": ["Stablecoins make cross-border payments effortless — real adoption is growing.", "Stablecoins are the bridge between crypto and everyday finance."],
  "security":   ["Stronger security makes the whole space more trustworthy.", "Every hardening step makes Web3's foundation more reliable."],
  "bitcoin":    ["Bitcoin's scarcity and decentralization are its long-term moat.", "The store-of-value narrative keeps gaining acceptance."],
  "ethereum":   ["Ethereum's ecosystem keeps thriving — L2 scalability opens huge room to grow.", "Ethereum remains the engine of Web3 innovation."],
  "market":     ["Volatility is short-term; the long-term trend stays up.", "Pullbacks are entry points — fundamentals keep improving."],
  "research":   ["Deep research builds real understanding — Web3's narrative keeps getting stronger."],
 },
 "ja": {
  "regulation": ["規制の明確化は成熟の証、Web3は正しい方向へ進んでいる。", "ルールが整えば主流化が加速する。", "コンプライアンス対応のステーブルコインが機関マネーの扉を開く。", "規制当局が寄り添えば、エコシステム全体の信頼が高まる。"],
  "etf":        ["ETFへの資金流入はWeb3の価値が認められた証拠。", "伝統金融と暗号資産の架け橋はさらに強くなる。"],
  "exchange":   ["より良い製品と流動性、インフラは着実に強くなっている。", "新しいサービスがWeb3の実用性を広げる。"],
  "ai":         ["AIとWeb3の融合はさらに大きな可能性を開く。", "計算資源とスマートコントラクトの組み合わせが価値創造を変える。"],
  "stablecoin": ["ステーブルコインは国際送金を簡単に、実用が広がっている。", "ステーブルコインは暗号資産と日常金融の橋渡し。"],
  "security":   ["セキュリティ強化が業界全体の信頼を高める。", "強固な基盤がWeb3の未来を支える。"],
  "bitcoin":    ["ビットコインの希少性と非中央集権こそ長期の強み。", "価値保存の物語はますます受け入れられている。"],
  "ethereum":   ["イーサリアムの生態系は最も活発、L2で拡張性も向上。", "イーサリアムはWeb3革新のエンジン。"],
  "market":     ["変動は短期、長期的な上昇トレンドは変わらない。", "押し目はチャンス、ファンダメンタルは改善中。"],
 "research":   ["深い研究が理解を深め、Web3の物語を強くする。"],
  },
}

# ---- 负面情绪点评库（发帖人对坏消息的抱怨/吐槽，贴近真人，去 AI 味）----
# 仅覆盖负面意图：security / market / regulation / exchange。
COMPLAINT_BANKS = {
 "zh_hant": {
  "security":   ["又看到被盜的消息，鏈上安全真的讓人心累，錢放哪都不踏實。", "每次這種漏洞曝光，我都要回去翻一遍自己授權過哪些網站，太煩了。", "黑客真是防不勝防，這波又有人要哭了，私鑰和授權都得再查一遍。", "安全事件一出接著一出，搞得我現在什麼都不敢點，心累。"],
  "market":     ["這行情把人折磨得夠嗆，浮虧看得我心都在滴血。", "又崩了，前兩天剛回的一點血一下全吐回去，真的很難受。", "跌成這樣還談什麼信仰，先讓我的賬戶緩一緩吧。", "這波震得我人都麻了，天天盯盤眼睛都花了還是虧。"],
  "regulation": ["監管一出手就是一堆麻煩，項目方頭疼，我們這些散戶也跟著遭殃。", "罰單一張接一張，行業整天人心惶惶，什麼時候能安穩點。", "政策風向變得比翻書還快，現在佈局都不敢亂動了。", "規矩改來改去，真的不知道下個月還能不能玩。"],
  "exchange":   ["交易所能不能不搞這麼多騷操作，突然清算真的扛不住。", "槓桿爆倉的教訓太慘痛了，現在都不敢重倉了。", "公告改來改去，散戶就是被收割的命，真的累了。", "一上線一停牌，錢包跟著心驚膽戰，這體驗太折磨人。"],
 },
 "en": {
  "security":   ["Another hack… honestly tired of re-securing everything after every breach.", "These exploits keep happening and it's exhausting watching funds disappear again.", "Every time I see news like this I go re-check my approvals. So annoying.", "Security incidents one after another — now I'm scared to click anything, tired of it."],
  "market":     ["This market is honestly exhausting — my unrealized losses hurt to look at.", "Another dump. All of last week's gains just evaporated, this is rough.", "At this point I'm past panic, just tired of the swings.", "Watching the tape burn all day just to end up red — draining."],
  "regulation": ["Regulators throwing fines left and right, and retail ends up footing the bill.", "Regulation whiplash is real — hard to plan moves when rules keep shifting.", "These crackdowns keep everyone on edge, wish things would just settle for once.", "Rules changing every other week, no idea if this is even playable next month."],
  "exchange":   ["Exchanges pulling moves like this is why the liquidation stories never end.", "Got burned by leverage before, never touching heavy margin again.", "Announcements flip so fast, retail always ends up on the losing side. Exhausting.", "Listing then halting, my wallet can't take the whiplash anymore."],
 },
 "ja": {
  "security":   ["また盗難のニュース。オンチェーンの安全には本当に疲れる。", "脆弱性が出るたびに承認を見直すの、正直うんざりだ。", "ハッカーには本当に手がつけられない。また誰かが泣く。", "セキュリティ事故が続いて、もう何も押せなくなった。疲れた。"],
  "market":     ["この相場には本当に疲れた。含み損を見るのがつらい。", "また暴落。先週の利益が一瞬で消えた、きつい。", "もうパニックじゃなくて、ただ揺れに疲れた。", "一日中チャート見てて結局マイナス、消耗がひどい。"],
  "regulation": ["規制が厳しくなると、結局は個人投資家が割を食う。", "方針が二転三転して、ポジションも動かせない。", "罰金のニュースばかりで、業界全体が落ち着かない。", "ルールが毎回変わる、来月も続けられるかわからない。"],
  "exchange":   ["取引所のこういう動き、清算の話が絶えないわけだ。", "レバレッジで痛い目を見たから、もう重い証拠金は握らない。", "告知がすぐ変わる、個人はいつも不利だ。疲れる。", "上場してすぐ停止、財布がひやひやして耐えられない。"],
 },
 "ms": {
  "security":   ["Berita kecurian lagi. Keselamatan on-chain ni buat orang letih betul.", "Setiap kali exploit muncul, saya kena semak balik semua kelulusan. Menyusahkan.", "Hacker memang tak boleh diduga, ada lagi yang kena tanggung rugi.", "Insiden keselamatan berturut-turut, sekarang takut nak tekan apa-apa."],
  "market":     ["Pasaran macam ni buat orang letih, tengok rugi belum realis pun sakit.", "Jatuh lagi. Untung minggu lepas hilang semua, memang susah.", "Dah tak panik, cuma penat dengan turun naik ni.", "Sepanjang hari tengok carta, akhirnya masih rugi. Menyakitkan."],
  "regulation": ["Regulasi makin ketat, akhirnya pelabur runcit yang tanggung.", "Polisi berubah tak menentu, nak rancang langkah pun susah.", "Berita denda tak habis-habis, industri tak tenang.", "Peraturan berubah setiap minggu, tak tahu bulan depan boleh main lagi ke tak."],
  "exchange":   ["Pertukaran buat hal macam ni, sebab tu cerita likuidasi tak habis.", "Pernah kena leverage, dah tak berani margin besar lagi.", "Pengumuman berubah cepat, runcit selalu di pihak rugi.", "Baru disenarai terus digantung, dompet tak boleh tahan lagi."],
 },
}
NEGATIVE_INTENTS = {"security", "market", "regulation", "exchange"}

# ---- 币安广场式收益感慨点评库（发帖人结合资讯表达自身已获收益的感慨）----
TRADER_BANKS = {
 "zh_hant": {
  "regulation": ["政策一明朗，我早前佈局的倉位就漲了，這波合規紅利算是吃到了。", "監管落地是利好，我持倉終於回本了，這次是賺的。"],
  "etf":        ["ETF 資金持續流入，我手裡的現貨跟著水漲船高，這波吃到了。", "機構進場的信號太明顯了，我早就埋伏，賬戶已經翻倍。"],
  "exchange":   ["新幣上線前我就在關注了，上市後第一時間進場，已經吃到肉。", "這波交易所行情我踩對了節奏，利潤很可觀。"],
  "ai":         ["AI 概念我早早就埋伏了，這波漲勢讓我賬戶大豐收。", "看好 AI 這條線，我持倉已經漲了不少，感慨當初的判斷。"],
  "stablecoin": ["穩定幣收益雖然穩，但積少成多，我這幾個月也攢了不少。", "穩定幣借貸的收益我一直在吃，複利真的很香。"],
  "security":   ["安全第一，我躲過了幾次盜幣，保住了本金就是賺。", "好在提前撤了槓桿，躲過了這波清算，本金還在。"],
  "bitcoin":    ["比特幣這波反彈我抄底成功，賬戶已經翻倍，感恩。", "BTC 就是信仰，我從低點一路拿到現在，利潤可觀。"],
  "ethereum":   ["以太坊生態我重倉了，這波 L2 行情讓我賺了不少。", "ETH 的 Layer2 賽道我埋伏很久，這次終於爆發了。"],
  "market":     ["這波行情我踩對了節奏，低吸高拋，賺得盆滿缽滿。", "回調就是機會，我趁跌加倉，現在賬戶浮盈可觀。"],
  "research":   ["看了研報提前佈局，這波賺到了，深度研究的價值就在這。", "跟著研究報告走，我的持倉翻倍了，認知就是財富。"],
 },
 "en": {
  "regulation": ["My early positions pumped once the rules clarified — this compliance rally paid off.", "Regulatory clarity finally pushed my bags back into profit."],
  "etf":        ["ETF inflows lifted my spot holdings nicely — glad I positioned early.", "I saw the institutional signal and loaded up; the account has doubled."],
  "exchange":   ["I watched the listing before launch and got in first — this one paid.", "Timed this exchange move right and the gains have been solid."],
  "ai":         ["I positioned into AI early and this rally made my portfolio a lot richer.", "Holding the AI narrative has paid off big time — glad I trusted it."],
  "stablecoin": ["Stablecoin yields add up — months of compounding really shows.", "I've been collecting stablecoin lending yield and it's compounding nicely."],
  "security":   ["Kept my keys safe and dodged a few hacks — protecting principal is a win.", "Glad I pulled leverage early and avoided the liquidation."],
  "bitcoin":    ["Caught this BTC dip and my bag is up nicely now — this is why I hold.", "Bought the low and rode it up — the account has doubled, grateful."],
  "ethereum":   ["Heavy in the Ethereum ecosystem and this L2 run made me solid gains.", "I've been in the L2 trade for a while — finally it paid off."],
  "market":     ["Timed this swing right and banked solid profits.", "Added on the dip and I'm nicely in profit now."],
  "research":   ["Read the report early and positioned ahead — this one paid, research is wealth."],
 },
 "ja": {
  "regulation": ["規制が明確になって、早めのポジションが上がった。この上昇は大きい。", "コンプライアンスの追い風で、持ち分がやっと利益に戻った。"],
  "etf":        ["ETF流入で現物も上がった。早めに仕込んで正解だった。", "機関のシグナルに乗って、口座は倍になった。"],
  "exchange":   ["上場前に注目して、一番で入った。今回は利益が出た。", "取引所の動きに乗って、しっかり稼げた。"],
  "ai":         ["AIは早めに仕込んでいて、この上昇で大きく増えた。", "AIの流れを信じて持っていたら、大きく化けた。"],
  "stablecoin": ["ステーブルの利回りは地味に効く。複利でじわじわ増えている。", "ステーブルのレンディング利回りをずっと回している。"],
  "security":   ["鍵を守ってハッキングを回避、元本を守れたのが勝ち。", "早めにレバを解消して清算を回避、助かった。"],
  "bitcoin":    ["BTCの底で拾って、そのまま上がった。口座は倍、感謝。", "ビットコインは信仰。安く買って持ち続けたら増えた。"],
  "ethereum":   ["イーサリアムを厚めに持っていて、L2相場で大きく稼げた。", "L2は長く仕込んでいた、ようやく花開いた。"],
  "market":     ["この相場、リズムを掴んでしっかり利益を取れた。", "押し目で買い増して、今は含み益が大きい。"],
  "research":   ["レポートを読んで先回り、今回は勝てた。研究は財産。"],
 },
}

TAGS_MS = {
  "regulation": ["#web3", "#RegulasiKripto", "#Pematuhan"],
  "etf": ["#web3", "#ETFKripto", "#Institusi"],
  "exchange": ["#web3", "#Pertukaran", "#Derivatif"],
  "ai": ["#web3", "#AI", "#Teknologi"],
  "stablecoin": ["#web3", "#Stablecoin", "#DeFi"],
  "security": ["#web3", "#KeselamatanOnchain", "#Keselamatan"],
  "bitcoin": ["#web3", "#Bitcoin", "#BTC"],
  "ethereum": ["#web3", "#Ethereum", "#Layer2"],
  "market": ["#web3", "#PasaranKripto", "#Pasaran"],
  "research": ["#web3", "#Penyelidikan", "#Trend"],
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
TAGS_JA = {
  "regulation": ["#web3", "#暗号規制", "#コンプライアンス"],
  "etf": ["#web3", "#暗号ETF", "#機関投資家"],
  "exchange": ["#web3", "#取引所", "#デリバティブ"],
  "ai": ["#web3", "#AI", "#テクノロジー"],
  "stablecoin": ["#web3", "#ステーブルコイン", "#DeFi"],
  "security": ["#web3", "#オンチェーンセキュリティ", "#セキュリティ"],
  "bitcoin": ["#web3", "#ビットコイン", "#BTC"],
  "ethereum": ["#web3", "#イーサリアム", "#Layer2"],
  "market": ["#web3", "#暗号市場", "#マーケット"],
  "research": ["#web3", "#リサーチ", "#トレンド"],
}
TAGS_RU = {
  "regulation": ["#web3", "#КриптоРегулирование", "#Комплаенс"],
  "etf": ["#web3", "#КриптоETF", "#Институционалы"],
  "exchange": ["#web3", "#Биржа", "#Деривативы"],
  "ai": ["#web3", "#AI", "#Технологии"],
  "stablecoin": ["#web3", "#Стейблкоин", "#DeFi"],
  "security": ["#web3", "#ОнчейнБезопасность", "#Инфобез"],
  "bitcoin": ["#web3", "#Биткоин", "#BTC"],
  "ethereum": ["#web3", "#Эфириум", "#Layer2"],
  "market": ["#web3", "#КриптоРынок", "#Рынки"],
  "research": ["#web3", "#Исследование", "#Тренды"],
}
SITE_TAG = {"techflow": "#TechFlow", "web3bbs": "#Web3BBS", "foresight": "#ForesightNews",
            "menews": "#MENews", "web3caff": "#Web3Caff", "panews": "#PANews", "bingx": "#BingX",
            "theblock": "#TheBlock", "decrypt": "#Decrypt", "thedefiant": "#TheDefiant",
            "bitcoinmagazine": "#BitcoinMagazine", "beincrypto": "#BeInCrypto", "odaily": "#Odaily",
            "bloomberg": "#Bloomberg", "cnbc": "#CNBC", "wsj": "#WSJ", "reuters": "#Reuters",
            "marketwatch": "#MarketWatch", "yahoo_finance": "#YahooFinance", "benzinga": "#Benzinga",
            "ft": "#FT", "barrons": "#Barrons", "thestreet": "#TheStreet"}

def detect_intent(text: str) -> str | None:
    t = text or ""
    for name, kws in INTENTS:
        for kw in kws:
            if kw in t:
                return name
    return None

def clean_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "")).strip()
    t = re.split(r"\s*[\|｜]\s*(?:PA日報|PA日报|會員週報|会员周报).*$", t)[0].strip()
    return t.strip("｜|-–— 、，,").strip()

def role_lang(nick: str) -> str:
    """按昵称的文字系统判断发帖者角色语言口吻（仅在 --lang auto-nick 时使用）。"""
    if not nick:
        return "zh_hant"
    has_jp = any('\u3040' <= c <= '\u30ff' for c in nick)  # 平/片假名
    has_cjk = any('\u4e00' <= c <= '\u9fff' for c in nick)
    has_ru = any('\u0400' <= c <= '\u04ff' for c in nick)  # 西里尔字母
    has_latin = any('a' <= c.lower() <= 'z' for c in nick)
    if has_jp:
        return "ja"
    if has_ru:
        return "ru"
    if has_cjk:
        return "zh_hant"
    if has_latin:
        return "en"
    return "zh_hant"  # 泰文/阿拉伯文等 → 繁中兜底


def detect_content_lang(title: str) -> str:
    """根据原始标题内容的语言决定输出语言。
    中文内容 → zh_hant（繁体中文呈现），英文内容 → en。
    判断逻辑：统计 CJK 字符占比，有一定比例中文字符就认为是中文内容。
    """
    if not title:
        return "zh_hant"
    cjk_count = sum(1 for c in title if '\u4e00' <= c <= '\u9fff')
    # 日文假名
    jp_count = sum(1 for c in title if '\u3040' <= c <= '\u30ff' or '\u31f0' <= c <= '\u31ff')
    latin_count = sum(1 for c in title if 'a' <= c.lower() <= 'z')
    if jp_count > 3:
        return "ja"
    if cjk_count >= 2:
        return "zh_hant"
    if latin_count > 0:
        return "en"
    return "zh_hant"

def _truncate_clean(body: str, limit: int) -> str:
    """在不超过 limit 的前提下，尽量按句末/换行/空格边界截断，避免拦腰切断句子。"""
    if limit <= 0:
        return ""
    if len(body) <= limit:
        return body
    # 依次找最近的可断点：句末 > 换行 > 空格
    for sep in ("。", ". ", "!", "?", "\n", "，", ", ", "；", "; "):
        idx = body.rfind(sep, 0, limit)
        if idx > 0:
            cut = body[:idx].rstrip()
            if cut:
                return cut
    # 退回到最近的空格
    idx = body.rfind(" ", 0, limit)
    if idx > 0:
        return body[:idx].rstrip()
    return body[:limit].rstrip().rstrip("...") + "…"


def _strip_source(s: str) -> str:
    """去除文案里的信息来源痕迹（媒体名、据XX报道、作者/编译、原文链接、金十等）。"""
    if not s:
        return s
    s = re.sub(r"深潮\s*TechFlow\s*(?:消息|讯息|資訊|消息|资讯)?[，,]?\s*", "", s)
    s = re.sub(r"(?:编辑|編輯)\s*\|\s*(?:吴说区块链|吳說區塊鏈)[，,]?\s*", "", s)
    s = re.sub(r"AI\s*(?:解读|解讀)\s*", "", s)
    s = re.sub(r"[据據][^\s，,。；;]{1,20}?\s*(?:数据|數據|报道|報道|消息|讯息|訊息)", "", s)
    s = re.sub(r"(?:作者|編譯|编译|撰文)\s*[|：:]\s*[^\s，,。；;]{1,30}", "", s)
    s = re.sub(r"(?:原文链接|原文鏈接|来源|來源)\s*[|：:]\s*\S+", "", s)
    s = re.split(r"免责声明|免責聲明|本文系|本文系", s)[0]
    s = re.sub(r"整理\s*&\s*(?:编译|編譯)\s*[|：:]\s*[^\s，,。；;]{1,30}", "", s)
    s = re.sub(r"[（(]金十[)）]", "", s)
    s = re.sub(r"^吴说每日精选(?:加密新闻)?\s*[-\-–]\s*", "", s)
    s = re.sub(r"^吳說每日精選(?:加密新聞)?\s*[-\-–]\s*", "", s)
    s = re.sub(r"^白线\s*WhiteLine\s*Daily\s*[｜|]\s*", "", s)
    s = re.sub(r"^白線\s*WhiteLine\s*Daily\s*[｜|]\s*", "", s)
    s = re.split(r"白线日报\s*WhiteLine\s*Daily\s*[，,]", s)[0]
    s = re.split(r"白線日報\s*WhiteLine\s*Daily\s*[，,]", s)[0]
    s = re.split(r"凝聚(?:吴说|吳說)(?:团队|團隊)思考", s)[0]
    s = re.sub(r"\s{2,}", " ", s).strip(" ，,。；;|:：")
    return s


# 负面情绪词（标题/摘要命中 → 视为坏消息，供 complain 口吻使用）
_NEG_TONE_KW = ["跌", "崩", "暴跌", "下跌", "重挫", "闪崩", "爆仓", "清算", "亏损", "诈骗",
                "黑客", "被盗", "违法", "调查", "起诉", "逮捕", "洗钱", "腰斩", "跳水",
                "罚款", "罚单", "崩溃", "危机", "暴雷", "跑路", "恐慌", "抛售", "缩水",
                "crash", "plunge", "fall", "drop", "decline", "slump", "loss", "bear",
                "dump", "hack", "scam", "fraud", "arrest", "lawsuit", "ban", "delist",
                "suspend", "liquidat", "selloff", "sell-off", "crackdown", "exploit",
                "stolen", "fined", "fine", "probe", "investigat", "breach", "theft"]


def _is_negative(text: str) -> bool:
    """判断资讯是否为负面消息（按负面情绪词命中）。"""
    t = (text or "").lower()
    return any(k in t for k in _NEG_TONE_KW)


def make_caption(title: str, brief: str, site: str, lang: str, idx: int,
                 min_len: int = 0, max_len: int = 280, no_source: bool = False,
                 tone: str = "neutral") -> str:
    """生成文案。支持 min_len/max_len 控制字符数。

    关键原则：整条帖子语言统一。
    - 如果 lang=en，整条帖子全英文（不夹杂中文标题）；
    - 如果 lang=ms，整条帖子全马来语（不夹杂中文标题）；
    - 如果 lang=zh_hant，标题+点评都是繁中。
    - no_source=True 时：不追加来源标签，且清洗摘要里的媒体/作者等来源痕迹。
    - tone=positive 时：使用正向口吻点评库（侧重描述 Web3 优势与发展）。
    - tone=complain 时：仅对负面消息（标题/摘要命中负面情绪词）使用抱怨/吐槽点评，否则回退中性。
    """
    ct = clean_title(title)
    if no_source:
        ct = _strip_source(ct)
        brief = _strip_source(brief or "")
    # 意图分类优先看标题，标题无匹配时用摘要兜底（如引用型标题），最终回落 market
    intent = detect_intent(ct) or detect_intent(brief) or "market"
    negative = _is_negative(ct + " " + (brief or ""))
    if tone == "complain" and negative and intent in NEGATIVE_INTENTS and lang in COMPLAINT_BANKS:
        bank = COMPLAINT_BANKS[lang][intent]
    elif tone == "positive" and lang in POSITIVE_BANKS:
        bank = POSITIVE_BANKS[lang][intent]
    elif tone == "trader" and lang in TRADER_BANKS:
        bank = TRADER_BANKS[lang][intent]
    elif lang == "ru":
        bank = BANKS["ru"][intent]
    else:
        bank = BANKS[lang][intent]
    seed = sum(ord(c) for c in ct) + idx
    comment = bank[seed % len(bank)]
    # 取第二条点评（用于补足长度）
    comment2 = bank[(seed + 1) % len(bank)]
    if comment2 == comment:
        comment2 = bank[(seed + 2) % len(bank)]
    # 选择标签集
    if lang == "ms":
        tags = TAGS_MS[intent][:]
    elif lang == "en":
        tags = TAGS_EN[intent][:]
    elif lang == "ja":
        tags = TAGS_JA[intent][:]
    elif lang == "ru":
        tags = TAGS_RU[intent][:]
    else:
        tags = TAGS[intent][:]
    st = SITE_TAG.get(site)
    if st and st not in tags and not no_source:
        tags.append(st)
    tagline = " ".join(tags)

    # ---- 组装正文（确保语言统一）----
    if lang in ("en", "ms", "ja", "ru"):
        # 英文/马来文/日文/俄文帖：不嵌入中文标题，纯用对应语言的评论
        # 用两条评论拼接以达到足够长度，避免出现中英/中日混杂
        body = f"{comment}\n\n{comment2}"
    else:
        # zh_hant：中文标题 + 繁中点评（标题统一转繁体，避免简繁混排）
        body = f"{_to_hant(ct)}\n{comment}"

    out = f"{body}\n{tagline}"

    # 如果低于 min_len 且有 brief，尝试补足（仅限同语言内容）
    if min_len > 0 and len(out) < min_len:
        # 对于 en/ms/ja/ru，再加第三条点评
        if lang in ("en", "ms", "ja", "ru"):
            comment3 = bank[(seed + 3) % len(bank)]
            if comment3 not in (comment, comment2):
                body = f"{comment}\n\n{comment2}\n\n{comment3}"
                out = f"{body}\n{tagline}"
        else:
            # zh_hant 可以追加 brief
            if brief:
                brief_clean = re.sub(r"\s+", " ", brief).strip()
                avail = max_len - len(out) - 2
                if avail > 20:
                    body = f"{_to_hant(ct)}\n{comment}\n\n{_to_hant(brief_clean[:avail])}"
                    out = f"{body}\n{tagline}"

    # 限制 max_len：优先在句末/词边界截断，避免把句子拦腰切断
    if len(out) > max_len:
        avail = max_len - len(tagline) - 1
        if avail <= 0:
            body = ""
        else:
            body = _truncate_clean(body, avail)
        out = f"{body}\n{tagline}".strip()
    # 最终硬截断（仍截在边界）
    if len(out) > max_len:
        out = _truncate_clean(out, max_len)
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--accounts-csv", required=True)
    ap.add_argument("--lang", default="content",
                    choices=["content", "zh_hant", "en", "ja", "ms", "ru", "auto-nick", "mixed_en_ms"],
                    help="语言策略：content=按内容语言自动判断，zh_hant/en/ja/ms/ru=强制统一，"
                         "mixed_en_ms=50%%英文+50%%马来语交替，auto-nick=按昵称。默认 content。")
    ap.add_argument("--min-len", type=int, default=0,
                    help="文案最小字符数（默认 0 不限制）")
    ap.add_argument("--max-len", type=int, default=280,
                    help="文案最大字符数（默认 280）")
    ap.add_argument("--no-source", action="store_true",
                    help="不带信息来源：不追加来源标签，并清洗摘要里的媒体名/据XX报道/作者等痕迹")
    ap.add_argument("--tone", default="neutral", choices=["neutral", "positive", "trader", "complain"],
                    help="点评口吻：neutral=中性点评，positive=正向点评（侧重描述 Web3 优势），"
                         "trader=币安广场式收益感慨（发帖人表达自身已获收益），"
                         "complain=对坏消息的抱怨/吐槽（仅负面意图 security/market/regulation/exchange 生效）")
    args = ap.parse_args()

    lang_mode = args.lang
    min_len = args.min_len
    max_len = args.max_len

    # 载入账号昵称（轮询顺序）
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

    from caption_dedupe import load_used_captions, save_used_captions
    seen = load_used_captions("state/seen_web3_captions.json")

    with open(args.output, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for i, row in enumerate(rows):
            nick = nicks[i % n_acc] if n_acc else ""
            # 根据策略决定语言
            if lang_mode == "content":
                lang = detect_content_lang(row.get("content", ""))
            elif lang_mode == "auto-nick":
                lang = role_lang(nick)
            elif lang_mode == "mixed_en_ms":
                # 50% 英文 + 50% 马来语，交替分配
                lang = "en" if (i % 2 == 0) else "ms"
            else:
                lang = lang_mode  # 强制统一 (zh_hant/en/ja/ms/ru)
            # 生成文案；若与跨批次/本批已用重复，则偏移 seed 重试直到唯一
            cap = make_caption(row.get("content", ""), row.get("_brief", ""),
                               row.get("_site", ""), lang, i,
                               min_len=min_len, max_len=max_len,
                               no_source=args.no_source, tone=args.tone)
            j = 1
            while cap in seen and (i + j) < 1000:
                cap = make_caption(row.get("content", ""), row.get("_brief", ""),
                                   row.get("_site", ""), lang, i + j,
                                   min_len=min_len, max_len=max_len,
                                   no_source=args.no_source, tone=args.tone)
                j += 1
            seen.add(cap)
            row["content"] = cap
            row["_lang"] = lang
            row["_role_nick"] = nick
            w.writerow(row)

    save_used_captions(seen, "state/seen_web3_captions.json")
    # 统计语言分布
    from collections import Counter
    lang_stats = Counter()
    with open(args.output, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            lang_stats[r.get("_lang", "")] += 1
    print(f"[OK] wrote {len(rows)} web3 captions (lang_mode={lang_mode}, dist={dict(lang_stats)}) -> {args.output}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
