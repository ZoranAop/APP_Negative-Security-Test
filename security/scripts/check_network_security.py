#!/usr/bin/env python3
"""NS-12: 网络安全配置检查（SSL/ATS/CA Bypass/Pinning Disabled）
Fail-Closed：无输入或框架未实现 → SKIPPED → BLOCK（绝不 PASS / exit 0）
"""
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--manifest", help="AndroidManifest.xml 或 Info.plist 路径")
parser.add_argument("--apk", help="APK 文件路径")
parser.add_argument("--output-json")
args = parser.parse_args()

CHECKS = [
    {"id":"cleartext_traffic","desc":"usesCleartextTraffic=true / NSAllowsArbitraryLoads","severity":"CRITICAL","method":"解析 manifest / plist"},
    {"id":"ca_trust_all","desc":"trust-all CA / debug CA / certificate pinning disabled","severity":"CRITICAL","method":"搜索 kTrustAllCertificates / NSExceptionDomains"},
    {"id":"hostname_verifier_bypass","desc":"hostname verifier bypass / SSL bypass","severity":"HIGH","method":"代码/资源搜索"},
    {"id":"debug_proxy","desc":"Debug proxy / MITM 配置残留","severity":"HIGH","method":"配置文件扫描"},
    {"id":"network_config_file","desc":"Android NetworkSecurityConfig / iOS ATS 配置完整性","severity":"MEDIUM","method":"检查配置文件存在与内容"}
]

has_input = bool((args.manifest and args.manifest) or (args.apk and args.apk))
if not has_input:
    status = "SKIPPED"
    notes = "Fail-Closed：无 manifest/apk 输入，无法执行网络安全配置检查。SKIPPED → BLOCK，绝不视为 PASS。"
elif True:
    # 当前为框架占位实现，未解析传入的 manifest/APK
    status = "SKIPPED"
    notes = "Fail-Closed：框架占位实现，尚未解析 manifest/APK。SKIPPED → BLOCK，需补充真实解析逻辑后方可放行。"
else:
    status = "FRAMEWORK_READY"
    notes = "完整执行需要解析实际构建产物的 manifest、Info.plist、NetworkSecurityConfig 文件。"

res = {
    "test_case":"NS-12", "test_name":"Network Security Configuration",
    "status":status,
    "checks":CHECKS,
    "notes":notes
}
with open(args.output_json or "/tmp/NS-12.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
print(f"NS-12 结果: {status} — {notes}")
# Fail-Closed：仅当真实 PASS 时退出码 0
sys.exit(0 if status == "PASS" else 1)
