---
name: grill-web3-feature
description: "Web3 功能需求讨论技能。在实现新的新闻源或采集功能前，通过结构化提问明确需求，避免功能重复或方向偏差。"
---

# Web3 功能需求讨论

用于新 Web3 新闻源对接前的需求澄清。

## 讨论模板

每次添加新源前，回答以下问题：

### 1. 源信息

- **站点 URL**：`https://example.com`
- **内容类型**：RSS / API / HTML SSR / CSR（需要 JS 渲染）
- **访问门槛**：公开 / 需注册 / 需 IP 白名单
- **反爬措施**：Cloudflare / 阿里云 WAF / IP 限速 / Bot 检测

### 2. 数据格式

- **接口文档**：（如有）
- **实际响应样例**：保存一页 HTML 到 `debug_example.html`
- **关键字段**：标题、链接、发布时间、作者、摘要

### 3. 去重策略

- 该源是否已在 `FETCHERS` 中？
- 标题归一化逻辑是否需要调整？（当前 `_norm()` 去掉所有空白标点）
- 与其他源的重复率预估：高（>70%）/ 中（30-70%）/ 低（<30%）

### 4. 文案适配

- **目标语言**：zh_hant / en / ja / ms / mixed_en_ms
- **账号池**：哪个 accounts_*.csv？
- **发布场景**：纯文本帖 / 图文混合

### 5. 现有功能覆盖

检查 `scripts/fetch_web3.py:FETCHERS` 是否已包含：
- 同类站点（如已有 techflow，是否需要 techflow_cn？）
- 相同 RSS 源（可能域名不同但内容相同）

## 输出物

讨论完成后，在 `docs/24-web3-sources.md` 的 "B. 注册源站点" 部分添加条目，格式：

```markdown
| 站点 | URL | 类型 | 状态 | 备注 |
|------|-----|------|------|------|
| xxx | https://... | RSS/HTML/API | 待对接 | 需处理 Cloudflare |
```
