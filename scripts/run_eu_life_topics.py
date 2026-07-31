#!/usr/bin/env python3
"""
run_eu_life_topics.py — European/Western lifestyle publisher for English-nickname
users from the pre-1720 pool.

Topics: Life, Art, Travel, Cars (欧美标签)
Language: ALL English
Image rules: single/multi-image random, images matched to text content

Workflow:
    1) Fetch content from 4 topic RSS sources (life/art/travel/cars)
    2) Generate English first-person captions with topic-specific hashtags
    3) Assemble 1 post per user (10 users = 10 posts)
    4) Publish via publish_from_tokens.py with 30-150s random delays

Usage:
    py -3 scripts/run_eu_life_topics.py --accounts-csv accounts_eu_life_10.csv --yes
    py -3 scripts/run_eu_life_topics.py --skip-publish
"""
from __future__ import annotations

import argparse
import csv
import io
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
# Source attribution stripping (aligned with run_us_life.py)
# ============================================================
_KNOWN_SITES = {
    "Refinery29", "The Everygirl", "BuzzFeed",
    "ArtNews", "Hyperallergic", "Artforum",
    "Lonely Planet", "Condé Nast Traveler", "Travel + Leisure",
    "Motor1", "Top Gear", "Car and Driver",
    "refinery29", "theeverygirl", "buzzfeed",
    "artnews", "hyperallergic", "artforum",
    "lonelyplanet", "conde_nast_t", "travel_leisure",
    "motor1", "topgear", "caranddriver",
}


