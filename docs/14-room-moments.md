# 14. 群组 / 房间发帖（Room Moments）

> 把动态发到某个**群组 / 房间（room）**，而不是发到个人动态。
> 本章基于后端 OpenAPI（`${OPENAPI_DOC_URL}`）+ **iOS 客户端真实抓包**（2026-07-07）整理，
> 与个人发帖复用同一套 `POST /api/v1/moments` 接口——只是多带一个 `room_id`。

最近更新：2026-07-07（补充抓包实测：feed 域名 / Matrix room_id / is_async 双 id / forwarded_user_* 字段）

---

## 14.1 与个人发帖的关系

发帖用的是**同一个接口** `POST .../api/v1/moments`：

- `room_id` **为空 / 不传** → 发到发帖人**个人动态**（即前面 03 章讲的默认玩法）。
- `room_id` **非空** → 发到对应**群组 / 房间**。

所以脚本层面无需换脚本：`scripts/post_moments.py` 已支持从素材 CSV 的
`room_id` 列读取并写进请求体（见 §14.4）。

## 14.1.1 发帖端点（两个，注意区分）

| 场景             | 端点                                                                 |
| ---------------- | -------------------------------------------------------------------- |
| **客户端实测**（外网 / 抓包所见） | `POST https://testapi-feed-x.tp-ex.com/api/v1/moments`               |
| **内网直连**（仓库 `.env` 默认 / 压测） | `POST ${MOMENTS_API_URL}`（test 默认 `http://100.64.0.53:8889/api/v1/moments/`；dev 为 `100.64.0.47`）|

> 两个端点是同一套接口的不同接入地址：iOS App 走 feed 网关域名
> `testapi-feed-x.tp-ex.com`，脚本压测走内网 `100.64.0.x`。
> 用哪个取决于你的网络环境；字段完全一致。脚本通过 `.env` 的 `MOMENTS_API_URL`
> 或 `--api-url` 指定，也可直接填 feed 域名。

## 14.2 发布到房间：`POST /api/v1/moments`

| 项目     | 值                                                        |
| -------- | --------------------------------------------------------- |
| 方法     | `POST`                                                    |
| 地址     | 见 §14.1.1（`https://testapi-feed-x.tp-ex.com/api/v1/moments` 或 `${MOMENTS_API_URL}`）|
| 认证     | `Authorization: Bearer <token>`（先用 `POST ${LOGIN_URL}` 换 token） |
| Content-Type | `application/json`                                    |

客户端另外会带一组设备类请求头（脚本压测**非必需**，仅记录以备排查）：
`Accept-Language: zh-Hans`、`Device-Id`、`Device-Name`（如 `iPhone`）、
`Device-OS`（如 `iOS`）、`Device-OS-Version`、`App-Version`（如 `1.3.0`）、
`App-Version-Build`。

### 请求体字段

| 字段            | 类型    | 必填 | 说明                                                                 |
| --------------- | ------- | ---- | -------------------------------------------------------------------- |
| `content`       | string  | ✅   | 正文内容                                                             |
| `room_id`       | string  | ❌   | **房间 ID；为空则发到个人动态**。是 **Matrix 风格 ID**，形如 `!wYYcMFpnG0b0Keot:xxai.com`（带 `!` 前缀、`:xxai.com` 后缀），**必须原样当字符串传**|
| `visibility`    | integer | ❌   | 可见性：`0=公开` / `1=私密` / `2=部分可见`                           |
| `is_async`      | boolean | ❌   | 是否异步发布公开版本（默认 `false`）。当 `room_id` 非空且此值为 `true` 时，**同步再发一个 `room_id` 为空的公开帖子**，响应额外返回 `public_moment_id`|
| `is_vip_group`  | boolean | ❌   | VIP 群组标识（如"收费群"场景）                                       |
| `media_info`    | object  | ❌   | 媒体信息，见下表；纯文字帖可省略或传 `{"type":"text"}`               |
| `location`      | object  | ❌   | 位置信息：`name` / `address` / `latitude` / `longitude`（四项均必填）|

