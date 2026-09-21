#!/usr/bin/env python3
"""
发布门禁（Release Gate）决策脚本
基于 OPA 策略评估反向安全测试证据，决定发布是否允许
"""

import argparse
import json
import sys
from pathlib import Path


def load_json(path):
    """加载 JSON 文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_policy_decision(policy_path, policy_input):
    """加载 OPA 策略评估结果（真实执行 opa eval，失败则完整性检查 fallback，默认拒绝）"""
    import subprocess, tempfile, os
    if policy_path and Path(policy_path).exists():
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(policy_input, f, ensure_ascii=False, indent=2)
            input_path = f.name
        try:
            cmd = ["opa", "eval", "-i", input_path, "-d", str(policy_path), "--format", "json", "data.release.allow"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                try:
                    opa_output = json.loads(result.stdout)
                    expressions = opa_output.get("result", [{}])[0].get("expressions", [{}])
                    value_raw = expressions[0].get("value", False) if expressions else False
                    allow = bool(value_raw) if isinstance(value_raw, bool) else False
                    return {"allow": allow, "source": "opa_eval", "complete": True, "raw_stdout": result.stdout}
                except Exception:
                    pass
            # 完整性检查 fallback（默认拒绝）
            evidence_items = policy_input.get("evidence", {})
            evidence_complete = isinstance(evidence_items, dict) and len(evidence_items) > 0 and all(isinstance(v, dict) for v in evidence_items.values())
            all_pass = evidence_complete and all(v.get("status") == "PASS" for v in evidence_items.values())
            return {"allow": False, "source": "integrity_check_fallback", "complete": evidence_complete, "all_evidence_complete": evidence_complete, "all_tests_pass": all_pass, "evidence": evidence_items, "note": "OPA 执行失败，执行完整性检查 fallback（Fail-Closed 默认拒绝）；请安装 opactl 并修复 policy"}
        finally:
            try:
                os.unlink(input_path)
            except Exception:
                pass
    else:
        evidence_items = policy_input.get("evidence", {})
        evidence_complete = isinstance(evidence_items, dict) and len(evidence_items) > 0 and all(isinstance(v, dict) for v in evidence_items.values())
        all_pass = evidence_complete and all(v.get("status") == "PASS" for v in evidence_items.values())
        return {"allow": False, "source": "integrity_check_no_policy", "complete": evidence_complete, "all_evidence_complete": evidence_complete, "all_tests_pass": all_pass, "evidence_summary": evidence_items, "note": "无 policy 文件，执行完整性检查（默认拒绝）；提供 negative.rego 并安装 opa 以启用完整策略评估"}


def evaluate_gate(policy_decision, test_results):
    """评估门禁决策"""
    all_tests_pass = all(
        result.get("status") == "PASS"
        for result in test_results
    )
    
    policy_allow = policy_decision.get("allow", False)
    
    # 只有策略允许且所有测试通过才允许发布
    allow = policy_allow and all_tests_pass
    
    return {
        "decision": "ALLOW" if allow else "BLOCK",
        "policy_decision": policy_decision,
        "all_tests_pass": all_tests_pass,
        "test_results": test_results,
        "evaluated_at": "now"
    }


def main():
    parser = argparse.ArgumentParser(description="发布门禁决策脚本")
    parser.add_argument("--evidence-dir", required=True, help="证据目录")
    parser.add_argument("--policy-dir", help="策略目录")
    parser.add_argument("--policy-file", default=None, help="OPA 策略文件路径")
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    parser.add_argument("--platform", default="android,ios", help="测试平台")
    
    args = parser.parse_args()
    
    evidence_dir = Path(args.evidence_dir)
    policy_dir = Path(args.policy_dir) if args.policy_dir else evidence_dir
    
    # 加载平台证据
    platform_list = [p.strip() for p in args.platform.split(",") if p.strip()]
    policy_input = {
        "platforms": platform_list,
        "required_rules": {
            platform: [f"NS-{i:02d}" for i in range(1, 10)]
            for platform in platform_list
        },
        "evidence": {}
    }
    
    for platform in platform_list:
        platform_evidence_path = evidence_dir / f"{platform}.json"
        if platform_evidence_path.exists():
            platform_evidence = load_json(platform_evidence_path)
            policy_input["evidence"][platform] = platform_evidence
        else:
            policy_input["evidence"][platform] = {
                "status": "FAIL",
                "rules": [],
                "artifacts": {},
                "error": f"缺少平台证据文件: {platform_evidence_path}"
            }
    
    # 加载策略
    policy_path = args.policy_file if args.policy_file else policy_dir / "negative.rego"
    policy_decision = load_policy_decision(policy_path, policy_input)
    
    # 加载测试结果
    test_results = []
    for platform in platform_list:
        platform_result_path = evidence_dir / f"{platform}_results.json"
        if platform_result_path.exists():
            test_results.extend(load_json(platform_result_path))
        else:
            # 尝试从平台证据中提取
            platform_evidence = policy_input["evidence"][platform]
            test_results.extend(platform_evidence.get("rules", []))
    
    # 评估门禁
    gate_decision = evaluate_gate(policy_decision, test_results)
    
    # 保存结果
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(gate_decision, f, ensure_ascii=False, indent=2)
    
    # 输出决策
    print(f"门禁决策: {gate_decision['decision']}")
    print(f"策略允许: {policy_decision.get('allow', False)}")
    print(f"所有测试通过: {gate_decision['all_tests_pass']}")
    print(f"失败测试数: {sum(1 for r in test_results if r.get('status') != 'PASS')}")
    
    if gate_decision["decision"] == "BLOCK":
        for result in test_results:
            if result.get("status") != "PASS":
                print(f"  - 失败: {result.get('test_name', result.get('test_case', 'unknown'))}")
    
    sys.exit(0 if gate_decision["decision"] == "ALLOW" else 1)


if __name__ == "__main__":
    main()