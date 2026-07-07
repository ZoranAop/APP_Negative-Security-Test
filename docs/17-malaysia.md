# 17. 马来西亚内容发布（Malaysia branch）

> 本文档随 `malaysia` 分支维护，汇总"马来西亚图文内容采集 → 马来语文案 →
> 底部水印裁切 → 广场发布"的完整调用方式，便于对应马来西亚内容的发布。

本分支在 `main` 基础上，新增/强化了三块能力：

1. **马来西亚图片采集源**（两个新脚本）
2. **马来语（Bahasa Melayu）主体视角文案**（`caption_multilang.py --langs ms`）
3. **底部水印整条裁切**：小红书 + backpackers 论坛（bbkz.net）统一处理

---

## 17.1 马来西亚采集源

| 脚本 | 站点 | 取图方式 | 产出 |
| ---- | ---- | -------- | ---- |
| `scripts/fetch_stock_my.py`      | Pexels / Pixabay        | Playwright 真实浏览器绕过 Cloudflare，取**原图直链**（无水印、无 API key） | 单图 moments 行 |
| `scripts/fetch_backpackers_my.py`| backpackers.com.tw f=111 | 解析论坛游记贴，取 `sa.bbkz.net` **附件原图**（去 `thumb=1`、剥离 `s=` 会话参数） | **多图** moments 行（每贴一个 thread） |

### A. Pexels + Pixabay（图库原图，需要 Playwright）

```powershell
# 依赖：pip install playwright ; python -m playwright install chromium
py -3 scripts/fetch_stock_my.py `
    --sources pexels,pixabay `
    --query malaysia `
    --per-source 30 `
    --output my_raw.csv
```

- 绕过 Cloudflare "Just a moment..." JS 挑战，抓 `images.pexels.com/photos/...`
  与 `cdn.pixabay.com/photo/...` 原图（Pixabay 自动升到 `_1280`）。
- 输出标准 moments CSV，`_source` = `pexels` / `pixabay`。

### B. backpackers.com.tw 论坛（多图游记，纯 HTTP）

```powershell
py -3 scripts/fetch_backpackers_my.py `
    --fid 111 `
    --posts 10 `
    --imgs-per-post 9 `
    --min-imgs 4 `
    --listing-pages 3 `
    --dedupe-file bp_used_threads.json `
    --output bp_raw.csv
```

- `--fid 111` = 论坛「馬來西亞」版；每个游记贴（≥`--min-imgs` 张图）聚合成**一条多图帖**。
- 自动跳过「包车 / 转让 / 代购 / 换汇 / 咨询」等广告贴（`AD_KEYWORDS`）。
- 附件图取全尺寸（去掉 `&thumb=1`），链接稳定（无需 Referer / 无 Cloudflare）。
- `--dedupe-file` 传入已用过的 thread id JSON，保证下次取到新贴。
- `_source` = `backpackers`。

---

## 17.2 马来语文案（Bahasa Melayu）

`caption_multilang.py` 已内建马来语（`ms`）模板池 + 场景识别（含马来西亚地名）：

```powershell
$env:DEFAULT_SCENE = "travel"   # 图库/游记多为风景，兜底场景设为 travel 更贴切
py -3 scripts/caption_multilang.py `
    --input bp_raw.csv `
    --output moments_bp.csv `
    --langs ms
```

- 支持语言：`en / zh / zh_hant / ja / ms`。本分支重点是 `ms`。
- 场景识别新增中英文马来西亚关键词：吉隆坡/KLCC/Petronas（night）、
  槟城/乔治市/壁画/马六甲（street）、沙巴神山/金马仑高原（winter）、
  白咖啡/美食/餐厅（cafe）、马来西亚/自由行/开斋节/黑风洞（travel）等。
- 文案为马来西亚本地口语，带 hashtag + emoji，如：
  `Menara berkembar bergemerlapan, malam KL memang ada auranya. ✨ #petronas #malamKL #malaysiaindah`
- 若配置了 `LLM_TEXT_*`，加 `--use-llm` 可用大模型生成马来语文案（已内置 `ms` 提示词）。

---

## 17.3 底部水印裁切（小红书 + backpackers 统一）

