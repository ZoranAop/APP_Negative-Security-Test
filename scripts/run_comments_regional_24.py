#!/usr/bin/env python3
"""
run_comments_regional_24.py — Add comments to 24 regional-news posts
(result/publish_20260915_110459.csv) using FRESH 670-pool accounts that
did not publish the posts. 3-15 random comments per post, random-language,
in commenter voice (agree / add / question / enthusiasm).
"""
from __future__ import annotations

import csv, json, random, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

REPORT = ROOT / "result" / "publish_20260915_110459.csv"
TOKENS = ROOT / "result" / "tokens.json"
INTERACT_XLSX = ROOT / "互动用户池_670账号.xlsx"
POST_COMMENTS = HERE / "post_comments.py"
BATCH_OUT = ROOT / "temp_comments_regional_24_batch.csv"

# ─── Contextual comment banks by topic ─────────────────────────────────────
# each topic has en / zh_hant / ja / ko / ms / id variants
BANKS = {
    "politics": {
        "en": [
            "Strong take. I've been saying this for months now.",
            "Inflation is definitely the core issue people are feeling. Politics has to answer to that.",
            "This is exactly the kind of long-term view that's missing from the usual political chatter.",
            "Not everyone agrees with this framing, but the data is trending this way.",
            "I'm watching the next election very closely on this front.",
            "Housing alone will define this cycle. Everything else is secondary.",
            "The cost-of-living point is hitting harder than most analysts expected.",
        ],
        "zh_hant": [
            "說得對，通膨這塊確實是普通百姓最敏感的問題。",
            "這個觀點我認同，長期才會看清楚方向。",
            "住房問題不解決，其他政策都白搭。",
        ],
        "ja": [
            "この視点に大賛成。次の選挙でも注目します。",
            "生活コストの問題が本当に核心だなと思います。",
            "長期視点で言うと、今の政策はまだ始まったばかり。",
        ],
        "ko": [
            "이 분석에 동의합니다. 특히 주거비가 핵심 문제죠.",
            "다음 선거에서 어떻게 흘러갈지 주목하고 있어요.",
        ],
        "ms": [
            "Saya setuju, kos sara hidup memang isu utama sekarang.",
            "Perkara perumahan tu memang tak boleh diabaikan.",
            "Ini pandangan jangka panjang yang baik.",
        ],
        "id": [
            "Setuju, inflasi memang isu paling terasa bagi masyarakat.",
            "Ini analisis yang tajam. Saya follow perkembangan selanjutnya.",
            "Harga bahan pokok jadi tolok ukur kebijakan yang nyata.",
        ],
    },
    "tech": {
        "en": [
            "The semiconductor angle here is underrated. That's where the real leverage is.",
            "I've been following the AI compute buildout and the pace is genuinely surprising.",
            "Deep tech is the only lane with real defensibility right now.",
            "The talent question is real but the output is showing up regardless.",
            "This is the kind of tech trend that compounds quietly and then all at once.",
            "Cambridge + SG + Seoul research output is a serious combination.",
            "The gap between policy and engineering speed is the real bottleneck.",
        ],
        "zh_hant": [
            "半導體這塊被低估了，真正的槓桿在這裡。",
            "AI算力建設的速度確實超出預期。",
            "深科技是唯一有護城河的赛道。",
        ],
        "ja": [
            "半導体の角度が一番重要です。ここが見えてない人が多い。",
            "AIインフラの拡張速度、確かに驚きです。",
            "ディープテックが唯一デファビシビリティを持つ領域。",
        ],
        "ko": [
            "반도체가 정말 핵심이죠. AI 인프라 확장 속도도 놀랍습니다.",
            "딥테크가 유일한 차별화 포인트입니다.",
        ],
        "ms": [
            "Sudut semikonduktor memang underrated. Itu leverage sebenar.",
            "Kelajuan AI compute buildout memang mengejutkan.",
            "Deep tech memang satu-satunya lane yang ada defensibility.",
        ],
        "id": [
            "Sudut semikonduktor sangat underrated. Di situ leverage sebenarnya.",
            "Laju ekspansi AI compute memang bikin kagum.",
            "Deep tech satu-satunya yang punya defensibility nyata.",
        ],
    },
    "web3": {
        "en": [
            "Regulatory clarity is exactly what this sector needed to mature.",
            "The RWA tokenization story is going to be the biggest narrative of the next cycle.",
            "I've been tracking the institutional on-ramps and the pace is accelerating.",
            "TradFi absorbing DeFi rails is the real story, not the other way around.",
            "The settlement layer is where all the value will eventually get captured.",
            "Boring infrastructure work is what makes the exciting applications possible.",
        ],
        "zh_hant": [
            "監管清晰度才是這個行業成熟需要的關鍵。",
            "RWA代幣化將會是下一輪周期最大的敘事。",
            "TradFi吸收DeFi基礎設施才是真正的主线。",
        ],
        "ja": [
            "規制の明確さこそが成熟に必要だったもの。",
            "RWAトークン化が次のサイクル最大のナラティブになる気がする。",
            "結算レイヤーにこそ価値が詰まる。",
        ],
        "ko": [
            "규제 명확성이 바로 이 섹터가 성숙에 필요한 것이었죠.",
            "RWA 토큰화가 다음 사이클 최대 서사가 될 겁니다.",
            "결제 레이어에 가치의 핵심이 있습니다.",
        ],
        "ms": [
            "Ketelapan regulator memang yang sector ni perlukan untuk mature.",
            "RWA tokenization akan jadi narrative paling besar next cycle.",
            "TradFi serap rails DeFi — itu cerita sebenar.",
        ],
        "id": [
            "Kejelasan regulasi memang yang dibutuhkan untuk mature.",
            "RWA tokenization bakal jadi narrative terbesar siklus berikutnya.",
            "TradFi serap rails DeFi — itu cerita sesungguhnya.",
        ],
    },
    "crypto": {
        "en": [
            "The ETF inflow pattern is the clearest institutional signal we have.",
            "Not calling a top — just saying the structure has fundamentally changed.",
            "The halving cycle plus institutional supply is a different beast.",
            "I DCA through every dip and the math works out in the long run.",
            "Retail behaviour is shifting from FOMO to measured allocation.",
            "The holder base keeps getting deeper every cycle.",
        ],
        "zh_hant": [
            "ETF資金流入是最清晰的機構訊號。",
            "我不預測頂，只說結構已經根本改變了。",
            "每次下跌DCA，長期數學上算得通。",
        ],
        "ja": [
            "ETF流入パターンが最も明確なインシグナル。",
            "トップコールはしない — 構造が変わったってこと。",
            "毎回のD&Dで長期数学が成立する。",
        ],
        "ko": [
            "ETF 유입 패턴이 가장 명확한 기관 신호입니다.",
            "탑은 안 부릅니다 — 구조 자체가 바뀌었죠.",
            "매 하락 DCA, 장기 수학은 통합니다.",
        ],
        "ms": [
            "ETF inflow pattern memang signal paling clear dari institusi.",
            "Tak call top — struktur dah berubah asasnya.",
            "DCA setiap kali turun, matematik jangka panjang memang jalan.",
        ],
        "id": [
            "Pola inflow ETF adalah sinyal institusi paling jelas.",
            "Tidak call top — strukturnya sudah berubah fundamental.",
            "DCA tiap turun, dalam jangka panjang matematikanya jalan.",
        ],
    },
}

