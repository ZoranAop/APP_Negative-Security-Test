#!/usr/bin/env python3
"""
run_web3_wublock.py — web3 用户池发布 web3 资讯（含吴说深度分析，繁中/英文）。

1) 从 accounts_web3_100.csv 选用户（避开本次会话已用账号）：
       - 中文昵称 → 繁体中文（其中若干帖为「吴说」深度分析）
       - 英文昵称 → 英文
2) 采集：
       - 吴说深度源：fetch_web3.wublock_deep（抓吴说正文 AI 解读 + 要点，独立去重账本）
       - 中文常规：Google News（加密货币/区块链/Web3，zh）
       - 英文：Google News（crypto/blockchain/web3，en）
3) 生成第一人称「感知陈述」口吻文案 200-500 字，话题 + 口吻(点评/正向/收益)去同质
4) 纯文本发布
"""
from __future__ import annotations

import argparse
import csv
import glob
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
    build_caption, detect_intent_fixed, _is_sensitive, load_used_captions, save_used_captions,
)

WEB3_CSV = ROOT / "accounts_web3_100.csv"
DEDUPE_WUBLOCK = ROOT / "state" / "seen_wublock_depth.json"
DEDUPE_NEWS = ROOT / "state" / "seen_web3_wublock_news.json"
DEDUPE_CAP = ROOT / "state" / "seen_web3_wublock_captions.json"

ZH_QUERIES = [
    ("加密货币 OR 区块链 OR Web3", "zh-CN", "CN", "CN:zh-Hans"),
]
EN_QUERIES = [
    ("crypto OR blockchain OR web3", "en-US", "US", "US:en"),
    ("stablecoin OR DeFi OR Bitcoin", "en-US", "US", "US:en"),
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

NOISE = ["PA日报", "白线日报", "早报", "晚报", "今日要闻"]


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


def _session_used() -> set:
    used = set()
    for d in ("web3_stablecoin_run", "web3_taiwan_run"):
        for f in glob.glob(str(ROOT / d / "accounts_*.csv")):
            try:
                for r in csv.DictReader(open(f, encoding="utf-8-sig")):
                    for k in ("邮箱", "email", "Email"):
                        v = (r.get(k) or "").strip().lower()
                        if "@" in v:
                            used.add(v)
            except Exception:
                pass
    return used


def _load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _norm(t: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"[^\w\u4e00-\u9fff]", "", (t or "").lower()))


def _toks(t):
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2}", (t or "").lower()))


def _clean_gn(raw: str) -> str:
    t = html.unescape(raw or "")
    t = re.sub(r"<[^>]+>", "", t)
    for _ in range(2):
        prev = t
        t = re.sub(r"\s+-\s+[^-]+$", "", t).strip()
        if t == prev:
            break
    return re.sub(r"\s+", " ", t).strip()


def _load_json(path: Path) -> list:
    if not path.exists():
        return []
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(d, list):
            return [str(x) for x in d]
        if isinstance(d, dict):
            return [str(v) for v in d.values() if isinstance(v, str)]
    except Exception:
        pass
    return []