def strip_source_attribution(text: str) -> str:
    """Remove all source/attribution marks so the post looks user-original."""
    if not text:
        return text
    text = re.sub(r'[（(]\s*[來来]源\s*[:：]?\s*[^）)]+[）)]', '', text)
    text = re.sub(r'\(\s*(?:via|source|sumber)\s*[:：]?\s*[^)]+\)', '', text)
    _escaped = [re.escape(n) for n in _KNOWN_SITES if n]
    if _escaped:
        _pat = '|'.join(sorted(_escaped, key=len, reverse=True))
        text = re.sub(r'\[(?:' + _pat + r')\]\s*', '', text)
        text = re.sub(r'(?:via|source|from)\s*[:：]?\s*(?:' + _pat + r')', '', text, flags=re.IGNORECASE)
        text = re.sub(r'(?:reported by|courtesy of)\s+(?:' + _pat + r')', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'[（(]\s*[）)]', '', text)
    text = re.sub(r'\[\s*\]', '', text)
    text = re.sub(r'^\s*[,.\-—;:]+\s*', '', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


# ============================================================
# Topic-specific English caption templates
# Each template: {title} placeholder + topic hashtag
# ============================================================

TOPIC_TAGS = {
    "life": "#Lifestyle #DailyLife",
    "art": "#Art #Creative",
    "travel": "#Travel #Wanderlust",
    "cars": "#Cars #Automotive",
}

TEMPLATES = {
    "life": [
        "{title}, this popped up in my feed and I couldn't scroll past {tag}",
        "{title}, love stumbling upon content like this {tag}",
        "{title}, adding this to my things-to-try list {tag}",
        "{title}, the internet delivered today {tag}",
        "{title}, this made my day better {tag}",
        "{title}, bookmark-worthy stuff right here {tag}",
        "{title}, sharing because this genuinely made me smile {tag}",
        "{title}, too good not to share {tag}",
        "{title}, my feed just got more interesting {tag}",
        "{title}, lifestyle content done right {tag}",
        "{title}, found my new weekend inspo {tag}",
        "{title}, exactly what I needed to see today {tag}",
        "{title}, sometimes the simplest ideas are the most brilliant {tag}",
        "{title}, the little things that make life feel put together {tag}",
        "{title}, genuinely inspired to try something new {tag}",
    ],
    "art": [
        "{title}, this is the kind of creativity that stops you in your tracks {tag}",
        "{title}, art that speaks without saying a word {tag}",
        "{title}, the vision behind this is remarkable {tag}",
        "{title}, moments like this remind me why I love art {tag}",
        "{title}, the detail and craft here are next level {tag}",
        "{title}, this is what happens when imagination meets skill {tag}",
        "{title}, couldn't look away from this one {tag}",
        "{title}, the colors and composition are just perfect {tag}",
        "{title}, art that makes you feel something real {tag}",
        "{title}, this piece stayed with me long after I scrolled past {tag}",
        "{title}, the kind of work that redefines a medium {tag}",
        "{title}, pure inspiration right here {tag}",
        "{title}, creativity at its finest {tag}",
        "{title}, this is why I keep coming back to art {tag}",
        "{title}, the emotion captured here is powerful {tag}",
    ],
    "travel": [
        "{title}, adding this to my bucket list immediately {tag}",
        "{title}, this is why I never stop dreaming of travel {tag}",
        "{title}, the world is full of places like this and I want to see them all {tag}",
        "{title}, wanderlust activated {tag}",
        "{title}, saving this for my next adventure {tag}",
        "{title}, this view alone would be worth the trip {tag}",
        "{title}, travel content that actually delivers {tag}",
        "{title}, the kind of destination that stays with you {tag}",
        "{title}, already planning how to get here {tag}",
        "{title}, this is what travel dreams are made of {tag}",
        "{title}, the beauty of this place is unreal {tag}",
        "{title}, adding another pin to my map {tag}",
        "{title}, this is going straight to my travel board {tag}",
        "{title}, the world never ceases to amaze me {tag}",
        "{title}, places like this are why I travel {tag}",
    ],
    "cars": [
        "{title}, this is what automotive passion looks like {tag}",
        "{title}, the engineering behind this is something else {tag}",
        "{title}, car content that actually gets me excited {tag}",
        "{title}, the design language here is just chef's kiss {tag}",
        "{title}, this is the kind of build that turns heads {tag}",
        "{title}, performance and style in one package {tag}",
        "{title}, the details on this are insane {tag}",
        "{title}, automotive art right here {tag}",
        "{title}, this is why I love cars {tag}",
        "{title}, the sound of this alone would be worth it {tag}",
        "{title}, design perfection if you ask me {tag}",
        "{title}, the kind of car that makes you stop and stare {tag}",
        "{title}, engineering meets emotion {tag}",
        "{title}, this build is on another level {tag}",
        "{title}, pure driving pleasure right here {tag}",
    ],
}


def _caption(title: str, topic: str, rng: random.Random, seen: set) -> str:
    """Generate an English first-person caption for a given topic."""
    title = strip_source_attribution(title)
    tag = TOPIC_TAGS.get(topic, "#Lifestyle")
    templates = TEMPLATES.get(topic, TEMPLATES["life"])
    for _ in range(40):
        tpl = rng.choice(templates)
        cap = tpl.format(title=title[:60], tag=tag)
        cap = strip_source_attribution(cap)
        if len(cap) > 300:
            cap = tpl.format(title=title[:45], tag=tag)
            cap = strip_source_attribution(cap)
        if cap not in seen:
            seen.add(cap)
            return cap
    base = templates[0].format(title=title[:50], tag=tag)
    return strip_source_attribution(base)


def _run(cmd: list) -> int:
    import os
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="EU Life Topics publisher (Life/Art/Travel/Cars, 10 users x 1 post)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", default="accounts_eu_life_10.csv")
    ap.add_argument("--topics", default="life,art,travel,cars")
    ap.add_argument("--per-site", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=1,
                    help="Concurrency=1 for sequential posting with random delays")
    ap.add_argument("--delay-min", type=float, default=30.0,
                    help="Min random delay between posts (seconds)")
    ap.add_argument("--delay-max", type=float, default=150.0,
                    help="Max random delay between posts (seconds)")
    ap.add_argument("--tokens", default="result/tokens_eu_life.json")
    ap.add_argument("--workdir", default="eu_life_topics_run")
    ap.add_argument("--skip-fetch", action="store_true")
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    wd = ROOT / args.workdir
    wd.mkdir(parents=True, exist_ok=True)
    (ROOT / "state").mkdir(exist_ok=True)

    raw_csv = wd / f"eu_life_raw_{ts}.csv"
    moments_csv = wd / f"eu_life_moments_{ts}.csv"

    # ------------------------------------------------------------------
    # Step 1: Fetch content from 4 topic sources
    # ------------------------------------------------------------------
    if not args.skip_fetch:
        print("\n=== Step 1/3: Fetch Life/Art/Travel/Cars content ===")
        cmd = PY + [str(HERE / "fetch_eu_life_topics.py"),
                    "--topics", args.topics,
                    "--per-site", str(args.per_site),
                    "--output", str(raw_csv)]
        if _run(cmd) != 0 or not raw_csv.exists():
            print("[ERROR] fetch failed")
            return 1
    else:
        existing = sorted(wd.glob("eu_life_raw*.csv"))
        if existing:
            raw_csv = existing[-1]
        else:
            print("[ERROR] --skip-fetch but no existing raw CSV")
            return 1

    # ------------------------------------------------------------------
    # Step 2: Assemble 10 posts (1 per user) with English captions
    # ------------------------------------------------------------------
    print("\n=== Step 2/3: Assemble posts with English captions ===")

    with open(raw_csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    acc_path = ROOT / args.accounts_csv
    with open(acc_path, encoding="utf-8-sig") as f:
        accts = list(csv.DictReader(f))

    n_users = len(accts)
    print(f"  Users: {n_users}")
    print(f"  Raw items available: {len(rows)}")

    if len(rows) < n_users:
        print(f"[ERROR] Not enough items ({len(rows)} < {n_users})")
        return 1

    rng = random.Random(int(ts.replace("_", "")))

    # Group items by topic for balanced distribution
    by_topic: dict[str, list[dict]] = {}
    for r in rows:
        topic = r.get("_topic", "life")
        by_topic.setdefault(topic, []).append(r)

    # Shuffle each topic group
    for topic in by_topic:
        rng.shuffle(by_topic[topic])

    # Distribute topics across users: cycle through topics
    topics_list = [t.strip() for t in args.topics.split(",") if t.strip()]
    # Build a pool: round-robin pick from topics
    selected_items: list[dict] = []
    topic_idx = {t: 0 for t in topics_list}
    for i in range(n_users):
        topic = topics_list[i % len(topics_list)]
        pool = by_topic.get(topic, [])
        idx = topic_idx[topic]
        if idx < len(pool):
            selected_items.append(pool[idx])
            topic_idx[topic] += 1
        else:
            # Fallback: pick from any topic that has items
            for fallback_topic in topics_list:
                fb_pool = by_topic.get(fallback_topic, [])
                fb_idx = topic_idx[fallback_topic]
                if fb_idx < len(fb_pool):
                    selected_items.append(fb_pool[fb_idx])
                    topic_idx[fallback_topic] += 1
                    break

    if len(selected_items) < n_users:
        print(f"[ERROR] Could not select enough items ({len(selected_items)} < {n_users})")
        return 1

    # Generate captions
    seen_caps: set = set()
    out_rows = []
    for i, item in enumerate(selected_items[:n_users]):
        title = item.get("content", "")
        topic = item.get("_topic", "life")
        site = item.get("_site", "")
        img_urls = item.get("image_urls", "")

        cap = _caption(title, topic, rng, seen_caps)

        # Randomize single vs multi-image
        # If we have image URLs, randomly decide 1 or multiple
        final_img_urls = img_urls
        if img_urls:
            urls = [u.strip() for u in img_urls.split(",") if u.strip()]
            if len(urls) > 1:
                # 50% chance single, 50% chance multi (up to 4)
                if rng.random() < 0.5:
                    final_img_urls = rng.choice(urls)
                else:
                    n_imgs = rng.randint(2, min(4, len(urls)))
                    final_img_urls = ",".join(rng.sample(urls, n_imgs))
            # If single URL, keep as is

        out_rows.append({
            "content": cap,
            "visibility": "0",
            "room_id": "",
            "image_urls": final_img_urls,
            "location_name": "",
            "location_address": "",
            "location_lat": "",
            "location_lon": "",
            "_source": "eu_life_topics",
            "_topic": topic,
            "_site": site,
            "_lang": "en",
            "_dedupe_key": f"eu_life:{title[:50]}",
        })

    # Write final CSV
    fields = ["content", "visibility", "room_id", "image_urls",
              "location_name", "location_address", "location_lat", "location_lon",
              "_source", "_topic", "_site", "_lang", "_dedupe_key"]
    with open(moments_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in out_rows:
            w.writerow({k: r.get(k, "") for k in fields})

    # Verify
    unique = len(set(r["content"] for r in out_rows))
    cjk = sum(1 for r in out_rows if re.search(r"[\u4e00-\u9fff]", r["content"]))
    img_count = sum(1 for r in out_rows if r["image_urls"])
    text_count = n_users - img_count
    topic_dist = {}
    for r in out_rows:
        t = r["_topic"]
        topic_dist[t] = topic_dist.get(t, 0) + 1

    print(f"  [OK] {len(out_rows)} posts assembled")
    print(f"  [OK] Unique content: {unique}/{len(out_rows)}")
    print(f"  [OK] CJK contamination: {cjk} (should be 0)")
    print(f"  [OK] Image posts: {img_count}, Text posts: {text_count}")
    print(f"  [OK] Topic distribution: {topic_dist}")
    print(f"  [OK] Output: {moments_csv.name}")

    # Show sample
    for i, r in enumerate(out_rows[:3]):
        n_imgs = len([u for u in r["image_urls"].split(",") if u.strip()]) if r["image_urls"] else 0
        print(f"\n  Sample {i+1} [{r['_topic']}] ({n_imgs} img):")
        print(f"    {r['content'][:120]}...")

    if args.skip_publish:
        print(f"\n--skip-publish set. Content ready at: {moments_csv}")
        return 0

    # ------------------------------------------------------------------
    # Step 3: Publish via publish_from_tokens.py
    # ------------------------------------------------------------------
    print(f"\n=== Step 3/3: Publish ({n_users} posts, delay {args.delay_min}-{args.delay_max}s) ===")

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
                "--post-delay-min", str(args.delay_min),
                "--post-delay-max", str(args.delay_max),
                "--tokens-out", str(tokens_path)]
    if tokens_path.exists():
        cmd += ["--tokens-in", str(tokens_path)]

    rc = _run(cmd)
    if rc != 0:
        print(f"[EU_LIFE_TOPICS] publish returned {rc}")
        return rc

    print(f"\n[EU_LIFE_TOPICS] Done! Published {len(out_rows)} posts.")
    print(f"[EU_LIFE_TOPICS] Report: result/publish_*.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
