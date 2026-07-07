# 19. 台灣內容發布（Taiwan branch）

> 本文檔隨 `taiwan` 分支維護，彙整「台灣圖文內容採集 → 繁體中文（台灣語境）文案 →
> 底部浮水印裁切 → 廣場發布」的完整呼叫方式。做法與 `malaysia` / `indonesia` 分支一致，
> 語言換為**繁體中文（台灣語境）**（`--langs zh_hant`）。

本分支在 `main` 基礎上，提供三塊能力（**自包含**）：

1. **台灣圖片採集源**（觀光署相簿 + Pexels/Unsplash 圖庫）
2. **繁體中文／台灣語境主體視角文案**（`caption_multilang.py --langs zh_hant`）
3. **底部浮水印整條裁切**：小紅書 + backpackers（bbkz.net）+ 觀光署（erv-nsa.gov.tw）統一處理

---

## 19.1 台灣採集源

| 腳本 | 站點 | 取圖方式 | 產出 |
| ---- | ---- | -------- | ---- |
| `scripts/fetch_ervnsa_tw.py` | erv-nsa.gov.tw 觀光署相簿分享 | Playwright（JS 渲染 + 忽略 TLS）逐相簿取 `/image/<id>/1024x768` | **多圖** moments 行（每相簿一帖） |
| `scripts/fetch_stock_my.py --sources pexels,unsplash --query taiwan --locale zh-TW` | Pexels / Unsplash | Playwright 繞過反爬，取原圖直鏈（無浮水印、免 API key） | 單圖 moments 行 |

> 三個來源網址：
> - `https://www.erv-nsa.gov.tw/zh-tw/service/albumlist`（觀光署官方相簿，台灣風景／部落／活動）
> - `https://www.pexels.com/zh-cn/search/台灣/`
> - `https://unsplash.com/s/photos/taiwan`
>
> erv-nsa 為政府網站，TLS 憑證鏈不完整，採集端以 `ignore_https_errors` 處理；
> 發布端下載時對 `erv-nsa.gov.tw` 走 `verify=False`（`POST_NO_VERIFY_HOSTS` 預設含此域名）。

### A. 觀光署相簿（多圖，預設）

```powershell
py -3 scripts/fetch_ervnsa_tw.py --posts 10 --imgs-per-post 9 --min-imgs 3 `
    --listing-pages 8 --dedupe-file tw_used_albums.json --output tw_raw.csv
```

### B. Pexels + Unsplash（圖庫原圖，需 Playwright）

```powershell
py -3 scripts/fetch_stock_my.py --sources pexels,unsplash --query taiwan `
    --locale zh-TW --per-source 30 --output tw_raw.csv
```

---

## 19.2 繁體中文／台灣語境文案

`caption_multilang.py --langs zh_hant` 的繁中模板池已加入台灣語境變體，
並在場景識別加入台灣地名關鍵字：

```powershell
$env:DEFAULT_SCENE = "travel"
py -3 scripts/caption_multilang.py --input tw_raw.csv --output moments_tw.csv --langs zh_hant
```

- 場景關鍵字：台北101／夜市（night）、九份／台南／老街（street）、
  墾丁／東北角／澎湖（beach）、合歡山／阿里山／玉山（winter）、
  高美濕地／夕陽（goldenhour）、台灣／花蓮／太魯閣／日月潭／環島（travel）等。
- 文案為台灣在地口吻＋繁體字，如：
  `台北101點燈的夜晚，怎麼拍都好看。🌆 #台北101 #台北夜景 #台灣之美`、
  `九份老街的紅燈籠一亮，整條街都有故事。🏮 #九份 #台灣景點 #老街`。
- 若配置 `LLM_TEXT_*`，加 `--use-llm` 可用大模型生成繁中文案（內建 `zh_hant` 提示詞）。

---

## 19.3 底部浮水印裁切（小紅書 / backpackers / 觀光署 統一）

`publish_from_tokens.py` 上傳 S3 前，對命中域名圖片**整條裁掉底部**去浮水印，預設：

```
POST_CROP_BOTTOM_HOSTS = xhscdn.com,xiaohongshu.com,bbkz.net,erv-nsa.gov.tw
POST_CROP_BOTTOM_PCT   = 0.08
POST_NO_VERIFY_HOSTS   = erv-nsa.gov.tw   # 政府站 TLS 鏈不完整 → 下載時 verify=False
```

- 觀光署相簿圖（`erv-nsa.gov.tw`）**開箱即用**自動裁切。
- Pexels / Unsplash 原圖無浮水印，不在裁切列表，原樣上傳。

---

## 19.4 端到端 runbook（台灣）

### 一鍵腳本（推薦）

```powershell
# 預設：觀光署相簿，5 帳號，10 個多圖帖，繁體中文，自動裁底部浮水印
py -3 scripts/run_taiwan.py --accounts-csv accounts_5.csv --posts 10

# 圖庫源（Pexels + Unsplash，台灣關鍵字）
py -3 scripts/run_taiwan.py --source stock --accounts-csv accounts_10.csv --posts 50

# 只採集 + 文案、不發布
py -3 scripts/run_taiwan.py --posts 5 --skip-publish

# 無人值守
py -3 scripts/run_taiwan.py --accounts-csv accounts_5.csv --posts 10 --yes
```

| 參數 | 說明 | 預設 |
| ---- | ---- | ---- |
| `--source` | `ervnsa`（觀光署多圖） / `stock`（Pexels+Unsplash） | `ervnsa` |
| `--langs` | 文案語言 | `zh_hant`（繁體中文） |
| `--crop-pct` | 底部裁切比例 | `0.08` |
| `--skip-publish` / `--yes` | 只產素材 / 免確認 | 關 |

中間產物落 `tw_run/`，報告落 `result/publish_*.csv`。

---

## 19.5 安全

- 沿用 `docs/09-security.md`：**不入庫**任何帳號 CSV / `.env` / token。
- `.env.example` 的 `POST_CROP_BOTTOM_HOSTS` 預設已含 `erv-nsa.gov.tw`。
