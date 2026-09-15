#!/usr/bin/env python3
"""
run_comments_x_video_18.py — Add 3-12 random-language comments to the 18
X-video posts published by run_x_video_publish_18.py.

- Uses the 850 pool for BOTH publisher and commenter (per requirement)
- Commenters are picked from 850 pool minus the 18 publishers
- 3-12 comments per post, random count
- Languages: 60% EN / 20% zh_hant / 20% mixed (ja/ko/ms/id)
- Comment tone: agree / add / question / humor, no AI flavor
"""
from __future__ import annotations

import csv, json, random, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

RESULTS_FILE = ROOT / "x_video_18_20260915_144947_run" / "results.json"
TOKENS = ROOT / "result" / "tokens.json"
POOL_850 = ROOT / "pre_企管用户_850.csv"
POST_COMMENTS = HERE / "post_comments.py"
BATCH_OUT = ROOT / "temp_comments_x_video_18_batch.csv"

# ─── Comment banks: topic → language → list ──────────────────────────────
# Topics cover: daily life / web3 / politics / tech / crypto
BANKS = {
    "daily_life": {
        "en": [
            "This video is hilarious, I was laughing the whole time",
            "Love how real this feels, very natural",
            "I saw this exact situation happen yesterday 😂",
            "The timing on this video is perfect",
            "This is the kind of clip that deserves a viral moment",
            "Watched this on loop, it's so satisfying",
            "Very funny, the reaction at the end got me",
            "I would've been so embarrassed if it was me",
            "This makes my day, thanks for sharing",
            "Caught me off guard in the best way",
        ],
        "zh_hant": [
            "看完笑翻，反應也太自然了",
            "這種真實感太愛了",
            "昨天剛遇到一模一样的情況",
            "影片的節奏掌握得很好",
            "這種畫面真的值得傳播",
            "看了好幾遍，太治癒了",
        ],
        "ja": [
            "笑って止まらない、自然な反応が最高",
            "この動画、何度も見たくなる",
            "昨日まさに同じ目に遭った",
        ],
        "ko": [
            "이 영상 웃음이 터져요",
            "반응이 너무 자연스러워서 좋아요",
        ],
        "ms": [
            "Video ni memang lawak, saya gelak sampai habiskah",
            "Rasa sangat natural dan real",
            "Tadi pagi saya jumpa situasi macam ni juga",
        ],
        "id": [
            "Video ini lucu banget, saya ketawa sampai selesai",
            "Perasaannya sangat natural",
            "Tadi pagi saya juga ngalamin yang sama",
        ],
    },
    "web3": {
        "en": [
            "The RWA narrative is genuinely the next leg of this cycle",
            "I've been tracking this protocol's TVL — the retention is real",
            "Shielded red envelopes is a smart move for onboarding friends",
            "USDT settlement for commodities is the infra we needed",
            "KCGI treasure map rewards are a smart growth play",
            "Yield farming on L1 is where the next alpha hides",
            "Anoma's privacy angle is undervalued right now",
            "The UX gap on new wallets is closing fast",
            "Watch the tokenomics carefully before FOMO",
            "Real users are the only KPI that matters",
        ],
        "zh_hant": [
            "RWA代幣化確實是下一輪的主線",
            "Watched their TVL 好一陣子，留存是真的好",
            "Shielded 紅包對拉新人確實聰明",
            "USDT結算大宗商品，是市場真正需要的基建",
            "KCGI 地圖獎勵是成長的好打法",
            "L1 上的 Yield farming 才是下一波 alpha",
        ],
        "ja": [
            "RWAは確かに次のサイクルの主要テーマ",
            "TVLの継続率が本物だと感じている",
            "プライバシーの角度がまだ割と評価されていない",
        ],
        "ko": [
            "RWA가 다음 사이클 핵심이죠",
            "TVL 유지율이 진짜 실전 데이터입니다",
        ],
        "ms": [
            "Naratif RWA memang leg seterusnya cycle ni",
            "Saya track TVL dia, retention memang real",
        ],
        "id": [
            "Narasi RWA memang leg berikutnya dari siklus ini",
            "Saya track TVL-nya, retention-nya nyata",
        ],
    },
    "politics": {
        "en": [
            "Cultural clash in a handshake — fascinating",
            "The way Putin handled that was very calculated",
            "India's reaction is genuinely funny and telling",
            "Cross-cultural moments like this are a study in social norms",
            "I appreciate how the video cuts to the exact moment",
            "The body language is doing all the storytelling",
            "Interesting diplomatic moment, and very human",
            "The social status gap made this awkward by design",
        ],
        "zh_hant": [
            "握手之間的文化衝突，看得很開眼",
            "普京那個動作處理得很精準",
            "印度的反應真的很有看頭",
            "影片剪到那個關鍵瞬間，很好",
        ],
        "ja": [
            "握手の文化差、非常に興味深い",
            "あの瞬間の切り取り方が秀逸",
        ],
        "ko": [
            "악수 한 동작의 문화 차이, 흥미롭습니다",
            "그 순간을 딱 잘라서 보여주는 편집이 좋네요",
        ],
        "ms": [
            "Benturan budaya dalam satujabat tangan, menarik",
            "Cara dia handle it memang sangat calculated",
        ],
        "id": [
            "Benturan budaya dalam satu jabat tangan, menarik",
            "Cara dia menangani momen itu sangat terukur",
        ],
    },
    "tech": {
        "en": [
            "Jensen Huang on AI chips — he knows what he's doing",
            "Trump calling into an interview is a very Trump moment",
            "The AI doom-saying narrative is getting thinner",
            "UK's King meeting AI leaders is the right call",
            "Apple DUO warm blanket comment was the funniest reply I've seen today",
            "The iPhone DUO review angle is sharp",
            "I agree — deceleration just hands the lead to China",
            "AI is the new growth engine, not a risk to fear",
        ],
        "zh_hant": [
            "黃仁勛聊AI晶片，水平不用說",
            "川普殺進專訪現場，太川普了",
            "AI末日論的聲量越來越虛",
            "查爾斯會見AI巨頭，方向是對的",
            "蘋果DUO那句『暖寶寶』評註太好笑了",
        ],
        "ja": [
            "黄仁勲のAIチップ論、圧倒的",
            "トランプが取材現場に飛び込み、典型トランプ",
            "AIの終末論は薄れてきてる",
        ],
        "ko": [
            "젠슨 황의 AI 칩 논평, 수준이 다릅니다",
            "트럼프가 인터뷰 현장 전화, 전형적 트럼프",
        ],
        "ms": [
            "Jensen Huang bercakap pasal AI chip, memang kelas",
            "Trump telefon masuk ke temu bual, sangat Trump",
        ],
        "id": [
            "Pernyataan Jensen Huang soal chip AI, kelas banget",
            "Trump menelepon ke live interview, sangat Trump",
        ],
    },
    "crypto": {
        "en": [
            "Sun Yu Chen's Lux Coffee bet is the textbook contrarian play",
            "Buy at the bottom, hold through the noise — that's the whole game",
            "1亿 USD profit from 2% position is wild",
            "The Lux Coffee store expansion post-restructuring is real",
            "His WeChat post before the buy was a tell",
            "Distressed investing is about reading the death pricing",
            "I was there through the 2022 winter, so I feel this one",
            "The governance fixup opened the door for the long leg up",
        ],
        "zh_hant": [
            "孫宇晨的瑞幸賭注，是教科書級的反向操作",
            "底部買入、風浪中持有，這就整個遊戲",
            "2% 倉位浮盈1億，太狠了",
            "重組後瑞幸的門店擴張是真的",
            "他買之前發的那個朋友圈就是信号",
            "困境投資的核心就是看死亡定價有沒有過頭",
        ],
        "ja": [
            "孫宇晨のLuckin Coffee賭けは教科書通りの逆張り",
            "2%ポジションで1億米ドルの浮き",
            "再編後、出店数は本物",
        ],
        "ko": [
            "선 위전 씨의 럭인 버틴은 교과서적 역張り",
            "2% 포지션으로 1억 불 수익, 대박",
        ],
        "ms": [
            "Pertaruhan Sun Yu Chen di Luckin memang contrarian kelasik",
            "2% position, untung 1 juta USD, memang gila",
            "Ekspansi kedai pasca-restructuring memang nyata",
        ],
        "id": [
            "Pertaruhan Sun Yu Chen di Luckin memang contrarian klasik",
            "2% position, profit 1 juta USD, gila",
            "Ekspansi gerai pasca-restrukturisasi nyata",
        ],
    },
    "general": {
        "en": [
            "Good clip, shared to the group",
            "Interesting take, bookmarked",
            "Watched this on my lunch break",
            "This is the kind of content I follow for",
            "Solid post, keep it up",
            "Came here from the feed, stays for the content",
        ],
        "zh_hant": [
            "影片剪得好，分享到大群",
            "觀點不錯，收藏了",
            "午休時看的",
        ],
        "ja": [
            "良い動画、グループに共有しました",
            "面白い視点、ブックマーク",
        ],
        "ko": [
            "좋은 영상, 그룹에 공유했습니다",
            "관점이 좋습니다, 북마크",
        ],
        "ms": [
            "Klip bagus, saya share ke group",
            "Pandangan menarik, bookmark",
        ],
        "id": [
            "Klip bagus, saya share ke grup",
            "Sudut pandangnya menarik, bookmark",
        ],
    },
}


