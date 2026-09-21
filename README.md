# xxai_app_negative-security-test

App 生产构建 **反向安全测试（Negative Security Test）+ CI 发布门禁（Release Gate）** 完整机制。

> 核心思想：把生产包安全要求转化为 **反向断言（必须为 FALSE 才算 PASS）的自动化测试**，在 CI 流水线中做强制门禁——任意一条红线被触碰，构建直接阻断，不允许发布。

本仓库覆盖从 **原始 9 条生产安全红线**（NS-01~NS-09）到 **扩展 21 项完整能力框架**（NS-01~NS-21 + SEC-012）的反向测试体系，包含静态扫描、动态验证、构建检查、第三方依赖审计、网络安全配置、权限审计、组件暴露检测、WebView 安全、本地数据残留、屏幕隐私、产物完整性、动态禁止能力测试等完整维度，并集成 OPA 策略即代码（Policy-as-Code）实现自动化门禁。

---

## 完整能力框架（21 项安全基线）

本机制将安全控制分为四个层次：**静态检查层**（构建包内容扫描）、**动态验证层**（运行时行为验证）、**构建配置层**（构建参数与产物完整性）、**第三方与环境层**（依赖、网络、权限、组件暴露）。

### 原始 9 条生产红线（NS-01 ~ NS-09）

| 编号 | 安全目标 | 反向断言（FAIL 条件） | 检测手段 | 完整状态 |
|---|---|---|---|---|
| **NS-01** | 调试面板/抓包隔离 | `debugPrint` / `kDebugMode` / `DevMenu` 等存在 | 静态扫描 + 动态触发尝试 | ✅ 框架完整，动态需设备 |
| **NS-02** | 接口/域名/Associated Domains 隔离 | 非生产域名存在（含第三方 SDK 分类） | `Info.plist` / `forbidden_domains.yaml` 比对 | ✅ 增强（含 THIRDPARTY 分类） |
| **NS-03** | Android 深链白名单 | `AndroidManifest.xml` 注册非生产 `host` | `aapt2 dump xmltree` + 深度解析 | ✅ 框架完整，解析需构建环境 |
| **NS-04** | 日志输出隔离 | 日志含明文 `token` / `password` / 敏感信息 | 启动 App → `adb logcat` → 正则扫描（分级：Critical/High/Medium） | ⚠️ 静态完整，动态需设备 |
| **NS-05** | 登录态加密存储 | 旧版 `Hive` / `SharedPreferences` 含明文 token | 静态文件扫描 + 动态登录验证 | ✅ 基础完整，完整验证需运行 |
| **NS-06** | iOS Documents 文件共享关闭 | `UIFileSharingEnabled == YES` | 解析 `Info.plist` | ✅ 完整 |
| **NS-07** | Mock 数据移除 | 资源含 `mock_` 前缀或测试数据 | 解包 APK/IPA + 资源扫描 | ✅ 完整（已发现真实 FAIL 案例） |
| **NS-08** | Dart 混淆 + 符号文件 | 类名可读（未混淆）或映射文件缺失 | `jadx` 反编译抽样 + 映射文件存在性检查 | ⚠️ 需构建产物验证 |
| **NS-09** | 发布前校验 IPA/APK | 签名证书不匹配 | `apksigner verify` / `codesign -dv` | ⚠️ 需构建产物验证 |

### 扩展能力框架（NS-10 ~ NS-21 + SEC-012）

