# XXAI 广场内容自动发布

> 通过 HTTP 接口方式向 XXAI 广场（朋友圈/动态）批量发布图文 / 视频内容。
> 本仓库基于 `tester/auto-poster` 的工作流沉淀而成，并附带 **MCP Server**，可被大模型 / Agent 直接调用。

最近更新：2026-07-13

- 加入 **混合交错发帖**（拟真 / 去规则化）：每用户随机帖数 + 文本/图文/问题（T/I/Q）交错 +
  单语分配 + 两级去重，一键脚本 `run_mixed.py`，发布层新增登录自适应/节奏打散/失败重试/
  回写去重档（见 [`docs/25-mixed-posting.md`](docs/25-mixed-posting.md)）
- 加入 **多源采集**（opennana / open-prompts / lovimg）+ **广告过滤**
- 加入 **多语言主体视角文案**（EN / 繁中 / 简中 / 日）
- 加入 **两阶段发布**（避开并发登录 429），支持 token 复用
- 加入 **地区/站点内容线**：马来西亚 / 印尼 / 台湾（`run_malaysia.py` / `run_indonesia.py` / `run_taiwan.py`），
  以及 **刺猬社区 cizucu.com 摄影图片线**（`run_cizucu.py`，见 [`docs/23-cizucu.md`](docs/23-cizucu.md)）
- 加入 **Web3 资讯多源线**：9 个 Web3 媒体（TechFlow / Web3BBS / ForesightNews / ME News / Web3Caff /
  PANews / BingX / BlockWeeks / 吴说）统一 `web3` 标签，纯文本发布（`run_web3.py`，见 [`docs/24-web3-sources.md`](docs/24-web3-sources.md)）

---

## 仓库结构

```
xxai-square-publisher/
├── README.md                       # 本文件，总览
├── .env.example                    # 凭证与端点示例（拷为 .env 后填写）
├── docs/                           # 知识库（模型主要读取此目录）
│   ├── 01-overview.md              # 整体背景与资源
│   ├── 02-environment.md           # 环境准备 / GitLab 拉代码 / 依赖
│   ├── 03-post-moments.md          # post_moments.py / publish_from_tokens.py 用法
│   ├── 04-content-pipeline.md      # 素材采集 + 文案改写规范
│   ├── 05-batch-records.md         # 已执行批次记录与样本账号
│   ├── 06-post-video.md            # 视频发布流程（重点）与 media_info 格式
│   ├── 07-artifacts.md             # 产物文件清单
│   ├── 08-quick-replay.md          # 复用步骤速查
│   ├── 09-security.md              # 凭证与脱敏约定
│   ├── 10-auto-poster-merge.md     # 与 tester/auto-poster 的合并说明
│   ├── 11-anti-ad-filtering.md     # 广告 / 商业素材过滤规则
│   ├── 12-multi-source.md          # 多源素材采集（opennana / openprompts / lovimg）
│   ├── 13-multilang-captions.md    # 多语言主体视角文案改写
│   ├── 14-room-moments.md          # 群组 / 房间发帖（room_id）接口与用法
│   ├── 23-cizucu.md                # 刺猬社区 cizucu.com 摄影图片采集与发布（Playwright + 摄影师口吻）
│   ├── 24-web3-sources.md          # Web3 资讯多源采集与发布（9 个媒体，web3 标签，纯文本）
│   ├── 25-mixed-posting.md         # 混合交错发帖（随机帖数 + 文本/图文/问题交错 + 发布层优化）
│   └── runbooks/                   # 可直接照抄的 runbook
│       ├── run-image-post.md
│       ├── run-room-post.md
│       └── run-video-post.md
├── scripts/                        # 可运行 Python 工具
│   ├── post_moments.py             # 图文 / 文本批量发帖（登录并发，≤10 账号最方便）
│   ├── publish_from_tokens.py      # 两阶段发帖：顺序登录 → 并发发布（≥15 账号）
│   ├── post_single_moment_vision.py# 单条带 Vision LLM 的发帖
│   ├── post_video.py               # 视频发帖
│   ├── opennana_fetch.py           # 从 OpenNana 拉图/视频（含 --exclude-ads / --theme / --dedupe-file，输出 _slug 列）
│   ├── fetch_openprompts.py        # 从 open-prompts.com 拉图
│   ├── fetch_lovimg.py             # 从 lovimg.com 拉图（SSR 反解）
│   ├── multi_source_fetch.py       # 多源统一入口（默认过滤广告 + 主题过滤 + 跨源去重）
│   ├── caption_multilang.py        # 三语言/四语言主体视角文案改写
│   ├── record_sent_slugs.py        # 发完回写已发 slug 到 used_slugs.json（下次拉图自动排除）
│   ├── fetch_cizucu.py             # 从 cizucu.com（刺猬摄影社区）主题模块采集图片（Playwright，见 docs/23）
│   ├── run_cizucu.py               # cizucu 一键发布（采集 → 主体视角文案 → 发布，摄影师口吻）
│   ├── fetch_web3.py               # 从 9 个 Web3 媒体统一采集资讯，web3 标签，纯文本（见 docs/24）
│   ├── run_web3.py                 # Web3 资讯一键发布（多源采集 → 繁体/主体视角文案 → 纯文本发布）
│   ├── assemble_mixed.py           # 混合交错组装：每人随机帖数 + T/I/Q 交错 + 单语分配 + 配文去重（见 docs/25）
│   ├── web3_caption_by_role.py     # web3 资讯专用文案：按新闻意图 + 发帖者角色语言改写第一人称点评
│   ├── run_mixed.py                # 混合交错一键发布（采集 → 组装 → 发布层优化 + 回写去重，见 docs/25）
│   ├── run_xhs_video.py            # 小红书视频一键发布（采集 explore 视频 → S3 上传 → 批量发布，见 docs/16 §16.8）
│   ├── gitlab_pull.py              # 从 GitLab 拉取真实账号 CSV
│   ├── config.py utils.py retry.py validation.py
│   └── legacy/README.md            # 历史脚本说明
├── templates/                      # CSV 模板
│   ├── accounts.example.csv        # 账号 CSV 模板（不含真实账号）
│   └── moments.example.csv         # 素材 CSV 模板
├── mcp/                            # 可被模型调用的 MCP Server（Node + TypeScript）
│   ├── src/index.ts                # 入口
│   ├── src/tools.ts                # 所有工具实现
│   ├── package.json
│   ├── tsconfig.json
│   └── README.md
└── .gitlab/CODEOWNERS
```

