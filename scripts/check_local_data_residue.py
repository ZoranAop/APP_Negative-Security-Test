#!/usr/bin/env python3
"""NS-17: 本地敏感数据残留检查（扩展 NS-05）"""
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--apk")
parser.add_argument("--output-json")
args = parser.parse_args()
res = {
    "test_case":"NS-17", "test_name":"Sensitive Local Data Residue",
    "status":"FRAMEWORK_READY",
    "checks":[
        {"id":"shared_prefs_token","desc":"SharedPreferences / 数据库 / Hive 是否含明文 Token", "severity":"CRITICAL"},
        {"id":"cache_sensitive","desc":"Cache / 临时文件是否含敏感内容", "severity":"HIGH"},
        {"id":"clipboard_sensitive","desc":"剪贴板是否包含敏感数据（运行时检查）", "severity":"MEDIUM"},
        {"id":"sqlite_user_data","desc":"SQLite 数据库是否包含完整用户信息/消息/密钥", "severity":"HIGH"},
        {"id":"crash_dump_sensitive","desc":"崩溃日志是否包含敏感数据（运行时检查）", "severity":"MEDIUM"},
    ],
    "notes":"完整执行需要解包 APK 扫描资源 + 运行时登录验证（结合 NS-05 动态测试）。"
}
with open(args.output_json or "/tmp/NS-17.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
print("NS-17 框架完成")
