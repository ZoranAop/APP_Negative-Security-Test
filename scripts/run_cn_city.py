#!/usr/bin/env python3
"""
run_cn_city.py — 中国城市图文一键发布（长沙/深圳城市与夜景图 → 繁体中文怀旧文案 → 图文发布）

流程：
    1) 采集   fetch_stock_my.py（Pexels/Pixabay 搜「changsha/shenzhen city/night」）
    2) 去重   按图片 photoId 去重（种子来自历史 seen_cn_*.json，跨批次防重复）
    3) 文案   繁体中文、简洁怀旧口吻，附 #老照片 #那些往事
    4) 发布   publish_from_tokens.py（单图帖）

用法：
    py -3 scripts/run_cn_city.py --accounts-csv accounts_cn_city_3.csv --skip-publish
    py -3 scripts/run_cn_city.py --accounts-csv accounts_cn_city_3.csv --yes
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]
sys.path.insert(0, str(HERE))

from caption_dedupe import load_used_captions, save_used_captions, pick_caption  # noqa: E402

# 历史中国城市去重账本（按 photoId 判重）
SEED_URL_FILES = [
    "state/seen_cn_city.json", "state/seen_cn_city_en.json",
    "state/seen_cn_sz.json", "state/seen_cn_sz2.json",
    "state/seen_cn_modern.json", "state/seen_cn_modern2.json",
]

ID_DEDUPE_FILE = "state/seen_cn_city_ids.json"

# 累计已用文案账本（跨批次防文案重复）
CAPTION_DEDUPE_FILE = "state/seen_cn_city_captions.json"

# 明显非长沙/深圳的内容标记（alt 文案关键词），命中即剔除
NON_TARGET_MARKERS = [
    "malaysia", "kuala lumpur", "hangzhou", "shanghai", "beijing", "guangzhou",
    "chengdu", "wuhan", "chongqing", "nanjing", "xian", "hong kong", "singapore",
    "tokyo", "paris", "london", "new york", "indonesia", "thailand", "vietnam",
]

# 城市识别（alt 含关键词 → 归属城市）
CITY_CS = ["changsha"]
CITY_SZ = ["shenzhen"]

# 繁体中文·简洁怀旧文案池（第一人称，按城市 + 白天/夜景分池）
CS_DAY = [
    "長沙的街頭，時光慢了下來。🏮 #長沙 #老街 #老照片 #那些往事",
    "湘江穿城而過，風景如舊。🌉 #長沙 #湘江 #老照片 #那些往事",
    "高樓之間，藏著老城的影子。🏙️ #長沙 #城市 #老照片 #那些往事",
]
CS_NIGHT = [
    "長沙的夜，霓虹點點。🌃 #長沙 #夜景 #老照片 #那些往事",
    "湘江邊的燈火，暖了整座城。✨ #長沙 #湘江夜景 #老照片 #那些往事",
    "夜色裡的星城，還是記憶中的樣子。🌙 #長沙 #夜色 #老照片 #那些往事",
]
SZ_DAY = [
    "深圳的高樓，見證著這座城的飛躍。🏙️ #深圳 #城市 #老照片 #那些往事",
    "老街換了新裝，回憶卻還停在原地。🛤️ #深圳 #城市變遷 #老照片 #那些往事",
    "這座年輕的城市，也有說不完的故事。🌆 #深圳 #城市記憶 #老照片 #那些往事",
]
SZ_NIGHT = [
    "這座城的霓虹，徹夜不眠。🌃 #深圳 #夜景 #老照片 #那些往事",
    "昔日小漁村，如今萬家燈火。🏙️ #深圳 #城市夜景 #老照片 #那些往事",
    "高樓的燈，是這座城最亮的星。✨ #深圳 #夜色 #老照片 #那些往事",
]

NIGHT_MARKERS = ["night", "neon", "dusk", "twilight", "illuminated", "sunset", "evening", "lights"]


def _u8():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:  # noqa: BLE001
        pass


def photo_key(url: str) -> str:
    m = re.search(r"/photos/(\d+)/", url)
    if m:
        return "pexels:" + m.group(1)
    m = re.search(r"/(\d+)_\d{2,4}\.(?:jpg|jpeg|png|webp)$", url)
    if m:
        return "pixabay:" + m.group(1)
    return url


def load_id_dedupe() -> set[str]:
    p = ROOT / ID_DEDUPE_FILE
    ids: set[str] = set()
    if p.exists():
        try:
            ids = {str(x) for x in json.loads(p.read_text(encoding="utf-8"))}
        except Exception:  # noqa: BLE001
            ids = set()
    if ids:
        return ids
    for rel in SEED_URL_FILES:
        sp = ROOT / rel
        if not sp.exists():
            continue
        try:
            for u in json.loads(sp.read_text(encoding="utf-8")):
                ids.add(photo_key(str(u)))
        except Exception:  # noqa: BLE001
            pass
    return ids


def save_id_dedupe(ids: set[str]) -> None:
    p = ROOT / ID_DEDUPE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def _run(cmd, env_extra=None):
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main() -> int:
    _u8()
    ap = argparse.ArgumentParser(
        description="中国城市图文一键发布（长沙/深圳 → 繁体中文怀旧文案）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_cn_city_3.csv")
    ap.add_argument("--raw-csvs", default="",
                    help="逗号分隔的已采集 raw CSV，跳过采集")
    ap.add_argument("--posts", type=int, default=6, help="要发布的帖子总数")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--tokens", default="result/tokens_cn_city.json")
    ap.add_argument("--workdir", default="cn_city_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    acc_path = ROOT / args.accounts_csv
    if not acc_path.exists():
        print(f"[cn_city] 账号 CSV 不存在: {acc_path}", file=sys.stderr)
        return 2

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    moments = wd / f"moments_cn_city_{ts}.csv"

    # ---- Step 1: 采集（或复用）----
    if args.raw_csvs:
        raw_files = [ROOT / p.strip() for p in args.raw_csvs.split(",") if p.strip()]
        print(f"=== Step 1/3: 复用已采集 raw CSV：{len(raw_files)} 个 ===")
    else:
        raw_files = []
        print("=== Step 1/3: 采集长沙/深圳城市与夜景图 ===")
        for q in ("changsha city", "changsha night", "shenzhen city", "shenzhen night"):
            out = wd / f"{q.replace(' ', '_')}_raw_{ts}.csv"
            cmd = PY + [str(HERE / "fetch_stock_my.py"),
                        "--sources", "pexels,pixabay",
                        "--query", q,
                        "--per-source", "15",
                        "--dedupe-file", "state/seen_cn_city_all.json",
                        "--output", str(out)]
            if _run(cmd) != 0 or not out.exists():
                print(f"[cn_city] 采集失败：{q}", file=sys.stderr)
                continue
            raw_files.append(out)

    # ---- Step 2: 按 photoId 去重 + 过滤 + 归属城市 ----
    print("=== Step 2/3: 按 photoId 去重 + 过滤 ===")
    seed_ids = load_id_dedupe()
    seen: set[str] = set()
    fresh: list[dict] = []
    for rf in raw_files:
        if not rf.exists():
            continue
        for r in csv.DictReader(rf.open(encoding="utf-8-sig")):
            u = (r.get("image_urls") or "").strip()
            alt = (r.get("content") or "").lower()
            if not u:
                continue
            k = photo_key(u)
            if k in seed_ids or k in seen:
                continue
            if any(m in alt for m in NON_TARGET_MARKERS):
                continue
            if CITY_CS and any(m in alt for m in CITY_CS):
                city = "changsha"
            elif CITY_SZ and any(m in alt for m in CITY_SZ):
                city = "shenzhen"
            else:
                continue
            seen.add(k)
            fresh.append({"image_urls": u, "content": alt, "city": city})
    print(f"[cn_city] 去重后可用 {len(fresh)} 张")

    # 按 城市×白天/夜景 分桶，再交错选取，保证长沙/深圳、城市/夜景均衡
    def is_night(alt: str) -> bool:
        return any(k in alt for k in NIGHT_MARKERS)

    buckets = {"cs_day": [], "cs_night": [], "sz_day": [], "sz_night": []}
    for r in fresh:
        n = is_night(r["content"])
        key = ("cs" if r["city"] == "changsha" else "sz") + ("_night" if n else "_day")
        buckets[key].append(r)

    selected: list[dict] = []
    order = ["cs_day", "sz_night", "cs_night", "sz_day"]
    ptr = {k: 0 for k in order}
    while len(selected) < args.posts:
        progressed = False
        for k in order:
            if len(selected) >= args.posts:
                break
            if ptr[k] < len(buckets[k]):
                selected.append(buckets[k][ptr[k]])
                ptr[k] += 1
                progressed = True
        if not progressed:
            break
    if len(selected) < args.posts:
        print(f"[cn_city] 提示：仅 {len(selected)} 张可用（目标 {args.posts}）", file=sys.stderr)
    if not selected:
        print("[cn_city] 无可用图片，终止。", file=sys.stderr)
        return 1

    # ---- 生成文案 ----
    pool_for = {
        "cs_day": CS_DAY, "cs_night": CS_NIGHT, "sz_day": SZ_DAY, "sz_night": SZ_NIGHT,
    }
    used_captions = load_used_captions(ROOT / CAPTION_DEDUPE_FILE)
    out_rows = []
    for r in selected:
        n = is_night(r["content"])
        key = ("cs" if r["city"] == "changsha" else "sz") + ("_night" if n else "_day")
        cap = pick_caption(pool_for[key], used_captions)
        out_rows.append({
            "content": cap, "visibility": 0, "room_id": "",
            "image_urls": r["image_urls"],
            "location_name": "長沙" if r["city"] == "changsha" else "深圳",
            "location_address": "", "location_lat": "", "location_lon": "",
            "_site": "pexels", "_tag": "city", "_lang": "zh_hant",
        })
    save_used_captions(used_captions, ROOT / CAPTION_DEDUPE_FILE)

    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_site", "_tag", "_lang"]
    with moments.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    for i, r in enumerate(out_rows):
        print(f"  #{i+1} {r['content'][:46]} | {photo_key(r['image_urls'])}")
    print(f"[cn_city] moments 就绪：{len(out_rows)} 帖 → {moments}")

    save_id_dedupe(seed_ids | {photo_key(r["image_urls"]) for r in out_rows})

    if args.skip_publish:
        print("\n[cn_city] --skip-publish，仅产出素材：", moments)
        return 0

    # ---- Step 3: 发布 ----
    print("\n=== Step 3/3: 发布（单图帖）===")
    print(f"  账号 CSV : {acc_path}\n  素材帖数 : {len(out_rows)}  并发: {args.concurrency}")
    if not args.yes:
        if input("  确认发布真实帖子？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[cn_city] 已取消。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_path), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "2.5",
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd, env_extra={"POST_CROP_BOTTOM_HOSTS": ""})
    if rc != 0:
        print("[cn_city] 发布返回非零，请查看 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[cn_city] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
