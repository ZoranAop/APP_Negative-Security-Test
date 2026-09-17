# Skill: Pexels Video Publish

> 当用户说「发布 pexels 视频」/「publish pexels video」/「pexels 视频发帖」时，使用此技能。
> 对应仓库：`xxai-square-publisher`
> 主脚本：`scripts/run_pexels_video.py`
> 文档：`docs/25-pexels-video-publish.md`

---

## 快速调用（推荐）

直接运行仓库脚本：

```powershell
py -3 scripts/run_pexels_video.py `
    --theme {theme} `
    --nick-filter {en|jp|cn|random|auto} `
    --count {n} `
    --yes
```

**可选参数：**
- `--caption-lang ja` — 日文描述
- `--accounts-csv pre_企管用户_街拍摄影师.csv` — 自定义账号池
- `--no-dedupe` — 跳过 Pexels 视频 ID 去重
- `--post-delay 3` — 发帖间隔（秒，默认 5）

---

## 可用主题

| `--theme` | Pexels 搜索词 | 描述示例 |
|-----------|--------------|---------|
| `cambodia` | 柬埔寨 | "Wandering through old Cambodia..." |
| `tokyo` | 东京 | "Shinjuku at night. The neon never turns off..." |
| `japan` | 日本 | "The temple gates open before the sun..." |
| `korea` | 韩国 | "Seoul, late afternoon. The city slows down..." |
| `india` | 印度 | "Jaipur at golden hour. The pink city earns its name..." |
| `southeast-asia` | 东南亚 | "Bangkok's Grand Palace at sunrise..." |

---

## 昵称筛选规则（`--nick-filter`）

| 值 | 含义 | 回退顺序 |
|----|------|---------|
| `en` | 纯英文昵称 | en → random → cn → jp |
| `jp` | 日文昵称（假名/にこまる/星の） | jp → en → random → cn |
| `cn` | 中文昵称（CJK 汉字） | cn → en → random → jp |
| `random` | 非 en/jp/cn 的其他昵称 | random → en → cn → jp |
| `auto` | 优先 en，不够用 random 补 | en → random → cn → jp |

已使用账号自动排除（通过 `result/tokens.json` 跟踪）。

---

## 工作流程

```
1. 发现视频
   已知 Pexels 视频 ID（KNOWN_VIDEO_IDS）
   或 抓取 Pexels 搜索页 → download redirect 验证

2. 去重
   读取 data/used_pexels_video_ids.json
   跳过已发布过的视频 ID

3. 选账号
   按昵称分类筛选，排除已用账号
   顺序登录（2.5s 间隔，429 指数退避）

4. 上传
   获取 S3 凭证（anchor token）
   下载 MP4 + 封面图 → 上传 S3
   封面图：先试 Pexels 图片 URL，失败则用视频文件做 fallback

5. 发帖
   POST media_info: {type: video, video_url, thumbnail_url}
   每个帖间隔 post-delay 秒（默认 5s）

6. 记录
   更新 data/used_pexels_video_ids.json
   生成 result/publish_pexels_{theme}_{ts}.csv 报告
```

---

## 不启用评论

此技能**不触发评论发布**。如需评论，单独调用：

```powershell
# 批量评论（670 账号池，多语言）
py -3 scripts/run_comments_generic.py `
    --report result/publish_pexels_{theme}_{ts}.csv `
    --pool 670 `
    --topic general `
    --lang-mix "en:0.6:ja:0.2:zh_hant:0.1:ko:0.1" `
    --min-comments 2 --max-comments 5 `
    --yes
```

---

## 已知有效 Pexels 视频 ID

存储在脚本 `KNOWN_VIDEO_IDS` 中。新增主题时在 `scripts/run_pexels_video.py` 顶部追加即可。

**验证视频 ID 是否可用：**
```python
import requests
r = requests.get(
    f"https://www.pexels.com/download/video/{vid}/",
    timeout=15, allow_redirects=False, verify=False,
    headers={"User-Agent": "Mozilla/5.0"}
)
# 302 + Location 含 "video-files" → 有效
```

---

## 封面图处理

```
优先级：
1. https://images.pexels.com/videos/{vid}/pexels-photo-{vid}.jpeg
2. https://images.pexels.com/videos/{vid}/{vid}.jpeg
3. Fallback: 视频文件本身（S3 接受 .mp4 作为 thumbnail）
```

> Pexels 有 Cloudflare 限制，部分视频的封面图无法直接获取。
> 使用视频文件做 fallback 时，服务端会自动生成预览帧，视觉效果可接受。

---

## 错误处理速查

| 错误 | 处理 |
|------|------|
| Pexels 下载 403 | 加 `verify=False` + `Referer: https://www.pexels.com/` |
| 大文件下载中断（4K） | 自动 3 次重试，`Range` 请求头断点续传 |
| 登录 429 | 指数退避：`2.5 × 2^n` 秒 |
| Token 过期 | 自动重新登录重试一次 |
| 封面图 404 | 自动 fallback 到视频文件 |

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `scripts/run_pexels_video.py` | 主脚本 |
| `docs/25-pexels-video-publish.md` | 完整文档 |
| `data/used_pexels_video_ids.json` | 去重账本 |
| `result/publish_pexels_*.csv` | 发布报告 |
| `result/tokens.json` | 全局 token 缓存 |
