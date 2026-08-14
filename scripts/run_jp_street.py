#!/usr/bin/env python3
"""
run_jp_street.py — 日本街拍图片一键发布（东京街景图 → 日文摄影师口吻文案 → 图文发布）

流程：
    1) 采集   fetch_stock_my.py（Pexels/Pixabay 搜索「tokyo street」无水印原图）
    2) 去重   按图片 photoId 去重（Pexels 同一张图有多种 URL 形态，须按 ID 判重）
    3) 文案   日文第一人称街拍摄影师口吻，池内轮询不重复
    4) 发布   publish_from_tokens.py（单图帖）

用法：
    py -3 scripts/run_jp_street.py --accounts-csv accounts_jp_street_2.csv --skip-publish
    py -3 scripts/run_jp_street.py --accounts-csv accounts_jp_street_2.csv --yes
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

# 历史东京/日本街拍 URL 账本（用于首次播种 photoId 账本）
SEED_URL_FILES = [
    "state/seen_jp_street.json",
    "state/seen_street_jp_city.json",
]

# 累计已用 photoId 账本（跨批次防重复）
ID_DEDUPE_FILE = "state/seen_jp_street_ids.json"

# 累计已用文案账本（跨批次防文案重复）
CAPTION_DEDUPE_FILE = "state/seen_jp_street_captions.json"

# 明显非日本/东京的内容标记（alt 文案关键词），命中即剔除
NON_JP_MARKERS = [
    "malaysia", "kuala lumpur", "indonesia", "singapore", "thailand",
    "china", "korea", "vietnam", "new york", "paris", "london", "india",
]

# 日文街拍摄影师口吻文案池（第一人称，按白天/夜晚分池，池内轮询不重复）
DAY_CAPTIONS = [
    "通りを歩く人たちの何気ない一瞬を、レンズ越しに切り取った。📷 #東京 #街撮り #スナップ",
    "ビルの谷間から差す光。東京の街はいつ見ても表情が違う。🏙️ #東京 #街景 #建築",
    "看板がぎっしり並ぶ下町の景色。カメラを向けると、街の鼓動が聞こえてくる気がする。🏮 #東京街歩き #スナップ #下町",
    "静かな朝の東京。まだ人も少ない街を、レンズ越しに切り取る。☀️ #街撮り #東京の朝 #スナップ写真",
    "商店街のアーケードを抜ける風。看板の色が、シャッター音と重なる。📸 #街歩き #東京 #スナップ",
    "路地裏に迷い込んで、地元の人の生活が垣間見えた瞬間。こういう出会いが好きだ。🚲 #東京 #路地 #街撮り",
    "電柱と電線が空を切り取る。東京らしい、少しせわしないけれど愛おしい景色。🏘️ #東京 #下町 #スナップ",
    "交差点の人の波。信号が青に変わる一瞬に、この街のテンポを感じる。🚦 #東京 #交差点 #ストリートフォト",
]

NIGHT_CAPTIONS = [
    "ネオンに照らされた夜道。人混みの中、ふと足を止めてシャッターを切った。📷 #東京 #街撮り #夜景",
    "夕暮れの街、車のテールランプとネオンが交差する。一日の終わりにしか撮れない色。🌇 #東京 #夕暮れ #ストリートフォト",
    "夜の街、ネオンの海を抜けて。光と影のコントラストがたまらない。🌃 #東京ナイト #ストリート #夜景",
    "雑居ビルと電線の隙間から見える空。なんてことない景色だけど、ここにしかない表情がある。🌙 #東京 #街景 #日常",
    "路地裏の灯りに吸い込まれるように歩いた。ネオンが濡れた路面に滲んで、別世界みたいだった。🌧️ #東京 #路地 #ナイトウォーク",
    "仕事終わりの街は、昼とは違う顔を見せる。看板の光が人の流れを照らしている。🚶 #東京 #夜の街 #スナップ",
    "静まり返った商店街に、まだ灯りのついた一軒の店。この静けさがたまらなく好きだ。🏪 #東京 #夜 #日常",
    "ネオンの反射を追いかけて、いつの間にかシャッターを切る手が止まらない。📸 #東京 #ナイトスナップ #街撮り",
]

NIGHT_MARKERS = ["night", "neon", "dusk", "twilight", "nightlife", "light"]


def _u8():
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:  # noqa: BLE001
        pass


def photo_key(url: str) -> str:
    """按图片唯一 ID 生成去重键（Pexels 同图多种 URL 形态须归一）。"""
    m = re.search(r"/photos/(\d+)/", url)
    if m:
        return "pexels:" + m.group(1)
    m = re.search(r"/(\d+)_\d{2,4}\.(?:jpg|jpeg|png|webp)$", url)
    if m:
        return "pixabay:" + m.group(1)
    return url


def load_id_dedupe() -> set[str]:
    """读取累计 photoId 账本；首次运行时从历史 URL 账本播种。"""
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
        description="日本街拍图片一键发布（东京街景 → 日文文案 → 图文发布）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_jp_street_2.csv")
    ap.add_argument("--query", default="tokyo street")
    ap.add_argument("--posts", type=int, default=6, help="要发布的帖子总数")
    ap.add_argument("--per-source", type=int, default=20, help="每个图库最多取图数")
    ap.add_argument("--raw-csv", default="", help="复用已采集的 raw CSV（跳过采集）")
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--tokens", default="result/tokens_jp_street.json")
    ap.add_argument("--workdir", default="jp_street_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    acc_path = ROOT / args.accounts_csv
    if not acc_path.exists():
        print(f"[jp_street] 账号 CSV 不存在: {acc_path}", file=sys.stderr)
        return 2

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    moments = wd / f"moments_jp_street_{ts}.csv"

    # ---- Step 1: 采集 ----
    if args.raw_csv and (ROOT / args.raw_csv).exists():
        raw = ROOT / args.raw_csv
        print(f"=== Step 1/3: 复用已采集 raw CSV：{raw} ===")
    else:
        raw = wd / f"tokyo_street_raw_{ts}.csv"
        print(f"=== Step 1/3: 采集东京街景图（query={args.query}）===")
        cmd = PY + [str(HERE / "fetch_stock_my.py"),
                    "--sources", "pexels,pixabay",
                    "--query", args.query,
                    "--per-source", str(args.per_source),
                    "--dedupe-file", "state/seen_jp_street_all.json",
                    "--output", str(raw)]
        if _run(cmd) != 0 or not raw.exists():
            print("[jp_street] 采集失败，终止。", file=sys.stderr)
            return 1

    # ---- Step 2: 按 photoId 去重 + 过滤非东京内容 + 截断 ----
    print("=== Step 2/3: 按 photoId 去重 + 过滤 ===")
    seed_ids = load_id_dedupe()
    rows = list(csv.DictReader(raw.open(encoding="utf-8-sig")))
    fresh = []
    for r in rows:
        u = (r.get("image_urls") or "").strip()
        alt = (r.get("content") or "").lower()
        if not u:
            continue
        if photo_key(u) in seed_ids:
            continue
        if any(k in alt for k in NON_JP_MARKERS):
            continue
        fresh.append(r)
    print(f"[jp_street] 原始 {len(rows)} / 去重后可用 {len(fresh)}")
    fresh = fresh[:args.posts]
    if not fresh:
        print("[jp_street] 无可用图片，终止。", file=sys.stderr)
        return 1

    # ---- 生成文案并写入 moments CSV ----
    out_rows = []
    used_captions = load_used_captions(ROOT / CAPTION_DEDUPE_FILE)
    for r in fresh:
        alt = (r.get("content") or "").lower()
        is_night = any(k in alt for k in NIGHT_MARKERS)
        if is_night:
            caption = pick_caption(NIGHT_CAPTIONS, used_captions)
        else:
            caption = pick_caption(DAY_CAPTIONS, used_captions)
        out_rows.append({
            "content": caption, "visibility": 0, "room_id": "",
            "image_urls": r.get("image_urls", ""),
            "location_name": "東京", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_site": r.get("_source", ""), "_tag": "street", "_lang": "ja",
        })
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_site", "_tag", "_lang"]
    with moments.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)
    for i, r in enumerate(out_rows):
        print(f"  #{i+1} {r['content'][:48]} | {photo_key(r['image_urls'])}")
    print(f"[jp_street] moments 就绪：{len(out_rows)} 帖 → {moments}")

    # 回写 photoId 去重账本
    save_id_dedupe(seed_ids | {photo_key(r["image_urls"]) for r in out_rows})
    # 回写文案去重账本（跨批次防文案重复）
    save_used_captions(used_captions, ROOT / CAPTION_DEDUPE_FILE)

    if args.skip_publish:
        print("\n[jp_street] --skip-publish，仅产出素材：", moments)
        return 0

    # ---- Step 3: 发布 ----
    print("\n=== Step 3/3: 发布（单图帖）===")
    print(f"  账号 CSV : {acc_path}\n  素材帖数 : {len(out_rows)}  并发: {args.concurrency}")
    if not args.yes:
        if input("  确认发布真实帖子？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[jp_street] 已取消。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_path), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "2.5",
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd, env_extra={"POST_CROP_BOTTOM_HOSTS": ""})
    if rc != 0:
        print("[jp_street] 发布返回非零，请查看 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[jp_street] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
