#!/usr/bin/env python3
"""
run_web3_repost_prompt391.py — Repost prompt-391 with new caption for account u_6l6gx9ba.
New caption: first-person selfie-style, no reference to "Prompt 391".
"""
from __future__ import annotations

import argparse, csv, io, json, subprocess, sys, time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

ACCOUNTS_CSV = ROOT / "accounts_web3_100.csv"
TOKENS_PATH = ROOT / "result" / "tokens.json"
DEDUPE_SLUGS = ROOT / "state" / "seen_opennana_web3_5.json"

# The account to repost for
TARGET_EMAIL = "u_6l6gx9ba@xxai.com"
SLUG = "prompt-391"
IMAGE_URL = "https://img.opennana.com/prompts/images/391.jpeg"

# New caption: first-person selfie voice, no prompt references
NEW_CAPTION = (
    "Caught this moment tonight and I have to share it. "
    "The flash lighting makes everything feel so raw and real — "
    "this is the kind of shot I live for."
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    # Remove old dedupe entry
    if DEDUPE_SLUGS.exists():
        try:
            data = json.loads(DEDUPE_SLUGS.read_text(encoding="utf-8"))
            if SLUG in data:
                data.remove(SLUG)
                DEDUPE_SLUGS.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                print(f"[dedupe] removed {SLUG}")
        except Exception:
            pass

    # Find target account
    accounts = list(csv.DictReader(open(ACCOUNTS_CSV, encoding="utf-8-sig")))
    keys = list(accounts[0].keys())
    target = None
    for a in accounts:
        if a.get(keys[2], "").strip().lower() == TARGET_EMAIL:
            target = a
            break
    if not target:
        print(f"[ERROR] account {TARGET_EMAIL} not found", file=sys.stderr)
        return 1

    print(f"[account] {target.get(keys[1], '?')} ({TARGET_EMAIL})")
    print(f"[image] {IMAGE_URL}")
    print(f"[caption] {NEW_CAPTION}")

    # Write moments CSV
    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / "web3_repost_run"
    wd.mkdir(parents=True, exist_ok=True)
    moments_csv = wd / f"moments_repost_{ts}.csv"
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_lang", "_source", "_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerow({
            "content": NEW_CAPTION,
            "visibility": "0", "room_id": "",
            "image_urls": IMAGE_URL,
            "location_name": "", "location_address": "", "location_lat": "", "location_lon": "",
            "_lang": "en", "_source": "opennana",
            "_dedupe_key": f"onana:{SLUG}",
        })

    # Write accounts CSV
    acc_csv = wd / f"accounts_repost_{ts}.csv"
    with acc_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号", "昵称", "邮箱", "密码"])
        w.writeheader()
        w.writerow({
            "序号": target.get(keys[0], ""),
            "昵称": target.get(keys[1], ""),
            "邮箱": target.get(keys[2], ""),
            "密码": target.get(keys[3], ""),
        })

    if not args.yes:
        if input("\n  Confirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_csv),
                "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "2.0",
                "--record-dedupe",
                "--web3-dedupe-file", str(DEDUPE_SLUGS),
                "--img-dedupe-file", str(ROOT / "data" / "used_slugs.json"),
                "--tokens-out", str(TOKENS_PATH)]
    if TOKENS_PATH.exists():
        cmd += ["--tokens-in", str(TOKENS_PATH)]

    print("\n=== Publishing ===")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    print(f"Exit code: {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
