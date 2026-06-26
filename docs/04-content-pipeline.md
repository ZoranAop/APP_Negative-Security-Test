# 04. 内容素材制作

## 4.1 数据来源

### OpenNana 提示词图库

页面入口：`https://opennana.com/awesome-prompt-gallery`

> 页面是 Next.js 客户端渲染，静态 HTML 只有骨架；真实数据走后端 API。

| 用途                       | 接口                                                                          |
| -------------------------- | ----------------------------------------------------------------------------- |
| 图片列表                   | `GET https://api.opennana.com/api/prompts?media_type=image&page=N`            |
| 视频列表                   | `GET https://api.opennana.com/api/prompts?media_type=video&page=N`            |
| 详情（含图 / 视频 / 提示词）| `GET https://api.opennana.com/api/prompts/{slug}`                            |

详情常用字段：

| 字段             | 含义                       |
| ---------------- | -------------------------- |
| `title`          | 标题                       |
| `prompts[].text` | 提示词原文（英文）         |
| `images[]`       | 原图 URL 列表              |
| `video_urls[]`   | 视频（mp4）URL 列表        |
| `model`          | 生成模型                   |
| `tags`           | 标签                       |

> 抓取时务必带 `Referer: https://opennana.com/` 和正常 `User-Agent`，否则 403。

### 其他可选数据源

- https://www.open-prompts.com/zh/gallery
- https://lovimg.com/zh?category=people-characters
- https://meigenai.io/zh
- https://www.promptspace.in/images?sort=best&premium=true

## 4.2 文案改写原则（重要）

**不要直接把英文提示词当内容。** 必须经过下面四步：

1. **理解** — 读取每张图 / 视频对应的提示词，理解画面元素、场景、情绪。
2. **改写** — 转成 **用户第一人称的原创分享口吻**（"周末打卡了…" / "今日穿搭分享…" / "终于拍出来啦…"）。
3. **去标识** — 去掉 `【AI生图】`、`Prompt思路：`、英文原文、`#AI提示词` / `#NanoBananaPro` 等暴露生成属性的字样。
4. **加包装** — 配自然贴切的中文话题标签（`#今日穿搭` `#居家日常` `#国风` 等）+ 适量 emoji。

**内容筛选：** 选正向、生活化题材，规避露骨 / 低俗内容。

## 4.3 推荐 LLM 链路

`scripts/post_single_moment_vision.py` 内置了三段式 LLM 调用：

| 模型类型 | 环境变量前缀     | 用途                       |
| -------- | ---------------- | -------------------------- |
| 视觉模型 | `LLM_*`          | 通用 / 默认                |
| 纯 VL    | `LLM_VL_*`       | 直接发布模式 / 兜底识图    |
| 纯文本   | `LLM_TEXT_*`     | 文案润色（如 DeepSeek）   |

所有 `*_API_KEY` / `*_API_BASE` / `*_MODEL` 均通过 `.env` 配置，未设置时回退到通用配置。
