#!/usr/bin/env python3
"""
run_opennana_8_eng.py — 8指定OpenNana画廊，互动用户池账号发布（英文/日文文案）
使用有 token 的账号（含历史已登录），均匀分布避免 429。
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
import openpyxl

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

OPENNANA_API_BASE = "https://api.opennana.com"
OPENNANA_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://opennana.com/",
    "Accept": "application/json",
}

ACCOUNT_POOL_XLSX = ROOT / "互动用户池_220账号_完整信息.xlsx"
STATE_DIR = ROOT / "state"
DEDUPE_SLUG = STATE_DIR / "seen_opennana_8_eng.json"

GALLERIES = [
    {
        "slug": "blue-bikini-jet-ski-girl",
        "lang": "en",
        "caption": "Jet ski season is officially here 🏄‍♀️ Nothing beats the rush of cutting through the water with the wind in your hair. Blue bikini, sunny skies, pure adrenaline.",
    },
    {
        "slug": "soft-light-braided-pink-girl",
        "lang": "en",
        "caption": "Soft lighting and braided hair, the kind of shot that feels like a warm embrace ✨ There is something so gentle about this moment -- almost dreamy in the best way.",
    },
    {
        "slug": "east-asian-woman-black-dress-fur-shawl-portrait",
        "lang": "en",
        "caption": "Black dress, fur shawl, and that effortless elegance 💫 This look screams sophistication without trying too hard. The textures alone make this photo.",
    },
    {
        "slug": "stylish-couple-watercolor-campus",
        "lang": "en",
        "caption": "Campus life with a watercolor twist 🎨 Two people who get each other, walking through those golden afternoon rays. Simple, romantic, perfect.",
    },
    {
        "slug": "extreme-hourglass-selfie-in-vintage-boudoir",
        "lang": "en",
        "caption": "Vintage boudoir energy with curves on full display 🔥 The lighting, the pose, the confidence -- this is what self-love looks like in its finest form.",
    },
    {
        "slug": "y2k-office-core-fashion-portrait",
        "lang": "en",
        "caption": "Y2K office core hitting different this season 💼✨ Blazer with attitude, heels that mean business, and a desk full of dreams. Corporate but make it fashion.",
    },
    {
        "slug": "east-asian-woman-maroon-turtleneck-selfie-9-16",
        "lang": "en",
        "caption": "Maroon turtleneck era 🍷 There is something so cozy yet chic about this shade. The 9:16 ratio makes it feel like a story waiting to be continued.",
    },
    {
        "slug": "japanese-woman-bedroom-morning-selfie-lifestyle",
        "lang": "ja",
        "caption": "朝のベッドルームでのselfie、起きたてのくつろぎ vibes ☀️ 枕もとからの光が柔らかくて、今日のスタートにぴったりな一枚。",
    },
]


def _fetch_detail(slug: str) -> dict:
    for attempt in range(4):
        try:
            r = requests.get(f"{OPENNANA_API_BASE}/api/prompts/{slug}",
                             headers=OPENNANA_HEADERS, timeout=30, verify=False)
            r.raise_for_status()
            return r.json().get("data") or r.json()
        except Exception as e:
            if attempt < 3:
                time.sleep(2 * (attempt + 1))
            else:
                raise


def _load_all_token_emails() -> set:
    """Load ALL emails that have tokens (not excluding recent runs)."""
    try:
        tokens = json.loads((ROOT / "result" / "tokens.json").read_text(encoding="utf-8"))
        return set(tokens.keys())
    except Exception:
        return set()


def _is_english_nick(nick: str) -> bool:
    s = nick or ""
    if not s:
        return False
    return all(ord(c) <= 127 for c in s) and len(s) <= 20 and not re.search(r"[\u4e00-\u9fff]", s)


def _is_japanese_nick(nick: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff]", nick or ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="发布8个指定OpenNana画廊（7英文+1日文）")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--login-spacing", type=float, default=3.0)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="opennana_8_eng_run")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    # Load account pool
    wb = openpyxl.load_workbook(str(ACCOUNT_POOL_XLSX))
    ws = wb.active
    all_rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        all_rows.append({
            "序号": row[0],
            "昵称": str(row[3] or ""),
            "邮箱": row[1],
            "密码": row[4],
        })

    token_emails = _load_all_token_emails()
    avail_en = [r for r in all_rows
                if _is_english_nick(r["昵称"]) and (r["邮箱"] or "").strip().lower() in token_emails]
    avail_ja = [r for r in all_rows
                if _is_japanese_nick(r["昵称"]) and (r["邮箱"] or "").strip().lower() in token_emails]
    print(f"[opennana_8_eng] 可用账号(token): 英文 {len(avail_en)}, 日文 {len(avail_ja)}")

    # Fetch images and build moments
    moments = []
    account_pools = []  # list of pools, one per moment
    if not args.skip_fetch:
        print("\n=== 取 OpenNana 图片 ===")
        for g in GALLERIES:
            try:
                detail = _fetch_detail(g["slug"])
            except Exception as e:
                print(f"[opennana_8_eng] {g['slug'][:40]} 取图失败: {e}", file=sys.stderr)
                continue
            images = [u for u in (detail.get("images") or []) if str(u).startswith("http")]
            if not images:
                print(f"[opennana_8_eng] {g['slug'][:40]} 无图片，跳过", file=sys.stderr)
                continue
            lang = g["lang"]
            if lang == "ja":
                pool = avail_ja
            else:
                pool = avail_en
            if not pool:
                print(f"[opennana_8_eng] {g['slug'][:40]} 无可用{lang}账号，跳过", file=sys.stderr)
                continue
            account_pools.append(pool)
            moments.append({
                "content": g["caption"],
                "image_urls": ",".join(images[:9]),
                "_slug": g["slug"],
                "_lang": lang,
            })
            print(f"    [{lang}] {g['slug'][:40]} -> {len(images)} 图")

        acc_out = wd / f"accounts_opennana_8_eng_{ts}.csv"
        with acc_out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
            w.writeheader()
            for i, pool in enumerate(account_pools):
                # Round-robin across pool to distribute load
                a = pool[i % len(pool)]
                w.writerow({"序号": a["序号"], "昵称": a["昵称"],
                            "邮箱": a["邮箱"], "密码": a["密码"]})
                print(f"    账号[{i+1}]: {a['昵称']} ({a['邮箱']})")

        mom_csv = wd / f"moments_opennana_8_eng_{ts}.csv"
        fields = ["content", "visibility", "room_id", "image_urls",
                  "location_name", "location_address", "location_lat", "location_lon",
                  "_source", "_slug", "_lang"]
        with mom_csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for m in moments:
                w.writerow({k: m.get(k, "") for k in fields})
        print(f"\n[opennana_8_eng] 素材已保存: {mom_csv.name}")
    else:
        for f_ in sorted(wd.glob("moments_opennana_8_eng_*.csv"))[-1:]:
            for r in csv.DictReader(open(f_, encoding="utf-8-sig")):
                moments.append({"content": r["content"], "image_urls": r["image_urls"],
                                "_slug": r["_slug"], "_lang": r["_lang"]})
        for f_ in sorted(wd.glob("accounts_opennana_8_eng_*.csv"))[-1:]:
            rows = list(csv.DictReader(open(f_, encoding="utf-8-sig")))
            account_pools = [[r] for r in rows]

    if not moments:
        print("[opennana_8_eng] 未取到任何图片", file=sys.stderr)
        return 1

    print(f"\n[opennana_8_eng] 共 {len(moments)} 帖")
    for i, m in enumerate(moments):
        print(f"    [{i+1}] [{m['_lang']}] {m['_slug'][:35]}")

    # Dedupe
    seen_slugs = set()
    if DEDUPE_SLUG.exists():
        try:
            seen_slugs = set(json.loads(DEDUPE_SLUG.read_text(encoding="utf-8")))
        except Exception:
            pass
    seen_slugs |= {m["_slug"] for m in moments}
    DEDUPE_SLUG.write_text(json.dumps(sorted(seen_slugs), ensure_ascii=False, indent=2),
                           encoding="utf-8")

    if args.skip_publish:
        print("[opennana_8_eng] --skip-publish，仅产出素材。")
        return 0

    if not args.yes:
        if input(f"  确认发布 {len(moments)} 帖？（y/n）：").strip().lower() not in ("y", "yes"):
            print("已取消。")
            return 0

    # Publish
    print("\n=== 发布 ===")
    mom_csv = wd / f"moments_opennana_8_eng_{ts}.csv"
    acc_csv = wd / f"accounts_opennana_8_eng_{ts}.csv"
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_csv),
                "--csv", str(mom_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", str(args.login_spacing),
                "--tokens-out", str(ROOT / args.tokens)]
    if (ROOT / args.tokens).exists():
        cmd += ["--tokens-in", str(ROOT / args.tokens)]
    e = os.environ.copy()
    e.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(ROOT), env=e)
    if rc != 0:
        print("[opennana_8_eng] 发布返回非零。", file=sys.stderr)
        return rc
    print("\n[opennana_8_eng] 完成。报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
