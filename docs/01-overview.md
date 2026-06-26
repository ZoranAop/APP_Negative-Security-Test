# 01. 整体背景与资源

## 项目目标

通过 HTTP 接口方式，向 **XXAI 广场（朋友圈 / 动态）** 批量发布：

- 纯文字
- 图文（最多 9 张图）
- 视频（带封面）

适用于：内容运营、压测、灰度内容铺设。

## 资源清单

| 项目          | 内容                                                                                 |
| ------------- | ------------------------------------------------------------------------------------ |
| 入口 URL      | `${GITLAB_BASE_URL}/tester/auto-poster` — GitLab 仓库，**不是**可直接调用的 API     |
| GitLab 账号   | 通过 `.env` 中的 `GITLAB_USERNAME` / `GITLAB_PASSWORD` 或 `GITLAB_TOKEN` 注入       |
| 工具仓库      | GitLab 项目 `tester/auto-poster`（Python 自动发帖系统，`project_id=207`）           |
| 账号库        | `企管用户_邮箱密码pincode_200.csv`（200 个运营/压测账号，**不入库**，本地存放）     |

## 核心 API

> 全部配置走 `.env`，下表展示文档默认值。

| 用途                 | 方法 + 地址（默认）                                                       |
| -------------------- | ------------------------------------------------------------------------- |
| 登录获取 token       | `POST ${LOGIN_URL}`（默认 `https://devapi-x.tp-ex.com/login`）            |
| 获取 S3 上传临时凭证 | `POST ${UPLOAD_CREDENTIALS_URL}`（默认 `…/file/upload/credentials`）      |
| 发布动态             | `POST ${MOMENTS_API_URL}`（默认 `http://100.64.0.47:8889/api/v1/moments/`）|
| 接口文档(OpenAPI)    | `${OPENAPI_DOC_URL}`，Swagger UI 在 `/docs`                              |

> ⚠️ 全部 `100.64.0.x` 都是内网地址，需在 VPN / 内网环境调用。