| 编号 | 安全目标 | 检测内容 | 完整状态 |
|---|---|---|---|
| **NS-10** | 第三方依赖 / SDK 安全 | Flutter Plugin、Native Library、SDK 扫描 + `SBOM` 对比 | 🆕 框架已建（`policies/forbidden_domains.yaml` 增加 `THIRDPARTY` 分类），完整验证需构建环境 |
| **NS-11** | Secret / 凭证泄漏上下文检测 | 提取 `token`、`password`、`secret_key`、`private_key`、`auth_credential`，根据上下文（第三方参考 / 真实凭证 / 需人工确认）分类判断 | 🆕 框架已建（`scripts/check_secret_context.py`），完整熵值/PEM/JWT 格式判断需真实样本 |
| **NS-12** | 网络安全配置 | `cleartextTraffic`、`trust-all CA`、`certificate pinning disabled`、`hostname verifier bypass`、`debug proxy` | 🆕 框架已建（`scripts/check_network_security.py`），完整解析需构建配置文件 |
| **NS-13** | 权限最小化审计 | `CAMERA`、`RECORD_AUDIO`、`LOCATION`、`REQUEST_INSTALL_PACKAGES`、`QUERY_ALL_PACKAGES` 等与业务映射检查 | 🆕 框架已建（`scripts/check_permission_audit.py`），完整业务映射需构建环境 |
| **NS-14** | Android 组件暴露检查 | `exported` `Activity`、`Service`、`Receiver`、`Provider`、`DebugActivity`、`MockServer` 暴露检测 | 🆕 框架已建（`scripts/check_component_exposure.py`），完整解析需 `aapt2` |
| **NS-15** | Deep Link / Intent 注入安全 | `open redirect`、`javascript:` 注入、`intent:` 注入、未登录访问敏感页面、参数绕过 | 🆕 框架已建（`scripts/check_intent_injection.py`），完整动态测试需设备 |
| **NS-16** | WebView 安全 | `JavaScript` 接口暴露、`file://` 访问、`debugging`、`mixed content`、`URL allowlist` | 🆕 框架已建（`scripts/check_webview_security.py`），完整运行时验证需设备 |
| **NS-17** | 本地敏感数据残留 | `SharedPreferences`、`Hive`、`SQLite`、`Cache`、`Clipboard`、`Crash dump` 中敏感内容残留检查 | 🆕 框架增强（`scripts/check_local_data_residue.py` 扩展 NS-05），完整验证需运行 |
| **NS-18** | 屏幕隐私 / 截图保护 | `FLAG_SECURE`、`App Switcher` 快照保护、截图保护配置记录 | 🆕 框架已建（`scripts/check_screen_privacy.py`），完整验证需构建/设备 |
| **NS-19** | 产物完整性 / SBOM 对比 | 构建清单与实际 APK 内容逐项比对，确保构建一致性 | 🆕 框架已建（`scripts/check_release_inventory.py`），完整 `SBOM` 生成需构建环境 |
| **NS-20** | 发布产物清单 / 安全库存 | 自动列出 `dex`、`native .so`、`assets`、`flutter_assets`、`config`、`test/mock/debug resources` 等类型，生成安全库存报告 | 🆕 框架已建（`scripts/check_release_inventory.py`） |
| **NS-21** | 禁止能力动态测试 | 实际尝试触发 `Oops/DevMenu`、访问 `dev` 深链、连接 `Mock Server`、执行 `debug` 操作、访问测试资源，验证生产包不具备不应有能力 | 🆕 增强（`tests/test_dynamic_debug_trigger.py` 增加 `FORBIDDEN_CAPABILITIES` 清单），完整执行需模拟器/真机 |
| **SEC-012** | Release 构建配置检查 | 构建参数 `--release`、`--obfuscate`、`--split-debug-info`、`minifyEnabled`、`proguardFiles` 验证 | ✅ 框架已建（`scripts/check_release_config.py`），完整验证需构建日志 |

---

## 完整执行流程

### Phase 1：本地快速检查（开发阶段，无需设备）
适用于开发阶段快速反馈，覆盖所有静态规则（NS-01~NS-03、NS-06~NS-09、NS-10~NS-20 框架检查、NS-14/NS-15 基础解析）：

```bash
bash security/run_all_negative_tests.sh \
  --apk build/app/outputs/flutter-apk/app-release.apk \
  --output-dir results/
```

输出：每条规则的 `results/evidence/NS-XX.json` 证据文件。

### Phase 2：完整反向测试（CI 阶段，含动态验证）
在 `macos-latest`（构建 + iOS 测试）和 `ubuntu-latest`（Android 测试 + 门禁）环境执行完整流水线：

```bash
python -m pytest security/tests/test_negative_security.py -v \
  --junitxml=results/test.xml --sarif=results/test.sarif
```

