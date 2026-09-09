#!/usr/bin/env python3
"""
run_pexels_interact_7.py — 从 Pexels 获取大学校园图片，7个互动用户各发1帖。
使用已有 token 的账号（不重复上次已发布的7个账号），避免重复图片。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
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

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "qPYcteScsZbLDvxBcXSX1inBxLWdklBUBirESLX9d8Mosmf4vh3DzfnF")
ACCOUNTS_CSV = ROOT / "accounts_interact_200_20260827.csv"
TOKENS_FILE = ROOT / "result" / "tokens.json"
STATE_DIR = ROOT / "state"
SEEN_PEXELS = STATE_DIR / "seen_pexels_interact_7.json"

CAPTIONS = [
    (
        "Walking across campus in autumn, the golden light filtering through the trees makes everything feel like a movie scene. "
        "There's something about university paths lined with falling leaves that always makes you slow down and appreciate the moment.",
        "en",
    ),
    (
        "The old library stands at the heart of campus, its stone walls holding decades of quiet study and endless possibilities. "
        "Every corner tells a story of students who came here chasing dreams — and some who found them.",
        "en",
    ),
    (
        "Morning classes hit different when the campus is bathed in soft sunlight and the air smells like fresh rain. "
        "These quiet moments between semesters are what you carry with you long after graduation.",
        "en",
    ),
    (
        "The quad at golden hour is pure magic — students sprawled on grass, books open but forgotten, just existing in the warmth. "
        "This is the America we see in movies, and somehow it's even better in person.",
        "en",
    ),
    (
        "Campus architecture has a way of making you feel small in the best way. Gothic arches, towering libraries, "
        "and pathways that seem to go on forever. Every university has its own soul, and this one feels timeless.",
        "en",
    ),
    (
        "There's a particular kind of peace that comes with walking through an empty campus at dusk. "
        "The buildings cast long shadows, the lawns glow amber, and for a few quiet minutes everything feels possible.",
        "en",
    ),
    (
        "Fall on campus is its own season — not quite summer, not quite winter, just perfect. "
        "Crunching leaves underfoot, hot coffee in hand, and that feeling that whatever comes next, you're ready for it.",
        "en",
    ),
]


def _fetch_pexels_photos(query: str, per_page: int = 20, page: int = 1) -> list[dict]:
    r = requests.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "per_page": per_page, "page": page, "locale": "en-US"},
        headers={"Authorization": PEXELS_API_KEY},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("photos", [])


def _load_seen_pexels() -> set:
    if SEEN_PEXELS.exists():
        try:
            return set(json.loads(SEEN_PEXELS.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def _save_seen_pexels(ids: set) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_PEXELS.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def _get_fresh_photos(seen: set, count: int = 7) -> list[dict]:
    photos = []
    page = 1
    while len(photos) < count and page <= 5:
        batch = _fetch_pexels_photos("university campus landscape", per_page=20, page=page)
        for p in batch:
            pid = p.get("id")
            if pid in seen:
                continue
            w, h = p.get("width", 0), p.get("height", 0)
            if w > h and w >= 2500:
                photos.append(p)
                if len(photos) >= count:
                    break
        page += 1
    return photos


def _load_accounts_with_tokens() -> list[dict]:
    with open(ACCOUNTS_CSV, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    tokens = {}
    if TOKENS_FILE.exists():
        try:
            tokens = json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    result = []
    for r in rows:
        email = r.get("邮箱", "")
        if email in tokens:
            result.append({
                "序号": r.get("序号", ""),
                "邮箱": email,
                "昵称": r.get("昵称", ""),
                "密码": r.get("密码", ""),
            })
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Pexels大学校园图片 - 7互动用户发帖")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--login-spacing", type=float, default=2.5)
    ap.add_argument("--tokens-out", default="result/tokens.json")
    ap.add_argument("--workdir", default="pexels_interact_7_run")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    # Load accounts that already have tokens
    account_pool = _load_accounts_with_tokens()
    print(f"[pexels_interact_7] 有token账号池: {len(account_pool)}")

    # Load previously seen photo IDs to avoid duplicates
    seen = _load_seen_pexels()
    print(f"[pexels_interact_7] 已用图片ID数: {len(seen)}")

    # Fetch fresh photos
    moments = []
    if not args.skip_fetch:
        print("\n=== 取 Pexels 大学校园图片 ===")
        photos = _get_fresh_photos(seen, count=7)
        if not photos:
            print("[pexels_interact_7] 未取到可用图片", file=sys.stderr)
            return 1
        for i, p in enumerate(photos[:7]):
            pid = p.get("id")
            w, h = p.get("width"), p.get("height")
            url = p.get("src", {}).get("large", "")
            caption, lang = CAPTIONS[i]
            moments.append({
                "content": caption,
                "image_urls": url,
                "_lang": lang,
                "_photo_id": pid,
            })
            print(f"    [{i+1}] photo={pid} {w}x{h} lang={lang}")
        _save_seen_pexels(seen | {p.get("id") for p in photos[:7]})

        # Write accounts CSV (7 accounts, round-robin from pool)
        if len(account_pool) < 7:
            print(f"[pexels_interact_7] 有token账号不足7个（{len(account_pool)}），需补充登录", file=sys.stderr)
            return 1
        acc_out = wd / f"accounts_pexels_interact_7_{ts}.csv"
        with acc_out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
            w.writeheader()
            for i in range(7):
                a = account_pool[i]
                w.writerow({"序号": a["序号"], "昵称": a["昵称"],
                            "邮箱": a["邮箱"], "密码": a["密码"]})
                print(f"    账号[{i+1}]: {a['昵称']} ({a['邮箱']})")

        mom_csv = wd / f"moments_pexels_interact_7_{ts}.csv"
        fields = ["content", "visibility", "room_id", "image_urls",
                  "location_name", "location_address", "location_lat", "location_lon",
                  "_source", "_lang", "_photo_id"]
        with mom_csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for m in moments:
                w.writerow({
                    "content": m["content"],
                    "visibility": 0,
                    "room_id": "",
                    "image_urls": m["image_urls"],
                    "location_name": "",
                    "location_address": "",
                    "location_lat": "",
                    "location_lon": "",
                    "_source": "pexels",
                    "_lang": m["_lang"],
                    "_photo_id": m["_photo_id"],
                })
        print(f"\n[pexels_interact_7] 素材已保存: {mom_csv.name}")
    else:
        for f_ in sorted(wd.glob("moments_pexels_interact_7_*.csv"))[-1:]:
            for r in csv.DictReader(open(f_, encoding="utf-8-sig")):
                moments.append({"content": r["content"], "image_urls": r["image_urls"],
                                "_lang": r["_lang"], "_photo_id": r.get("_photo_id", "")})
        for f_ in sorted(wd.glob("accounts_pexels_interact_7_*.csv"))[-1:]:
            rows = list(csv.DictReader(open(f_, encoding="utf-8-sig")))
            account_pool = rows

    if not moments:
        print("[pexels_interact_7] 未取到任何图片", file=sys.stderr)
        return 1

    print(f"\n[pexels_interact_7] 共 {len(moments)} 帖")
    for i, m in enumerate(moments):
        print(f"    [{i+1}] photo={m['_photo_id']} lang={m['_lang']}")

    if args.skip_publish:
        print("[pexels_interact_7] --skip-fetch only, no publish.")
        return 0

    if not args.yes:
        if input(f"  确认发布 {len(moments)} 帖？（y/n）：").strip().lower() not in ("y", "yes"):
            print("已取消。")
            return 0

    print("\n=== 发布 ===")
    mom_csv = wd / f"moments_pexels_interact_7_{ts}.csv"
    acc_csv = wd / f"accounts_pexels_interact_7_{ts}.csv"
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
        print("[pexels_interact_7] 发布返回非零。", file=sys.stderr)
        return rc
    print("\n[pexels_interact_7] 完成。报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    import subprocess
    sys.exit(main())
