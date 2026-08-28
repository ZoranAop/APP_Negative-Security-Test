#!/usr/bin/env python3
"""
run_web3_stablecoin.py — web3 用户池发布稳定币资讯（美国/台湾/香港，第一人称口吻）。

1) 从 accounts_web3_100.csv（web3 用户池）选用户：
       - 英文昵称 → 英文文案
       - 中文昵称 → 繁体中文文案
       - 日文昵称 → 跳过
2) 采集稳定币资讯（Google News RSS，按地区定向：美国 en-US / 台湾 zh-TW / 香港 zh-Hant）
3) 生成第一人称「感知陈述」口吻文案，200-500 字，话题 + 口吻(点评/正向/收益)去同质
4) 纯文本发布（publish_from_tokens.py）

用法:
    py -3 scripts/run_web3_stablecoin.py --num-en 6 --num-zh 6 --skip-publish
    py -3 scripts/run_web3_stablecoin.py --num-en 6 --num-zh 6 --yes
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]
sys.path.insert(0, str(HERE))

from run_op200_crypto import (  # noqa: E402
    build_caption, _is_sensitive, load_used_captions, save_used_captions, detect_intent_fixed,
)

WEB3_CSV = ROOT / "accounts_web3_100.csv"
DEDUPE_WEB3 = ROOT / "state" / "seen_web3.json"
DEDUPE_CAP = ROOT / "state" / "seen_web3_stablecoin_captions.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# (query, hl, gl, ceid) — 稳定币资讯按地区定向
ZH_QUERIES = [
    ("穩定幣", "zh-TW", "TW", "TW:zh-Hant"),
    ("港元穩定幣", "zh-TW", "HK", "HK:zh-Hant"),
]
EN_QUERIES = [
    ("stablecoin OR USDC OR Tether", "en-US", "US", "US:en"),
    ("USDC", "en-US", "US", "US:en"),
]

NOISE = ["广告", "廣告", "促销", "秒杀", "优惠", "sponsored", "advertisement"]

_STABLECOIN_LATIN = re.compile(
    r"\b(usdt|usdc|usds|usde|dai|tether|stablecoin|stables|gusd|pyusd|fdusd|usdp)\b"
)
_STABLECOIN_ZH = ["穩定幣", "稳定币", "泰达", "泰達", "港元穩定幣", "港元稳定币"]


def _is_stablecoin_title(t: str) -> bool:
    """标题需明确命中稳定币词，剔除 `Circle`/`港元` 等泛词带来的误报（如 Full Circle Lithium、銀行定存）。"""
    x = (t or "").lower()
    if _STABLECOIN_LATIN.search(x):
        return True
    if "circle internet" in x:
        return True
    return any(k in x for k in _STABLECOIN_ZH)


def _run(cmd: list) -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def nick_lang(nick: str) -> str:
    s = nick or ""
    if re.search(r"[\u3040-\u30ff]", s):
        return "ja"
    if re.search(r"[\u4e00-\u9fff]", s):
        return "zh_hant"
    return "en"


def load_web3() -> list[dict]:
    with WEB3_CSV.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _norm(t: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[^\w\u4e00-\u9fff]", "", (t or "").lower()))


def _toks(t):
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2}", (t or "").lower()))


def clean_gn_title(raw: str) -> str:
    t = html.unescape(raw or "")
    t = re.sub(r"<[^>]+>", "", t)
    for _ in range(2):
        prev = t
        t = re.sub(r"\s+-\s+[^-]+$", "", t).strip()
        if t == prev:
            break
    return re.sub(r"\s+", " ", t).strip()


def _load_dedupe(path: Path) -> tuple[set, list]:
    used_norm, used_tok = set(), []
    if path.exists():
        try:
            for t in json.loads(path.read_text(encoding="utf-8")):
                used_norm.add(t)
                used_tok.append(_toks(t))
        except Exception:
            pass
    return used_norm, used_tok


def _save_dedupe(path: Path, norms: set) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(norms), ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_gn(query: str, hl: str, gl: str, ceid: str, want: int,
             used_norm: set, used_tok: list) -> list[dict]:
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query) +
           f"&hl={hl}&gl={gl}&ceid={ceid}")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    txt = r.content.decode("utf-8", errors="ignore")
    items = re.findall(r"<item>(.*?)</item>", txt, re.S)
    picked, picked_norm, picked_tok = [], set(), []
    for it in items:
        if len(picked) >= want:
            break
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        title = clean_gn_title(tm.group(1) if tm else "")
        if len(title) < 8 or len(title) > 90:
            continue
        if any(k in title.lower() for k in NOISE):
            continue
        n = _norm(title)
        if n in used_norm or n in picked_norm:
            continue
        tt = _toks(title)
        if any(tt and len(tt & ot) / len(tt) >= 0.7 for ot in used_tok + picked_tok):
            continue
        picked_norm.add(n)
        picked_tok.append(tt)
        picked.append({"title": title, "brief": "", "site": "google_news"})
    return picked


def main() -> int:
    ap = argparse.ArgumentParser(description="web3 用户池发布稳定币资讯（英文昵称英文/中文昵称繁体）")
    ap.add_argument("--num-en", type=int, default=6, help="英文昵称用户数")
    ap.add_argument("--num-zh", type=int, default=6, help="中文昵称用户数")
    ap.add_argument("--per-query", type=int, default=4)
    ap.add_argument("--min-len", type=int, default=200)
    ap.add_argument("--max-len", type=int, default=500)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--login-spacing", type=float, default=3.0)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="web3_stablecoin_run")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    # 1) 选用户
    users = load_web3()
    en = [u for u in users if nick_lang(u.get("昵称")) == "en"]
    zh = [u for u in users if nick_lang(u.get("昵称")) == "zh_hant"]
    print(f"[web3_stablecoin] web3 池 {len(users)} 人：英文 {len(en)}、中文 {len(zh)}、日文 {len(users)-len(en)-len(zh)}")
    sel_en = en[: args.num_en]
    sel_zh = zh[: args.num_zh]
    for u in sel_en + sel_zh:
        print(f"    - {u.get('昵称')}  [{nick_lang(u.get('昵称'))}]")

    # 2) 采集稳定币资讯（Google News 各地区定向）
    zh_rows: list[dict] = []
    en_rows: list[dict] = []
    if not args.skip_fetch:
        used_norm, used_tok = _load_dedupe(DEDUPE_WEB3)
        print("\n=== 采集中文稳定币资讯（台湾/香港）===")
        for q, hl, gl, ceid in ZH_QUERIES:
            got = fetch_gn(q, hl, gl, ceid, args.per_query * 2, used_norm, used_tok)
            for g in got:
                used_norm.add(_norm(g["title"]))
                used_tok.append(_toks(g["title"]))
            zh_rows.extend(got)
            print(f"  [{gl}] {q} -> {len(got)} 条")
        print("=== 采集英文稳定币资讯（美国）===")
        for q, hl, gl, ceid in EN_QUERIES:
            got = fetch_gn(q, hl, gl, ceid, args.per_query * 2, used_norm, used_tok)
            for g in got:
                used_norm.add(_norm(g["title"]))
                used_tok.append(_toks(g["title"]))
            en_rows.extend(got)
            print(f"  [{gl}] {q} -> {len(got)} 条")
        _save_dedupe(DEDUPE_WEB3, used_norm)
    else:
        zh_raw = sorted(wd.glob("stcoin_zh_*.csv"))[-1]
        en_raw = sorted(wd.glob("stcoin_en_*.csv"))[-1]
        zh_rows = [{"title": r["content"], "brief": r.get("_brief", ""), "site": r.get("_site", "")}
                   for r in csv.DictReader(zh_raw.open(encoding="utf-8-sig"))]
        en_rows = [{"title": r["content"], "brief": r.get("_brief", ""), "site": r.get("_site", "")}
                   for r in csv.DictReader(en_raw.open(encoding="utf-8-sig"))]

    # 稳定币相关度过滤（标题必须命中稳定币词）+ 敏感词过滤
    zh_rows = [r for r in zh_rows if _is_stablecoin_title(r["title"]) and not _is_sensitive(r["title"])]
    en_rows = [r for r in en_rows if _is_stablecoin_title(r["title"]) and not _is_sensitive(r["title"])]
    print(f"[web3_stablecoin] 过滤后：zh={len(zh_rows)}, en={len(en_rows)}")

    if len(zh_rows) < args.num_zh or len(en_rows) < args.num_en:
        print(f"[web3_stablecoin] 稳定币资讯不足：zh={len(zh_rows)}/{args.num_zh}, en={len(en_rows)}/{args.num_en}",
              file=sys.stderr)
        return 1

    # 存原始素材（供复用）
    def _save_raw(rows, sid, lang):
        p = wd / f"stcoin_{sid}_{ts}.csv"
        with p.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["content", "_brief", "_site", "_lang"])
            w.writeheader()
            for r in rows:
                w.writerow({"content": r["title"], "_brief": r.get("brief", ""),
                            "_site": r.get("site", ""), "_lang": lang})
        return p
    zh_raw_csv = _save_raw(zh_rows, "zh", "zh_hant")
    en_raw_csv = _save_raw(en_rows, "en", "en")

    # 3) 生成文案
    used_cap = load_used_captions(DEDUPE_CAP)
    rng = random.Random(int(ts.replace("_", "")))
    TONES = ["neutral", "positive", "trader"]

    def pick_diverse(rows, n, rng):
        groups = defaultdict(list)
        for r in rows:
            groups[detect_intent_fixed(r["title"]) or "market"].append(r)
        keys = list(groups.keys())
        rng.shuffle(keys)
        out, ptr = [], {k: 0 for k in keys}
        while len(out) < n and any(ptr[k] < len(groups[k]) for k in keys):
            for k in keys:
                if len(out) >= n:
                    break
                if ptr[k] < len(groups[k]):
                    out.append(groups[k][ptr[k]])
                    ptr[k] += 1
        return out

    zh_picked = pick_diverse(zh_rows, args.num_zh, rng)
    en_picked = pick_diverse(en_rows, args.num_en, rng)

    rows_out, meta = [], []
    n = min(len(zh_picked), len(en_picked))
    for i in range(max(len(zh_picked), len(en_picked))):
        for lang, picked in (("zh_hant", zh_picked), ("en", en_picked)):
            if i >= len(picked):
                continue
            r = picked[i]
            tone = TONES[i % len(TONES)]
            cap, intent = build_caption(
                r["title"], r.get("brief", ""), r.get("site", ""),
                lang, tone, i, rng, used_cap,
                min_len=args.min_len, max_len=args.max_len,
            )
            rows_out.append({
                "content": cap, "visibility": "0", "room_id": "", "image_urls": "",
                "location_name": "", "location_address": "", "location_lat": "", "location_lon": "",
                "_source": "web3_stablecoin", "_site": r.get("site", ""),
                "_lang": lang, "_tone": tone, "_intent": intent,
            })
            meta.append((lang, tone, intent, len(cap)))

    # 账号 CSV（顺序与 rows_out 一致：zh/en 交错）
    acc_out = wd / f"accounts_web3_stablecoin_{ts}.csv"
    ordered = []
    for k in range(n):
        ordered.append(sel_zh[k]); ordered.append(sel_en[k])
    with acc_out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["昵称", "邮箱", "密码"])
        w.writeheader()
        for u in ordered:
            w.writerow({"昵称": u.get("昵称", ""), "邮箱": u.get("邮箱", ""), "密码": u.get("密码", "")})

    mom_csv = wd / f"moments_web3_stablecoin_{ts}.csv"
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_site", "_lang", "_tone", "_intent"]
    with mom_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows_out:
            w.writerow({k: r.get(k, "") for k in fields})

    uniq = len(set(r["content"] for r in rows_out))
    print(f"\n[OK] {len(rows_out)} 帖 → {mom_csv.name}（文案唯一 {uniq}/{len(rows_out)}）")
    if meta:
        print(f"[OK] 长度：min={min(m[3] for m in meta)} max={max(m[3] for m in meta)}")
        for lang, tone, intent, l in meta:
            print(f"    [{lang}/{tone}/{intent}] {l} 字")

    save_used_captions(used_cap, DEDUPE_CAP)

    if args.skip_publish:
        print("\n--skip-publish，仅产出素材。")
        return 0

    if not args.yes:
        if input(f"  确认发布 {len(rows_out)} 帖？（y/n）：").strip().lower() not in ("y", "yes"):
            print("已取消。"); return 0

    print("\n=== 发布（纯文本）===")
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_out),
                "--csv", str(mom_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", str(args.login_spacing),
                "--tokens-out", str(ROOT / args.tokens)]
    if (ROOT / args.tokens).exists():
        cmd += ["--tokens-in", str(ROOT / args.tokens)]
    e = os.environ.copy()
    e.setdefault("PYTHONIOENCODING", "utf-8")
    e["POST_CROP_BOTTOM_HOSTS"] = ""
    rc = subprocess.call(cmd, cwd=str(ROOT), env=e)
    if rc != 0:
        print("[web3_stablecoin] 发布返回非零。", file=sys.stderr); return rc
    print("\n[web3_stablecoin] 完成。报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())