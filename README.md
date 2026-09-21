# xxai_app_negative-security-test

App 生产构建 **反向安全测试（Negative Security Test）+ CI 发布门禁（Release Gate）** 机制。

> 核心思路：把"生产包不得包含调试、测试、明文、mock、非生产域名、未混淆代码"这 9 条红线，转化为 **自动化的反向测试用例**，并在 **CI 发布流水线中做强制门禁**——任意一条红线被触碰，构建直接失败，绝不上架。

---

## 目录结构

```
security/
├── README.md                    # 本文件
├── docs/
│   └── NEGATIVE_TEST_GUIDE.md  # 机制设计说明（英文）
├── policies/
│   ├── negative.rego           # OPA 策略即代码（Policy-as-Code）
│   └── allowlist.yaml          # 白名单（已审计通过的第三方字符串）
├── scripts/
│   ├── gate_decision.py        # 发布门禁决策脚本
│   ├── check_binary_integrity.py    # NS-09 发布前校验 IPA/APK
│   ├── check_dart_obfuscation.py    # NS-08 Dart 混淆与符号文件检查
│   ├── check_debug_isolation.py     # NS-01 调试面板/抓包隔离
│   ├── check_deep_link_isolation.py # NS-03 Android 深链白名单
│   ├── check_domain_isolation.py    # NS-02 接口/域名/Associated Domains 隔离
│   ├── check_encryption_storage.py  # NS-05 登录态加密存储迁移
│   ├── check_ios_file_sharing.py    # NS-06 iOS Documents 文件共享关闭
│   ├── check_log_isolation.py       # NS-04 日志输出隔离
│   └── check_mock_data_removal.py   # NS-07 移除生产包 mock 数据
├── tests/
│   ├── conftest.py                 # pytest fixtures（构建产物/配置/断言工具）
│   └── test_negative_security.py   # pytest 测试用例（9 条规则 → 自动化测试）
└── run_all_negative_tests.sh       # 一键执行脚本（本地 / CI 入口）
```

---

## 9 条反向测试规则

| 编号 | 安全目标 | 反向断言（必须为 FALSE 才算 PASS） | 检测手段 |
|---|----------|---------------------------------------------|----------|
| **NS-01** | 调试面板/抓包隔离 | `debugPrint` / `kDebugMode` / `assert` 在 release 包中存在 → **FAIL** | `grep` 静态扫描 + 尝试连接 DevTools 端口 |
| **NS-02** | 接口/域名/Associated Domains 隔离 | `Info.plist` / `AssociatedDomains` 含非生产域名 → **FAIL** | 解析 plist + 域名白名单比对 |
| **NS-03** | Android 深链白名单 | `AndroidManifest.xml` 注册非生产 `host` → **FAIL** | `aapt2 dump xmltree` + 深度解析 |
| **NS-04** | 日志输出隔离 | `logcat` 抓取到明文 `token` / `password` → **FAIL** | 启动 App 执行登录 → 抓取 30s 日志 → 正则扫描 |
| **NS-05** | 登录态加密存储 | 旧版 Hive / HydratedBloc 文件仍含明文 token → **FAIL** | 解析 Hive 文件头 + 内容扫描 |
| **NS-06** | iOS Documents 文件共享关闭 | `UIFileSharingEnabled == YES` → **FAIL** | 解析 `Info.plist` |
| **NS-07** | Mock 数据移除 | APK/IPA 资源中含 `mock_` 前缀 → **FAIL** | 解包 APK/IPA + 资源扫描 |
| **NS-08** | Dart 混淆 + 符号文件 | 类名可读（未混淆）或映射文件缺失 → **FAIL** | `jadx` 反编译抽样 + 映射文件存在性检查 |
| **NS-09** | 发布前校验 IPA/APK | 签名证书不匹配 → **FAIL** | `apksigner verify` / `codesign -dv` |

---

## 执行模式

### 模式 A：本地快速检查（开发阶段）
```bash
# 只检查静态规则（1,2,3,6,7,8,9），不需要真机/模拟器
python -m pytest security/tests/test_negative_security.py -k "static" -v \
  --junitxml=results/static.xml
```

### 模式 B：完整反向测试（CI 阶段，含动态测试 1,4,5）
```bash
bash security/run_all_negative_tests.sh \
  --apk build/app/outputs/flutter-apk/app-release.apk \
  --ipa build/ios/ipa/*.ipa \
  --manifest build/app/intermediates/merged_manifests/release/AndroidManifest.xml \
  --output-dir results/ \
  --platform android,ios
```

### 模式 C：CI 门禁（Gate Only）
```bash
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
| 证据原始文件 | `results/evidence/debug_symbols/NS-01.txt` | 人工复核原始数据 |
| 策略评估结果 | `results/policy_decision.json` | OPA 评估的机器可读结果 |
| 执行日志 | `results/run_YYYYMMDD_HHMMSS.log` | 完整脚本执行过程 |

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

## 依赖安装（Python）

```bash
pip install pytest pyyaml
```

---

## OPA 策略说明

`policies/negative.rego` 定义了发布门禁策略：

- **默认拒绝（Fail-Closed）**：`default allow = false`
- **只有全部平台、全部规则全部通过时才允许发布**
- 策略与测试代码解耦，安全团队可独立维护规则

### 白名单配置

`policies/allowlist.yaml` 用于记录已审计通过的第三方字符串，避免误报：

- 必须由安全负责人在 Git 提交信息中签名（如 `Signed-off-by`）后生效
- 每季度审查一次，或在引入新第三方 SDK 时立即审查
- **严禁条目**：以下模式即使出现在白名单申请中也不被接受：
  - `token`、`password`、`secret_key`、`auth_credential`、`private_key`、`certificate_pinning_disabled`、`kTrustAllCertificates`

---

## CI 集成

### GitHub Actions 模板

```yaml
# .github/workflows/release-gate.yml
name: Release Security Gate

