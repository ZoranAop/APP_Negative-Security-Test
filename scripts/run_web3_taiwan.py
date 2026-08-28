#!/usr/bin/env python3
"""
run_web3_taiwan.py — web3 用户池（中文昵称）发布台湾 web3/币/稳定币财经资讯（繁体中文）。

1) 从 accounts_web3_100.csv 选中文昵称用户（繁体中文文案）
2) 采集台湾相关图片（Pexels「台北101」，按图 URL 去重）
3) 采集台湾 web3/币/稳定币财经资讯（Google News，地区定向 gl=TW / zh-TW）
4) 生成第一人称「台北拍摄场景 + 台湾财经资讯点评」繁体中文文案
5) 图文发布（publish_from_tokens.py）

用法:
    py -3 scripts/run_web3_taiwan.py --num 4 --skip-publish
    py -3 scripts/run_web3_taiwan.py --num 4 --yes
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
from pathlib import Path

import requests

try:
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

WEB3_CSV = ROOT / "accounts_web3_100.csv"
DEDUPE_IMG = ROOT / "state" / "seen_tw_taipei101_photo.json"
DEDUPE_NEWS = ROOT / "state" / "seen_tw_web3_news.json"
DEDUPE_CAP = ROOT / "state" / "seen_tw_web3_captions.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

TW_NEWS = [
    ("台灣 穩定幣 OR 加密貨幣", "zh-TW", "TW", "TW:zh-Hant"),
    ("台灣 Web3 OR 區塊鏈 OR 虛擬資產", "zh-TW", "TW", "TW:zh-Hant"),
]

# 敏感词（内容审核 50009）
SENSITIVE = ["trump", "特朗普", "川普", "总统", "總統", "習近平", "习近平"]

BANK_ZH = {
    "photo": [
        "週末跑了趟台北，101 這個角度怎麼拍都好看。",
        "台北的天空配上 101，隨手一拍都是風景。",
        "趁天氣好到信義區走走，順手拍了幾張 101。",
        "站在 101 腳下仰望，這座城市的天際線特別有故事。",
    ],
    "lead": [
        "另外最近台灣的加密與金融圈有則消息值得留意——{title}。",
        "台灣在數位資產這塊的動向，這條值得追：{title}。",
        "關於台灣虛擬資產 / 穩定幣的進展——{title}。",
    ],
    "comment": [
        "從洗錢防制到穩定幣監管，台灣這一年動作不少。",
        "交易所、VASP 牌照、穩定幣，台灣的監管框架一步步成形。",
        "週邊市場都在加速，台灣這波也不能慢。",
        "法規越清晰，市場的能見度就越高。",
    ],
    "closer": [
        "天際線在變，監管也在變。",
        "繼續觀察台灣接下來的動作。",
        "台北很美，但市場的訊息更值得留意。",
    ],
    "tags": "#台灣 #Web3 #穩定幣",
}


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


def _is_sensitive(text: str) -> bool:
    return any(k in (text or "").lower() for k in SENSITIVE)


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
        if len(title) < 8 or len(title) > 100:
            continue
        if "..." in title:
            continue
        n = _norm(title)
        tt = _toks(title)
        if n in used_norm:
            continue
        if any(tt and len(tt & ot) / len(tt) >= 0.6 for ot in used_tok):
            continue
        if _is_sensitive(title):
            continue
        used_norm.add(n)
        used_tok.append(tt)
        out.append({"title": title, "site": "google_news"})
    return out


def make_caption(lang: str, title: str, idx: int, rng: random.Random, used: set) -> str:
    b = BANK_ZH
    for _ in range(40):
        photo = rng.choice(b["photo"])
        lead = rng.choice(b["lead"]).format(title=title)
        comment = rng.choice(b["comment"])
        closer = rng.choice(b["closer"])
        cap = f"{photo}\n\n{lead} {comment}\n\n{closer}\n{b['tags']}"
        if cap not in used:
            used.add(cap)
            return cap
    return cap


def _used_emails() -> set:
    # 只统计运行目录下的批次账号（排除根目录的账号池文件如 accounts_web3_100.csv）
    used = set()
    for f in glob.glob(str(ROOT / "*" / "accounts_*.csv")):
        try:
            for r in csv.DictReader(open(f, encoding="utf-8-sig")):
                for k in ("邮箱", "email", "Email"):
                    v = (r.get(k) or "").strip().lower()
                    if "@" in v:
                        used.add(v)
        except Exception:
            pass
    try:
        used |= set(l.strip().lower() for l in (ROOT / "state" / "used_emails.txt").read_text(encoding="utf-8").splitlines() if "@" in l.strip().lower())
    except Exception:
        pass
    return used


def main() -> int:
    ap = argparse.ArgumentParser(description="web3 用户池发布台湾 web3/稳定币财经资讯（繁体中文）")
    ap.add_argument("--num", type=int, default=4)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--login-spacing", type=float, default=3.0)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="web3_taiwan_run")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    # 1) 选用户（中文昵称）
    users = list(csv.DictReader(WEB3_CSV.open(encoding="utf-8-sig")))
    used_emails = _used_emails()
    zh = [r for r in users if nick_lang(r.get("昵称")) == "zh_hant" and (r.get("邮箱") or "").strip().lower() not in used_emails]
    sel = zh[: args.num]
    print(f"[tw] web3 池中文昵称 fresh：{len(zh)}；选中 {len(sel)}")
    for r in sel:
        print(f"    - {r.get('昵称')}")

    # 2) 采集台北101图片（Pexels）
    img_csv = wd / f"taipei101_img_{ts}.csv"
    if not args.skip_fetch:
        print("\n=== 采集台北101图片（Pexels）===")
        cmd = PY + [str(HERE / "fetch_stock_my.py"), "--sources", "pexels",
                    "--query", "台北101", "--per-source", str(args.num + 3),
                    "--locale", "zh-CN", "--dedupe-file", str(DEDUPE_IMG),
                    "--output", str(img_csv)]
        if _run(cmd) != 0 or not img_csv.exists():
            print("[tw] 图片采集失败", file=sys.stderr); return 1
    else:
        img_csv = sorted(wd.glob("taipei101_img_*.csv"))[-1]
    with img_csv.open(encoding="utf-8-sig") as f:
        imgs = list(csv.DictReader(f))
    print(f"[tw] 图片 {len(imgs)} 张")

    # 3) 采集台湾 web3/稳定币财经资讯（Google News）
    news: list[dict] = []
    if not args.skip_fetch:
        used_norm = set(_load_json(DEDUPE_NEWS))
        used_tok = [_toks(t) for t in used_norm]
        for q, hl, gl, ceid in TW_NEWS:
            news.extend(fetch_gn(q, hl, gl, ceid, args.num + 3, used_norm, used_tok))
        _save_json(DEDUPE_NEWS, used_norm)
    else:
        for f_ in sorted(wd.glob("taiwan_news_*.csv")):
            for r in csv.DictReader(open(f_, encoding="utf-8-sig")):
                news.append({"title": r["title"], "site": ""})
    print(f"[tw] 资讯 {len(news)} 条")

    if args.skip_fetch:
        pass
    else:
        p = wd / f"taiwan_news_{ts}.csv"
        with p.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["title", "site"])
            w.writeheader()
            for r in news:
                w.writerow({"title": r["title"], "site": r["site"]})

    if len(news) < args.num:
        print(f"[tw] 资讯不足：{len(news)}/{args.num}", file=sys.stderr)
        return 1

    # 4) 生成文案
    used_cap = set(_load_json(DEDUPE_CAP))
    rng = random.Random(int(ts.replace("_", "")))
    rows_out = []
    for i, u in enumerate(sel):
        img = imgs[i % len(imgs)]["image_urls"] if imgs else ""
        title = news[i % len(news)]["title"]
        cap = make_caption("zh_hant", title, i, rng, used_cap)
        rows_out.append({
            "content": cap, "visibility": "0", "room_id": "", "image_urls": img,
            "location_name": "台北", "location_address": "", "location_lat": "", "location_lon": "",
            "_source": "web3_taiwan", "_lang": "zh_hant",
        })
        print(f"  {u.get('昵称')} <- img {img.split('/photos/')[-1][:18] if img else 'NONE'} | news: {title[:36]}")

    acc_out = wd / f"accounts_web3_taiwan_{ts}.csv"
    with acc_out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["昵称", "邮箱", "密码"])
        w.writeheader()
        for u in sel:
            w.writerow({"昵称": u.get("昵称", ""), "邮箱": u.get("邮箱", ""), "密码": u.get("密码", "")})

    mom_csv = wd / f"moments_web3_taiwan_{ts}.csv"
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_lang"]
    with mom_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows_out:
            w.writerow({k: r.get(k, "") for k in fields})

    uniq = len(set(r["content"] for r in rows_out))
    uniq_img = len(set(r["image_urls"] for r in rows_out if r["image_urls"]))
    print(f"\n[OK] {len(rows_out)} 帖（文案唯一 {uniq}/{len(rows_out)}，图片唯一 {uniq_img}/{len(rows_out)}）")

    _save_json(DEDUPE_CAP, used_cap)

    if args.skip_publish:
        print("\n--skip-publish，仅产出素材。")
        return 0

    if not args.yes:
        if input(f"  确认发布 {len(rows_out)} 帖？（y/n）：").strip().lower() not in ("y", "yes"):
            print("已取消。"); return 0

    print("\n=== 发布（图文）===")
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
    rc = subprocess.call(cmd, cwd=str(ROOT), env=e)
    if rc != 0:
        print("[tw] 发布返回非零。", file=sys.stderr); return rc
    print("\n[tw] 完成。报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())