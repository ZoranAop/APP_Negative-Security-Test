#!/usr/bin/env python3
"""
run_europe_en.py — European content (finance/news/life/tech/science/AI) publisher
for English-speaking users.

Workflow:
    1) Select 30 English-nickname accounts from pre2000 CSV
    2) Fetch European & global English-language news (text posts)
    3) Fetch tech/science images (image posts)
    4) Generate English captions with proper topic hashtags
    5) Publish via publish_from_tokens.py

Each user gets 2 posts: 1 text (news commentary) + 1 image (tech/science).
Language consistency: ALL content in English.
Ad filtering: inherited from fetch sources.
Image quality: handled by publish_from_tokens.py (7-step pipeline).
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
except Exception:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PY = [sys.executable]

# ============================================================
# English caption templates for European news/finance/tech/science/AI
# ============================================================

TEXT_OPENERS = [
    "Worth tracking closely \u2014 ",
    "This caught my attention: ",
    "Key signal in the news today. ",
    "The implications here are significant. ",
    "Something to watch from Europe and beyond: ",
    "Another reminder that the world is shifting fast. ",
    "Interesting development worth noting: ",
    "This has broader implications than it seems. ",
    "A story that deserves more attention: ",
    "Paying attention to this one \u2014 ",
    "The landscape is changing rapidly. ",
    "News like this shapes the next decade. ",
    "This one stopped me mid-scroll. ",
    "Big picture thinking needed here: ",
    "The signal-to-noise ratio on this story is high. ",
    "One of those headlines you read twice. ",
    "This connects to so many other things happening right now. ",
    "Can't ignore the trajectory this suggests. ",
    "Context matters more than the headline here. ",
    "Filing this under 'things that will compound'. ",
]

TEXT_CLOSERS = [
    "Staying informed is half the battle.",
    "Understanding context matters more than ever.",
    "The ripple effects will be felt globally.",
    "More developments to follow.",
    "Keep watching this space.",
    "The bigger picture is emerging.",
    "Worth revisiting in a few weeks.",
    "Critical thinking needed here.",
    "Curious to see where this leads.",
    "Keeping my eye on the follow-up.",
]

SITE_HASHTAGS = {
    "guardian": "#Europe #Tech #Guardian",
    "guardianintl": "#WorldNews #Europe #Analysis",
    "arstechnica": "#Tech #Science #ArsTechnica",
    "techcrunch": "#TechNews #Startups #Innovation",
    "engadget": "#Technology #Digital #Gadgets",
    "nyt": "#News #Analysis #Technology",
    "cnn": "#WorldNews #Breaking #Global",
    "bloomberg_jp": "#Finance #Markets #Bloomberg",
    "straitstimes": "#Asia #Europe #StraitsTimesNews",
    "cnbc_world": "#Finance #Economy #Markets",
}

TOPIC_TAGS = {
    "guardian": "#EUPolicy #Society",
    "guardianintl": "#GlobalAffairs #Geopolitics",
    "arstechnica": "#AI #DeepTech",
    "techcrunch": "#AIStartup #VentureCapital",
    "engadget": "#ConsumerTech #Digital",
    "nyt": "#Innovation #BigTech",
    "cnn": "#BreakingNews #World",
    "bloomberg_jp": "#Trading #GlobalMarkets",
    "straitstimes": "#APAC #Diplomacy",
    "cnbc_world": "#Economics #Business",
}

IMG_OPENERS = [
    "This is the kind of innovation that changes everything.",
    "Science and technology converging in fascinating ways.",
    "Another glimpse into what the future holds.",
    "The pace of research breakthroughs is remarkable.",
    "When engineering meets imagination, this happens.",
    "A visual reminder of how far we have come.",
    "The frontier of human knowledge keeps expanding.",
    "This image captures the spirit of discovery.",
    "Where science fiction meets reality.",
    "The intersection of research and real-world impact.",
    "Visual proof that the future is being built now.",
    "Every breakthrough starts with a single experiment.",
    "Moments like these make you appreciate human ingenuity.",
    "The speed of technological progress never ceases to amaze.",
    "Innovation at its finest \u2014 captured in one frame.",
    "This is what happens when brilliant minds collaborate.",
    "Technology moving faster than our ability to comprehend it.",
    "The quiet revolution happening in labs around the world.",
    "From concept to reality in record time.",
    "A snapshot of tomorrow's world, today.",
]

IMG_MIDDLES = [
    "The scale of resources dedicated to this field is unprecedented.",
    "What excites me most is the real-world application potential.",
    "The engineering precision here is truly impressive.",
    "This kind of work represents the best of human curiosity.",
    "The collaboration driving these results is inspiring.",
    "From lab to reality \u2014 the pipeline is getting shorter.",
    "The dedication behind this kind of research is immense.",
    "This is where fundamental research meets practical impact.",
    "The investment in this space speaks volumes about where we are headed.",
    "What a time to be following scientific progress.",
]

IMG_CLOSERS = [
    "#Science #Technology #Future",
    "#Innovation #Research #Engineering",
    "#AI #Tech #Discovery",
    "#DeepTech #Progress #NextGen",
    "#STEM #Breakthrough #Exploration",
    "#Physics #Engineering #Innovation",
    "#ClimateScience #Tech #Solutions",
    "#SpaceScience #NASA #Discovery",
    "#QuantumComputing #Tech #Research",
    "#BioTech #Medicine #Future",
]


def _run(cmd: list, *, env_extra=None) -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _ad_filter(title: str) -> bool:
    """Return True if title looks like an ad (should be skipped)."""
    AD_KEYWORDS = [
        "sponsored", "advertisement", "promo", "promotion",
        "buy now", "discount", "sale ", "coupon", "subscribe now",
        "limited offer", "free trial",
    ]
    lower = title.lower()
    return any(kw in lower for kw in AD_KEYWORDS)


def generate_text_caption(title: str, site: str, idx: int, rng: random.Random) -> str:
    """Generate English first-person commentary on a news headline."""
    opener = TEXT_OPENERS[idx % len(TEXT_OPENERS)]
    closer = rng.choice(TEXT_CLOSERS)
    hashtags = SITE_HASHTAGS.get(site, "#News #Europe #Tech")
    topic = TOPIC_TAGS.get(site, "#Technology #Innovation")
    # Truncate title if too long
    if len(title) > 120:
        title = title[:117] + "..."
    cap = f'{opener}\n\n"{title}"\n\n{closer}\n{hashtags} {topic}'
    return cap[:280]


def generate_img_caption(title: str, site: str, idx: int, rng: random.Random) -> str:
    """Generate English caption for a tech/science image post."""
    opener = IMG_OPENERS[idx % len(IMG_OPENERS)]
    middle = rng.choice(IMG_MIDDLES)
    closer = rng.choice(IMG_CLOSERS)
    # Use just a short excerpt from the title
    short_title = title[:80] if len(title) > 80 else title
    cap = f'{opener}\n\n"{short_title}"\n\n{middle}\n{closer}'
    return cap[:280]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="European EN content publisher (30 users x 2 posts = 60)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_europe30.csv",
                    help="Accounts CSV (30 English-nickname users)")
    ap.add_argument("--posts-per-user", type=int, default=2)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--tokens", default="result/tokens_europe.json")
    ap.add_argument("--workdir", default="europe_run")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="Skip fetching, use existing CSVs")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    (ROOT / "state").mkdir(exist_ok=True)

    text_csv = wd / f"text_raw_{ts}.csv"
    img_tech_csv = wd / f"img_tech_raw_{ts}.csv"
    img_sci_csv = wd / f"img_science_raw_{ts}.csv"
    moments_csv = wd / f"moments_europe_final_{ts}.csv"

    # ------------------------------------------------------------------
    # Step 1: Fetch text content (European/global English news)
    # ------------------------------------------------------------------
    if not args.skip_fetch:
        print("\n=== Step 1/4: Fetch European English news (text sources) ===")
        text_sources = "guardian,guardianintl,arstechnica,techcrunch,engadget,nyt,cnn,bloomberg_jp,straitstimes,cnbc_world"
        cmd = PY + [str(HERE / "fetch_tech.py"),
                    "--sources", text_sources,
                    "--per-site", "5",
                    "--dedupe-file", "state/seen_europe_en.json",
                    "--output", str(text_csv)]
        if _run(cmd) != 0 or not text_csv.exists():
            print("[ERROR] Text fetch failed")
            return 1

        # Step 2: Fetch image content (tech/AI)
        print("\n=== Step 2/4: Fetch tech/AI images ===")
        cmd = PY + [str(HERE / "fetch_us_tech_ai.py"),
                    "--sources", "techcrunch,theverge,wired,arstechnica,mittr,ieee_spectrum",
                    "--per-site", "4",
                    "--output", str(img_tech_csv)]
        if _run(cmd) != 0 or not img_tech_csv.exists():
            print("[ERROR] Tech image fetch failed")
            return 1

        # Step 2b: Fetch science images
        print("\n=== Step 2b/4: Fetch science images ===")
        cmd = PY + [str(HERE / "fetch_us_science.py"),
                    "--sources", "nasa,nsf,nist,energy",
                    "--per-site", "4",
                    "--output", str(img_sci_csv)]
        if _run(cmd) != 0 or not img_sci_csv.exists():
            print("[ERROR] Science image fetch failed")
            return 1
    else:
        # Use existing CSVs (check both timestamped and non-timestamped)
        existing_text = sorted(wd.glob("text_raw*.csv"))
        existing_tech = sorted(wd.glob("img_tech_raw*.csv"))
        existing_sci = sorted(wd.glob("img_science_raw*.csv"))
        # Also check for combined image file
        existing_combined = sorted(wd.glob("img_combined*.csv"))
        if existing_text:
            text_csv = existing_text[-1]
        if existing_tech:
            img_tech_csv = existing_tech[-1]
        if existing_sci:
            img_sci_csv = existing_sci[-1]
        elif existing_combined:
            # Use combined as science fallback
            img_sci_csv = existing_combined[-1]

    # ------------------------------------------------------------------
    # Step 3: Assemble 60 posts with proper English captions
    # ------------------------------------------------------------------
    print("\n=== Step 3/4: Assemble 60 posts (30 users x 2) ===")

    # Read sources
    with open(text_csv, encoding="utf-8-sig") as f:
        text_rows = list(csv.DictReader(f))
    
    # Combine image sources
    img_rows = []
    for img_f in [img_tech_csv, img_sci_csv]:
        if img_f.exists():
            with open(img_f, encoding="utf-8-sig") as f:
                img_rows.extend(list(csv.DictReader(f)))

    # Read accounts
    acc_path = ROOT / args.accounts_csv
    with open(acc_path, encoding="utf-8-sig") as f:
        accts = list(csv.DictReader(f))

    n_users = len(accts)
    n_posts = n_users * args.posts_per_user
    need_text = n_users  # 1 text per user
    need_img = n_users   # 1 image per user

    print(f"  Users: {n_users}, Posts needed: {n_posts}")
    print(f"  Text available: {len(text_rows)}, Image available: {len(img_rows)}")

    if len(text_rows) < need_text:
        print(f"[ERROR] Not enough text ({len(text_rows)} < {need_text})")
        return 1
    if len(img_rows) < need_img:
        print(f"[ERROR] Not enough images ({len(img_rows)} < {need_img})")
        return 1

    # Shuffle for variety
    rng = random.Random(int(ts.replace("_", "")))
    rng.shuffle(text_rows)
    rng.shuffle(img_rows)

    # Filter ads from text
    text_rows = [r for r in text_rows if not _ad_filter(r.get("content", ""))]

    # Assemble posts
    out_rows = []
    ti = ii = 0

    for u_idx in range(n_users):
        # Post 1: Text post (news commentary)
        tr = text_rows[ti]
        ti += 1
        title = tr["content"]
        site = tr.get("_site", "")
        text_content = generate_text_caption(title, site, u_idx, rng)

        out_rows.append({
            "content": text_content,
            "visibility": "0", "room_id": "", "image_urls": "",
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_source": "europe_news", "_ptype": "text",
            "_lang": "en", "_site": site,
            "_dedupe_key": f"news:{title[:50]}",
        })

        # Post 2: Image post (tech/science)
        ir = img_rows[ii]
        ii += 1
        img_title = ir.get("content", "")
        img_site = ir.get("_site", ir.get("_source", ""))
        img_urls = ir.get("image_urls", "")
        img_content = generate_img_caption(img_title, img_site, u_idx, rng)

        out_rows.append({
            "content": img_content,
            "visibility": "0", "room_id": "", "image_urls": img_urls,
            "location_name": "", "location_address": "",
            "location_lat": "", "location_lon": "",
            "_source": "europe_tech", "_ptype": "image",
            "_lang": "en", "_site": img_site,
            "_dedupe_key": f"img:{img_urls[:50]}",
        })

    # Write final CSV
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_ptype", "_lang", "_site", "_dedupe_key"]
    with open(moments_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    # Verify
    unique = len(set(r["content"] for r in out_rows))
    cjk = sum(1 for r in out_rows if re.search(r"[\u4e00-\u9fff]", r["content"]))
    print(f"  [OK] {len(out_rows)} posts assembled")
    print(f"  [OK] Unique content: {unique}/{len(out_rows)}")
    print(f"  [OK] CJK contamination: {cjk} (should be 0)")
    print(f"  [OK] Text: {sum(1 for r in out_rows if r['_ptype']=='text')}, "
          f"Image: {sum(1 for r in out_rows if r['_ptype']=='image')}")
    print(f"  [OK] Output: {moments_csv.name}")

    if args.skip_publish:
        print(f"\n--skip-publish set. Content ready at: {moments_csv}")
        return 0

    # ------------------------------------------------------------------
    # Step 4: Publish via publish_from_tokens.py
    # ------------------------------------------------------------------
    print("\n=== Step 4/4: Publish (sequential login + concurrent posting) ===")

    if not args.yes:
        ans = input(f"  Publish {len(out_rows)} posts with {n_users} accounts? (y/n): ")
        if ans.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0

    tokens_path = ROOT / args.tokens
    tokens_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = PY + [str(HERE / "publish_from_tokens.py"),
                "--accounts-csv", str(acc_path),
                "--csv", str(moments_csv),
                "--concurrency", str(args.concurrency),
                "--login-spacing", "3.0",
                "--tokens-out", str(tokens_path)]
    # Add tokens-in if existing
    if tokens_path.exists():
        cmd += ["--tokens-in", str(tokens_path)]

    rc = _run(cmd)
    if rc != 0:
        print(f"[EUROPE_EN] publish returned {rc}")
        return rc

    print(f"\n[EUROPE_EN] Done! Published {len(out_rows)} posts.")
    print(f"[EUROPE_EN] Report: result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
