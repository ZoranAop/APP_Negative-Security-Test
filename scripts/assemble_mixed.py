#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assemble_mixed.py — 组装「混合交错」发帖素材（拟真、去规则化）。

设计目标：产出看起来像真人、而非机器批量的一批帖子。核心手段：
  1) 每个用户的发帖数量随机（--min-posts ~ --max-posts），不形成固定数量规则；
  2) 每人帖子按 T/I/Q 交错，且不允许全同类（至少 1 文本类 + 1 图文）；
  3) 语言按用户单语分配（每人自己的所有帖同一种语言，用户间覆盖多语）；
  4) 同一用户内图文贴的配文不重复；文本/图文素材全局不重复消费。

帖类型：
  T = 文本贴（web3 真实资讯标题 + 第一人称点评）
  I = 图文贴（图库素材 image_urls + 场景化配文）
  Q = 问题贴（把资讯要点转成开放式提问，纯文本；平台无原生投票，故用提问式文本模拟）

用法：
  py -3 scripts/assemble_mixed.py \
      --accounts-csv accounts.csv \
      --text-csv web3_run/text_raw.csv \
      --image-csv web3_run/img_raw.csv \
      --langs zh_hant,en,ja,ms \
      --min-posts 3 --max-posts 7 \
      --output web3_run/moments_mixed.csv

输出 publish_from_tokens.py 兼容 CSV（含辅助列 _ptype/_lang/_site/_dedupe_key）。
"""
from __future__ import annotations
import argparse, csv, re, sys, random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from caption_multilang import detect_scene, pick_template  # 复用图文场景文案模板池

ROOT = Path(__file__).resolve().parent.parent

# ---- 每语言：web3 资讯的第一人称点评 ----
COMMENT = {
 "zh_hant": ["這則消息值得追蹤，影響不會只有一天。", "資訊差就是機會差，先看懂再說。", "市場情緒很極端，風險控制擺第一。", "長線來看，耐心的人通常笑到最後。", "監管與合規往前走，是行業成熟的訊號。", "把重點記下來，這波值得持續觀察。", "這種消息最能看出資金的真實態度。", "先別急著追，看清楚再決定。"],
 "en":      ["Worth tracking — the impact won't be just one day.", "Information edge is everything; understand it first.", "Sentiment is extreme; risk control comes first.", "Long term, the patient usually win.", "Compliance moving forward signals a maturing industry.", "Noting this down — worth watching closely.", "This is where you see real money's stance.", "Don't rush in; get clarity first."],
 "ja":      ["この件は注視したい。影響は一日で終わらない。", "情報差が勝負。まず理解してから動く。", "センチメントは極端。リスク管理が最優先。", "長期では忍耐する人が勝つ。", "規制の前進は業界成熟のサイン。", "メモしておく。じっくり見る価値あり。", "資金の本音が見える一件。", "焦らず、まず状況を見極める。"],
 "ms":      ["Berita ni patut dipantau — kesannya bukan sehari sahaja.", "Kelebihan maklumat itu segalanya; fahami dahulu.", "Sentimen melampau; kawalan risiko didahulukan.", "Jangka panjang, yang sabar biasanya menang.", "Pematuhan yang bergerak ke depan tanda industri matang.", "Dicatat — berbaloi diperhatikan.", "Di sini nampak sikap sebenar dana besar.", "Jangan tergesa; fahami dulu."],
}
# ---- 每语言：提问式帖模板（{topic} 填资讯要点）----
QUESTION = {
 "zh_hant": ["關於「{topic}」，你怎麼看？會影響你的佈局嗎？", "看到「{topic}」這則消息，大家是偏多還是偏空？", "「{topic}」——你覺得這是機會還是風險？留言聊聊。", "如果「{topic}」成真，對這個賽道會是好事嗎？"],
 "en":      ["What's your take on \"{topic}\"? Does it change your positioning?", "Seeing \"{topic}\" — are you leaning bullish or bearish?", "\"{topic}\" — opportunity or risk? Drop your thoughts.", "If \"{topic}\" plays out, is it good for the space?"],
 "ja":      ["「{topic}」について、どう見ますか？戦略に影響しますか？", "「{topic}」を見て、強気ですか弱気ですか？", "「{topic}」——チャンス？それともリスク？コメントで。", "もし「{topic}」が実現したら、この分野にプラス？"],
 "ms":      ["Apa pandangan anda tentang \"{topic}\"? Ubah strategi anda?", "Melihat \"{topic}\" — anda cenderung bullish atau bearish?", "\"{topic}\" — peluang atau risiko? Kongsi pendapat anda.", "Jika \"{topic}\" jadi kenyataan, baik untuk sektor ni?"],
}
QTAGS = {"zh_hant": "#web3 #討論 #加密", "en": "#web3 #Discussion #Crypto", "ja": "#web3 #議論 #暗号資産", "ms": "#web3 #Perbincangan #Kripto"}
TTAGS = {"zh_hant": "#web3 #加密資訊", "en": "#web3 #CryptoNews", "ja": "#web3 #暗号ニュース", "ms": "#web3 #BeritaKripto"}
SITE_TAG = {"techflow": "#TechFlow", "web3bbs": "#Web3BBS", "foresight": "#ForesightNews",
            "menews": "#MENews", "web3caff": "#Web3Caff", "panews": "#PANews", "bingx": "#BingX", "blockweeks": "#BlockWeeks"}

def clean_title(t: str) -> str:
    t = re.sub(r"\s+", " ", (t or "")).strip()
    t = re.split(r"\s*[\|｜]\s*(?:PA日報|PA日报|會員週報|会员周报).*$", t)[0].strip()
    return t.strip("｜|-–— 、，,").strip()

def _contains_cjk(text: str) -> bool:
    """Check if text contains CJK (Chinese/Japanese/Korean) characters."""
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf' or '\uf900' <= ch <= '\ufaff':
            return True
    return False


def text_caption(title, brief, site, lang, salt):
    ct = clean_title(title)
    cm = COMMENT[lang][salt % len(COMMENT[lang])]
    tagline = f"{TTAGS[lang]} {SITE_TAG.get(site,'')}".strip()
    # 语言一致性：如果目标语言是非中文但标题含中文，则不附加中文标题
    if lang in ("en", "ja", "ms") and lang != "ja":
        if _contains_cjk(ct) and lang == "en":
            # 纯英文模式：只用英文评论 + 标签，不混入中文标题
            body = cm
        else:
            body = f"{cm}\n\n{ct}"
    else:
        body = f"{ct}\n{cm}"
    return f"{body}\n{tagline}"[:280]

def question_caption(title, lang, salt):
    ct = clean_title(title)
    # 语言一致性：如果目标语言是英文但标题含中文，使用通用话题替代
    if lang == "en" and _contains_cjk(ct):
        ct = "this latest crypto development"
    q = QUESTION[lang][salt % len(QUESTION[lang])].format(topic=ct[:34])
    return f"{q}\n{QTAGS[lang]}"[:280]

_HASHTAG_RE = re.compile(r"#[^\s#]+")

def _orig_hashtag(orig: str) -> str:
    """从图库原始 content 里取一个话题标签作为差异化后缀（图库标题多含 #标签）。"""
    tags = _HASHTAG_RE.findall(orig or "")
    return tags[0] if tags else ""

