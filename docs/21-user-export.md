# 21. 企管用户账号导出（export_users.py）

> 从 XXAI 商户后台批量导出企管用户账号（含**密码 / pincode**），生成广场发布工具所需的账号池 CSV。
>
> 产出列与 `templates/accounts.example.csv` 一致：`序号,user_id,邮箱,用户名,昵称,密码,pincode`，
> 可直接作为 `post_moments.py` / `publish_from_tokens.py` 的账号源。

---

## 21.1 背景

广场发布需要一批可登录的企管测试账号。后台 `business.xxai.com`（商户管理端）
的「用户列表」不直接提供批量导出，密码/pincode 也不在列表接口里。本工具通过
**逆向出的接口**批量拉取，替代人工在网页上逐个点「编辑」复制。

## 21.2 接口逆向结论

前端为 Vue SPA，`baseURL = https://merchant-api.xxai.com`。关键接口：

| 接口 | 方法 | 说明 | 是否含密码/pincode |
|------|------|------|--------------------|
| `/user/pool-users` | GET | 用户池列表（约 10000，含 email） | 否 |
| `/user/users` | GET | 企管注册用户列表（约 21） | 否 |
| `/user/assume` | POST | **按 user_id 获取用户凭证** | **是** |
| `/stats` | GET | 用户统计（总数等） | — |

**核心发现：** 后台「用户列表 → 操作列『编辑』」打开的弹窗（`EditUserDialog`）中，
密码框与 pincode 框显示的值来源于 `props.user.password` / `props.user.pin_code`。
这些字段并非来自列表接口，而是点编辑时前端先调用：

```
POST /user/assume
Authorization: Bearer <商户端 token>
Content-Type: application/json

{ "user_id": 1xxxxxxxxxxxxxx }
```

响应：

```json
{
  "code": 0, "type": "SUCCESS", "msg": "OK",
  "data": {
    "localpart": "user_1xxxxxxxxxxxxxx",
    "token": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "password": "<12位随机密码>",
    "pin_code": "<6位数字>",
    "device_id": "merchant"
  }
}
```

`data.password` / `data.pin_code` 即编辑弹窗里可复制的密码与 pincode。

> 说明：`/user/assume` 同时被 Matrix 会话初始化复用（会带 `device_id` / `device_name`），
> 但导出场景仅需传 `user_id`。个别用户可能返回 `code=50001 / HTTP 500`（账号数据异常），
> 脚本会重试并在结束时列出失败的 user_id。

## 21.3 鉴权

需要**商户端 Bearer Token**（不是 GitLab token，也不是 admin-api token）：

1. 浏览器登录 `https://business.xxai.com`
2. F12 → Network → 任一 `merchant-api.xxai.com` 请求 → 复制请求头 `Authorization: Bearer <...>` 的 token 部分
3. 写入 `.env` 的 `XXAI_TOKEN`（**切勿提交**，`.env` 已被 `.gitignore` 忽略）

Token 为 JWT，含 `merchant_id` / `user_id` / `exp`，有效期约 7 天，过期需重新获取。

## 21.4 配置（.env）

```dotenv
# 商户端 API
XXAI_API_BASE=https://merchant-api.xxai.com
XXAI_TOKEN=your_merchant_bearer_token_here          # 商户端 Bearer Token（勿提交）

# 导出参数（也可用命令行覆盖）
XXAI_SOURCE=pool          # pool=用户池 / register=企管注册用户
XXAI_COUNT=2000
XXAI_CONCURRENCY=8        # /user/assume 并发数
```

## 21.5 用法

```powershell
# 安装依赖
py -3 -m pip install -r scripts/requirements.txt

# 默认：用户池前 2000，含密码/pincode
py -3 scripts/export_users.py

# 指定数量 / 来源 / 输出
py -3 scripts/export_users.py --count 2000 --source pool --out accounts_2000.csv

# 仅账号信息，跳过密码/pincode（快）
py -3 scripts/export_users.py --count 500 --no-credentials
```

输出示例（`accounts_pool_2000.csv`，utf-8-sig，Excel 直接打开）：

```
序号,user_id,邮箱,用户名,昵称,密码,pincode
1,1xxxxxxxxxxxxxx,u_xxxxxxxx@xxai.com,u_xxxxxxxx,昵称示例1,<12位随机密码>,<6位数字>
2,1xxxxxxxxxxxxxx,u_yyyyyyyy@xxai.com,u_yyyyyyyy,昵称示例2,<12位随机密码>,<6位数字>
...
```

## 21.6 与发布工具衔接

导出的 CSV 即账号池，供 `post_moments.py` / `publish_from_tokens.py` 使用
（参见 `docs/03-post-moments.md`）。账号 CSV 字段映射见 `scripts/config.py` 的
`ACCOUNTS_CSV_*_FIELDS`。

## 21.7 安全约定

- 导出的 `accounts_*.csv` / `*_pincode_*.csv` / `企管用户*.csv` 均已被 `.gitignore` 忽略，
  **禁止将含真实密码/pincode 的文件提交到仓库**。
- 仓库内只保留 `templates/accounts.example.csv`（占位示例）。
- Token 仅存于本地 `.env`，用完即弃，勿写入代码或文档。

参见 `docs/09-security.md`。
