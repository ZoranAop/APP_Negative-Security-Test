# 25. Pexels Video Publish Workflow

> **Purpose**: Publish Pexels-hosted video posts to XXAI Square using selected account pools.
>
> **Trigger**: User requests "pexels video publish" / "publish pexels videos" / "发布 pexels 视频"

---

## Quick Start

```powershell
py -3 scripts/run_pexels_video.py `
    --theme cambodia `
    --accounts-csv pre_企管用户_街拍摄影师.csv `
    --nick-filter en `
    --count 10 `
    --caption-lang en `
    --yes
```

| Flag | Description |
|------|-------------|
| `--theme` | Pexels search keyword (e.g. `cambodia`, `tokyo`, `korea`, `india`, `southeast-asia`) |
| `--accounts-csv` | Account CSV to draw from (default: `pre_企管用户_街拍摄影师.csv`) |
| `--nick-filter` | `en` / `jp` / `cn` / `random` / `auto` (pick by nickname category) |
| `--count` | Number of videos to post |
| `--caption-lang` | `en` / `ja` / `zh_hant` / `ko` / `mixed` |
| `--yes` | Skip interactive confirmation |

---

## Account Nickname Categories

The script classifies each account by its `昵称` column:

| Category | Pattern | Examples |
|----------|---------|----------|
| `en` | `^[A-Za-z][A-Za-z0-9_.\- ]+$` (pure English) | `CheungKai`, `WingLau88`, `Last Train Home` |
| `jp` | Contains hiragana/katakana or Japanese-specific chars | `にこまる`, `星のシャッター` |
| `cn` | Contains CJK unified ideographs | `我只是路過`, `街角觀察員`, `相機沒電了` |
| `random` | Everything else (non-EN, non-JP, non-CN mixed) | `35mm Diary`, `Grainy Days`, `Neon Walk` |

When `--nick-filter=random` is requested:
1. Try `random` category first
2. If not enough accounts, fall back to `en`
3. Log which category was used for each account

---

## Pexels Video Discovery

Pexels blocks direct page scraping with Cloudflare. Use the **download redirect trick**:

```python
import requests

def find_pexels_video_urls(theme: str, limit: int = 10) -> list[dict]:
    """
    1. Scrape the Pexels search page for /video/{id}/ links
    2. For each ID, hit the download endpoint to get the real MP4 URL
    3. Return list of {"vid": int, "video_url": str}
    """
    # Step 1: get video IDs from search page
    r = requests.get(
        f"https://www.pexels.com/zh-cn/search/videos/{theme}/",
        timeout=30, verify=False,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    import re
    ids = list(dict.fromkeys(re.findall(r'/video/(\d+)/', r.text)))

    # Step 2: resolve each ID to a video URL
    results = []
    for vid in ids[:limit * 3]:  # fetch extra to account for dead links
        if len(results) >= limit:
            break
        dr = requests.get(
            f"https://www.pexels.com/download/video/{vid}/",
            timeout=15, allow_redirects=False, verify=False,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        loc = dr.headers.get("Location", "")
        if "video-files" in loc:
            results.append({"vid": int(vid), "video_url": loc})
    return results
```

**Known-valid Pexels video IDs by theme** (confirmed working, use these directly to avoid re-scraping):

```python
KNOWN_VIDEO_IDS = {
    "cambodia":  [30170009, 29383140, 29247677, 29247695, 30170008,
                   29074122, 29383143, 29089383, 32927000, 30797834],
    "tokyo":     [854140, 7677258, 8926451, 9915238],
    "korea":     [32927000, 29191440, 4684166, 7677258, 8926451, 9678901, 9915238],
    "india":     [32927000, 4684166, 8926451, 9678901, 9915238],
    "southeast-asia": [29074122, 29104184, 29228800, 29247803, 29383140,
                       29458118, 31136459, 30570498, 30797834, 4030306],
}
```

> **Note**: IDs overlap across themes (e.g. `32927000` appears in korea/india/SEA lists).
> Always dedupe against previously-used IDs before re-posting.

---

## Thumbnail Handling

Pexels video thumbnails are fetched from `images.pexels.com`. The URL pattern:

```
https://images.pexels.com/videos/{vid}/pexels-photo-{vid}.jpeg?cs=tinysrgb&dpr=1&w=800
```

**Fallback strategy** (in order):
1. Try the canonical Pexels thumbnail URL above
2. Try `https://images.pexels.com/videos/{vid}/{vid}.jpeg?cs=tinysrgb&w=800`
3. If both fail (Cloudflare 403), fall back to the **video file itself** as thumbnail
   (S3 upload accepts `.mp4` as thumbnail — the server generates a preview frame)

