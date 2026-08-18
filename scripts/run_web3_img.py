#!/usr/bin/env python3
"""
run_web3_img.py — Web3/Crypto 图文一键发布（CoinDesk/CoinTelegraph RSS → 繁体/英文文案 → 图文发布）

模拟 Binance App timeline 的资讯卡片：每条数字货币资讯配一张封面图（图文匹配），
文案为发帖人第一人称口吻，语言统一（繁体中文 zh_hant 或英文 en，不中英混杂）。

用法：
    # 繁体中文文案（默认）
    py -3 scripts/run_web3_img.py --accounts-csv accounts_web3_img_10.csv --lang zh_hant --per-site 5 --yes

    # 英文文案
    py -3 scripts/run_web3_img.py --accounts-csv accounts_web3_en10.csv --lang en --per-site 5 --yes

    # 只采集+文案、不发布（预演）
    py -3 scripts/run_web3_img.py --skip-publish

去重：state/seen_web3_img.json 跨批次记录已发消息，自动跳过、不重复。
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

# 话题关键词 → (繁体中文, 英文)（用于文案话题标签，保证图文主题一致）
TOPIC_MAP = [
    (["bitcoin", "btc"], "比特幣", "Bitcoin"),
    (["ethereum", "eth"], "以太坊", "Ethereum"),
    (["solana", "sol"], "Solana", "Solana"),
    (["xrp", "ripple"], "瑞波", "XRP"),
    (["etf"], "ETF", "ETF"),
    (["binance", "coinbase", "okx", "exchange"], "交易所", "exchange"),
    (["sec", "regulat", "hong kong", "香港"], "監管", "regulation"),
    (["defi"], "DeFi", "DeFi"),
    (["nft"], "NFT", "NFT"),
    (["stablecoin", "tether", "usdt", "usdc"], "穩定幣", "stablecoin"),
    (["mining", "miner"], "挖礦", "mining"),
    (["meme"], "Meme幣", "meme"),
    (["ai"], "AI", "AI"),
]

# 繁体中文 · 第一人称口吻（香港/台湾通用繁体）
ZH_TEMPLATES = [
    "睇到今日幣圈新聞，{topic}又有新動靜。市場起起伏伏，但呢類消息都值得留意多兩眼。📈 #加密貨幣 #{topic} #幣市",
    "今日幣市焦點又係{topic}。呢排走勢反覆，見到呢種消息都會諗多一層。🧐 #幣市 #{topic} #加密貨幣",
    "一早就刷到{topic}嘅新聞。幣圈資訊更新得太快，跟唔上就落後。⚡ #加密貨幣 #{topic} #資訊",
    "{topic}嘅消息又上頭條。老實講，而家個市夠晒波動，任何風吹草動都要留意。📊 #幣市 #{topic} #加密貨幣",
    "啱啱見到{topic}嘅新動向，值得同大家分享下。做咗咁耐，越嚟越覺得資訊差先係關鍵。💡 #加密貨幣 #{topic} #幣圈",
]

# 英文 · 第一人称口吻
EN_TEMPLATES = [
    "Another {topic} headline worth tracking today. The market keeps moving, but these signals matter. 📈 #crypto #{topic} #markets",
    "Today's crypto focus is {topic} again. Reading into what this means next. 🧐 #crypto #{topic} #trading",
    "Fresh {topic} news just dropped — staying ahead in this space means keeping up. ⚡ #crypto #{topic} #news",
    "{topic} is back in the headlines. Honestly, with this much volatility every move deserves a second look. 📊 #crypto #{topic} #markets",
    "Just saw the latest {topic} development and had to share. Information edge is everything here. 💡 #crypto #{topic} #crypto",
]


def _u8():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


def _run(cmd, env_extra=None):
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _topic(title: str, lang: str) -> str:
    low = title.lower()
    for kws, zh, en in TOPIC_MAP:
        if any(k in low for k in kws):
            return zh if lang == "zh_hant" else en
    return "加密貨幣" if lang == "zh_hant" else "crypto"


def _caption(title: str, site: str, lang: str, idx: int) -> str:
    topic = _topic(title, lang)
    default = "加密貨幣" if lang == "zh_hant" else "crypto"
    pool = ZH_TEMPLATES if lang == "zh_hant" else EN_TEMPLATES
    cap = pool[idx % len(pool)].format(topic=topic)
    # 话题为默认值时，去掉重复的话题标签（模板已带 #加密貨幣 / #crypto）
    if topic == default:
        cap = re.sub(r"#" + re.escape(topic) + r"\s*", "", cap, count=1)
    return cap


def main() -> int:
    _u8()
    ap = argparse.ArgumentParser(
        description="Web3/Crypto 图文一键发布（CoinDesk/CoinTelegraph → 文案 → 图文）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--accounts-csv", default="accounts_web3_img_10.csv")
    ap.add_argument("--sources", default="coindesk,cointelegraph", help="来源 key：coindesk,cointelegraph")
    ap.add_argument("--per-site", type=int, default=5, help="每个来源取多少条")
    ap.add_argument("--lang", default="zh_hant", choices=["zh_hant", "en"],
                    help="文案语言：繁体中文或英文（语言统一）")
    ap.add_argument("--dedupe-file", default="state/seen_web3_img.json")
    ap.add_argument("--reset-dedupe", action="store_true")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="web3_img_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw = wd / f"web3_img_raw_{ts}.csv"
    moments = wd / f"moments_web3_img_{ts}.csv"

    dedupe_path = ROOT / args.dedupe_file
    if args.reset_dedupe and dedupe_path.exists():
        dedupe_path.unlink()
        print(f"[web3_img] 已重置去重档：{dedupe_path.name}")

    # Step 1: 采集
    print(f"\n=== Step 1/3: 采集 CoinDesk/CoinTelegraph 图文（lang={args.lang}）===")
    cmd = PY + [str(HERE / "fetch_web3_img.py"),
                "--sources", args.sources, "--per-site", str(args.per_site),
                "--dedupe-file", str(dedupe_path), "--output", str(raw)]
    if _run(cmd) != 0 or not raw.exists():
        print("[web3_img] 采集失败，终止。", file=sys.stderr)
        return 1

    # Step 2: 文案
    print("\n=== Step 2/3: 第一人称文案（话题匹配，语言统一）===")
    rows = list(csv.DictReader(raw.open(encoding="utf-8-sig")))
    out_rows = []
    for i, r in enumerate(rows):
        cap = _caption(r["content"], r.get("_site", ""), args.lang, i)
        out_rows.append({**r, "content": cap, "_lang": args.lang})
    fields = list(out_rows[0].keys()) if out_rows else []
    if "_lang" not in fields:
        fields.append("_lang")
    with moments.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"[web3_img] moments ready: {len(out_rows)} 条图文")

    if args.skip_publish:
        print("\n[web3_img] --skip-publish，仅产出素材：", moments)
        return 0

    # Step 3: 发布
    print("\n=== Step 3/3: 发布（图文帖，图片自动下载→S3）===")
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[web3_img] 账号 CSV 不存在: {acc}", file=sys.stderr)
        return 2
    if not args.yes:
        if input(f"  确认发布 {len(out_rows)} 条图文帖？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[web3_img] 已取消。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "2.5",
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print("[web3_img] 发布返回非零，请查看 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[web3_img] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
