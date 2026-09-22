# xxai_app_negative-security-test

App 生产构建 **反向安全测试（Negative Security Test）+ CI 发布门禁（Release Gate）** 完整机制。

> 核心思想：把生产包安全要求转化为 **反向断言（必须为 FALSE 才算 PASS 的自动化测试）**，在 CI 流水线中做强制门禁——任意一条红线被触碰，构建直接阻断，不允许发布。

本仓库覆盖从 **原始 9 条生产安全红线**（NS-01~NS-09）到 **扩展 21 项完整能力框架**（NS-01~NS-21 + SEC-012）的反向测试体系，包含静态扫描、动态验证、构建检查、第三方依赖审计、权限审计、组件暴露检测、WebView 安全、本地数据残留、屏幕隐私、产物完整性、动态禁止能力测试等完整维度，并集成 OPA 策略即代码（Policy-as-Code）实现自动化门禁。

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
| **NS-10** | 第三方依赖 / SDK 安全 | Flutter Plugin、Native Library、SDK 扫描 + `SBOM` 对比 | ✅ 真实执行（`check_dependency_audit.py` 解析 `pubspec.yaml`/`build.gradle`，上下文分类已修正） |
| **NS-11** | Secret / 凭证泄漏上下文检测 | 提取 `token`、`password`、`secret_key`、`private_key`、`auth_credential`，根据上下文（第三方参考 / 真实凭证 / 需人工确认）分类判断 | ✅ 真实执行（`check_secret_context.py` 熵值/PEM/JWT/上下文分类，非 FRAMEWORK_READY） |
| **NS-14** | Android 组件暴露检查 | `exported` `Activity`、`Service`、`Receiver`、`Provider`、`DebugActivity`、`MockServer` 暴露检测 | ✅ 真实执行（`check_component_exposure.py` 真实解析 `exported` 组件，检测 `DebugActivity`/`MockServer`） |
| **NS-19** | 产物完整性 / SBOM 对比 | 构建清单与实际 APK 内容逐项比对，确保构建一致性 | ✅ 真实执行（`check_release_inventory.py` 构建清单 + 禁止路径检测，完整 SBOM 仍需构建环境） |
| **NS-20** | 发布产物清单 / 安全库存 | 自动列出 `dex`、`native .so`、`assets`、`flutter_assets`、`config`、`test/mock/debug resources` 等类型，生成安全库存报告 | ✅ 真实执行（`check_release_inventory.py` 清单 + 禁止路径检测，完整 SBOM 仍需构建环境） |
| **NS-21** | 禁止能力动态测试 | 实际尝试触发 `Oops/DevMenu`、访问 `dev` 深链、连接 `Mock Server`、执行 `debug` 操作、访问测试资源，验证生产包不具备不应有能力 | ⚠️ 依赖设备/模拟器（已修正无设备不误判 PASS；`check_forbidden_capability.py` 输出 SKIPPED → BLOCK） |
| **SEC-012** | Release 构建配置检查 | 构建参数 `--release`、`--obfuscate`、`--split-debug-info`、`minifyEnabled`、`proguardFiles` 验证 | ✅ 真实执行（`check_release_config.py` 构建参数验证，完整验证需构建日志） |

> 已移除的占位规则（`NS-12` 网络安全配置、`NS-13` 权限审计、`NS-15` Intent 注入、`NS-16` WebView、`NS-17` 本地数据残留、`NS-18` 屏幕隐私）原为 FRAMEWORK_READY 占位脚本，无实际检测逻辑，已从矩阵中清除。

---

## 完整执行流程

### 阶段 1：本地快速检查（开发阶段，无设备依赖）
覆盖静态规则（NS-01~NS-03、NS-06~NS-09、NS-10~NS-20 基础解析/清单/配置检查、NS-14 基础解析）：

```bash
bash run_all_negative_tests.sh \
  --apk build/app/outputs/flutter-apk/app-release.apk \
  --output-dir results/
```

输出：每条规则的 `results/evidence/NS-XX.json` 证据文件。

### 阶段 2：完整反向测试（CI 阶段，含动态验证）
在 `macos-latest`（构建 + iOS 测试）和 `ubuntu-latest`（Android 测试 + 门禁）环境执行完整流水线：

