#!/usr/bin/env python3
"""NS-13: 生产构建权限最小化审计
Fail-Closed：无输入或框架未实现 → SKIPPED → BLOCK（绝不 PASS / exit 0）
"""
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--manifest", help="AndroidManifest.xml 路径")
parser.add_argument("--apk", help="APK 文件路径")
parser.add_argument("--output-json")
args = parser.parse_args()

CHECKS = [
    {"id":"high_risk_permissions","desc":"CAMERA/RECORD_AUDIO/READ_MEDIA/LOCATION/BLUETOOTH", "severity":"HIGH","rule":"检查是否有业务对应功能"},
    {"id":"install_packages","desc":"REQUEST_INSTALL_PACKAGES / SYSTEM_ALERT_WINDOW", "severity":"CRITICAL","rule":"生产包应禁止"},
    {"id":"query_all_packages","desc":"QUERY_ALL_PACKAGES", "severity":"MEDIUM","rule":"检查是否必要"},
    {"id":"permission_business_mapping","desc":"每个权限应映射到业务功能，否则应移除", "severity":"MEDIUM","rule":"构建脚本审计"}
]

has_input = bool((args.manifest and args.manifest) or (args.apk and args.apk))
if not has_input:
    status = "SKIPPED"
    notes = "Fail-Closed：无 manifest/apk 输入，无法执行权限最小化审计。SKIPPED → BLOCK，绝不视为 PASS。"
elif True:
    # 当前为框架占位实现，未解析传入的 manifest/APK
    status = "SKIPPED"
    notes = "Fail-Closed：框架占位实现，尚未解析 manifest 权限列表。SKIPPED → BLOCK，需补充真实解析逻辑后方可放行。"
else:
    status = "FRAMEWORK_READY"
    notes = "需要解析 AndroidManifest.xml + 业务功能映射表（白名单）。"

res = {
    "test_case":"NS-13", "test_name":"Production Permission Audit",
    "status":status,
    "checks":CHECKS,
    "notes":notes
}
with open(args.output_json or "/tmp/NS-13.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
print(f"NS-13 结果: {status} — {notes}")
# Fail-Closed：仅当真实 PASS 时退出码 0
sys.exit(0 if status == "PASS" else 1)
