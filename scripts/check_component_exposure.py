#!/usr/bin/env python3
"""
SEC-014: Android Component Exposure 检查框架
检查 AndroidManifest.xml 中 exported Activity / Service / Receiver / Provider
"""
import argparse, json, sys, re

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", help="AndroidManifest.xml 路径（可选）")
    parser.add_argument("--apk")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = {
        "test_case": "NS-14",
        "test_name": "Android Component Exposure",
        "status": "FRAMEWORK_READY",
        "findings": [
            {"check": "exported_activity", "value": "需要解析 manifest 提取 android:exported=true", "severity": "HIGH"},
            {"check": "debug_activity", "value": "检查 DebugActivity / TestActivity / InspectorActivity 是否存在", "severity": "CRITICAL"},
            {"check": "provider_permission", "value": "检查 exported Provider 是否受 android:authorities / permission 保护", "severity": "MEDIUM"},
            {"check": "receiver_exported", "value": "检查 BroadcastReceiver 是否无必要导出", "severity": "MEDIUM"},
        ],
        "notes": "完整执行需要 aapt2 解析 manifest 或解压后的 AndroidManifest.xml 文件。"
    }
    with open(args.output_json or "/tmp/NS-14.json", "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"NS-14 结果: {result['status']} — 框架已就绪")
    sys.exit(0)

if __name__ == "__main__":
    main()