def _roll_lang():
    r = random.random()
    if r < 0.6:
        return "en"
    elif r < 0.8:
        return "zh_hant"
    else:
        return random.choice(["ja", "ko", "ms", "id"])


def _topic_for_caption(cap: str) -> str:
    c = cap.lower()
    if any(k in c for k in ["luckin", "coin", "crypto", "defi", "nft", "btc", "eth", "solana",
                             "web3", "rwa", "usdt", "token", "airdrop", "uniswap",
                             "yield", "liquidity", "binance", "tokenpocket", "blockchain",
                             "blockchain", "layer 1", "layer 2", "bnbchain", "anoma",
                             "kcgí", "kcgil", "frags", "treasure map"]):
        return "web3"
    if "luckin" in c or "luckin coffee" in c or "瑞幸" in c or "孫宇晨" in c or "sun yuchen" in c:
        return "crypto"
    if any(k in c for k in ["trump", "Putin", "brics", "indian", "普京", "查爾斯",
                             "jensen", "ai chip", "ai 晶片", "ai chip", "ai 芯片",
                             "黃仁勳", "黄仁勋", "charles", "king", "president",
                             "presiden", "sultan", "king charles", "deepmind",
                             "openai", "anthropic", "google deepmind"]):
        return "politics"
    if any(k in c for k in ["ai", "apple", "iphone", "duo", "chip", "nvidia", "jensen",
                             "sony", "awards", "nominee", "tech", "software", "chip",
                             "warm", "apple duo", "folding"]):
        return "tech"
    if any(k in c for k in ["插队", "queue", "cut in", "line", "rules", "插", "规则",
                             "rules", "mess", "trouble", "incident"]):
        return "daily_life"
    return "general"