动态测试（需要模拟器/真机）：
```bash
# NS-01 动态触发验证
python security/tests/test_dynamic_debug_trigger.py --apk ... --device-id ...

# NS-04 日志隔离动态验证（执行业务流程后抓取 logcat）
python security/scripts/check_log_isolation.py --apk ... --log-dir logs/

# NS-05 登录态动态验证（执行登录后检查本地存储）
```

### Phase 3：CI 门禁（Gate Only — 最终阻断决策）

```bash
python security/scripts/gate_decision.py \
  --evidence-dir results/ \
  --policy-dir security/policies/ \
  --platform android,ios
```

门禁决策逻辑：

```
所有平台（android + ios）
  ↓
全部规则（NS-01~NS-21 + SEC-012）
  ↓
每条规则状态评估（PASS / FAIL / REVIEW / THIRDPARTY / ALLOWLIST）
  ↓
OPA 评估（negative.rego）
  ↓
默认拒绝（default allow = false）
  ↓
只有全部 PASS 且无 CRITICAL / HIGH FAIL → ALLOW
任意一条 FAIL（Critical/High 级别违规）→ BLOCK
```

---

## 证据、可追溯性与审计要求

每次执行必须产出以下可审计文件，用于安全团队复核、CI 门禁评估、外部审计追溯：

| 文件类型 | 路径示例 | 用途 | 生成方式 |
|---|---|---|---|
| JUnit XML | `results/android.xml` / `results/ios.xml` | CI 解析 PASS/FAIL 数量 | `pytest --junitxml` |
| SARIF | `results/android.sarif` | 安全扫描标准格式（可导入 GitHub Security / DefectDojo） | 测试框架生成 |
| JSON 证据（每条规则） | `results/evidence/NS-01.json` ... `NS-21.json` | 机器可读的每条规则检测结果 | 每个 `check_*.py` 输出 |
| 策略评估结果 | `results/policy_decision.json` | OPA 评估 `data.release.allow` 结果 | `gate_decision.py` 生成 |
| 执行日志 | `results/run_YYYYMMDD_HHMMSS.log` | 完整脚本执行过程（stdout/stderr） | `run_all_negative_tests.sh` |
| 安全测试矩阵 | `security/test_matrix.md` | 12 项基线规则与状态映射 | 文档 |
| 流水线架构图 | `docs/pipeline_diagram.md` | CI 流程可视化 | 文档 |
| 测试报告（APK 扫描示例） | `results/evidence/DESKTOP_APK_SCAN/APK_SCAN_REPORT.md` | 实际构建包反向检测完整报告（含发现、结论、修复建议） | 手动 + 脚本混合生成 |

---

## 完整目录结构（集成所有内容）

```
security/
├── README.md                    # 完整机制说明（本文件，含全部规则、执行模式、依赖、CI 模板、补充内容、阶段说明）
├── docs/
│   ├── NEGATIVE_TEST_GUIDE.md  # 英文技术设计文档
│   └── pipeline_diagram.md     # 流水线架构图
├── policies/
│   ├── negative.rego           # OPA 策略（Policy-as-Code，Fail-Closed 默认拒绝）
│   ├── allowlist.yaml          # 白名单（已审计第三方 SDK 字符串，严禁条目明确）
│   └── forbidden_domains.yaml  # 禁止域名列表（FAIL / THIRDPARTY / ALLOWLIST 分类）
├── scripts/
│   ├── gate_decision.py        # 发布门禁决策脚本（读取证据 → 评估策略 → 输出 ALLOW/BLOCK）
│   ├── check_binary_integrity.py    # NS-09 签名/完整性
│   ├── check_component_exposure.py  # NS-14 Android 组件暴露（新增）
│   ├── check_dart_obfuscation.py    # NS-08 混淆 + 符号
│   ├── check_debug_isolation.py     # NS-01 Debug 隔离
│   ├── check_deep_link_isolation.py # NS-03 深链白名单
│   ├── check_domain_isolation.py    # NS-02 域名隔离（增强）
│   ├── check_encryption_storage.py  # NS-05 加密存储
│   ├── check_intent_injection.py    # NS-15 Intent 注入（新增）
│   ├── check_ios_file_sharing.py    # NS-06 iOS 文件共享
│   ├── check_local_data_residue.py  # NS-17 本地数据残留（新增，扩展 NS-05）
│   ├── check_log_isolation.py       # NS-04 日志隔离（含分级规则）
│   ├── check_mock_data_removal.py   # NS-07 Mock 数据
│   ├── check_network_security.py    # NS-12 网络安全配置（新增）
│   ├── check_permission_audit.py    # NS-13 权限审计（新增）
│   ├── check_release_config.py      # SEC-012 构建配置
│   ├── check_release_inventory.py   # NS-20 产物清单（新增）
│   ├── check_screen_privacy.py      # NS-18 屏幕隐私（新增）
│   ├── check_secret_context.py      # NS-11 Secret 上下文检测（新增）
│   └── check_webview_security.py    # NS-16 WebView 安全（新增）
├── tests/
│   ├── conftest.py                 # pytest fixtures（构建产物、规则、断言工具）
│   ├── test_negative_security.py   # 主测试用例（静态 + 动态映射）
│   └── test_dynamic_debug_trigger.py # NS-01 动态触发 + NS-21 禁止能力清单
├── test_matrix.md                  # 21 项安全基线矩阵（SEC-001~SEC-021 + SEC-012）
├── docs/pipeline_diagram.md        # CI 流程可视化图
└── run_all_negative_tests.sh       # 一键执行脚本（本地 / CI 统一入口）
```

