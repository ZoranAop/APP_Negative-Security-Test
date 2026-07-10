# 23. 刺猬社区（cizucu.com）摄影图片发布

> 本文档介绍从 **cizucu.com（刺猬社区，一个摄影社区）** 采集图片 → 主体视角文案 →
> 广场发布的完整调用方式。做法与 `malaysia` / `indonesia` / `taiwan` 三条地区线一致，
> 数据源换为**摄影社区的主题模块图片**，发布人以**摄影师的角色**第一人称描述。

站点：<https://www.cizucu.com/zh-cn>

本能力**自包含**，提供三块：

1. **cizucu 图片采集源**（各主题模块页 → 二级/三级页 → CDN 原图）
2. **主体视角/摄影师口吻文案**（`caption_multilang.py`）
3. **不裁切**：cizucu 图为摄影师原创作品，无烧录水印，发布默认不裁切

---

## 23.1 站点结构与取图规律

cizucu 是 **Next.js + Firebase** 的单页应用：列表数据客户端渲染，直接抓静态 HTML
拿不到图，需用 **Playwright 渲染 + 滚动懒加载** 收集 `photoId`。

| 层级 | 路径 | 说明 |
| ---- | ---- | ---- |
| 模块 / 主题（列表） | `/zh-cn/explore/tags/<中文标签>` | 如 `.../tags/人像`、`.../tags/风光`、`.../tags/街拍` |
| 二级页（图片详情） | `/zh-cn/photos/<photoId>` | 单张照片详情 |
| 原图直链（CDN） | `https://cdn.cizucu.com/images/photos/<photoId>.jpg` | **公开、无需 Referer**，实测可直连下载 |

**「在网站模块中选择 → 进入二级/三级页面」的落地方式：**
1. 打开某主题模块的标签页（二级页）；
2. 向下滚动触发懒加载（三级/更多），按出现顺序收集 `photoId`；
3. `photoId` → 拼 CDN 原图直链，跨帖全局去重，每 `--imgs-per-post` 张聚合成一个多图帖。

可用主题模块（`--themes` 的 key → 站点中文标签）：

```
portrait=人像  street=街拍  scenery=风光  city=城市  nature=自然
architecture=建筑  film=胶片  daily=日常  humanity=人文  light=光影
sky=天空  mobile=手机摄影  casual=随手拍  snap=扫街  china=中国  travel=旅行摄影  bw=黑白
```

> 说明：`travel(旅行摄影)` / `bw(黑白)` 等个别标签页有时懒加载不稳定、收不到图，
> 采集器会打印「收集 0」并跳过，改用其它主题即可（每个主题约可稳定收 ~20 张）。

### 采集脚本 `fetch_cizucu.py`

```powershell
# 先装 Playwright：pip install playwright ; python -m playwright install chromium
py -3 scripts/fetch_cizucu.py `
    --themes portrait,street,scenery,city,nature,architecture,film,daily `
    --posts-per-theme 3 --imgs-per-post 6 --min-imgs 4 --scrolls 10 `
    --dedupe-file state/seen_cizucu.json `
    --output cizucu_raw.csv
```

- 每个主题产 `--posts-per-theme` 个多图帖；`--scrolls` 控制懒加载深度（进三级/更多）。
- `--dedupe-file`：累计已用 `photoId` 的 JSON，保证**跨批次不重复**（已发布过的图不再选）。
- 输出为标准 moments CSV，`content` 为主题中文标签（场景提示），`_source=cizucu`，附 `_theme`。

---

## 23.2 主体视角 / 摄影师口吻文案

采集产出的 `content` 是主题标签（场景提示）。用 `caption_multilang.py` 改写为
**发帖人（摄影师）的第一人称口吻**，并按图片场景（人像/街拍/风光/城市/自然/建筑…）分场景生成：

```powershell
py -3 scripts/caption_multilang.py --input cizucu_raw.csv --output moments_cizucu.csv --langs en,zh
```

- cizucu 图偏摄影作品，语言默认 `en,zh`（可按需 `--langs en,zh_hant,ja`）。
- 场景识别沿用 `caption_multilang.py` 的 `SCENE_RULES`（portrait/street/city/nature/…）。
- **按发帖人角色描述**：把不同账号设为不同专长的摄影师（街头纪实 / 人像 / 风光 /
  建筑 / 胶片 / 生活日常 / 手机街拍…），文案在人设内书写，且主题与人设一致。
  若配置 `LLM_TEXT_*` 可加 `--use-llm` 用大模型按人设生成。

