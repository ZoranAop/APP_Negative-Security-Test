# 26. 中古轻奢（Vintage Luxury）标签

> 「中古轻奢」标签专注于**二手奢侈品/中古包/轻奢转售**平台的内容采集与发布。
> 内容来源为东南亚及港台地区的 15 个中古奢侈品交易平台，
> 发帖时统一使用**英文文案 + 英文话题标签（含站点英文名称）**。

---

## 26.1 标签规则

| 规则项 | 说明 |
|--------|------|
| 标签名 | `vintage_luxury`（中古轻奢） |
| 语言 | 英文（`en`） |
| 帖子类型 | 图文帖（带图片） |
| 话题标签 | 英文，**必须包含来源站点英文名称** |
| 话题格式 | `#VintageLuxury #PreLoved #<SiteName> #<BrandTag>` |

### 话题标签规范

当选择「中古轻奢」标签内容发帖时，话题标签**必须带网站英文名称**：

```
#HuntStreet #LuxuryForLess #DesignerBags
#StyleTribute #SustainableFashion #Hermès
#Carousell #AuthenticLuxury #PreOwned
```

组合机制（3个标签）：

| 位置 | 来源 | 说明 |
|------|------|------|
| 1 | 来源站点英文名 | 固定，如 `#HuntStreet` `#BrandOff` |
| 2 | 候选池随机抽1 | 从9个通用标签中随机 |
| 3 | 候选池随机抽1 | 从9个通用标签中随机（不重复） |

候选池（9个）：
`#AuthenticLuxury` `#DesignerBags` `#LuxuryFinds` `#SecondHandLuxury`
`#SustainableFashion` `#PreOwned` `#{品牌名}` `#TimelessStyle` `#LuxuryForLess`

站点英文名称映射：

| 站点域名 | 话题标签名 |
|----------|-----------|
| huntstreet.com | `#HuntStreet` |
| styletribute.com | `#StyleTribute` |
| carousell.com | `#Carousell` |
| brandoff.com.hk | `#BrandOff` |
| hulaluxe.com | `#HulaLuxe` |
| belluxestore.com | `#BelluxeStore` |
| luxee.me | `#Luxee` |
| popchill.com | `#PopChill` |
| carousell.com.tw | `#CarousellTW` |
| tw.bid.yahoo.com | `#YahooBidTW` |
| luxeavenue.com.my | `#LuxeAvenue` |
| carousell.com.my | `#CarousellMY` |
| sfbrandname.com | `#SFBrandName` |
| brandnamemoney.com | `#BrandNameMoney` |
| zalind.com | `#Zalind` |

---

## 26.2 源站点清单（15 个）

### 新加坡/东南亚

| 站点 | URL | 类型 |
|------|-----|------|
| Hunt Street | `https://www.huntstreet.com` | 新加坡/东南亚二手奢侈品电商 |
| Style Tribute | `https://www.styletribute.com` | 新加坡轻奢寄售平台 |
| Carousell | `https://www.carousell.com` | 东南亚综合二手交易（含奢侈品） |
| Hula Luxe | `https://www.hulaluxe.com` | 东南亚二手名牌包/奢侈品 |
| Belluxe Store | `https://www.belluxestore.com` | 东南亚中古奢侈品精选店 |
| Luxee | `https://luxee.me` | 东南亚轻奢二手平台 |

### 马来西亚

| 站点 | URL | 类型 |
|------|-----|------|
| Luxe Avenue MY | `https://luxeavenue.com.my` | 马来西亚中古奢侈品 |
| Carousell MY | `https://www.carousell.com.my` | 马来西亚 Carousell（含奢侈品） |

### 香港

| 站点 | URL | 类型 |
|------|-----|------|
| Brand Off HK | `https://www.brandoff.com.hk` | 香港中古名牌店（日本品牌） |

### 台湾

| 站点 | URL | 类型 |
|------|-----|------|
| PopChill | `https://www.popchill.com` | 台湾二手精品/中古包平台 |
| Carousell TW | `https://www.carousell.com.tw` | 台湾 Carousell（含奢侈品） |
| Yahoo 拍卖 TW | `https://tw.bid.yahoo.com` | 台湾 Yahoo 拍卖（含名牌二手） |

### 泰国

| 站点 | URL | 类型 |
|------|-----|------|
| SF Brand Name | `https://www.sfbrandname.com` | 泰国中古名牌交易 |
| Brand Name Money | `https://www.brandnamemoney.com` | 泰国名牌包/奢侈品买卖 |
| Zalind | `https://www.zalind.com` | 泰国二手奢侈品平台 |

---

## 26.3 采集脚本 `fetch_vintage_luxury.py`

```powershell
py -3 scripts/fetch_vintage_luxury.py `
    --target 30 `
    --output moments_vintage_luxury.csv
```

- 从 15 个站点轮询采集商品图文（商品标题 + 商品主图 CDN URL）
- 自动为每条内容生成英文话题标签（含站点英文名）
- 输出标准 moments CSV，可直接进入 `publish_from_tokens.py` 发布

---

## 26.4 端到端 runbook

```powershell
# 1. 采集中古轻奢图文素材
py -3 scripts/fetch_vintage_luxury.py --target 30 --output moments_vintage_luxury.csv

# 2. 发布（自动执行图片质量管线：尺寸验证 + 宫格调整）
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_10.csv --csv moments_vintage_luxury.csv `
    --concurrency 4 --tokens-out result/tokens.json
```

---

## 26.5 与其他标签的区别

| 标签 | 内容类型 | 语言 | 话题标签 | 图片 |
|------|---------|------|---------|------|
| `web3` | 资讯/评论 | en/zh_hant | `#web3 #crypto` | 无（纯文本） |
| `xhs`（小红书） | 生活方式 | zh | 原文话题 | 多图 |
| `vintage_luxury`（中古轻奢） | 商品展示 | **en** | **必带站点英文名** | 商品图 |

---

## 26.6 安全

- 沿用 `docs/09-security.md`：不入库任何账号/密码/token。
- 15 个站点均为公开商品页面，无需登录即可浏览。