def _topic_for_url(url: str) -> str:
    """Map an X video URL to a comment topic via the account handle / content."""
    u = url.lower()
    if any(h in u for h in ["finworld", "binance", "uniswap", "anoma", "bnbchain",
                              "bid_bits", "orange_web3", "bitget", "motoswap",
                              "tokenpocket", "web3", "coinbase"]):
        return "web3"
    if "finworld" in u:  # 瑞幸 / 孙宇晨 (detailed distressed-investing story)
        return "crypto"
    if any(h in u for h in ["alina_lipp", "voachinese", "altcap", "sony",
                              "yiyong", "bagzuhre", "shaok"]):
        # alina=普京空姐(政治), voa=AI(科技), altcap=川普黄仁勋(科技),
        # sony=颁奖(科技), yiyong=插队(生活), bagzuhre=男人惹事(生活), shaok=苹果DUO(科技)
        if "alina_lipp" in u:
            return "politics"
        if "yiyong" in u or "bagzuhre" in u:
            return "daily_life"
        return "tech"
    return "general"


def _load_used_emails() -> set:
    used = set()
    try:
        used.update(json.loads(TOKENS.read_text(encoding="utf-8")).keys())
    except Exception:
        pass
    return used


def pick_commenters(n: int, exclude: set) -> list[dict]:
    picked, seen = [], set(exclude)
    for r in csv.DictReader(POOL_850.open(encoding="utf-8-sig")):
        email = (r.get("邮箱") or "").strip()
        if not email or email in seen:
            continue
        seen.add(email)
        picked.append(r)
        if len(picked) >= n:
            break
    return picked


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-comments", type=int, default=3)
    ap.add_argument("--max-comments", type=int, default=12)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    # Load 18 post results
    results = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    ok_posts = [r for r in results if r["status"] == "OK" and r.get("moment_id")]
    publishers = {r["email"] for r in ok_posts}
    print(f"[posts] {len(ok_posts)} successful video posts, {len(publishers)} publishers excluded")

    # Get 850 pool
    fresh = pick_commenters(len(ok_posts), publishers | _load_used_emails())
    print(f"[commenters] {len(fresh)} fresh 850-pool accounts (non-publisher, non-tokens)")
    if not fresh:
        print("[ERROR] No fresh accounts available", file=sys.stderr)
        return 1

    # Build batch
    batch = []
    for p in ok_posts:
        n = random.randint(args.min_comments, args.max_comments)
        topic = _topic_for_url(p.get("url", ""))
        for _ in range(n):
            lang = _roll_lang()
            pool = BANKS[topic].get(lang, BANKS["general"].get(lang, BANKS["general"]["en"]))
            batch.append({
                "email": random.choice(fresh)["邮箱"].strip(),
                "post_id": p["moment_id"],
                "topic": topic,
                "text": random.choice(pool),
                "nickname": "",
            })

    random.shuffle(batch)
    BATCH_OUT.write_text(
        "\r\n".join(
            ["email,post_id,topic,text,nickname"] +
            [f"{r['email']},{r['post_id']},{r['topic']},\"{r['text'].replace(chr(34),'')}\",\"{r['nickname']}\""
             for r in batch]
        ),
        encoding="utf-8-sig",
    )

    from collections import Counter
    per_post = Counter(r["post_id"] for r in batch)
    lang_c = Counter()
    for r in batch:
        t = r["text"]
        if any("\u3040" <= c <= "\u30ff" for c in t):
            lang_c["ja"] += 1
        elif any("\u4e00" <= c <= "\u9fff" for c in t):
            lang_c["zh_hant"] += 1
        else:
            lang_c["en/other"] += 1

    print(f"\n[batch] {len(batch)} comments across {len(ok_posts)} posts")
    print(f"  per-post: {min(per_post.values())}-{max(per_post.values())}")
    print(f"  lang dist: {dict(lang_c)}")

    if not args.yes:
        if input("  Confirm post comments? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled."); return 0

    # Build accounts CSV for token refresh (with passwords from 850 pool)
    pwd_map = {}
    for r in csv.DictReader(POOL_850.open(encoding="utf-8-sig")):
        pwd_map[r["邮箱"].strip()] = r.get("密码", "").strip()
    accts_csv = ROOT / "accounts_x_video_18_commenters.csv"
    with accts_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
        w.writeheader()
        for i, a in enumerate(fresh):
            w.writerow({"序号": i + 1, "昵称": a.get("昵称", ""),
                       "邮箱": a["邮箱"].strip(), "密码": pwd_map.get(a["邮箱"].strip(), "")})

    cmd = PY + [str(POST_COMMENTS),
                "--batch", str(BATCH_OUT),
                "--tokens", str(TOKENS),
                "--accounts", str(accts_csv),
                "--delay", str(args.delay)]
    print(f"\n[exec] {' '.join(str(c) for c in cmd)}")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    return rc


if __name__ == "__main__":
    sys.exit(main())
