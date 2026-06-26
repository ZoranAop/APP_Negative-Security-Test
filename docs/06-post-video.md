# 06. 视频发布方法（重点）

`post_moments.py` **原生不支持视频**，需要单独走 `post_video.py`。通过 OpenAPI 文档（`${OPENAPI_DOC_URL}`）已确认正确的 payload 结构。

## 6.1 关键结论：视频 `media_info` 格式

```json
{
  "media_info": {
    "type": "video",
    "video_url":     "https://teststatic-x.tp-ex.com/square/original/YYYY/MM/DD/xxx.mp4",
    "thumbnail_url": "https://teststatic-x.tp-ex.com/square/original/YYYY/MM/DD/xxx.png"
  }
}
```

- 字段必须是 **snake_case**：`video_url` / `thumbnail_url`。
- camelCase（`videoUrl`）会被服务端拒绝：

  ```json
  { "code": 20005, "msg": "媒体信息格式错误" }
  ```

- 图文则为：

  ```json
  { "type": "image", "images": [ ... ] }
  ```

- 纯文字：

  ```json
  { "type": "text" }
  ```

## 6.2 完整流程（`post_video.py`）

```
1. 登录拿 token
2. POST /file/upload/credentials 拿 S3 临时凭证
   → access_key_id / secret_access_key / session_token / region / bucket / domain
3. 从 OpenNana 下载 mp4 + 封面图
   请求头必须带：
     User-Agent: <桌面浏览器 UA>
     Referer:    https://opennana.com/
   （否则会被防盗链 403）
4. boto3 上传到 S3
   key 格式: square/original/YYYY/MM/DD/{文件名}
   ContentType:
     - 视频:  video/mp4
     - 封面:  image/png（按后缀判断）
5. 拼接公网 URL: https://{domain}/{key}
6. POST /api/v1/moments/ 发布
   body 含上面的 video media_info
```

## 6.3 已发布案例

- **案例**：「十二花神绝美卡点变装」
- 账号：`u_1wvpv9ak`
- `moment_id`：`722391747824455680`

## 6.4 ⚠️ 探测格式时产生的废帖

确认视频格式过程中，曾用占位 URL 探测过 4 条无效测试帖（账号 `u_1wvpv9ak`）：

```
722391483944013824
722391487538532352
722391488587108352
722391492936601600
```

清理方法：

```http
DELETE ${MOMENTS_API_URL}/{moment_id}
Authorization: Bearer <token>
```
