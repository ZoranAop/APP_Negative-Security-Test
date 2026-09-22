# 反向安全测试流水线架构图

## 整体架构

```
                 git push
                    ↓
               Build Release
                    ↓
             Generate IPA/APK
                    ↓
        ┌─────────────────────────┐
        │ Production Security Gate│
        └────────────┬────────────┘
                     ↓
        ┌────────────────────────┐
        │ SEC-001 ~ SEC-012      │
        │                        │
        │  ├─ Domain (SEC-002/003)
        │  ├─ Deep Link (SEC-005)
        │  ├─ Oops/Debug (SEC-001)
        │  ├─ Debug/Logs (SEC-006)
        │  ├─ Token Storage (SEC-007)
        │  ├─ Mock Data (SEC-009)
        │  ├─ Obfuscation/Symbol (SEC-010/011)
        │  ├─ iOS Sharing (SEC-008)
        │  ├─ Associated Domains (SEC-004)
        │  └─ Release Config (SEC-012)
        └────────────┬───────────┘
                     ↓
               ┌─────┴─────┐
               ↓           ↓
             PASS          FAIL
               ↓           ↓
          Upload Store    Block
```

---

## 反向测试流程说明

| 阶段 | 说明 |
|---|---|
| 构建 | `flutter build` 生成 Release IPA/APK，启用 `--obfuscate --split-debug-info` |
| 扫描 | 9 个脚本并行/串行运行，每条都是反向断言：必须不存在违规项 |
| 证据 | 每条规则输出 JSON 证据到 `results/evidence/NS-XX.json` |
| 评估 | `gate_decision.py` 读取所有证据，应用 OPA `negative.rego` 策略 |
| 决策 | 只有全部 PASS 才 `ALLOW`，否则 `BLOCK` |
| 上架 | PASS → 上传 App Store / Play Store；FAIL → 阻断并通知 |

---

## 数据流

```
构建产物 (APK/IPA + mapping + Info.plist + Manifest)
         ↓
[静态扫描] ──► check_domain_isolation / check_deep_link_isolation
         ↓
[二进制扫描] ──► check_binary_integrity / check_dart_obfuscation
         ↓
[动态扫描] ──► check_log_isolation / check_debug_isolation (ADB)
         ↓
[存储扫描] ──► check_encryption_storage / check_ios_file_sharing
         ↓
[资源扫描] ──► check_mock_data_removal
         ↓
[构建检查] ──► check_release_config
         ↓
证据汇总 ──► results/evidence/ (JSON)
         ↓
策略评估 ──► OPA / gate_decision.py
         ↓
门禁决策 ──► ALLOW / BLOCK
