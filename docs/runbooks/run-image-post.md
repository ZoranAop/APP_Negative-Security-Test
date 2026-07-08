# Runbook：图文批量发帖（结合仓库筛图 + 排除已发）

## 目标

结合仓库能力从 OpenNana 图库**筛选美女/人像图片**，改写成自主角色文案，
用 N 个账号向 XXAI 广场发帖，并且**绝不重复发送已经发过的图片**。

> 去重键：**OpenNana 的 prompt `slug`**（每个图库条目唯一）。
> 已发记录统一存放在 [`data/used_slugs.json`](../../data/used_slugs.json)，
> 每次发完追加，下次拉图时自动跳过。

## 前置

- 已完成 [`docs/02-environment.md`](../02-environment.md) 的准备，`.env` 已填好
  （`LOGIN_URL` / `UPLOAD_CREDENTIALS_URL` / `MOMENTS_API_URL` 指向目标环境）。
- 工作目录有账号 CSV（如 `accounts_5.csv`）。
- Windows PowerShell 里先设置 UTF-8，避免文案里的 emoji 触发
  `UnicodeEncodeError`（GBK 控制台）：

  ```powershell
  $env:PYTHONIOENCODING = "utf-8"
  $env:PYTHONUTF8 = "1"
  ```

## 步骤

### Step 1 — 拉素材（自动排除已发图片）

关键：带上 `--dedupe-file data/used_slugs.json`。脚本会**跳过**该文件里
记录过的所有 slug，只产出**没发过的新图**；同时把这一批的 slug 写入 CSV 的
`_slug` 列，便于发完追溯。

```powershell
py -3 scripts/opennana_fetch.py `
    --media-type image `
    --theme beauty `
    --exclude-ads `
    --page 1 --pages 15 `
    --limit 30 `
    --shuffle-pages `
    --dedupe-file data/used_slugs.json `
    --output result/moments_fetched.csv
```

- `--theme beauty`：只保留美女 / 人像题材（关键词过滤）。
- `--exclude-ads`：过滤广告 / 海报 / 商业创意（含中英关键词）。
- `--limit`：本批想要的新图数量（多拉一些留作人工挑选）。
- 产出 `result/moments_fetched.csv`，含 `_slug` 列。

### Step 2 — 改写文案（自主角色内容）

**不要直接用英文提示词。** 参照 [`docs/04-content-pipeline.md`](../04-content-pipeline.md) §4.2：
把每张图的提示词理解后，改写成**用户第一人称的原创分享口吻**，去掉英文原文和
`AI生图` / `Prompt` / `#NanoBananaPro` 等生成标识，配自然中文话题标签 + 适量 emoji。

可以给每个账号设定一个"角色人设"，让同一账号的多条帖子口吻一致
（如：法式复古 / 国风古风 / 韩系清冷 / 居家日常 / 旅行穿搭）。

改写后落到 `moments.csv`（保留 `image_urls`；`_slug` 列可保留也可删除，
发帖脚本会忽略未知列）。轮询规则：`帖子数 ÷ 账号数 = 每账号帖数`，
例如 25 帖 / 5 账号 = 每账号 5 帖（顺序不打乱，`row i → 账号 i%N`）。

若需要多语言主体视角文案，可用
[`caption_multilang.py`](../13-multilang-captions.md)。

### Step 3 — 批量发帖

```powershell
py -3 scripts/post_moments.py `
    --accounts-csv accounts_5.csv `
    --csv moments.csv `
    --num-accounts 0 `
    --num-posts 0 `
    --concurrency 1 `
    --delay 2.0
```

脚本会自动下载外部图片、转存 S3、再发布。

### Step 4 —（关键）记录已发图片，供下次排除

发完后，把这一批实际发出的图片 slug 追加进 `used_slugs.json`。
最省事的做法是直接从 Step 1 的 fetch CSV 读取 `_slug` 列：

```powershell
py -3 scripts/record_sent_slugs.py `
    --from-csv result/moments_fetched.csv `
    --dedupe-file data/used_slugs.json
```

也可以只记录你实际发出的若干 slug：

```powershell
py -3 scripts/record_sent_slugs.py `
    --slugs slug-a slug-b slug-c `
    --dedupe-file data/used_slugs.json
```

> 只要每次都：**Step 1 带 `--dedupe-file` 拉图 → Step 4 回写 slug**，
> 就能保证后续批次永远不会重复发送已发过的图片。

## 验收

```powershell
$latest = Get-ChildItem result\post_results_*.csv | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Import-Csv $latest.FullName | Group-Object status | Format-Table -AutoSize
Import-Csv $latest.FullName | Group-Object poster_account | Format-Table -AutoSize
```

预期：`success = 全部`，`failed = 0`，每个账号帖数 = 总帖数 ÷ 账号数。

## 实战记录（示例：5 用户 × 5 帖 = 25 帖）

- 账号：`accounts_5.csv`（5 个企管账号，各配一个角色人设）。
- 素材：OpenNana `media_type=image`，`--theme beauty --exclude-ads`，共 25 张。
- 文案：25 条第一人称自主角色文案（复古胶片 / 国风 / 韩系 / 居家 / 度假）。
- 结果：**25/25 成功，每账号精确 5 帖**。
- 已发 25 个 slug 已写入 `data/used_slugs.json`，下次拉图自动排除。