```bash
python -m pytest security/tests/test_negative_security.py -v \
  --junitxml=results/test.xml --sarif=results/test.sarif

# 动态触发验证（需模拟器/真机环境）
python security/tests/test_dynamic_debug_trigger.py --apk ... --device-id ...
```

### 阶段 3：发布门禁（Gate Only — 最终阻断决策）

```bash
python security/scripts/gate_decision.py \
  --evidence-dir results/ \
  --policy-dir security/policies/ \
  --platform android,ios
```

门禁决策逻辑：

```
所有平台证据收集
  ↓
每条规则状态评估（PASS / FAIL / REVIEW / THIRDPARTY / ALLOWLIST）
  ↓
OPA 评估（negative.rego）
  ↓
默认拒绝（default allow = false）
  ↓
只有全部 PASS 且无 CRITICAL/HIGH FAIL → ALLOW
任意一条 FAIL（Critical/High 级别违规）→ BLOCK
```

---

## 证据、可追溯性与审计要求

每次执行必须产出以下可审计文件：

| 文件类型 | 路径示例 | 用途 | 生成方式 |
|---|---|---|---|
| JUnit XML | `results/android.xml` / `results/ios.xml` | CI 解析 PASS/FAIL 数量 | `pytest --junitxml` |
| SARIF | `results/android.sarif` | 安全扫描标准格式（可导入 GitHub Security / DefectDojo） | 测试框架生成 |
| JSON 证据（每条规则） | `results/evidence/NS-01.json` ... `NS-21.json` | 机器可读的每条规则检测结果 | 每个 `check_*.py` 输出 |
| 策略评估结果 | `results/policy_decision.json` | OPA 评估 `data.release.allow` 结果 | `gate_decision.py` 生成 |
| 执行日志 | `results/run_YYYYMMDD_HHMMSS.log` | 完整脚本执行过程（stdout/stderr） | `run_all_negative_tests.sh` |
| 测试矩阵 | `security/test_matrix.md` | 21 项基线规则与状态映射 | 文档 |
| 流水线架构图 | `docs/pipeline_diagram.md` | CI 流程可视化 | 文档 |

---

## 完整目录结构（集成所有内容）

```
security/
├── README.md                       # 完整机制说明（本文件，含全部规则、执行模式、依赖、CI 模板）
├── README_EN.md                    # 英文精简技术手册（原 NEGATIVE_TEST_GUIDE.md）
├── run_all_negative_tests.sh       # 一键执行脚本（本地 / CI 统一入口）
├── test_matrix.md                  # 21 项安全基线矩阵（NS 编号）
├── docs/
│   ├── pipeline_diagram.md         # 流水线架构图
│   ├── MANUAL_TEST_MATRIX.md       # 人工验证矩阵
│   └── environment_limitations.md  # 环境限制说明
├── policies/
│   ├── negative.rego               # OPA 策略（Policy-as-Code，Fail-Closed 默认拒绝）
│   ├── allowlist.yaml              # 白名单（已审计第三方 SDK 字符串，严禁条目明确）
│   └── forbidden_domains.yaml      # 禁止域名列表
├── scripts/
│   ├── gate_decision.py            # 发布门禁决策脚本
│   ├── check_debug_isolation.py    # NS-01 Debug 隔离
│   ├── check_domain_isolation.py   # NS-02 域名隔离
│   ├── check_deep_link_isolation.py# NS-03 深链白名单
│   ├── check_log_isolation.py      # NS-04 日志隔离（含分级规则）
│   ├── check_encryption_storage.py # NS-05 加密存储
│   ├── check_ios_file_sharing.py   # NS-06 iOS 文件共享
│   ├── check_mock_data_removal.py  # NS-07 Mock 数据
│   ├── check_dart_obfuscation.py   # NS-08 混淆 + 符号
│   ├── check_binary_integrity.py   # NS-09 签名完整性
│   ├── check_dependency_audit.py   # NS-10 第三方依赖审计
│   ├── check_secret_context.py     # NS-11 Secret 上下文检测
│   ├── check_component_exposure.py # NS-14 Android 组件暴露
│   ├── check_release_config.py     # SEC-012 构建配置
│   ├── check_release_inventory.py  # NS-20 产物清单
│   ├── check_artifact_consistency.py # NS-19 构建产物一致性
│   └── check_forbidden_capability.py # NS-21 禁止能力动态测试
├── tests/
│   ├── conftest.py                 # pytest fixtures（构建产物、规则、断言工具）
│   ├── test_negative_security.py   # 主测试用例（静态 + 动态映射）
│   ├── test_dynamic_debug_trigger.py # NS-01 动态触发 + NS-21 禁止能力清单
│   └── test_self_gate_negative.py  # 门禁自测（验证 fail-closed 行为）
├── ci-templates/
│   └── gitlab-ci-negative-security.yml # GitLab CI 模板
└── artifacts/                      # 构建产物目录（APK/IPA/symbols，本地运行时生成）
```

