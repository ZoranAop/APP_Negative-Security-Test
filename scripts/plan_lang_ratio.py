#!/usr/bin/env python3
"""
plan_lang_ratio.py — Assign a ``_lang`` column to a moments CSV by an *exact*
target ratio, instead of the even round-robin split that
``caption_multilang.py`` does by default.

Motivating requirement (real batch spec)
    "繁体中文(台湾) / 日文 / 英文 三语，英文+日文 合计 80%，繁中 20%，
     英/日在 80% 内随机拆分，不要简体中文。"

This script computes exact integer quotas per language for N rows and writes
them into ``_lang`` (shuffled, deterministic with --seed). Downstream,
run ``caption_multilang.py --use-existing-lang`` so the ratio is preserved
when captions are generated.

Ratio spec
    --minor-lang / --minor-ratio   the small slice (default: zh_hant = 0.20)
    --major-langs                  the languages that share the rest
                                   (default: en,ja  → together 0.80)
    --major-split                  how the major slice is divided, e.g.
                                   "en=0.375,ja=0.625" (of the WHOLE file that
                                   is 30% / 50%). If omitted, the major slice is
                                   split *randomly* per --seed.

Guards
    - refuses ``zh`` (Simplified Chinese) unless --allow-simplified is passed,
      matching the "不要简体中文" rule.
    - quotas always sum to N exactly (largest-remainder rounding).

Output
    same CSV schema + ``_lang`` column. Prints the realised distribution and a
    PASS/FAIL check against the requested ratio tolerance.

See docs/13-multilang-captions.md §13.5 and docs/14-tophub-source.md §14.5.
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

SUPPORTED_LANGS = {"en", "zh", "zh_hant", "ja"}


def _largest_remainder(total: int, weights: dict[str, float]) -> dict[str, int]:
    """Apportion `total` across keys by `weights`, summing exactly to total."""
    s = sum(weights.values())
    if s <= 0:
        raise ValueError("weights must sum to > 0")
    raw = {k: total * (w / s) for k, w in weights.items()}
    floor = {k: int(v) for k, v in raw.items()}
    remainder = total - sum(floor.values())
    # hand out the remaining units to the largest fractional parts
    order = sorted(weights.keys(), key=lambda k: raw[k] - floor[k], reverse=True)
    for k in order[:remainder]:
        floor[k] += 1
    return floor


def build_plan(
    n: int,
    *,
    minor_lang: str,
    minor_ratio: float,
    major_langs: list[str],
    major_split: dict[str, float] | None,
    seed: int,
) -> list[str]:
    rng = random.Random(seed)

    minor_count = round(n * minor_ratio)
    minor_count = max(0, min(minor_count, n))
    major_total = n - minor_count

    if major_split is None:
        # random split of the major slice across major_langs (per seed)
        cuts = sorted(rng.random() for _ in range(len(major_langs) - 1))
        bounds = [0.0, *cuts, 1.0]
        weights = {lg: bounds[i + 1] - bounds[i] for i, lg in enumerate(major_langs)}
        # avoid a zero weight
        weights = {k: (v if v > 0 else 1e-6) for k, v in weights.items()}
    else:
        weights = {lg: major_split.get(lg, 0.0) for lg in major_langs}

    major_counts = _largest_remainder(major_total, weights) if major_total else {lg: 0 for lg in major_langs}

    plan: list[str] = [minor_lang] * minor_count
    for lg, c in major_counts.items():
        plan.extend([lg] * c)
    assert len(plan) == n, (len(plan), n)
    rng.shuffle(plan)
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assign _lang to a moments CSV by an exact target ratio",
    )
    ap.add_argument("--input", required=True, help="input moments CSV")
    ap.add_argument("--output", required=True, help="output CSV with _lang column")
    ap.add_argument("--minor-lang", default="zh_hant",
                    help="the small-slice language (default: zh_hant)")
    ap.add_argument("--minor-ratio", type=float, default=0.20,
                    help="share of the small slice (default: 0.20)")
    ap.add_argument("--major-langs", default="en,ja",
                    help="comma list sharing the remaining slice (default: en,ja)")
    ap.add_argument("--major-split", default="",
                    help='optional fixed split of the WHOLE file across major '
                         'langs, e.g. "en=0.30,ja=0.50"; omit for random split')
    ap.add_argument("--allow-simplified", action="store_true",
                    help="permit zh (Simplified); default forbids it")
    ap.add_argument("--tolerance", type=float, default=0.02,
                    help="max abs deviation for the ratio PASS check (default 0.02)")
    ap.add_argument("--seed", type=int, default=20260703)
    args = ap.parse_args()

    minor = args.minor_lang.strip()
    majors = [l.strip() for l in args.major_langs.split(",") if l.strip()]
    all_langs = [minor, *majors]

    unknown = [l for l in all_langs if l not in SUPPORTED_LANGS]
    if unknown:
        print(f"[error] unknown languages: {unknown}. supported: {sorted(SUPPORTED_LANGS)}",
              file=sys.stderr)
        return 2
    if not args.allow_simplified and "zh" in all_langs:
        print("[error] 'zh' (Simplified Chinese) is not allowed; pass --allow-simplified "
              "to override (spec: 不要简体中文)", file=sys.stderr)
        return 2

    major_split: dict[str, float] | None = None
    if args.major_split.strip():
        major_split = {}
        for chunk in args.major_split.split(","):
            k, _, v = chunk.strip().partition("=")
            k = k.strip()
            if k in majors:
                try:
                    major_split[k] = float(v)
                except ValueError:
                    print(f"[error] bad --major-split value: {chunk!r}", file=sys.stderr)
                    return 2

    with Path(args.input).open("r", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        print("[warn] input CSV has no rows", file=sys.stderr)
        return 1

    n = len(rows)
    plan = build_plan(
        n,
        minor_lang=minor, minor_ratio=args.minor_ratio,
        major_langs=majors, major_split=major_split, seed=args.seed,
    )

    fields = list(rows[0].keys())
    if "_lang" not in fields:
        fields.append("_lang")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for i, row in enumerate(rows):
            row["_lang"] = plan[i]
            w.writerow(row)

    stats = Counter(plan)
    major_share = sum(stats[l] for l in majors) / n
    minor_share = stats[minor] / n
    print(f"[OK] wrote {n} rows → {out}")
    print(f"[OK] distribution: {dict(stats)}")
    print(f"[OK] major({'+'.join(majors)}) = {sum(stats[l] for l in majors)} "
          f"({major_share:.0%}) | minor({minor}) = {stats[minor]} ({minor_share:.0%})")

    target_major = 1.0 - args.minor_ratio
    ok = (abs(major_share - target_major) <= args.tolerance
          and abs(minor_share - args.minor_ratio) <= args.tolerance)
    print(f"[{'PASS' if ok else 'FAIL'}] ratio check "
          f"(target major={target_major:.0%}±{args.tolerance:.0%})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
