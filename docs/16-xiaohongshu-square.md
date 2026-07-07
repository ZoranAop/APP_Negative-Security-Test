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
| `scripts/multi_source_fetch.py` | 已注册 `xhs` 源（`--sources ...,xhs`）             |
| `mcp/src/tools.ts`       | 提供 `fetch_xhs` MCP 工具                                 |
| `docs/16-xiaohongshu-square.md` | 本文档                                            |

其余脚本（`post_moments.py` / `publish_from_tokens.py` / `caption_multilang.py`
/ `config.py` / `utils.py` / `retry.py` / `validation.py`）直接复用。
`config.py` 已内置 `XHS_EXPLORE_URL` / `XHS_HEADERS` / `XHS_NOTE_URL_TEMPLATE`
/ `CRAWL_DEFAULT_*` 等小红书相关配置。

### 小红书能力清单（均已在 `main`）

| # | 能力 | 落地位置 | 关键配置 |
| - | ---- | -------- | -------- |
| 1 | 采集 `iter_rows()`（供多源统一调度）+ UTF-8 日志包装 | `scripts/crawl_xhs.py`（`iter_rows` / `_ensure_utf8_stdout`） | `CRAWL_DEFAULT_*` |
| 2 | `xhs` 源接入（import + dispatch） | `scripts/multi_source_fetch.py`（`from crawl_xhs import iter_rows`；`--sources ...,xhs`） | — |
| 3 | MCP `fetch_xhs` 工具 + README 登记 | `mcp/src/tools.ts` / `README.md` | — |
| 4 | xhscdn Referer 自动映射（避免 403） | `publish_from_tokens.py` `resolve_referer` | `POST_REFERER_MAP` |
| 5 | 底部 8% 水印裁切（默认 0.08、仅 xhs） | `publish_from_tokens.py` `_maybe_crop_bottom` | `POST_CROP_BOTTOM_PCT` / `POST_CROP_BOTTOM_HOSTS` |
| 6 | 裁切依赖 + 环境变量登记 | `scripts/requirements.txt`（Pillow） / `.env.example` | — |
| 7 | 端到端 runbook（采集→文案→发布） | 本文档 §16.3–§16.4 | — |

## 16.3 两条采集路径

小红书采集有两条路径，按需选用：

### A. 多源统一入口（推荐，产出 CDN 直链，直接可发）

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

- 产出行的 `image_urls` 是 `sns-webpic-*.xhscdn.com/...` 直链。
- `--exclude-ads` 按标题关键词过滤广告/带货/种草等条目。

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

- CSV 的 `image_urls` 写的是**本地文件路径**（非直链）。
- 多线程并发 + CSV 实时去重；统一走 `retry.py` 的 `robust_request` 退避重试。
- 相关默认值见 `config.py` 的 `CRAWL_DEFAULT_*` 与 `.env` 的 `CRAWL_*`。
- 已内置 UTF-8 stdout 包装（`_ensure_utf8_stdout`），Windows GBK 控制台下 emoji/中文日志不再崩。

> 合规提示：小红书对抓取有风控与版权要求。仅在获授权/合规范围内使用，
> 控制频率（`--delay`）、遵守站点条款，勿抓取敏感或侵权内容。

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
