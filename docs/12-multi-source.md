# 12. 多源素材采集

单一站点素材反复使用会让不同批次的帖子看起来很像，
本文说明如何**混合三个素材站**做采集，并保证不重复。

## 12.1 支持的站点与接入方式

| 站点              | 入口                                                    | 接入方式                | 备注                                  |
| ----------------- | ------------------------------------------------------- | ----------------------- | ------------------------------------- |
| `opennana.com`    | `https://api.opennana.com/api/prompts`                  | REST JSON               | 支持 `model=ChatGPT / Nano banana pro`|
| `open-prompts.com`| `https://www.open-prompts.com/api/prompts?page=N`       | REST JSON（未官宣）     | 一页 1100 条；有 `category` / `tags`  |
| `lovimg.com`      | `https://lovimg.com/zh?category=people-characters`      | SSR HTML + `$R[..]` 反序列化 | 从 legacy/harvest_lovimg 移植 |

三个脚本一一对应：

- `scripts/opennana_fetch.py`
- `scripts/fetch_openprompts.py`
- `scripts/fetch_lovimg.py`

统一入口：`scripts/multi_source_fetch.py`。

## 12.2 CLI

```powershell
py -3 scripts/multi_source_fetch.py `
    --sources opennana,openprompts,lovimg `
    --theme beauty `
    --exclude-ads `
    --limit 100 `
    --source-weights "opennana=40,openprompts=40,lovimg=20" `
    --dedupe-file result\used_slugs.json `
    --output moments.csv `
    --shuffle
```

- `--sources`：逗号分隔的启用列表。默认 `opennana,openprompts,lovimg`。
- `--theme`：主体过滤：`beauty / portrait / sport / travel / food / all`。
- `--exclude-ads`：默认开启广告过滤（见 `docs/11-anti-ad-filtering.md`）。
- `--limit`：全部行数上限。
- `--source-weights`：可选，指定每源期望占比；总和不超过 `--limit`。
  留空则按源数量平均分配。
- `--dedupe-file`：JSON 文件，记录已用过的 `slug`；本次采集会读入 + 写回。
- `--shuffle`：混排最终 CSV，避免明显按源块聚集。

## 12.3 输出 CSV 增加了 `_source` 列

```csv
content,visibility,room_id,image_urls,location_name,location_address,location_lat,location_lon,_source
"Kimono weekend, tea in hand …",0,,https://…,,,,,openprompts
"面朝大海的一刻…",0,,https://…,,,,,lovimg
"周末拍到的日常光影…",0,,https://…,,,,,opennana
```

`post_moments.py` / `publish_from_tokens.py` 会忽略未知列，
但 `publish_from_tokens.py` 会把 `_source` / `_lang` / `_scene` 写进结果 CSV
作为分析用元数据。

## 12.4 去重策略

`--dedupe-file result/used_slugs.json` 会存已用过的 slug 集合：

```json
[
  "1791258384712-abc",
  "camera-evolution-poster-43fef448",
  "editorial-portrait-golden-hour"
]
```

- 采集时读入，用于**跳过**已见 slug。
- 新采集到的 slug 会合并写回，下次自动跳过。
- 每个采集脚本独立支持 `--dedupe-file`。
- 三个来源的 slug 命名空间不同，共存在同一个 JSON 无冲突。

## 12.5 每源建议参数（基于三轮实战）

| 源            | 每次可安全抓页       | 每页典型条数 | 备注                                           |
| ------------- | -------------------- | ------------ | ---------------------------------------------- |
| opennana      | 8-20 页              | 21           | `--shuffle-pages` 分散不同分类                 |
| openprompts   | 1-3 页               | 1100         | 一页数据量大，通常够用；分页超过 4 偶发 502    |
| lovimg        | 15-25 页（游标翻页） | ~10 每页有效 | 需要 `Referer: https://lovimg.com/zh`         |

## 12.6 与旧 `opennana_fetch.py` 的兼容

新 `opennana_fetch.py` 支持所有旧参数（`--media-type / --page / --pages / --limit / --output`），
新增可选参数不会破坏旧 runbook：

- `--model ChatGPT` – 只抓 ChatGPT 模型
- `--theme beauty` – 只抓美女题材
- `--exclude-ads` – 广告过滤
- `--dedupe-file` – 与其他脚本共享去重列表
- `--shuffle-pages` – 打乱分页顺序增加多样性
