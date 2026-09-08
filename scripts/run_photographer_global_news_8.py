#!/usr/bin/env python3
"""
run_photographer_global_news_8.py — 8 English text posts about global news.
Uses fresh accounts from pre_企管用户_街拍摄影师.csv.
Pure text, no images, no identifiers.
"""
from __future__ import annotations

import argparse, csv, io, json, os, re, subprocess, sys, time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"
ALT_ACCOUNTS_CSV = ROOT / "pre_企管用户_850.csv"
STATE_DIR = ROOT / "state"
DEDUPE_FILE = STATE_DIR / "seen_photographer_global_news_8.json"
CAPTION_DEDUPE = STATE_DIR / "seen_global_news_captions2.json"

# Fresh news topics - 8 unique entries
NEWS_TOPICS = [
    ("tech", "en",
     "Artificial intelligence is reshaping every industry at unprecedented speed. What seemed like science fiction a decade ago is now daily reality. The transformation is just beginning."),
    ("business", "en",
     "The global tech economy is experiencing a major shift. Big players are acquiring AI startups at record pace, while regulators are waking up to the need for oversight. Exciting times ahead."),
    ("science", "en",
     "Space exploration is entering a golden age. Private companies are competing to reach Mars, while telescopes peer back to the dawn of time. We're living through the most exciting era of discovery."),
    ("society", "en",
     "The future of work is being rewritten right now. Hybrid models, AI assistants, four-day weeks — the corporate world is experimenting faster than ever before. Adaptation is key."),
    ("health", "en",
     "Medical technology is advancing at breakneck pace. From mRNA vaccines to gene editing, we're gaining tools that were unimaginable just years ago. Healthcare will never be the same."),
    ("climate", "en",
     "Green energy is finally hitting its stride. Solar and wind costs have plummeted, electric vehicles are everywhere, and battery technology keeps improving. The transition is accelerating."),
    ("finance", "en",
     "Cryptocurrency and blockchain are maturing beyond the hype. Institutional adoption is real, regulation is taking shape, and the technology is finding practical applications. The dust is settling."),
    ("education", "en",
     "Education technology is transforming how we learn. AI tutors, virtual classrooms, personalized curricula — the pandemic forced changes that are now permanent. Knowledge access is expanding."),
]


def _load_tokens():
    try:
        return set(json.loads((ROOT / "result/tokens.json").read_text(encoding="utf-8")).keys())
    except Exception:
        return set()


def _load_used_emails():
    used = set()
    for d in ROOT.glob("photographer_*_run"):
        for f in d.glob("accounts_merged_*.csv"):
            try:
                for row in csv.DictReader(open(f, encoding="utf-8-sig")):
                    e = row.get("邮箱", "").strip().lower()
                    if e:
                        used.add(e)
            except Exception:
                pass
    return used


def pick_accounts(n):
    tokens = _load_tokens()
    prev_used = _load_used_emails()
    exclude = tokens | prev_used
    
    # Try photographer CSV first, then fallback to alt accounts
    for csv_path in [PHOTOGRAPHER_CSV, ALT_ACCOUNTS_CSV]:
        if not csv_path.exists():
            continue
        rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
        picked = []
        seen = set(exclude)
        for r in rows:
            email = r.get("邮箱", "").strip().lower() or r.get("email", "").strip().lower()
            if not email:
                continue
            if email in seen:
                continue
            seen.add(email)
            picked.append(r)
            if len(picked) >= n:
                break
        if picked:
            return picked
    
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--num-users", type=int, default=8)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="photographer_global_news_8_run")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)

    accounts = pick_accounts(args.num_users)
    print(f"[accounts] {len(accounts)} photographers: {[a['昵称'] for a in accounts]}")

    # Load used captions for dedup
    used_caps = set()
    if CAPTION_DEDUPE.exists():
        try:
            used_caps = set(json.loads(CAPTION_DEDUPE.read_text(encoding="utf-8")))
        except Exception:
            pass

    # Build moments
    moments = []
    for i in range(min(len(NEWS_TOPICS), len(accounts))):
        topic, lang, caption = NEWS_TOPICS[i]
        
        # Use caption as-is, no modification
        used_caps.add(caption)
        
        moments.append({
            "content": caption,
            "visibility": "0",
            "room_id": "",
            "image_urls": "",  # Text only
            "location_name": "",
            "location_address": "",
            "location_lat": "",
            "location_lon": "",
            "_lang": lang,
            "_source": "global_news",
            "_topic": topic,
            "_dedupe_key": f"global_news8_{i}",
        })

    moments_csv = wd / f"moments_global_news_8_{ts}.csv"
    fields = ["content","visibility","room_id","image_urls","location_name","location_address","location_lat","location_lon","_lang","_source","_topic","_dedupe_key"]
    with moments_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for m in moments:
            w.writerow(m)

    print(f"\n[OK] {len(moments)} text-only posts ready")
    for i, m in enumerate(moments):
        acct = accounts[i] if i < len(accounts) else {"昵称": "?"}
        preview = m["content"][:65].replace("\n", " ")
        print(f"  [{i+1}] {acct['昵称']:15} [{m['_topic']:10}] | {preview}...")

    if not args.yes:
        if input("\nConfirm publish? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    # Save caption dedupe
    CAPTION_DEDUPE.write_text(json.dumps(sorted(used_caps), ensure_ascii=False), encoding="utf-8")

    dedupe_file = DEDUPE_FILE
    used = set()
    if dedupe_file.exists():
        try:
            used = set(json.loads(dedupe_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    new_keys = {m["_dedupe_key"] for m in moments}
    dedupe_file.write_text(json.dumps(sorted(used | new_keys), ensure_ascii=False), encoding="utf-8")

    merged_acc = wd / f"accounts_merged_{ts}.csv"
    tokens_path = ROOT / args.tokens
    tokens_path.parent.mkdir(parents=True, exist_ok=True)
    with merged_acc.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["序号","昵称","邮箱","密码"])
        w.writeheader()
        for a in accounts[:len(moments)]:
            w.writerow({"序号": a.get("序号",""), "昵称": a["昵称"],
                        "邮箱": a["邮箱"], "密码": a.get("密码","")})

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(merged_acc),
                "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "3.0",
                "--record-dedupe",
                "--web3-dedupe-file", str(dedupe_file),
                "--skip-upload",
                "--tokens-out", str(tokens_path)]
    if tokens_path.exists():
        cmd += ["--tokens-in", str(tokens_path)]

    print(f"\n=== publishing {len(moments)} text-only posts ===")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    print(f"Exit code: {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
