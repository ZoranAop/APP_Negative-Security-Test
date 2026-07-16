# 23. Image Processing Policy (图片处理标准策略)

> 本文档定义了 XXAI 广场内容发布系统的**图片处理标准策略**，
> 所有发帖脚本（publish_from_tokens.py / post_room_moments.py / post_moments.py）
> 统一遵循此策略，确保 feed 呈现的完整性、一致性和友好性。

---

## 23.1 媒体类型规范

| 类型 | media_info | 规则 |
|------|-----------|------|
| **图片帖** | `{"type": "image", "images": [...]}` | 最少 1 张，最多 9 张（可配置） |
| **视频帖** | `{"type": "video", "video_url": "...", "thumbnail_url": "..."}` | 有且仅有 1 个视频 |
| **纯文本帖** | `{"type": "text"}` | 无媒体，仅文案描述 |

---

## 23.2 图片选择流水线（7 步）

```
原始 N 张图片 URLs
  │
  ├─ Step 1: 可用性筛选
  │    仅保留已成功上传到 S3 的图片（排除下载失败/水印跳过的）
  │
  ├─ Step 2: 宽高比（AR）一致性
  │    按方向分三组: 横图(AR>1.1) / 竖图(AR<0.9) / 方图(0.9~1.1)
  │    保留最大组，组内中位数 AR ±25% 容差过滤
  │    → 保证同帖图片方向统一，不出现横竖混排
  │
  ├─ Step 3: 分辨率一致性
  │    剔除总像素数 < 中位数 1/3 的离群图片
  │    → 避免高清大图和模糊小图混在同一帖
  │
  ├─ Step 4: 方向感知数量上限
  │    竖图(portrait): 最多 4 张 (2×2)
  │    横图(landscape): 最多 6 张 (2×3)
  │    方图(square):    最多 9 张 (3×3)
  │    → 竖图宽度有限，多张并排会压缩过度
  │
  ├─ Step 5: 网格友好数量调整
  │    友好数: 1, 2, 3, 4, 6, 9
  │    5→4, 7→6, 8→6（向下取最近友好数）
  │    → 避免不完整的最后一行
  │
  ├─ Step 6: 质量排序
  │    按总像素数降序排列
  │    → 最大/最清晰的图片排首位（封面/英雄图位置）
  │
  └─ Step 7: 硬上限截取
       截取前 POST_MAX_IMAGES 张（默认 9）
```

---

## 23.3 图片质量门槛

### 采集阶段（fetch 脚本）

| 检查项 | 规则 | 跳过行为 |
|--------|------|---------|
| 水印域名 | 500px / dpreview / gettyimages / shutterstock / istock / alamy / dreamstime / depositphotos / 123rf | 采集时直接跳过，不进入 CSV |
| 广告/垃圾图 | URL含 logo/banner/avatar/icon/sprite/ad/doubleclick/placeholder/share/favicon/pixel/1x1 | 跳过 |
| 缩略图 URL 模式 | WordPress `-NNNxNNN.jpg` / `?w=300` / `?width=200` / `?size=thumb` / `/thumb/` / `/small/` | 跳过 |

### 发布阶段（publish_from_tokens.py）

| 检查项 | 规则 | 跳过行为 |
|--------|------|---------|
| 水印域名 | POST_WATERMARK_SKIP_HOSTS（同上列表） | Phase 2 跳过上传 |
| 最小尺寸 | `POST_MIN_IMAGE_WIDTH=400` × `POST_MIN_IMAGE_HEIGHT=300` | 下载后 Pillow 检测，不达标则删除本地文件 |
| 下载失败 | HTTP 非 200 / 超时 / SSL 错误（重试 3 次） | 不进入 cache |

---

## 23.4 降级规则（Graceful Degradation）

**核心原则：不达标就降低数量，绝不用低质量图凑数。**

