# 21. Singapore Life Content Publishing

> This document covers the "Singapore life" branch: fetching lifestyle content
> from Singapore media → English captions → publish to Square.

This branch provides three capabilities:

1. **Singapore lifestyle content sources** (4 sites: herworld, eatbook, timeout, tripzilla)
2. **English (Singapore) captions** (`caption_multilang.py --langs en`)
3. **No watermark cropping** (editorial photos are watermark-free)

---

## 21.1 Singapore Sources

| Script | Site | Content Type | Output |
| ------ | ---- | ------------ | ------ |
| `scripts/fetch_sg_life.py` | herworld.com/life | Lifestyle, wellness, culture | Multi-image moments |
| `scripts/fetch_sg_life.py` | eatbook.sg | Food reviews, cafes, restaurants | Multi-image moments |
| `scripts/fetch_sg_life.py` | timeout.com/singapore | Food, nightlife, events, things to do | Multi-image moments |
| `scripts/fetch_sg_life.py` | tripzilla.com/.../singapore | Travel, attractions, activities | Multi-image moments |
| `scripts/fetch_stock_my.py --query singapore` | Pexels / Pixabay | Stock photos of Singapore | Single-image moments |

Source URLs:
- https://www.herworld.com/life
- https://eatbook.sg/
- https://www.timeout.com/singapore
- https://www.tripzilla.com/category/destinations/asia/southeast-asia/singapore

All sources are Playwright-based (JS-rendered). No API key required.

### A. Lifestyle Articles (default, multi-image)

```powershell
py -3 scripts/fetch_sg_life.py `
    --sources herworld,eatbook,timeout,tripzilla `
    --posts 10 `
    --imgs-per-post 9 `
    --min-imgs 2 `
    --dedupe-file state/seen_sg_life.json `
    --output sg_raw.csv
```

- Each article becomes one multi-image post (>= `--min-imgs` photos).
- Ad/sponsored articles are filtered by title keywords.
- `_source` = `herworld` / `eatbook` / `timeout` / `tripzilla`.

### B. Pexels + Pixabay Stock (requires Playwright)

```powershell
py -3 scripts/fetch_stock_my.py `
    --sources pexels,pixabay `
    --query singapore `
    --per-source 30 `
    --output sg_stock_raw.csv
```

---

## 21.2 English Captions (Singapore)

```powershell
$env:DEFAULT_SCENE = "travel"
py -3 scripts/caption_multilang.py `
    --input sg_raw.csv `
    --output moments_sg.csv `
    --langs en
```

- Language: `en` (English, suitable for Singapore's English-speaking audience)
- Scene detection keywords: Marina Bay, Orchard, Sentosa, hawker, kopitiam,
  Changi, Gardens by the Bay, Clarke Quay, Chinatown, Little India, etc.
- Captions are conversational English with hashtags + emoji.

---

## 21.3 Image Cropping (disabled)

Singapore sources are all editorial/stock photos **without watermarks**:
- herworld.com — SPH Media editorial images
- eatbook.sg — original food photography
- timeout.com — licensed editorial images
- tripzilla.com — travel photography
- Pexels/Pixabay — free stock photos

`run_singapore.py` **disables cropping by default** (`POST_CROP_BOTTOM_HOSTS=""`).
Use `--crop` to enable if needed.

---

## 21.4 End-to-End Runbook

### One-command script (recommended)

```powershell
# Default: 4 SG lifestyle sites, 5 accounts, 10 multi-image posts, English
py -3 scripts/run_singapore.py --accounts-csv accounts_5.csv --posts 10

# Stock photos (Pexels + Pixabay)
py -3 scripts/run_singapore.py --source stock --accounts-csv accounts_10.csv --posts 50

# Only fetch + caption, no publish (preview)
py -3 scripts/run_singapore.py --posts 5 --skip-publish

# Unattended (skip confirmation)
py -3 scripts/run_singapore.py --accounts-csv accounts_5.csv --posts 10 --yes
```

Key parameters:

| Parameter | Description | Default |
| --------- | ----------- | ------- |
| `--source` | `life` (4 SG media sites) / `stock` (Pexels+Pixabay) | `life` |
| `--accounts-csv` | Accounts CSV (local, not committed) | `accounts_5.csv` |
| `--posts` | Number of posts to publish | `10` |
| `--langs` | Caption language | `en` |
| `--crop` | Enable bottom watermark crop | off |
| `--skip-publish` / `--yes` | Preview only / skip confirmation | off |

Intermediate files go to `--workdir` (default `sg_run/`).
Publish report: `result/publish_*.csv`.

### Step-by-step (manual)

```powershell
# 1. Fetch articles
py -3 scripts/fetch_sg_life.py --sources herworld,eatbook,timeout,tripzilla `
    --posts 10 --imgs-per-post 9 --min-imgs 2 --output sg_raw.csv

# 2. English captions
$env:DEFAULT_SCENE = "travel"
py -3 scripts/caption_multilang.py --input sg_raw.csv --output moments_sg.csv --langs en

# 3. Publish (no crop)
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_5.csv --csv moments_sg.csv `
    --concurrency 3 --tokens-out result/tokens.json
```

---

## 21.5 Category Tag (sources/categories.json)

The "新加坡生活" category is registered in `sources/categories.json` for use with
`post_room_moments.py --category 新加坡生活`. This allows room/group posting
to reference the Singapore life tag directly.

---

## 21.6 Security

- Follow `docs/09-security.md`: **never commit** accounts CSV / `.env` / tokens.
- All editorial images are from public sites; no special auth required.
