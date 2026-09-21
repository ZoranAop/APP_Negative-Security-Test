# Manual Test Matrix — 动态/人工辅助验证项（Fail-Closed 补充）

> 目标：不让“人工”成为无约束自由发挥，而是标准化为可审计的 Evidence 链路。
> 原则：自动化发现 → 人工执行 → 证据留痕 → Gate 决策（PASS/FAIL/SKIPPED）。

## 状态图例

| 标记 | 含义 | Gate 行为 |
|---|---|---|
| 🟢 | 自动化基本可独立证明 | PASS → ALLOW |
| 🟡 | 自动化为主 + 人工辅助确认 | PASS 需人工签字 / REVIEW 需人工确认 |
| 🟠 | 自动化仅完成部分，动态/业务验证关键 | 自动化结果 + 人工观察 → 最终 PASS/FAIL |
| 🔴 | 当前脚本无法独立证明，必须人工/设备 | SKIPPED（无设备）→ BLOCK；完成后 → PASS/FAIL |

---

## NS-01 ~ NS-21 + SEC-012 自动化/人工分级

| 编号 | 测试项 | 自动化覆盖 | 必须人工/设备 | 测试步骤（标准化） | Evidence 要求 | 最终状态 |
|---|---|---|---|---|---|---|
| NS-01 | Debug/Oops 隔离 | 🟡 静态 + 动态框架 | ✅ 真机/模拟器触发面板 | 1. 安装构建包 2. 尝试触发 DevMenu/Oops 3. 记录是否出现 | 设备信息 / 触发方式 / 屏幕录制 / 结果 | PASS / FAIL / SKIPPED |
| NS-02 | 域名/API 隔离 | 🟢 静态解析完整 | ❌ 少量 Review | 自动解析 + allowlist 对比 | JSON 证据 + 白名单签字 | PASS / REVIEW |
| NS-03 | Deep Link 白名单 | 🟡 静态解析可做 | ✅ 设备深链触发 | 1. `adb shell am start -d ...` 2. 验证跳转目标 3. 尝试非生产 host | Manifest 解析 + 深链执行日志 + 截图 | PASS / FAIL / SKIPPED |
| NS-04 | 日志隔离 | 🟡 静态 + logcat 框架 | ✅ 运行 App 抓取 | 1. 执行业务流程 2. `adb logcat -v time` 3. 正则扫描分级 | log 文件 + 扫描报告 + 分级结果 | PASS / FAIL / SKIPPED |
| NS-05 | 加密存储 | 🟡 静态扫描 | ✅ 登录/退出/重启 | 1. 登录 2. 检查 Hive/SharedPreferences/Keychain 3. 退出 4. 重启 5. 再检查 | 存储快照 + 登录流程记录 + 退出后验证 | PASS / FAIL / SKIPPED |
| NS-06 | iOS 文件共享 | 🟢 完整 | ❌ 基本不需要 | 解析 `Info.plist` `UIFileSharingEnabled` | Info.plist 解析 JSON | PASS / FAIL |
| NS-07 | Mock 数据移除 | 🟢 自动化完整 | ⚠️ 命中后人工判断误报 | 扫描 `mock_`/`fixture_` 资源 + 代码引用 | 扫描报告 + 误报说明 | PASS / FAIL / REVIEW |
| NS-08 | Dart 混淆 | 🟡 脚本完整 | ⚠️ 构建产物/人工抽查 | 1. `jadx` 抽样 2. 检查映射文件 3. 验证混淆 | 反编译报告 + 映射文件存在性 | PASS / FAIL / REVIEW |
| NS-09 | 签名/完整性 | 🟡 脚本完整 | ⚠️ 构建环境辅助 | `apksigner verify` / `codesign -dv` | 签名验证报告 | PASS / FAIL / REVIEW |
| NS-10 | 第三方依赖 | 🟡 真实解析 | ⚠️ allowlist / 业务审计 | 解析 `pubspec.yaml`/`build.gradle` + 版本 + 来源 + 许可证 | 依赖清单 + 业务映射签字 | PASS / REVIEW / FAIL |
| NS-11 | Secret 泄漏 | 🟡 真实扫描 | ✅ 高风险命中必须人工确认 | 1. 扫描 APK/构建产物 2. 熵值/格式/上下文分类 3. `REAL_SECRET` → 直接 FAIL；`CONTEXT_NEEDED` → REVIEW | 证据 JSON + 人工确认记录 + 分类说明 | PASS / REVIEW / FAIL |
| NS-12 | 网络安全配置 | 🟠 基础解析 | ✅ 构建配置 + 动态网络验证 | 解析 `NetworkSecurityConfig`/`ATS` + MITM/证书验证 | 配置解析 + 网络测试报告 | PASS / FAIL / REVIEW / SKIPPED |
| NS-13 | 权限审计 | 🟠 基础解析 | ✅ 业务必要性人工确认 | 解析 manifest + 业务功能映射表 | 权限清单 + 业务映射签字 | PASS / REVIEW / FAIL |
| NS-14 | 组件暴露 | 🟠 解析完整 | ✅ 动态验证 `exported` 实际行为 | `aapt2` / `apktool` 解析 + 尝试启动导出组件 | Manifest 解析 + 动态触发报告 | PASS / FAIL / SKIPPED |
| NS-15 | Intent/Deep Link 注入 | 🟠 解析完整 | ✅ 动态 + 人工观察 | 1. 解析 `intent-filter` 2. 尝试恶意 URL/`javascript:`/`intent:` 注入 3. 观察跳转 | 深链测试报告 + 截图/录屏 + 结果 | PASS / FAIL / SKIPPED |
| NS-16 | WebView 安全 | 🟠 基础扫描 | ✅ 运行时验证 | 1. 代码/资源扫描 JS 接口 2. 运行时打开 WebView 3. 测试 `file://`/`javascript:`/混合内容 | 扫描 JSON + 运行时测试报告 | PASS / FAIL / REVIEW / SKIPPED |
| NS-17 | 本地数据残留 | 🟠 基础扫描 | ✅ 运行时验证（登录→退出→重启→再检查） | 扫描存储文件 + 运行时数据残留验证 | 存储快照 + 运行时验证记录 | PASS / REVIEW / SKIPPED |
| NS-18 | 屏幕隐私 | 🔴 当前基本框架 | ✅ 必须人工/设备验证 | 1. 打开敏感页面 2. 后台 / App Switcher 3. 截图/录屏 4. 确认是否泄露 Token/密码/私密内容 | 屏幕截图 + 设备信息 + 结果 | PASS / FAIL / SKIPPED |
| NS-19 | 产物一致性 | 🟡 真实实现 | ⚠️ 构建证据辅助 | SHA256 + 构建日志 + 版本/包名/签名对比 | SHA + 构建日志 + 一致性报告 | PASS / FAIL / REVIEW |
| NS-20 | 产物清单 | 🟡 真实扫描 | ⚠️ 人工判断特殊资源 | APK 清单 + 禁止路径检测 + 资源分类 | 清单 JSON + 误报说明 | PASS / FAIL / REVIEW |
| NS-21 | 禁止能力动态 | 🔴 有框架 | ✅ 必须真机/模拟器 | 1. 尝试触发 `Oops/DevMenu` 2. 访问 `dev` 深链 3. 连接 `Mock Server` 4. 执行 `debug` 4. 观察是否出现 | 触发记录 + 设备信息 + 屏幕录制 + 结果 | PASS / FAIL / SKIPPED |
| SEC-012 | 构建配置 | 🟡 真实脚本 | ⚠️ 构建日志/CI 辅助 | 解析 `build.log` / `pubspec.yaml` / `build.gradle` / `Info.plist` | 配置报告 + 构建参数验证 | PASS / FAIL / REVIEW |

