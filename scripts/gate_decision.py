#!/usr/bin/env python3
"""
发布门禁（Release Gate）决策脚本
基于 OPA 策略评估反向安全测试证据，决定发布是否允许
优先调用 opa eval；OPA 不可用时 fallback 到内置逻辑并输出 WARNING
"""
import argparse, json, subprocess, sys, shutil
from pathlib import Path


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def opa_available():
    return shutil.which("opa") is not None


def run_opa_eval(policy_path, input_data, output_json):
    """调用 OPA 执行策略，返回 allow 决策"""
    tmp_input = Path(output_json).parent / "opa_input.json"
    tmp_input.write_text(json.dumps(input_data), encoding="utf-8")
    try:
        r = subprocess.run(
            ["opa", "eval",
             "--data", str(policy_path),
             "--input", str(tmp_input),
             "--format", "json",
             "data.release"],
            capture_output=True, text=True, timeout=30,
        )
        tmp_input.unlink(missing_ok=True)
        if r.returncode != 0:
            print(f"WARNING: opa eval 失败 (rc={r.returncode}): {r.stderr.strip()}", file=sys.stderr)
            return None
        result = json.loads(r.stdout)
        try:
            value = result["result"][0]["expressions"][0]["value"]
            return value
        except (KeyError, IndexError):
            print(f"WARNING: OPA 输出格式异常: {r.stdout[:200]}", file=sys.stderr)
            return None
    except subprocess.TimeoutExpired:
        print("WARNING: opa eval 超时", file=sys.stderr)
        return None
    except Exception as e:
        print(f"WARNING: opa eval 异常: {e}", file=sys.stderr)
        return None


def simplified_policy_decision(policy_input):
    """OPA 不可用时的简化 fallback：所有平台所有规则必须 PASS"""
    all_pass = True
    for platform, evidence in policy_input.get("evidence", {}).items():
        if evidence.get("status") != "PASS":
            all_pass = False
        for rule in evidence.get("rules", []):
            if rule.get("status") != "PASS":
                all_pass = False
        required = policy_input.get("required_rules", {}).get(platform, [])
        if len(evidence.get("rules", [])) != len(required):
            all_pass = False
    return {"allow": all_pass, "method": "simplified_fallback"}


def evaluate_gate(policy_decision, test_results):
    all_tests_pass = all(r.get("status") == "PASS" for r in test_results)
    policy_allow = policy_decision.get("allow", False)
    allow = policy_allow and all_tests_pass
    return {
        "decision": "ALLOW" if allow else "BLOCK",
        "policy_decision": policy_decision,
        "all_tests_pass": all_tests_pass,
        "test_results": test_results,
    }


def main():
    parser = argparse.ArgumentParser(description="发布门禁决策脚本")
    parser.add_argument("--evidence-dir", required=True, help="证据目录")
    parser.add_argument("--policy-dir", help="策略目录")
    parser.add_argument("--policy-file", default=None, help="OPA rego 文件路径（默认 policy-dir/negative.rego）")
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    parser.add_argument("--platform", default="android,ios", help="测试平台")
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir)
    policy_dir = Path(args.policy_dir) if args.policy_dir else evidence_dir
    policy_path = Path(args.policy_file) if args.policy_file else policy_dir / "negative.rego"

    platform_list = [p.strip() for p in args.platform.split(",") if p.strip()]
    policy_input = {
        "platforms": platform_list,
        "required_rules": {
            platform: [f"NS-{i:02d}" for i in range(1, 10)]
            for platform in platform_list
        },
        "evidence": {},
    }

    for platform in platform_list:
        platform_evidence_path = evidence_dir / f"{platform}.json"
        if platform_evidence_path.exists():
            policy_input["evidence"][platform] = load_json(platform_evidence_path)
        else:
            policy_input["evidence"][platform] = {
                "status": "FAIL",
                "rules": [],
                "artifacts": {},
                "error": f"缺少平台证据文件: {platform_evidence_path}",
            }

    # 收集测试结果
    test_results = []
    for platform in platform_list:
        platform_result_path = evidence_dir / f"{platform}_results.json"
        if platform_result_path.exists():
            data = load_json(platform_result_path)
            test_results.extend(data if isinstance(data, list) else [data])
        else:
            test_results.extend(policy_input["evidence"][platform].get("rules", []))

    # 策略决策
    opa_ok = opa_available() and policy_path.exists()
    if opa_ok:
        opa_result = run_opa_eval(policy_path, policy_input, args.output_json or "/tmp/opa_eval.json")
        if opa_result is not None:
            policy_decision = {
                "allow": bool(opa_result.get("allow", False)),
                "method": "opa_eval",
                "details": opa_result,
            }
            print(f"策略评估方式: opa_eval (allow={policy_decision['allow']})")
        else:
            policy_decision = simplified_policy_decision(policy_input)
            print(f"WARNING: OPA 评估失败，使用简化 fallback: {json.dumps(policy_decision, ensure_ascii=False)}",
                  file=sys.stderr)
    else:
        policy_decision = simplified_policy_decision(policy_input)
        if not opa_available():
            print("WARNING: opa 命令未找到，使用简化 fallback 策略", file=sys.stderr)
        if not policy_path.exists():
            print(f"WARNING: 策略文件 {policy_path} 不存在，使用简化 fallback 策略", file=sys.stderr)

    gate_decision = evaluate_gate(policy_decision, test_results)
    gate_decision["evaluated_at"] = "now"

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(gate_decision, f, ensure_ascii=False, indent=2)

    print(f"门禁决策: {gate_decision['decision']}")
    print(f"  策略允许: {policy_decision.get('allow', False)}  (method: {policy_decision.get('method','?')})")
    print(f"  所有测试通过: {gate_decision['all_tests_pass']}")
    print(f"  失败测试数: {sum(1 for r in test_results if r.get('status') != 'PASS')}")

    if gate_decision["decision"] == "BLOCK":
        for result in test_results:
            if result.get("status") != "PASS":
                print(f"  - 失败: {result.get('test_name', result.get('test_case', 'unknown'))}")

    sys.exit(0 if gate_decision["decision"] == "ALLOW" else 1)


if __name__ == "__main__":
    main()
