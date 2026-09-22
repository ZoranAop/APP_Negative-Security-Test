# NS-22 / NS-23 / NS-24 / NS-28 / NS-29 统一测试标准说明

## 一、统一流程（适用于全部 NS-22~NS-29）

```
测试准备
  ↓
提取测试对象（IPA / Info.plist / 业务环境 / 角色定义）
  ↓
基础静态检查（解析 Entitlements / AASA / URL Schemes / ATS / 角色矩阵）
  ↓
专项规则检查（三方对照 / JSON 解析 / 业务用途表 / 角色-资源矩阵）
  ↓
必要时动态验证（codesign / curl AASA / OAuth 回调 / MITM / 业务动态越权）
  ↓
收集证据（summary.json + evidence.json + report.md + raw/）
  ↓
规则化判定（4 状态严格区分：PASS / FAIL / REVIEW / SKIP）
  ↓
人工 REVIEW（业务动效验证 / 三方对照确认 / 过度授权判断）
  ↓
PASS / FAIL / REVIEW / SKIP
  ↓
生成 JSON + Markdown 报告（results/NS-XX/ 下四文件）
```

## 二、四状态严格定义（与现有 Gate 决策一致）

| 状态 | 含义 | 触发条件示例 |
|---|---|---|
| **PASS** | 已完成规定测试，证据满足安全要求 | 完整执行动态测试，有完整证据，且无问题 |
| **FAIL** | 已确认存在问题 | 发现越权、过度授权、AASA 过宽匹配、ATS 允许任意加载 |
| **REVIEW** | 测试没有足够证据完成最终判断 | 工具缺失（codesign/curl）、无真实设备/业务环境、仅完成静态框架需人工补测 |
| **SKIP** | 当前产品不适用 | 测试项与产品功能无关（如无群功能时群管理测试） |

> **特别重要**：工具执行失败 ≠ 安全 FAIL。\n> 例如 `codesign` 不存在 → `REVIEW` + `reason=tool_unavailable`。\n> 例如 `curl` 不可用 → `REVIEW` + `reason=tool_unavailable`。\n> 绝对不能把环境缺失直接降级为 `FAIL`。

## 三、结果目录标准（每项 NS-XX 都必须产生）

```
results/NS-22/
  summary.json      # 标准化结果（id / status / checks / reason / timestamp / raw_files / notes）
  evidence.json     # 完整证据包（evidence_summary / findings / manual_review_required / recommendation）
  report.md         # 人工 REVIEW 记录 + 判定依据 + 测试步骤说明
  raw/              # 原始解析文件（embedded.mobileprovision / Info.plist / AASA JSON / codesign 输出 / 测试计划）
```

## 四、各专项关键规则（与用户提方案一致）

- **NS-22 Entitlements**：三方对照（Profile vs codesign vs Info.plist）；过度授权检查（App Groups / Keychain / Associated Domains / iCloud）；工具缺失 → REVIEW。
- **NS-23 AASA**：必须解析 JSON（不只 HTTP 200）；校验 `appID`（TeamID.BundleID）；路径检查（`*` / `/*` 过宽）；正向/反向动态测试计划记录。
- **NS-24 OAuth / Custom URL**：Scheme 用途表（不能只看到 Scheme 就判 FAIL）；动态回调测试计划（正常/篡改 state/重复/过期/错误 redirect_uri）；Scheme 劫持验证条件（仅在证明敏感认证结果可被劫持且无保护时才判 FAIL）。
- **NS-28 ATS / TLS**：ATS 配置检查（`NSAllowsArbitraryLoads` 直接 FAIL）；真实 TLS 测试计划；**无 Certificate Pinning ≠ FAIL**，真正测试是是否错误信任不受信任证书。
- **NS-29 Auth / AuthZ**：从“Authentication Test”改为**“Authentication & Authorization Negative Test”**；角色矩阵 + 资源矩阵；动态业务越权测试计划；无真实环境 → REVIEW（不得直接 PASS）。

## 五、执行脚本

已更新 `run_all_negative_tests.sh`，新增：
- `check_ns22_entitlements.py`
- `check_ns23_aasa.py`
- `check_ns24_custom_url.py`
- `check_ns28_ats_tls.py`
- `check_ns29_authz_negative.py`

运行方式：
```bash
bash run_all_negative_tests.sh --ipa artifacts/XXAI.ipa --info-plist artifacts/Info.plist --output-dir results --platform android,ios
```

各脚本独立运行也支持：
```bash
python scripts/check_ns22_entitlements.py --ipa artifacts/XXAI.ipa --output-dir results/NS-22
```