def image_caption(orig, lang, used, seen_contents: set):
    """图文配文：优先用场景模板；若与已用配文重复，追加图库原图的一个话题标签做差异化，
    仍重复则再加序号，确保整批内配文文本不重复。"""
    scene = detect_scene(orig or "")
    base = pick_template(scene, lang, used)
    cap = base
    if cap in seen_contents:
        tag = _orig_hashtag(orig)
        if tag and tag not in cap:
            cap = f"{base} {tag}"
    if cap in seen_contents:
        k = 2
        while f"{cap} ·{k}" in seen_contents:
            k += 1
        cap = f"{cap} ·{k}"
    seen_contents.add(cap)
    return cap

def build_pattern(n_posts: int, rng: random.Random) -> list[str]:
    """生成长度 n_posts 的 T/I/Q 序列，保证：非全同类、至少 1 文本类 + 1 图文、
    问题贴占比最低、相邻尽量不同类。"""
    if n_posts <= 1:
        return ["I"] if rng.random() < 0.5 else ["T"]
    # 先保证骨架：至少 1 个 I 和 1 个 T
    seq = ["I", "T"]
    # 问题贴以较低概率加入（每帖 ~25% 触发，且总量不超过 floor(n/3)）
    max_q = max(0, n_posts // 3)
    remaining = n_posts - len(seq)
    q_added = 0
    for _ in range(remaining):
        r = rng.random()
        if r < 0.22 and q_added < max_q:
            seq.append("Q"); q_added += 1
        elif r < 0.60:
            seq.append("I")
        else:
            seq.append("T")
    # 打散并尽量避免相邻同类
    rng.shuffle(seq)
    for i in range(1, len(seq)):
        if seq[i] == seq[i-1]:
            for j in range(i+1, len(seq)):
                if seq[j] != seq[i-1]:
                    seq[i], seq[j] = seq[j], seq[i]
                    break
    return seq

def main():
    ap = argparse.ArgumentParser(description="Assemble mixed/interleaved posting material (randomized counts).")
    ap.add_argument("--accounts-csv", required=True)
    ap.add_argument("--text-csv", required=True, help="web3 资讯 CSV（fetch_web3 输出）")
    ap.add_argument("--image-csv", required=True, help="图库 CSV（multi_source_fetch 输出）")
    ap.add_argument("--output", required=True)
    ap.add_argument("--langs", default="zh_hant,en,ja,ms",
                    help="按用户轮流分配的语言列表（每人单语）")
    ap.add_argument("--min-posts", type=int, default=3, help="每用户最少帖数")
    ap.add_argument("--max-posts", type=int, default=7, help="每用户最多帖数")
    ap.add_argument("--seed", type=int, default=None, help="随机种子（默认真随机）")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]

    accts = list(csv.DictReader(open(args.accounts_csv, encoding="utf-8-sig")))
    texts = list(csv.DictReader(open(args.text_csv, encoding="utf-8-sig")))
    imgs  = list(csv.DictReader(open(args.image_csv, encoding="utf-8-sig")))
    rng.shuffle(texts); rng.shuffle(imgs)

    n = len(accts)
    # 语言按用户均匀轮流分配（每人单语）
    langs_by_user = [langs[i % len(langs)] for i in range(n)]
    # 每人随机帖数
    counts = [rng.randint(args.min_posts, args.max_posts) for _ in range(n)]

    # 素材需求预估与容量校验
    need_ti = sum(counts)  # 上限（T+Q 都吃 text，I 吃 image）；实际按 pattern 决定
    # 先生成每人 pattern
    patterns = [build_pattern(counts[u], rng) for u in range(n)]
    need_text = sum(p.count("T") + p.count("Q") for p in patterns)
    need_img  = sum(p.count("I") for p in patterns)
    if need_text > len(texts):
        sys.exit(f"[error] 文本素材不足：需要 {need_text}，仅有 {len(texts)}。请增大 fetch_web3 的 --per-site。")
    if need_img > len(imgs):
        sys.exit(f"[error] 图文素材不足：需要 {need_img}，仅有 {len(imgs)}。请增大 multi_source_fetch 的 --limit。")

    ti = ii = 0
    per_user = []
    tmpl_used: dict = {}        # 全局共享的模板轮换计数器（跨用户尽量不撞）
    seen_img_caps: set = set()  # 全局已用图文配文，保证整批内不重复
    for u in range(n):
        lang = langs_by_user[u]
        rows = []
        for slot, kind in enumerate(patterns[u]):
            if kind == "T":
                s = texts[ti]; ti += 1
                content = text_caption(s["content"], s.get("_brief",""), s.get("_site",""), lang, slot+u)
                rows.append({"content": content, "image_urls": "", "_ptype": "text",
                             "_lang": lang, "_site": s.get("_site",""), "_dkey": ("web3", clean_title(s["content"]))})
            elif kind == "Q":
                s = texts[ti]; ti += 1
                content = question_caption(s["content"], lang, slot+u)
                rows.append({"content": content, "image_urls": "", "_ptype": "question",
                             "_lang": lang, "_site": s.get("_site",""), "_dkey": ("web3", clean_title(s["content"]))})
            else:  # I
                s = imgs[ii]; ii += 1
                content = image_caption(s.get("content",""), lang, tmpl_used, seen_img_caps)
                rows.append({"content": content, "image_urls": s.get("image_urls",""),
                             "_ptype": "image", "_lang": lang, "_site": s.get("_source",""),
                             "_dkey": ("img", s.get("_slug","") or (s.get("image_urls","").split(",")[0]))})
        per_user.append(rows)

    # 交织为轮询顺序：因每人帖数不同，按最大长度逐 slot 铺开（真实发布仍按行序 i%N 轮询）
    max_len = max(len(r) for r in per_user)
    out_rows = []
    for slot in range(max_len):
        for u in range(n):
            if slot < len(per_user[u]):
                out_rows.append(per_user[u][slot])

    fields = ["content","visibility","room_id","image_urls","location_name","location_address",
              "location_lat","location_lon","_source","_ptype","_lang","_site","_dedupe_key"]
    with open(args.output, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            dk = r["_dkey"]
            w.writerow({"content": r["content"], "visibility": "0", "room_id": "",
                        "image_urls": r["image_urls"], "location_name":"", "location_address":"",
                        "location_lat":"", "location_lon":"", "_source":"mixed",
                        "_ptype": r["_ptype"], "_lang": r["_lang"], "_site": r["_site"],
                        "_dedupe_key": f"{dk[0]}:{dk[1]}"})

    from collections import Counter
    pc = Counter(r["_ptype"] for r in out_rows)
    lc = Counter(r["_lang"] for r in out_rows)
    print(f"[OK] users={n} counts(min/max/avg)={min(counts)}/{max(counts)}/{sum(counts)/n:.1f}")
    print(f"[OK] wrote {len(out_rows)} rows. types={dict(pc)} langs={dict(lc)}")
    print(f"[OK] text used {ti}/{len(texts)}, img used {ii}/{len(imgs)} -> {args.output}")

if __name__ == "__main__":
    main()
