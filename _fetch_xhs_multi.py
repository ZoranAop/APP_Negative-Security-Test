#!/usr/bin/env python3
"""Expand XHS video fetching using different note types and pagination."""
import requests, re, json, time
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HEADERS = {"User-Agent": UA, "Referer": "https://www.xiaohongshu.com/"}

def fetch_explore_page(page=1, cursor="", has_more=True):
    """Fetch explore page with pagination."""
    params = {
        "num": 20,
        "cursor": cursor,
        "screen_duration": 0,
        "app_stack": 0,
    }
    r = requests.get(
        "https://www.xiaohongshu.com/explore",
        headers=HEADERS,
        params=params,
        timeout=20
    )
    m = re.search(r"window.__INITIAL_STATE__=(.*?)</script>", r.text, re.S)
    if not m:
        return None, False
    
    data = json.loads(m.group(1).replace(":undefined", ":null"))
    feeds = data.get("feed", {}).get("feeds", [])
    has_more = data.get("feed", {}).get("hasMore", False)
    cursor = data.get("feed", {}).get("cursor", "")
    
    return feeds, has_more, cursor

def extract_videos(feeds):
    """Extract video notes from feeds."""
    videos = []
    for feed in feeds:
        note_card = feed.get("noteCard", {})
        if note_card.get("type", "").lower() == "video":
            videos.append({
                "id": feed.get("id", ""),
                "xsecToken": feed.get("xsecToken", ""),
                "title": note_card.get("displayTitle", ""),
            })
    return videos

all_videos = []
seen_ids = set()
cursor = ""
page = 1
max_pages = 10

print("Fetching XHS explore pages with pagination...")

while page <= max_pages:
    feeds, has_more, cursor = fetch_explore_page(page=page, cursor=cursor)
    if not feeds:
        print(f"  Page {page}: No feeds found")
        break
    
    new_videos = []
    for v in extract_videos(feeds):
        if v["id"] and v["id"] not in seen_ids:
            seen_ids.add(v["id"])
            new_videos.append(v)
            all_videos.append(v)
    
    print(f"  Page {page}: {len(feeds)} feeds, {len(new_videos)} new videos (total: {len(all_videos)})")
    
    if not has_more or not cursor:
        break
    
    time.sleep(1.5)
    page += 1

# Also try popular tags/keywords
keywords = ["vlog", "日常", "生活", "美食", "旅行", "穿搭", "美妆", "健身", "游戏"]
print(f"\nSearching for keywords...")

for kw in keywords:
    url = f"https://www.xiaohongshu.com/search_result?keyword={kw}&source=web_explore_feed&search_id=&note_type=0&sort=general&page=1"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        m = re.search(r"window.__INITIAL_STATE__=(.*?)</script>", r.text, re.S)
        if m:
            data = json.loads(m.group(1).replace(":undefined", ":null"))
            # Try to find notes in search results
            search_result = data.get("searchResult", {})
            notes = search_result.get("notes", [])
            for note in notes:
                note_card = note.get("noteCard", {})
                if note_card.get("type", "").lower() == "video":
                    nid = note.get("id", "") or note_card.get("id", "")
                    if nid and nid not in seen_ids:
                        seen_ids.add(nid)
                        all_videos.append({
                            "id": nid,
                            "xsecToken": note.get("xsecToken", "") or note_card.get("xsecToken", ""),
                            "title": note_card.get("displayTitle", "")[:40],
                            "source_kw": kw,
                        })
            print(f"  Keyword '{kw}': +{len([n for n in notes if n.get('noteCard',{}).get('type','').lower()=='video'])} videos")
        time.sleep(1)
    except Exception as e:
        print(f"  Keyword '{kw}': Error - {e}")
        time.sleep(1)

print(f"\n{'='*60}")
print(f"Total unique video notes: {len(all_videos)}")

# Show samples
for i, v in enumerate(all_videos[:20]):
    src = v.get("source_kw", "explore")
    print(f"[{i+1}] [{src:10}] {v['id'][:12]} | {v['title'][:35]}")

# Save
out = Path(__file__).parent / "xhs_video_candidates.json"
out.write_text(json.dumps(all_videos, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nSaved {len(all_videos)} videos to {out}")