# language distribution: random pick from each post's source language + en mix
def _roll_lang():
    r = random.random()
    if r < 0.5:
        return "en"
    elif r < 0.65:
        return "zh_hant"
    elif r < 0.75:
        return "ja"
    elif r < 0.85:
        return "ko"
    elif r < 0.92:
        return "ms"
    else:
        return "id"


def load_fresh_accounts(n: int, exclude_emails: set, used_publishers: set) -> list:
    """Load fresh 670-pool accounts that have tokens but did NOT publish these 24 posts."""
    import openpyxl
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))
    # Fresh = in tokens (already logged in) but NOT a publisher
    fresh = [e for e in tokens.keys()
             if e not in used_publishers]
    random.shuffle(fresh)
    return fresh[:n]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-comments", type=int, default=3)
    ap.add_argument("--max-comments", type=int, default=15)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    # 1. Read report to get post IDs + publishers
    report = list(csv.DictReader(REPORT.open(encoding="utf-8-sig")))
    posts = []
    publishers = set()
    for r in report:
        pid = (r.get("moment_id_or_err") or "").strip()
        email = (r.get("email") or "").strip()
        topic = (r.get("_source") or "general").split("_")[-1]  # last part: politics/tech/web3/crypto
        if pid.isdigit() and "True" in str(r.get("success", "")):
            posts.append({"post_id": int(pid), "topic": topic, "email": email})
            if email:
                publishers.add(email)

    print(f"[posts] {len(posts)} successful posts, {len(publishers)} publisher accounts to exclude")
    print(f"  topics: {dict((t, sum(1 for p in posts if p['topic']==t)) for t in set(p['topic'] for p in posts))}")

    # 2. Pick fresh commenters (in tokens, not publishers)
    tokens = json.loads(TOKENS.read_text(encoding="utf-8"))
    fresh = [e for e in tokens.keys() if e not in publishers]
    random.shuffle(fresh)
    print(f"[commenters] {len(fresh)} fresh accounts (token holders, not publishers)")

    # 3. Build batch
    batch = []
    for p in posts:
        n = random.randint(args.min_comments, args.max_comments)
        topic = p["topic"]
        bank = BANKS.get(topic, BANKS["general"] if "general" in BANKS else BANKS["crypto"])
        for _ in range(n):
            lang = _roll_lang()
            text = random.choice(bank.get(lang, bank["en"]))
            batch.append({
                "email": random.choice(fresh),
                "post_id": p["post_id"],
                "topic": topic,
                "text": text,
                "nickname": "",
            })

    random.shuffle(batch)
    with BATCH_OUT.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["email", "post_id", "topic", "text", "nickname"])
        w.writeheader()
        for row in batch:
            w.writerow(row)

    from collections import Counter
    per_post = Counter(r["post_id"] for r in batch)
    print(f"\n[batch] {len(batch)} total comments across {len(posts)} posts")
    print(f"  per-post range: {min(per_post.values())}-{max(per_post.values())}")
    lang_counter = Counter()
    for r in batch:
        t = r["text"]
        if any("\u3040" <= c <= "\u30ff" for c in t):
            lang_counter["ja"] += 1
        elif any("\u4e00" <= c <= "\u9fff" for c in t):
            lang_counter["zh/ms/id"] += 1
        else:
            lang_counter["en"] += 1
    print(f"  lang distribution: {dict(lang_counter)}")

    if not args.yes:
        if input("  Confirm post comments? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled."); return 0

    # Write accounts CSV for post_comments.py token refresh
    accounts_csv = ROOT / "accounts_regional_24_commenters.csv"
    with accounts_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
        w.writeheader()
    # Load passwords from xlsx
    import openpyxl
    wb = openpyxl.load_workbook(str(INTERACT_XLSX), read_only=True)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    pwd_map = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        d = dict(zip(headers, row))
        e = str(d.get("邮箱", "") or "").strip()
        pwd_map[e] = str(d.get("密码", "") or "")
    wb.close()
    with accounts_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
        w.writeheader()
        for i, e in enumerate(fresh[:200]):  # include top 200 for login fallback
            w.writerow({"序号": i + 1, "昵称": "", "邮箱": e, "密码": pwd_map.get(e, "")})

    cmd = PY + [str(POST_COMMENTS),
                "--batch", str(BATCH_OUT),
                "--tokens", str(TOKENS),
                "--accounts", str(accounts_csv),
                "--delay", str(args.delay)]
    print(f"\n[exec] {' '.join(str(c) for c in cmd)}")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    return rc


if __name__ == "__main__":
    sys.exit(main())
