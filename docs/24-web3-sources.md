# 24. Web3 资讯多源采集与发布（web3 标签）

> 本文档介绍 Web3/Crypto/Tech 多源内容采集 → 主体视角文案 →
> 广场纯文本发布的完整调用方式。所有内容统一打上 **`web3` 标签**（`_tag=web3`）。
> 做法与其它内容线一致，数据源换为 Web3 媒体，产出**纯文本帖**（无图，
> `media_info={"type":"text"}`）。

---

## 24.1 Web3 源站点清单

### A. 已对接采集源（14 个，`fetch_web3.py` 中有 fetcher 实现）

#### 中文/繁中源（9 个）

| key | 媒体 | 入口 | 取数方式 |
| --- | ---- | ---- | -------- |
| `techflow`   | 深潮 TechFlow    | `https://www.techflowpost.com/api/client/common/rss` | JSON（title/description/pubDate） |
| `web3bbs`    | Web3BBS          | `https://www.web3bbs.net/column_7.html`              | HTML（`article_<id>.html` 列表 + Web3 关键词过滤） |
| `foresight`  | ForesightNews    | `https://foresightnews.pro` / API                    | JSON（`data.list` = **base64 + zlib** 压缩） |
| `menews`     | ME News          | `POST https://api.me.news/aimpact/articles`          | JSON（需 Origin/Referer 头，`data.list`） |
| `web3caff`   | Web3Caff Research | `https://research.web3caff.com/wp-json/wp/v2/posts`  | WordPress REST（`title.rendered`） |
| `panews`     | PANews           | `https://www.panewslab.com/zh/newsflash`             | HTML SSR（`/zh/articles/<uuid>` 锚文本，去 `「」`） |
| `bingx`      | BingX News       | `https://bingx.com/zh-tc/news/web3`                   | HTML SSR（SSR JSON 里的 `headline` 字段，繁体） |
| `blockweeks` | BlockWeeks       | `https://blockweeks.com/feed/`                        | RSS（`/wp-json` 返回 401 → 改用 feed） |
| `wublock`    | 吴说 WuBlock123   | `https://www.wublock123.com/`                         | HTML（**阿里云 WAF**，脚本内置 `acw_sc__v2` cookie 求解） |

#### 东南亚英文源（5 个）

| key | 媒体 | 入口 | 取数方式 | 说明 |
| --- | ---- | ---- | -------- | ---- |
| `e27`        | e27.co           | `https://e27.co/feed/`                               | RSS | 东南亚创投/科技/Web3 新闻 |
| `techinasia` | Tech in Asia     | `https://www.techinasia.com/feed`                    | RSS | 亚洲科技/创业/融资报道 |
| `coinlive`   | CoinLive         | `https://www.coinlive.com/news`                      | HTML | Crypto/Web3 英文新闻 |
| `superteam`  | Superteam SG     | `https://superteam.sg/`                              | HTML | 新加坡 Solana 生态/Web3 社区 |
| `blockhead`  | Blockhead        | `https://www.blockhead.co/`                          | HTML | 东南亚 Crypto/Web3 深度报道 |

### B. 注册源站点（待对接，按区域分类）

以下站点已登记为 Web3 标签内容源，后续可逐步实现 fetcher 对接：

#### 马来西亚 Web3

| 站点 | URL | 类型 |
|------|-----|------|
| Luno Learn (MY) | `https://www.luno.com/en/my/learn` | 加密货币教育/市场分析 |
| Malaysia Blockchain Week | `https://malaysiablockchainweek.com` | 马来西亚区块链峰会/活动 |
| Access Malaysia | `https://accessmalaysia.my` | 马来西亚 Web3 生态入口 |
| Lowyat Forum | `https://forum.lowyat.net` | 马来西亚科技社区/论坛（含 Crypto 版块） |

#### 泰国 Web3

| 站点 | URL | 类型 |
|------|-----|------|
| Bitcoin Addict | `https://bitcoinaddict.org` | 泰国最大 Crypto 社区/新闻 |
| Thai Blockchain | `https://thaiblockchain.org` | 泰国区块链协会/行业动态 |
| Bitcoin Thailand | `https://bitcointhailand.org` | 泰国比特币/Crypto 资讯 |
| Zipmex | `https://zipmex.com` | 东南亚加密交易所/市场资讯 |

#### 越南 Web3

| 站点 | URL | 类型 |
|------|-----|------|
| Coin68 | `https://coin68.com` | 越南最大 Crypto 新闻门户 |
| MarginATM | `https://marginatm.com` | 越南 Crypto 分析/教育 |
| VBA (Vietnam Blockchain Association) | `https://vba.org.vn` | 越南区块链协会/行业标准 |
| Kyros Ventures | `https://kyros.ventures` | 越南 Web3 VC/投资研究 |

