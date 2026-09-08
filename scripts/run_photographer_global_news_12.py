#!/usr/bin/env python3
"""
run_photographer_global_news_12.py — 12 English text posts about global news.
Topics: Tech, Business, Science, Society, Politics from European/American sources.
Pure text posts, no images, first-person photographer voice.
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
STATE_DIR = ROOT / "state"
DEDUPE_FILE = STATE_DIR / "seen_photographer_global_news_12.json"
CAPTION_DEDUPE = STATE_DIR / "seen_global_news_captions.json"

# Global news topics with first-person commentary
NEWS_TOPICS = [
    # Tech & AI
    ("tech", "en",
     "The pace of AI development is absolutely breathtaking. Every week brings breakthroughs that redefine what we thought possible. We're witnessing the birth of a new era in computing."),
    ("tech", "en",
     "OpenAI's latest moves have everyone talking. The competition between Anthropic and OpenAI is pushing the boundaries of what's possible. This is the golden age of artificial intelligence."),
    ("tech", "en",
     "The race for quantum computing supremacy is heating up. Major tech giants are investing billions, and the implications for cryptography and drug discovery could be revolutionary."),
    # Business & Finance
    ("business", "en",
     "The tech sector continues to reshape global markets. NVIDIA's acquisition strategy shows they're not just selling chips — they're building an ecosystem. Smart move."),
    ("business", "en",
     "Microsoft's integration of AI into Office 365 is a game changer. Productivity tools are becoming intelligent assistants. The workplace will never be the same."),
    ("business", "en",
     "The IPO market is showing signs of life again. After a brutal 2022-2023, startups are finding their footing. Venture capital is flowing back into the ecosystem."),
    # Science & Nature
    ("science", "en",
     "NASA's latest discoveries about Mars are mind-blowing. The possibility of ancient microbial life keeps getting stronger. We might be alone in the universe, but we're definitely not alone in our solar system."),
    ("science", "en",
     "Climate science is getting more urgent by the day. New research shows tipping points are closer than we thought. But also — new carbon capture technologies are emerging fast."),
    # Society & Culture
    ("society", "en",
     "Remote work is here to stay, but the debate about productivity vs. wellbeing continues. Companies are experimenting with 4-day weeks. The future of work is being rewritten right now."),
    ("society", "en",
     "The global education system is undergoing a massive transformation. AI tutors, personalized learning paths, digital classrooms — the pandemic accelerated what was already coming."),
    ("society", "en",
     "Democracy faces challenges worldwide, but technology also offers new tools for civic engagement. Digital governance, transparent voting systems — the future of politics is being coded."),
    # Healthcare
    ("health", "en",
     "mRNA vaccine technology is proving to be a platform, not a one-trick pony. Cancer vaccines, HIV treatments — the applications are expanding rapidly. This is medical revolution."),
    ("health", "en",
     "Mental health awareness has reached a tipping point. Gen Z is leading the charge, normalizing therapy and self-care. The stigma is finally crumbling."),
    # Space & Exploration
    ("space", "en",
     "SpaceX's Starship tests are getting closer to orbit. When that thing lands vertically on its first orbital flight, it changes everything about cost of access to space."),
    ("space", "en",
     "The James Webb Space Telescope keeps giving us gift after gift. Distant galaxies, exoplanet atmospheres, the early universe — we're seeing things no human eye has ever witnessed."),
    # Environment
    ("environment", "en",
     "Renewable energy costs have plummeted. Solar and wind are now cheaper than fossil fuels in most of the world. The energy transition is accelerating faster than most models predicted."),
    ("environment", "en",
     "Ocean conservation is getting the attention it deserves. Marine protected areas are expanding, and new technologies are helping us monitor ocean health in real time."),
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
    rows = list(csv.DictReader(open(PHOTOGRAPHER_CSV, encoding="utf-8-sig")))
    picked = []
    seen = set(exclude)
    for r in rows:
        email = r.get("邮箱", "").strip().lower()
        if email in seen:
            continue
        seen.add(email)
        picked.append(r)
        if len(picked) >= n:
            break
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--num-users", type=int, default=12)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--tokens", default="result/tokens.json")
    ap.add_argument("--workdir", default="photographer_global_news_12_run")
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
        
        # Ensure uniqueness
        original_caption = caption
        for j in range(5):
            if caption not in used_caps:
                break
            # Add suffix if duplicate
            caption = f"{original_caption} ({i+1})"
        
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
            "_dedupe_key": f"global_news_{i}",
        })

    moments_csv = wd / f"moments_global_news_{ts}.csv"
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
