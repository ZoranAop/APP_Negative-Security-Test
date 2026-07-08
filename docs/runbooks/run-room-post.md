# Runbook：群组 / 房间批量发帖

## 目标

用 N 个账号，把图文动态**批量发到指定群组 / 房间（room）**，
并可结合仓库能力筛图 + 排除已发（沿用 image-post 的去重账本）。

> 原理：与个人发帖同一个接口 `POST /api/v1/moments`，只是素材 CSV 里多填一列
> `room_id`。详见 [`docs/14-room-moments.md`](../14-room-moments.md)。

## 前置

- 已完成 [`docs/02-environment.md`](../02-environment.md) 的准备，`.env` 已填好。
- 拿到目标**房间 ID（`room_id`，字符串）**，且发帖账号在该房间有发帖权限。
- 工作目录有账号 CSV（如 `accounts_5.csv`）。
- PowerShell 先设 UTF-8，避免文案 emoji 触发 GBK 的 `UnicodeEncodeError`：

  ```powershell
  $env:PYTHONIOENCODING = "utf-8"
  $env:PYTHONUTF8 = "1"
  ```

## 步骤

### Step 1 — 拉素材（自动排除已发图片）

```powershell
py -3 scripts/opennana_fetch.py `
    --media-type image `
    --theme beauty `
    --exclude-ads `
    --page 1 --pages 15 `
    --limit 30 `
    --shuffle-pages `
    --dedupe-file data/used_slugs.json `
    --output result/moments_room_fetched.csv
```

### Step 2 — 改写文案 + 填 room_id

参照 [`docs/04-content-pipeline.md`](../04-content-pipeline.md) §4.2 把提示词改写成
**用户第一人称的自主角色文案**，写回 `moments_room.csv`，并给每行填上 `room_id`：

```csv
content,visibility,room_id,is_async,is_vip_group,image_urls,location_name,location_address,location_lat,location_lon
"周末打卡～今日穿搭分享 #今日穿搭",0,!wYYcMFpnG0b0Keot:xxai.com,true,,https://.../a.jpg,,,,
"深夜书房，安静地看会儿书 #清冷感",0,!wYYcMFpnG0b0Keot:xxai.com,true,,https://.../b.jpg,,,,
```

- **整批发同一个房间**：所有行 `room_id` 填同一个值。
- **不同房间**：逐行填不同 `room_id`。
- **混合个人 + 房间**：部分行留空 `room_id` 即发个人动态。
- `is_async=true`（配非空 `room_id`）：后端会同步再发一条公开帖，响应含 `public_moment_id`。
- `is_vip_group=true`：收费 / VIP 群场景。

> `room_id` 是 **Matrix 风格字符串**（`!xxx:xxai.com`），原样填、别当数字。

### Step 3 — 批量发帖

命令与个人发帖一致（room_id 已在 CSV 里）：

```powershell
py -3 scripts/post_moments.py `
    --accounts-csv accounts_5.csv `
    --csv moments_room.csv `
    --num-accounts 0 --num-posts 0 `
    --concurrency 1 --delay 2.0
```

### Step 4 — 记录已发图片（供下次排除）

```powershell
py -3 scripts/record_sent_slugs.py `
    --from-csv result/moments_room_fetched.csv `
    --dedupe-file data/used_slugs.json
```

## 验收

### A. 看发帖脚本结果

```powershell
$latest = Get-ChildItem result\post_results_*.csv | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Import-Csv $latest.FullName | Group-Object status | Format-Table -AutoSize
```

预期：`success = 全部`，`failed = 0`。

### B. 直接读房间动态确认（可选）

用任一发帖账号的 token 调 `GET /api/v1/feed/room_moments` 核对刚发的帖子是否在房间里：

```powershell
$token = "<用某账号登录拿到的 token>"
$room  = "10086"
Invoke-RestMethod -Method Get `
  -Uri "http://100.64.0.47:8889/api/v1/feed/room_moments?room_id=$room&page_size=20" `
  -Headers @{ Authorization = "Bearer $token" } |
  Select-Object -ExpandProperty data
```

> 游标翻页：把返回 `list` 最后一条的 `id` 作为下次的 `last_id`，直到 `has_more=false`。

## 单条发到房间（不走 CSV，直接调接口）

脚本已支持通过 CSV 的 `is_async` / `is_vip_group` 列透传，所以一般不需要手写 HTTP。
但如果想临时验一条、或走客户端的 feed 域名，可直接调：

```powershell
$token = "<token>"
$body = @{
  content    = "群里也发一条～ #分享"
  room_id    = "!wYYcMFpnG0b0Keot:xxai.com"
  visibility = 0
  is_async   = $true
  media_info = @{ type = "image"; images = @("https://.../a.jpg") }
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post `
  -Uri "https://testapi-feed-x.tp-ex.com/api/v1/moments" `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body $body
```

返回里 `moment_id` 是房间帖、`public_moment_id` 是同步的公开帖（均为字符串 id）。

> 内网压测环境可把 URL 换成 `${MOMENTS_API_URL}`（如 `http://100.64.0.53:8889/api/v1/moments/`）。
