#!/usr/bin/env python3
"""NS-12: 网络安全配置检查框架（SSL/ATS/CA Bypass/Pinning Disabled）"""
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--manifest", help="AndroidManifest.xml 或 Info.plist 路径")
parser.add_argument("--output-json")
args = parser.parse_args()
res = {
    "test_case":"NS-12", "test_name":"Network Security Configuration",
    "status":"FRAMEWORK_READY",
    "checks":[
        {"id":"cleartext_traffic","desc":"usesCleartextTraffic=true / NSAllowsArbitraryLoads","severity":"CRITICAL","method":"解析 manifest / plist"},
        {"id":"ca_trust_all","desc":"trust-all CA / debug CA / certificate pinning disabled","severity":"CRITICAL","method":"搜索 kTrustAllCertificates / NSExceptionDomains"},
        {"id":"hostname_verifier_bypass","desc":"hostname verifier bypass / SSL bypass","severity":"HIGH","method":"代码/资源搜索"},
        {"id":"debug_proxy","desc":"Debug proxy / MITM 配置残留","severity":"HIGH","method":"配置文件扫描"},
        {"id":"network_config_file","desc":"Android NetworkSecurityConfig / iOS ATS 配置完整性","severity":"MEDIUM","method":"检查配置文件存在与内容"}
    ],
    "notes":"完整执行需要解析实际构建产物的 manifest、Info.plist、NetworkSecurityConfig 文件。"
}
with open(args.output_json or "/tmp/NS-12.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
print("NS-12 框架完成")