---

## 完整规则映射（从原始 9 条到 21 项扩展）

| 原始编号 | 扩展编号 | 完整名称 | 当前状态 | 完整验证依赖 |
|---|---|---|---|---|
| NS-01 | NS-01 | Debug 隔离（静态 + 动态触发） | ✅ 框架完整 | 设备/模拟器 |
| — | NS-10 | 第三方依赖/SDK 扫描 | 🆕 框架已建 | 构建环境（`pubspec.yaml`、`build.gradle`、`SBOM`） |
| NS-02 | NS-02 + NS-02A | 域名隔离 + 端点验证 + 第三方分类 | ✅ 增强（含 `THIRDPARTY` 分类） | 构建配置文件 |
| NS-03 | NS-03 | 深链白名单 | ✅ 框架完整 | `aapt2`（构建环境） |
| NS-04 | NS-04 | 日志隔离（含分级规则） | ⚠️ 静态完整，动态缺设备 | 设备运行 |
| NS-05 | NS-05 + NS-17 | 加密存储 + 本地数据残留 | ✅ 基础完整，增强已建 | 运行时验证 |
| NS-06 | NS-06 | iOS 文件共享 | ✅ 完整 | — |
| NS-07 | NS-07 | Mock 数据移除 | ✅ 完整（已发现真实 FAIL 案例） | — |
| NS-08 | NS-08 | Dart 混淆 + 符号文件 | ⚠️ 框架完整，验证需构建产物 | 构建环境 |
| NS-09 | NS-09 + NS-19/20 | 签名完整性 + 产物完整性/清单 | ⚠️ 基础完整，`SBOM` 缺构建环境 | 构建环境 |
| — | NS-11 | Secret 上下文检测（上下文 + 熵值 + 分类） | 🆕 框架已建（基础分类规则已定义） | 真实构建样本验证熵值/PEM/JWT |
| — | NS-12 | 网络安全配置（SSL/ATS/CA/Pinning） | 🆕 框架已建 | 构建配置文件解析 |
| — | NS-13 | 权限审计 | 🆕 框架已建 | `manifest` 深度解析 |
| — | NS-14 | Android 组件暴露（`exported` 检查） | 🆕 框架已建 | `aapt2` 解析 |
| — | NS-15 | Intent 注入安全 | 🆕 框架已建 | 动态触发验证 |
| — | NS-16 | WebView 安全 | 🆕 框架已建 | 运行时验证 |
| — | NS-18 | 屏幕隐私 | 🆕 框架已建 | 构建/设备配置检查 |
| — | NS-21 | 禁止能力动态测试（完整反向能力验证） | 🆕 增强（清单已定义） | 完整动态执行需设备 |
| — | SEC-012 | Release 构建配置检查（`--obfuscate`、`minifyEnabled`、参数验证） | ✅ 框架已建，验证缺构建日志 | 构建环境 |

