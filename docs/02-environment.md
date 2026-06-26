# 02. 环境准备

## 2.1 Python

- **必须使用 `py -3`**（实测 Python 3.14 可用）。
- ⚠️ Windows 下的 `python.exe`（WindowsApps 版本）是占位 stub，**不可用**，必须用 `py -3`。

```powershell
py -3 --version
```

## 2.2 安装依赖

```powershell
py -3 -m pip install -r scripts/requirements.txt
# 或最小集：
py -3 -m pip install requests python-dotenv boto3
```

## 2.3 拉取工具仓库代码（无 git 时通过 GitLab REST API）

**Step 1 — OAuth 密码模式换 token：**

```http
POST ${GITLAB_BASE_URL}/oauth/token
Content-Type: application/json

{
  "grant_type": "password",
  "username":   "${GITLAB_USERNAME}",
  "password":   "${GITLAB_PASSWORD}"
}
```

返回 `access_token`（默认 2 小时有效）。

**Step 2 — 下载单个文件：**

```http
GET ${GITLAB_BASE_URL}/api/v4/projects/${GITLAB_PROJECT_ID}/repository/files/{文件名URL编码}/raw?ref=main
Authorization: Bearer <access_token>
```

需下载的文件：

```
post_moments.py
config.py
utils.py
retry.py
validation.py
requirements.txt
.env.example
```

> 仓库附带的 [`scripts/gitlab_pull.py`](../scripts/gitlab_pull.py) 已封装上述两步，直接运行即可。

## 2.4 准备账号 CSV

账号库 CSV **不在本仓库**（被 `.gitignore` 拦截），有两种获取方式：

### 方式 A：从 `tester/auto-poster`（Project 207）运行时拉取（推荐）

`tester/auto-poster` 仍是真实账号池的唯一存储仓，本仓库通过 `scripts/gitlab_pull.py` 拉取：

```powershell
# .env 中需先设置：
#   GITLAB_BASE_URL=http://100.64.0.45:8999
#   GITLAB_PROJECT_ID=207   ← 关键：指向 auto-poster
#   GITLAB_TOKEN=glpat-xxxx    （或同时设置 GITLAB_USERNAME + GITLAB_PASSWORD）

py -3 scripts/gitlab_pull.py `
    --files "企管用户_邮箱密码pincode_200.csv" `
    --ref main `
    --out .
```

执行后会在当前目录得到 `企管用户_邮箱密码pincode_200.csv`（不会被 `git` 跟踪）。

### 方式 B：本地手动放置

把账号库 CSV 复制到工作目录（**绝对不要 commit**）。

### 字段要求

- 把账号库 CSV 复制到工作目录（**不要 commit**）。
- 按需求裁剪出 N 个用户的子集（如 `accounts_10.csv`，保留表头 + 前 10 行）。

字段名（小写英文或中文均可，参考 `config.py` 的 `ACCOUNTS_CSV_*_FIELDS`）：

| 字段名（任一）                              | 用途       |
| ------------------------------------------- | ---------- |
| `邮箱` / `email` / `username` / `Email`    | 登录用户名 |
| `密码` / `password` / `Password`           | 登录密码   |

模板见 [`templates/accounts.example.csv`](../templates/accounts.example.csv)。
