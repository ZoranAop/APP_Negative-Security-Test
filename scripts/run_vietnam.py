#!/usr/bin/env python3
"""
run_vietnam.py — Vietnam life content one-command publisher
(fetch → Vietnamese caption → publish)

Workflow:
    1) Fetch    fetch_vn_life.py (baomoi/tuoitre/vietnamnews/timeout/saigoneer)
               or fetch_stock_my.py --query vietnam (Pexels/Pixabay stock)
    2) Caption  caption_multilang.py --langs vi (Vietnamese language)
    3) Publish  publish_from_tokens.py (no bottom crop — editorial photos)

Usage examples:
    # Default: lifestyle articles from 5 VN sites, 5 accounts, 10 posts, Vietnamese
    py -3 scripts/run_vietnam.py --accounts-csv accounts_5.csv --posts 10

    # Stock photos (Pexels + Pixabay, requires Playwright)
    py -3 scripts/run_vietnam.py --source stock --accounts-csv accounts_10.csv --posts 50

    # Only fetch + caption, no publish (dry run)
    py -3 scripts/run_vietnam.py --posts 5 --skip-publish

    # Skip confirmation (unattended)
    py -3 scripts/run_vietnam.py --accounts-csv accounts_5.csv --posts 10 --yes
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
        description="Vietnam life one-command publisher (fetch → VI caption → publish)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    PY = [sys.executable]
    ap.add_argument("--source", choices=["life", "stock"], default="life",
                    help="Source: life (baomoi/tuoitre/vietnamnews/timeout/saigoneer) / stock (Pexels+Pixabay)")
    ap.add_argument("--accounts-csv", default="accounts_5.csv",
                    help="Accounts CSV (local, not committed)")
    ap.add_argument("--posts", type=int, default=10,
                    help="Number of posts to publish (= articles to fetch)")
    # life source options
    ap.add_argument("--vn-sources", default="baomoi,tuoitre,vietnamnews,timeout,saigoneer",
                    help="[life] Comma-separated site sources")
    ap.add_argument("--imgs-per-post", type=int, default=9,
                    help="Max images per post")
    ap.add_argument("--min-imgs", type=int, default=2,
                    help="Min images for article to qualify")
    # stock options
    ap.add_argument("--stock-sources", default="pexels,pixabay")
    ap.add_argument("--query", default="vietnam",
                    help="[stock] Search keyword")
    ap.add_argument("--per-source", type=int, default=30,
                    help="[stock] Max images per stock source")
    # dedupe
    ap.add_argument("--dedupe-file", default=None,
                    help="Dedupe file path (default: auto state/seen_vn_<source>.json)")
    ap.add_argument("--reset-dedupe", action="store_true",
                    help="Clear dedupe records and re-fetch")
    # caption
    ap.add_argument("--langs", default="vi",
                    help="Caption language (vi for Vietnamese)")
    ap.add_argument("--default-scene", default="travel",
                    help="Default scene hint for captions")
    # publish
    ap.add_argument("--concurrency", type=int, default=3,
                    help="Publish concurrency")
    ap.add_argument("--tokens", default="result/tokens.json",
                    help="Token cache file")
    # Vietnam: no crop by default (editorial photos without watermarks)
    ap.add_argument("--crop", action="store_true",
                    help="Enable bottom watermark cropping (default: off)")
    ap.add_argument("--crop-pct", default="0.08",
                    help="Crop percentage if --crop enabled")
    # control
    ap.add_argument("--workdir", default="vn_run",
                    help="Working directory for intermediate files")
    ap.add_argument("--skip-publish", action="store_true",
                    help="Only fetch + caption, no publish")
    ap.add_argument("--yes", action="store_true",
                    help="Skip publish confirmation")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    raw = wd / f"{args.source}_raw_{ts}.csv"
    moments = wd / f"moments_{args.source}_{ts}.csv"

    print(f"[run_vietnam] source={args.source} posts={args.posts} langs={args.langs}")
    print(f"[run_vietnam] raw={raw.name}  moments={moments.name}")

    # ---- Step 1: Fetch ----
    print("\n=== Step 1/3: Fetch ===")
    state_dir = ROOT / "state"
    state_dir.mkdir(exist_ok=True)
    default_dd = {
        "life": state_dir / "seen_vn_life.json",
        "stock": state_dir / "seen_vn_stock.json",
    }[args.source]
    dedupe_path = (ROOT / args.dedupe_file) if args.dedupe_file else default_dd
    if args.reset_dedupe and dedupe_path.exists():
        dedupe_path.unlink()
        print(f"[run_vietnam] Reset dedupe: {dedupe_path.name}")
    print(f"[run_vietnam] Dedupe file: {dedupe_path}")

    if args.source == "life":
        cmd = PY + [str(HERE / "fetch_vn_life.py"),
                    "--sources", args.vn_sources,
                    "--posts", str(args.posts),
                    "--imgs-per-post", str(args.imgs_per_post),
                    "--min-imgs", str(args.min_imgs),
                    "--dedupe-file", str(dedupe_path),
                    "--output", str(raw)]
    else:  # stock
        cmd = PY + [str(HERE / "fetch_stock_my.py"),
                    "--sources", args.stock_sources,
                    "--query", args.query,
                    "--per-source", str(args.per_source),
                    "--dedupe-file", str(dedupe_path),
                    "--output", str(raw)]

    if _run(cmd) != 0 or not raw.exists():
        print("[run_vietnam] Fetch failed.", file=sys.stderr)
        return 1

    # ---- Step 2: Vietnamese caption ----
    print("\n=== Step 2/3: Vietnamese caption ===")
    cmd = PY + [str(HERE / "caption_multilang.py"),
                "--input", str(raw), "--output", str(moments),
                "--langs", args.langs]
    if _run(cmd, env_extra={"DEFAULT_SCENE": args.default_scene}) != 0 or not moments.exists():
        print("[run_vietnam] Caption rewrite failed.", file=sys.stderr)
        return 1

    # Count rows
    import csv as _csv
    rows = list(_csv.DictReader(moments.open(encoding="utf-8-sig")))
    print(f"[run_vietnam] Moments ready: {len(rows)} posts")

    if args.skip_publish:
        print(f"\n[run_vietnam] --skip-publish set. Material saved: {moments}")
        return 0

    # ---- Step 3: Publish (no crop by default) ----
    print("\n=== Step 3/3: Publish ===")
    acc = ROOT / args.accounts_csv
    if not acc.exists():
        print(f"[run_vietnam] Accounts CSV not found: {acc}", file=sys.stderr)
        return 2
    print(f"  Accounts CSV : {acc}")
    print(f"  Posts        : {len(rows)}  Concurrency: {args.concurrency}  "
          f"Crop: {'bottom ' + str(args.crop_pct) if args.crop else 'off'}")
    if not args.yes:
        ans = input("  Confirm publish? Enter y to continue: ").strip().lower()
        if ans not in ("y", "yes"):
            print("[run_vietnam] Cancelled. Material saved:", moments)
            return 0
    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc), "--csv", str(moments),
                "--concurrency", str(args.concurrency),
                "--tokens-in", str(ROOT / args.tokens),
                "--tokens-out", str(ROOT / args.tokens)]
    # Vietnam: no crop by default
    if args.crop:
        pub_env = {"POST_CROP_BOTTOM_PCT": str(args.crop_pct)}
    else:
        pub_env = {"POST_CROP_BOTTOM_HOSTS": ""}
    rc = _run(cmd, env_extra=pub_env)
    if rc != 0:
        print("[run_vietnam] Publish returned non-zero. Check logs and result/.", file=sys.stderr)
        return rc
    print("\n[run_vietnam] Done. Report: result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