---

## 执行模式（完整三阶段流程）

### 阶段 1：本地快速检查（开发阶段，无设备依赖）
适合开发阶段快速反馈，覆盖静态规则（所有 NS-01 静态、NS-02、NS-03 基础解析、NS-06、NS-07、NS-08 基础抽样、NS-09 基础签名、NS-10~NS-20 框架检查、NS-14 基础解析）：

```bash
bash security/run_all_negative_tests.sh \
  --apk build/app/outputs/flutter-apk/app-release.apk \
  --platform android \
  --output-dir results/
```

输出：每条规则的 JSON 证据（`results/evidence/NS-XX.json`）。

### 阶段 2：完整反向测试（CI 阶段，含动态验证 + 构建检查）
在 `macos-latest`（构建 + iOS 测试 + 符号文件验证）和 `ubuntu-latest`（Android 测试 + 门禁 + 动态测试 + `aapt2` 解析）环境执行：

```bash
# 完整流水线执行
python -m pytest security/tests/test_negative_security.py -v \
  --junitxml=results/test.xml --sarif=results/test.sarif

# 动态触发验证（需模拟器/真机环境）
python security/tests/test_dynamic_debug_trigger.py \
  --apk build/app/outputs/flutter-apk/app-release.apk \
  --device-id $DEVICE_ID \
  --output-json results/evidence/NS-01-dynamic.json

# 构建配置检查（需构建日志）
python security/scripts/check_release_config.py \
  --build-log build.log \
  --output-json results/evidence/SEC-012.json
```

### 阶段 3：发布门禁（Gate Only — 最终阻断决策）

```bash
python security/scripts/gate_decision.py \
  --evidence-dir results/ \
  --policy-dir security/policies/ \
  --platform android,ios
```

门禁评估逻辑（集成分类机制）：

```
所有平台证据收集
  ↓
每条规则状态分类（PASS / FAIL / REVIEW / THIRDPARTY / ALLOWLIST / CRITICAL / HIGH / MEDIUM / LOW）
  ↓
OPA 策略评估（negative.rego）
  ↓
默认拒绝（default allow = false）
  ↓
规则：无 CRITICAL / HIGH 级别 FAIL → ALLOW
      有任意 CRITICAL / HIGH 级别 FAIL → BLOCK
      REVIEW 项目需人工确认后才能 ALLOW
```

---

## 证据、可追溯性与审计体系

每次执行必须产出可审计文件，用于安全团队复核、外部审计、漏洞追溯、合规证明：

| 文件类型 | 路径示例 | 生成方式 | 用途 |
|---|---|---|---|
| JUnit XML | `results/android.xml` | `pytest --junitxml` | CI 解析 PASS/FAIL 数量 |
| SARIF | `results/android.sarif` | 测试框架生成 | 安全工具标准格式（GitHub Security / DefectDojo 导入） |
| 规则 JSON 证据 | `results/evidence/NS-01.json` ... `NS-21.json` | 每个 `check_*.py` 输出 | 机器可读每条规则检测结果 |
| 策略决策结果 | `results/policy_decision.json` | `gate_decision.py` 生成 | `ALLOW` / `BLOCK` 最终决策 |
| 执行日志 | `results/run_YYYYMMDD_HHMMSS.log` | `run_all_negative_tests.sh` 产生 | 完整执行过程（stdout/stderr） |
| 测试矩阵 | `security/test_matrix.md` | 静态文档 | 21 项基线规则状态映射 |
| 流水线图 | `docs/pipeline_diagram.md` | 静态文档 | CI 流程可视化 |
| 完整报告模板 | `results/evidence/DESKTOP_APK_SCAN/APK_SCAN_REPORT.md` | 扫描报告示例 | 实际构建包反向检测完整报告格式 |

---

## 完整执行依赖与环境要求

### 必需工具（本环境已确认可用或可安装）

| 工具 | 版本要求 | 安装方式 | 当前状态 | 完整验证所需 |
|---|---|---|---|---|
| Python | >=3.10 | `python3` / `python` | ✅ 可用（`python3` 可执行） | ✅ |
| pytest | >=7.0 | `pip install pytest` | ⚠️ 可安装 | ✅ |
| bash / git | 任意 | 系统自带 | ✅ 完整可用 | ✅ |

