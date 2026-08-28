#!/usr/bin/env python3
"""
run_web3_opennana_5.py — 5 new web3 accounts, each posts 1 opennana image in English.
Caption written in poster's first-person voice, no blank lines between paragraphs.
"""
from __future__ import annotations

import argparse, csv, io, json, random, subprocess, sys, time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]
API = "https://api.opennana.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://opennana.com/",
}
ACCOUNTS_CSV = ROOT / "accounts_web3_100.csv"
DEDUPE_SLUGS = ROOT / "state" / "seen_opennana_web3_5.json"

# 5 posts: (slug, caption)
POSTS = [
    (
        "otaku-must-see-anime-girl",
        "The anime art style in this one is immaculate — every detail from the hair to the expression is perfectly rendered. This is the kind of character design that makes you stop scrolling.",
    ),
    (
        "prompt-391",
        "Prompt 391 delivered exactly what I was imagining. The composition and lighting feel so natural, like a real moment caught on film rather than generated art.",
    ),
    (
        "tropical-bikini-vacation-gelato",
        "Summer vibes in this shot — the tropical setting, the gelato, the whole scene feels like a memory from a perfect vacation. I wish I could live in this moment.",
    ),
    (
        "night-flash-intimate-couple-moment",
        "That night flash photography gives this such a raw, intimate energy. The way the light hits their faces makes this feel like a private moment frozen in time.",
    ),
    (
        "boho-summer-vacation-coconut-time",
        "Boho summer aesthetics at their finest. Coconut trees, golden hour light, and that effortless vacation energy — this is the mood I live for every single summer.",
    ),
]


def fetch_image(slug: str) -> str:
    import requests as _req
    r = _req.get(f"{API}/api/prompts/{slug}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    d = r.json().get("data") or {}
    imgs = d.get("images") or d.get("image") or []
    if not imgs:
        raise ValueError(f"No images for {slug}")
    return imgs[0]


def load_used_slugs() -> set:
    if DEDUPE_SLUGS.exists():
        try:
            return set(json.loads(DEDUPE_SLUGS.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_used_slugs(used: set) -> None:
    DEDUPE_SLUGS.parent.mkdir(parents=True, exist_ok=True)
    DEDUPE_SLUGS.write_text(json.dumps(sorted(used), ensure_ascii=False), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="web3_opennana_5_run")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)

    tokens = json.load(open(ROOT / args.tokens, encoding="utf-8"))
    token_emails = set(tokens.keys())
    print(f"[tokens] {len(token_emails)} available")

    # Load accounts
    accounts = list(csv.DictReader(open(ACCOUNTS_CSV, encoding="utf-8-sig")))
    keys = list(accounts[0].keys())
    email_col = keys[2]
    nick_col = keys[1]
    pwd_col = keys[3]
    id_col = keys[0]

    valid_accounts = [a for a in accounts if a.get(email_col, "").strip().lower() in token_emails]
    print(f"[accounts] {len(valid_accounts)} valid")

    # Fetch images and build moments
    moments = []
    used_slugs = load_used_slugs()
    for i, (slug, cap) in enumerate(POSTS):
        if slug in used_slugs:
            print(f"  [SKIP] slug already used: {slug}")
            continue
        try:
            img_url = fetch_image(slug)
        except Exception as e:
            print(f"  [ERROR] {slug}: {e}")
            continue
        acct = valid_accounts[i % len(valid_accounts)]
        moments.append({
            "content": cap,
            "visibility": "0",
            "room_id": "",
            "image_urls": img_url,
            "location_name": "", "location_address": "", "location_lat": "", "location_lon": "",
            "_lang": "en",
            "_source": "opennana",
            "_dedupe_key": f"onana:{slug}",
        })
        print(f"  [{i+1}] {acct.get(nick_col,'?'):20} | {slug[:40]} | {img_url[:70]}")

    if not moments:
        print("[ERROR] No moments to publish", file=sys.stderr)
        return 1

    # Write moments CSV
    moments_csv = wd / f"moments_web3_opennana_{ts}.csv"
    fields = ["content","visibility","room_id","image_urls","location_name","location_address","location_lat","location_lon","_lang","_source","_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow(m)

    print(f"\n[OK] {len(moments)} posts ready")
    for i, m in enumerate(moments):
        acct = valid_accounts[i % len(valid_accounts)]
        print(f"  [{i+1}] {acct.get(nick_col,'?'):20} | {m['content'][:70]}")

    if not args.yes:
        if input("\n  Confirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    # Save dedupe
    all_slugs = {m["_dedupe_key"].split(":")[1] for m in moments}
    save_used_slugs(used_slugs | all_slugs)

    # Build merged accounts CSV (only used accounts)
    merged_acc = wd / f"accounts_merged_{ts}.csv"
    with merged_acc.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号","昵称","邮箱","密码"])
        w.writeheader()
        for i in range(len(moments)):
            acct = valid_accounts[i % len(valid_accounts)]
            w.writerow({"序号": acct.get(id_col, ""), "昵称": acct.get(nick_col, ""),
                        "邮箱": acct.get(email_col, ""), "密码": acct.get(pwd_col, "")})

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(merged_acc),
                "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "2.0",
                "--record-dedupe",
                "--web3-dedupe-file", str(DEDUPE_SLUGS),
                "--img-dedupe-file", str(ROOT / "data" / "used_slugs.json"),
                "--tokens-out", str(ROOT / args.tokens)]
    if (ROOT / args.tokens).exists():
        cmd += ["--tokens-in", str(ROOT / args.tokens)]

    print("\n=== Publishing ===")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    print(f"Exit code: {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
