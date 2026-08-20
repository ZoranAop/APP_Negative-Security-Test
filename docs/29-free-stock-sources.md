# 29. 免费商用图库（5 源）

`pexels / pixabay / unsplash / kaboompics / gratisography` 五个免费股票图库，
均为**公开、无需登录、无 API key** 的图片源，图片无水印（区别于 Shutterstock /
iStock 带水印预览图）。统一由 `scripts/fetch_stock_my.py` 采集。

| source        | 站点                                    | 搜索链接                                        | 图片直链特征                                        | 抓取方式     |
| ------------- | --------------------------------------- | ----------------------------------------------- | --------------------------------------------------- | ------------ |
| `pexels`      | https://www.pexels.com/                 | `https://www.pexels.com/search/<q>/`            | `images.pexels.com/photos/<id>/...`                 | Playwright（Cloudflare） |
| `pixabay`     | https://pixabay.com/                    | `https://pixabay.com/photos/search/<q>/`        | `cdn.pixabay.com/photo/....jpg`（自动升级 _640→_1280） | Playwright（Cloudflare） |
| `unsplash`    | https://unsplash.com/                   | `https://unsplash.com/s/photos/<q>`             | `images.unsplash.com/photo-...`（`?fm=jpg&q=80&w=1440`） | Playwright |
| `kaboompics`  | https://kaboompics.com/                 | `https://kaboompics.com/gallery?search=<q>`     | `kaboompics.com/cache_1/<…>/<hash>.jpeg/.png`       | Playwright（Cloudflare） |
| `gratisography` | https://gratisography.com/            | `https://gratisography.com/?s=<q>`              | `gratisography.com/wp-content/uploads/…/*.jpg`（800x525 缩略尺寸） | 普通 HTTP（WordPress SSR） |

> 五个网站均**公开无需登录**，切勿在仓库或 `.env` 写入任何站点账号密码。

## 29.1 采集

```powershell
# 单源 / 多源
py -3 scripts/fetch_stock_my.py `
    --sources pexels,pixabay,unsplash,kaboompics,gratisography `
    --query "city" --per-source 10 `
    --dedupe-file state/seen_stock.json `
    --output moments_raw.csv

# 中国大陆境外图片（新加坡）
py -3 scripts/fetch_stock_my.py `
    --sources pexels --query singapore --per-source 6 `
    --locale en-US --dedupe-file state/seen_sg.json --output sg.csv
```

- `--sources`：逗号分隔，缺省 `pexels,pixabay`，可用五个任一组合。
- `--query`：搜索关键词（中文自动 URL 编码）。
- `--per-source`：每源取图数。
- `--dedupe-file`：图片 URL 去重账本（跨批次不重复发图）。
- `--locale`：浏览器语言（影响 alt 文案语言）。

## 29.2 去重与质量

- 图片以 **CDN 直链 URL 去重**（`--dedupe-file`），发布后非零回写，跨批次不重复。
- 发布阶段走 `publish_from_tokens.py` 的 7 步质量门槛（尺寸≥400×300、
  宽高比一致、宫格数调整等），不达标自动降级纯文本。

## 29.3 说明

- **kaboompics** 首页/gallery 需多滚几屏（懒加载），脚本已内置 9s 等待 + 多轮滚动。
- **gratisography** 为 WordPress SSR，直接抓取无需浏览器；图片使用 `-800x525` 缩略尺寸
  （约 800px 宽、几十 KB），原图无后缀版本可达数 MB，默认不使用（过重）。
- 图片均为免费商用授权，发布时按需配多语言口吻文案（见 docs/13 、run_*.py）。