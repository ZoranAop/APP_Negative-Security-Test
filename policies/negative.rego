package release
import rego.v1
default allow = false

# Fail-Closed: 只有全部 PASS 且无禁止状态且证据完整才允许
allow {
  not block_if_platform_failed
  not block_if_forbidden_status
  not block_if_thirdparty_unlisted
  not block_if_rule_failed
  evidence_complete
  every platform in input.platforms {
    input.evidence[platform].status == "PASS"
    count(input.evidence[platform].rules) == count(input.required_rules[platform])
    every rule in input.evidence[platform].rules {
      rule.status == "PASS"
    }
  }
}

block_if_platform_failed {
  some platform in input.platforms
  input.evidence[platform].status == "FAIL"
}

block_if_forbidden_status {
  some platform in input.platforms
  some rule in input.evidence[platform].rules
  forbidden := {"FRAMEWORK_READY","SKIPPED","REVIEW","UNKNOWN","FAIL"}
  forbidden[rule.status]
}

block_if_thirdparty_unlisted {
  some platform in input.platforms
  some rule in input.evidence[platform].rules
  rule.status == "THIRDPARTY"
  not input.allowlist[rule.id]
}

block_if_rule_failed {
  some platform in input.platforms
  some rule in input.evidence[platform].rules
  rule.status != "PASS"
}

evidence_complete {
  every platform in input.platforms {
    every required in input.required_rules[platform] {
      some rule in input.evidence[platform].rules
      rule.id == required
      rule.status == "PASS"
    }
    count(input.evidence[platform].rules) == count(input.required_rules[platform])
  }
}

release_decision := "ALLOW" if { allow }
release_decision := "BLOCK" if { not allow }

# Severity vocabulary for manual review / reporting (not blocking logic)
# Critical: must block; High: must block; Medium: block unless reviewed; Low: record; Informational: record

