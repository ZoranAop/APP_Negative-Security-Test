# 09. 凭证与脱敏约定

## 入库红线（永远不要 commit）

| 类别       | 示例                                                                 |
| ---------- | -------------------------------------------------------------------- |
| 账号密码   | GitLab 邮箱 / 密码、企管账号 / 密码 等明文                          |
| Token      | GitLab `access_token` / `refresh_token`、`Bearer …`                 |
| S3 临时凭证| `access_key_id` / `secret_access_key` / `session_token`             |
| 真实账号库 | `企管用户_邮箱密码pincode_200.csv`、`accounts_*.csv`                |
| 媒体       | 下载到本地的 `images/` `media/` `*.mp4` `*.png` 等                 |

以上由 `.gitignore` 默认拦截。**入库前请运行 `git status` 自查**。

## 通过 `.env` 注入

仓库内所有源码 / 文档不出现真实凭证，全部走 `.env`：

```bash
GITLAB_BASE_URL=http://100.64.0.45:8999
GITLAB_USERNAME=your_gitlab_email_here
GITLAB_PASSWORD=your_gitlab_password_here   # 或 GITLAB_TOKEN
LOGIN_URL=https://api.xxai.com/login
MOMENTS_API_URL=https://feed-api.xxai.com/api/v1/moments/
```

完整列表见 `.env.example`。

## 给 MCP 用的环境变量

启动 MCP Server 时务必同样注入这些环境变量（见 `mcp/README.md`），否则模型调用 `run_post_moments` / `run_post_video` 等工具时会因缺凭证而失败。

## 凭证轮换建议

- 任务结束后，对 OAuth password grant 颁发的 `access_token` / `refresh_token` 视为已暴露，重新登录获取新的。
- S3 临时凭证有时效性，到期重发即可。
- 真实账号密码若疑似泄露，立即修改企管侧密码并重建 `accounts_*.csv`。
