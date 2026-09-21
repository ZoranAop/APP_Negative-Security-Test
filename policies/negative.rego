package release

# 反向安全测试（Negative Security Test）策略即代码（Policy-as-Code）
# 评估对象：CI 流水线产出的证据包（evidence bundle）
# 评估结果：data.release.allow = true  → 允许发布
#            data.release.allow = false → 阻断发布

import rego.v1

# ---------------------------------------------------------------------------
# 默认策略：默认拒绝（Fail-Closed）
# ---------------------------------------------------------------------------
default allow = false

# 只有当所有平台、所有规则全部通过时，才允许发布
allow {
  every platform in input.platforms {
    platform_evidence := input.evidence[platform]
    platform_evidence.exists
    platform_evidence.status == "PASS"
    every rule in platform_evidence.rules {
      rule.status == "PASS"
    }
    count(platform_evidence.rules) == count(input.required_rules[platform])
  }
}

# ---------------------------------------------------------------------------
# 平台证据结构（由 gate_decision.py / CI 流水线生成）
# ---------------------------------------------------------------------------
# input.evidence = {
#   "android": {
#     "status": "PASS" | "FAIL" | "SKIPPED",
#     "rules": [
#       {
#         "id": "NS-01-debug-isolation",
#         "name": "调试面板/抓包隔离",
#         "status": "PASS",
#         "evidence_file": "results/evidence/debug_symbols/NS-01.txt",
#         "details": "grep 未检出 debugPrint/kDebugMode/assert"
#       }
#     ],
#     "artifacts": {
#       "apk": "build/app/outputs/flutter-apk/app-release.apk",
#       "mapping_file": "build/symbols/android/mapping.txt"
#     }
#   },
#   "ios": {...}
# }

# ---------------------------------------------------------------------------
# 平台级规则
# ---------------------------------------------------------------------------
platform_status_evidence(platform, status) {
  input.evidence[platform].status == status
}

# ---------------------------------------------------------------------------
# 平台级阻断条件
# ---------------------------------------------------------------------------
block_if_platform_failed {
  some platform in input.platforms
  input.evidence[platform].status == "FAIL"
}

# ---------------------------------------------------------------------------
# 规则级阻断条件（任一规则 FAIL 即阻断）
# ---------------------------------------------------------------------------
block_if_rule_failed {
  some platform in input.platforms
  some rule in input.evidence[platform].rules
  rule.status == "FAIL"
}

# ---------------------------------------------------------------------------
# 证据完整性检查
# ---------------------------------------------------------------------------
evidence_complete {
  every platform in input.platforms {
    platform_evidence := input.evidence[platform]
    platform_evidence.artifacts.apk
    platform_evidence.artifacts.mapping_file
    every rule in platform_evidence.rules {
      rule.evidence_file
    }
  }
}

# ---------------------------------------------------------------------------
# 发布决策
# ---------------------------------------------------------------------------
release_decision := "ALLOW" if {
  allow
  evidence_complete
}

release_decision := "BLOCK" if {
  not allow
}