| 情况 | 行为 |
|------|------|
| 文章 9 张图 → 7 张通过质量 | AR 一致性 + 网格调整 → 发 6 张 |
| 文章 6 张图 → 5 张通过质量 | 网格调整 5→4 → 发 4 张 |
| 文章 4 张图 → 3 张方向一致 | 发 3 张（3 是友好数） |
| 文章 3 张图 → 1 张通过质量 | 发 1 张图文帖 |
| 文章 5 张图 → 0 张通过质量 | **降级为纯文本帖** |
| 文章无图片 | 直接纯文本帖 |

---

## 23.5 方向与布局建议

| 方向 | AR 范围 | 最佳图片数 | 网格布局 | 说明 |
|------|---------|-----------|---------|------|
| 横图 Landscape | > 1.1 | 2, 3, 4, 6 | 1×2, 1×3, 2×2, 2×3 | 最通用，适合风景/科技/新闻 |
| 方图 Square | 0.9~1.1 | 4, 9 | 2×2, 3×3 | Instagram 风格，适合美食/产品 |
| 竖图 Portrait | < 0.9 | 2, 3, 4 | 1×2, 1×3, 2×2 | 适合人像/写真/时尚 |

### 竖图帖的特殊处理

竖图宽度有限，多张并排时每张被压缩到很窄：
- ≤4 张竖图：2×2 网格，每张保留足够展示宽度
- 5+ 张竖图：强制截为 4 张，避免压缩过度
- 可配置：`POST_MAX_PORTRAIT_IMAGES=4`

---

## 23.6 配置参数一览

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `POST_MAX_IMAGES` | 9 | 单帖最大图片数（硬上限） |
| `POST_MIN_IMAGE_WIDTH` | 400 | 最小图片宽度（px） |
| `POST_MIN_IMAGE_HEIGHT` | 300 | 最小图片高度（px） |
| `POST_IMAGE_AR_TOLERANCE` | 0.25 | 宽高比一致性容差（25%） |
| `POST_GRID_FRIENDLY` | true | 启用网格友好数量调整 |
| `POST_MAX_PORTRAIT_IMAGES` | 4 | 竖图帖最大图片数 |
| `POST_MAX_LANDSCAPE_IMAGES` | 6 | 横图帖最大图片数 |
| `POST_MAX_SQUARE_IMAGES` | 9 | 方图帖最大图片数 |
| `POST_WATERMARK_SKIP_HOSTS` | 500px.com,dpreview.com,... | 水印域名跳过列表 |
| `POST_CROP_BOTTOM_HOSTS` | xhscdn.com,bbkz.net,... | 底部水印裁切域名 |
| `POST_CROP_BOTTOM_PCT` | 0.08 | 底部裁切比例 |
| `POST_NO_VERIFY_HOSTS` | erv-nsa.gov.tw | TLS 容错域名 |

---

## 23.7 日志输出示例

```
[Phase 2] skipping 3 watermarked image(s) (hosts: 500px.com,gettyimages.com)
[Phase 2] uploading 27 unique urls
  thumbnail skipped: 340x510 < 400x300 (eatbook.sg/wp-content/...)
[Phase 2] cached 26/27

[Phase 3] 4 post(s) image count reduced for quality (e.g. 8→6 imgs)
[Phase 3] 2 post(s) trimmed for dimension consistency
[Phase 3] 1 post(s) will be text-only

  ✓ [1/8] UserA [4img] 732847828195348480
  ✓ [2/8] UserB [6img] 732847829805961216
  ✓ [3/8] UserC [3img] 732847830309277696
  ✓ [4/8] UserD [9img] 732847830984560640
  ✓ [5/8] UserE [2img] 732847831505243136
  ✓ [6/8] UserF [1img] 732847832015216640
  ✓ [7/8] UserG [text] 732847832515203072
  ✓ [8/8] UserH [6img] 732847833023774720
```

---

## 23.8 适用脚本

| 脚本 | 图片策略适用范围 |
|------|----------------|
| `publish_from_tokens.py` | 完整 7 步流水线（广场发帖） |
| `post_room_moments.py` | S3 上传 + 发帖（房间/群组发帖） |
| `post_moments.py` | 基础发帖（遗留脚本，部分适用） |
| `post_video.py` | 视频帖（仅 1 视频规则） |
| `fetch_*.py` | 采集阶段质量门槛（水印/缩略图/广告过滤） |
