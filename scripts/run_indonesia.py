#!/usr/bin/env python3
"""
run_indonesia.py — 印尼内容一键发布（采集 → 印尼语文案 → 裁切 → 发布）

把印尼内容的三步串成一条命令：
    1) 采集       fetch_backpackers_my.py --fid 54  (默认，印尼版)  /  fetch_stock_my.py
    2) 印尼语文案  caption_multilang.py --langs id
    3) 发布       publish_from_tokens.py   (小红书 + bbkz.net 底部水印自动裁切)

用法示例
    # 默认：backpackers 论坛印尼版(f=54)，5 账号 × 2 帖 = 10 个多图帖，印尼语
    py -3 scripts/run_indonesia.py --accounts-csv accounts_5.csv --posts 10

    # 图库源（Pexels + Pixabay，印尼关键词，需要 Playwright）
    py -3 scripts/run_indonesia.py --source stock --accounts-csv accounts_10.csv --posts 50

    # 只采集+文案、不发布（预演）
    py -3 scripts/run_indonesia.py --posts 5 --skip-publish

参数说明见 --help。发布前会打印计划并要求确认（除非 --yes）。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                              # repo root


def _run(cmd: list[str], *, env_extra: dict | None = None) -> int:
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Indonesia one-command publisher (fetch → Indonesian caption → crop → publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    PY = [sys.executable]
    ap.add_argument("--source", choices=["backpackers", "stock"], default="backpackers",
                    help="采集源：backpackers 印尼版论坛多图 / stock 图库(Pexels+Pixabay)")
    ap.add_argument("--accounts-csv", default="accounts_5.csv", help="账号 CSV（不入库，本地放置）")
    ap.add_argument("--posts", type=int, default=10, help="要发布的帖子数量（=采集条数）")
    # backpackers options — 印尼版默认 f=54
    ap.add_argument("--fid", type=int, default=54, help="[backpackers] 论坛版块 id（54=印尼 Indonesia）")
    ap.add_argument("--imgs-per-post", type=int, default=9, help="[backpackers] 每帖最多图片数（后端上限 9）")
    ap.add_argument("--min-imgs", type=int, default=4, help="[backpackers] 少于 N 张图的贴跳过")
    ap.add_argument("--listing-pages", type=int, default=4, help="[backpackers] 扫描的论坛列表页数")
    ap.add_argument("--dedupe-file", default="id_used_threads.json",
                    help="[backpackers] 已用过的 thread id JSON（保证取新贴）")
    # stock options
    ap.add_argument("--query", default="indonesia", help="[stock] 搜索关键词")
    ap.add_argument("--per-source", type=int, default=30, help="[stock] 每个图库最多取图数")
    ap.add_argument("--locale", default="id-ID", help="[stock] 浏览器 locale")
    # caption
    ap.add_argument("--langs", default="id", help="文案语言（本流程默认印尼语 id）")
    ap.add_argument("--default-scene", default="travel", help="文案兜底场景（印尼多为风景 → travel）")
    # publish
    ap.add_argument("--concurrency", type=int, default=3, help="发布并发数")
    ap.add_argument("--tokens", default="result/tokens.json", help="token 缓存（复用免重复登录）")
    ap.add_argument("--crop-pct", default="0.08", help="底部水印裁切比例（bbkz/小红书生效）")
    # workflow control
    ap.add_argument("--workdir", default="id_run", help="中间产物目录")
    ap.add_argument("--skip-publish", action="store_true", help="只采集+文案，不发布")
    ap.add_argument("--yes", action="store_true", help="跳过发布前确认")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw = wd / f"{args.source}_raw_{ts}.csv"
    moments = wd / f"moments_{args.source}_{ts}.csv"

    print(f"[run_indonesia] source={args.source} posts={args.posts} langs={args.langs}")
    print(f"[run_indonesia] raw={raw.name}  moments={moments.name}")

    # ---- Step 1: fetch ----
    print("\n=== Step 1/3: 采集 ===")
    if args.source == "backpackers":
        cmd = PY + [str(HERE / "fetch_backpackers_my.py"),
                    "--fid", str(args.fid), "--posts", str(args.posts),
                    "--imgs-per-post", str(args.imgs_per_post),
                    "--min-imgs", str(args.min_imgs),
                    "--listing-pages", str(args.listing_pages),
                    "--output", str(raw)]
        if args.dedupe_file:
            cmd += ["--dedupe-file", str(ROOT / args.dedupe_file)]
    else:  # stock
        cmd = PY + [str(HERE / "fetch_stock_my.py"),
                    "--sources", "pexels,pixabay",
                    "--query", args.query,
                    "--per-source", str(args.per_source),
                    "--locale", args.locale,
                    "--output", str(raw)]
    if _run(cmd) != 0 or not raw.exists():
        print("[run_indonesia] 采集失败，终止。", file=sys.stderr)
        return 1

    # ---- Step 2: Indonesian caption ----
    print("\n=== Step 2/3: 印尼语文案 ===")
    cmd = PY + [str(HERE / "caption_multilang.py"),
                "--input", str(raw), "--output", str(moments),
                "--langs", args.langs]
    if _run(cmd, env_extra={"DEFAULT_SCENE": args.default_scene}) != 0 or not moments.exists():
        print("[run_indonesia] 文案改写失败，终止。", file=sys.stderr)
        return 1

    import csv as _csv
    rows = list(_csv.DictReader(moments.open(encoding="utf-8-sig")))
    print(f"[run_indonesia] moments ready: {len(rows)} 帖")

    if args.skip_publish:
        print("\n[run_indonesia] --skip-publish 已设置，仅产出素材，未发布。")
        print(f"  素材 CSV: {moments}")
        return 0

    # ---- Step 3: publish (with bbkz/xhs bottom crop) ----
    print("\n=== Step 3/3: 发布（bbkz + 小红书底部水印自动裁切）===")
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[run_indonesia] 账号 CSV 不存在: {acc}", file=sys.stderr)
        return 2
    print(f"  账号 CSV : {acc}")
    print(f"  素材帖数 : {len(rows)}  并发: {args.concurrency}  裁切: bottom {args.crop_pct}")
    if not args.yes:
        ans = input("  确认发布真实帖子？输入 y 继续：").strip().lower()
        if ans not in ("y", "yes"):
            print("[run_indonesia] 已取消发布。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd, env_extra={"POST_CROP_BOTTOM_PCT": str(args.crop_pct)})
    if rc != 0:
        print("[run_indonesia] 发布过程返回非零，请查看上面日志与 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[run_indonesia] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
