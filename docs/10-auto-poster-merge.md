# 10. 与 `tester/auto-poster` 的合并说明

整理日期：2026-06-26

## 背景

`tester/auto-poster`（GitLab Project ID **207**）是更早的"广场帖子自动发布"工作脚本集，
本仓库 `chenzhuo/xxai-square-publisher`（Project ID **212**）基于它沉淀，并在以下方面做了演进：

| 维度       | `tester/auto-poster`                  | 本仓库                                                |
| ---------- | ------------------------------------- | ----------------------------------------------------- |
| 目录结构   | 所有脚本平铺在仓库根                  | `scripts/` 收口，按职责区分 + `legacy/` 历史代码        |
| 文档       | 仅 `README.md`                        | `docs/` 知识库（10 篇）+ `docs/runbooks/` 可复用操作书 |
| 模型接入   | 无                                    | `mcp/` MCP Server（TypeScript），暴露 9 个工具         |
| 素材源     | 小红书爬虫（`crawl_xhs.py`）          | OpenNana 提示词图库（`opennana_fetch.py`）            |
| 视频发布   | 无                                    | `scripts/post_video.py` + `docs/06-post-video.md`     |
| 凭证管理   | 直接放仓库根                          | `.env` + `.gitignore` 强制隔离，禁止真实账号入库       |
| 账号池来源 | 直接放 `企管用户_邮箱密码pincode_200.csv` | 运行时通过 `scripts/gitlab_pull.py` 从 207 拉取        |

## 当前合并状态

逐文件比对（基于 2026-06-26 SHA256 校验）：

| 文件                              | 207 (auto-poster)                                 | 212 (本仓库)              | 关系          |
| --------------------------------- | ------------------------------------------------- | ------------------------- | ------------- |
| `post_moments.py`                 | ✅ 存在                                            | `scripts/post_moments.py` | **完全一致**  |
| `post_single_moment_vision.py`    | ✅ 存在                                            | `scripts/post_single_moment_vision.py` | **完全一致** |
| `config.py`                       | ✅ 存在                                            | `scripts/config.py`       | **完全一致**  |
| `utils.py`                        | ✅ 存在                                            | `scripts/utils.py`        | **完全一致**  |
| `retry.py`                        | ✅ 存在                                            | `scripts/retry.py`        | **完全一致**  |
| `validation.py`                   | ✅ 存在                                            | `scripts/validation.py`   | **完全一致**  |
| `requirements.txt`                | ✅ 存在                                            | `scripts/requirements.txt`| **完全一致**  |
| `crawl_xhs.py`                    | ✅ 存在                                            | `scripts/legacy/crawl_xhs.py` | **完全一致**（已收纳到 legacy） |
| `企管用户_邮箱密码pincode_200.csv` | ✅ 200 个真实企管账号                              | ❌ **不入库**（被 `.gitignore` 拦截） | 运行时拉取    |
| `README.md`                       | 旧版（小红书爬虫场景为主）                        | 新版总览                  | 新版替代       |
| `.env.example`                    | 旧版                                              | 新版（含 OpenNana / LLM） | 新版替代      |

**结论：本仓库的代码层已是 `auto-poster` 的严格超集**，无需再做代码合并；
唯一未入库的是真实账号 CSV，按设计保留在 207，通过 `gitlab_pull.py` 在运行时拉取。

## 调用方式（替代直接使用 auto-poster 的工作流）

### 旧方式（在 auto-poster 里直接运行）

```powershell
# clone auto-poster → 已包含 csv 和脚本
git clone http://100.64.0.45:8999/tester/auto-poster.git
cd auto-poster
py -3 post_moments.py --accounts-csv 企管用户_邮箱密码pincode_200.csv --csv moments.csv
```

### 新方式（在本仓库执行，账号运行时拉）

```powershell
# 1. clone 本仓库
git clone http://100.64.0.45:8999/chenzhuo/xxai-square-publisher.git
cd xxai-square-publisher

# 2. 准备 .env（含 GITLAB_TOKEN 或 GITLAB_USERNAME/PASSWORD）
Copy-Item .env.example .env
# 编辑 .env：设置 GITLAB_PROJECT_ID=207（auto-poster）

# 3. 安装依赖
py -3 -m pip install -r scripts/requirements.txt

# 4. 从 auto-poster 拉账号池到本地（不入 git 历史）
py -3 scripts/gitlab_pull.py `
    --files "企管用户_邮箱密码pincode_200.csv" `
    --out . `
    --ref main

# 5. 取前 10 行做本批账号 CSV（PowerShell）
$src = Get-Content "企管用户_邮箱密码pincode_200.csv" -Encoding UTF8
$src[0..10] | Set-Content "accounts_10.csv" -Encoding UTF8

# 6. 拉素材（OpenNana 图库）
py -3 scripts/opennana_fetch.py --media-type image --pages 8 --limit 50 --output moments.csv

# 7. 批量发布
py -3 scripts/post_moments.py `
    --accounts-csv accounts_10.csv `
    --csv moments.csv `
    --concurrency 1 --delay 2.0
```

## auto-poster 仓库未来归宿

`tester/auto-poster` 仅作为 **账号池存储仓** 保留，**不再追加新功能**：

- 它的核心脚本如有更新，统一在本仓库（212）的 `scripts/` 下进行
- 它的 `crawl_xhs.py` 历史代码完整镜像在 `scripts/legacy/crawl_xhs.py`
- 它的真实账号 CSV `企管用户_邮箱密码pincode_200.csv` 继续作为该仓库的唯一资产，由运维补充/吊销

## 兼容性保证

- **CSV 字段名**：`scripts/config.py` 的 `ACCOUNTS_CSV_EMAIL_FIELDS / ACCOUNTS_CSV_PASSWORD_FIELDS`
  已同时支持 `邮箱/email/username` 与 `密码/password`，与 207 的中文列名 100% 兼容。
- **接口契约**：`LOGIN_URL` / `MOMENTS_API_URL` 与 207 完全一致，未做任何改变。
- **重试与延时默认值**：均与 207 一致。

## 验证（2026-06-26 真跑结果）

使用本仓库 + 207 账号池跑了一次 **10 账号 × 50 帖** 真实发布：

- 登录成功：9 / 10（1 个触发 429，由调度器自动跳过）
- 发布成功：**50 / 50 = 100%**
- 服务端字节级抽检：8 / 8 内容字段长度与客户端完全一致
- 耗时：121.2 s

详见仓库执行日志（不入库，工作目录下的 `result/post_results_*.csv`）。
