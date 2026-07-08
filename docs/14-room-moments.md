# 14. 群组 / 房间发帖（Room Moments）

> 把动态发到某个**群组 / 房间（room）**，而不是发到个人动态。
> 本章基于后端 OpenAPI（`${OPENAPI_DOC_URL}`，Swagger UI 在 `/docs`）整理，
> 与个人发帖复用同一套 `POST /api/v1/moments` 接口——只是多带一个 `room_id`。

最近更新：2026-07-07

---

## 14.1 与个人发帖的关系

发帖用的是**同一个接口** `POST ${MOMENTS_API_URL}`：

- `room_id` **为空 / 不传** → 发到发帖人**个人动态**（即前面 03 章讲的默认玩法）。
- `room_id` **非空** → 发到对应**群组 / 房间**。

所以脚本层面无需换脚本：`scripts/post_moments.py` 已支持从素材 CSV 的
`room_id` 列读取并写进请求体（见 §14.4）。

## 14.2 发布到房间：`POST /api/v1/moments`

| 项目     | 值                                                        |
| -------- | --------------------------------------------------------- |
| 方法     | `POST`                                                    |
| 地址     | `${MOMENTS_API_URL}`（默认 `http://100.64.0.47:8889/api/v1/moments/`） |
| 认证     | `Authorization: Bearer <token>`（先用 `POST ${LOGIN_URL}` 换 token） |
| Content-Type | `application/json`                                    |

### 请求体字段

| 字段            | 类型    | 必填 | 说明                                                                 |
| --------------- | ------- | ---- | -------------------------------------------------------------------- |
| `content`       | string  | ✅   | 正文内容                                                             |
| `room_id`       | string  | ❌   | **房间 ID；为空则发到个人动态**。群组发帖就靠这个字段                 |
| `visibility`    | integer | ❌   | 可见性：`0=公开` / `1=私密` / `2=部分可见`                           |
| `is_async`      | boolean | ❌   | 是否异步发布公开版本（默认 `false`）。当 `room_id` 非空且此值为 `true` 时，**同步再发一个 `room_id` 为空的公开帖子** |
| `is_vip_group`  | boolean | ❌   | VIP 群组标识                                                         |
| `media_info`    | object  | ❌   | 媒体信息，见下表；纯文字帖可省略或传 `{"type":"text"}`               |
| `location`      | object  | ❌   | 位置信息：`name` / `address` / `latitude` / `longitude`（四项均必填）|

`media_info` 结构：

| 字段                     | 类型          | 说明                                       |
| ------------------------ | ------------- | ------------------------------------------ |
| `type`                   | string ✅     | `text` / `image` / `video` / `forward`     |
| `images`                 | array<string> | 图片 URL 列表（`type=image` 时；最多 9 张）|
| `video_url`              | string        | 视频 URL（`type=video` 时）                |
| `thumbnail_url`          | string        | 缩略图 URL                                 |
| `forwarded_post_id`      | integer       | 转发原动态 ID（`type=forward` 时）         |
| `forwarded_post_user_id` | integer       | 转发原动态作者用户 ID                      |
| `forwarded_desc`         | string        | 转发说明 / 摘要文案                        |

### 请求示例

```bash
curl -X POST "http://100.64.0.47:8889/api/v1/moments/" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "周末打卡～今日穿搭分享 #今日穿搭",
    "room_id": "10086",
    "visibility": 0,
    "media_info": {
      "type": "image",
      "images": [
        "https://teststatic-x.tp-ex.com/square/original/2026/07/08/a.jpg"
      ]
    }
  }'
```

### 响应

| 字段                | 类型    | 说明                                                   |
| ------------------- | ------- | ------------------------------------------------------ |
| `moment_id`         | integer | 新建动态 ID                                            |
| `public_moment_id`  | integer | 同步发布的公开版动态 ID（**仅** `room_id` + `is_async=true` 时有值）|

> 后端统一响应外层通常是 `{"code":0,"msg":"OK","data":{...}}`；
> `moment_id` 在 `data` 内。脚本里的 `validate_post_response` 已做兼容解析。

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

素材 CSV 表头（`room_id` 是标准列之一）：

```csv
content,visibility,room_id,image_urls,location_name,location_address,location_lat,location_lon
```

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

- **`room_id` 是 string**：CSV 里当字符串填写即可（如 `10086`），不要当成数字处理导致前导 0 丢失。
- **权限**：发帖账号需具备目标房间的发帖权限；无权限时后端会返回非 0 `code`，脚本会记为失败。
- **`is_async` / `is_vip_group`**：这两个字段目前 `post_moments.py` 暂未透传（脚本只透传 `content`/`visibility`/`room_id`/`media_info`/`location`）。若需要"发房间的同时同步发一条公开帖"，请直接按 §14.2 调 HTTP 接口，或在脚本 `build_payload` 中补上这两个字段。
- 全部 `100.64.0.x` 为内网地址，需在 VPN / 内网环境调用。
