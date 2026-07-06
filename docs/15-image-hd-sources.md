# 15. 高清图片源：yituyu / tuzi（含 Referer 反爬处理）

## 15.1 背景

`opennana / open-prompts / lovimg` 是提示词图库，图偏"AI 生图"。
有时需要**真人写真类高清大图**。本文接入两个公开图站：

| 源      | 站点                              | 高清图规律                                   |
| ------- | --------------------------------- | -------------------------------------------- |
| yituyu  | https://www.yituyu.com/gallery/   | `img.yituyu.com/pic/<gid>/NN_*.jpg`（如 3600×2400，~600KB） |
| tuzi    | http://tuziyouwang.com/meitui/    | `tuziyouwang.com/d/file/<date>/<hash>.jpg`（如 800×1200） |

> 两站均**公开、无需登录**。不要把任何账号密码写进仓库或 `.env`（见 docs/09-security.md）。

## 15.2 为什么强调"高清"

- **yituyu**：列表缩略图在 `img.yituyu.com/grapher/*.jpg`（小图）；
  真正的高清图在 gallery 详情页的 `pic/<gid>/NN_*.jpg`。脚本只取后者。
- **tuzi**：列表只有 `titlepic` 小缩略图；文章正文里的 `/d/file/*` 才是原图。
  脚本进详情页取 `/d/file/*`，并可用 `--min-side` 按 JPEG 头部校验分辨率。

## 15.3 采集脚本

### fetch_yituyu.py
```powershell
py -3 scripts/fetch_yituyu.py `
    --limit 60 --theme beauty --exclude-ads `
    --imgs-per-gallery 3 --min-side 1000 `
    --dedupe-file result/used_yituyu.json `
    --output yituyu.csv
```
- 从首页 / `/gallery/` / `/rank/` 收集 gallery id，逐个进详情页取 HD 图。
- `--min-side`：探测 JPEG 头部，要求 `min(宽,高) >= N`，强制只要高清（0=跳过）。

### fetch_tuzi.py
```powershell
py -3 scripts/fetch_tuzi.py `
    --column meitui --pages 6 --limit 60 --exclude-ads `
    --imgs-per-article 3 --min-side 700 `
    --dedupe-file result/used_tuzi.json `
    --output tuzi.csv
```
- `--column`：EmpireCMS 栏目 slug（`meitui` 美腿 / `gengduo` 更多 / …）。
- 列表分页为 `/<column>/index_N.html`；`--pages` 控制翻几页。

两者也接入多源统一入口：
```powershell
py -3 scripts/multi_source_fetch.py `
    --sources yituyu,tuzi --theme beauty --exclude-ads `
    --tuzi-column meitui --tuzi-pages 5 --hd-min-side 800 `
    --limit 100 --output moments_raw.csv --shuffle
```

## 15.4 广告过滤

沿用 docs/11 的思路：按标题关键词（广告/推广/优惠/微信/扫码/福利群/coupon/promo…）
丢弃疑似广告条目。`--exclude-ads` 开启。

## 15.5 ⚠️ Referer 反爬：发布前需预下载

`publish_from_tokens.py` 的 `upload_url_to_s3` 下载外链图片时用的是**固定的
opennana Referer**。yituyu / tuzi 的 CDN 对 Referer 敏感，直接下载会失败
（表现为 S3 上传阶段 `FileNotFoundError`）。

**处理方式**：发布前用**各站正确的 Referer** 把图片预下载到
`publish_from_tokens.py` 期望的本地缓存路径，函数便会复用本地文件、跳过失败下载：

```python
import hashlib, requests, pathlib
def local_name(u):
    h = hashlib.md5(u.encode()).hexdigest()[:12]
    ext = ".jpg"
    for e in (".png", ".webp", ".gif"):
        if e in u.lower(): ext = e; break
    return f"downloaded_{h}{ext}"

REFERER = {"yituyu": "https://www.yituyu.com/", "tuzi": "http://tuziyouwang.com/"}
imgs = pathlib.Path("images"); imgs.mkdir(exist_ok=True)
for url, source in url_source_pairs:
    p = imgs / local_name(url)
    if p.exists(): continue
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": REFERER[source]}, timeout=30)
    if r.status_code == 200 and len(r.content) > 1000:
        p.write_bytes(r.content)
```

预下载后照常跑：
```powershell
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts.csv --csv moments.csv `
    --concurrency 3 --tokens-out result/tokens.json
```

> 后续可给 `upload_url_to_s3` 增加按图片域名自动匹配 Referer 的逻辑，
> 从根本上省掉预下载这一步。

## 15.6 端到端 runbook（高清图 → 文案 → 发布）

```powershell
# 1. 采集高清图（两站混合，规避广告，强制 HD）
py -3 scripts/multi_source_fetch.py --sources yituyu,tuzi `
    --theme beauty --exclude-ads --tuzi-column meitui --tuzi-pages 6 `
    --hd-min-side 800 --limit 100 --output materials.csv --shuffle

# 2. 匹配文案（按图片场景生成主体视角文案，可多语言）
py -3 scripts/caption_multilang.py --input materials.csv --output moments.csv `
    --langs en,zh_hant,ja

# 3. 预下载图片（正确 Referer）到 images/ 缓存  ← 见 §15.5

# 4. 两阶段发布
py -3 scripts/publish_from_tokens.py --accounts-csv accounts.csv `
    --csv moments.csv --concurrency 3 --tokens-out result/tokens.json
```

## 15.7 环境变量（均可留默认）

| 变量                | 默认值                          |
| ------------------- | ------------------------------- |
| `YITUYU_BASE`       | `https://www.yituyu.com`        |
| `YITUYU_REFERER`    | `https://www.yituyu.com/`       |
| `YITUYU_USER_AGENT` | Chrome UA                       |
| `TUZI_BASE`         | `http://tuziyouwang.com`        |
| `TUZI_USER_AGENT`   | Chrome UA                       |

## 15.8 实战验证

- yituyu 详情页图实测 3600×2400、~600KB；tuzi/meitui 详情图 800×1200。
- 已用两站高清图完成小规模真实发布（5 用户 × 2 帖，10/10 成功；
  20 用户 × 2-3 帖，53/53 成功），均走"预下载 + 两阶段发布"。