### 构建与测试环境依赖（完整验证必需）

| 工具 | 版本要求 | 当前状态 | 影响规则 | 完整验证要求 |
|---|---|---|---|---|
| `flutter` / `dart` | stable / latest | ⚠️ 未在本环境验证 | 所有构建检查 | 构建真实 APK/IPA |
| `apktool` | >=2.9 | ❌ 不可用（需安装） | NS-03、NS-14、NS-20 | 解析 `AndroidManifest.xml` |
| `jadx` | >=1.4 | ❌ 不可用 | NS-08、NS-10 | 反编译抽样检查混淆 |
| `aapt2` | Android SDK | ❌ 不可用 | NS-03、NS-13、NS-14、NS-20 | 解析压缩 manifest |
| `adb` | Android SDK | ❌ 不可用 | NS-01（动态）、NS-04（动态）、NS-21（动态） | 连接模拟器/真机执行动态触发 |
| `xcrun simctl` | macOS | ❌ 不可用（非 macOS） | NS-06（iOS 测试） | iOS 模拟器测试 |
| 构建产物（`build/` 目录） | 真实构建输出 | ❌ 无（仅有桌面 APK 测试文件） | NS-07、NS-08、NS-09、NS-10、NS-19、NS-20、SEC-012 | 真实构建包验证 |
| 构建日志（`build.log`） | 构建输出 | ❌ 无 | SEC-012 | 构建参数验证 |
| `opa`（OPA CLI） | >=0.50 | ⚠️ 可安装 | 门禁决策（所有规则） | 执行 `gate_decision.py` |

---

## 完整规则分类体系（支持精细门禁）

基于第二份 APK 扫描报告（发现 `assets/mock/` 数据、`dev.fluttercommunity.plus` 等第三方域名、`private_key` 字段）的实际验证结果，本机制引入分类评估而非简单的 PASS/FAIL：

| 分类标签 | 定义 | 门禁行为 | 示例 |
|---|---|---|---|
| `CRITICAL` | 直接违反生产安全红线，必须阻断 | 直接 `BLOCK` | NS-01 Debug 面板存在、NS-07 Mock 数据存在、NS-04 Token 泄露 |
| `HIGH` | 高风险违规，通常阻断（可人工确认例外） | 默认 `BLOCK` | NS-02 非生产域名、NS-05 明文 Token、NS-14 测试组件导出 |
| `MEDIUM` | 需要审查，默认不阻断但必须记录 | `REVIEW` → 人工确认后 `ALLOW` 或修复 | NS-13 权限过度、NS-16 WebView 配置、NS-17 本地残留 |
| `LOW` | 低风险配置问题，记录即可 | `ALLOW`（记录） | NS-18 屏幕隐私配置、NS-20 产物清单完整性 |
| `THIRDPARTY` | 第三方 SDK / 依赖 / 生态域名，不阻断但必须审计 | `ALLOW`（需白名单审计记录） | `plugins.flutter.dev`、`androidx.test`、`firebase` 相关域名 |
| `ALLOWLIST` | 已审计通过的第三方字符串，明确允许 | `ALLOW`（必须 `Signed-off-by` 审批） | 已审计 SDK 字符串（严禁条目除外：`token`、`password`、`secret_key`、`auth_credential`、`private_key`、`certificate_pinning_disabled`、`kTrustAllCertificates`） |

这确保第二份 APK 扫描报告中出现的 `private_key` 字段不会被简单误判为 `FAIL`（应进入 `CONTEXT_NEEDED` / `REVIEW`），而 `assets/mock/` 数据则正确识别为 `CRITICAL` / `HIGH` 并触发 `BLOCK`。

---

## 完整执行状态与阶段说明

### 当前仓库交付状态（已完成）

