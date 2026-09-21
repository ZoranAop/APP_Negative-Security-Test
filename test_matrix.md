# 反向安全测试矩阵（Security Test Matrix）

完整覆盖 12 项生产包安全基线，形成可持续执行的安全测试矩阵。

| ID | 测试项 | 类型 | 失败级别 | 对应脚本 | 说明 |
|---|---|---|---|---|---|
| SEC-001 | Oops / Debug 入口检查 | 静态 + 动态 | Critical | `check_debug_isolation.py` | 静态扫 debug 符号 + 动态尝试触发面板 |
| SEC-002 | 非生产 API 检查 | 静态 | Critical | `check_domain_isolation.py` | 扫描构建包中非生产 API 域名 |
| SEC-003 | 非生产域名检查 | 静态 | Critical | `check_domain_isolation.py` | 扫描构建包中 `dev.`/`test.`/`staging.` 域名 |
| SEC-004 | iOS Associated Domains | 静态 | High | `check_domain_isolation.py` | 解析 `Info.plist` / `AssociatedDomains` |
| SEC-005 | Android Deep Links | 静态 | High | `check_deep_link_isolation.py` | 解析 `AndroidManifest.xml` `intent-filter` |
| SEC-006 | Debug / 敏感日志 | 动态 | Critical | `check_log_isolation.py` | 运行 App → 抓取日志 → 分级扫描 |
| SEC-007 | Token 本地存储 | 静态 + 动态 | Critical | `check_encryption_storage.py` | 旧版 Hive 扫描 + Keychain 验证 |
| SEC-008 | iOS Documents Sharing | 静态 | High | `check_ios_file_sharing.py` | 检查 `UIFileSharingEnabled` |
| SEC-009 | Mock 数据 | 静态 | Medium/High | `check_mock_data_removal.py` | 扫描 `mock_`/`fixture_` 资源 |
| SEC-010 | Dart Obfuscation | 构建检查 | High | `check_dart_obfuscation.py` | 检查 `--obfuscate` + 映射文件 |
| SEC-011 | Symbol 文件 | 构建检查 | High | `check_dart_obfuscation.py` | 验证符号文件可映射崩溃堆栈 |
| SEC-012 | Release 配置 | 构建检查 | Critical | `check_release_config.py` | 验证构建参数 `--release`/`--obfuscate` |

---

## 执行流程

```
git push → Build Release → Generate IPA/APK → Security Gate → PASS / FAIL
                                      ↓
                          ┌─────────────────────────┐
                          │ Production Security Gate│
                          └────────────┬────────────┘
                                       ↓
                    ┌──────────────────┼──────────────────┐
                    ↓                  ↓                  ↓
               SEC-001            SEC-002~003          SEC-004~005
               (Debug/Oops)       (Domain/Link)        (iOS/Android)
                    ↓                  ↓                  ↓
               SEC-006            SEC-007              SEC-008~009
               (Logs/Token)         (Storage)           (Sharing/Mock)
                    ↓                  ↓                  ↓
               SEC-010~011         SEC-012
               (Obfuscation/     (Release Config)
                Symbols)
                    └──────────────────┬──────────────────┘
                                       ↓
                                  PASS / FAIL
```

---

## 分级标准（SEC-006 日志检测）

| 级别 | 模式示例 | 说明 |
|---|---|---|
| Critical | `token=...` / `Bearer ...` / `authorization: Bearer ...` | 完整凭证泄露，立即阻断 |
| Critical | `password=...` / `secret_key=...` | 敏感凭证明文 |
| High | `userId=...` / `email=...` / `phone=...` | 用户标识信息 |
| Medium | `requestBody=...` / `responseBody=...` | 业务参数（需结合业务判断） |

---

## 白名单治理

- `policies/forbidden_domains.yaml`：定义禁止出现的测试/开发域名
- `policies/allowlist.yaml`：定义已审计通过的第三方 SDK 字符串（白名单）
- 更新必须 `Signed-off-by` 审批，不得直接修改