---

## 完整规则分类体系（支持精细门禁）

基于实际构建样本验证结果，本机制引入分类评估而非简单的 PASS/FAIL：

| 分类标签 | 定义 | 门禁行为 | 示例 |
|---|---|---|---|
| `CRITICAL` | 直接违反生产安全红线，必须阻断 | 直接 `BLOCK` | NS-01 Debug 面板存在、NS-07 Mock 数据存在、NS-04 Token 泄露 |
| `HIGH` | 高风险违规，通常阻断（可人工确认例外） | 默认 `BLOCK` | NS-02 非生产域名、NS-05 明文 Token、NS-14 测试组件导出 |
| `MEDIUM` | 需要审查，默认不阻断但必须记录 | `REVIEW` → 人工确认后 `ALLOW` 或修复 | NS-14 组件暴露审计（已移除 NS-13 权限审计占位脚本） |
| `LOW` | 低风险配置问题，记录即可 | `ALLOW`（记录） | NS-18 屏幕隐私配置（已移除占位脚本）、NS-20 产物清单完整性 |
| `THIRDPARTY` | 第三方 SDK / 依赖 / 生态域名，不阻断但必须审计 | `ALLOW`（需白名单审计记录） | `plugins.flutter.dev`、`androidx.test`、`firebase` 相关域名 |
| `ALLOWLIST` | 已审计通过的第三方字符串，明确允许 | `ALLOW`（必须 `Signed-off-by` 审批） | 已审计 SDK 字符串（严禁条目除外：`token`、`password`、`secret_key`、`auth_credential`、`private_key`、`certificate_pinning_disabled`、`kTrustAllCertificates`） |

---

## 完整执行状态与阶段说明

### 当前仓库交付状态（已完成）

- ✅ **原始 9 条规则脚本**（`check_debug_isolation.py` ~ `check_binary_integrity.py`）
- ✅ **补充脚本**（`check_release_config.py`、`check_secret_context.py`、`check_component_exposure.py`、`check_release_inventory.py`、`check_dependency_audit.py`）
- ✅ **策略文件**（`negative.rego`、`allowlist.yaml`、`forbidden_domains.yaml` 含分类规则）
- ✅ **测试框架**（`conftest.py`、`test_negative_security.py`、`test_dynamic_debug_trigger.py` 增强 `FORBIDDEN_CAPABILITIES` 清单）
- ✅ **文档**（完整中文 `README.md`、`README_EN.md`、`test_matrix.md`、`pipeline_diagram.md`）
- ✅ **CI 模板**（`ci-templates/gitlab-ci-negative-security.yml` 真实文件）
- ✅ **APK 扫描报告示例**（`results/evidence/DESKTOP_APK_SCAN/APK_SCAN_REPORT.md`，含发现、结论、修复建议、规则映射）

### 阶段 1：本地框架执行（已就绪，无设备依赖）
可在任何开发环境执行静态检查、框架运行、文档生成：

```bash
bash run_all_negative_tests.sh \
  --apk build/app/outputs/flutter-apk/app-release.apk \
  --output-dir results/
python security/scripts/gate_decision.py --evidence-dir results/ --policy-dir security/policies/
```

### 阶段 2：完整 CI 流水线执行（需要构建环境 + 构建产物）
需要真实 `flutter build --release --obfuscate --split-debug-info=...` 产物，以及构建日志：

```bash
# 构建阶段
flutter build apk --release --obfuscate --split-debug-info=build/symbols/android
flutter build ios --release --obfuscate --split-debug-info=build/symbols/ios

# 测试阶段
python -m pytest security/tests/ --platform android,ios --artifact-dir artifacts/
```

### 阶段 3：完整验证与动态能力测试（需要构建环境 + 模拟器/真机 + 完整构建日志）
只有在真实构建环境、真实设备连接、完整构建日志可用时，才能完成以下完整验证：

