#!/usr/bin/env python3
"""NS-21: 禁止能力动态测试（真实执行框架版，需设备/模拟器完整执行）
检查生产包是否具备不应存在的能力（Debug Menu、Mock Server、开发深链、测试资源访问等）
状态：PASS（能力不可用）/ FAIL（能力可用）/ SKIPPED（无设备无法执行动态触发，Fail-Closed → BLOCK）
"""
import argparse, json, sys, os

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--apk"); parser.add_argument("--device-id"); parser.add_argument("--output-json")
    args = parser.parse_args()
    # 无真实设备 = SKIPPED；按 Fail-Closed 原则，不得为 PASS
    if not args.device_id:
        with open(args.output_json or "/tmp/NS-21.json","w") as f: json.dump({"test_case":"NS-21","test_name":"Forbidden Capability Dynamic Test","status":"SKIPPED","findings":[{"capability":"Oops_DevMenu_Trigger","expected":"不可用","actual":"未执行（无设备）","severity":"CRITICAL"}],"notes":"动态能力测试需要连接模拟器/真机执行完整触发流程。缺少设备应为 SKIPPED → BLOCK。","source":"无设备"}, f, indent=2, ensure_ascii=False)
        print("NS-21 SKIPPED — 无设备，动态能力测试无法执行（Fail-Closed → BLOCK）")
        sys.exit(1)
    # 有设备时执行触发（简化：记录触发尝试）
    findings = [{"capability":"Oops_DevMenu_Trigger","expected":"不可用","actual":"需运行时验证","severity":"CRITICAL"}]
    with open(args.output_json or "/tmp/NS-21.json","w") as f: json.dump({"test_case":"NS-21","test_name":"Forbidden Capability Dynamic Test","status":"REVIEW","findings":findings,"notes":"已提供设备 ID，但完整触发验证需执行动态脚本（test_dynamic_debug_trigger.py）。","source":"device_id: "+args.device_id}, f, indent=2, ensure_ascii=False)
    print("NS-21 REVIEW — 设备已提供，需完整触发脚本执行（建议结合 test_dynamic_debug_trigger.py 执行）")
    sys.exit(1)
if __name__=="__main__": main()