`media_info` 结构：

| 字段                       | 类型          | 说明                                       |
| -------------------------- | ------------- | ------------------------------------------ |
| `type`                     | string ✅     | `text` / `image` / `video` / `forward`     |
| `images`                   | array<string> | 图片 URL 列表（`type=image` 时；最多 9 张）|
| `video_url`                | string        | 视频 URL（`type=video` 时）                |
| `thumbnail_url`            | string        | 缩略图 URL                                 |
| `forwarded_post_id`        | integer       | 转发原动态 ID（`type=forward` 时）         |
| `forwarded_post_user_id`   | integer       | 转发原动态作者用户 ID                      |
| `forwarded_user_name`      | string        | 转发原动态作者昵称（抓包所见）             |
| `forwarded_user_avatar`    | string        | 转发原动态作者头像 URL（抓包所见）         |
| `forwarded_desc`           | string        | 转发说明 / 摘要文案                        |

> 客户端会把 `media_info` 里用不到的字段显式传 `null`（如非转发场景下的
> `video_url`/`thumbnail_url`/`forwarded_*` 全为 `null`）。脚本这边**省略不传**
> 这些字段即可，效果等价。

### 请求示例（对应真实抓包：VIP 群图文 + is_async）

```bash
curl -X POST "https://testapi-feed-x.tp-ex.com/api/v1/moments" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -H "Accept-Language: zh-Hans" \
  -d '{
    "content": "收费群帖子",
    "room_id": "!wYYcMFpnG0b0Keot:xxai.com",
    "is_async": true,
    "media_info": {
      "type": "image",
      "images": [
        "https://teststatic-x.tp-ex.com/square/original/2026/07/07/6848609a15f5aa3fb328f2c9523fa57b.jpeg"
      ]
    }
  }'
```

### 响应

| 字段                | 类型   | 说明                                                   |
| ------------------- | ------ | ------------------------------------------------------ |
| `moment_id`         | string | 新建动态 ID（房间帖）。**实测返回字符串**，如 `"729599881982775296"`|
| `public_moment_id`  | string | 同步发布的公开版动态 ID（**仅** `room_id` + `is_async=true` 时有值），如 `"729599881995358208"`|

真实响应体示例：

```json
{ "moment_id": "729599881982775296", "public_moment_id": "729599881995358208" }
```

> 后端统一响应外层通常是 `{"code":0,"msg":"OK","data":{...}}`，`moment_id` 在 `data` 内；
> 抓包里直接看到的是 `data` 层。脚本的 `validate_post_response` 已 `str()` 兼容
> 字符串 / 数字两种 id，无需担心类型。

## 14.3 读取房间动态：`GET /api/v1/feed/room_moments`

用于**核对发帖结果 / 分页浏览某房间的动态**（也可用来做房间级去重）。

| 参数        | 位置  | 必填 | 说明                                       |
| ----------- | ----- | ---- | ------------------------------------------ |
| `room_id`   | query | ✅   | 房间 ID                                    |
| `page_size` | query | ✅   | 每页数量（默认 20）                        |
| `last_id`   | query | ❌   | 上一页最后一条动态 ID（首次不传或传 `0`）  |

响应：

| 字段        | 类型          | 说明                       |
| ----------- | ------------- | -------------------------- |
| `list`      | array<moment> | 动态列表（含 `id` / `user_id` / `user_name` / `content` / `media_info` / 各类计数 / `created_at` 等）|
| `has_more`  | boolean       | 是否还有下一页             |

分页方式为**游标翻页**：拿本页 `list` 最后一条的 `id` 作为下一次的 `last_id`，直到 `has_more=false`。

```bash
curl "http://100.64.0.47:8889/api/v1/feed/room_moments?room_id=10086&page_size=20" \
  -H "Authorization: Bearer <token>"
```

## 14.4 用脚本批量发到房间（推荐）