```python
def get_thumbnail(vid: int, media_dir: Path) -> Path:
    """Return local thumbnail file. Falls back to the video file if Pexels blocks."""
    thumb = media_dir / f"thumb_{vid}.jpg"
    if thumb.exists() and thumb.stat().st_size > 0:
        return thumb
    for url in [
        f"https://images.pexels.com/videos/{vid}/pexels-photo-{vid}.jpeg?cs=tinysrgb&dpr=1&w=800",
        f"https://images.pexels.com/videos/{vid}/{vid}.jpeg?cs=tinysrgb&w=800",
    ]:
        try:
            r = requests.get(url, timeout=15, verify=False,
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.pexels.com/"})
            if r.status_code == 200 and len(r.content) > 5000:
                thumb.write_bytes(r.content)
                return thumb
        except:
            pass
    # Fallback: use video file as thumbnail
    return media_dir / f"video_{vid}.mp4"
```

---

## Caption Templates

Captions are written in the voice of a **traveler/poster** — short, first-person, no AI-flavor.
All captions are in the requested language.

### English (default)

```python
CAPTION_BANKS = {
    "cambodia": [
        "Wandering through old Cambodia. The air is thick with history, every stone remembers.",
        "Angkor from above. 1,000 years of empire, still standing. The scale is humbling.",
        "Breakfast at a little Cambodian cafe. Strong coffee, warm bread, slow morning.",
        "A quiet corner in Phnom Penh. The kind of stop you don't plan, just live in for a while.",
        "Cambodia in 2025. Markets, temples, the river. It moves at its own pace, and that's the point.",
        "Angkor Wat at dawn. You don't need words. You just stand there and let it in.",
        "Drone run over the old capital. The geometry of it is still unreal, nine centuries on.",
        "Lost in the temple corridors. The carvings tell stories nobody's written down.",
        "Evening walk through the lanes. Lanterns coming up, the heat finally breaking.",
        "The 12th century built this. And it still stops you mid-stride.",
    ],
    "tokyo": [
        "Shinjuku at night. The neon never really turns off, and tonight it's my turn to disappear into it.",
        "Quiet morning walk through the old quarter. Tokyo hides the best moments in its smallest alleys.",
        "Caught the sky over Shibuya just as it turned gold. Tokyo rewards you for looking up.",
        "Ramen at 1am. The right bowl after a long day tastes better than you'd expect.",
        "The trains run on time here, but the city itself runs on a rhythm only Tokyo knows.",
        "A single maple leaf on the wet pavement. Autumn in Tokyo arrives quietly, then all at once.",
        "Surrendered to the crowd on the crossing. Just another face in the beautiful chaos.",
        "A bench, a river, and the whole city humming beyond the water. Tokyo is easier to love from here.",
        "Neon, rain, and the smell of warm bread. Tokyo in the rain has a mood you can't plan for.",
        "Last light over Tokyo Tower. The city glows from within, even before the dark.",
    ],
    "korea": [
        "Seoul, late afternoon. The city slows down just enough to let you breathe.",
        "A quiet street in Hongdae. The kind of moment you don't need to photograph, just remember.",
        "Busan at dusk. The harbour lights come up one by one, and the whole bay turns gold.",
        "A tiny cafe in Incheon, steam rising off the cup, rain on the window. Perfect.",
        "Walking through Myeongdong after the crowds thin out. The neon looks better at night.",
        "The Han River on a Sunday. People bring picnic blankets and let the afternoon just pass.",
        "A hanok district in the morning. The silence here feels different, older.",
    ],
    "india": [
        "Jaipur at golden hour. The pink city earns its name every evening.",
        "The Ganges at dawn. A hundred boats, a million small prayers on the water.",
        "Nile's own chaos, its own rhythm. You stop fighting it after a while.",
        "A quiet street in Udaipur. The lake is just a wall away, and the whole place breathes.",
        "The road through the Deccan. Open sky, old stone, and nowhere to rush to.",
    ],
    "southeast-asia": [
        "Bangkok's Grand Palace at sunrise. The whole city holds its breath, then starts all at once.",
        "A boat on the Chao Phraya, the bridge lights coming up one by one. Bangkok rewards the patient.",
        "The street food of Singapore's night market is its own language. You just have to listen.",
        "A coconut by the water in Bali. The kind of stop where time stops with you.",
        "The rice terraces of Vietnam at dawn. Water in every field, gold in every layer.",
        "Malacca's old quarter. The Dutch built it, the centuries kept it, and it still works beautifully.",
        "A temple deep in the jungle. The stones are older than the country's name.",
        "Phuket's harbour at sunset. The boats turn into a thousand small lights.",
        "The road through Cambodia's highlands. Red earth, green water, and no hurry at all.",
        "A night train into the hills of Laos. The dark outside the window does the talking.",
    ],
}
```

