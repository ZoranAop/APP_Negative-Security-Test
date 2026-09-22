#!/usr/bin/env python3
"""NS-17: 本地敏感数据残留检查（扩展 NS-05）
Fail-Closed：无输入或框架未实现 → SKIPPED → BLOCK（绝不 PASS / exit 0）
"""
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--apk", help="APK 文件路径")
parser.add_argument("--build-dir", help="构建目录路径")
parser.add_argument("--output-json")
args = parser.parse_args()

CHECKS = [
    {"id":"shared_prefs_token","desc":"SharedPreferences / 数据库 / Hive 是否含明文 Token", "severity":"CRITICAL"},
    {"id":"cache_sensitive","desc":"Cache / 临时文件是否含敏感内容", "severity":"HIGH"},
    {"id":"clipboard_sensitive","desc":"剪贴板是否包含敏感数据（运行时检查）", "severity":"MEDIUM"},
    {"id":"sqlite_user_data","desc":"SQLite 数据库是否包含完整用户信息/消息/密钥", "severity":"HIGH"},
    {"id":"crash_dump_sensitive","desc":"崩溃日志是否包含敏感数据（运行时检查）", "severity":"MEDIUM"}
]

has_input = bool((args.apk and args.apk) or (args.build_dir and args.build_dir))
if not has_input:
    status = "SKIPPED"
    notes = "Fail-Closed：无 apk/build-dir 输入，无法执行本地数据残留检查。SKIPPED → BLOCK，绝不视为 PASS。"
elif True:
    # 当前为框架占位实现，未扫描传入的 APK/构建目录
    status = "SKIPPED"
    notes = "Fail-Closed：框架占位实现，尚未扫描 APK 本地存储文件。SKIPPED → BLOCK，需补充真实扫描逻辑后方可放行。"
else:
    status = "FRAMEWORK_READY"
    notes = "完整执行需要解包 APK 扫描资源 + 运行时登录验证（结合 NS-05 动态测试）。"

res = {
    "test_case":"NS-17", "test_name":"Sensitive Local Data Residue",
    "status":status,
    "checks":CHECKS,
    "notes":notes
}
with open(args.output_json or "/tmp/NS-17.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
print(f"NS-17 结果: {status} — {notes}")
# Fail-Closed：仅当真实 PASS 时退出码 0
sys.exit(0 if status == "PASS" else 1)
