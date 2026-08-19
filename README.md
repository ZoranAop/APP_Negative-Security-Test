# XXAI 广场内容自动发布

> 通过 HTTP 接口方式向 XXAI 广场（朋友圈/动态）批量发布图文 / 视频内容。
> 本仓库基于 `tester/auto-poster` 的工作流沉淀而成，并附带 **MCP Server**，可被大模型 / Agent 直接调用。
>
> **双分支**: `main`（发布工具链）← 与 → `test/regression-suite-v2`（测试套件，独立分支）

最近更新：2026-08-19

- **Web3 用户池**：新增 `accounts_web3_104.csv`（104 个 Web3/Crypto 主题账号，昵称覆盖英文/繁体中文/日文三种风格），用于 Web3/加密/美股资讯发布
- **架构优化 v0.4**：提取公共工具函数到 `utils.py`（`ensure_utf8_stdout`、`run_cmd`、`strip_source_attribution`），消除 20+ 处重复代码
- **`caption_multilang.py`**：`zh_hant` 繁体中文模板去台湾地名化，改为通用场景描述，避免非台湾图片输出地域错误文案
- **`publish_from_tokens.py`**：新增 token 过期自动刷新（发布阶段检测 `TOKEN_EXPIRED` → 重新登录 → 重试），减少静默失败
- **`post_comments.py`**：新增 `--accounts` / `--login-url` / `--tokens-out` 参数，token 过期或无 token 时自动从账号 CSV 重新登录并重试
- **`post_laos_mm_v2.py`**：废弃硬编码密码，改为 `--accounts-csv` 参数读取账号
- **文档同步**：`docs/13-multilang-captions.md` 更新完整 14 种语言支持表；注明东南亚语言回退策略

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
│   ├── 06-post-video.md            # 视频发布流程与 media_info 格式
│   ├── 07-artifacts.md             # 产物文件清单
│   ├── 08-quick-replay.md          # 复用步骤速查
│   ├── 09-security.md              # 凭证与脱敏约定
│   ├── 10-auto-poster-merge.md     # 与 tester/auto-poster 的合并说明
│   ├── 11-anti-ad-filtering.md     # 广告 / 商业素材过滤规则
│   ├── 12-multi-source.md          # 多源素材采集
│   ├── 13-multilang-captions.md    # 多语言主体视角文案改写
│   ├── 14-room-moments.md          # 群组 / 房间发帖
│   ├── 15-image-hd-sources.md      # yituyu/tuzi 高清图源
│   ├── 16-xiaohongshu-square.md    # 小红书广场
│   ├── 20-dedupe.md                # 跨批次去重
│   ├── 23-cizucu.md                # cizucu 摄影社区
│   ├── 24-web3-sources.md          # Web3 资讯多源
│   ├── 25-mixed-posting.md         # 混合交错发帖
│   ├── 28-source-attribution-filter.md # 来源过滤
│   └── runbooks/                   # 可直接照抄的 runbook
├── scripts/                        # 可运行 Python 工具
│   ├── post_moments.py             # 图文/文本批量发帖（≤10 账号）
│   ├── publish_from_tokens.py      # 三阶段发帖：顺序登录 → S3 → 并发发布（✨推荐生产）
│   ├── post_video.py               # 视频发帖
│   ├── opennana_fetch.py           # OpenNana 拉图/视频
│   ├── multi_source_fetch.py       # 多源统一采集入口
│   ├── caption_multilang.py        # 多语言文案改写
│   ├── assemble_mixed.py           # 混合交错组装
│   ├── run_mixed.py                # 混合交错一键发布
│   ├── record_sent_slugs.py        # 去重回写
│   ├── gitlab_pull.py              # 从 GitLab 拉账号
│   ├── export_users.py             # 导出企管用户
│   ├── image_quality.py            # 图片质量评估
│   ├── run_eu_life_topics.py       # 欧美生活话题（Life/Art/Travel/Cars）
│   ├── fetch_eu_life_topics.py     # 欧美生活四话题RSS采集器
│   ├── config.py utils.py retry.py validation.py
│   ├── run_*.py                    # 28 条地区/内容线
│   │   ├── run_malaysia.py        马来西亚    ├── run_indonesia.py      印尼
│   │   ├── run_taiwan.py          台湾        ├── run_singapore.py      新加坡
│   │   ├── run_vietnam.py         越南        ├── run_jp_life.py        日本生活
│   │   ├── run_europe.py          欧洲多语    ├── run_europe_en.py      欧洲英语
│   │   ├── run_us_life.py         美国生活    ├── run_us_tech_ai.py     美国科技AI
│   │   ├── run_tech.py            科技资讯    ├── run_web3.py           Web3 资讯
│   │   ├── run_cizucu.py          摄影社区    ├── run_xhs_video.py      小红书视频
│   │   └── run_africa/arab/gulf/south_america... 非洲/阿拉伯/南美等
│   ├── post_comments.py             # 自然口吻评论发布（消除AI感/Token复用）
│   └── legacy/README.md            # 历史脚本说明
├── templates/                      # CSV 模板
│   ├── accounts.example.csv        # 账号 CSV 模板
│   └── moments.example.csv         # 素材 CSV 模板
├── data/                           # 去重文件
│   └── used_slugs.json             # 跨批次图片去重记录
├── result/                         # 发布结果 & token 缓存
├── mcp/                            # MCP Server（Node + TypeScript，25 工具）
└── .gitlab/CODEOWNERS
```

> **测试套件**位于独立分支 `test/regression-suite-v3`，包含 12 套自动化套件（347 用例）+ 17 模块手工用例（227 条），
> 详见 [测试分支 README](http://100.64.0.45:8999/chenzhuo/xxai-square-publisher/-/tree/test/regression-suite-v3)。

---

## 快速开始

### 推荐流程（三阶段发布）

```powershell
py -3 -m pip install -r scripts/requirements.txt
Copy-Item .env.example .env   # 编辑填写 LOGIN_URL / MOMENTS_API_URL 等