### Japanese

```python
CAPTION_BANKS_JA = {
    "cambodia": [
        "古いカンボジアを歩く。空気は歴史で満ちていて、石の一つ一つが記憶している。",
        "上空から見るアンコール。千年の帝国が、まだ立っている。その規模に圧倒される。",
        "小さなカンボジアのカフェで朝食。濃いコーヒー、温かいパン、ゆっくりとした朝。",
        "プノンペンの静かな一角。計画しないまま、自然とそこに留まる時間。",
    ],
    "tokyo": [
        "夜の Shinjuku。ネオンは本当に消えず、今夜は僕が溶け込む番だ。",
        "古い町の静かな朝の散歩。東京は一番いい瞬間を一番狭い路地に隠している。",
        "渋谷の上の空が、ちょうど金色に変わる瞬間を撮れた。東京は上を向いている人に報いてくれる。",
        "深夜のラーメン。長い一日の後、正しい一杯は想像以上においしい。",
    ],
}
```

---

## Full Execution Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  1. DISCOVER VIDEO URLs                                          │
│     Known IDs (if available) OR scrape Pexels search page       │
│     → verify via download redirect → list of {vid, video_url}   │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. DEDUPE                                                       │
│     Load data/used_pexels_video_ids.json                         │
│     Remove already-posted IDs                                    │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. SELECT ACCOUNTS                                              │
│     Read accounts CSV                                            │
│     Classify nicknames: en / jp / cn / random                   │
│     Filter by --nick-filter                                      │
│     Exclude: already in result/tokens.json + previous runs      │
│     If not enough: fall back to en category                     │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. LOGIN (sequential, 2.5s spacing, 429 backoff)               │
│     POST https://api.xxai.com/login                             │
│     Save tokens to result/tokens.json                            │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. GET S3 CREDENTIALS                                           │
│     POST https://api.xxai.com/file/upload/credentials           │
│     (any valid token works as anchor)                           │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. FOR EACH VIDEO:                                              │
│     a. Download MP4 → media/pexels_{theme}_{vid}.mp4            │
│     b. Get thumbnail (Pexels URL → fallback to video file)     │
│     c. Upload video + thumbnail to S3                           │
│     d. POST moment: {content, media_info:{type:video,...}}     │
│     e. Record moment_id + used video ID                         │
│     sleep 5s between posts                                       │
└──────────────────────┬──────────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  7. PERSIST STATE                                               │
│     Update data/used_pexels_video_ids.json                      │
│     Update result/tokens.json                                    │
│     Write result/publish_pexels_{theme}_{ts}.csv report         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Deduplication

Maintain `data/used_pexels_video_ids.json` to avoid re-posting the same Pexels video:

```json
{
  "30170009": {"theme": "cambodia", "posted_at": "2026-09-17", "account": "u_8uq2uf0o@xxai.com"},
  "29383140": {"theme": "cambodia", "posted_at": "2026-09-17", "account": "u_9eea8r3r@xxai.com"}
}
```

Load before each run; exclude any `vid` already in the file.

---

## File Locations

| File | Purpose |
|------|---------|
| `scripts/run_pexels_video.py` | Main runner (create this) |
| `data/used_pexels_video_ids.json` | Pexels video dedup ledger |
| `result/tokens.json` | Token cache (shared across all scripts) |
| `pexels_{theme}_video_run/media/` | Downloaded video + thumbnail files |
| `result/publish_pexels_{theme}_{ts}.csv` | Publish report |

---

## Error Handling

| Error | Recovery |
|-------|----------|
| Pexels download 403 (Cloudflare) | Use `verify=False` + `Referer: https://www.pexels.com/` |
| Pexels video download broken (large 4K files) | Retry up to 3× with 3s backoff; use `Range` header to resume |
| Login 429 | Exponential backoff: `2.5 × 2^attempt` seconds |
| S3 upload timeout | Retry 3×; credentials are short-lived so re-fetch if > 15 min old |
| Token expired during post | Re-login with stored password, retry once |
| Thumbnail 404 / 403 | Fall back to video file as thumbnail (server generates frame) |

---

## Adding New Theme Support

1. Add the Pexels search keyword to `--theme` choices
2. Optionally add a `KNOWN_VIDEO_IDS[theme]` entry for reliable IDs
3. Add caption bank entries to `CAPTION_BANKS[theme]` (minimum 5 captions)
4. Run: `py -3 scripts/run_pexels_video.py --theme {keyword} --nick-filter en --count 10 --yes`
