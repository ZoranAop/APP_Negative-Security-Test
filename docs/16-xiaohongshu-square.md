# 16. 小红书广场自动发送（小红书源 xhs）

> 来源：原 `xiaohongshu-square-publisher` 分支（中文名 **小红书广场自动发送**），
> 已合并进 `main`；小红书现已作为一等采集源 `xhs` 接入统一管线。

## 16.1 这个能力是做什么的

`main` 的采集源原本偏图库（opennana / open-prompts / lovimg / yituyu / tuzi）
与热榜文本（tophub）。本能力**把小红书（XHS）作为内容来源**，
形成「从小红书广场采集 → 文案改写 → 广场自动发送」的闭环。

小红书采集脚本沿用并取代自 [`tester/auto-poster`](http://100.64.0.45:8999/tester/auto-poster)
的 `crawl_xhs.py`（多线程并发抓取 + CSV 实时去重 + 统一重试）。

## 16.2 相关文件

| 文件                     | 说明                                                     |
| ------------------------ | -------------------------------------------------------- |
| `scripts/crawl_xhs.py`   | 小红书采集脚本：独立命令行爬虫 + `iter_rows()`（供多源统一调度） |
| `scripts/crawl_xhs_multiimg.py` | 小红书多图采集脚本：详情页提取全部 imageList CDN 直链 |
| `scripts/run_xhs_video.py` | 小红书视频一键脚本：采集 explore 视频 → S3 上传 → 批量发布（含重试/Referer/标签一致） |
| `scripts/multi_source_fetch.py` | 已注册 `xhs` 源（`--sources ...,xhs`）             |
| `mcp/src/tools.ts`       | 提供 `fetch_xhs` MCP 工具                                 |
| `docs/16-xiaohongshu-square.md` | 本文档                                            |
| `docs/23-image-policy.md` | 图片处理标准策略（多图质量管线详细定义）               |

其余脚本（`post_moments.py` / `publish_from_tokens.py` / `caption_multilang.py`
/ `config.py` / `utils.py` / `retry.py` / `validation.py`）直接复用。
`config.py` 已内置 `XHS_EXPLORE_URL` / `XHS_HEADERS` / `XHS_NOTE_URL_TEMPLATE`
/ `CRAWL_DEFAULT_*` 等小红书相关配置。

### 小红书能力清单（均已在 `main`）

| # | 能力 | 落地位置 | 关键配置 |
| - | ---- | -------- | -------- |
| 1 | 采集 `iter_rows()`（供多源统一调度）+ UTF-8 日志包装 | `scripts/crawl_xhs.py`（`iter_rows` / `_ensure_utf8_stdout`） | `CRAWL_DEFAULT_*` |
| 2 | 多图 CDN 直链采集（详情页 `imageList` 全量提取） | `scripts/crawl_xhs_multiimg.py` | `--target` / `--delay` |
| 3 | `xhs` 源接入（import + dispatch） | `scripts/multi_source_fetch.py`（`from crawl_xhs import iter_rows`；`--sources ...,xhs`） | — |
| 4 | MCP `fetch_xhs` 工具 + README 登记 | `mcp/src/tools.ts` / `README.md` | — |
| 5 | xhscdn Referer 自动映射（避免 403） | `publish_from_tokens.py` `resolve_referer` | `POST_REFERER_MAP` |
| 6 | 底部 8% 水印裁切（默认 0.08、仅 xhs） | `publish_from_tokens.py` `_maybe_crop_bottom` | `POST_CROP_BOTTOM_PCT` / `POST_CROP_BOTTOM_HOSTS` |
| 7 | 多图质量管线（AR一致性/分辨率/网格友好/排序） | `publish_from_tokens.py` `_select_images` | `POST_IMAGE_AR_TOLERANCE` / `POST_GRID_FRIENDLY` |
| 8 | 裁切依赖 + 环境变量登记 | `scripts/requirements.txt`（Pillow） / `.env.example` | — |
| 9 | 端到端 runbook（采集→文案→发布） | 本文档 §16.4–§16.7 | — |

## 16.3 三条采集路径

小红书采集有三条路径，按需选用：

### A. 多源统一入口（轻量，产出封面图 CDN 直链，单图）

`multi_source_fetch.py --sources xhs` 调用 `crawl_xhs.iter_rows()`：
取小红书 explore 推荐流的**笔记标题 + 封面图 CDN 直链**，
**不落地本地图片**，输出与其他源一致的 moments CSV，可直接进两阶段发布。

```powershell
py -3 scripts/multi_source_fetch.py `
    --sources xhs `
    --exclude-ads `
    --limit 100 `
    --output moments_raw.csv `
    --shuffle
```

- 产出行的 `image_urls` 是 `sns-webpic-*.xhscdn.com/...` 直链（**仅封面单图**）。
- `--exclude-ads` 按标题关键词过滤广告/带货/种草等条目。
- **局限性**：仅获取每条笔记的封面图，不进入详情页，无法提取多图。

### B. 独立爬虫（抓正文详情 + 本地下载图片/视频）

`crawl_xhs.py` 的完整流程：进每条笔记详情页、下载图片/视频到本地、
CSV 实时去重。适合需要本地素材归档的场景。

```powershell
# 目标新增 200 条、最多 30 次请求、间隔 1.5s、2 线程；注意用 --csv 与 --images-dir
py -3 scripts/crawl_xhs.py `
    --target 200 `
    --max-requests 30 `
    --delay 1.5 `
    --workers 2 `
    --csv moments_xhs.csv `
    --images-dir images
```

- CSV 的 `image_urls` 写的是**本地文件路径**（非直链），逗号分隔多张图。
- 多线程并发 + CSV 实时去重；统一走 `retry.py` 的 `robust_request` 退避重试。
- **多图支持**：从详情页的 `imageList` 提取全部图片（非仅封面），下载到本地。
- 相关默认值见 `config.py` 的 `CRAWL_DEFAULT_*` 与 `.env` 的 `CRAWL_*`。
- 已内置 UTF-8 stdout 包装（`_ensure_utf8_stdout`），Windows GBK 控制台下 emoji/中文日志不再崩。

### C. 多图 CDN 直链采集（推荐，详情页多图 + 不落地本地）

`crawl_xhs_multiimg.py` 结合路径 A 和 B 的优势：先从 explore 推荐流获取笔记
列表，再逐一请求详情页提取完整 `imageList`（所有图片 CDN 直链），
**不下载到本地**，直接输出多图 CDN URL 逗号分隔的 moments CSV。

```powershell
py -3 scripts/crawl_xhs_multiimg.py `
    --target 25 `
    --delay 1.5 `
    --output moments_xhs_multi.csv
```

- 产出行的 `image_urls` 是**逗号分隔的多张 CDN 直链**（与 `publish_from_tokens.py` 兼容）。
- 从详情页解析 `window.__INITIAL_STATE__` 的 `note.noteDetailMap[id].note.imageList`。
- 完整正文提取（Title + Desc），并自动清理小红书话题标签、表情、@提及。
- 广告关键词过滤、仅图文笔记（跳过视频）。
- 无需登录（explore 页公开接口 + 详情页免登录）。
- **适用场景**：需要多图质量保障的发帖场景（配合 `publish_from_tokens.py` 的图片处理管线）。

> 合规提示：小红书对抓取有风控与版权要求。仅在获授权/合规范围内使用，
> 控制频率（`--delay`）、遵守站点条款，勿抓取敏感或侵权内容。

### 路径对比

| 路径 | 多图 | 正文 | 落地本地 | 速度 | 适用场景 |
|------|------|------|---------|------|---------|
| A. `iter_rows()` | 单图（封面） | 仅标题 | 否 | 快（1次请求N条） | 快速批量、混源 |
| B. `crawl_xhs.py` | 全部图片 | 完整(Title+Desc) | 是 | 慢（逐条详情+下载） | 本地素材归档 |
| C. `crawl_xhs_multiimg.py` | 全部图片 | 完整(Title+Desc) | 否（CDN直链） | 中等（逐条详情） | 多图高质量发帖 |

## 16.4 端到端 runbook（小红书 → 文案 → 广场发送）

推荐走路径 A（CDN 直链，无需本地下载）：

```powershell
# 1. 采集小红书素材（explore 推荐流 → CDN 直链，规避广告）
py -3 scripts/multi_source_fetch.py --sources xhs --exclude-ads `
    --limit 100 --output moments_raw.csv --shuffle

# 2.（可选）多语言主体视角文案改写（en / 繁中(台湾) / 日）
py -3 scripts/caption_multilang.py --input moments_raw.csv --output moments.csv `
    --langs en,zh_hant,ja

# 3. 两阶段安全发布（顺序登录避 429 → 并发发布）
#    小红书图 CDN(xhscdn) 的 Referer 已在 publish_from_tokens.py 中自动匹配
#    (xhscdn.com / xiaohongshu.com -> https://www.xiaohongshu.com/)，无需预下载。
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts.csv --csv moments.csv `
    --concurrency 4 --tokens-out result/tokens.json
```

> 实测验证：5 账号 × 2 帖 = **10/10** 成功，Phase2 图片上传 10/10（小红书 CDN 图
> 经自动 Referer 下载 → 底部 8% 水印裁切 → S3 上传 → 发布）；抽查上传图 640×853 → 640×785（height_ratio≈0.920）。
> 早前另一批 3 账号 × 2 帖 = 6/6 亦全部成功。

若走路径 B（本地图片），发布前需先把本地图上传或改写为可访问 URL；
`publish_from_tokens.py` 的两阶段发布默认消费 http 直链。

### 去除小红书右下角水印（发布上传时自动裁切）

小红书图片把水印烧录在**右下角**，无法用 URL 参数关闭，只能裁掉底部一条。
`publish_from_tokens.py` 在下载图片、上传 S3 之前会自动裁切：

- `POST_CROP_BOTTOM_HOSTS`：需裁切的图片域名子串，默认 `xhscdn.com,xiaohongshu.com,bbkz.net`
  （默认对**小红书**与 **backpackers.com.tw 论坛附件图**（`sa.bbkz.net` / `sa1.bbkz.net`）生效，
  其它源不动）；置空 `""` 可完全关闭。
- `POST_CROP_BOTTOM_PCT`：裁掉的底部高度比例，默认 `0.08`（8%）。水印偏大时调到 0.10~0.12。

```powershell
# 例：把小红书图底部裁 10%
$env:POST_CROP_BOTTOM_PCT = "0.10"
py -3 scripts/publish_from_tokens.py --accounts-csv accounts.csv --csv moments.csv --concurrency 4
```

- 依赖 Pillow（`pip install pillow`）；未安装时自动跳过裁切、原图上传（有告警）。
- 实测：小红书封面图 640×853 → 裁后 640×785（去掉底部 8% 水印带），非命中域名的图不受影响。

### backpackers.com.tw 论坛图片底部水印（与小红书同款处理）

backpackers.com.tw 论坛（`fetch_backpackers_my.py` 采集，图床 `sa.bbkz.net` / `sa1.bbkz.net`）
的附件图会在**底部/右下角**带论坛水印。处理方式与小红书完全一致：由
`publish_from_tokens.py` 在上传前对命中 `bbkz.net` 的图**整体裁掉底部一条**。

- 已把 `bbkz.net` 加入 `POST_CROP_BOTTOM_HOSTS` 默认值，开箱即用，无需额外配置。
- 若论坛水印偏大，调高 `POST_CROP_BOTTOM_PCT`（如 `0.10`）。

```powershell
# backpackers 论坛图默认已裁底部 8%；如需裁更多：
$env:POST_CROP_BOTTOM_PCT = "0.10"
py -3 scripts/publish_from_tokens.py --accounts-csv accounts_5.csv --csv moments_bp.csv --concurrency 3
```


## 16.5 与 main 的关系

- 小红书源已**合并进 `main`**：`crawl_xhs.iter_rows()` + `multi_source_fetch.py`
  的 `xhs` 分支 + MCP `fetch_xhs` + `publish_from_tokens.py` 的 xhscdn Referer 映射
  与右下角水印裁切。
- 与图库/文本源并存，可 `--sources xhs` 单独用，也可与其它源混排。

## 16.6 安全

- 沿用 `docs/09-security.md`：不入库任何账号/密码/token，全部走环境变量。
- 小红书 Cookie / 账号（如需登录态抓取）只放本地 `.env`，切勿提交。

## 16.7 多图采集与处理机制

### 多图数据提取（采集阶段）

小红书图文笔记通常包含多张图片。`crawl_xhs.py` 与 `crawl_xhs_multiimg.py`
从详情页的 `window.__INITIAL_STATE__` 中提取完整图片列表：

```python
# 数据路径：state.note.noteDetailMap[note_id].note.imageList
images = note_detail.get("imageList", [])
for img in images:
    url = img.get("urlDefault") or img.get("urlPre") or img.get("url", "")
```

- `imageList` 包含笔记的**全部图片**（非仅封面），每张有多个分辨率版本。
- 优先取 `urlDefault`（最高质量），其次 `urlPre`、`url`。
- 产出 CSV 的 `image_urls` 字段以逗号分隔多张 URL。

### 多图质量处理管线（发布阶段）

`publish_from_tokens.py` 在发布时自动对小红书多图执行 7 步质量管线
（完整定义见 `docs/23-image-policy.md`）：

```
原始 N 张图片 → S3上传 → AR一致性 → 分辨率一致性 → 方向数量上限
→ 网格友好调整 → 质量排序 → 硬上限截取 → 发布
```

#### 小红书图片的特殊处理

| 处理项 | 说明 | 配置 |
|--------|------|------|
| **Referer 映射** | xhscdn.com 域名自动带 `Referer: https://www.xiaohongshu.com/`（避免 403） | `POST_REFERER_MAP` |
| **底部水印裁切** | 下载后裁掉底部 8%（小红书水印烧录在图片底部） | `POST_CROP_BOTTOM_PCT=0.08` |
| **尺寸门槛** | 低于 400×300px 的缩略图/小图自动过滤 | `POST_MIN_IMAGE_WIDTH/HEIGHT` |
| **AR 一致性** | 横竖混排自动筛除少数方向不同的图（保留最大方向组） | `POST_IMAGE_AR_TOLERANCE=0.25` |
| **分辨率一致性** | 剔除像素数低于中位数 1/3 的离群图 | — |
| **网格友好** | 调整到 {1,2,4,6,9}（3→2, 5→4, 7→6, 8→6） | `POST_GRID_FRIENDLY=true` |

#### 典型多图处理实例

| 原始 | AR筛选后 | 分辨率筛选后 | 方向上限 | 网格调整 | 最终发布 |
|------|---------|------------|---------|---------|---------|
| 15张（南京美食） | 12张竖图 | 12张 | 4张（竖图上限） | 4（友好数） | **4图** |
| 13张（猫咪盲盒） | 10张竖图 | 10张 | 4张 | 4 | **4图** |
| 9张（醒狮国粹） | 9张方图 | 9张 | 9张（方图上限） | 9（友好数） | **9图** |
| 4张（穿越时空） | 3张一致 | 3张 | 3张 | 2（友好数3→2） | **2图** |
| 1张（高情商） | 1张 | 1张 | 1张 | 1 | **1图** |

#### 降级原则

**核心：宁可少发也不发混乱布局的图。**

- 多图中有横竖混排 → 仅保留数量最多的方向组
- 分辨率差异过大（如1张高清+1张模糊） → 剔除模糊图
- 剩余数量非友好数（如3张、5张） → 向下取最近友好数（2张、4张）
- 所有图都不达标 → 降级为纯文本帖

### 多图端到端 runbook（推荐路径 C）

```powershell
# 1. 多图采集（详情页提取全部 imageList CDN 直链）
py -3 scripts/crawl_xhs_multiimg.py `
    --target 25 --delay 1.5 --output moments_xhs_multi.csv

# 2. 文案改写（content-aware 模式：基于原文差异化改写，避免模板重复）
py -3 scripts/caption_multilang.py `
    --input moments_xhs_multi.csv --output moments.csv `
    --langs zh_hant --content-aware

# 3. 两阶段发布（自动执行多图质量管线：水印裁切→尺寸验证→AR一致→网格调整）
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_10.csv --csv moments.csv `
    --concurrency 4 --tokens-out result/tokens.json
```

> 实测验证：10 账号 × 2 帖 = **20/20** 成功，Phase2 上传 101 张图片（101/101）；
> 11 帖触发多图质量筛选（AR 一致性 + 分辨率过滤），11 帖触发网格调整；
> 最终发帖图片数分布：9图×1, 6图×1, 4图×12, 2图×4, 1图×2。
> 文案唯一性：20/20（content-aware 模式确保每帖内容不重复）。

### 文案改写策略（`--content-aware` 模式）

小红书采集的原始内容本身就是优质的中文图文，文案改写需要**保留原文个性化信息**
而非用通用模板替换。

#### 推荐：`--content-aware`（差异化改写）

```powershell
# 基于每行原始标题生成独特文案（保留原文特色 + 附加目标语言评论）
py -3 scripts/caption_multilang.py `
    --input moments_xhs.csv --output moments.csv `
    --langs zh_hant --content-aware
```

效果示例：
```
最近在看《心理创伤 #漫画 #小熊虫》，這篇的視角很對我的味。 #漫画 #小熊虫 #生活記錄
分享：家常菜！一周大集合3！ 比起浪漫，我更喜欢烟火气——美食配上這種氛圍，誰能抵擋。 #美食 #吃货薯看这里 #笔记灵感
职场真正实用的表情包🫡 最想说的是: 别整这死出，话说明白点｜看完心情都變好了。 #职场 #日常 #好心情
```

### #话题标签提取策略

小红书原始内容通常自带丰富的 `#话题` 标签。改写时的标签处理优先级：

| 优先级 | 策略 | 说明 |
|--------|------|------|
| 1 | **直接复用原文话题** | 从原始 content 中提取已有 `#话题` 标签（如 `#美食` `#穿搭` `#日常`） |
| 2 | **关键词推导** | 从正文关键词推导标签（如内容含"咖啡"→ `#咖啡`） |
| 3 | **兜底默认** | 通用标签（`#生活記錄` `#好心情` `#日常`） |

这确保每帖的话题标签**与原始内容主题一致**，而非千篇一律的通用标签。

示例对比：

| 原始内容 | 之前（通用标签） | 现在（原文提取） |
|---------|----------------|----------------|
| 当我每天吃一顿抗炎饮食 #一人食吃什么 #抗炎饮食 | `#台灣 #生活記錄 #編輯精選` | `#一人食吃什么 #抗炎饮食 #美食` |
| 妈耶终于要播 #追剧 #甜剧 #剧荒推荐 | `#台灣 #生活記錄 #編輯精選` | `#追剧 #甜剧 #剧荒推荐` |
| 520快乐💜 | `#台灣 #生活記錄 #編輯精選` | `#生活記錄 #好心情 #日常` |

#### 不推荐：纯模板模式（无 `--content-aware`）

```powershell
# 纯模板改写（丢失原文信息，重复度高）
py -3 scripts/caption_multilang.py --input moments.csv --output out.csv --langs zh_hant
```

问题：会产生大量重复模板（如"只是一個想留下來的小片段"出现多次），
丢失小红书原始内容的丰富上下文。

#### 对比

| 模式 | 唯一性 | 原文保留 | 适用场景 |
|------|--------|---------|---------|
| `--content-aware` | 20/20（100%唯一） | 保留标题+正文关键信息 | **小红书（推荐）** |
| 纯模板（无flag） | 低（模板池有限） | 完全丢失 | 图库类（opennana/lovimg） |
| `--use-llm` | 高 | 高（LLM 改写） | 有 LLM API 时使用 |

### 搜索采集的限制

小红书搜索页面（`/search_result?keyword=...`）需要**登录态**才能加载结果，
无登录时页面会弹出登录窗口。当前采集均基于 **explore 推荐流**（无需登录）。

如需按关键词采集（如"世界杯"、"旅游攻略"），需要：
1. 在 `.env` 中配置小红书 Cookie（登录态）
2. 使用 Playwright 带登录态访问搜索页面
3. 从搜索结果的 `__INITIAL_STATE__.search.feeds` 提取数据

目前 explore 推荐流已能满足大部分内容采集需求。

## 16.8 小红书视频采集与发布

> 从小红书 explore 推荐流采集**视频**笔记，经 S3 上传后发布到 XXAI 广场。
> 与图文流程（§16.4）类似，但 media_info 走 `type=video` 路径（见 docs/06-post-video.md）。

### 视频采集流程

小红书视频笔记的数据结构与图文不同，采集时需注意：

```
explore 推荐流 (GET /explore)
  └─ feeds[].noteCard.type == "video"    ← 筛选视频笔记
  └─ feeds[].noteCard.cover              ← 封面图（fallback 用）
  └─ feeds[].id / xsecToken             ← 进入详情页

详情页 (GET /explore/{note_id}?xsec_token=...)
  └─ __INITIAL_STATE__.note.noteDetailMap[id].note
       ├─ type: "video"
       ├─ title / desc                   ← 文案
       ├─ video.media.stream.h264[0]     ← 视频流
       │    ├─ masterUrl                 ← 首选
       │    └─ backupUrl                 ← 备选
       └─ video.image                    ← 封面图
            ├─ urlDefault                ← 首选
            └─ url                       ← 备选
```

### 视频封面 fallback 机制（重要）

实测发现，详情页 `video.image` 字段**有时为空**（约 60% 的视频笔记缺失此字段）。
必须实现多级 fallback：

| 优先级 | 来源 | 字段路径 |
|--------|------|----------|
| 1 | 详情页 video.image | `note.video.image.urlDefault` / `.url` |
| 2 | 详情页 imageList[0] | `note.imageList[0].urlDefault` |
| 3 | explore feed cover | `noteCard.cover.urlDefault` / `.urlPre` |

**如果三级都为空，则跳过该视频（无法发布无封面的视频）。**

### 视频发布完整流程

```
1. 登录 test 环境: POST https://testapi-x.tp-ex.com/login
   body: {"email": ..., "password": ..., "device_id": ..., "device_name": ...}
   → data.token

2. 获取 S3 临时凭证: POST /file/upload/credentials
   → access_key_id / secret_access_key / session_token / region / bucket / domain

3. 下载视频 mp4 + 封面图
   请求头必须带:
     User-Agent: <桌面浏览器 UA>
     Referer: https://www.xiaohongshu.com/

4. boto3 上传到 S3
   key: square/original/YYYY/MM/DD/{uuid}.mp4 / {uuid}.jpg
   ContentType: video/mp4 / image/jpeg

5. POST http://100.64.0.53:8889/api/v1/moments/
   body:
   {
     "content": "<文案>",
     "visibility": 0,
     "media_info": {
       "type": "video",
       "video_url": "https://{domain}/{key}.mp4",
       "thumbnail_url": "https://{domain}/{key}.jpg"
     }
   }
   → data.moment_id
```

### 环境差异

| 环境 | 登录 API | 发布 API | 用户来源 |
|------|----------|----------|----------|
| **test** | `testapi-x.tp-ex.com/login` | `100.64.0.53:8889/api/v1/moments/` | `test_企管用户_邮箱密码pincode_500.csv.xlsx` |
| **dev** | `devapi-x.tp-ex.com/login` | `100.64.0.47:8889/api/v1/moments/` | `pre_企管用户2000.csv` / 用户池 |

- **test 环境登录字段为 `email`**（非 `username`），否则返回 `code=10002`。
- test 500 用户表格式：`序号, 用户昵称, 注册账户, 用户密码, 用户邮箱, Pincode`。

### 实战验证

2026-07-20 实测（test 环境）：

- 5 个用户 × 5 条视频 = **5/5 成功**
- 视频来源：小红书 explore 推荐流（美食、运动、护肤、书法等主题）
- 视频大小范围：1.1 MB ~ 56.4 MB
- 封面图大小：75 KB ~ 252 KB

| 用户 | 视频 | moment_id |
|------|------|-----------|
| Elijah Hall | Brushlettering练字｜浅浅的白绿混色 | (首批) |
| 赵鹿鸣 | 脆脆薯饼～外酥里糯 | `734310659499495424` |
| Aadhya | 沉浸式制冰 | `734310722699268096` |
| 敦子 | 300块钱还是和老婆一起吃个宵夜香！ | `734310830635487232` |
| Mia Rodriguez | 中式早餐🥟好久没有这样吃 | `734310906061656064` |

### Runbook（小红书视频 → 广场发布）

#### 推荐方式：`run_xhs_video.py` 一键脚本（采集 + 发布）

```powershell
# 设置环境变量指向 test
$env:LOGIN_URL = "https://testapi-x.tp-ex.com/login"
$env:UPLOAD_CREDENTIALS_URL = "https://testapi-x.tp-ex.com/file/upload/credentials"
$env:MOMENTS_API_URL = "http://100.64.0.53:8889/api/v1/moments/"

# 20 用户各发 1 个视频（自动采集 + 发布）
py -3 scripts/run_xhs_video.py `
    --accounts-xlsx "test_企管用户_邮箱密码pincode_500.csv.xlsx" `
    --num-users 20 --env test --yes

# 只采集不发布（预览模式）
py -3 scripts/run_xhs_video.py --crawl-only --target 30 --output my_videos.csv

# 从已有 CSV 发布（跳过采集）
py -3 scripts/run_xhs_video.py `
    --accounts-xlsx accounts.xlsx --csv moments_video.csv --num-users 10 --env test --yes
```

`run_xhs_video.py` 内置的关键优化：

| 优化项 | 说明 |
|--------|------|
| **环境自适应登录** | test 环境用 `email` 字段，dev 环境用 `username` |
| **Referer 自动映射** | xhscdn.com → `Referer: https://www.xiaohongshu.com/`（避免封面 403） |
| **封面多级 fallback** | `video.image` → `imageList[0]` → explore feed cover |
| **失败自动重试** | 下载超时自动切换备用视频（`--max-retries`） |
| **文案标签一致性** | 保留原始 #标签 / 关键词推导 / 兜底默认 |
| **登录间隔可配** | `--login-spacing`（默认 5s，避免 429） |

#### 逐条发布方式（单账号单视频）

```powershell
# 1. 采集视频（crawl_xhs.py 已支持 type=video，自动下载 mp4 + 生成缩略图）
py -3 scripts/crawl_xhs.py --target 5 --delay 1.5 --csv moments_video.csv --images-dir images

# 2. 逐账号发布视频
#    需要从 moments_video.csv 中读取 video_url 和 thumbnail_url 列
py -3 scripts/post_video.py --account <email> --accounts-csv <csv> `
    --video <local_or_url> --cover <local_or_url> --caption "文案"
```

或使用独立脚本一次性完成（采集 + 登录 + S3 + 发布）：

```powershell
# 设置环境变量指向 test
$env:LOGIN_URL = "https://testapi-x.tp-ex.com/login"
$env:UPLOAD_CREDENTIALS_URL = "https://testapi-x.tp-ex.com/file/upload/credentials"
$env:MOMENTS_API_URL = "http://100.64.0.53:8889/api/v1/moments/"

py -3 scripts/post_video.py --account u_5x3ghocm@xxai.com `
    --accounts-csv "test_企管用户_邮箱密码pincode_500.csv.xlsx" `
    --video <mp4_url> --cover <cover_url> --caption "视频文案"
```

### 注意事项

1. **视频下载超时**：小红书视频文件较大（最大 50+ MB），`timeout` 建议 ≥120s。
2. **封面必须有效**：`thumbnail_url` 为空会导致发布成功但前端无法展示。
3. **Referer 防盗链**：下载视频/封面时必须带 `Referer: https://www.xiaohongshu.com/`。
4. **explore JSON 解析**：页面约 1MB，`__INITIAL_STATE__` 结束位置应以 `</script>` 标签定位（而非逐字符匹配大括号），否则解析耗时极长。
5. **登录间隔**：多账号顺序登录，间隔 ≥2.5s，避免 429。
6. **S3 上传 ContentType**：视频必须为 `video/mp4`，封面为 `image/jpeg` 或 `image/png`。
