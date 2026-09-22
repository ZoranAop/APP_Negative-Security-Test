#!/usr/bin/env python3
"""NS-15: Deep Link / Intent 注入安全检查
Fail-Closed：无输入或框架未实现 → SKIPPED → BLOCK（绝不 PASS / exit 0）
"""
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--manifest", help="AndroidManifest.xml 路径")
parser.add_argument("--apk", help="APK 文件路径")
parser.add_argument("--output-json")
args = parser.parse_args()

CHECKS = [
    {"id":"open_redirect","desc":"deep link 参数中是否存在未验证 redirect/url/callback", "severity":"CRITICAL"},
    {"id":"javascript_scheme","desc":"javascript: / file: / content: 注入", "severity":"HIGH"},
    {"id":"intent_redirection","desc":"未登录状态访问敏感页面 / 参数绕过权限", "severity":"HIGH"},
    {"id":"parameter_validation","desc":"intent 参数未验证格式/长度/类型", "severity":"MEDIUM"},
    {"id":"exported_deep_link_protection","desc":"导出的 Deep Link Activity 是否受权限保护", "severity":"MEDIUM"}
]

has_input = bool((args.manifest and args.manifest) or (args.apk and args.apk))
if not has_input:
    status = "SKIPPED"
    notes = "Fail-Closed：无 manifest/apk 输入，无法执行 Intent 注入安全检查。SKIPPED → BLOCK，绝不视为 PASS。"
elif True:
    # 当前为框架占位实现，未解析传入的 manifest/APK
    status = "SKIPPED"
    notes = "Fail-Closed：框架占位实现，尚未解析 manifest 深链暴露。SKIPPED → BLOCK，需补充真实解析逻辑后方可放行。"
else:
    status = "FRAMEWORK_READY"
    notes = "完整执行需要解析 manifest + 测试实际深链触发（动态测试结合 NS-21）。"

res = {
    "test_case":"NS-15", "test_name":"Intent / Deep Link Injection Security",
    "status":status,
    "checks":CHECKS,
    "notes":notes
}
with open(args.output_json or "/tmp/NS-15.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
print(f"NS-15 结果: {status} — {notes}")
# Fail-Closed：仅当真实 PASS 时退出码 0
sys.exit(0 if status == "PASS" else 1)