# 三阶段发布：顺序登录防429 + 图片质量过滤 + Token复用
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_20.csv `
    --csv moments.csv `
    --concurrency 4 `
    --login-spacing 2.5 `
    --tokens-out result/tokens.json

# Token 复用（跳过登录阶段）
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_20.csv `
    --csv moments.csv `
    --tokens-in result/tokens.json
```

### 简易流程（≤10 账号）

```powershell
py -3 scripts/opennana_fetch.py --media-type image --page 1 --output moments.csv
py -3 scripts/post_moments.py --accounts-csv accounts_10.csv --csv moments.csv `
    --num-accounts 0 --num-posts 0 --concurrency 1 --delay 2.0
```

详见 [`docs/08-quick-replay.md`](docs/08-quick-replay.md)。

---

## 发帖管线对比

| 特性 | post_moments.py | publish_from_tokens.py |
|------|:---:|:---:|
| 429 防护 | ❌ 并发时触发限流 | ✅ 顺序登录 + deburst + 重试 |
| 图片质量门 | 基础尺寸 | ✅ 7 步完整管线 |
| Token 复用 | ❌ | ✅ JSON 持久化 + --tokens-in |
| Token 过期刷新 | ❌ | ✅ 发布阶段自动重新登录重试 |
| 中断恢复 | ❌ | ✅ 复用 tokens 续传 |
| 文本降级 | ❌ 直接失败 | ✅ 自动纯文本兜底 |

> **建议: 生产环境统一使用 `publish_from_tokens.py`。**

---

## Web3 用户池（accounts_web3_104.csv）

- `accounts_web3_104.csv`：Web3/Crypto 主题发布账号池，共 **104 个账号**（序号/昵称/邮箱/密码）。
- 昵称覆盖三种风格：**英文**（`0xVoidWalker`、`GaslessRonin`、`SolStalker` 等）、**繁体中文**（`链上炼金师`、`钻石手旅人`、`以太沉默者` 等）、**日文**（`ガス代回避`、`ガス代ゼロ派` 等），均为 Web3 社区化昵称（含 0x 地址风、链上/钻石手/Meme 等梗）。
- 账号源自 `pre_企管用户_1300.csv` 主池，邮箱/密码与主池一致。
- 用途：配合 `run_web3.py` / `fetch_web3.py` / `web3_caption_by_role.py` 发布 Web3/加密/美股资讯；`--lang auto-nick` 会按昵称文字系统自动匹配文案语言（英文昵称→英文、中文昵称→繁体、日文昵称→日文）。

---

## 评论发布（post_comments.py）

在已有帖子下用不同用户发表自然评论，消除 AI 感。

### 单帖模式

```powershell
py -3 scripts/post_comments.py `
    --post-id 739388370119036928 `
    --tokens result/tokens.json `
    --commenters accounts.csv `
    --topic tech_ai `
    --count 3
```

### 批量模式（带 token 自动刷新）

```powershell
py -3 scripts/post_comments.py `
    --batch comments_batch.csv `
    --tokens result/tokens.json `
    --accounts accounts.csv
```

特点：Token 复用免登录、token 过期自动从账号 CSV 重新登录并重试、随机选评论消除模式感、延时防 429、支持中文简体/繁体/英文。

---

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
| `run_publish_from_tokens`     | 调用 `publish_from_tokens.py`（三阶段发布，避 429）  |
| `run_mixed`                   | 调用 `run_mixed.py`（混合交错一键发布）              |
| `run_post_video`              | 调用 `post_video.py` 发视频                          |
| `fetch_opennana`              | 从 OpenNana 拉素材（图片 / 视频 + 提示词）           |
| `fetch_openprompts`           | 从 open-prompts.com 拉素材                            |
| `fetch_lovimg`                | 从 lovimg.com 拉素材                                  |
| `fetch_multi_source`          | 多源统一采集（默认过滤广告 + 跨源去重）              |
| `fetch_eu_life_topics`        | 欧美生活四话题采集（Life/Art/Travel/Cars）           |
| `generate_multilang_captions` | 多语言主体视角文案改写                                |
| `rewrite_caption`             | 返回「英文提示词 → 中文用户口吻文案」的改写指令      |
| `run_eu_life_topics`          | 欧美生活话题一键发布（采集→英文文案→发布）           |

详细参数与启动方式见 [`mcp/README.md`](mcp/README.md)。

---

## 安全提示

- **不要把 `.env`、真实账号 CSV、token 提交到本仓库**，`.gitignore` 已默认拦截。
- 仓库内提及的所有账号/密码/URL，参考 `docs/09-security.md` 与 `.env.example`，**全部通过环境变量注入**。
- 任务执行后建议轮换凭证。

---

## 仓库演变

本仓库继承并取代了 [`tester/auto-poster`](http://100.64.0.45:8999/tester/auto-poster) 的发布工具链，
详见 [`docs/10-auto-poster-merge.md`](docs/10-auto-poster-merge.md)。

近期改动摘要（v0.3）：

- 更新 Pre 用户表（2000 → 1720 普通 + 80 街拍）
- `publish_from_tokens.py` 三阶段流水线正式推荐为生产方案
- 28 条地区/内容发布管线完整覆盖
- 测试分支 `test/regression-suite-v2` 独立维护（8 套件 259 用例 + 17 模块 227 手工用例）

近期改动摘要（v0.2）：

- 多源采集 + 广告过滤 + 多语言文案 + 两阶段发布
- 三批实战验证：300/300 帖全部成功（详见 `docs/05-batch-records.md`）
