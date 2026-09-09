#!/usr/bin/env python3
"""
run_pexels_autumn_photographer_9.py — 9个摄影师用户发布 Pexels 秋季美学图片。
使用英文口吻，每个账号一张图，避免重复。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY",
                           "qPYcteScsZbLDvxBcXSX1inBxLWdklBUBirESLX9d8Mosmf4vh3DzfnF")
PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"
TOKENS_FILE = ROOT / "result" / "tokens.json"
STATE_DIR = ROOT / "state"
SEEN_PHOTOS = STATE_DIR / "seen_pexels_autumn_photographer_9.json"

CAPTIONS = [
    "There's something about autumn light that makes everything look like it was painted just for you. Golden hour on a crisp October morning — that's the kind of moment photographers live for.",
    "Fall colors don't ask for permission. They just arrive, unexpected and overwhelming, turning ordinary streets into something worth stopping for. This is why I keep coming back to autumn photography.",
    "The best shots happen when you least expect them. One moment the trees are green, the next they're on fire with color. Autumn teaches you to pay attention.",
    "I've shot hundreds of autumns, and yet every year still catches me off guard. The way light filters through falling leaves, the texture of frost on old brick — there's always something new to discover.",
    "People rush through autumn like it's an inconvenience. But slow down for five minutes and the whole world turns gold. That's the photographer's secret — knowing when to stop and look.",
    "Golden leaves, deep shadows, and that particular blue hour that only exists in November. Autumn photography isn't about chasing the perfect shot — it's about being present for the ones that find you.",
    "There's a quiet beauty to autumn that summer never had. Summer shouts; autumn whispers. The best images come from listening.",
    "Walking through a park covered in fallen leaves, camera in hand, feeling the crisp air — this is what autumn photography means to me. No fancy gear, just patience and a willingness to be outside.",
    "Every autumn tells a different story. Last year it was crimson and bold; this year it's soft amber and gold. The season never repeats itself, and neither does the light.",
]


def _fetch_photos(query: str, count: int, skip_ids: set) -> list[dict]:
    all_photos = []
    page = 1
    while len(all_photos) < count and page <= 10:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            params={"query": query, "per_page": 20, "page": page, "locale": "en-US"},
            headers={"Authorization": PEXELS_API_KEY},
            timeout=30,
        )
        batch = r.json().get("photos", [])
        if not batch:
            break
        for p in batch:
            pid = p.get("id")
            if pid in skip_ids:
                continue
            w, h = p.get("width", 0), p.get("height", 0)
            if max(w, h) >= 3000:
                all_photos.append(p)
                if len(all_photos) >= count:
                    break
        page += 1
    return all_photos[:count]


def _load_seen() -> set:
    if SEEN_PHOTOS.exists():
        try:
            return set(json.loads(SEEN_PHOTOS.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def _save_seen(ids: set) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_PHOTOS.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2),
                           encoding="utf-8")


def _load_accounts() -> list[dict]:
    with open(PHOTOGRAPHER_CSV, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    tokens = {}
    if TOKENS_FILE.exists():
        try:
            tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return [{"序号": r["序号"], "邮箱": r["邮箱"], "昵称": r["昵称"], "密码": r["密码"]}
            for r in rows if r["邮箱"] in tokens]


def main() -> int:
    ap = argparse.ArgumentParser(description="Pexels秋季美学 - 9摄影师用户发帖")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--login-spacing", type=float, default=2.5)
    ap.add_argument("--tokens-out", default="result/tokens.json")
    ap.add_argument("--workdir", default="pexels_autumn_photographer_9_run")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    account_pool = _load_accounts()
    print(f"[pexels_autumn_photo9] 有token摄影师账号: {len(account_pool)}")

    seen_ids = _load_seen()
    print(f"[pexels_autumn_photo9] 已用图片数: {len(seen_ids)}")

    moments = []
    if not args.skip_fetch:
        print("\n=== 取 Pexels 秋季美学图片 ===")
        photos = _fetch_photos("autumn aesthetic", count=9, skip_ids=seen_ids)
        if not photos:
            print("[pexels_autumn_photo9] 未取到可用图片", file=sys.stderr)
            return 1
        for i, p in enumerate(photos):
            pid = p.get("id")
            w, h = p.get("width"), p.get("height")
            url = p.get("src", {}).get("large", "")
            moments.append({
                "content": CAPTIONS[i],
                "image_urls": url,
                "_lang": "en",
                "_photo_id": pid,
            })
            print(f"    [{i+1}] photo={pid} {w}x{h}")
        _save_seen(seen_ids | {p.get("id") for p in photos})

        if len(account_pool) < 9:
            print(f"[pexels_autumn_photo9] 账号不足9个（{len(account_pool)}）", file=sys.stderr)
            return 1

        acc_out = wd / f"accounts_pexels_autumn_photo9_{ts}.csv"
        with acc_out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
            w.writeheader()
            for i in range(9):
                a = account_pool[i]
                w.writerow({"序号": a["序号"], "昵称": a["昵称"],
                            "邮箱": a["邮箱"], "密码": a["密码"]})
                print(f"    账号[{i+1}]: {a['昵称']} ({a['邮箱']})")

        mom_csv = wd / f"moments_pexels_autumn_photo9_{ts}.csv"
        fields = ["content", "visibility", "room_id", "image_urls",
                  "location_name", "location_address", "location_lat", "location_lon",
                  "_source", "_lang", "_photo_id"]
        with mom_csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for m in moments:
                w.writerow({k: m.get(k, "") for k in fields})
        print(f"\n[pexels_autumn_photo9] 素材已保存: {mom_csv.name}")
    else:
        for f_ in sorted(wd.glob("moments_pexels_autumn_photo9_*.csv"))[-1:]:
            for r in csv.DictReader(open(f_, encoding="utf-8-sig")):
                moments.append({"content": r["content"], "image_urls": r["image_urls"],
                                "_lang": r["_lang"], "_photo_id": r.get("_photo_id", "")})
        for f_ in sorted(wd.glob("accounts_pexels_autumn_photo9_*.csv"))[-1:]:
            account_pool = list(csv.DictReader(open(f_, encoding="utf-8-sig")))

    if not moments:
        print("[pexels_autumn_photo9] 未取到任何图片", file=sys.stderr)
        return 1

    print(f"\n[pexels_autumn_photo9] 共 {len(moments)} 帖")
    for i, m in enumerate(moments):
        print(f"    [{i+1}] photo={m['_photo_id']} lang={m['_lang']}")

    if args.skip_publish:
        print("[pexels_autumn_photo9] --skip-publish，仅产出素材。")
        return 0

    if not args.yes:
        if input(f"  确认发布 {len(moments)} 帖？（y/n）：").strip().lower() not in ("y", "yes"):
            print("已取消。")
            return 0

    print("\n=== 发布 ===")
    mom_csv = wd / f"moments_pexels_autumn_photo9_{ts}.csv"
    acc_csv = wd / f"accounts_pexels_autumn_photo9_{ts}.csv"
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_csv),
                "--csv", str(mom_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", str(args.login_spacing),
                "--tokens-out", str(ROOT / args.tokens_out)]
    if TOKENS_FILE.exists():
        cmd += ["--tokens-in", str(TOKENS_FILE)]
    e = os.environ.copy()
    e.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    rc = subprocess.call(cmd, cwd=str(ROOT), env=e)
    if rc != 0:
        print("[pexels_autumn_photo9] 发布返回非零。", file=sys.stderr)
        return rc
    print("\n[pexels_autumn_photo9] 完成。报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
