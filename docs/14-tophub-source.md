# 14. tophub 热榜文本源（tophub.today/hot）

## 14.1 背景

前面的素材源（opennana / open-prompts / lovimg）产出的都是**图片**素材，
配套「主体视角文案」发图文。有时我们想发一批**纯文字**的「话题 / 观点 / 反应」
类动态，让 feed 更像真实用户的日常吐槽与讨论。

`scripts/fetch_tophub.py` 从 [tophub.today/hot](https://tophub.today/hot)
抓取全网热榜话题标题，产出与其他 `fetch_*` 脚本一致的 moments CSV
（只是 `image_urls` 恒为空），再交给 `caption_multilang.py` 改写成
**多语言主体视角文案**后发布。

> tophub 的 `/hot` 页面**公开、无需登录**。脚本不涉及任何账号密码，
> 也**不要**把任何 tophub 账号写进仓库或 `.env`（见 `docs/09-security.md`）。

## 14.2 采集原理

tophub 未开放 `/hot` 的公开 JSON API，页面为服务端渲染 HTML。
虽然 class 名做了混淆，但每一条热榜条目都被渲染在一个重复的
`center-item` 卡片里（一条一个）。脚本按 `center-item` 切块，
取每块内第一个「有意义的文本节点」作为话题标题：

- 跳过纯数字 / 排名 / 百分号 / 符号；
- 跳过 `查看更多`、`热`、`·` 等结构性噪声。

页面通常一次给出 100 条热榜。

## 14.3 输入 / 输出

输入：无（直接抓取 `/hot`）。

输出：标准 moments CSV，列与其他 fetch 脚本一致：

```
content,visibility,room_id,image_urls,location_name,location_address,location_lat,location_lon
```

`image_urls` 恒为空 → 发布时走 `media_info={"type":"text"}`（纯文本动态）。

## 14.4 CLI

```powershell
# 抓 100 条热榜话题
py -3 scripts/fetch_tophub.py --limit 100 --output tophub_raw.csv

# 过滤明显广告 / 促销条目 + 跨批次去重
py -3 scripts/fetch_tophub.py `
    --limit 100 `
    --exclude-ads `
    --dedupe-file result/used_topics.json `
    --output tophub_raw.csv
```

- `--limit`：最多写多少条（默认 100）。
- `--exclude-ads`：丢弃标题含 `优惠/折扣/推广/广告/coupon/promo…` 的条目
  （与 `docs/11-anti-ad-filtering.md` 同一思路）。
- `--dedupe-file`：JSON，记录已用话题的哈希，跨批次去重后合并回写。

也可以通过多源统一入口带上 tophub（text 源与 image 源混排）：

```powershell
py -3 scripts/multi_source_fetch.py `
    --sources opennana,tophub `
    --limit 100 `
    --output moments_raw.csv `
    --shuffle
```

## 14.5 端到端 runbook（热榜话题 → 多语言 → 20 账号发布）

这是本源实战跑通的完整链路（100 条话题、20 个企管账号、100% 成功）：

```powershell
# 1. 抓取 100 条热榜话题（纯文本）
py -3 scripts/fetch_tophub.py --limit 100 --exclude-ads `
    --dedupe-file result/used_topics.json --output tophub_raw.csv

# 2. 多语言主体视角改写：英 / 繁中 / 日
#    需要「英+日合计 80%、繁中 20%」这类分布时，可多次调用并按比例合并，
#    或直接用 --langs 控制语言集合（详见 docs/13-multilang-captions.md）。
py -3 scripts/caption_multilang.py `
    --input tophub_raw.csv `
    --output moments.csv `
    --langs en,zh_hant,ja

# 3. 从 500 企管账号 CSV 中随机抽 20 个（见 docs/05-batch-records.md 的抽样约定），
#    落地为 accounts_20.csv（列：邮箱,密码,昵称）。

# 4. 两阶段安全发布（顺序登录避 429 → 并发发帖）
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_20.csv `
    --csv moments.csv `
    --concurrency 4 `
    --login-spacing 2.5 `
    --tokens-out result/tokens.json
```

### 语言分布小抄（英+日 80% / 繁中 20%）

`caption_multilang.py --langs` 会把语言集合按行均匀轮询后打乱。
若要严格控制「英+日=80%、繁中=20%」的比例，先按目标条数生成语言排布再喂给它：

- 100 条 → 繁中 20 条；剩下 80 条在 en / ja 之间随机拆分（如 en 30 / ja 50）。
- 关键校验：`en + ja == 80`（占比 80%），`zh_hant == 20`（占比 20%），**不含简体**。

## 14.6 环境变量

`fetch_tophub.py` 全部走默认值即可，无需配置。可选覆盖：

| 变量               | 默认值                        | 说明                    |
| ------------------ | ----------------------------- | ----------------------- |
| `TOPHUB_HOT_URL`   | `https://tophub.today/hot`    | 热榜页面 URL            |
| `TOPHUB_REFERER`   | `https://tophub.today/`       | 请求 Referer            |
| `TOPHUB_USER_AGENT`| Chrome UA                     | 请求 User-Agent         |

## 14.7 注意事项

- **纯文本源**：`image_urls` 恒空；与图片源混排时，两阶段发布的
  Phase 2（S3 上传）会自动跳过没有图片的行。
- **话题时效性**：热榜实时变动，两次抓取结果会不同；用 `--dedupe-file`
  避免跨批次重复。
- **合规**：热榜标题可能含时事/敏感话题，改写文案时保持生活化、分享型语气，
  避免直接搬运争议性表述（与 `docs/13-multilang-captions.md §13.6` 一致）。