on:
  workflow_dispatch:
    inputs:
      version:
        required: true
      build_number:
        required: true

jobs:
  build-release:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Flutter (release)
        uses: subosito/flutter-action@v2
        with:
          channel: stable
      - name: Build Android Release (obfuscated)
        run: |
          flutter build apk --release \
            --obfuscate --split-debug-info=build/symbols/android
      - name: Build iOS Release (obfuscated)
        run: |
          flutter build ios --release \
            --obfuscate --split-debug-info=build/symbols/ios
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: release-artifacts
          path: |
            build/app/outputs/flutter-apk/app-release.apk
            build/ios/ipa/*.ipa
            build/symbols/**

  negative-tests:
    needs: build-release
    runs-on: ubuntu-latest
    strategy:
      matrix:
        platform: [android, ios]
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: release-artifacts
          path: artifacts
      - name: Install test deps
        run: |
          sudo apt-get update && sudo apt-get install -y \
            apktool jadx unzip python3-pip adb
          pip3 install mobsfscan pyyaml
      - name: Run Negative Test Suite
        id: negtest
        run: |
          python -m pytest security/tests/ \
            --platform ${{ matrix.platform }} \
            --artifact-dir artifacts \
            --junitxml=results/${{ matrix.platform }}.xml \
            --sarif=results/${{ matrix.platform }}.sarif
      - name: Upload test evidence
        uses: actions/upload-artifact@v4
        with:
          name: negative-test-${{ matrix.platform }}
          path: results/**

  gate:
    needs: negative-tests
    runs-on: ubuntu-latest
    if: always()
    steps:
      - name: Download all test results
        uses: actions/download-artifact@v4
        with:
          path: all-results
      - name: Evaluate Policy (OPA)
        id: policy
        run: |
          opa eval -i all-results -d policies/negative.rego \
            "data.release.allow" --format json > policy.json
          ALLOW=$(jq -r '.result[0].expressions[0].value' policy.json)
          echo "allow=$ALLOW" >> $GITHUB_OUTPUT
      - name: Block on FAIL
        if: steps.policy.outputs.allow != 'true'
        run: |
          echo "::error::Negative security tests FAILED – release blocked"
          exit 1
      - name: Publish to Store (only if PASS)
        if: steps.policy.outputs.allow == 'true'
        run: |
          ./scripts/upload_to_playstore.sh
          ./scripts/upload_to_appstore.sh
```

---

## Git 提交规范

- **安全规则修改**：必须由安全负责人 `Signed-off-by` 审批
- **白名单更新**：必须附带审批记录，说明理由和有效期
- **测试用例新增**：必须同时更新 `security_test_manifest` fixture

---

## 安全注意事项

1. 所有脚本在处理 APK/IPA 时只做 **只读分析**（`unzip -l`、`strings`、反编译抽样），不会修改原包。
2. 测试用 `adb shell` / `xcrun simctl` 发起的深链、日志抓取操作，**不会发送真实用户数据**到外部，只读取本地构建包行为。
3. 白名单文件 `policies/allowlist.yaml` 必须由安全负责人签字（Git 提交签名或审批记录）后才能修改，防止通过白名单绕过安全规则。
4. CI 流水线中的门禁步骤必须设置为 `required` check，否则会被绕过。

---

## 联系与维护

- **安全负责人**：负责审批白名单、审查新规则、处理误报
- **开发团队**：负责修复 FAIL 的测试项、更新构建配置
- **CI 管理员**：负责维护流水线配置、监控门禁状态

如有疑问或需要新增规则，请联系安全团队。

---

## 补充内容说明

### 1. 统一测试矩阵（SEC-001 ~ SEC-012）
详见 `security/test_matrix.md`，将原 9 条规则扩展为完整的 12 项安全基线，覆盖动态触发、日志分级、Release 配置验证。

### 2. 禁止域名列表（forbidden_domains.yaml）
`policies/forbidden_domains.yaml` 定义了生产包中绝对禁止出现的域名（`dev.*`、`test.*`、`staging.*`、`localhost`、`192.168.*` 等），`check_domain_isolation.py` 现在会同时比对该列表。

### 3. Release 配置检查（SEC-012）
新增 `scripts/check_release_config.py`，检查构建参数（`--release`、`--obfuscate`、`--split-debug-info`）以及 `build.gradle` `minifyEnabled` 配置。

### 4. 动态触发测试（SEC-001 动态层）
新增 `tests/test_dynamic_debug_trigger.py`，用于在模拟器/真机上尝试触发 Oops/Debug 面板，验证无法进入。

### 5. 日志分级（SEC-006）
`check_log_isolation.py` 现在支持分级扫描：Critical（Token/Secret）、High（UserId/Email）、Medium（Business params）。

### 6. 流水线架构图（docs/pipeline_diagram.md）
新增可视化流程说明：`Build → Security Gate → PASS/FAIL → Upload/Block`，并标出各 SEC 项在流水线中的位置。