`publish_from_tokens.py` 在下载图片、上传 S3 之前，对**命中域名**的图片
**整体裁掉底部一条**去水印。默认命中：

```
POST_CROP_BOTTOM_HOSTS = xhscdn.com,xiaohongshu.com,bbkz.net   # 默认值
POST_CROP_BOTTOM_PCT   = 0.08                                   # 底部 8%
```

- **小红书**（`xhscdn.com`）与 **backpackers 论坛**（`sa.bbkz.net` / `sa1.bbkz.net`）
  开箱即用，无需额外配置。
- Pexels / Pixabay 原图无水印，**不在裁切列表**，原样上传。
- 水印偏大时把 `POST_CROP_BOTTOM_PCT` 调到 `0.10~0.12`；置空 `POST_CROP_BOTTOM_HOSTS=""` 可完全关闭。
- 依赖 Pillow；未安装则跳过裁切并告警。
- 实测：backpackers 图 h-ratio 0.920（裁掉底部 8%），35/35 全部命中；非命中域名不受影响。

---

## 17.4 端到端 runbook（马来西亚）

### 一键脚本（推荐）

`scripts/run_malaysia.py` 把「采集 → 马来语文案 → 底部水印裁切 → 发布」串成一条命令：

```powershell
# 默认：backpackers 论坛，5 账号 CSV，10 个多图帖，马来语，自动裁 bbkz 底部水印
py -3 scripts/run_malaysia.py --accounts-csv accounts_5.csv --posts 10

# 图库源（Pexels + Pixabay，需要 Playwright）
py -3 scripts/run_malaysia.py --source stock --accounts-csv accounts_10.csv --posts 50

# 只采集 + 文案、不发布（预演产素材）
py -3 scripts/run_malaysia.py --posts 5 --skip-publish

# 跳过发布前确认（无人值守）
py -3 scripts/run_malaysia.py --accounts-csv accounts_5.csv --posts 10 --yes
```

关键参数：

| 参数 | 说明 | 默认 |
| ---- | ---- | ---- |
| `--source` | `backpackers`（论坛多图） / `stock`（Pexels+Pixabay 图库） | `backpackers` |
| `--accounts-csv` | 账号 CSV（不入库） | `accounts_5.csv` |
| `--posts` | 发布帖子数（=采集条数） | `10` |
| `--langs` | 文案语言 | `ms`（马来语） |
| `--crop-pct` | 底部水印裁切比例（bbkz/小红书生效） | `0.08` |
| `--skip-publish` | 只产素材不发布 | 关 |
| `--yes` | 跳过发布前确认 | 关 |

中间产物落在 `--workdir`（默认 `my_run/`）：`<source>_raw_<ts>.csv` 与 `moments_<source>_<ts>.csv`。
发布报告见 `result/publish_*.csv`。

### 分步执行（等价手动流程）

```powershell
# 1. 采集（二选一或混用）
py -3 scripts/fetch_backpackers_my.py --fid 111 --posts 10 --imgs-per-post 9 `
    --min-imgs 4 --listing-pages 3 --output bp_raw.csv
# 或
py -3 scripts/fetch_stock_my.py --sources pexels,pixabay --query malaysia `
    --per-source 30 --output my_raw.csv

# 2. 马来语文案
$env:DEFAULT_SCENE = "travel"
py -3 scripts/caption_multilang.py --input bp_raw.csv --output moments_bp.csv --langs ms

# 3. 发布（bbkz 底部水印自动裁切；小红书图同款处理）
py -3 scripts/publish_from_tokens.py `
    --accounts-csv accounts_5.csv --csv moments_bp.csv `
    --concurrency 3 --tokens-out result/tokens.json
```

实测批次：
- backpackers：5 账号 × 2 帖 = 10/10 多图帖成功（82 图，均裁底 8%）；另 6/6 复验成功。
- Pexels+Pixabay：10 账号 × 5 帖 = 50/50 成功，马来语文案。

---

## 17.5 安全

- 沿用 `docs/09-security.md`：**不入库**任何账号 CSV / `.env` / token；本分支同样遵守。
- `.env.example` 已把 `bbkz.net` 写入 `POST_CROP_BOTTOM_HOSTS` 默认值与说明。
