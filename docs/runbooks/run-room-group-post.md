# Runbook：群组 / 房间发帖并在群聊显示

## 目标

把图文 / 文字动态发布到指定**群组 / 房间**，并让它**作为消息出现在群聊里**
（两步：创建动态 + 发送群消息）。原理见 [`docs/21-room-group-post.md`](../21-room-group-post.md)。

## 前置

- 已完成 [`docs/02-environment.md`](../02-environment.md) 的准备。
- 有**目标房间的发帖权限**（发帖账号需为房间创建者，否则后端 `50006` 拒绝）。
- 拿到目标房间的 **Matrix room_id**（形如 `!yourRoomId:xxai.com`）。
- 依赖：`pip install requests boto3`（外部图片转存 S3 需要 boto3）。
- PowerShell 先设 UTF-8：

  ```powershell
  $env:PYTHONIOENCODING = "utf-8"
  $env:PYTHONUTF8 = "1"
  ```

- 账号 / 房间用环境变量传入（不写进命令行历史 / 脚本）：

  ```powershell
  $env:ROOM_POST_EMAIL    = "your_account@example.com"
  $env:ROOM_POST_PASSWORD = "your_password"
  $env:ROOM_POST_ROOM_ID  = "!yourRoomId:xxai.com"
  ```

## 场景 A — 纯文字帖

```powershell
py -3 scripts/post_room_moments.py --text "大家好呀～今天天气不错，有一起出来玩的朋友吗？"
```

## 场景 B — 从 tuziyouwang 抓图发多图帖（2/4 混合）

因为该源每个详情页只有 1 张原图，脚本会**聚合多篇的图**成多图帖：

```powershell
# 5 条帖, 分别 4/4/2/4/2 张图, 文案依次取自文案文件
py -3 scripts/post_room_moments.py `
    --tuzi-column xiongqi `
    --group-plan 4,4,2,4,2 `
    --captions-file templates/room_captions.example.txt `
    --delay 1.5
```

- 换栏目：`--tuzi-column meitui` / `fengtun` / `xiaoneinei` / `gengduo`。
- 固定张数：`--group-size 9 --num-posts 3`（发 3 条九宫格）。
- 不给 `--captions-file` 时用占位文案 `分享 #N`。

## 场景 C — 从 CSV 素材发布

CSV 表头与个人发帖一致（`room_id` 列可留空，用 `--room-id` 覆盖）：

```csv
content,visibility,room_id,is_async,image_urls,location_name,location_address,location_lat,location_lon
"周末打卡～今日穿搭分享",0,!yourRoomId:xxai.com,false,https://.../a.jpg,,,,
```

```powershell
py -3 scripts/post_room_moments.py --csv moments_room.csv
# 或统一覆盖房间：--room-id !yourRoomId:xxai.com
```

- `image_urls` 里的**外部 URL** 会自动下载并转存 S3，再用站内 URL 发布。
- `is_async` 列：`true`=同时发广场；空 / `false`=只进群。

## 广场开关（is_async）

- **默认 `false`**：只发到群，不复制到广场。
- 加 `--square`：`is_async=true`，发群的同时再发一条公开广场帖。

## 先看不发（dry-run）

```powershell
py -3 scripts/post_room_moments.py --tuzi-column xiongqi --group-plan 4,4,2 --dry-run
```

只装配并打印将发布的帖子（房间 / 图片数 / 文案），不实际调用发帖接口。

## 验收

### A. 看脚本输出

预期结尾：`完成: 成功 N/N 条`，逐条列出 `moment_id` 与图片数。

### B. 读房间 feed 核对

```powershell
$token = "<用发帖账号登录拿到的 token>"
$room  = $env:ROOM_POST_ROOM_ID
Invoke-RestMethod -Method Get `
  -Uri "$($env:ROOM_FEED_URL)?room_id=$room&page_size=10" `
  -Headers @{ Authorization = "Bearer $token" } |
  Select-Object -ExpandProperty data
```

确认刚发的帖子在房间 feed 顶部、图片张数正确。

## 排错

| 现象 | 原因 / 处理 |
| ---- | ---- |
| 第1步 `code=50006 只有房间创建者可以在该房间发帖` | 发帖账号无该房间发帖权限，换房间创建者账号 |
| 第2步 HTTP 403 / 401 | token 与房间不匹配或已过期，重新登录 |
| emoji 报 `UnicodeEncodeError` | 忘了设 `PYTHONUTF8=1` |
| 外部图片下载失败 | 该源需要 Referer；脚本已对 tuzi 设好，其他源在 `.env` 里配 Referer |
