# 22. 真人美女视频发到群组（Real-Beauty Video → Room）

> 采集 opennana **真人**少女/美女/女友/模特 视频（排除卡通/动漫），
> 以**发帖人第一人称口吻**改写文案，发布到群组/房间并在群聊显示。
> 两个脚本：`scripts/fetch_beauty_real.py`（采集+改写）+ `scripts/post_room_video.py`（发布）。

最近更新：在 docs/21（房间发帖）与 docs/06（视频 media_info）基础上补齐
「视频 + 房间两步 + 群聊显示」的组合流程。

---

## 22.1 为什么需要这两个脚本

| 已有脚本 | 视频 | 发房间 | 群聊显示 | 缺口 |
| -------- | ---- | ------ | -------- | ---- |
| `post_video.py` | ✅ | ✅ 有 `--room-id` | ❌ 缺 Matrix 第 2 步 | 视频进房间 feed 但不进群聊 |
| `post_room_moments.py` | ❌ 仅图文 | ✅ 两步 | ✅ | 不支持视频 |

`scripts/post_room_video.py` = 两者结合：
```
登录 -> S3 凭证 -> 下载 opennana mp4+封面 -> 上传 S3
  -> POST moment(room_id, media_info.type=video)      // 第1步, 见 docs/06
  -> PUT  m.room.message(video_url, video_thumnail)   // 第2步, 见 docs/21
```

## 22.2 采集：只要真人美女，排除动漫/卡通

`scripts/fetch_beauty_real.py`：

- `REAL_BLOCK`：命中 anime/cartoon/CG/3D 渲染/插画/机甲/怪物/科幻/宠物/
  武侠奇幻/教程/演讲/产品 等一律丢弃（优先级最高）。
- `STRONG_GIRL` / `GIRL_KEYWORDS`：命中少女/美女/女友/模特/写真/穿搭 等才保留。
- `--dedupe-file`：跳过账本里已发过的 slug，新选中的写回。
- **仍建议人工复核**一遍（关键词无法 100% 判定画面），确认无动漫/非美女漏网。

```powershell
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"
py -3 scripts/fetch_beauty_real.py `
    --limit 10 --start-page 1 --max-pages 30 `
    --dedupe-file result/used_video_slugs.json `
    --output result/beauty_videos.csv
```

## 22.3 文案：发帖人第一人称口吻 + 干净标签

`build_caption()` 的三条硬性规则：

1. **第一人称口吻**：以「发帖人自己」的角度陈述（“今天我…/忍不住…/姐妹们觉得…”），
   在原提示词画面信息上升级，贴近真人分享语气，而非复述提示词。
2. **删除所有 AI / 模型类标签**：`AI_TAG_BLOCK` 过滤 Seedance/提示词/模型/生成
   以及纯画质技术词（超写实/电影感/运镜/4K/HD…）。
3. **只留 2~3 个标签**：按发帖人关心的关键信息（场景 / 穿搭 / 心情）梳理，
   由 `_SCENE_RULES` 场景模板给出干净标签。

示例（改写前 → 改写后）：
```
丰腴沙漏模特的时尚杂志大片…… #超写实 #电影感 #Seedance   ← 改写前(含AI/画质标签)
今天试了组杂志风的写真，多角度转了一圈，感觉自己也能当回封面模特啦～ #模特写真 #时尚穿搭
```

## 22.4 发布到群组

```powershell
$env:PYTHONIOENCODING="utf-8"; $env:PYTHONUTF8="1"
$env:ROOM_POST_EMAIL    = "your_account@example.com"
$env:ROOM_POST_PASSWORD = "your_password"
$env:ROOM_POST_ROOM_ID  = "!yourRoomId:xxai.com"

# 先看不发
py -3 scripts/post_room_video.py --csv result/beauty_videos.csv --dry-run

# 实际发布(只进群; 加 --square 同时发广场)
py -3 scripts/post_room_video.py --csv result/beauty_videos.csv --delay 2.5

# 只发指定行 / 限量
py -3 scripts/post_room_video.py --csv result/beauty_videos.csv --rows 1,2,3 --delay 2.5
py -3 scripts/post_room_video.py --csv result/beauty_videos.csv --limit 5
```

## 22.5 验收

```powershell
# 房间 feed 顶部应能看到 type=video 的新帖
Invoke-RestMethod -Method Get `
  -Uri "$($env:ROOM_FEED_URL)?room_id=$([uri]::EscapeDataString($env:ROOM_POST_ROOM_ID))&page_size=12" `
  -Headers @{ Authorization = "Bearer <token>" } | Select-Object -ExpandProperty data
```

## 22.6 注意事项

- 发帖账号需为目标房间创建者/有发帖权限（否则 `code=50006`）。
- opennana 下载必须带 `Referer: https://opennana.com/` 与桌面 UA（防盗链）。
- `video_thumnail` 是后端接口原始拼写，勿改。
- 凭据一律走环境变量 / `.env`，不入库；批次结束建议轮换。
