# 27. 设计师（Designer）标签

> 「设计师」标签专注于**独立设计师品牌/买手店/设计师平台**的内容采集与发布。
> 内容来源为全球 38 个设计师品牌电商、买手店及独立设计平台，
> 发帖时统一使用**英文文案 + 英文话题标签（含站点英文名称）**。

---

## 27.1 标签规则

| 规则项 | 说明 |
|--------|------|
| 标签名 | `designer`（设计师） |
| 语言 | 英文（`en`） |
| 帖子类型 | 图文帖（带图片） |
| 话题标签 | 英文，**必须包含来源站点英文名称** |
| 话题格式 | `#<SiteName> #<RandomTag1> #<RandomTag2>` |

### 话题标签规范

选择「设计师」标签内容发帖时，话题标签**必须带网站英文名称**，均为英文：

```
#SSENSE #EmergingDesigners #IndependentFashion
#DoverStreetMarket #AvantGarde #ConceptualDesign
#Farfetch #DesignerFinds #LuxuryFashion
```

组合机制（3个标签）：

| 位置 | 来源 | 说明 |
|------|------|------|
| 1 | 来源站点英文名（固定） | 如 `#SSENSE` `#Farfetch` |
| 2 | 候选池随机抽1 | 从通用标签池中随机 |
| 3 | 候选池随机抽1（不重复） | 从通用标签池中随机 |

候选池：
`#EmergingDesigners` `#IndependentFashion` `#AvantGarde` `#ConceptualDesign`
`#DesignerFinds` `#LuxuryFashion` `#Minimalist` `#SustainableDesign`
`#{品牌名}` `#CuratedStyle` `#ArtisanCraft`

站点英文名称映射：

| 站点域名 | 话题标签名 |
|----------|-----------|
| ssense.com | `#SSENSE` |
| ln-cc.com | `#LNCC` |
| brownsfashion.com | `#Browns` |
| shop.doverstreetmarket.com | `#DoverStreetMarket` |
| hlorenzo.com | `#HLorenzo` |
| machine-a.com | `#MachineA` |
| farfetch.com | `#Farfetch` |
| mytheresa.com | `#Mytheresa` |
| modaoperandi.com | `#ModaOperandi` |
| net-a-porter.com | `#NetAPorter` |
| matchesfashion.com | `#MatchesFashion` |
| garmentory.com | `#Garmentory` |
| wolfandbadger.com | `#WolfAndBadger` |
| notjustalabel.com | `#NotJustALabel` |
| apoc-store.com | `#APOCStore` |
| zozo.jp | `#ZOZO` |
| houyhnhnm.jp | `#Houyhnhnm` |
| fashionsnap.com | `#Fashionsnap` |
| gr8.jp | `#GR8` |
| coverchord.com | `#Coverchord` |
| musinsa.com | `#Musinsa` |
| us.wconcept.com | `#WConcept` |
| 29cm.co.kr | `#29CM` |
| eqlstore.com | `#EQL` |
| plain-me.com | `#PlainMe` |
| marais.com.tw | `#Marais` |
| pinkoi.com | `#Pinkoi` |
| designorchard.sg | `#DesignOrchard` |
| beyondthevines.com | `#BeyondTheVines` |
| finnishdesignshop.com | `#FinnishDesignShop` |
| nordicnest.com | `#NordicNest` |
| connox.com | `#Connox` |
| etsy.com | `#Etsy` |
| folksy.com | `#Folksy` |
| goimagine.com | `#GoImagine` |
| mejuri.com | `#Mejuri` |
| missoma.com | `#Missoma` |
| monicavinader.com | `#MonicaVinader` |

---

## 27.2 源站点清单（38 个）

### 全球顶级买手店/设计师电商

| 站点 | URL | 类型 |
|------|-----|------|
| SSENSE | `https://www.ssense.com` | 加拿大先锋买手店（新锐设计师聚集） |
| LN-CC | `https://www.ln-cc.com` | 伦敦概念买手店（前卫/实验性设计） |
| Browns | `https://www.brownsfashion.com` | 伦敦老牌买手店（Farfetch 旗下） |
| Dover Street Market | `https://shop.doverstreetmarket.com` | 川久保玲概念店（全球顶级） |
| H.Lorenzo | `https://www.hlorenzo.com` | 洛杉矶前卫设计师买手店 |
| Machine-A | `https://www.machine-a.com` | 伦敦新锐设计师孵化/买手店 |

### 全球奢侈品/设计师多品牌平台

| 站点 | URL | 类型 |
|------|-----|------|
| Farfetch | `https://www.farfetch.com` | 全球最大设计师品牌聚合平台 |
| Mytheresa | `https://www.mytheresa.com` | 德国高端设计师品牌电商 |
| Moda Operandi | `https://www.modaoperandi.com` | 设计师 Trunk Show/预售平台 |
| Net-A-Porter | `https://www.net-a-porter.com` | 全球顶级女装设计师电商 |
| Matches Fashion | `https://www.matchesfashion.com` | 英国设计师品牌电商 |

### 独立设计师/小众品牌平台

