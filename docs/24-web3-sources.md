# 24. Web3 资讯多源采集与发布（web3 标签）

> 本文档介绍从 **9 个 Web3 资讯媒体**统一采集资讯 → 主体视角/繁体中文文案 →
> 广场纯文本发布的完整调用方式。所有内容统一打上 **`web3` 标签**（`_tag=web3`）。
> 做法与其它内容线一致，数据源换为 Web3 媒体，产出**纯文本帖**（无图，
> `media_info={"type":"text"}`）。

---

## 24.1 支持的 9 个来源

| key | 媒体 | 入口 | 取数方式 |
| --- | ---- | ---- | -------- |
| `techflow`   | 深潮 TechFlow    | `https://www.techflowpost.com/api/client/common/rss` | JSON（title/description/pubDate） |
| `web3bbs`    | Web3BBS          | `https://www.web3bbs.net/column_7.html`              | HTML（`article_<id>.html` 列表 + Web3 关键词过滤） |
| `foresight`  | ForesightNews    | `https://api.foresightnews.pro/v1/news`              | JSON（`data.list` = **base64 + zlib** 压缩） |
| `menews`     | ME News          | `POST https://api.me.news/aimpact/articles`          | JSON（需 Origin/Referer 头，`data.list`） |
| `web3caff`   | Web3Caff Research | `https://research.web3caff.com/wp-json/wp/v2/posts`  | WordPress REST（`title.rendered`） |
| `panews`     | PANews           | `https://www.panewslab.com/zh/newsflash`             | HTML SSR（`/zh/articles/<uuid>` 锚文本，去 `「」`） |
| `bingx`      | BingX News       | `https://bingx.com/zh-tc/news/web3`                   | HTML SSR（SSR JSON 里的 `headline` 字段，繁体） |
| `blockweeks` | BlockWeeks       | `https://blockweeks.com/feed/`                        | RSS（`/wp-json` 返回 401 → 改用 feed） |
| `wublock`    | 吴说 WuBlock123   | `https://www.wublock123.com/`                         | HTML（**阿里云 WAF**，脚本内置 `acw_sc__v2` cookie 求解） |

> 全部**公开、无需登录**。请勿在仓库或 `.env` 写入任何账号密码（见 `docs/09-security.md`）。
>
> **反爬说明**：
> - `foresight` 的 `data.list` 是 base64+zlib，脚本自动解压。
> - `wublock` 首页是阿里云 WAF 挑战页（4KB shell + `arg1`），脚本内置确定性求解算法算出
>   `acw_sc__v2` cookie 后二次请求拿正文；若站点轮换 WAF 常量导致再次返回 shell，
>   需从 shell 内联 JS 重新取 `key`。
> - `menews` 需带 `Origin: https://www.me.news` 与 `Referer` 头。
> - `blockweeks` 的 `wp-json` 被锁（401），改用公开 RSS `/feed/`。

---

## 24.2 采集脚本 `fetch_web3.py`

```powershell
py -3 scripts/fetch_web3.py `
    --sources techflow,web3bbs,foresight,menews,web3caff,panews,bingx,blockweeks,wublock `
    --per-site 10 `
    --tag web3 `
    --dedupe-file state/seen_web3.json `
    --output web3_raw.csv
```

- `--sources`：逗号分隔，缺省=全部 9 源；每源取 `--per-site` 条。
- `--dedupe-file`：记录已用消息（归一化标题），**跨批次自动跳过、不重复发**；
  内置 60%~70% 词重叠判重，避免不同源报道同一事件时重复。
- 输出标准 moments CSV：`content`=标题，`image_urls` 空（纯文本帖），`_source=web3news`，
  附 `_site`（来源）、`_tag=web3`、`_brief`（摘要，供文案延展用）。

---

## 24.3 文案：主体视角 / 繁体中文延展

采集产出的 `content` 是原始标题。用 `caption_multilang.py` 改写为
**发帖人第一人称口吻**（可繁体中文），或按需自定义延展：

```powershell
py -3 scripts/caption_multilang.py --input web3_raw.csv --output moments_web3.csv --langs zh_hant
```

**主体视角写作建议（实战沉淀）：**
- 用发帖人第一人称转述+点评，而非直接贴标题；结合 `_brief` 摘要补一句上下文细节。
- 语气自然口语化，按主题（涨/跌/ETF/监管/巨鲸/DeFi/NFT/交易所/AI）给不同的反应，
  避免固定「开场白…大家怎么看」模板导致同质化。
- 繁体中文用 `opencc`（`s2twp`，台湾用语：網路/槓桿/專案 等）。
- 单条控制在 **≤300 字符**，统一带 `#web3` 及来源标签（如 `#TechFlow`/`#PANews`）。

> 若配置 `LLM_TEXT_*` 环境变量，可在 `caption_multilang.py` 加 `--use-llm` 用大模型按人设生成。

---

## 24.4 端到端 runbook（一键脚本）

```powershell
# 默认：9 源各 10 条，10 账号轮询，繁体中文文案
py -3 scripts/run_web3.py --accounts-csv accounts_10.csv --per-site 10

# 指定来源与语言
py -3 scripts/run_web3.py --sources techflow,foresight,panews,bingx --langs zh_hant

# 只采集+文案、不发布（预演）
py -3 scripts/run_web3.py --skip-publish

# 无人值守
py -3 scripts/run_web3.py --accounts-csv accounts_10.csv --yes
```

| 参数 | 说明 | 默认 |
| ---- | ---- | ---- |
| `--sources` | 来源 key（逗号分隔） | 全部 9 源 |
| `--per-site` | 每源取多少条 | `10` |
| `--langs` | 文案语言 | `zh_hant`（繁体） |
| `--no-caption` | 不改写、直接发原标题 | 关 |
| `--dedupe-file` / `--reset-dedupe` | 去重档 / 清空去重 | `state/seen_web3.json` |
| `--skip-publish` / `--yes` | 只产素材 / 免确认 | 关 |

中间产物落 `web3_run/`，报告落 `result/publish_*.csv`。

**发布层轮询**：`素材条数 ÷ 账号数 = 每账号条数`。例如 30 条 ÷ 10 账号 = 每人 3 条；
30 条 ÷ 5 账号 = 每人 6 条。素材为纯文本，Phase 2 上传 0 张图，发布很快。

---

## 24.5 实战验证

- 9 源各取 5 条，实测 45/45 全部拿到当日真实标题（techflow/web3bbs/foresight/menews/
  web3caff/panews/bingx/blockweeks/wublock 全部可用）。
- 多轮发布累计验证：5 用户×6 帖、10 用户×3 帖等组合均 30/30 成功；
  繁体中文、发帖人第一人称、≤300 字符、跨批次不重复。

---

## 24.6 安全

- 沿用 `docs/09-security.md`：**不入库**任何账号 CSV / `.env` / token。
- 9 个来源均为公开媒体、无需登录；不要写入任何站点账号密码。
