# 20. 自動去重：避免重複抓取已抓過的內容

> 三條地區線（`run_malaysia.py` / `run_indonesia.py` / `run_taiwan.py`）以及底層
> 各採集器都內建**持久去重**。已經抓過的內容會被記錄下來，**下次執行自動跳過**，
> 不需要手動管理，也不會重覆發同一篇/同一相簿/同一圖庫圖。

## 20.1 原理

每個採集器在抓取時，用一個「內容身份」判斷是否抓過，並把身份寫進去重檔（JSON）：

| 採集器 | 內容身份（去重鍵） |
| ------ | ------------------ |
| `fetch_backpackers_my.py`（f=111 / f=54） | 論壇 **thread id** |
| `fetch_ervnsa_tw.py` | 觀光署 **album id** |
| `fetch_tw_media.py`（shoppingdesign/gq/sony） | 文章 **URL** |
| `fetch_stock_my.py`（pexels/pixabay/unsplash） | 圖片 **CDN URL** |
| `fetch_cizucu.py`（cizucu.com 摄影社区） | 照片 **photoId** |
| `fetch_web3.py`（9 个 Web3 媒体） | 消息 **归一化标题**（跨源词重叠判重） |
執行流程：
1. 開跑時讀入去重檔 → 得到「已抓集合」。
2. 抓取時，命中已抓集合的條目**直接跳過**，只收新內容。
3. 收工時把新抓到的身份**合併寫回**去重檔。

所以第二次跑同一個源，永遠拿到**沒抓過的新內容**（實測：連跑兩次 gq，第二次與第一次 0 重疊）。

## 20.2 去重檔位置（開箱即用，無需配置）

runner 會依「源」自動選用固定去重檔，統一放在 `state/` 目錄：

```
state/seen_my_backpackers_f111.json      # 馬來西亞 backpackers
state/seen_my_stock.json                 # 馬來西亞 圖庫
state/seen_id_backpackers_f54.json       # 印尼 backpackers
state/seen_id_stock.json                 # 印尼 圖庫
state/seen_tw_ervnsa.json                # 台灣 觀光署相簿
state/seen_tw_media.json                 # 台灣 媒體(shoppingdesign/gq/sony)
state/seen_tw_stock.json                 # 台灣 圖庫
state/seen_cizucu.json                   # cizucu 摄影社区（按 photoId 去重）
state/seen_web3.json                     # Web3 资讯 9 源（按归一化标题去重）
```

- `state/` 已加入 `.gitignore`：**本地持久保留**、不入庫（去重紀錄屬機器本地狀態，避免污染倉庫）。
- 想跨機器共用「已抓紀錄」時，可自行備份/同步 `state/` 目錄。

## 20.3 常用操作

```powershell
# 正常執行：自動跳過已抓內容（預設行為，什麼都不用加）
py -3 scripts/run_taiwan.py --source media --posts 15 --accounts-csv accounts_5.csv --yes

# 指定自訂去重檔（例如不同任務分開記錄）
py -3 scripts/run_taiwan.py --source media --dedupe-file state/my_campaignA.json ...

# 需要重新抓已抓過的內容時，清空該源去重紀錄
py -3 scripts/run_taiwan.py --source media --reset-dedupe ...
```

`run_malaysia.py` / `run_indonesia.py` 參數一致（`--dedupe-file` / `--reset-dedupe`）。

## 20.4 與「發帖不重複」的關係

- **抓取層**（本文）：跨批次不重覆抓同一篇/相簿/圖庫圖。
- **發布層**：批內還會做圖片 URL 去重（單帖內不重覆、跨帖不重覆），詳見各地區 runbook。

兩層疊加，確保「廣場上不會出現重覆的內容與圖片」。
