---
name: diagnose-web3-fetcher
description: "针对 Web3 新闻采集脚本（fetch_*.py）的专用诊断 skill。当抓取失败、反爬拦截、数据质量差时使用。"
---

# Web3 Fetcher 诊断指南

针对 xxai-square-publisher 项目的新闻采集脚本调试。

## 典型问题模式

### 1. HTTP 403 / WAF 拦截

**症状**：请求返回 403、401，或 HTML 中包含 "access denied"、"cloudflare"、"challenge"

**排查步骤**：
```python
# 检查响应头
import requests
r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
print(r.status_code, r.headers.get("server"), r.headers.get("cf-ray"))
```

**解决方案**：
- Cloudflare：使用 `curl_cffi` 模拟 TLS 指纹（见 `docs/24-web3-sources.md`）
- 阿里云 WAF：参考 `fetch_web3.py:_wublock_solve()` 实现 cookie 求解
- 需要 JS challenge：切换 Playwright 渲染（见 `scripts/xhs_playwright.py`）

### 2. 数据为空或解析失败

**症状**：脚本输出 0 条记录，或 `re.findall()` 返回空列表

**排查步骤**：
```python
# 1. 保存原始 HTML
r = requests.get(url, headers=headers)
Path("debug_page.html").write_text(r.text, encoding="utf-8")

# 2. 检查关键选择器
import re
print(re.findall(r'<your-selector-here>', r.text))
```

**常见原因**：
- SSR 页面：HTML 中有数据，但 CSS/JS 动态加载的内容不在静态 HTML 中
- 分页：数据在第 2+ 页，需循环多页抓取
- 编码：`r.encoding` 不是 utf-8，检查 `r apparent_encoding`

### 3. 去重误杀

**症状**：`--dedupe-file` 导致正常新闻被跳过

**排查**：
```python
import json
from pathlib import Path
data = json.loads(Path("state/seen_web3.json").read_text())
# 检查归一化逻辑：_norm() 去掉所有空白和标点
for item in data[:5]:
    print(repr(item))
```

**解决**：调整 `_norm()` 或 `_toks()` 函数，放宽匹配阈值（当前 70%）

### 4. 文案质量差

**症状**：`web3_caption_by_role.py` 产出中英混杂或 AI 味过重

**排查**：
```powershell
# 查看中间产物
Get-Content web3_run/web3_raw_*.csv | Select-Object -First 3
Get-Content web3_run/moments_web3_*.csv | Select-Object -First 3
```

**解决**：
- 调整 `--tone` 参数（neutral/positive/trader/complain）
- 使用 Firecrawl Search 获取英文源 + `--lang en`
- 增加 `--min-len` 到 150 强制完整句子

## 快速诊断命令

```powershell
# 单点测试某个源
py -3 scripts/fetch_web3.py --sources wublock --per-site 3 --output debug_wublock.csv

# 测试 Firecrawl 兜底
py -3 scripts/run_web3_fc.py --use-firecrawl --search "bitcoin news" --skip-publish

# 查看最近失败日志
Get-ChildItem logs/ -Filter "*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 3
```

## 决策树

```
Fetcher 失败?
├── HTTP 错误 (4xx/5xx)
│   └── 检查 UA/Referer → 升级 curl_cffi → 考虑 Firecrawl
├── 解析为空
│   └── 检查 HTML 结构 → 调整正则 → 考虑 Playwright
├── 去重误杀
│   └── 检查 seen_*.json → 放宽阈值或重置
└── 文案质量差
    └── 检查 _brief 字段 → 调整 --tone/--lang
```
