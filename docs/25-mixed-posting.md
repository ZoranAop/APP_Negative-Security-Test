# 25. 混合交错发帖（拟真 / 去规则化）

> 本文档描述「混合交错」发帖机制：让一批帖子看起来像真人发布，而非机器批量。
> 对应脚本：`scripts/assemble_mixed.py`（组装）、`scripts/run_mixed.py`（一键）、
> 以及 `scripts/publish_from_tokens.py` 的发布层优化。

---

## 25.1 设计目标

规避「整齐划一」的机器特征：

- **帖数随机**：每个用户的发帖数量由随机数决定（默认 3~7），不再固定每人 N 帖。
- **类型交错**：文本 / 图文 / 问题三类交错排列，且**不允许全同类**。
- **单语分配**：每个用户自己的所有帖用同一种语言（用户间覆盖多语）。
- **内容不重复**：素材全局唯一消费 + 两级去重档，历史发过的不重发。
- **发布拟真**：登录限流自适应、帖间随机延迟打散、失败自动重试。

## 25.2 帖类型（T / I / Q）

| 代号 | 类型 | 内容 | media_info |
| ---- | ---- | ---- | ---------- |
| `T` | 文本贴 | web3/科技真实资讯标题 + 第一人称点评 | `{"type":"text"}` |
| `I` | 图文贴 | 图库素材（真实图片 URL）+ 场景化配文 | `{"type":"image","images":[...]}` |
| `Q` | 问题贴 | 把资讯要点转成开放式提问（纯文本） | `{"type":"text"}` |

> **注意**：广场发帖 API 只支持 `text` / `image` / `video` 三种 `media_info.type`，
> **没有原生投票/问题贴类型**。因此 `Q`（问题贴）用「提问式纯文本」模拟，归为文本类。

## 25.3 编排规则（assemble_mixed.py）

1. **语言按用户轮流分配**：`--langs zh_hant,en,ja,ms` → 用户 0,4,8… = zh_hant，
   用户 1,5,9… = en，以此类推。每个用户单语。
2. **每人随机帖数**：`random.randint(--min-posts, --max-posts)`。
3. **交错序列 `build_pattern`**：
   - 骨架先放 1 个 `I` + 1 个 `T`（保证非全同类、至少 1 文本 + 1 图文）。
   - 其余帖按概率填充：问题贴 `Q` 低概率（~22%，且总量 ≤ ⌊n/3⌋），其余在 `I`/`T` 间分配。
   - 打散后**尽量避免相邻同类**。
4. **配文去重**：同一用户内图文配文不重复（每人独立的模板计数器）。
5. **素材唯一消费**：文本 / 图文素材各自 shuffle 后顺序取用，用一条丢一条，全局不重复。

输出 CSV 除标准列外，附带辅助列：`_ptype`（text/image/question）、`_lang`、`_site`、
`_dedupe_key`（形如 `web3:<归一化标题>` 或 `img:<slug或URL>`，供发布后回写去重档）。

## 25.4 发布层优化（publish_from_tokens.py）

| 优化 | 参数 | 说明 |
| ---- | ---- | ---- |
| 登录限流自适应 | `--adaptive-login` | 按账号数自动调 `login-spacing`：≤5 账号→1.0s，≤12→2.5s，更多→3.5s |
| 发布节奏打散 | `--post-delay-min` / `--post-delay-max` | 每帖发布前随机延迟（秒），避免瞬时集中 |
| 失败自动重试 | `--post-retries`（默认 3） | 单帖遇 429/5xx/网络错自动指数退避重试；业务失败(code≠0)与非 429 的 4xx 不重试 |
| 回写去重档 | `--record-dedupe` | 只把**发成功**的 `_dedupe_key` 写回 `--web3-dedupe-file` / `--img-dedupe-file` |

> 登录仍是顺序 + 429 退避（`sequential_login`），沿用批次 7-8 的经验（并发登录 20 账号会 12/20 触发 429）。

## 25.5 一键运行（run_mixed.py）

```powershell
# 默认：4 语言按用户分，每人随机 3~7 帖，全流程去重 + 发布层优化
py -3 scripts/run_mixed.py --accounts-csv accounts.csv --langs zh_hant,en,ja,ms --min-posts 3 --max-posts 7

# 只产素材、不发布（预演，强烈建议先跑一遍看 preview）
py -3 scripts/run_mixed.py --accounts-csv accounts.csv --skip-publish

# 无人值守
py -3 scripts/run_mixed.py --accounts-csv accounts.csv --yes
```

四步：`fetch_web3` → `multi_source_fetch` → `assemble_mixed` → `publish_from_tokens`。
中间产物落 `web3_run/`，报告落 `result/publish_*.csv`。

## 25.6 手动分步（等价）

```powershell
# 1) 采文本（带去重）
py -3 scripts/fetch_web3.py --per-site 12 --dedupe-file state/seen_web3.json --output web3_run/text_raw.csv
# 2) 采图文（带 slug 去重）
py -3 scripts/multi_source_fetch.py --theme beauty --exclude-ads --limit 80 --dedupe-file data/used_slugs.json --output web3_run/img_raw.csv --shuffle
# 3) 组装混合交错
py -3 scripts/assemble_mixed.py --accounts-csv accounts.csv --text-csv web3_run/text_raw.csv --image-csv web3_run/img_raw.csv --langs zh_hant,en,ja,ms --min-posts 3 --max-posts 7 --output web3_run/moments_mixed.csv
# 4) 发布（含全部优化 + 回写去重）
py -3 scripts/publish_from_tokens.py --accounts-csv accounts.csv --csv web3_run/moments_mixed.csv --adaptive-login --post-delay-min 0.3 --post-delay-max 1.5 --record-dedupe
```

## 25.7 安全

- 沿用 `docs/09-security.md`：账号 CSV、`.env`、`result/tokens*.json` **一律不入库**（`.gitignore` 已拦）。
- 采集源均为公开媒体 / 图库，无需登录，勿写入任何站点账号密码。
- web3 文本为真实、可验证资讯（非提示词）；图文为图库真实图片。

## 25.8 实战验证

- 20 用户 × 5 帖（固定）= 100/100 成功；四语各 25，文本 40 / 图文 40 / 问题 20；图片 64 张全部上传 S3。
- 随机帖数版（每人 3~7）经 `--skip-publish` 预演，帖数离散、类型交错、无全同类、素材不重复。