## 快速开始（人工执行 — 推荐流程）

```powershell
# 1. 准备环境
py -3 -m pip install -r scripts/requirements.txt

# 2. 复制 .env 模板并填写凭证
Copy-Item .env.example .env
# 编辑 .env，填好 LOGIN_URL / MOMENTS_API_URL / 账号 CSV 路径 等

# 3. 多源采集（自动过滤广告）
py -3 scripts/multi_source_fetch.py `
    --sources opennana,openprompts,lovimg `
    --theme beauty `
    --exclude-ads `
    --limit 100 `
    --dedupe-file data/used_slugs.json `
    --output moments_raw.csv `
    --shuffle

# 4. 多语言主体视角文案改写
py -3 scripts/caption_multilang.py `
    --input moments_raw.csv `
    --output moments.csv `
    --langs en,zh_hant,ja

# 5. 两阶段发布（避开并发登录 429）
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_20.csv `
    --csv moments.csv `
    --concurrency 4 `
    --login-spacing 2.5 `
    --tokens-out result/tokens.json

# 6. 视频（单独走这条）
py -3 scripts/post_video.py --account <email> --video <mp4_url_or_path> `
    --cover <png_url_or_path> --caption "文案内容"
```

如果只有 ≤10 个账号 / 不需要多语言 / 不介意广告，可以走简易流程：

```powershell
py -3 scripts/opennana_fetch.py --media-type image --page 1 --output moments.csv
py -3 scripts/post_moments.py --accounts-csv accounts_10.csv --csv moments.csv \
    --num-accounts 0 --num-posts 0 --concurrency 1 --delay 2.0
```

详见 [`docs/08-quick-replay.md`](docs/08-quick-replay.md)。

## 模型 / Agent 接入（MCP）

本仓库附带 MCP Server，模型可通过以下工具调用本系统：

| Tool                          | 用途                                                 |
| ----------------------------- | ---------------------------------------------------- |
| `list_docs`                   | 列出 `docs/` 下所有 Markdown 知识文档                |
| `read_doc`                    | 读取指定文档全文                                     |
| `search_docs`                 | 在文档中按关键词检索                                 |
| `list_scripts`                | 列出可调用的 Python 脚本及其用途                     |
| `read_script`                 | 读取脚本源码（让模型理解后再决定如何调用）           |
| `run_post_moments`            | 调用 `post_moments.py` 批量发图文                    |
| `run_publish_from_tokens`     | 调用 `publish_from_tokens.py`（两阶段发布，避 429）  |
| `run_mixed`                   | 调用 `run_mixed.py`（混合交错一键发布：随机帖数+T/I/Q交错+去重+发布层优化）|
| `run_post_video`              | 调用 `post_video.py` 发视频                          |
| `fetch_opennana`              | 从 OpenNana 拉素材（图片 / 视频 + 提示词）           |
| `fetch_openprompts`           | 从 open-prompts.com 拉素材                            |
| `fetch_lovimg`                | 从 lovimg.com 拉素材                                  |
| `fetch_multi_source`          | 多源统一采集（默认过滤广告 + 跨源去重）              |
| `generate_multilang_captions` | 多语言主体视角文案改写                                |
| `rewrite_caption`             | 返回「英文提示词 → 中文用户口吻文案」的改写指令      |

详细参数与启动方式见 [`mcp/README.md`](mcp/README.md)。

## 安全提示

- **不要把 `.env`、真实账号 CSV、token 提交到本仓库**，`.gitignore` 已默认拦截。
- 仓库内提及的所有账号/密码/URL，参考 `docs/09-security.md` 与 `.env.example`，**全部通过环境变量注入**。
- 任务执行后建议轮换凭证。

## 仓库演变

本仓库继承并取代了 [`tester/auto-poster`](http://100.64.0.45:8999/tester/auto-poster) 的发布工具链，
详见 [`docs/10-auto-poster-merge.md`](docs/10-auto-poster-merge.md)。

近期改动摘要（v0.2）：

- 多源采集：加入 `fetch_openprompts.py` / `fetch_lovimg.py` / `multi_source_fetch.py`
- 广告过滤：统一三层规则（category / tags / 关键词），默认开启
- 多语言文案：`caption_multilang.py` 内建 EN / 简中 / 繁中 / 日 模板池
- 两阶段发布：`publish_from_tokens.py` 顺序登录 + 429 退避 + token 复用
- 三批实战验证：300/300 帖全部成功（详见 `docs/05-batch-records.md`）
