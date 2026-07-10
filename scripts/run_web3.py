#!/usr/bin/env python3
"""
run_web3.py — Web3 资讯一键发布（多源采集 → 繁体中文/主体视角文案 → 纯文本发布）

把 Web3 资讯的三步串成一条命令：
    1) 采集   fetch_web3.py   （9 个 Web3 媒体，统一 web3 标签，纯文本）
    2) 文案   caption_multilang.py 或内置轻量改写（发帖人第一人称，可繁体）
    3) 发布   publish_from_tokens.py （纯文本帖，无图，media_info type=text）

支持来源（--sources）：
    techflow / web3bbs / foresight / menews / web3caff / panews / bingx / blockweeks / wublock

用法：
    # 默认：9 源各 10 条，10 账号轮询
    py -3 scripts/run_web3.py --accounts-csv accounts_10.csv --per-site 10

    # 指定来源与语言（繁体中文）
    py -3 scripts/run_web3.py --sources techflow,foresight,panews --langs zh_hant

    # 只采集+文案、不发布
    py -3 scripts/run_web3.py --skip-publish

去重：--dedupe-file（默认 state/seen_web3.json）跨批次记录已发消息，自动跳过、不重复。
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

ALL = "techflow,web3bbs,foresight,menews,web3caff,panews,bingx,blockweeks,wublock"


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
        description="Web3 news one-command publisher (multi-source → caption → text publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_10.csv")
    # fetch
    ap.add_argument("--sources", default=ALL, help="逗号分隔的来源 key（见 fetch_web3.py）")
    ap.add_argument("--per-site", type=int, default=10, help="每个来源取多少条")
    ap.add_argument("--tag", default="web3")
    ap.add_argument("--dedupe-file", default=None,
                    help="去重档（默认 state/seen_web3.json，跨批次防重复）")
    ap.add_argument("--reset-dedupe", action="store_true")
    # caption
    ap.add_argument("--langs", default="zh_hant", help="文案语言（默认繁体中文 zh_hant）")
    ap.add_argument("--default-scene", default="portrait")
    ap.add_argument("--no-caption", action="store_true",
                    help="不改写文案，直接用原标题发（默认会走 caption_multilang 改写）")
    # publish
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--tokens", default="result/tokens.json")
    # control
    ap.add_argument("--workdir", default="web3_run")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw = wd / f"web3_raw_{ts}.csv"
    moments = wd / f"moments_web3_{ts}.csv"

    print(f"[run_web3] sources={args.sources} per-site={args.per_site} langs={args.langs}")

    # ---- Step 1: fetch ----
    print("\n=== Step 1/3: 多源采集（9 个 Web3 媒体，web3 标签，纯文本）===")
    state_dir = ROOT / "state"
    state_dir.mkdir(exist_ok=True)
    dedupe_path = (ROOT / args.dedupe_file) if args.dedupe_file else (state_dir / "seen_web3.json")
    if args.reset_dedupe and dedupe_path.exists():
        dedupe_path.unlink()
        print(f"[run_web3] 已重置去重档：{dedupe_path.name}")
    print(f"[run_web3] 去重档：{dedupe_path}（自动跳过已发过的消息）")

    cmd = PY + [str(HERE / "fetch_web3.py"),
                "--sources", args.sources, "--per-site", str(args.per_site),
                "--tag", args.tag, "--dedupe-file", str(dedupe_path),
                "--output", str(raw)]
    if _run(cmd) != 0 or not raw.exists():
        print("[run_web3] 采集失败，终止。", file=sys.stderr)
        return 1

    # ---- Step 2: caption ----
    if args.no_caption:
        moments = raw
        print("\n[run_web3] --no-caption：直接用原标题发。")
    else:
        print("\n=== Step 2/3: 主体视角文案 ===")
        cmd = PY + [str(HERE / "caption_multilang.py"),
                    "--input", str(raw), "--output", str(moments), "--langs", args.langs]
        if _run(cmd, env_extra={"DEFAULT_SCENE": args.default_scene}) != 0 or not moments.exists():
            print("[run_web3] 文案改写失败，终止。", file=sys.stderr)
            return 1

    import csv as _csv
    rows = list(_csv.DictReader(moments.open(encoding="utf-8-sig")))
    print(f"[run_web3] moments ready: {len(rows)} 条（纯文本）")

    if args.skip_publish:
        print("\n[run_web3] --skip-publish，仅产出素材：", moments)
        return 0

    # ---- Step 3: publish (text-only) ----
    print("\n=== Step 3/3: 发布（纯文本，media_info type=text）===")
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[run_web3] 账号 CSV 不存在: {acc}", file=sys.stderr)
        return 2
    print(f"  账号 CSV : {acc}\n  素材条数 : {len(rows)}  并发: {args.concurrency}")
    if not args.yes:
        if input("  确认发布真实帖子？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[run_web3] 已取消。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print("[run_web3] 发布返回非零，请查看日志与 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[run_web3] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
