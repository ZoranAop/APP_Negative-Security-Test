# 13. 多语言主体视角文案

## 13.1 背景

早期 `post_moments.py` 只发中文文案，实战里我们把批次拆到 3 语言（英、繁中、日）
后发现社区互动更活跃。本文说明如何直接调用
`scripts/caption_multilang.py` 一次性把素材 CSV 的 `content` 列改写为
**多语言主体第一人称**分享文案，并将语言比例控制在你想要的分布。

## 13.2 支持的语言

| 代码       | 语言       |
| ---------- | ---------- |
| `en`       | English    |
| `zh`       | 简体中文   |
| `zh_hant`  | 繁体中文   |
| `ja`       | 日本語     |

## 13.3 输入 / 输出

输入：`opennana_fetch.py` / `fetch_openprompts.py` / `fetch_lovimg.py` /
`multi_source_fetch.py` 产出的任一 CSV（至少有 `content` 列）。

输出：同 schema，`content` 列被重写；额外附加两列：

| 列       | 含义                              |
| -------- | --------------------------------- |
| `_lang`  | 该行使用的语言代码                |
| `_scene` | 检测到的场景（portrait / ootd / …）|

`post_moments.py` / `publish_from_tokens.py` 会忽略未知列，直接读 `content`。

## 13.4 CLI

```powershell
# 均匀 3 语言（默认 en / zh_hant / ja 平均）
py -3 scripts/caption_multilang.py `
    --input moments.csv `
    --output moments_multilang.csv `
    --langs en,zh_hant,ja

# 只用简中
py -3 scripts/caption_multilang.py `
    --input moments.csv `
    --output moments_zh.csv `
    --langs zh

# 使用 LLM 生成而非模板（需要 LLM_TEXT_* 或 LLM_* 环境变量）
py -3 scripts/caption_multilang.py `
    --input moments.csv `
    --output moments_llm.csv `
    --langs en,zh_hant,ja `
    --use-llm
```

- `--langs`：语言集合，逗号分隔。会按行均匀轮询后打乱。
- `--use-llm`：如果配置了 `LLM_TEXT_API_BASE / LLM_TEXT_API_KEY / LLM_TEXT_MODEL`
  或通用的 `LLM_*`，会调用 OpenAI 兼容 `chat/completions` 接口生成文案；
  失败时自动回退到内置模板池。
- `--use-existing-lang`：沿用输入 CSV 里已有的 `_lang` 列（例如
  `scripts/plan_lang_ratio.py` 按精确配比生成的），不再用均匀分配覆盖。
  需要「英+日=80%、繁中=20%」这类**精确**比例时用它，见 docs/14 §14.5。
- `--seed`：随机种子（用来生成语言排布 & 模板抽签），复现用。

## 13.5 场景检测

从 CSV 原 `content`（通常是英文/中文 title + tags）用关键词表匹配：

```
kimono · hanfu · bride · beach · goldenhour · winter · rain ·
cafe · night · street · gym · running · swim · dance ·
selfie · ootd · bedroom · flower · travel · cinema · portrait
```

匹配不到时默认 `portrait`。

## 13.6 文案模板设计原则

参考 `docs/04-content-pipeline.md §4.2`：

1. **第一人称口吻**（"今日穿搭 / 出来看看世界 / 早晨的光刚好…"）。
2. **去 AI 标识**：绝不出现 `【AI 生图】`、`Prompt 思路` 之类。
3. **2-4 个话题标签** + **1-2 个 emoji**。
4. **规避露骨内容**：所有模板均是生活化 / 分享型语气。

每个 (scene, lang) 组合有 1-3 条候选，脚本会**均衡使用**——
使用次数最少的候选优先被抽中，保证同一批次不重复。

## 13.7 扩展文案库

`scripts/caption_multilang.py` 顶部有 `TEMPLATES` 字典：

```python
TEMPLATES = {
    "en": { "beach": [...], "portrait": [...], ... },
    "zh_hant": {...},
    "ja": {...},
}
```

添加语言只需追加新键；添加场景只需在 `SCENE_RULES` 表补关键词，
同时给三个语言各写 1-3 条模板即可。

## 13.8 三轮实战效果

| 批次    | 帖数 | 语言分布            | 成功率 |
| ------- | ---- | ------------------- | ------ |
| Batch 2 | 100  | EN 34 / 繁中 33 / 日 33 | 100%   |
| Batch 3 | 100  | EN 34 / 繁中 33 / 日 33 | 100%   |

抽样验证时后端存的 `content` 与本地生成完全一致，emoji / 特殊符号无破损。
