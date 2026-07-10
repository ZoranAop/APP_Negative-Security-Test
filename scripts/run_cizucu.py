#!/usr/bin/env python3
"""
run_cizucu.py — 刺猬社区(cizucu.com)内容一键发布（采集 → 主体视角文案 → 发布）

把 cizucu 摄影社区内容的三步串成一条命令：
    1) 采集       fetch_cizucu.py   （Playwright，从各主题模块页取图，多图帖）
    2) 文案       caption_multilang.py  （按图片场景生成主体视角/摄影师口吻文案）
    3) 发布       publish_from_tokens.py（cizucu 图无水印 → 默认不裁切）

做法与 malaysia / indonesia / taiwan 三条地区线一致，仅数据源换为 cizucu 摄影社区，
主题模块（人像/街拍/风光/城市/自然/建筑/胶片/日常…）即「网站模块」，
标签页为二级页，滚动懒加载进入三级/更多，photoId → CDN 原图直链。

用法范例
    # 默认：8 个主题模块 × 3 帖，10 账号轮询，英文+中文文案
    py -3 scripts/run_cizucu.py --accounts-csv accounts_10.csv --posts-per-theme 3

    # 指定主题模块与语言
    py -3 scripts/run_cizucu.py --themes portrait,street,film --langs en,zh_hant --posts-per-theme 4

    # 只采集+文案、不发布（预演）
    py -3 scripts/run_cizucu.py --skip-publish

    # 无人值守
    py -3 scripts/run_cizucu.py --accounts-csv accounts_10.csv --yes

参数说明见 --help。发布前会打印计划并要求确认（除非 --yes）。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]


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
        description="cizucu one-command publisher (fetch → caption → publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_10.csv", help="账号 CSV（不入库，本地放置）")
    # fetch options
    ap.add_argument("--themes",
                    default="portrait,street,scenery,city,nature,architecture,film,daily",
                    help="逗号分隔的主题模块（见 fetch_cizucu.py 的 THEME_TAGS）")
    ap.add_argument("--posts-per-theme", type=int, default=3, help="每个主题模块产出的帖子数")
    ap.add_argument("--imgs-per-post", type=int, default=6, help="每帖图片数（后端上限 9）")
    ap.add_argument("--min-imgs", type=int, default=4, help="少于 N 张图的主题块跳过")
    ap.add_argument("--scrolls", type=int, default=10, help="每个主题页滚动次数（懒加载深度）")
    ap.add_argument("--posts", type=int, default=0, help="总帖数上限（0=不限）")
    ap.add_argument("--dedupe-file", default=None,
                    help="去重档路径（默认 state/seen_cizucu.json，持久保留跨批次防重复）")
    ap.add_argument("--reset-dedupe", action="store_true", help="清空去重记录，允许重新抓取已抓过的图")
    # caption
    ap.add_argument("--langs", default="en,zh", help="文案语言（cizucu 图偏摄影作品，默认 en,zh）")
    ap.add_argument("--default-scene", default="portrait", help="文案兜底场景")
    # publish
    ap.add_argument("--concurrency", type=int, default=3, help="发布并发数")
    ap.add_argument("--tokens", default="result/tokens.json", help="token 缓存（复用免重复登录）")
    # cizucu 图无水印 → 默认不裁切；如某图确需裁切用 --crop 开启
    ap.add_argument("--crop", action="store_true", help="开启底部裁切（默认关闭，cizucu 图无水印）")
    ap.add_argument("--crop-pct", default="0.08")
    # workflow control
    ap.add_argument("--workdir", default="cizucu_run", help="中间产物目录")
    ap.add_argument("--skip-publish", action="store_true", help="只采集+文案，不发布")
    ap.add_argument("--yes", action="store_true", help="跳过发布前确认")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw = wd / f"cizucu_raw_{ts}.csv"
    moments = wd / f"moments_cizucu_{ts}.csv"

    print(f"[run_cizucu] themes={args.themes} posts-per-theme={args.posts_per_theme} langs={args.langs}")

    # ---- Step 1: fetch ----
    print("\n=== Step 1/3: 采集（cizucu 主题模块 → 二级/三级页 → 多图帖）===")
    state_dir = ROOT / "state"
    state_dir.mkdir(exist_ok=True)
    dedupe_path = (ROOT / args.dedupe_file) if args.dedupe_file else (state_dir / "seen_cizucu.json")
    if args.reset_dedupe and dedupe_path.exists():
        dedupe_path.unlink()
        print(f"[run_cizucu] 已重置去重档：{dedupe_path.name}")
    print(f"[run_cizucu] 去重档：{dedupe_path}（自动跳过已抓过的图）")

    cmd = PY + [str(HERE / "fetch_cizucu.py"),
                "--themes", args.themes,
                "--posts-per-theme", str(args.posts_per_theme),
                "--imgs-per-post", str(args.imgs_per_post),
                "--min-imgs", str(args.min_imgs),
                "--scrolls", str(args.scrolls),
                "--dedupe-file", str(dedupe_path),
                "--output", str(raw)]
    if args.posts:
        cmd += ["--posts", str(args.posts)]
    if _run(cmd) != 0 or not raw.exists():
        print("[run_cizucu] 采集失败，终止。", file=sys.stderr)
        return 1

    # ---- Step 2: caption ----
    print("\n=== Step 2/3: 主体视角文案 ===")
    cmd = PY + [str(HERE / "caption_multilang.py"),
                "--input", str(raw), "--output", str(moments), "--langs", args.langs]
    if _run(cmd, env_extra={"DEFAULT_SCENE": args.default_scene}) != 0 or not moments.exists():
        print("[run_cizucu] 文案改写失败，终止。", file=sys.stderr)
        return 1

    import csv as _csv
    rows = list(_csv.DictReader(moments.open(encoding="utf-8-sig")))
    print(f"[run_cizucu] moments ready: {len(rows)} 帖")

    if args.skip_publish:
        print("\n[run_cizucu] --skip-publish 已设置，仅产出素材：", moments)
        return 0

    # ---- Step 3: publish ----
    print("\n=== Step 3/3: 发布（cizucu 图无水印，默认不裁切）===")
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[run_cizucu] 账号 CSV 不存在: {acc}", file=sys.stderr)
        return 2
    print(f"  账号 CSV : {acc}")
    print(f"  素材帖数 : {len(rows)}  并发: {args.concurrency}  "
          f"裁切: {'bottom '+str(args.crop_pct) if args.crop else '关闭（不裁切）'}")
    if not args.yes:
        if input("  确认发布真实帖子？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[run_cizucu] 已取消。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    if args.crop:
        pub_env = {"POST_CROP_BOTTOM_PCT": str(args.crop_pct)}
    else:
        pub_env = {"POST_CROP_BOTTOM_HOSTS": ""}  # cizucu 无水印，关闭裁切
    rc = _run(cmd, env_extra=pub_env)
    if rc != 0:
        print("[run_cizucu] 发布返回非零，请查看日志与 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[run_cizucu] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
