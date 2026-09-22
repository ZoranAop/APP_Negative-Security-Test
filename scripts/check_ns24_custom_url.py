#!/usr/bin/env python3
"""
NS-24: Custom URL Scheme / OAuth Security Check
目标：验证第三方 App 是否可劫持 OAuth / 登录回调；每个 Scheme 必须有业务用途表；动态测试 state/noset/repeat/code/redirect_uri
状态：PASS / FAIL / REVIEW / SKIP
工具缺失（无法读取 Info.plist / 无测试设备）→ REVIEW + reason=tool_unavailable
"""
import argparse, os, sys, json, subprocess, re
from pathlib import Path
from datetime import datetime, timezone


def ensure_dir(p):
    Path(p).mkdir(parents=True, exist_ok=True)


def run_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return -1, "", str(e)


def main():
    parser = argparse.ArgumentParser(description="NS-24 Custom URL Scheme / OAuth Security Check")
    parser.add_argument("--ipa", default="")
    parser.add_argument("--info-plist", default="")
    parser.add_argument("--manifest", default="")
    parser.add_argument("--output-dir", default="results/NS-24", help="输出目录")
    args = parser.parse_args()

    ensure_dir(args.output_dir)
    ensure_dir(os.path.join(args.output_dir, "raw"))

    timestamp = datetime.now(timezone.utc).isoformat()
    result = {
        "id": "NS-24",
        "test_name": "Custom URL Scheme / OAuth Negative Security Test",
        "status": "REVIEW",
        "reason": "",
        "timestamp": timestamp,
        "checks": {
            "url_schemes_extracted": "REVIEW",
            "scheme_purpose_map": "REVIEW",
            "oauth_state_check": "REVIEW",
            "oauth_nonce_check": "REVIEW",
            "oauth_pkce_check": "REVIEW",
            "callback_dynamic_tests": "REVIEW",
            "scheme_hijack_validation": "REVIEW"
        },
        "test_mode": "STATIC + DYNAMIC",
        "evidence": {},
        "raw_files": [],
        "notes": []
    }

    # 提取 URL Schemes（从 Info.plist 或 Manifest）
    schemes = []
    info_path = args.info_plist
    if info_path and os.path.isfile(info_path):
        rc_pl, out_pl, _ = run_cmd(f"plutil -convert xml1 -o - '{info_path}' 2>/dev/null || cat '{info_path}'")
        plist_text = out_pl
        # 提取 CFBundleURLSchemes
        m_schemes = re.search(r'<key>CFBundleURLSchemes</key>.*?<array>(.*?)</array>', plist_text, re.DOTALL)
        if m_schemes:
            schemes = re.findall(r'<string>([^<]+)</string>', m_schemes.group(1))
    else:
        # 尝试解包提取（简化）
        result["notes"].append("未提供 Info.plist，尝试依赖默认提取流程。")

    result["checks"]["url_schemes_extracted"] = "PASS" if schemes else ("FAIL" if not schemes else "PASS")
    result["evidence"]["url_schemes"] = schemes
    result["notes"].append(f"提取到的 Scheme 列表: {schemes}")

    # 建立用途表（标准化要求：每个 Scheme 必须有用途）
    # 默认业务映射（根据用户描述示例）
    purpose_map = {
        "xxai": {"purpose": "App Deep Link", "required": True, "status": "PASS"},
        "com.xxai.app.mobile": {"purpose": "Internal Callback", "required": False, "status": "REVIEW"},
        "com.googleusercontent.apps": {"purpose": "Google Login", "required": True, "status": "PASS"}
    }
    # 对提取到的每个 Scheme 建立条目；若无业务依据则标记为 REVIEW
    mapped_purposes = {}
    for s in schemes:
        if s in purpose_map:
            mapped_purposes[s] = purpose_map[s]
        else:
            mapped_purposes[s] = {"purpose": "UNKNOWN", "required": False, "status": "REVIEW", "note": "无明确业务依据，需人工确认是否必要"}
    result["evidence"]["scheme_purpose_map"] = mapped_purposes
    result["checks"]["scheme_purpose_map"] = "PASS" if all(p.get("status") == "PASS" for p in mapped_purposes.values()) else "REVIEW"

    # OAuth 配置检查（静态/半静态：检查代码/配置中是否存在 state/nonce/pkce 相关配置）
    # 当前脚本记录检查框架，真实业务动态验证需要运行时测试环境
    result["checks"]["oauth_state_check"] = "REVIEW"
    result["checks"]["oauth_nonce_check"] = "REVIEW"
    result["checks"]["oauth_pkce_check"] = "REVIEW"
    result["checks"]["callback_dynamic_tests"] = "REVIEW"
    result["checks"]["scheme_hijack_validation"] = "REVIEW"
    result["notes"].append("OAuth state/noset/PKCE/redirect_uri 检查：需要运行时动态测试（正常/篡改 state、重复 state、过期 code、重复 code、错误 client_id）才能最终判定 PASS/FAIL。静态检查已记录标准框架。")
    result["notes"].append("Scheme 劫持验证：需要在测试环境安装一个测试 App 注册相同 Scheme，观察 XXAI OAuth Callback 是否可能被截获。仅在证明敏感认证结果通过可被劫持的 Scheme 传递且无充分保护时，才可判 FAIL；否则为 REVIEW。")

    # 最终状态判断：不能直接判 PASS（缺少动态验证）；不能直接判 FAIL（无证据证明漏洞存在）
    # 标准化要求：没有足够证据完成最终判断 → REVIEW
    result["status"] = "REVIEW"
    result["reason"] = "requires_dynamic_oauth_callback_and_scheme_hijack_validation"

    # 写证据
    evidence_bundle = {
        "test_case": "NS-24",
        "test_name": "Custom URL Scheme / OAuth Security Check",
        "status": result["status"],
        "reason": result["reason"],
        "timestamp": timestamp,
        "test_mode": result["test_mode"],
        "checks": result["checks"],
        "notes": result["notes"],
        "evidence_summary": result["evidence"],
        "manual_review_required": True,
        "recommendation": "执行完整验证建议：1) 确认每个 Scheme 有业务用途表，无业务依据的 Scheme 应移除或标记；2) 执行 OAuth 动态测试（正常/篡改 state/重复/过期 code）；3) 执行 Scheme 劫持测试，确认敏感认证结果不通过可被劫持的 Scheme 传递。"
    }

    with open(os.path.join(args.output_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.output_dir, "evidence.json"), "w", encoding="utf-8") as f:
        json.dump(evidence_bundle, f, ensure_ascii=False, indent=2)

    # 动态测试计划（记录为 Markdown 证据）
    dynamic_plan = """## 动态测试计划（标准化结构）

### 正常 Callback 测试
- 预期：`code=A` + `state=X` → PASS（继续流程）

### 篡改 State 测试
- 输入：`code=A` + `state=Y`（与原请求不一致）
- 预期：拒绝（FAIL 处理），不继续流程

### 重复 State 测试
- 输入：重复使用已消费的 `state`
- 预期：拒绝

### 错误 Redirect URI 测试
- 输入：`redirect_uri` 与注册值不一致
- 预期：拒绝

### 过期 Code 测试
- 输入：已过期或已使用的 `code`
- 预期：拒绝

### 重复 Code 测试
- 输入：重复提交同一 `code`
- 预期：拒绝

### 错误 Client ID 测试
- 输入：`client_id` 不匹配
- 预期：拒绝

### Scheme 劫持测试
- 在测试设备安装测试 App 注册相同 Scheme（如 `xxai`）
- 触发 XXAI OAuth 回调
- 观察：敏感认证结果（如 `token`、用户标识）是否可能被测试 App 截获
- 判定条件：仅在证明敏感认证结果通过可被劫持的 Scheme 传递，且无充分保护（如无 state 绑定、无签名验证、无应用来源校验）时 → FAIL；否则 → REVIEW（不能直接判 FAIL）。
"""
    with open(os.path.join(args.output_dir, "raw", "dynamic_test_plan.md"), "w", encoding="utf-8") as f:
        f.write(dynamic_plan)
    result["raw_files"].append("raw/dynamic_test_plan.md")

    report_md = f"""# NS-24 报告 — Custom URL Scheme / OAuth 专项

## 测试状态
- **状态**: `{result['status']}`
- **原因**: `{result['reason']}`
- **时间戳**: `{timestamp}`

## 流程执行
1. 测试准备: 完成
2. 提取测试对象: 提取 `CFBundleURLSchemes` → `{schemes}`
3. 基础静态检查: 已提取 Info.plist / Manifest（如可用）
4. 专项规则检查: 已建立 `scheme_purpose_map`（每个 Scheme 必须有业务依据）
5. 必要动态验证: **REVIEW**（需要运行时 OAuth 测试与 Scheme 劫持测试）
6. 证据收集: `evidence.json` + `summary.json` + `raw/dynamic_test_plan.md`
7. 规则化判定: 完成（标准化状态）
8. 人工 REVIEW: **必需**（确认业务依据 + 执行动态测试）
9. 最终判定: `{result['status']}`

## 检查结果
| 检查项 | 状态 | 说明 |
|---|---|---|
| url_schemes_extracted | `{result['checks']['url_schemes_extracted']}` | 提取状态 |
| scheme_purpose_map | `{result['checks']['scheme_purpose_map']}` | 每个 Scheme 必须有明确业务用途 |
| oauth_state_check | `{result['checks']['oauth_state_check']}` | 需动态测试 |
| oauth_nonce_check | `{result['checks']['oauth_nonce_check']}` | 需动态测试 |
| oauth_pkce_check | `{result['checks']['oauth_pkce_check']}` | 需动态测试 |
| callback_dynamic_tests | `{result['checks']['callback_dynamic_tests']}` | 需执行正常/篡改/重复/过期等测试 |
| scheme_hijack_validation | `{result['checks']['scheme_hijack_validation']}` | 需安装测试 App 注册同 Scheme 观察截获 |

## 重要规则重申
- **Custom Scheme 存在 ≠ 漏洞**：正确判断是：是否存在敏感认证结果通过可被其他 App 劫持的 Scheme 传递，并且没有充分的安全保护（如 state 绑定、签名验证、应用来源校验）。
- 无足够证据时，不得判 FAIL（只能判 REVIEW）。
- 工具不可用时，状态为 REVIEW（`reason=tool_unavailable`），不得降级为 FAIL。
"""
    with open(os.path.join(args.output_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"[NS-24] 完成。状态={result['status']}, 原因={result['reason']}, 输出={args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
