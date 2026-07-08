#!/usr/bin/env python3
"""
record_sent_slugs.py — Merge already-sent OpenNana prompt slugs into a dedupe
JSON file so that the *next* ``opennana_fetch.py`` / ``multi_source_fetch.py``
run (invoked with ``--dedupe-file``) will skip images that have already been
published.

Why this exists
    ``opennana_fetch.py`` records slugs into the dedupe file at *fetch* time.
    But in the recommended pipeline we usually rewrite the captions by hand
    into a separate ``moments.csv`` before publishing, and only a subset of the
    fetched rows may actually get posted. This helper lets you record exactly
    the slugs you *did* send, keyed by OpenNana slug, right after publishing.

Sources of slugs (any combination)
    --from-csv PATH     read the ``_slug`` column of a fetch CSV
                        (``opennana_fetch.py`` writes this column).
    --slugs A B C       explicit slugs on the command line.

The dedupe file is a JSON array of slug strings (the same format
``opennana_fetch.py --dedupe-file`` reads and writes). New slugs are merged in;
existing ones are preserved; the result is sorted and de-duplicated.

Examples
    # After publishing moments that came from a fetch CSV:
    py -3 scripts/record_sent_slugs.py \
        --from-csv result/moments_fetched.csv \
        --dedupe-file data/used_slugs.json

    # Or record specific slugs manually:
    py -3 scripts/record_sent_slugs.py \
        --slugs elegant-red-hanfu-... tang-dynasty-noble-woman-... \
        --dedupe-file data/used_slugs.json

Then next time fetch with the same dedupe file to avoid re-sending:
    py -3 scripts/opennana_fetch.py --media-type image --theme beauty \
        --exclude-ads --limit 25 \
        --dedupe-file data/used_slugs.json \
        --output result/moments_next.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


def load_dedupe(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] cannot parse {path}: {e}", file=sys.stderr)
        return set()
    if isinstance(data, list):
        return {str(x) for x in data}
    if isinstance(data, dict) and "slugs" in data:
        return {str(x) for x in data["slugs"]}
    return set()


def save_dedupe(path: Path, slugs: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sorted(slugs), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def slugs_from_csv(csv_path: Path, column: str) -> set[str]:
    out: set[str] = set()
    # utf-8-sig so we tolerate the BOM opennana_fetch.py writes.
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if column not in (reader.fieldnames or []):
            print(
                f"[warn] column '{column}' not found in {csv_path} "
                f"(has: {reader.fieldnames}); no slugs read from CSV",
                file=sys.stderr,
            )
            return out
        for row in reader:
            val = (row.get(column) or "").strip()
            if val:
                out.add(val)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge already-sent OpenNana slugs into a dedupe JSON file"
    )
    ap.add_argument(
        "--dedupe-file",
        required=True,
        help="JSON array of used slugs to update (created if missing)",
    )
    ap.add_argument(
        "--from-csv",
        action="append",
        default=[],
        help="fetch CSV to read slugs from (repeatable); uses the _slug column",
    )
    ap.add_argument(
        "--slug-column",
        default="_slug",
        help="CSV column holding the slug (default: _slug)",
    )
    ap.add_argument(
        "--slugs",
        nargs="*",
        default=[],
        help="explicit slugs to add",
    )
    args = ap.parse_args()

    dedupe_path = Path(args.dedupe_file)
    existing = load_dedupe(dedupe_path)
    before = len(existing)

    new_slugs: set[str] = set()
    for csv_file in args.from_csv:
        p = Path(csv_file)
        if not p.exists():
            print(f"[warn] CSV not found: {p}", file=sys.stderr)
            continue
        got = slugs_from_csv(p, args.slug_column)
        print(f"[csv] {p}: {len(got)} slug(s)")
        new_slugs |= got

    if args.slugs:
        cli = {s.strip() for s in args.slugs if s.strip()}
        print(f"[cli] {len(cli)} slug(s)")
        new_slugs |= cli

    if not new_slugs:
        print("[warn] no new slugs provided (use --from-csv and/or --slugs)",
              file=sys.stderr)
        return 1

    merged = existing | new_slugs
    added = len(merged) - before
    save_dedupe(dedupe_path, merged)

    print(f"[OK] dedupe file {dedupe_path}: {before} -> {len(merged)} slugs "
          f"(+{added} new)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