| 站点 | URL | 类型 |
|------|-----|------|
| Garmentory | `https://www.garmentory.com` | 独立设计师/精品店聚合 |
| Wolf & Badger | `https://www.wolfandbadger.com` | 独立品牌发现平台 |
| Not Just A Label | `https://www.notjustalabel.com` | 全球最大新锐设计师平台 |
| APOC Store | `https://apoc-store.com` | 概念设计/先锋时装 |

### 日本

| 站点 | URL | 类型 |
|------|-----|------|
| ZOZOTOWN | `https://zozo.jp` | 日本最大时尚电商（含设计师品牌） |
| Houyhnhnm | `https://www.houyhnhnm.jp` | 日本时尚/设计/文化媒体 |
| Fashionsnap | `https://www.fashionsnap.com` | 日本时尚新闻/设计师报道 |
| GR8 | `https://gr8.jp` | 东京潮流买手店 |
| Coverchord | `https://coverchord.com` | 日本设计师/音乐/文化买手 |

### 韩国

| 站点 | URL | 类型 |
|------|-----|------|
| Musinsa | `https://www.musinsa.com` | 韩国最大时尚平台（含独立设计师） |
| W Concept | `https://us.wconcept.com` | 韩国设计师品牌集合平台 |
| 29CM | `https://www.29cm.co.kr` | 韩国策展型设计师电商 |
| EQL | `https://www.eqlstore.com` | 韩国限定/设计师联名平台 |

### 台湾

| 站点 | URL | 类型 |
|------|-----|------|
| Plain-me | `https://www.plain-me.com` | 台湾设计师/质感男装平台 |
| Marais | `https://www.marais.com.tw` | 台湾设计师选品/买手店 |
| Pinkoi | `https://www.pinkoi.com` | 亚洲最大设计师商品平台 |

### 新加坡/东南亚

| 站点 | URL | 类型 |
|------|-----|------|
| Design Orchard | `https://designorchard.sg` | 新加坡本土设计师孵化/零售 |
| Beyond The Vines | `https://www.beyondthevines.com` | 新加坡设计师品牌 |

### 北欧/欧洲设计

| 站点 | URL | 类型 |
|------|-----|------|
| Finnish Design Shop | `https://www.finnishdesignshop.com` | 北欧/芬兰设计精品 |
| Nordic Nest | `https://www.nordicnest.com` | 斯堪的纳维亚设计家居/生活 |
| Connox | `https://www.connox.com` | 德国设计家居/生活用品 |

### 手工/独立匠人平台

| 站点 | URL | 类型 |
|------|-----|------|
| Etsy | `https://www.etsy.com` | 全球最大手工/独立设计市集 |
| Folksy | `https://folksy.com` | 英国手工设计师市集 |
| GoImagine | `https://goimagine.com` | 美国独立手工匠人平台 |

### 设计师珠宝/配饰

| 站点 | URL | 类型 |
|------|-----|------|
| Mejuri | `https://mejuri.com` | 加拿大极简设计师珠宝 |
| Missoma | `https://www.missoma.com` | 英国设计师轻珠宝 |
| Monica Vinader | `https://www.monicavinader.com` | 英国设计师珠宝（可定制） |

---

## 27.3 采集脚本 `fetch_designer.py`

```powershell
py -3 scripts/fetch_designer.py `
    --target 30 `
    --output moments_designer.csv
```

- 从 38 个站点轮询采集设计师商品/内容图文
- 自动生成英文话题标签（含站点英文名）
- 图片质量管线：过滤广告图、水印图、小尺寸图（<400x300）
- 输出标准 moments CSV，可直接进入 `publish_from_tokens.py` 发布

---

## 27.4 图片处理机制

设计师标签的图片处理遵循仓库统一策略（`docs/23-image-policy.md`），并额外注意：

| 处理项 | 说明 |
|--------|------|
| 广告过滤 | URL 含 banner/ad/promo/popup/newsletter 的图片跳过 |
| 水印跳过 | `POST_WATERMARK_SKIP_HOSTS` 中的水印图库域名自动跳过 |
| 尺寸门槛 | 低于 400×300px 的缩略图/icon 过滤 |
| 宫格调整 | 多图时调整为 {1,2,4,6,9} 友好数 |
| 质量排序 | 最高分辨率图片排首位（封面位） |

---

## 27.5 端到端 runbook

```powershell
# 1. 采集设计师图文素材
py -3 scripts/fetch_designer.py --target 30 --output moments_designer.csv

# 2.（可选）文案差异化改写
py -3 scripts/caption_multilang.py `
    --input moments_designer.csv --output moments.csv `
    --langs en --content-aware

# 3. 发布（自动执行图片质量管线）
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_10.csv --csv moments_designer.csv `
    --concurrency 4 --tokens-out result/tokens.json
```

---

## 27.6 与其他标签的区别

| 标签 | 内容风格 | 站点定位 | 话题标签 |
|------|---------|---------|---------|
| `vintage_luxury`（中古轻奢） | 二手奢侈品/转售 | 二手交易平台 | `#站点名 + 随机2` |
| `designer`（设计师） | 新品/独立设计/前卫 | 买手店/设计师平台 | `#站点名 + 随机2` |
| `web3` | 资讯/评论 | Crypto/Tech 媒体 | `#web3 + 来源` |

---

## 27.7 安全

- 沿用 `docs/09-security.md`：不入库任何账号/密码/token。
- 38 个站点均为公开商品/内容页面，无需登录即可浏览。
