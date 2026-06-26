# 03. 图文 / 文本发帖（post_moments.py）

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
| `room_id`         | 房间 ID（可空）                                                                            |
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
