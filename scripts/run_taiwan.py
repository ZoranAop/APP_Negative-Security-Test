#!/usr/bin/env python3
"""
run_taiwan.py — 台灣內容一鍵發布（採集 → 繁體中文/台灣語境文案 → 裁切 → 發布）

把台灣內容的三步串成一條命令：
    1) 採集       fetch_ervnsa_tw.py  (預設，觀光署相簿多圖)  /  fetch_stock_my.py (Pexels/Unsplash)
    2) 繁中文案    caption_multilang.py --langs zh_hant  (台灣語境模板)
    3) 發布       publish_from_tokens.py  (小紅書 + bbkz + erv-nsa 底部浮水印自動裁切)

用法範例
    # 預設：觀光署相簿，5 帳號 × 2 帖 = 10 個多圖帖，繁體中文
    py -3 scripts/run_taiwan.py --accounts-csv accounts_5.csv --posts 10

    # 圖庫源（Pexels + Unsplash，台灣關鍵字，需 Playwright）
    py -3 scripts/run_taiwan.py --source stock --accounts-csv accounts_10.csv --posts 50

    # 只採集+文案、不發布（預演）
    py -3 scripts/run_taiwan.py --posts 5 --skip-publish
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _run(cmd, *, env_extra=None):
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Taiwan one-command publisher (fetch → zh_hant caption → crop → publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    PY = [sys.executable]
    ap.add_argument("--source", choices=["ervnsa", "stock", "media"], default="ervnsa",
                    help="採集源：ervnsa 觀光署相簿 / stock 圖庫(Pexels+Unsplash) / "
                         "media 台灣媒體(shoppingdesign+gq+sony)")
    ap.add_argument("--accounts-csv", default="accounts_5.csv")
    ap.add_argument("--posts", type=int, default=10)
    # ervnsa options
    ap.add_argument("--imgs-per-post", type=int, default=9)
    ap.add_argument("--min-imgs", type=int, default=3)
    ap.add_argument("--listing-pages", type=int, default=8)
    ap.add_argument("--dedupe-file", default=None,
                    help="去重檔路徑（預設按源自動放 state/seen_tw_<source>.json，持久保留）")
    ap.add_argument("--reset-dedupe", action="store_true",
                    help="清空該源的去重紀錄，允許重新抓取已抓過的內容")
    # stock options
    ap.add_argument("--stock-sources", default="pexels,unsplash")
    ap.add_argument("--query", default="taiwan")
    ap.add_argument("--per-source", type=int, default=30)
    ap.add_argument("--locale", default="zh-TW")
    # media options
    ap.add_argument("--media-sources", default="shoppingdesign,gq,sony")
    # caption
    ap.add_argument("--langs", default="zh_hant")
    ap.add_argument("--default-scene", default="travel")
    # publish
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--tokens", default="result/tokens.json")
    # 台灣分支：預設「不裁切」任何圖片。若確有需要可用 --crop 開啟並用 --crop-pct 指定比例。
    ap.add_argument("--crop", action="store_true",
                    help="開啟底部浮水印裁切（預設關閉，台灣分支圖片不裁切）")
    ap.add_argument("--crop-pct", default="0.08")
    # control
    ap.add_argument("--workdir", default="tw_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw = wd / f"{args.source}_raw_{ts}.csv"
    moments = wd / f"moments_{args.source}_{ts}.csv"

    print(f"[run_taiwan] source={args.source} posts={args.posts} langs={args.langs}")

    print("\n=== Step 1/3: 採集 ===")
    # 持久去重：每個源用固定的 dedupe 檔（放 state/），下次自動跳過已抓內容。
    # --dedupe-file 可覆蓋；--reset-dedupe 清空重抓。
    state_dir = ROOT / "state"
    state_dir.mkdir(exist_ok=True)
    default_dd = {
        "ervnsa": state_dir / "seen_tw_ervnsa.json",
        "media": state_dir / "seen_tw_media.json",
        "stock": state_dir / "seen_tw_stock.json",
    }[args.source]
    dedupe_path = (ROOT / args.dedupe_file) if args.dedupe_file else default_dd
    if args.reset_dedupe and dedupe_path.exists():
        dedupe_path.unlink()
        print(f"[run_taiwan] 已重置去重檔：{dedupe_path.name}")
    print(f"[run_taiwan] 去重檔：{dedupe_path}（自動跳過已抓內容）")

    if args.source == "ervnsa":
        cmd = PY + [str(HERE / "fetch_ervnsa_tw.py"),
                    "--posts", str(args.posts),
                    "--imgs-per-post", str(args.imgs_per_post),
                    "--min-imgs", str(args.min_imgs),
                    "--listing-pages", str(args.listing_pages),
                    "--dedupe-file", str(dedupe_path),
                    "--output", str(raw)]
    elif args.source == "media":
        cmd = PY + [str(HERE / "fetch_tw_media.py"),
                    "--sources", args.media_sources,
                    "--posts", str(args.posts),
                    "--imgs-per-post", str(args.imgs_per_post),
                    "--min-imgs", str(args.min_imgs),
                    "--dedupe-file", str(dedupe_path),
                    "--output", str(raw)]
    else:
        cmd = PY + [str(HERE / "fetch_stock_my.py"),
                    "--sources", args.stock_sources,
                    "--query", args.query,
                    "--per-source", str(args.per_source),
                    "--locale", args.locale,
                    "--dedupe-file", str(dedupe_path),
                    "--output", str(raw)]
    if _run(cmd) != 0 or not raw.exists():
        print("[run_taiwan] 採集失敗，終止。", file=sys.stderr)
        return 1

    print("\n=== Step 2/3: 繁體中文文案 ===")
    cmd = PY + [str(HERE / "caption_multilang.py"),
                "--input", str(raw), "--output", str(moments), "--langs", args.langs]
    # media 源帶有文章正文 _excerpt → 用內容感知文案，結合網頁內容差異化，避免同質化
    if args.source == "media":
        cmd.append("--content-aware")
    if _run(cmd, env_extra={"DEFAULT_SCENE": args.default_scene}) != 0 or not moments.exists():
        print("[run_taiwan] 文案改寫失敗，終止。", file=sys.stderr)
        return 1

    import csv as _csv
    rows = list(_csv.DictReader(moments.open(encoding="utf-8-sig")))
    print(f"[run_taiwan] moments ready: {len(rows)} 帖")

    if args.skip_publish:
        print("\n[run_taiwan] --skip-publish，僅產出素材：", moments)
        return 0

    print("\n=== Step 3/3: 發布（bbkz + erv-nsa + 小紅書底部浮水印自動裁切）===")
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[run_taiwan] 帳號 CSV 不存在: {acc}", file=sys.stderr)
        return 2
    print(f"  帳號 CSV : {acc}\n  素材帖數 : {len(rows)}  併發: {args.concurrency}  裁切: {'bottom '+str(args.crop_pct) if args.crop else '關閉（不裁切）'}")
    if not args.yes:
        if input("  確認發布真實帖子？輸入 y 繼續：").strip().lower() not in ("y", "yes"):
            print("[run_taiwan] 已取消。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    # 台灣分支預設不裁切：把裁切域名清空（覆蓋 .env / 代碼預設）。--crop 才啟用。
    if args.crop:
        pub_env = {"POST_CROP_BOTTOM_PCT": str(args.crop_pct)}
    else:
        pub_env = {"POST_CROP_BOTTOM_HOSTS": ""}
    rc = _run(cmd, env_extra=pub_env)
    if rc != 0:
        print("[run_taiwan] 發布返回非零，請查看日誌與 result/ 報告。", file=sys.stderr)
        return rc
    print("\n[run_taiwan] 完成。發布報告見 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
