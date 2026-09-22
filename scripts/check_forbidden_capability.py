#!/usr/bin/env python3
"""NS-21: 禁止能力动态测试（增强版，静态+框架结合）
无设备时 SKIPPED（Fail-Closed → BLOCK）；有设备时需结合动态触发脚本执行；增加静态预检（debug symbols/mock/dev domains）
"""
import argparse, json, sys, os

def static_precheck(apk_path):
    findings = []
    # Pre-check: if debug symbols / dev URLs / mock resources exist statically, note as potential capability
    # Actual full dynamic trigger requires device + test_dynamic_debug_trigger.py
    if apk_path and os.path.exists(apk_path):
        try:
            import zipfile
            with zipfile.ZipFile(apk_path,"r") as z:
                names = z.namelist()
                for n in names:
                    if "debug" in n.lower() or "mock" in n.lower() or "dev" in n.lower() or ".debug" in n:
                        findings.append({"id":"potential_debug_artifact","severity":"MEDIUM","note":"APK 中存在调试/模拟/开发相关文件: "+n,"suggest":"需设备动态触发验证是否可用"})
        except Exception as e:
            findings.append({"id":"static_check_error","severity":"LOW","note":"静态预检异常: "+str(e)})
    return findings

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--apk"); parser.add_argument("--device-id"); parser.add_argument("--output-json")
    args = parser.parse_args()
    static_findings = static_precheck(args.apk)
    if not args.device_id:
        res = {"test_case":"NS-21","test_name":"Forbidden Capability Dynamic Test","status":"SKIPPED","findings":static_findings + [{"id":"no_device","severity":"CRITICAL","note":"无设备无法执行动态触发。Fail-Closed：SKIPPED → BLOCK，绝不视为 PASS"}],"notes":"已执行静态预检；动态能力测试（Oops/DevMenu/Mock Server/Debug 操作）需要连接模拟器/真机完成完整触发流程并生成证据（触发记录+设备信息+屏幕录制+结果）"}
        with open(args.output_json or "/tmp/NS-21.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
        print("NS-21 SKIPPED — 无设备，动态能力测试无法执行（Fail-Closed → BLOCK）。已附静态预检结果。")
        sys.exit(0)  # Exit 0 with SKIPPED status; gate_decision must treat SKIPPED as BLOCK
    # With device: combine static findings + trigger attempt record
    findings = static_findings + [{"id":"device_available","severity":"LOW","note":"设备已提供（"+args.device_id+"），建议结合 test_dynamic_debug_trigger.py 执行完整触发并记录证据"}]
    res = {"test_case":"NS-21","test_name":"Forbidden Capability Dynamic Test","status":"REVIEW","findings":findings,"notes":"设备已提供，应执行完整触发验证（尝试触发 Oops/DevMenu、访问 dev 深链、连接 Mock Server、执行 debug）并生成 JUnit JSON + 屏幕录制证据。如触发成功 → FAIL；如无法触发 → PASS（需人工确认）。"}
    with open(args.output_json or "/tmp/NS-21.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
    print("NS-21 REVIEW — 设备已提供，需结合动态触发脚本执行完整验证并生成证据链。")
    sys.exit(0)
if __name__=="__main__": main()
