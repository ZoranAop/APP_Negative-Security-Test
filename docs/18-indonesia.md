# 18. 印尼内容发布（Indonesia branch）

> 本文档随 `indonesia` 分支维护，汇总"印尼图文内容采集 → 印尼语文案 →
> 底部水印裁切 → 广场发布"的完整调用方式。做法与 `malaysia` 分支一致，
> 只是语言换成印尼语（Bahasa Indonesia），论坛版块换成 f=54（印尼）。

本分支在 `main` 基础上，提供三块能力（**自包含**，不依赖 malaysia 分支）：

1. **印尼图片采集源**（复用通用采集脚本 + 印尼关键词/版块）
2. **印尼语（Bahasa Indonesia）主体视角文案**（`caption_multilang.py --langs id`）
3. **底部水印整条裁切**：小红书 + backpackers 论坛（bbkz.net）统一处理

---

## 18.1 印尼采集源

| 脚本 | 站点 | 取图方式 | 产出 |
| ---- | ---- | -------- | ---- |
| `scripts/fetch_backpackers_my.py --fid 54` | backpackers.com.tw 印尼版 | 解析论坛游记贴，取 `sa.bbkz.net` 附件原图（去 `thumb=1`、剥离 `s=`） | **多图** moments 行 |
| `scripts/fetch_stock_my.py --query indonesia --locale id-ID` | Pexels / Pixabay | Playwright 绕过 Cloudflare，取原图直链（无水印、无 API key） | 单图 moments 行 |

> 采集引擎与 malaysia 分支共用（`fetch_backpackers_my.py` 支持 `--fid`，
> `fetch_stock_my.py` 支持 `--query` / `--locale`），无需重复造轮子。
> 其它源（getyourguide / magnific）为动态渲染或商业站，未纳入自动采集；
> 如需可后续按 Pexels/Pixabay 同样的 Playwright 思路扩展。

### A. backpackers.com.tw 印尼版（f=54，多图游记）

```powershell
py -3 scripts/fetch_backpackers_my.py `
    --fid 54 --posts 10 --imgs-per-post 9 --min-imgs 4 --listing-pages 4 `
    --dedupe-file id_used_threads.json --output id_raw.csv
```

- `--fid 54` = 论坛「印尼 Indonesia」版；每个游记贴聚合成一条多图帖。
- 自动跳过「包车 / 转让 / 代购 / 换汇 / 咨询」等广告贴。
- 附件图取全尺寸，链接稳定（无需 Referer / 无 Cloudflare）。

### B. Pexels + Pixabay（图库原图，需要 Playwright）

```powershell
py -3 scripts/fetch_stock_my.py `
    --sources pexels,pixabay --query indonesia --locale id-ID `
    --per-source 30 --output id_raw.csv
```

---

## 18.2 印尼语文案（Bahasa Indonesia）

`caption_multilang.py` 已内建印尼语（`id`）模板池 + 场景识别（含印尼地名）：

```powershell
$env:DEFAULT_SCENE = "travel"
py -3 scripts/caption_multilang.py --input id_raw.csv --output moments_id.csv --langs id
```

- 支持语言：`en / zh / zh_hant / ja / ms / id`。本分支重点是 `id`。
- 场景识别新增印尼关键词：雅加达 Jakarta（night）、日惹 Yogyakarta/Malioboro/婆罗浮屠 Borobudur（street）、
  巴厘岛 Bali/Raja Ampat/Gili（beach）、布罗莫 Bromo/Dieng/火山（winter）、
  印尼/wonderful indonesia/Komodo/Toba（travel）等。
- 文案为印尼本地口语，带 hashtag + emoji，如：
  `Dari Bali sampai Raja Ampat, tiap tempat punya cerita sendiri. 🧳 #jelajahindonesia #liburan #harianku`
- 若配置了 `LLM_TEXT_*`，加 `--use-llm` 可用大模型生成印尼语文案（已内置 `id` 提示词）。

---

## 18.3 底部水印裁切（与小红书 / backpackers 统一）

`publish_from_tokens.py` 上传 S3 前，对命中域名图片**整体裁掉底部一条**去水印，默认：

```
POST_CROP_BOTTOM_HOSTS = xhscdn.com,xiaohongshu.com,bbkz.net   # 默认值
POST_CROP_BOTTOM_PCT   = 0.08                                   # 底部 8%
```

- backpackers 印尼版图床同为 `sa.bbkz.net` / `sa1.bbkz.net`，**开箱即用**自动裁切。
- Pexels / Pixabay 原图无水印，不在裁切列表，原样上传。
- 水印偏大时把 `POST_CROP_BOTTOM_PCT` 调到 `0.10~0.12`。

---

## 18.4 端到端 runbook（印尼）

### 一键脚本（推荐）

`scripts/run_indonesia.py` 把「采集 → 印尼语文案 → 底部裁切 → 发布」串成一条命令：

```powershell
# 默认：backpackers 印尼版(f=54)，5 账号，10 个多图帖，印尼语，自动裁 bbkz 水印
py -3 scripts/run_indonesia.py --accounts-csv accounts_5.csv --posts 10

# 图库源（Pexels + Pixabay，印尼关键词）
py -3 scripts/run_indonesia.py --source stock --accounts-csv accounts_10.csv --posts 50

# 只采集 + 文案、不发布（预演）
py -3 scripts/run_indonesia.py --posts 5 --skip-publish

# 无人值守
py -3 scripts/run_indonesia.py --accounts-csv accounts_5.csv --posts 10 --yes
```

关键参数：

| 参数 | 说明 | 默认 |
| ---- | ---- | ---- |
| `--source` | `backpackers`（f=54 多图） / `stock`（Pexels+Pixabay） | `backpackers` |
| `--accounts-csv` | 账号 CSV（不入库） | `accounts_5.csv` |
| `--posts` | 发布帖子数（=采集条数） | `10` |
| `--langs` | 文案语言 | `id`（印尼语） |
| `--crop-pct` | 底部水印裁切比例 | `0.08` |
| `--skip-publish` / `--yes` | 只产素材 / 免确认 | 关 |

中间产物落 `id_run/`，报告落 `result/publish_*.csv`。

### 分步执行

```powershell
py -3 scripts/fetch_backpackers_my.py --fid 54 --posts 10 --imgs-per-post 9 `
    --min-imgs 4 --listing-pages 4 --dedupe-file id_used_threads.json --output id_raw.csv
$env:DEFAULT_SCENE = "travel"
py -3 scripts/caption_multilang.py --input id_raw.csv --output moments_id.csv --langs id
py -3 scripts/publish_from_tokens.py --accounts-csv accounts_5.csv --csv moments_id.csv --concurrency 3
```

---

## 18.5 安全

- 沿用 `docs/09-security.md`：**不入库**任何账号 CSV / `.env` / token。
- `.env.example` 的 `POST_CROP_BOTTOM_HOSTS` 默认已含 `bbkz.net`。
