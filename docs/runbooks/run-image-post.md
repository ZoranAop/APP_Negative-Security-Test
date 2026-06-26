# Runbook：图文批量发帖

## 目标

用 10 个企管账号，向 XXAI 广场各发 1 条 OpenNana 风格图文。

## 前置

- 已完成 [`docs/02-environment.md`](../02-environment.md) 的 4 步准备。
- `.env` 已填好。
- 工作目录有 `accounts_10.csv`。

## 步骤

```powershell
# Step 1 — 拉素材（10 条）
py -3 scripts/opennana_fetch.py `
    --media-type image `
    --page 1 `
    --limit 10 `
    --output moments_gallery_v2.csv

# Step 2 —（可选）人工 / LLM 改写文案
#   把 moments_gallery_v2.csv 里的 content 列改成用户口吻
#   规则见 docs/04-content-pipeline.md §4.2

# Step 3 — 批量发帖
py -3 scripts/post_moments.py `
    --accounts-csv accounts_10.csv `
    --csv moments_gallery_v2.csv `
    --num-accounts 0 `
    --num-posts 0 `
    --concurrency 1 `
    --delay 2.0
```

## 验收

```powershell
$latest = Get-ChildItem result\post_results_*.csv | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Import-Csv $latest.FullName | Group-Object status | Format-Table -AutoSize
```

预期：`success = 10`，`failed = 0`。
