# XXAI 广场内容自动发布

> 通过 HTTP 接口方式向 XXAI 广场（朋友圈/动态）批量发布图文 / 视频内容。
> 本仓库基于 `tester/auto-poster` 的工作流沉淀而成，并附带 **MCP Server**，可被大模型 / Agent 直接调用。

整理日期：2026-06-17

---

## 仓库结构

```
xxai-square-publisher/
├── README.md                       # 本文件，总览
├── .env.example                    # 凭证与端点示例（拷为 .env 后填写）
├── docs/                           # 知识库（模型主要读取此目录）
│   ├── 01-overview.md              # 整体背景与资源
│   ├── 02-environment.md           # 环境准备 / GitLab 拉代码 / 依赖
│   ├── 03-post-moments.md          # post_moments.py 用法与素材 CSV 规范
│   ├── 04-content-pipeline.md      # 素材采集 + 文案改写规范（OpenNana 等）
│   ├── 05-batch-records.md         # 已执行批次记录与样本账号
│   ├── 06-post-video.md            # 视频发布流程（重点）与 media_info 格式
│   ├── 07-artifacts.md             # 产物文件清单
│   ├── 08-quick-replay.md          # 复用步骤速查
│   ├── 09-security.md              # 凭证与脱敏约定
│   ├── 10-auto-poster-merge.md     # 与 tester/auto-poster 的合并说明
│   └── runbooks/                   # 可直接照抄的 runbook
│       ├── run-image-post.md
│       └── run-video-post.md
├── scripts/                        # 可运行 Python 工具（与 tester/auto-poster 同源）
│   ├── post_moments.py             # 图文 / 文本批量发帖
│   ├── post_single_moment_vision.py# 单条带 Vision LLM 的发帖
│   ├── post_video.py               # 视频发帖（基于文档 §6 复刻）
│   ├── opennana_fetch.py           # 从 OpenNana 拉取图片/视频素材
│   ├── config.py utils.py retry.py validation.py
│   ├── crawl_xhs.py                # 小红书爬虫（来自原仓库）
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

## 快速开始（人工执行）

```powershell
# 1. 准备环境
py -3 -m pip install -r scripts/requirements.txt

# 2. 复制 .env 模板并填写凭证
Copy-Item .env.example .env
# 编辑 .env，填好 LOGIN_URL / MOMENTS_API_URL / 账号 CSV 路径 等

# 3. 批量发图文
py -3 scripts/post_moments.py --accounts-csv accounts_10.csv --csv moments.csv \
    --num-accounts 0 --num-posts 0 --concurrency 1 --delay 2.0

# 4. 发视频
py -3 scripts/post_video.py --account <email> --video <mp4_url_or_path> \
    --cover <png_url_or_path> --caption "文案内容"
```

详见 [`docs/08-quick-replay.md`](docs/08-quick-replay.md)。

## 模型 / Agent 接入（MCP）

本仓库附带 MCP Server，模型可通过以下工具调用本系统：

| Tool                 | 用途                                                 |
| -------------------- | ---------------------------------------------------- |
| `list_docs`          | 列出 `docs/` 下所有 Markdown 知识文档                |
| `read_doc`           | 读取指定文档全文                                     |
| `search_docs`        | 在文档中按关键词检索                                 |
| `list_scripts`       | 列出可调用的 Python 脚本及其用途                     |
| `read_script`        | 读取脚本源码（让模型理解后再决定如何调用）           |
| `run_post_moments`   | 调用 `post_moments.py` 批量发图文                    |
| `run_post_video`     | 调用 `post_video.py` 发视频                          |
| `fetch_opennana`     | 从 OpenNana 拉素材（图片 / 视频 + 提示词）           |
| `rewrite_caption`    | 把英文提示词改写为中文用户口吻文案                   |

详细参数与启动方式见 [`mcp/README.md`](mcp/README.md)。

## 安全提示

- **不要把 `.env`、真实账号 CSV、token 提交到本仓库**，`.gitignore` 已默认拦截。
- 仓库内提及的所有账号/密码/URL，参考 `docs/09-security.md` 与 `.env.example`，**全部通过环境变量注入**。
- 任务执行后建议轮换凭证。

## 仓库演变

本仓库继承并取代了 [`tester/auto-poster`](http://100.64.0.45:8999/tester/auto-poster) 的发布工具链：

- 该仓库的 7 个核心脚本（`post_moments.py` / `config.py` / `utils.py` / `retry.py` / `validation.py` / `post_single_moment_vision.py` / `requirements.txt`）已**完全融合**进本仓库 `scripts/` 目录（SHA256 一致）。
- 历史的小红书爬虫 `crawl_xhs.py` 已收纳到 `scripts/legacy/crawl_xhs.py`。
- 该仓库的真实账号池 `企管用户_邮箱密码pincode_200.csv` **按设计不入本仓库**，由 `scripts/gitlab_pull.py` 在运行时从 Project 207 拉取。

完整差异比对、迁移指引与真实回归结果，见 [`docs/10-auto-poster-merge.md`](docs/10-auto-poster-merge.md)。
