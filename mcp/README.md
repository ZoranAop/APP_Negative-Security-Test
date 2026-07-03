# XXAI Square Publisher — MCP Server

让大模型 / Agent 通过 [Model Context Protocol](https://modelcontextprotocol.io/) 调用本仓库的知识库与发帖工具。

## 提供的能力

### Resources（让模型自动读到知识库）

- 自动暴露 `docs/**/*.md` 为 `xxai-doc:///docs/xx.md` 资源；
  支持 MCP 的 `resources/list` + `resources/read`。

### Tools

| 工具                          | 说明                                                                                       |
| ----------------------------- | ------------------------------------------------------------------------------------------ |
| `list_docs`                   | 列出 docs 下所有 Markdown                                                                  |
| `read_doc`                    | 读取一个文档                                                                               |
| `search_docs`                 | 在文档中按关键词检索（返回 file:line:snippet）                                            |
| `list_scripts`                | 列出可调用的 Python 脚本及 docstring 摘要                                                  |
| `read_script`                 | 读取脚本源码（让模型理解后再决定如何调用）                                                |
| `run_post_moments`            | 调用 `scripts/post_moments.py` 批量发图文（登录并发，≤10 账号）                            |
| `run_publish_from_tokens`     | 调用 `scripts/publish_from_tokens.py`（两阶段：顺序登录→并发发布，避 429）                |
| `run_post_video`              | 调用 `scripts/post_video.py` 发视频                                                        |
| `fetch_opennana`              | 从 OpenNana 拉素材（含 --theme / --model / --exclude-ads / --dedupe-file）                 |
| `fetch_openprompts`           | 从 open-prompts.com 拉素材                                                                  |
| `fetch_lovimg`                | 从 lovimg.com 拉素材（SSR 反解）                                                            |
| `fetch_multi_source`          | 多源统一采集（默认广告过滤 + 跨源去重）                                                    |
| `generate_multilang_captions` | 三/四语言主体视角文案改写                                                                  |
| `rewrite_caption`             | 返回「英文提示词 → 中文用户口吻文案」的改写指令（由调用方 LLM 完成实际改写）              |

> 所有"会真的发帖"的工具都支持 `dry_run: true`，方便模型先打草稿再执行。

## 启动方式（stdio）

```bash
cd mcp
npm install
npm run build
# 启动（一般由 MCP 客户端 / IDE 配置启动，stdio 协议）
node dist/index.js
```

开发模式（无需 build）：

```bash
cd mcp
npm install
npm run dev
```

### 在 Cursor / Claude Desktop / OpenCode 等接入

以 `~/.config/claude-desktop/claude_desktop_config.json` 为例：

```json
{
  "mcpServers": {
    "xxai-square-publisher": {
      "command": "node",
      "args": ["D:/path/to/xxai-square-publisher/mcp/dist/index.js"],
      "env": {
        "PYTHON_BIN": "py -3",
        "GITLAB_BASE_URL": "http://100.64.0.45:8999",
        "GITLAB_TOKEN":    "glpat-xxx",
        "LOGIN_URL":       "https://devapi-x.tp-ex.com/login",
        "MOMENTS_API_URL": "http://100.64.0.47:8889/api/v1/moments/",
        "UPLOAD_CREDENTIALS_URL": "https://devapi-x.tp-ex.com/file/upload/credentials"
      }
    }
  }
}
```

OpenCode 在 `opencode.json` 中：

```json
{
  "mcp": {
    "xxai-square-publisher": {
      "type": "local",
      "command": ["node", "D:/path/to/xxai-square-publisher/mcp/dist/index.js"],
      "environment": {
        "PYTHON_BIN": "py -3"
      }
    }
  }
}
```

> Server 进程会从环境变量读取所有凭证（与 `scripts/config.py` 共用一套 `.env`）。
> **不要把凭证写在仓库内任何文件里。**

## 安全护栏

- `read_doc` / `read_script` 都做了路径越界检查，只暴露 `docs/` 与 `scripts/`。
- `run_*` 工具均有 5 分钟超时；模型可指定 `dry_run` 先回显命令。
- 子进程 `shell:false`，参数走数组，无 shell 注入面。

## 典型 Agent 工作流

### v0.2 推荐（多源 + 多语言 + 两阶段发布）

```
用户："帮我用 20 个 test 企管账号，从 3 个素材站抓美女题材（不要广告），
      写英/繁中/日 3 语言文案，每人发 5 条。"

模型：
  1. call list_docs → 看见 03/04/05/11/12/13
  2. call read_doc(docs/12-multi-source.md) + read_doc(docs/13-multilang-captions.md)
  3. call fetch_multi_source(sources="opennana,openprompts,lovimg",
                             theme="beauty", exclude_ads=true, limit=100,
                             dedupe_file="result/used_slugs.json",
                             output="moments_raw.csv", shuffle=true)
  4. call generate_multilang_captions(input="moments_raw.csv",
                                       output="moments.csv",
                                       langs="en,zh_hant,ja")
  5. call run_publish_from_tokens(accounts_csv="accounts_20.csv",
                                   csv="moments.csv",
                                   concurrency=4, login_spacing=2.5,
                                   dry_run=true)
     → 给用户看一眼阶段 1 (login) 报告
  6. 用户确认 → call run_publish_from_tokens(...) 实跑
  7. 读取 result/publish_<ts>.csv 汇报成功率
```

### 简易（≤10 账号 / 单语 / 不介意广告）

```
用户："帮我用 10 个企管账号，给广场各发一条今日穿搭风格的图文。"

模型：
  1. call list_docs  → 看见 03/04/08 等文档
  2. call read_doc(docs/04-content-pipeline.md) + read_doc(docs/03-post-moments.md)
  3. call fetch_opennana(media_type=image, limit=10, output="moments_today.csv")
  4. 对每行 content 调用 rewrite_caption 得到中文文案（自己产出后写回 CSV）
  5. call run_post_moments(accounts_csv="accounts_10.csv", csv="moments_today.csv",
                            dry_run=true)
     → 给用户看一眼命令
  6. 用户确认 → call run_post_moments(...) 实跑
  7. 读取 result/ 目录的 summary，汇报成功率
```