- ✅ **原始 9 条规则脚本**（`check_debug_isolation.py` ~ `check_binary_integrity.py`）
- ✅ **补充脚本**（`check_release_config.py`、`check_secret_context.py`、`check_component_exposure.py`、`check_network_security.py`、`check_permission_audit.py`、`check_intent_injection.py`、`check_webview_security.py`、`check_local_data_residue.py`、`check_screen_privacy.py`、`check_release_inventory.py`）
- ✅ **策略文件**（`negative.rego`、`allowlist.yaml`、`forbidden_domains.yaml` 含分类规则）
- ✅ **测试框架**（`conftest.py`、`test_negative_security.py`、`test_dynamic_debug_trigger.py` 增强 `FORBIDDEN_CAPABILITIES` 清单）
- ✅ **文档**（完整中文 `README.md`、`test_matrix.md`、`pipeline_diagram.md`、`NEGATIVE_TEST_GUIDE.md`）
- ✅ **CI 模板**（`.github/workflows/release-gate.yml` 真实文件）
- ✅ **APK 扫描报告示例**（`results/evidence/DESKTOP_APK_SCAN/APK_SCAN_REPORT.md`，含发现、结论、修复建议、规则映射）

### Phase 1：本地框架执行（已就绪，无设备依赖）
可在任何开发环境执行静态检查、框架运行、文档生成：

```bash
bash security/run_all_negative_tests.sh \
  --apk build/app/outputs/flutter-apk/app-release.apk \
  --output-dir results/
python security/scripts/gate_decision.py --evidence-dir results/ --policy-dir security/policies/
```

### Phase 2：完整 CI 流水线执行（需要构建环境 + 构建产物）
需要真实 `flutter build --release --obfuscate --split-debug-info=...` 产物，以及构建日志：

```bash
# 构建阶段
flutter build apk --release --obfuscate --split-debug-info=build/symbols/android
flutter build ios --release --obfuscate --split-debug-info=build/symbols/ios

# 测试阶段（ubuntu-latest / macos-latest）
python -m pytest security/tests/ --platform android,ios --artifact-dir artifacts/

# 门禁阶段
python security/scripts/gate_decision.py --evidence-dir results/
```

### Phase 3：完整验证与动态能力测试（需要构建环境 + 模拟器/真机 + 完整构建日志）
只有在真实构建环境、真实设备连接、完整构建日志可用时，才能完成以下完整验证：

- **NS-03**：`aapt2 dump xmltree` 完整解析 `AndroidManifest.xml`
- **NS-04**：真实设备运行 `adb logcat` 抓取业务流程日志，执行分级扫描（Critical/High/Medium）
- **NS-05 + NS-17**：执行真实登录流程，检查 `Hive` / `SharedPreferences` / `Keychain` 存储状态
- **NS-08 + NS-19**：执行 `jadx` 反编译抽样，验证混淆映射文件可还原崩溃堆栈，执行 `SBOM` 对比
- **NS-09**：执行 `apksigner verify --print-certs --verbose` 完整签名验证
- **NS-10**：解析真实 `pubspec.yaml` / `build.gradle`，生成 `SBOM`，与构建产物逐项比对
- **NS-11**：使用真实构建样本测试 `REAL_SECRET_CANDIDATE` / `THIRDPARTY_REF` / `CONTEXT_NEEDED` 分类规则，验证熵值/PEM/JWT 格式判断准确性
- **NS-12**：解析真实 `Info.plist` / `NetworkSecurityConfig`，验证 `cleartextTraffic`、`certificate_pinning_disabled` 配置状态
- **NS-13**：解析完整 `manifest` 深度权限列表，与业务功能映射表对比
- **NS-14**：解析完整 `manifest` 提取所有 `exported` 组件，检测 `DebugActivity` / `MockServer` / 测试组件
- **NS-15**：执行真实深链触发（`adb shell am start -W -d ...`），验证 `open redirect` / `intent` 注入 / 参数绕过
- **NS-16**：运行时验证 `WebView` 配置（`JavaScript` 接口、`file://` 访问、`debugging` 状态）
- **NS-21**：完整执行 `FORBIDDEN_CAPABILITIES` 清单（`Oops_DevMenu_Trigger`、`DeepLink_DevHost_Open`、`Mock_Server_Connection`、`Certificate_Pinning_Bypass` 等），验证生产包不具备不应有能力
- **SEC-012**：使用真实 `build.log` 验证构建参数完整性

