# 11. 广告 / 商业素材过滤

在实战中我们发现，直接从提示词图库拉素材，有相当比例的图是
**商品广告 / 品牌海报 / 应用界面 mockup**，直接发到广场会破坏"生活分享"的调性。

本文说明我们统一的过滤规则；三个采集脚本（`opennana_fetch.py`、
`fetch_openprompts.py`、`fetch_lovimg.py`）以及 `multi_source_fetch.py`
都能通过 `--exclude-ads` 触发同一套判定。

## 11.1 三层过滤

### 一、分类（`category`）级

open-prompts 直接给出分类字段。以下分类视为广告：

| 分类                | 含义                              |
| ------------------- | --------------------------------- |
| `productCommercial` | 产品广告                          |
| `commercial`        | 商业创意                          |
| `advertising`       | 广告设计                          |
| `product`           | 产品图 / mockup                   |
| `brand`             | 品牌视觉                          |

其他站没有 category，走下面两层。

### 二、标签（`tags`）级

标签名（小写去空格）命中以下集合即算广告 / 图形设计：

```
poster · typography · infographic · diagram ·
web design · app ui · social media post · product mockup
```

lovimg 没有 tag 数据，跳过此层。

### 三、关键词（title / description / prompt）级

以下英文/中文子串出现在标题 / 描述 / prompt 前 400 字节内即算广告：

```
 ad , ad., ad,, advertisement, advert , advertising,
commercial, sponsor, brand-, brand:, campaign,
promo, promotion, logo, packaging, billboard
```

## 11.2 效果（第 3 轮实战抽样）

open-prompts 1100 条候选：
- 落入 `productCommercial` 分类：18
- 命中 tag 集合：约 470 条（Poster / Typography / Infographic 等海报设计类占主体）
- 命中关键词但未被分类拦截：约 24 条

**合计判定为广告：512 / 1100 ≈ 46.5%**

剩下 588 条中通过 `--theme beauty` 二次筛选 → 388 条真美女题材。
最终 100 帖发布 100% 成功，肉眼抽检无广告页面。

## 11.3 CLI 用法

### 单源

```powershell
py -3 scripts/fetch_openprompts.py `
    --page 1 --pages 1 --limit 100 `
    --theme beauty `
    --exclude-ads `
    --dedupe-file result\used_slugs.json `
    --output moments_op.csv
```

### 多源统一入口

```powershell
py -3 scripts/multi_source_fetch.py `
    --sources opennana,openprompts,lovimg `
    --theme beauty `
    --exclude-ads `
    --limit 100 `
    --dedupe-file result\used_slugs.json `
    --output moments.csv
```

### 关闭过滤（不推荐）

`--include-ads` 会关闭过滤（`multi_source_fetch.py`）。
或不加 `--exclude-ads` 参数（其他脚本，默认关闭）。

## 11.4 扩展 / 自定义

各脚本的 `AD_TAGS_LOWER` / `AD_KEYWORDS` / `AD_CATEGORIES` 为模块级常量。
若发现某类未被过滤，可以：

1. 加入 tags 集合 / 关键词列表
2. 重新运行采集脚本

改动集中在 `scripts/opennana_fetch.py`、`scripts/fetch_openprompts.py`、
`scripts/fetch_lovimg.py` 顶部；`multi_source_fetch.py` 只做调度、
不重复维护规则表。

## 11.5 已知误伤

- 老式术语 `AD`（Anno Domini / Analog-to-Digital）会误伤，加了空格前后缀降低误报。
- `campaign` 会把 "editorial campaign" 类的时尚大片一并过滤掉——
  这类通常是模特写真，不是产品广告，属于**保守过滤**代价。
  如需保留，从 `AD_KEYWORDS` 里移除即可。