#### 印尼 Web3

| 站点 | URL | 类型 |
|------|-----|------|
| Blockchain Media ID | `https://blockchainmedia.id` | 印尼区块链/Crypto 新闻 |
| Coinvestasi | `https://coinvestasi.com` | 印尼 Crypto 投资教育/分析 |
| Tokocrypto | `https://tokocrypto.com` | 印尼加密交易所/市场资讯 |

#### 全球顶级 Crypto 媒体

| 站点 | URL | 类型 |
|------|-----|------|
| CoinDesk | `https://www.coindesk.com` | 全球最大 Crypto 新闻（英文） |
| CoinTelegraph | `https://cointelegraph.com` | 全球 Crypto/区块链媒体 |
| Decrypt | `https://decrypt.co` | Crypto/Web3 深度报道 |
| The Defiant | `https://thedefiant.io` | DeFi 专业媒体 |
| Bankless | `https://www.bankless.com` | DeFi/Web3 深度内容/播客 |
| Blockworks | `https://blockworks.co` | 机构级 Crypto 研究/新闻 |
| BeInCrypto | `https://beincrypto.com` | 多语言 Crypto 新闻 |

#### 东南亚/全球 Web3 活动

| 站点 | URL | 类型 |
|------|-----|------|
| TOKEN2049 | `https://www.token2049.com` | 亚洲最大 Crypto 峰会（新加坡/迪拜） |
| Coinfest Asia | `https://coinfest.asia` | 东南亚 Crypto 嘉年华（巴厘岛） |
| ETHGlobal | `https://ethglobal.com` | 以太坊全球黑客松/开发者活动 |
| Solana Breakpoint | `https://solana.com/breakpoint` | Solana 年度开发者大会 |
| Chain Debrief | `https://chaindebrief.com` | 东南亚 Web3 研究/活动 |

#### Web3 社交/社区平台

| 站点 | URL | 类型 |
|------|-----|------|
| Galxe | `https://galxe.com` | Web3 任务/凭证/社区平台 |
| Zealy | `https://zealy.io` | Web3 社区增长/任务平台 |
| Mirror.xyz | `https://mirror.xyz` | Web3 去中心化写作/出版 |
| Warpcast | `https://warpcast.com` | Farcaster 社交协议客户端 |
| Lens Protocol | `https://lens.xyz` | 去中心化社交图谱协议 |

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
    --sources techflow,web3bbs,foresight,menews,web3caff,panews,bingx,blockweeks,wublock,e27,techinasia,coinlive,superteam,blockhead `
    --per-site 10 `
    --tag web3 `
    --dedupe-file state/seen_web3.json `
    --output web3_raw.csv
```

- `--sources`：逗号分隔，缺省=全部 14 源；每源取 `--per-site` 条。
- `--dedupe-file`：记录已用消息（归一化标题），**跨批次自动跳过、不重复发**；
  内置 60%~70% 词重叠判重，避免不同源报道同一事件时重复。
- 输出标准 moments CSV：`content`=标题，`image_urls` 空（纯文本帖），`_source=web3news`，
  附 `_site`（来源）、`_tag=web3`、`_brief`（摘要，供文案延展用）。

---

## 24.3 文案：语言统一化文案改写（web3_caption_by_role.py）

采集产出的 `content` 是原始标题（多为中文）。用 `web3_caption_by_role.py` 改写为
**发帖人第一人称口吻**，并确保**整条帖子语言统一**（不出现中英混杂）。

### 语言统一化原则

| 输出语言 | 正文组成 | 说明 |
|---------|---------|------|
| `zh_hant` | 中文标题 + 繁中点评 | 标题+评论都是繁中，保持一致 |
| `en` | 英文点评 × 2 | **不嵌入中文标题**，纯英文评论内容 |
| `ms` | 马来语点评 × 2 | **不嵌入中文标题**，纯马来语评论内容 |
| `ja` | 日文点评 + 中文标题 | 日文用户可读中文，保留标题 |

### --lang 策略参数

| 值 | 说明 |
|----|------|
| `content` | 按原始标题语言自动判断（中文→繁中，英文→英文） |
| `zh_hant` / `en` / `ja` / `ms` | 强制统一某种语言 |
| `mixed_en_ms` | **50%英文 + 50%马来语**交替分配（推荐多语言场景） |
| `auto-nick` | 按账号昵称的文字系统判断（旧逻辑） |

### 用法示例

```powershell
# 50% 英文 + 50% 马来语，150-300 字符（语言严格统一）
py -3 scripts/web3_caption_by_role.py `
    --input web3_raw.csv --output moments.csv `
    --accounts-csv accounts_20.csv `
    --lang mixed_en_ms --min-len 150 --max-len 300

# 全部繁体中文
py -3 scripts/web3_caption_by_role.py `
    --input web3_raw.csv --output moments.csv `
    --accounts-csv accounts.csv --lang zh_hant

# 按内容语言自动判断
py -3 scripts/web3_caption_by_role.py `
    --input web3_raw.csv --output moments.csv `
    --accounts-csv accounts.csv --lang content
```

