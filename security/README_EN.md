# 反向安全测试机制设计说明

本目录为 **生产构建安全反向测试（Negative Security Test）+ CI 发布门禁（Release Gate）** 的完整脚本机制，基于前述的 9 条生产包安全加固要求构建。

## 设计哲学

| 维度 | 正向测试（传统 QA） | 反向安全测试（本机制） |
|------|-------------------|-------------------------|
| 目标 | “功能是否正常” | **“危险能力是否被彻底移除/隔离”** |
| 断言方式 | `assert result == expected` | **`assert forbidden NOT IN artifact`** / **`assert failure must occur`** |
| 失败处理 | 修复功能缺陷 | **阻断发布流水线（Gate Block）** |
| 证据要求 | 可选截图 | **强制产出 JUnit XML + SARIF + 原始证据（apk/ipa 解析输出、日志片段、抓包结果）** |

---

## 目录结构

```
security/
├── docs/
│   └── NEGATIVE_TEST_GUIDE.md          # 本文件
├── policies/                           # 策略即代码（Policy-as-Code）
│   ├── negative.rego                    # OPA（Open Policy Agent）规则
│   └── allowlist.yaml                   # 白名单（已审计通过的第三方字符串）
├── scripts/                             # 单项检查脚本（可单独调用，也可被 pytest 组合）
│   ├── check_binary_integrity.py
│   ├── check_debug_isolation.py
│   ├── check_domain_isolation.py
│   ├── check_deep_link_isolation.py
│   ├── check_log_isolation.py
│   ├── check_encryption_storage.py
│   ├── check_ios_file_sharing.py
│   ├── check_mock_data_removal.py
│   ├── check_dart_obfuscation.py
│   └── gate_decision.py
├── tests/                               # pytest 测试框架
│   ├── conftest.py                       # 共享 fixture（APK/IPA 路径、构建配置）
│   └── test_negative_security.py         # 9 条规则 → 自动化测试用例
├── ci-templates/                         # CI 流水线模板
│   ├── release-gate.yml                  # GitHub Actions 模板
│   └── .gitlab-ci.yml                    # GitLab CI 模板
└── run_all_negative_tests.sh             # 一键执行脚本
```

---

## 9 条反向测试规则映射

每条规则对应前文的 9 条生产包安全加固要求，并转化为 **可执行的反向断言**：

| 编号 | 安全目标 | 反向断言（必须为 FALSE 才算 PASS） | 检查脚本 | 测试类型 |
|---|----------|-----------------------------------|----------|----------|
| 1 | 调试面板/抓包隔离 | `debugPrint` / `kDebugMode` / `assert` 在 release 包中存在 → **FAIL** | `check_debug_isolation.py` | 静态分析 + 动态连接拒绝 |
| 2 | 接口/域名/Associated Domains 隔离 | `Info.plist` 含非生产域名 → **FAIL** | `check_domain_isolation.py` | 二进制解析 |
| 3 | Android 深链白名单 | `AndroidManifest.xml` 注册非生产 `host` → **FAIL** | `check_deep_link_isolation.py` | Manifest 解析 + `adb` 验证 |
| 4 | 日志脱敏/控制 | `logcat` 抓取到明文 `token` → **FAIL** | `check_log_isolation.py` | 动态日志扫描 |
| 5 | 登录态加密存储 | 旧文件/Hive 仍含明文 token → **FAIL** | `check_encryption_storage.py` | 文件解析 + 存储读取 |
| 6 | iOS Documents 共享关闭 | `UIFileSharingEnabled == YES` → **FAIL** | `check_ios_file_sharing.py` | Plist 解析 |
| 7 | Mock 数据移除 | APK/IPA 资源中含 `mock_` 前缀 → **FAIL** | `check_mock_data_removal.py` | 资源扫描 |
| 8 | Dart 混淆 + 符号文件 | 类名可读（未混淆）或映射文件缺失 → **FAIL** | `check_dart_obfuscation.py` | 反编译抽样 + 文件存在性 |
| 9 | 发布前自动校验 | 签名证书不匹配 → **FAIL** | `check_binary_integrity.py` | `apksigner` / `codesign` |

---

## 执行模式

### 模式 A：本地快速检查（开发阶段）
```bash
# 只检查静态规则（1,2,3,6,7,8,9），不需要真机/模拟器
python -m pytest security/tests/test_negative_security.py \
  -k "static" -v --junitxml=results/static.xml
```

### 模式 B：完整反向测试（CI 阶段，含动态测试 1,4,5）
```bash
# 完整执行，要求已构建 release APK/IPA，并有模拟器/emulator 可用
bash security/run_all_negative_tests.sh \
  --apk build/app/outputs/flutter-apk/app-release.apk \
  --ipa build/ios/ipa/*.ipa \
  --manifest build/app/intermediates/merged_manifests/release/AndroidManifest.xml \
  --output-dir results/ \
  --platform android,ios
```

### 模式 C：CI 门禁（Gate Only）
```bash
# 只做“通过/拒绝”判定，不运行测试（由前置步骤产出证据）
python security/scripts/gate_decision.py \
  --evidence-dir results/ \
  --policy-dir security/policies/ \
  --platform android,ios
```

---

## 证据与可追溯性

每次执行必须产出以下文件（用于审计与回溯）：

| 文件类型 | 路径示例 | 用途 |
|----------|----------|------|
| JUnit XML | `results/android.xml` / `results/ios.xml` | CI 解析 PASS/FAIL 数量 |
| SARIF | `results/android.sarif` | 安全扫描工具标准格式（可导入 GitHub Security / DefectDojo） |
| 证据原始文件 | `results/evidence/debug_symbols/`、`results/evidence/log_snippet/` | 人工复核原始数据 |
| 策略评估结果 | `results/policy_decision.json` | OPA 评估的机器可读结果 |
| 执行日志 | `results/run_YYYYMMDD_HHMMSS.log` | 完整脚本执行过程（含 `stdout`/`stderr`） |

---

## 依赖

| 依赖 | 版本要求 | 安装方式 |
|------|----------|----------|
| Python | >=3.10 | `python3` |
| pytest | >=7.0 | `pip install pytest` |
| apktool | >=2.9 | `brew install apktool` / `apt install apktool` |
| jadx | >=1.4 | `brew install jadx` |
| aapt2 | Android SDK Build Tools | 随 Android SDK 安装 |
| adb | 同上 | 同上 |
| xcrun / simctl | macOS Xcode CLI | macOS 系统自带 |

---

## 安全注意事项

1. 所有脚本在处理 APK/IPA 时只做 **只读分析**（`unzip -l`、`strings`、反编译抽样），不会修改原包。  
2. 测试用 `adb shell` / `xcrun simctl` 发起的深链、日志抓取操作，**不会发送真实用户数据**到外部，只读取本地构建包行为。  
3. 白名单文件 `security/policies/allowlist.yaml` 必须由安全负责人签字（Git 提交签名或审批记录）后才能修改，防止通过白名单绕过安全规则。  
