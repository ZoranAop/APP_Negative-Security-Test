# 24. Content Isolation Policy (内容隔离策略)

> 本文档定义了特殊内容分支与主分支之间的**隔离规则**，
> 确保敏感/特殊类目内容不会意外混入常规发帖流程。

---

## 24.1 隔离分支清单

| 分支 | 标签 | 隔离级别 | 说明 |
|------|------|---------|------|
| `feature/customs-links` | 风俗习惯 | **严格隔离** | 仅在明确指定时使用，不与其他标签混合 |

---

## 24.2 `feature/customs-links` 隔离规则

### 默认行为

- **main 分支的所有发帖脚本默认不加载、不引用、不混合 `feature/customs-links` 分支的内容**
- `sources/categories.json`（main 分支）中**不包含**风俗习惯类目
- 常规标签发帖（美国生活/欧洲生活/日本生活/美女/科技等）**绝不**从该分支取图

### 触发条件

仅在以下**任一条件**满足时，才使用该分支的内容：

1. **明确指定仓库链接**：用户提供
   `http://100.64.0.45:8999/chenzhuo/xxai-square-publisher/-/tree/feature/customs-links`
2. **明确指定标签名**：用户说"风俗习惯"或"customs"
3. **明确指定数据文件**：引用 `sources/customs_images.json` 或 `sources/customs_links.json`

### 使用流程

```bash
# 1. 切换到该分支
git checkout feature/customs-links

# 2. 使用该分支专属脚本
py -3 scripts/fetch_customs_links.py ...
py -3 scripts/run_customs.py ...

# 3. 发帖时建议：仅发到房间（is_async=false），不同步广场
#    除非明确要求发到广场
```

### 禁止行为

- ❌ 不得将 `customs_images.json` 中的图片混入其他标签的 moments CSV
- ❌ 不得在 main 分支的 `categories.json` 中添加风俗习惯类目
- ❌ 常规批量发帖（run_singapore.py / run_vietnam.py 等）不得引用该分支数据
- ❌ 不得将该分支合并到 main

---

## 24.3 其他标签的安全保障

main 分支中的所有标签（美女/科技/科学/美国生活/欧洲生活/日本生活/台湾生活/
新加坡生活/越南生活/马来西亚生活）的数据源均定义在 main 分支的
`sources/categories.json` 中，与 `feature/customs-links` 完全独立。

采集脚本（`fetch_*.py`）只读取 main 分支中已注册的源站 URL，
不会跨分支访问其他数据文件。

---

## 24.4 审计

如需确认隔离状态：

```bash
# 确认 main 分支不含 customs 数据
git log main -- sources/customs_images.json
# 应返回空（无记录）

# 确认 categories.json 中无风俗习惯
grep "风俗" sources/categories.json
# 应返回空
```