`scripts/post_moments.py` 会读取素材 CSV 的 `room_id` 列并写进请求体。
只要在 CSV 里**填上 `room_id`**，就是群组发帖；**留空**就是个人动态。

素材 CSV 表头（`room_id` / `is_async` / `is_vip_group` 均为可选列）：

```csv
content,visibility,room_id,is_async,is_vip_group,image_urls,location_name,location_address,location_lat,location_lon
```

示例（对应"收费群 + 同步发公开帖"）：

```csv
content,visibility,room_id,is_async,is_vip_group,image_urls,location_name,location_address,location_lat,location_lon
"收费群帖子",0,!wYYcMFpnG0b0Keot:xxai.com,true,true,https://teststatic-x.tp-ex.com/square/original/2026/07/07/xxx.jpeg,,,,
```

- `room_id`：**Matrix 风格字符串**（`!xxx:xxai.com`），CSV 里原样填。
- `is_async`：`true` / `false`（或 `1` / `0`）。`room_id` 非空且 `true` 时，后端会
  同步再发一条公开帖，响应含 `public_moment_id`。空 = 用后端默认（`false`）。
- `is_vip_group`：`true` / `false`（或 `1` / `0`）。空 = 不透传。
- **整批发到同一个房间**：把该批所有行的 `room_id` 填成同一个 ID。
- **不同帖子发到不同房间**：逐行填不同 `room_id`。
- **混合**：部分行填 `room_id`（发房间），部分行留空（发个人）。

发帖命令与个人发帖完全一致（room_id 藏在 CSV 里）：

```powershell
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
py -3 scripts/post_moments.py `
    --accounts-csv accounts_5.csv `
    --csv moments_room.csv `
    --num-accounts 0 --num-posts 0 `
    --concurrency 1 --delay 2.0
```

> 轮询规则不变：`帖子数 ÷ 账号数 = 每账号帖数`。
> 图片仍会自动下载并转存 S3 后再发布（见 03 章）。

完整可照抄流程见 [`runbooks/run-room-post.md`](runbooks/run-room-post.md)。

## 14.5 其他相关接口（同一 token 即可调用）

| 用途           | 方法 + 地址                        | 关键字段                              |
| -------------- | ---------------------------------- | ------------------------------------- |
| 修改动态       | `PUT /api/v1/moments`              | `moment_id`✅；`content`/`media_info`/`visibility`/`location` 传则改、不传不改；`media_info` 传 `{}` 清空媒体 |
| 删除动态       | `DELETE /api/v1/moments`           | `moment_id`✅ → 返回 `success`         |
| 分享动态       | `POST /api/v1/moments/share`       | `moment_id`✅ → `share_count+1`        |
| 动态详情       | `GET /api/v1/moments/detail`       | `moment_id`✅                          |

## 14.6 注意事项

- **`room_id` 是 Matrix 风格字符串**：形如 `!wYYcMFpnG0b0Keot:xxai.com`（带 `!` 前缀、`:xxai.com` 后缀）。CSV 里原样填字符串，**不要**当数字处理、也不要去掉前后缀。
- **响应 id 是字符串**：`moment_id` / `public_moment_id` 实测返回字符串（如 `"729599881982775296"`），脚本已 `str()` 兼容。
- **权限**：发帖账号需具备目标房间的发帖权限；无权限时后端会返回非 0 `code`，脚本会记为失败。
- **`is_async` / `is_vip_group` 已支持透传**：在素材 CSV 里加 `is_async` / `is_vip_group` 列（`true`/`false` 或 `1`/`0`）即可，`scripts/post_moments.py` 的 `build_payload` 会解析并写进请求体（空值不透传，用后端默认）。
- **两个发帖端点**：客户端走 `https://testapi-feed-x.tp-ex.com/api/v1/moments`，脚本压测走内网 `${MOMENTS_API_URL}`（`100.64.0.x`）。二者字段一致，按网络环境选一个。
- 全部 `100.64.0.x` 为内网地址，需在 VPN / 内网环境调用。
