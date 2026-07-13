#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_mixed.py — 「混合交错」一键发布（拟真、去规则化）。

把四步串成一条命令：
    1) 采集文本   fetch_web3.py         （web3/科技真实资讯，带去重档）
    2) 采集图文   multi_source_fetch.py （图库素材，带 slug 去重档）
    3) 组装       assemble_mixed.py     （每人随机帖数 + T/I/Q 交错 + 单语分配 + 配文去重）
    4) 发布       publish_from_tokens.py（登录自适应 + 节奏打散 + 失败重试 + 回写去重档）

关键机制（见 docs/25-mixed-posting.md）：
  - 每个用户发帖数量随机（--min-posts ~ --max-posts），不形成固定规则。
  - 帖类型 T=文本 / I=图文 / Q=问题（提问式文本）交错，保证非全同类。
  - 语言按用户单语分配（--langs 轮流），用户内不混语。
  - 两级去重（web3 归一化标题 / 图库 slug），只有真正发成功的内容回写去重档。

用法：
    py -3 scripts/run_mixed.py --accounts-csv accounts.csv \
        --langs zh_hant,en,ja,ms --min-posts 3 --max-posts 7

    # 只产素材、不发布（预演）
    py -3 scripts/run_mixed.py --accounts-csv accounts.csv --skip-publish

    # 无人值守
    py -3 scripts/run_mixed.py --accounts-csv accounts.csv --yes
"""
from __future__ import annotations
import argparse, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]
WEB3_ALL = "techflow,web3bbs,foresight,menews,web3caff,panews,bingx,blockweeks,wublock"


def _run(cmd):
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="One-command mixed/interleaved publisher (randomized counts).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--accounts-csv", required=True)
    # fetch
    ap.add_argument("--web3-sources", default=WEB3_ALL)
    ap.add_argument("--per-site", type=int, default=12, help="每个 web3 源取多少条")
    ap.add_argument("--img-sources", default="opennana,openprompts,lovimg")
    ap.add_argument("--img-theme", default="beauty")
    ap.add_argument("--img-limit", type=int, default=80)
    ap.add_argument("--web3-dedupe", default="state/seen_web3.json")
    ap.add_argument("--img-dedupe", default="data/used_slugs.json")
    # assemble
    ap.add_argument("--langs", default="zh_hant,en,ja,ms")
    ap.add_argument("--min-posts", type=int, default=3)
    ap.add_argument("--max-posts", type=int, default=7)
    ap.add_argument("--seed", type=int, default=None)
    # publish
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--post-delay-min", type=float, default=0.3)
    ap.add_argument("--post-delay-max", type=float, default=1.5)
    ap.add_argument("--tokens", default="result/tokens_mixed.json")
    # control
    ap.add_argument("--workdir", default="web3_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    text_csv = wd / f"text_raw_{ts}.csv"
    img_csv = wd / f"img_raw_{ts}.csv"
    moments = wd / f"moments_mixed_{ts}.csv"

    # ---- Step 1: fetch text (web3) ----
    print("\n=== Step 1/4: 采集 web3 文本资讯（带去重）===")
    if _run(PY + [str(HERE / "fetch_web3.py"), "--sources", args.web3_sources,
                  "--per-site", str(args.per_site), "--tag", "web3",
                  "--dedupe-file", args.web3_dedupe, "--output", str(text_csv)]) != 0:
        print("[run_mixed] 文本采集失败", file=sys.stderr); return 1

    # ---- Step 2: fetch images ----
    print("\n=== Step 2/4: 采集图库图文（带 slug 去重）===")
    if _run(PY + [str(HERE / "multi_source_fetch.py"), "--sources", args.img_sources,
                  "--theme", args.img_theme, "--exclude-ads", "--limit", str(args.img_limit),
                  "--dedupe-file", args.img_dedupe, "--output", str(img_csv), "--shuffle"]) != 0:
        print("[run_mixed] 图文采集失败", file=sys.stderr); return 1

    # ---- Step 3: assemble mixed ----
    print("\n=== Step 3/4: 组装混合交错素材（随机帖数 + T/I/Q 交错）===")
    asm = PY + [str(HERE / "assemble_mixed.py"), "--accounts-csv", args.accounts_csv,
                "--text-csv", str(text_csv), "--image-csv", str(img_csv),
                "--langs", args.langs, "--min-posts", str(args.min_posts),
                "--max-posts", str(args.max_posts), "--output", str(moments)]
    if args.seed is not None:
        asm += ["--seed", str(args.seed)]
    if _run(asm) != 0 or not moments.exists():
        print("[run_mixed] 组装失败", file=sys.stderr); return 1

    if args.skip_publish:
        print("\n[run_mixed] --skip-publish，仅产素材：", moments); return 0

    # ---- Step 4: publish ----
    print("\n=== Step 4/4: 发布（登录自适应 + 节奏打散 + 失败重试 + 回写去重）===")
    if not args.yes:
        if input("  确认发布真实帖子？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[run_mixed] 已取消。素材已保存：", moments); return 0
    pub = PY + [str(HERE / "publish_from_tokens.py"), "--accounts-csv", args.accounts_csv,
                "--csv", str(moments), "--concurrency", str(args.concurrency),
                "--adaptive-login",
                "--post-delay-min", str(args.post_delay_min),
                "--post-delay-max", str(args.post_delay_max),
                "--record-dedupe",
                "--web3-dedupe-file", args.web3_dedupe,
                "--img-dedupe-file", args.img_dedupe,
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(pub)
    if rc != 0:
        print("[run_mixed] 发布返回非零，查看 result/ 报告。", file=sys.stderr); return rc
    print("\n[run_mixed] 完成。报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
