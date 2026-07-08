# 03. 图文 / 文本发帖（post_moments.py / publish_from_tokens.py）

## 3.1 流程

```
读取账号 CSV 登录 → 读取素材 CSV → 轮询(Round-Robin) 分配 → 逐条 / 并发发布
```

## 3.2 素材 CSV 表头

```csv
content,visibility,room_id,image_urls,location_name,location_address,location_lat,location_lon
```

| 字段              | 说明                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------ |
| `content`         | **正文（必填）**                                                                           |
| `visibility`      | `0=公开` / `1=私密` / `2=部分可见`                                                         |
| `room_id`         | 房间 ID（可空）。**非空 = 发到群组/房间**，为空 = 发到个人动态（见 [`14-room-moments.md`](14-room-moments.md)）|
| `image_urls`      | 多张图用 **英文逗号** 分隔；留空 = 纯文字帖；填外部 URL 时脚本会自动下载并转存到 S3        |
| `location_*`      | 位置信息（可空）                                                                           |

> 图片**最多 9 张**。

模板见 [`templates/moments.example.csv`](../templates/moments.example.csv)。

## 3.3 常用命令

```powershell
py -3 scripts/post_moments.py `
    --accounts-csv "accounts_10.csv" `
    --csv "moments.csv" `
    --num-accounts 0 `
    --num-posts 0 `
    --concurrency 1 `
    --delay 2.0
```

| 参数            | 说明                                                                       |
| --------------- | -------------------------------------------------------------------------- |
| `--num-accounts`| `0` = 用 CSV 内全部账号；`N` = 随机抽 N 个                                |
| `--num-posts`   | `0` = 发全部素材（**不打乱**，保证轮询顺序）；`M` = 随机抽 M 条           |
| `--concurrency` | 并发线程数；`=1` 时顺序发并按 `--delay` 间隔                              |
| `--delay`       | 顺序模式下每条之间的延迟（秒）                                            |

## 3.4 轮询规则

```
素材数 ÷ 账号数 = 每账号帖数
```

- `20 帖 / 10 账号 = 每账号 2 帖`
- `10 帖 / 10 账号 = 每账号 1 帖`

## 3.5 结果输出

`result/post_results_<时间戳>.csv` + `_summary.txt`，含每帖 `moment_id`、状态、成功率。

---

## 3.6 高级：`publish_from_tokens.py`（避开 429 的两阶段发布）

`post_moments.py` 会**在启动时并发登录所有账号**。实战中 ≥15 个账号同时登录
会有较大概率触发服务端限流（HTTP 429）——参见 `docs/05-batch-records.md`
批次 7-8 的记录（12/20 → 首次登录失败）。

`scripts/publish_from_tokens.py` 把流程拆成三阶段：

1. **登录**：顺序执行，账号之间间隔 `LOGIN_SPACING`（默认 2.5s），
   遇 429 自动指数退避。产出 `{email: token}` 映射并落盘。
2. **上传**：把 CSV 里所有外部图片 URL 去重后统一上传到 S3，
   `image_urls` 就地替换为 AWS URL 缓存。
3. **发布**：并发（默认 4）向后端 `/api/v1/moments/` POST。

```powershell
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_20.csv `
    --csv moments.csv `
    --concurrency 4 `
    --login-spacing 2.5 `
    --tokens-out result/tokens.json
```

### 复用 token

第二次跑同批账号时，直接复用：

```powershell
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_20.csv `
    --csv moments_batch3.csv `
    --tokens-in result/tokens.json
```

token 无效则自动重新登录缺失账号并合并回文件。

### 与 post_moments.py 的关系

| 场景                                | 推荐脚本                      |
| ----------------------------------- | ----------------------------- |
| ≤ 10 个账号 / 一次性发帖            | `post_moments.py`             |
| ≥ 15 个账号 / 高并发 / 多批次       | `publish_from_tokens.py`      |
| 上一批 token 还没过期，想跳过登录    | `publish_from_tokens.py`      |

功能等价，`publish_from_tokens.py` 更适合大规模、更容易失败恢复。