- **NS-03**：`aapt2 dump xmltree` 完整解析 `AndroidManifest.xml`
- **NS-04**：真实设备运行 `adb logcat` 抓取业务流程日志，执行分级扫描（Critical/High/Medium）
- **NS-05**：执行真实登录流程，检查 `Hive` / `SharedPreferences` / `Keychain` 存储状态
- **NS-08 + NS-19**：执行 `jadx` 反编译抽样，验证混淆映射文件可还原崩溃堆栈，执行 `SBOM` 对比
- **NS-09**：执行 `apksigner verify --print-certs --verbose` 完整签名验证
- **NS-10**：解析真实 `pubspec.yaml` / `build.gradle`，生成 `SBOM`，与构建产物逐项比对
- **NS-11**：使用真实构建样本测试 `REAL_SECRET_CANDIDATE` / `THIRDPARTY_REF` / `CONTEXT_NEEDED` 分类规则，验证熵值/PEM/JWT 格式判断准确性
- **NS-12 / NS-13 / NS-15 / NS-16 / NS-17 / NS-18**：已移除（原为 FRAMEWORK_READY 占位脚本，无真实检测逻辑；已从矩阵清除）
- **NS-14**：解析完整 `manifest` 提取所有 `exported` 组件，检测 `DebugActivity` / `MockServer` / 测试组件
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
- ✅ **补充框架脚本（NS-10~NS-21 + SEC-012 增强）**：全部交付（`check_release_inventory.py`、`test_dynamic_debug_trigger.py` 增强）
- ✅ **策略与白名单**：`negative.rego`、`allowlist.yaml`、`forbidden_domains.yaml`（含分类规则）
- ✅ **文档与矩阵**：`README.md`（完整集成说明）、`README_EN.md`（英文精简版）、`test_matrix.md`（21 项基线）、`pipeline_diagram.md`
- ✅ **CI 流水线模板**：`ci-templates/gitlab-ci-negative-security.yml`（真实文件）
- ✅ **测试框架**：`tests/conftest.py`、`test_negative_security.py`、`run_all_negative_tests.sh`
- ✅ **APK 扫描报告示例**：完整报告格式已交付（可作为标准模板复用）
- ⚠️ **完整验证依赖外部环境**：构建产物（真实 APK/IPA）、构建日志（`build.log`）、`aapt2`、`jadx`、模拟器/真机、真实构建环境（用于完整 `SBOM`、熵值验证、动态能力测试）

---

## 使用说明

1. **快速检查**：直接执行 `bash run_all_negative_tests.sh --apk ... --output-dir results/`
2. **完整 CI 流水线**：参考 `ci-templates/gitlab-ci-negative-security.yml`，在 `macos-latest` 构建 + `ubuntu-latest` 测试环境执行
3. **门禁执行**：执行 `python security/scripts/gate_decision.py --evidence-dir results/ --policy-dir security/policies/`
4. **证据审计**：每条规则生成 `results/evidence/NS-XX.json`，策略决策生成 `results/policy_decision.json`
5. **缺口追踪**：查看 `test_matrix.md` 和 `docs/pipeline_diagram.md` 了解完整 21 项基线状态与流水线位置

如有疑问、需要新增规则、需要完整 `SBOM` 生成、需要动态能力完整验证环境支持，或需要针对特定业务（如 `ope.ai` 深链、`xxai_feature_square` 模块、`flutter_assets` 第三方依赖）的定制检测规则，请联系安全团队。参见完整测试与人工验证矩阵：security/docs/MANUAL_TEST_MATRIX.md

---

## 联系与维护

- **安全负责人**：审批白名单（`policies/allowlist.yaml`）、审查新规则、处理误报、确认 `REVIEW` 级别发现
- **开发团队**：修复 `FAIL` 测试项（如 `NS-07 Mock 数据`）、更新构建配置、清理构建产物中的测试/调试资源
- **CI 管理员**：维护流水线配置（`ci-templates/gitlab-ci-negative-security.yml`）、监控门禁状态、确保构建产物与构建日志完整可追溯
- **业务团队**：确认 `THIRDPARTY` 分类中的第三方 SDK 是否为业务必需、提供业务功能映射关系（支持完整 `manifest` 权限审计）