---

## Evidence 格式（人工测试可复用）

每项人工/动态测试应生成与脚本一致的 JSON 证据：

```json
{
  "test_case": "NS-15",
  "test_name": "Intent Injection Security",
  "status": "PASS",
  "test_mode": "DYNAMIC + MANUAL",
  "device": {"type":"Android","os":"14","device_id":"emulator-5554"},
  "tester": "xxx",
  "test_steps": ["未登录状态打开深链","修改 redirect 参数","尝试访问敏感页面"],
  "evidence_file": "results/evidence/NS-15-dynamic.json",
  "findings": [{"id":"open_redirect","severity":"HIGH","result":"未复现","status":"PASS"}],
  "result_summary": "未出现绕过认证或开放重定向",
  "timestamp": "2026-09-01T12:00:00Z"
}
```

---

## Gate 决策规则（Fail-Closed，人工结果同样适用）

```text
PASS        → 允许（需同时满足自动化 + 人工确认的项）
FAIL        → 阻断（自动化或人工任一项发现违规）
REVIEW      → 阻断，直到人工签字确认为 PASS（或修复后重新测试）
SKIPPED     → 阻断（无设备/无构建/未执行 → 不得视为 PASS）
FRAMEWORK_READY → 阻断（框架未转化为真实检测）
UNKNOWN     → 阻断（无法确定结果）
```

---

## 重要修正说明

1. **NS-10 依赖审计**：已可真实解析 `pubspec.yaml`，但 `THIRDPARTY` 不直接等于 `PASS`，需结合 `allowlist.yaml` + 业务审计 → `REVIEW` → 人工确认 → `PASS`。
2. **NS-21 禁止能力**：无设备时 `SKIPPED`（已修正，不再误判 `PASS`）；有设备时需完整触发 + 观察 → `PASS/FAIL`。
3. **NS-18 屏幕隐私**：当前脚本为基础框架；完整验证必须进入敏感页面 → 后台 → App Switcher → 截图/录屏 → 人工确认 → `PASS/FAIL`。
4. **NS-11 Secret**：已实现熵值 + PEM + JWT + 上下文分类；`REAL_SECRET` → 直接 `FAIL`；`CONTEXT_NEEDED` → `REVIEW` → 人工确认。
5. **NS-15/NS-16/NS-17**：动态验证仍需设备/运行时；自动化完成基础解析，动态部分标记为 `SKIPPED`（无环境）或 `REVIEW`（有环境但需人工观察）。

---

## 使用说明

- 自动化脚本：运行 `bash security/run_all_negative_tests.sh --apk ...`
- 人工测试：参照本矩阵执行对应步骤，生成 `results/evidence/NS-XX-manual.json`
- Evidence 校验：`python security/scripts/validate_evidence_bundle.py --evidence-dir results/evidence`
- Gate 决策：`python security/scripts/gate_decision.py --evidence-dir results/`
- OPA 评估：`opa eval -d security/policies/negative.rego ...`
