#!/usr/bin/env python3
"""
run_web3.py — Web3 资讯一键发布（多源采集 → 语言统一化文案 → 纯文本发布）

把 Web3 资讯的三步串成一条命令：
    1) 采集   fetch_web3.py   （9 个 Web3 媒体，统一 web3 标签，纯文本）
    2) 文案   web3_caption_by_role.py（语言统一化：整条帖子保证同一语言）
    3) 发布   publish_from_tokens.py （纯文本帖，无图，media_info type=text）

语言统一化说明（--lang 参数）：
    content      按采集内容语言自动判断（中文标题→繁中帖，英文标题→英文帖）
    zh_hant      全部繁体中文
    en           全部英文
    ms           全部马来语
    ja           全部日文
    mixed_en_ms  50%英文 + 50%马来语交替（推荐：整条帖子语言统一，不夹杂中文）
    auto-nick    按账号昵称语言判断（旧逻辑）

用法：
    # 50% 英文 + 50% 马来语，150-300 字符
    py -3 scripts/run_web3.py --accounts-csv accounts_20.csv --lang mixed_en_ms \\
        --min-len 150 --max-len 300 --yes

    # 全部繁体中文（默认）
    py -3 scripts/run_web3.py --accounts-csv accounts_10.csv --per-site 10

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
    ap.add_argument("--lang", default="content",
                    choices=["content", "zh_hant", "en", "ja", "ms", "auto-nick", "mixed_en_ms"],
                    help="文案语言策略：content=按采集内容语言自动判断，"
                         "zh_hant/en/ja/ms=强制统一，mixed_en_ms=50%%英文+50%%马来语，"
                         "auto-nick=按昵称判断。默认 content。")
    ap.add_argument("--min-len", type=int, default=0, help="文案最小字符数")
    ap.add_argument("--max-len", type=int, default=280, help="文案最大字符数")
    ap.add_argument("--no-caption", action="store_true",
                    help="不改写文案，直接用原标题发（默认会走 web3_caption_by_role 改写）")
    ap.add_argument("--no-source", action="store_true",
                    help="不带信息来源：不追加来源标签，并清洗摘要里的媒体/作者等来源痕迹")
    ap.add_argument("--tone", default="neutral",
                    choices=["neutral", "positive", "trader", "complain"],
                    help="点评口吻：neutral=中性，positive=正向，trader=收益感慨，"
                         "complain=对坏消息的抱怨（负面意图生效）")
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

    print(f"[run_web3] sources={args.sources} per-site={args.per_site} lang={args.lang}")

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
        print("\n=== Step 2/3: 主体视角文案（web3_caption_by_role）===")
        cmd = PY + [str(HERE / "web3_caption_by_role.py"),
                    "--input", str(raw), "--output", str(moments),
                    "--accounts-csv", str(ROOT / args.accounts_csv),
                    "--lang", args.lang,
                    "--min-len", str(args.min_len),
                    "--max-len", str(args.max_len),
                    "--tone", args.tone]
        if args.no_source:
            cmd.append("--no-source")
        if _run(cmd) != 0 or not moments.exists():
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