---

## APK 扫描报告参考（实际构建包反向检测示例）

本仓库包含实际 APK 扫描报告示例（`results/evidence/DESKTOP_APK_SCAN/APK_SCAN_REPORT.md`），基于桌面 APK `b731070990d8b0db3eec4a401a1eb210.apk` 执行反向检测，报告包含：

- 基本信息（文件大小、构建时间、框架版本）
- 完整规则映射表（每条规则状态、检测手段、发现内容、结论、修复建议）
- 关键发现（`NS-07 FAIL`：`assets/mock/announcements_page1.json`、`announcements_page2.json`）
- 安全影响分析（`Critical` 级别违规：内部测试数据泄露到生产包）
- 修复建议（删除构建流程中的 `assets/mock/`、重新构建、执行完整流水线验证）
- 门禁结论（`FAIL — 阻断发布`，修复后通过完整 CI 流程验证 `ALLOW` 才可发布）

该报告格式可作为所有后续构建包反向检测的标准模板。

---

## 最终状态说明

- ✅ **原始 9 条规则脚本**：全部交付、可运行、可独立执行
- ✅ **补充框架脚本（NS-10~NS-21 + SEC-012 增强）**：全部交付（`check_network_security.py`、`check_secret_context.py`、`check_permission_audit.py`、`check_component_exposure.py`、`check_intent_injection.py`、`check_webview_security.py`、`check_local_data_residue.py`、`check_screen_privacy.py`、`check_release_inventory.py`、`test_dynamic_debug_trigger.py` 增强）
- ✅ **策略与白名单**：`negative.rego`、`allowlist.yaml`、`forbidden_domains.yaml`（含分类规则）
- ✅ **文档与矩阵**：`README.md`（完整集成说明）、`test_matrix.md`（21 项基线）、`pipeline_diagram.md`、`NEGATIVE_TEST_GUIDE.md`
- ✅ **CI 流水线模板**：`.github/workflows/release-gate.yml`（真实文件）
- ✅ **测试框架**：`tests/conftest.py`、`test_negative_security.py`、`run_all_negative_tests.sh`
- ✅ **APK 扫描报告示例**：完整报告格式已交付（可作为标准模板复用）
- ⚠️ **完整验证依赖外部环境**：构建产物（真实 APK/IPA）、构建日志（`build.log`）、`aapt2`、`jadx`、模拟器/真机、真实构建环境（用于完整 `SBOM`、熵值验证、动态能力测试）

---

## 使用说明

1. **快速检查**：直接执行 `bash security/run_all_negative_tests.sh --apk ... --output-dir results/`
2. **完整 CI 流水线**：参考 `.github/workflows/release-gate.yml`，在 `macos-latest` 构建 + `ubuntu-latest` 测试环境执行
3. **门禁执行**：执行 `python security/scripts/gate_decision.py --evidence-dir results/ --policy-dir security/policies/`
4. **证据审计**：每条规则生成 `results/evidence/NS-XX.json`，策略决策生成 `results/policy_decision.json`
5. **缺口追踪**：查看 `test_matrix.md` 和 `docs/pipeline_diagram.md` 了解完整 21 项基线状态与流水线位置

---

## 联系与维护

- **安全负责人**：审批白名单（`policies/allowlist.yaml`）、审查新规则、处理误报、确认 `REVIEW` 级别发现
- **开发团队**：修复 `FAIL` 测试项（如 `NS-07 Mock 数据`）、更新构建配置、清理构建产物中的测试/调试资源
- **CI 管理员**：维护流水线配置（`.github/workflows/release-gate.yml`）、监控门禁状态、确保构建产物与构建日志完整可追溯
- **业务团队**：确认 `THIRDPARTY` 分类中的第三方 SDK 是否为业务必需、提供业务功能与权限映射关系（支持 `NS-13` 完整审计）

如有疑问、需要新增规则、需要完整 `SBOM` 生成、需要动态能力完整验证环境支持，或需要针对特定业务（如 `ope.ai` 深链、`xxai_feature_square` 模块、`flutter_assets` 第三方依赖）的定制检测规则，请联系安全团队。