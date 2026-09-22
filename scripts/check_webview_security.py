#!/usr/bin/env python3
"""NS-16: WebView 安全检查
Fail-Closed：无输入或框架未实现 → SKIPPED → BLOCK（绝不 PASS / exit 0）
"""
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--manifest", help="AndroidManifest.xml 路径")
parser.add_argument("--apk", help="APK 文件路径")
parser.add_argument("--output-json")
args = parser.parse_args()

CHECKS = [
    {"id":"javascript_enabled","desc":"JavaScript 是否不必要启用", "severity":"MEDIUM"},
    {"id":"javascript_interface","desc":"addJavascriptInterface 是否暴露敏感接口", "severity":"CRITICAL"},
    {"id":"file_access","desc":"setAllowFileAccess / setAllowUniversalAccessFromFileURLs", "severity":"HIGH"},
    {"id":"debug_webview","desc":"setWebContentsDebuggingEnabled(true)", "severity":"HIGH"},
    {"id":"mixed_content","desc":"混合内容策略（HTTP/HTTPS 混合）", "severity":"MEDIUM"},
    {"id":"url_whitelist","desc":"WebView 加载 URL 是否有白名单控制", "severity":"HIGH"}
]

has_input = bool((args.manifest and args.manifest) or (args.apk and args.apk))
if not has_input:
    status = "SKIPPED"
    notes = "Fail-Closed：无 manifest/apk 输入，无法执行 WebView 安全检查。SKIPPED → BLOCK，绝不视为 PASS。"
elif True:
    # 当前为框架占位实现，未解析传入的 manifest/APK
    status = "SKIPPED"
    notes = "Fail-Closed：框架占位实现，尚未扫描 WebView 配置。SKIPPED → BLOCK，需补充真实扫描逻辑后方可放行。"
else:
    status = "FRAMEWORK_READY"
    notes = "完整执行需要代码扫描（查找 WebView 相关类和配置）+ 运行时验证。"

res = {
    "test_case":"NS-16", "test_name":"WebView Security",
    "status":status,
    "checks":CHECKS,
    "notes":notes
}
with open(args.output_json or "/tmp/NS-16.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
print(f"NS-16 结果: {status} — {notes}")
# Fail-Closed：仅当真实 PASS 时退出码 0
sys.exit(0 if status == "PASS" else 1)