**主体视角写作建议（实战沉淀）：**
- 用发帖人第一人称口吻点评，语气自然口语化。
- 按新闻意图（涨/跌/ETF/监管/巨鲸/DeFi/交易所/AI/安全/研报）选择不同语气的评论。
- 马来语/英文帖不嵌入中文原标题，避免语言混杂。
- 单条控制在 `--min-len` 到 `--max-len` 之间，统一带 `#web3` 及来源标签。
- 每个意图有 4 条评论轮换，通过 seed 避免连续帖子用相同评论。

---

## 24.4 端到端 runbook（一键脚本）

```powershell
# 默认：14 源各 10 条，按内容语言自动判断
py -3 scripts/run_web3.py --accounts-csv accounts_10.csv --per-site 10

# 50% 英文 + 50% 马来语，150-300 字符（语言统一化）
py -3 scripts/run_web3.py --accounts-csv accounts_20.csv --per-site 5 `
    --lang mixed_en_ms --min-len 150 --max-len 300 --yes

# 仅东南亚英文源
py -3 scripts/run_web3.py --sources e27,techinasia,coinlive,superteam,blockhead --lang en

# 指定中文源
py -3 scripts/run_web3.py --sources techflow,foresight,panews,bingx --lang zh_hant

# 只采集+文案、不发布（预演）
py -3 scripts/run_web3.py --skip-publish

# 无人值守
py -3 scripts/run_web3.py --accounts-csv accounts_10.csv --yes
```

| 参数 | 说明 | 默认 |
| ---- | ---- | ---- |
| `--sources` | 来源 key（逗号分隔） | 全部 14 源 |
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

- 14 源各取 5 条，实测原有 9 源（techflow/web3bbs/foresight/menews/
  web3caff/panews/bingx/blockweeks/wublock）全部可用。
- 新增 5 源（e27/techinasia/coinlive/superteam/blockhead）为东南亚英文源，
  内容偏向创投/科技/Crypto 报道，适合英文文案（`--lang en`）场景。
- 多轮发布累计验证：5 用户×6 帖、10 用户×3 帖等组合均 30/30 成功；
  繁体中文、发帖人第一人称、≤300 字符、跨批次不重复。

---

## 24.7 Firecrawl 增强采集

当 RSS/API 源不稳定或需要抓取反爬网站时，可使用 Firecrawl 作为补充采集方式。

### 24.7.1 配置

1. 确保 `~/.workbuddy/skills/firecrawl/.api_key` 存在（见 `docs/30-firecrawl-migration.md`）
2. 或在 `.env` 中设置 `FIRECRAWL_API_KEY`

### 24.7.2 使用方式

#### 方式一：抓取指定 URL 列表

```powershell
# 创建 URL 列表文件
Set-Content scripts/urls_web3.txt @'
https://www.coindesk.com
https://cointelegraph.com
https://www.theblock.co
'https@' -Encoding UTF8

# 运行（自动输出到 web3_run/ 目录）
py -3 scripts/run_web3_fc.py --use-firecrawl --urls-file scripts/urls_web3.txt `
    --accounts-csv accounts_10.csv --per-site 5 --yes
```

#### 方式二：Firecrawl Search 搜索新闻

```powershell
py -3 scripts/run_web3_fc.py --use-firecrawl --search "bitcoin ethereum crypto news" `
    --fc-limit 10 --accounts-csv accounts_10.csv --lang en --yes
```

#### 方式三：混合模式（原有源 + Firecrawl 补充）

```powershell
py -3 scripts/run_web3_fc.py --sources techflow,foresight,wublock `
    --urls-file scripts/urls_web3.txt --per-site 5 --yes
```

### 24.7.3 脚本说明

| 脚本 | 用途 |
|------|------|
| `fetch_firecrawl.py` | 独立的 Firecrawl 采集器，输出标准 moments CSV |
| `run_web3_fc.py` | 完整版一键发布（含文案改写 + 发布），支持 Firecrawl 模式 |

### 24.7.4 降级策略

- Firecrawl 失败时自动回退到原有 fetchers
- 无需修改现有工作流程，`--use-firecrawl` 为可选开关

---

## 24.6 安全

- 沿用 `docs/09-security.md`：**不入库**任何账号 CSV / `.env` / token。
- 14 个来源均为公开媒体、无需登录；不要写入任何站点账号密码。
