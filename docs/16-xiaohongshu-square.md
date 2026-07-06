# 16. 小红书广场自动发送（分支：xiaohongshu-square-publisher）

> 分支中文名：**小红书广场自动发送**
> 分支 slug：`xiaohongshu-square-publisher`
> 基线：从 `main` 拉出，继承全部广场发布工具链（登录 / 两阶段发布 / 多语言文案 / 多源采集）。

## 16.1 这个分支是做什么的

`main` 分支的采集源偏图库（opennana / open-prompts / lovimg / yituyu / tuzi）
与热榜文本（tophub）。本分支在此基础上**把小红书（XHS）作为内容来源**，
形成"从小红书广场采集 → 文案改写 → 广场自动发送"的闭环。

小红书采集脚本沿用并取代自 [`tester/auto-poster`](http://100.64.0.45:8999/tester/auto-poster)
的 `crawl_xhs.py`（多线程并发抓取 + CSV 实时去重 + 富脚本回滚 + 统一重试）。

## 16.2 新增/提升的文件

| 文件                     | 说明                                                     |
| ------------------------ | -------------------------------------------------------- |
| `scripts/crawl_xhs.py`   | 小红书笔记采集脚本（从 `scripts/legacy/` 提升为一等公民） |
| `docs/16-xiaohongshu-square.md` | 本文档                                            |

其余脚本（`post_moments.py` / `publish_from_tokens.py` / `caption_multilang.py`
/ `config.py` / `utils.py` / `retry.py` / `validation.py`）与 `main` 完全一致，
直接复用。`config.py` 已内置 `XHS_EXPLORE_URL` / `XHS_HEADERS` /
`XHS_NOTE_URL_TEMPLATE` / `CRAWL_DEFAULT_*` 等小红书相关配置。

## 16.3 采集：crawl_xhs.py

```powershell
# 目标新增 200 条、最多 30 次请求、请求间隔 1.5s，输出到 moments.csv
py -3 scripts/crawl_xhs.py `
    --target 200 `
    --max-requests 30 `
    --delay 1.5 `
    --output moments_xhs.csv
```

- 多线程并发抓取，CSV 实时去重（重复笔记不会重复写入）。
- 统一走 `retry.py` 的 `robust_request` 做退避重试。
- 相关默认值见 `config.py` 的 `CRAWL_DEFAULT_TARGET / CRAWL_DEFAULT_MAX_REQUESTS
  / CRAWL_DEFAULT_DELAY` 与 `.env` 的 `CRAWL_*`。

> 合规提示：小红书对抓取有风控与版权要求。仅在获授权/合规范围内使用，
> 控制频率（`--delay`）、遵守站点条款，勿抓取敏感或侵权内容。

## 16.4 端到端 runbook（小红书 → 文案 → 广场发送）

```powershell
# 1. 从小红书采集素材
py -3 scripts/crawl_xhs.py --target 200 --output moments_xhs.csv

# 2.（可选）多语言主体视角文案改写
py -3 scripts/caption_multilang.py --input moments_xhs.csv --output moments.csv `
    --langs en,zh_hant,ja

# 3. 两阶段安全发布（顺序登录避 429 → 并发发布；图片 Referer 已自动处理）
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts.csv --csv moments.csv `
    --concurrency 4 --tokens-out result/tokens.json
```

## 16.5 与 main 的关系

- 本分支是 `main` 的**平行（对立）分支**，聚焦小红书源；
- 不改动 main 的图库/文本源逻辑；
- 若小红书采集成熟，可考虑把 `crawl_xhs.py` 以 `xhs` 源形式接入
  `multi_source_fetch.py`（后续工作），再合回 main。

## 16.6 安全

- 沿用 `docs/09-security.md`：不入库任何账号/密码/token，全部走环境变量。
- 小红书 Cookie / 账号（如需登录态抓取）只放本地 `.env`，切勿提交。
