#!/usr/bin/env python3
"""NS-18: 屏幕隐私 / 截图 / App Switcher 保护检查
Fail-Closed：无输入或框架未实现 → SKIPPED → BLOCK（绝不 PASS / exit 0）
"""
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--apk", help="APK 文件路径")
parser.add_argument("--ipa", help="IPA 文件路径")
parser.add_argument("--output-json")
args = parser.parse_args()

CHECKS = [
    {"id":"flag_secure","desc":"FLAG_SECURE 是否启用（Android）", "severity":"MEDIUM"},
    {"id":"app_switcher_snapshot","desc":"iOS App Switcher 快照是否受保护", "severity":"LOW"},
    {"id":"screenshot_protection","desc":"截图保护配置（运行时检查）", "severity":"LOW"}
]

has_input = bool((args.apk and args.apk) or (args.ipa and args.ipa))
if not has_input:
    status = "SKIPPED"
    notes = "Fail-Closed：无 apk/ipa 输入，无法执行屏幕隐私检查。SKIPPED → BLOCK，绝不视为 PASS。"
elif True:
    # 当前为框架占位实现，未扫描传入的 APK/IPA
    status = "SKIPPED"
    notes = "Fail-Closed：框架占位实现，尚未扫描 APK/IPA 屏幕保护配置。SKIPPED → BLOCK，需补充真实扫描逻辑后方可放行。"
else:
    status = "FRAMEWORK_READY"
    notes = "生产包可根据业务需求决定是否启用屏幕保护；本检查记录配置状态而非强制阻断。"

res = {
    "test_case":"NS-18", "test_name":"Screen / Snapshot Privacy",
    "status":status,
    "checks":CHECKS,
    "notes":notes
}
with open(args.output_json or "/tmp/NS-18.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
print(f"NS-18 结果: {status} — {notes}")
# Fail-Closed：仅当真实 PASS 时退出码 0
sys.exit(0 if status == "PASS" else 1)