def _save_json(path: Path, items: set) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(items), ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_gn(query: str, hl: str, gl: str, ceid: str, want: int, used_norm: set, used_tok: list) -> list[dict]:
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query) +
           f"&hl={hl}&gl={gl}&ceid={ceid}")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
    r.raise_for_status()
    txt = r.content.decode("utf-8", errors="ignore")
    out = []
    for it in re.findall(r"<item>(.*?)</item>", txt, re.S):
        if len(out) >= want:
            break
        tm = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", it, re.S)
        title = _clean_gn(tm.group(1) if tm else "")
        if len(title) < 8 or len(title) > 110:
            continue
        if "..." in title:
            continue
        if any(k in title for k in NOISE):
            continue
        n = _norm(title)
        tt = _toks(title)
        if n in used_norm:
            continue
        if any(tt and len(tt & ot) / len(tt) >= 0.6 for ot in used_tok):
            continue
        used_norm.add(n)
        used_tok.append(tt)
        out.append({"title": title, "brief": "", "site": "google_news"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="web3 用户池发布 web3 资讯（含吴说深度分析）")
    ap.add_argument("--num-zh", type=int, default=6)
    ap.add_argument("--num-en", type=int, default=6)
    ap.add_argument("--num-deep", type=int, default=3, help="吴说深度分析帖数（占中文帖）")
    ap.add_argument("--min-len", type=int, default=200)
    ap.add_argument("--max-len", type=int, default=500)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--login-spacing", type=float, default=3.0)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="web3_wublock_run")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    # 1) 选用户
    users = list(csv.DictReader(WEB3_CSV.open(encoding="utf-8-sig")))
    used = _session_used()
    zh = [r for r in users if nick_lang(r.get("昵称")) == "zh_hant" and (r.get("邮箱") or "").strip().lower() not in used]
    en = [r for r in users if nick_lang(r.get("昵称")) == "en" and (r.get("邮箱") or "").strip().lower() not in used]
    print(f"[wublock] web3 池（排除本次会话已用）：中文 {len(zh)}、英文 {len(en)}；选中 中文 {args.num_zh}、英文 {args.num_en}")
    sel_zh = zh[: args.num_zh]
    sel_en = en[: args.num_en]
    for r in sel_zh:
        print(f"    [zh] {r.get('昵称')}")
    for r in sel_en:
        print(f"    [en] {r.get('昵称')}")

    # 2) 采集
    deep_csv = wd / f"web3_deep_{ts}.csv"
    if not args.skip_fetch:
        print("\n=== 采集吴说深度源（wublock_deep，独立去重）===")
        cmd = PY + [str(HERE / "fetch_web3.py"), "--sources", "wublock_deep", "--per-site", str(max(4, args.num_deep + 1)),
                    "--dedupe-file", str(DEDUPE_WUBLOCK), "--tag", "web3", "--output", str(deep_csv)]
        if _run(cmd) != 0 or not deep_csv.exists():
            print("[wublock] 吴说深度采集失败", file=sys.stderr); return 1

        print("=== 采集中文常规 + 英文（Google News）===")
        used_norm = set(_load_json(DEDUPE_NEWS))
        used_tok = [_toks(t) for t in used_norm]
        zh_rows, en_rows = [], []
        for q, hl, gl, ceid in ZH_QUERIES:
            zh_rows.extend(fetch_gn(q, hl, gl, ceid, args.num_zh + 6, used_norm, used_tok))
        for q, hl, gl, ceid in EN_QUERIES:
            en_rows.extend(fetch_gn(q, hl, gl, ceid, args.num_en + 6, used_norm, used_tok))
        _save_json(DEDUPE_NEWS, used_norm)
        # 存素材备查
        for sid, lang, rows in (("zh", "zh_hant", zh_rows), ("en", "en", en_rows)):
            p = wd / f"web3_{sid}_gn_{ts}.csv"
            with p.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=["content", "_brief", "_site"])
                w.writeheader()
                for r in rows:
                    w.writerow({"content": r["title"], "_brief": r["brief"], "_site": r["site"]})
    else:
        deep_csv = sorted(wd.glob("web3_deep_*.csv"))[-1]
        zh_gn = sorted(wd.glob("web3_zh_gn_*.csv"))[-1]
        en_gn = sorted(wd.glob("web3_en_gn_*.csv"))[-1]
        zh_rows = [{"title": r["content"], "brief": r.get("_brief", ""), "site": r.get("_site", "")} for r in _load(zh_gn)]
        en_rows = [{"title": r["content"], "brief": r.get("_brief", ""), "site": r.get("_site", "")} for r in _load(en_gn)]

    def _clean(rows):
        return [r for r in rows if (r.get("content") or "").strip()
                and not _is_sensitive(r.get("content", "")) and not _is_sensitive(r.get("_brief", ""))]

    # fetch 阶段已过滤敏感词；deep 源直接读
    deep_rows = _clean(_load(deep_csv))
    zh_rows = [r for r in zh_rows if not _is_sensitive(r["title"])]
    en_rows = [r for r in en_rows if not _is_sensitive(r["title"])]
    print(f"[wublock] 过滤后：吴说深度 {len(deep_rows)}、中文常规 {len(zh_rows)}、英文 {len(en_rows)}")

    n_deep = min(args.num_deep, len(deep_rows), args.num_zh)
    n_zh_reg = args.num_zh - n_deep
    if n_deep < args.num_deep or len(zh_rows) < n_zh_reg or len(en_rows) < args.num_en:
        print(f"[wublock] 资讯不足（deep={len(deep_rows)}/{args.num_deep}, zh={len(zh_rows)}/{n_zh_reg}, en={len(en_rows)}/{args.num_en}）",
              file=sys.stderr)
        return 1

    # 3) 生成文案
    used_cap = load_used_captions(DEDUPE_CAP)
    rng = random.Random(int(ts.replace("_", "")))
    TONES = ["neutral", "positive", "trader"]

    def pick_diverse(rows, n):
        groups = defaultdict(list)
        for r in rows:
            groups[detect_intent_fixed(r["content" if "content" in r else "title"]) or "market"].append(r)
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

    deep_picked = deep_rows[:n_deep]
    reg_picked = pick_diverse(zh_rows, n_zh_reg)
    en_picked = pick_diverse(en_rows, args.num_en)
    zh_picked = deep_picked + reg_picked
    rng.shuffle(zh_picked)

    def _fields(r):
        return r.get("content") or r.get("title", ""), r.get("_brief") or r.get("brief", ""), r.get("_site") or r.get("site", "")

    rows_out, meta = [], []
    for i, r in enumerate(zh_picked):
        tone = TONES[i % len(TONES)]
        title, brief, site = _fields(r)
        cap, intent = build_caption(title, brief, site, "zh_hant", tone, i, rng, used_cap,
                                    min_len=args.min_len, max_len=args.max_len)
        rows_out.append({"content": cap, "visibility": "0", "room_id": "", "image_urls": "",
                         "location_name": "", "location_address": "", "location_lat": "", "location_lon": "",
                         "_source": "web3_wublock", "_site": site, "_lang": "zh_hant", "_tone": tone, "_intent": intent})
        meta.append(("zh_hant", tone, intent, len(cap), "吴说深度" if "wublock" in site else site))
    for i, r in enumerate(en_picked):
        tone = TONES[i % len(TONES)]
        title, brief, site = _fields(r)
        cap, intent = build_caption(title, brief, site, "en", tone, i, rng, used_cap,
                                    min_len=args.min_len, max_len=args.max_len)
        rows_out.append({"content": cap, "visibility": "0", "room_id": "", "image_urls": "",
                         "location_name": "", "location_address": "", "location_lat": "", "location_lon": "",
                         "_source": "web3_wublock", "_site": site, "_lang": "en", "_tone": tone, "_intent": intent})
        meta.append(("en", tone, intent, len(cap), site))

    acc_out = wd / f"accounts_web3_wublock_{ts}.csv"
    with acc_out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["昵称", "邮箱", "密码"])
        w.writeheader()
        for u in sel_zh + sel_en:
            w.writerow({"昵称": u.get("昵称", ""), "邮箱": u.get("邮箱", ""), "密码": u.get("密码", "")})

    mom_csv = wd / f"moments_web3_wublock_{ts}.csv"
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
        for lang, tone, intent, l, src in meta:
            print(f"    [{lang}/{tone}/{intent}] {l} 字  <{src}>")

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
        print("[wublock] 发布返回非零。", file=sys.stderr); return rc
    print("\n[wublock] 完成。报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())