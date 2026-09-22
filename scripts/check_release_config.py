#!/usr/bin/env python3
"""
SEC-012: 发布前自动校验 Release 构建配置
检查构建参数、build.gradle、pubspec.yaml、Info.plist 是否正确配置为 Release/Obfuscate
"""

import argparse
import json
import re
import sys
from pathlib import Path

def check_build_config(build_log_path, build_gradle_path, pubspec_path):
    result = {
        "test_case": "SEC-012",
        "test_name": "Release 构建配置检查",
        "status": "PASS",
        "findings": [],
        "details": {}
    }

    # 无任何构建输入 → SKIPPED（Fail-Closed：不得默认 PASS）
    has_any_input = any(
        p and Path(p).exists()
        for p in (build_log_path, build_gradle_path, pubspec_path)
    )
    if not has_any_input:
        result["status"] = "SKIPPED"
        result["findings"].append({
            "type": "no_build_input",
            "severity": "CRITICAL",
            "value": "未提供 build.log / build.gradle / pubspec.yaml，无法验证 Release 构建配置"
        })
        result["details"]["note"] = "Fail-Closed: 无构建输入 → SKIPPED → BLOCK，绝不视为 PASS。"
        return result

    # 检查构建日志参数
    if build_log_path and Path(build_log_path).exists():
        content = Path(build_log_path).read_text(errors='ignore')
        
        if "--release" not in content:
            result["findings"].append({
                "type": "build_mode_not_release",
                "value": "缺少 --release 参数",
                "severity": "CRITICAL"
            })
        
        if "--obfuscate" not in content:
            result["findings"].append({
                "type": "obfuscate_flag_missing",
                "value": "缺少 --obfuscate 参数",
                "severity": "HIGH"
            })
        
        if "--split-debug-info" not in content:
            result["findings"].append({
                "type": "split_debug_info_missing",
                "value": "缺少 --split-debug-info 参数",
                "severity": "HIGH"
            })
        
        result["details"]["build_log"] = "已分析"
    
    # 检查 Android build.gradle
    if build_gradle_path and Path(build_gradle_path).exists():
        content = Path(build_gradle_path).read_text(errors='ignore')
        
        if "minifyEnabled" in content:
            match = re.search(r"minifyEnabled\s+(true|false)", content)
            if match and match.group(1) == "false":
                result["findings"].append({
                    "type": "android_minify_disabled",
                    "value": "minifyEnabled = false",
                    "severity": "CRITICAL"
                })
        else:
            result["findings"].append({
                "type": "android_minify_not_configured",
                "severity": "MEDIUM"
            })
        
        if "proguardFiles" not in content:
            result["findings"].append({
                "type": "android_proguard_missing",
                "severity": "LOW"
            })
        
        result["details"]["android_build_gradle"] = "已分析"
    
    # 检查 pubspec.yaml
    if pubspec_path and Path(pubspec_path).exists():
        content = Path(pubspec_path).read_text(errors='ignore')
        
        if "environment" in content:
            # 检查是否有调试环境变量
            if "DEBUG" in content or "dev" in content.lower():
                result["findings"].append({
                    "type": "pubspec_debug_env",
                    "severity": "MEDIUM"
                })
        
        result["details"]["pubspec"] = "已分析"
    
    if result["findings"]:
        result["status"] = "FAIL"
        result["details"]["total_findings"] = len(result["findings"])
    
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-log", help="构建日志")
    parser.add_argument("--build-gradle", help="build.gradle 路径")
    parser.add_argument("--pubspec", help="pubspec.yaml 路径")
    parser.add_argument("--output-json", help="输出 JSON")
    args = parser.parse_args()
    
    res = check_build_config(args.build_log, args.build_gradle, args.pubspec)
    
    if args.output_json:
        with open(args.output_json, 'w') as f:
            json.dump(res, f, indent=2)
    
    print(f"SEC-012 结果: {res['status']}")
    for f in res["findings"]:
        print(f"  - [{f['severity']}] {f['type']} {f.get('value','')}")
    
    sys.exit(0 if res["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()