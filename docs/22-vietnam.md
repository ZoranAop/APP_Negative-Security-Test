# 22. Vietnam Life Content Publishing

> This document covers the "Vietnam life" branch: fetching lifestyle content
> from Vietnamese media -> English captions -> publish to Square.

This branch provides three capabilities:

1. **Vietnam lifestyle content sources** (5 sites: saigoneer, baomoi, tuoitre, vietnamnews, timeout)
2. **English captions** (`caption_multilang.py --langs en`) with Vietnam-specific hashtags
3. **No watermark cropping** (editorial photos are watermark-free)

---

## 22.1 Vietnam Sources

| Script | Site | Language | Content Type | Output |
| ------ | ---- | -------- | ------------ | ------ |
| `scripts/fetch_vn_life.py` | saigoneer.com | EN | Arts, culture, food, travel, heritage | Multi-image moments |
| `scripts/fetch_vn_life.py` | baomoi.com | VI | Vietnamese news aggregator (lifestyle) | Multi-image moments |
| `scripts/fetch_vn_life.py` | tuoitre.vn | VI | Tuoi Tre (major VN newspaper, life section) | Multi-image moments |
| `scripts/fetch_vn_life.py` | vietnamnews.vn/life-style | EN | Vietnam News Agency Life & Style | Multi-image moments |
| `scripts/fetch_vn_life.py` | timeout.com/hanoi | EN | Time Out Hanoi (food, events, things to do) | Multi-image moments |
| `scripts/fetch_stock_my.py --query vietnam` | Pexels / Pixabay | - | Stock photos of Vietnam | Single-image moments |

Source URLs:
- https://saigoneer.com/ (English-language Saigon/Vietnam lifestyle)
- https://baomoi.com/ (Vietnamese news aggregator)
- https://tuoitre.vn/ (Tuoi Tre newspaper)
- https://vietnamnews.vn/life-style (VN News Agency English)
- https://www.timeout.com/hanoi (Time Out Hanoi)

All sources are Playwright-based (JS-rendered). No API key required.

### A. Lifestyle Articles (default, multi-image)

```powershell
py -3 scripts/fetch_vn_life.py `
    --sources saigoneer,baomoi,tuoitre,vietnamnews,timeout `
    --posts 10 `
    --imgs-per-post 9 `
    --min-imgs 2 `
    --dedupe-file state/seen_vn_life.json `
    --output vn_raw.csv
```

- Each article becomes one multi-image post (>= `--min-imgs` photos).
- Ad/sponsored articles filtered by both Vietnamese and English keywords.
- Image host patterns per source:
  - saigoneer: `media.urbanistnetwork.com`
  - baomoi: `photo-baomoi.bmcdn.me`, `zadn.vn`
  - tuoitre: `cdn.tuoitre.vn`, `static.tuoitre.vn`
  - vietnamnews: `image.vietnamnews.vn`
  - timeout: `media.timeout.com`, `imagekit.io`

### B. Pexels + Pixabay Stock (requires Playwright)

```powershell
py -3 scripts/fetch_stock_my.py `
    --sources pexels,pixabay `
    --query "vietnam food street hanoi saigon" `
    --per-source 30 `
    --output vn_stock_raw.csv
```

---

## 22.2 English Captions (Vietnam Life)

```powershell
$env:DEFAULT_SCENE = "travel"
py -3 scripts/caption_multilang.py `
    --input vn_raw.csv `
    --output moments_vn.csv `
    --langs en
```

- Language: `en` (English) — Saigoneer is English; other sources' images get English captions
- Vietnam-specific hashtags: #pho, #banhmi, #saigonlife, #hanoi, #vietnamfood,
  #streetfood, #hoian, #halongbay, #mekongdelta, #vietnamtravel, etc.
- Captions are conversational English with local Vietnamese food/place names.

---

## 22.3 Image Cropping (disabled)

All Vietnam sources are editorial/stock photos **without watermarks**:
- saigoneer.com — Urbanist Network editorial images
- baomoi.com — news aggregator CDN images
- tuoitre.vn — newspaper editorial images
- vietnamnews.vn — VNA editorial images
- timeout.com — licensed editorial images
- Pexels/Pixabay — free stock photos

`run_vietnam.py` **disables cropping by default** (`POST_CROP_BOTTOM_HOSTS=""`).

---

## 22.4 End-to-End Runbook

### One-command script (recommended)

```powershell
# Default: 5 VN media sites, 5 accounts, 10 multi-image posts, English
py -3 scripts/run_vietnam.py --accounts-csv accounts_5.csv --posts 10

# Stock photos (Pexels + Pixabay)
py -3 scripts/run_vietnam.py --source stock --accounts-csv accounts_10.csv --posts 50

# Only fetch + caption, no publish (preview)
py -3 scripts/run_vietnam.py --posts 5 --skip-publish

# Unattended (skip confirmation)
py -3 scripts/run_vietnam.py --accounts-csv accounts_5.csv --posts 10 --yes
```

Key parameters:

| Parameter | Description | Default |
| --------- | ----------- | ------- |
| `--source` | `life` (5 VN media sites) / `stock` (Pexels+Pixabay) | `life` |
| `--accounts-csv` | Accounts CSV (local, not committed) | `accounts_5.csv` |
| `--posts` | Number of posts to publish | `10` |
| `--langs` | Caption language | `en` |
| `--vn-sources` | Comma-separated site sources | `saigoneer,baomoi,tuoitre,vietnamnews,timeout` |
| `--crop` | Enable bottom watermark crop | off |
| `--skip-publish` / `--yes` | Preview only / skip confirmation | off |

Intermediate files go to `--workdir` (default `vn_run/`).
Publish report: `result/publish_*.csv`.

---

## 22.5 Interleaved Posting

The publisher uses round-robin account assignment by default, meaning posts
are **interleaved across users** automatically. For 10 users x 3 posts:
- Post 1 -> User 1, Post 2 -> User 2, ... Post 10 -> User 10
- Post 11 -> User 1, Post 12 -> User 2, ... Post 20 -> User 10
- Post 21 -> User 1, etc.

This ensures natural-looking posting patterns rather than one user bulk-posting.

---

## 22.6 Language Strategy

- **Saigoneer** and **Vietnam News** are English-language sites -> captions in English
- **Báo Mới** and **Tuổi Trẻ** are Vietnamese-language -> images fetched, captions written in English
- All posts use English with Vietnamese food/place names preserved (pho, banh mi, etc.)
- Hashtags mix English and romanized Vietnamese: #saigonlife #hanoi #banhmi #vietnamfood

---

## 22.7 Security

- Follow `docs/09-security.md`: **never commit** accounts CSV / `.env` / tokens.
- All editorial images are from public sites; no special auth required.