---

## 23.3 图片裁切（cizucu：默认不裁切）

cizucu 是摄影师原创作品，**无烧录水印**，发布**默认不裁切**：

- `run_cizucu.py` 发布时默认关闭裁切（等同 `POST_CROP_BOTTOM_HOSTS=""`）。
- 如某来源图确有需要，`run_cizucu.py --crop [--crop-pct 0.08]` 可临时开启。
- cizucu 不在 `.env.example` 的 `POST_CROP_BOTTOM_HOSTS` 默认值内。

---

## 23.4 端到端 runbook（cizucu）

### 一键脚本（推荐）

```powershell
# 默认：8 个主题模块 × 3 帖，10 账号轮询（每账号 3 帖），英文+中文文案，不裁切
py -3 scripts/run_cizucu.py --accounts-csv accounts_10.csv --posts-per-theme 3

# 指定主题模块与语言
py -3 scripts/run_cizucu.py --themes portrait,street,film --langs en,zh_hant --posts-per-theme 4

# 只采集 + 文案、不发布（预演）
py -3 scripts/run_cizucu.py --skip-publish

# 无人值守
py -3 scripts/run_cizucu.py --accounts-csv accounts_10.csv --yes
```

| 参数 | 说明 | 默认 |
| ---- | ---- | ---- |
| `--themes` | 主题模块（逗号分隔） | `portrait,street,scenery,city,nature,architecture,film,daily` |
| `--posts-per-theme` | 每个模块产出的帖子数 | `3` |
| `--imgs-per-post` | 每帖图片数（上限 9） | `6` |
| `--langs` | 文案语言 | `en,zh` |
| `--scrolls` | 懒加载滚动次数（进三级/更多） | `10` |
| `--crop` / `--crop-pct` | 临时开启底部裁切 | 关闭 |
| `--dedupe-file` / `--reset-dedupe` | 去重档 / 清空去重 | `state/seen_cizucu.json` |
| `--skip-publish` / `--yes` | 只产素材 / 免确认 | 关 |

中间产物落 `cizucu_run/`，报告落 `result/publish_*.csv`。

### 分步执行

```powershell
# 1. 采集（Playwright 渲染各主题模块页，滚动懒加载收图）
py -3 scripts/fetch_cizucu.py --themes portrait,street,film --posts-per-theme 3 `
    --imgs-per-post 6 --dedupe-file state/seen_cizucu.json --output cizucu_raw.csv

# 2. 主体视角文案
py -3 scripts/caption_multilang.py --input cizucu_raw.csv --output moments_cizucu.csv --langs en,zh

# 3. 两阶段发布（cizucu 图无水印，关闭裁切）
$env:POST_CROP_BOTTOM_HOSTS = ""
py -3 scripts/publish_from_tokens.py --accounts-csv accounts_10.csv `
    --csv moments_cizucu.csv --concurrency 3 --tokens-out result/tokens.json
```

---

## 23.5 实战验证

- 从 12 个主题模块（人像/街拍/风光/城市/自然/建筑/胶片/日常/光影/手机摄影/扫街/中国）
  采集，产出 **10 用户 × 3 帖 = 30 帖**，每帖 6 张图，**共 180 张图全部唯一不重复**。
- 10 个账号各设为不同专长摄影师人设，文案第一人称在人设内书写、主题与人设一致。
- 通过 `publish_from_tokens.py` 发布（180 张图下载 → S3 上传 100% → **30/30 成功**，
  每账号正好 3 帖，30 个独立 moment_id）。

> 大批量（100+ 张）下载 + S3 上传较慢，`publish_from_tokens.py` 的**下载一次即缓存**机制
> 让中断后重跑会跳过已下载图并快速续传（token 也复用），实测续跑一次即 30/30。

---

## 23.6 安全

- 沿用 `docs/09-security.md`：**不入库**任何账号 CSV / `.env` / token。
- cizucu 为公开站点、无需登录；不要在仓库或 `.env` 写入任何账号密码。
