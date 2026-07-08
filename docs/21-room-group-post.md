# 21. 群组 / 房间发帖并在群聊显示（Room Group Post）

> 把动态发布到某个**群组 / 房间（Matrix room）**，并让它**作为一条消息出现在群聊里**。
> 用 `scripts/post_room_moments.py` 一个脚本跑通「创建动态 + 发送群消息」两步。

最近更新：基于 iOS 客户端真实抓包 + 内网压测联调整理。

---

## 21.1 为什么需要"两步"

发到房间和发到个人动态是**同一个接口** `POST .../api/v1/moments`，只是多带一个
`room_id`（见 `docs/03-post-moments.md` / `docs/14-*`）。但**只做这一步**时，
动态虽然进入了房间的 feed（`GET /api/v1/feed/room_moments` 能查到），
却**不会作为一条消息出现在群聊界面**。

要让帖子在群聊里显示，必须补上第 2 步：向 Matrix `m.room.message` 端点
PUT 一条 `xxai.fee_message`，把刚创建的 `moment_id` 作为 `post_id` 挂上去。

```
第1步  POST  ${MOMENTS_API_URL}                                  -> moment_id
第2步  PUT   ${MATRIX_API_BASE}/{room}/send/m.room.message/{txn} -> event_id (群聊显示)
```

## 21.2 认证：一枚 token 走两个接口

先用 `POST ${LOGIN_URL}` 换登录响应，其 `data` 同时给出两样东西：

```json
{ "code": 0, "data": { "token": "<access_token>", "mxid": "@user_26:xxai.com" } }
```

| 字段    | 用途                                                        |
| ------- | ----------------------------------------------------------- |
| `token` | **同一枚** token 兼容发帖 API（Bearer）和 Matrix 消息接口   |
| `mxid`  | Matrix 用户 ID，用来构造第 2 步的事务 ID `txn`              |

> **权限**：发帖账号必须是目标房间的**创建者 / 有发帖权限**，否则第 1 步返回
> `code=50006 只有房间创建者可以在该房间发帖`。

## 21.3 第 1 步：创建动态 `POST /api/v1/moments`

| 端点 | 说明 |
| ---- | ---- |
| `${ROOM_MOMENTS_API_URL}` | 房间发帖端点。默认走 feed 网关域名 `https://testapi-feed-x.tp-ex.com/api/v1/moments`（客户端实测），也可用内网 `${MOMENTS_API_URL}` |

请求体（房间发帖关键字段）：

| 字段          | 类型    | 说明                                                                 |
| ------------- | ------- | -------------------------------------------------------------------- |
| `content`     | string  | 正文                                                                 |
| `room_id`     | string  | **Matrix 风格房间 ID**，如 `!yourRoomId:xxai.com`（原样字符串） |
| `is_async`    | boolean | **广场发帖开关**，见 §21.5                                           |
| `media_info`  | object  | `{"type":"text"}` 或 `{"type":"image","images":[...]}`（最多 9 张）  |

响应：`{"code":0,"data":{"moment_id":"729..."}}`。

## 21.4 第 2 步：群消息 `PUT .../send/m.room.message/{txn}`

- URL：`${MATRIX_API_BASE}/{urlencode(room_id)}/send/m.room.message/{urlencode(txn)}`
- `txn`（事务 ID）：`{mxid}-11-{毫秒时间戳}`，保证幂等去重
- 请求体：

```json
{
  "msgtype": "xxai.fee_message",
  "body": "正文",
  "content": "正文",
  "post_id": "729...",          // 第1步拿到的 moment_id
  "is_sync": false,
  "images_url": ["https://teststatic-x.tp-ex.com/.../a.jpg"],
  "video_url": "",
  "video_thumnail": ""           // 注意：后端接口原拼写就是 thumnail
}
```

响应：`{"event_id":"$xxxx"}` —— 帖子已显示在群聊中。

## 21.5 `is_async`：广场发帖开关（true → false）

`room_id` 非空时：

| 值                | 效果                                                                 |
| ----------------- | -------------------------------------------------------------------- |
| `is_async=true`   | 发到房间的同时，后端**再复制一条公开帖到广场**（响应含 `public_moment_id`）|
| `is_async=false`  | **只发到房间，不进广场**（脚本默认）                                  |

脚本默认 `is_async=false`；加 `--square` 才会同时发广场。

## 21.6 多图聚合

某些图片源（如 tuziyouwang.com）每个详情页**只有 1 张原图**。要发多图帖，
脚本会把**多张图聚合成一条**：

- `--group-size N`：每条帖固定 N 张（如 `--group-size 9` 发九宫格）。
- `--group-plan a,b,c,...`：混合张数，如 `--group-plan 4,4,2,4,2` = 5 条帖分别 4/4/2/4/2 张。

外部图片 URL 会**自动下载并转存 S3**（`POST ${UPLOAD_CREDENTIALS_URL}` 取临时凭证，
`boto3` 上传到 `teststatic-x.tp-ex.com`），再用站内 URL 发布。

## 21.7 快速命令

```powershell
# UTF-8，避免 emoji 触发 GBK 报错
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"

# 账号 / 房间从环境变量读（不写进命令行历史）
$env:ROOM_POST_EMAIL    = "your_account@example.com"
$env:ROOM_POST_PASSWORD = "your_password"
$env:ROOM_POST_ROOM_ID  = "!yourRoomId:xxai.com"

# A. 纯文字帖
py -3 scripts/post_room_moments.py --text "大家好呀～有一起玩的朋友吗？"

# B. 从 tuzi 抓图, 发 5 条多图帖(4/4/2/4/2), 用文案文件
py -3 scripts/post_room_moments.py `
    --tuzi-column xiongqi `
    --group-plan 4,4,2,4,2 `
    --captions-file templates/room_captions.example.txt

# C. 从 CSV 发(room_id 可写在 CSV 的 room_id 列, 或用 --room-id 覆盖)
py -3 scripts/post_room_moments.py --csv moments_room.csv
```

完整流程见 [`runbooks/run-room-group-post.md`](runbooks/run-room-group-post.md)。

## 21.8 核对 / 验收

用同一账号 token 调 `GET ${ROOM_FEED_URL}?room_id=<room>&page_size=N` 看刚发的帖子
是否在房间 feed 顶部、图片张数是否正确：

```powershell
$env:ROOM_FEED_URL  # 默认 http://100.64.0.53:8889/api/v1/feed/room_moments
```

## 21.9 注意事项

- **不硬编码任何凭据**：账号 / 密码 / 房间 ID 一律走环境变量或 `.env`。
- **`room_id` 是 Matrix 风格字符串**（`!xxx:xxai.com`），原样传，别当数字。
- **权限**：非房间创建者会被 `50006` 拒绝。
- **端点**：客户端走 feed 域名 `testapi-feed-x.tp-ex.com`，内网压测走 `100.64.0.x`；
  Matrix 消息走 `testd-x.tp-ex.com`。全部 `100.64.0.x` 需在内网 / VPN 环境。
- `video_thumnail` 是后端接口的原始拼写，勿"纠正"。
