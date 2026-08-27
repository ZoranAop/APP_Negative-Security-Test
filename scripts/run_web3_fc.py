#!/usr/bin/env python3
"""
run_web3_fc.py — Web3 资讯一键发布（Firecrawl 增强版）

与 run_web3.py 的区别：
  1. 支持 --use-firecrawl 参数，优先用 Firecrawl Scrape 抓取新闻源
  2. 支持自定义 URL 列表（--urls-file），适合抓取 RSS/API 无法覆盖的网站
  3. 支持 --search 模式，用 Firecrawl Search 搜索最新 Web3 新闻
  4. 自动降级：Firecrawl 失败时回退到原有 fetchers

用法：
    # 使用 Firecrawl 抓取指定 URL 列表
    py -3 scripts/run_web3.py --use-firecrawl --urls-file scripts/urls_web3.txt \\
        --accounts-csv accounts_10.csv --per-site 5 --yes

    # 用 Firecrawl Search 搜索 crypto 新闻
    py -3 scripts/run_web3_fc.py --use-firecrawl --search "bitcoin crypto news" \\
        --limit 10 --accounts-csv accounts_10.csv --lang en --yes

    # 混合模式：原有源 + Firecrawl 补充
    py -3 scripts/run_web3_fc.py --sources techflow,foresight,wublock \\
        --urls-file scripts/urls_web3.txt --per-site 5 --yes
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]


def _get_fc_key() -> str | None:
    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if key:
        return key
    key_file = Path.home() / ".workbuddy" / "skills" / "firecrawl" / ".api_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return None


def _run(cmd, *, env_extra=None):
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _fetch_with_firecrawl(urls: list[str], tag: str, limit: int) -> list[dict]:
    """用 Firecrawl 抓取 URL 列表，返回结构化结果。"""
    urls_file = ROOT / "_tmp_urls.txt"
    urls_file.write_text("\n".join(urls[:limit]), encoding="utf-8")
    out_file = ROOT / "_tmp_fc_out.csv"
    cmd = PY + [str(HERE / "fetch_firecrawl.py"),
                "--urls-file", str(urls_file),
                "--tag", tag,
                "--output", str(out_file)]
    rc = subprocess.call(cmd, cwd=str(ROOT))
    urls_file.unlink(missing_ok=True)
    if rc != 0 or not out_file.exists():
        return []
    rows = list(csv.DictReader(out_file.open(encoding="utf-8-sig")))
    out_file.unlink(missing_ok=True)
    return [{"title": r["content"], "brief": r.get("_brief", ""), "site": r.get("_site", "")}
            for r in rows]


def _search_with_firecrawl(query: str, limit: int, tag: str) -> list[dict]:
    """用 Firecrawl Search 搜索新闻，返回结构化结果。"""
    out_file = ROOT / "_tmp_fc_search.csv"
    cmd = PY + [str(HERE / "fetch_firecrawl.py"),
                "--search", query,
                "--limit", str(limit),
                "--tag", tag,
                "--output", str(out_file)]
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0 or not out_file.exists():
        return []
    rows = list(csv.DictReader(out_file.open(encoding="utf-8-sig")))
    out_file.unlink(missing_ok=True)
    return [{"title": r["content"], "brief": r.get("_brief", ""), "site": r.get("_site", "")}
            for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Web3 news publisher with Firecrawl support",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_10.csv")
    # Firecrawl options
    ap.add_argument("--use-firecrawl", action="store_true",
                    help="Enable Firecrawl scraping mode")
    ap.add_argument("--urls-file", help="URL list file (one per line) for Firecrawl")
    ap.add_argument("--search", help="Search query for Firecrawl Search mode")
    ap.add_argument("--fc-limit", type=int, default=10, help="Max items from Firecrawl")
    # Original web3 options
    ap.add_argument("--sources", default="techflow,web3bbs,foresight,menews,web3caff,panews,bingx,blockweeks,wublock",
                    help="Comma-separated source keys (used when --use-firecrawl is off)")
    ap.add_argument("--per-site", type=int, default=10)
    ap.add_argument("--tag", default="web3")
    ap.add_argument("--dedupe-file", default=None)
    ap.add_argument("--reset-dedupe", action="store_true")
    # caption
    ap.add_argument("--lang", default="content",
                    choices=["content", "zh_hant", "en", "ja", "ms", "auto-nick", "mixed_en_ms"])
    ap.add_argument("--min-len", type=int, default=0)
    ap.add_argument("--max-len", type=int, default=280)
    ap.add_argument("--no-caption", action="store_true")
    ap.add_argument("--no-source", action="store_true")
    ap.add_argument("--tone", default="neutral",
                    choices=["neutral", "positive", "trader", "complain"])
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

    print(f"[run_web3_fc] mode={'firecrawl' if args.use_firecrawl else 'original'} "
          f"sources={args.sources} per-site={args.per_site} lang={args.lang}")

    # Check Firecrawl availability
    fc_key = _get_fc_key()
    if args.use_firecrawl and not fc_key:
        print("[warn] FIRECRAWL_API_KEY not found, falling back to original fetchers", file=sys.stderr)
        args.use_firecrawl = False

    # ---- Step 1: fetch ----
    print("\n=== Step 1/3: 多源采集 ===")
    state_dir = ROOT / "state"
    state_dir.mkdir(exist_ok=True)
    dedupe_path = (ROOT / args.dedupe_file) if args.dedupe_file else (state_dir / "seen_web3.json")
    if args.reset_dedupe and dedupe_path.exists():
        dedupe_path.unlink()
        print(f"[run_web3_fc] 已重置去重档：{dedupe_path.name}")
    print(f"[run_web3_fc] 去重档：{dedupe_path}")

    if args.use_firecrawl:
        # Firecrawl mode
        if args.search:
            print(f"[firecrawl] Searching: {args.search}", file=sys.stderr)
            fc_items = _search_with_firecrawl(args.search, args.fc_limit, args.tag)
            print(f"[firecrawl] Got {len(fc_items)} items from search", file=sys.stderr)
        elif args.urls_file:
            urls_path = Path(args.urls_file)
            if not urls_path.exists():
                print(f"[ERR] URLs file not found: {urls_path}", file=sys.stderr)
                return 1
            urls = [l.strip() for l in urls_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            print(f"[firecrawl] Scraping {len(urls)} URLs", file=sys.stderr)
            fc_items = _fetch_with_firecrawl(urls, args.tag, args.fc_limit)
            print(f"[firecrawl] Got {len(fc_items)} items", file=sys.stderr)
        else:
            print("[ERR] Need --urls-file or --search with --use-firecrawl", file=sys.stderr)
            return 1

        # Write Firecrawl results to CSV
        if fc_items:
            out = Path(args.output) if hasattr(args, 'output') else raw
            fields = ["content", "visibility", "room_id", "image_urls",
                      "location_name", "location_address", "location_lat", "location_lon",
                      "_source", "_site", "_tag", "_brief"]
            with out.open("w", newline="", encoding="utf-8-sig") as fh:
                w = csv.DictWriter(fh, fieldnames=fields)
                w.writeheader()
                for it in fc_items:
                    w.writerow({
                        "content": it["title"],
                        "visibility": 0,
                        "room_id": "",
                        "image_urls": "",
                        "location_name": "",
                        "location_address": "",
                        "location_lat": "",
                        "location_lon": "",
                        "_source": "firecrawl",
                        "_site": it["site"],
                        "_tag": args.tag,
                        "_brief": it["brief"],
                    })
            print(f"[firecrawl] Saved {len(fc_items)} items → {out}", file=sys.stderr)
        else:
            print("[warn] No items from Firecrawl, falling back to original fetchers", file=sys.stderr)
            args.use_firecrawl = False

    if not args.use_firecrawl:
        # Original fetchers
        cmd = PY + [str(HERE / "fetch_web3.py"),
                    "--sources", args.sources, "--per-site", str(args.per_site),
                    "--tag", args.tag, "--dedupe-file", str(dedupe_path),
                    "--output", str(raw)]
        if _run(cmd) != 0 or not raw.exists():
            print("[run_web3_fc] 采集失败，终止。", file=sys.stderr)
            return 1

    # ---- Step 2: caption ----
    if args.no_caption:
        moments = raw if not args.use_firecrawl else raw
        print("\n[run_web3_fc] --no-caption：直接用原标题发。")
    else:
        print("\n=== Step 2/3: 主体视角文案 ===")
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
            print("[run_web3_fc] 文案改写失败，终止。", file=sys.stderr)
            return 1

    import csv as _csv
    rows = list(_csv.DictReader(moments.open(encoding="utf-8-sig")))
    print(f"[run_web3_fc] moments ready: {len(rows)} 条（纯文本）")

    if args.skip_publish:
        print("\n[run_web3_fc] --skip-publish，仅产出素材：", moments)
        return 0

    # ---- Step 3: publish ----
    print("\n=== Step 3/3: 发布 ===")
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[run_web3_fc] 账号 CSV 不存在: {acc}", file=sys.stderr)
        return 2
    print(f"  账号 CSV : {acc}\n  素材条数 : {len(rows)}  并发: {args.concurrency}")
    if not args.yes:
        if input("  确认发布真实帖子？输入 y 继续：").strip().lower() not in ("y", "yes"):
            print("[run_web3_fc] 已取消。素材已保存：", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    rc = _run(cmd)
    if rc != 0:
        print("[run_web3_fc] 发布返回非零，请查看日志与 result/ 报告。", file=sys.stderr)
        return rc
    print("\n[run_web3_fc] 完成。发布报告见 result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
