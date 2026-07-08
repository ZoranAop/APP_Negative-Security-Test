#!/usr/bin/env python3
"""
multi_source_fetch.py — Aggregate materials from multiple prompt-gallery sites
into a single moments CSV, with shared theme / ad filters and a shared
dedupe list.

Sources
    opennana         (via scripts/opennana_fetch.py helpers)
    openprompts      (via scripts/fetch_openprompts.py helpers)
    lovimg           (via scripts/fetch_lovimg.py helpers)

Typical usage
    py -3 scripts/multi_source_fetch.py \\
        --sources opennana,openprompts,lovimg \\
        --theme beauty \\
        --exclude-ads \\
        --dedupe-file data/used_slugs.json \\
        --limit 100 \\
        --output moments.csv

CSV columns are identical to opennana_fetch: post_moments.py consumes it directly.

See docs/12-multi-source.md for the rationale and per-source quirks.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

# We deliberately import from the sibling modules — they live in the same folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from opennana_fetch import (  # noqa: E402
    iter_rows as opennana_iter_rows,
)
from fetch_openprompts import (  # noqa: E402
    iter_rows as openprompts_iter_rows,
)
from fetch_lovimg import (  # noqa: E402
    fetch as lovimg_fetch,
    build_caption as lovimg_caption,
)


def _load_dedupe(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        return set()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, list):
            return {str(x) for x in d}
        if isinstance(d, dict) and "slugs" in d:
            return {str(x) for x in d["slugs"]}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] dedupe read {path}: {e}", file=sys.stderr)
    return set()


def _save_dedupe(path: str | None, seen: set[str]) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Aggregate materials from multiple gallery sites → CSV",
    )
    ap.add_argument("--sources", default="opennana,openprompts,lovimg",
                    help="comma-separated sources to draw from")
    ap.add_argument("--theme", default="beauty",
                    help="beauty / portrait / sport / travel / food / all")
    ap.add_argument("--model", default=None,
                    help="optional opennana/openprompts model filter")
    ap.add_argument("--exclude-ads", action="store_true", default=True,
                    help="apply the shared ad filter to every source (default: on)")
    ap.add_argument("--include-ads", dest="exclude_ads", action="store_false",
                    help="disable ad filter")
    ap.add_argument("--limit", type=int, default=100,
                    help="total rows in output CSV")
    ap.add_argument("--dedupe-file", default=None,
                    help="JSON of already-used slugs; new picks are merged back in")
    ap.add_argument("--output", required=True)
    # per-source page budgets
    ap.add_argument("--opennana-pages", type=int, default=8)
    ap.add_argument("--openprompts-pages", type=int, default=3)
    ap.add_argument("--lovimg-max-pages", type=int, default=15)
    ap.add_argument("--shuffle", action="store_true",
                    help="shuffle final rows for a more mixed feed")
    ap.add_argument("--source-weights", default="",
                    help="optional per-source share overrides, e.g. "
                         "'opennana=40,openprompts=40,lovimg=20' (sum must ≤ limit)")
    args = ap.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    seen = _load_dedupe(args.dedupe_file)
    picked_slugs: set[str] = set()

    # Compute per-source budget
    budget: dict[str, int] = {s: 0 for s in sources}
    if args.source_weights:
        for chunk in args.source_weights.split(","):
            k, _, v = chunk.strip().partition("=")
            if k in budget:
                try:
                    budget[k] = int(v)
                except ValueError:
                    pass
    if sum(budget.values()) == 0:
        # Even split (rounding remainder toward the first source)
        base, rem = divmod(args.limit, len(sources))
        for i, s in enumerate(sources):
            budget[s] = base + (1 if i < rem else 0)

    print(f"[Plan] sources={sources}, theme={args.theme}, "
          f"exclude_ads={args.exclude_ads}, budget={budget}", file=sys.stderr)

    rows: list[dict] = []

    for src in sources:
        if len(rows) >= args.limit:
            break
        want = min(budget.get(src, 0), args.limit - len(rows))
        if want <= 0:
            continue
        print(f"[{src}] want={want}", file=sys.stderr)

        if src == "opennana":
            pages = range(1, 1 + args.opennana_pages)
            new_rows = list(opennana_iter_rows(
                "image", pages, want,
                model=args.model, theme=args.theme,
                exclude_ads=args.exclude_ads,
                seen_slugs=seen, fetched_slugs=picked_slugs,
                shuffle_pages=True,
            ))
            for r in new_rows:
                r["_source"] = "opennana"
                rows.append(r)
        elif src == "openprompts":
            pages = range(1, 1 + args.openprompts_pages)
            new_rows = list(openprompts_iter_rows(
                pages, want,
                model=args.model, theme=args.theme,
                exclude_ads=args.exclude_ads,
                seen_slugs=seen, fetched_slugs=picked_slugs,
            ))
            for r in new_rows:
                r["_source"] = "openprompts"
                rows.append(r)
        elif src == "lovimg":
            items = lovimg_fetch(
                "people-characters",
                max_pages=args.lovimg_max_pages,
                limit=want,
                theme=args.theme,
                exclude_ads=args.exclude_ads,
                seen_slugs=seen, fetched_slugs=picked_slugs,
            )
            for it in items:
                rows.append({
                    "content": lovimg_caption(it),
                    "visibility": 0,
                    "room_id": "",
                    "image_urls": ",".join(it["images"][:9]),
                    "location_name": "",
                    "location_address": "",
                    "location_lat": "",
                    "location_lon": "",
                    "_source": "lovimg",
                })
        else:
            print(f"[warn] unknown source: {src}", file=sys.stderr)

    if not rows:
        print("[warn] no rows produced", file=sys.stderr)
        return 1

    if args.shuffle:
        random.shuffle(rows)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})

    _save_dedupe(args.dedupe_file, seen)

    # Report distribution
    from collections import Counter
    dist = Counter(r.get("_source", "?") for r in rows)
    print(f"[OK] wrote {len(rows)} rows → {out}", file=sys.stderr)
    print(f"[OK] source distribution: {dict(dist)}", file=sys.stderr)
    if args.dedupe_file:
        print(f"[OK] dedupe file → {args.dedupe_file} ({len(seen)} slugs)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
