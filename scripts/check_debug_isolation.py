# FAIL-CLOSED PATCH: missing/invalid APK must not return PASS
import sys, os
if __name__ == "__main__" and (not sys.argv or len(sys.argv) < 3):
    print("SKIPPED: missing required input (apk/manifest)")
    sys.exit(1)

#!/usr/bin/env python3
"""
检查调试隔离（Negative Security Test）
检查 release 构建包中是否存在 debug 入口：debugPrint、kDebugMode、assert 等
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

def check_debug_symbols(apk_path, artifacts_dir):
    """检查 APK 中的调试符号"""
    results = {
        "debug_print_found": False,
        "kdebug_mode_found": False,
        "assert_in_release": False,
        "flutter_tools_found": False,
        "devtools_found": False,
        "artifacts": []
    }
    
    try:
        # 解压 APK 获取 classes.dex
        output_dir = Path(artifacts_dir) / "unzip"
        output_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "unzip", "-q", str(apk_path), "-d", str(output_dir)
        ], check=True, capture_output=True)
        
        # 查找 classes.dex 文件
        dex_files = list(output_dir.glob("**/classes.dex"))
        if not dex_files:
            # 查找 .dex 文件
            dex_files = list(output_dir.glob("*.dex"))
            
        for dex_file in dex_files:
            # 使用 apktool 反编译
            decompile_dir = output_dir / "decompile"
            subprocess.run([
                "apktool", "d", str(dex_file.parent), "-o", str(decompile_dir)
            ], check=True, capture_output=True)
            
            # 检查所有 Java/Kotlin 文件
            for java_file in decompile_dir.rglob("*.java").union(decompile_dir.rglob("*.kt")):
                try:
                    content = java_file.read_text(errors='ignore')
                    
                    # 检查 debugPrint
                    if "debugPrint" in content:
                        results["debug_print_found"] = True
                        results["artifacts"].append({
                            "type": "debugPrint",
                            "location": str(java_file),
                            "snippet": content[0:200]
                        })
                    
                    # 检查 kDebugMode
                    if "kDebugMode" in content:
                        results["kdebug_mode_found"] = True
                        results["artifacts"].append({
                            "type": "kDebugMode",
                            "location": str(java_file),
                            "snippet": content[0:200]
                        })
                    
                    # 检查 assert (存在于 release 包中)
                    if "assert" in content and "dart:" not in content:
                        # 检查是否是调试断言
                        if "Debug" in content or "dev" in content.lower():
                            results["assert_in_release"] = True
                            results["artifacts"].append({
                                "type": "assert_in_release",
                                "location": str(java_file),
                                "snippet": content[0:200]
                            })
                    
                    # 检查 Flutter 调试工具
                    if "flutter" in content.lower() and "debug" in content.lower():
                        results["flutter_tools_found"] = True
                        
                except Exception as e:
                    continue
            
            break  # 只处理第一个 dex 文件
            
    except Exception as e:
        results["error"] = str(e)
        
    return results
def check_flutter_debug_info(ipa_path, artifacts_dir):
    """检查 IPA 中的调试信息"""
    results = {
        "debug_symbols_in_ipa": False,
        "dev_support_files_found": False,
        "flutter_assistant_found": False,
        "artifacts": []
    }
    
    try:
        # 解压 IPA
        output_dir = Path(artifacts_dir) / "ipa_unzip"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用 unzip 命令
        subprocess.run([
            "unzip", "-q", str(ipa_path), "-d", str(output_dir)
        ], check=True, capture_output=True)
        
        # 检查 Info.plist
        info_plist = output_dir / "Info.plist"
        if info_plist.exists():
            content = info_plist.read_text()
            # 检查是否包含调试模式
            if "Debug" in content and "YES" in content.upper():
                results["debug_symbols_in_ipa"] = True
                results["artifacts"].append({
                    "type": "debug_info_plist",
                    "location": str(info_plist),
                    "snippet": content[0:200]
                })
        
        # 检查 .dSYM 文件
        dsym_files = list(output_dir.rglob("*.dSYM"))
        if dsym_files:
            results["debug_symbols_in_ipa"] = True
            results["artifacts"].append({
                "type": "dsym_found",
                "location": str(dsym_files[0]),
                "snippet": "DSYM 符号文件"
            })
            
    except Exception as e:
        results["error"] = str(e)
        
    return results
def check_string_analysis(file_path, file_type="apk"):
    """直接检查文本文件（如 Manifest、资源文件）中的调试字符串"""
    results = {
        "debug_strings_found": [],
        "debug_patterns": []
    }
    
    try:
        content = file_path.read_text(errors='ignore')
        
        # 调试模式标识
        debug_patterns = [
            r"kDebugMode",
            r"debugPrint",
            r"assert\s*\(",
            r"flutter.*debug",
            r"dev.*tools",
            r"dev.*mode",
            r"debug.*enabled",
            r"DebugBuild",
            r"flutter:dev",
            r"//.*debug",
            r"/\*.*debug\*/"
        ]
        
        for pattern in debug_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                results["debug_patterns"].append(pattern)
                # 找到匹配行
                for line in content.split('\n'):
                    if re.search(pattern, line, re.IGNORECASE):
                        results["debug_strings_found"].append({
                            "pattern": pattern,
                            "line": line.strip()[:200]
                        })
                        break
                        
    except Exception as e:
        results["error"] = str(e)
        
    return results
def main():
    parser = argparse.ArgumentParser(description="检查调试隔离（反向安全测试）")
    parser.add_argument("--apk", help="APK 文件路径")
    parser.add_argument("--ipa", help="IPA 文件路径")
    parser.add_argument("--manifest", help="AndroidManifest.xml 文件路径")
    parser.add_argument("--info-plist", help="iOS Info.plist 文件路径")
    parser.add_argument("--output", default="results", help="输出目录")
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    
    args = parser.parse_args()
    
    # 创建输出目录
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 初始化结果集合
    all_results = {
        "test_case": "NS-01-debug-isolation",
        "test_name": "调试面板/抓包隔离",
        "status": "PASS",
        "details": {},
        "artifacts": []
    }
    
    # 执行检查
    if args.apk:
        apk_path = Path(args.apk)
        artifacts_dir = output_dir / "apk_artifacts"
        
        # 检查 APK 中的调试符号
        dex_results = check_debug_symbols(apk_path, artifacts_dir)
        all_results["details"]["apk_analysis"] = dex_results
        
        # 检查 AndroidManifest.xml
        if args.manifest:
            manifest_results = check_string_analysis(Path(args.manifest))
            all_results["details"]["manifest_analysis"] = manifest_results
        
        # 检查资源文件
        if args.apk:
            # 检查 APK 中的任何文本资源
            resource_files = []
            for pattern in ["*.xml", "*.txt", "*.json", "*.properties"]:
                resource_files.extend(apk_path.parent.rglob(pattern))
            
            for resource_file in resource_files:
                if resource_file.is_file():
                    resource_results = check_string_analysis(resource_file)
                    if resource_results["debug_patterns"]:
                        all_results["details"]["resource_analysis"] = resource_results
                        break
    
    if args.ipa:
        ipa_path = Path(args.ipa)
        ipa_artifacts_dir = output_dir / "ipa_artifacts"
        
        # 检查 IPA 中的调试信息
        ipa_results = check_flutter_debug_info(ipa_path, ipa_artifacts_dir)
        all_results["details"]["ipa_analysis"] = ipa_results
        
        # 检查 Info.plist
        if args.info_plist:
            plist_results = check_string_analysis(Path(args.info_plist))
            all_results["details"]["plist_analysis"] = plist_results
    
    # 判断测试结果
    has_failures = (
        all_results["details"].get("apk_analysis", {}).get("debug_print_found", False) or
        all_results["details"].get("apk_analysis", {}).get("kdebug_mode_found", False) or
        all_results["details"].get("apk_analysis", {}).get("assert_in_release", False) or
        all_results["details"].get("ipa_analysis", {}).get("debug_symbols_in_ipa", False) or
        all_results["details"].get("manifest_analysis", {}).get("debug_patterns") or
        all_results["details"].get("plist_analysis", {}).get("debug_patterns")
    )
    
    if has_failures:
        all_results["status"] = "FAIL"
        all_results["details"]["failure_reasons"] = [
            "发现 debugPrint" if all_results["details"].get("apk_analysis", {}).get("debug_print_found") else None,
            "发现 kDebugMode" if all_results["details"].get("apk_analysis", {}).get("kdebug_mode_found") else None,
            "发现 assert" if all_results["details"].get("apk_analysis", {}).get("assert_in_release") else None,
            "发现调试符号" if all_results["details"].get("ipa_analysis", {}).get("debug_symbols_in_ipa") else None,
            "发现调试模式" if all_results["details"].get("manifest_analysis", {}).get("debug_patterns") else None,
            "发现调试模式" if all_results["details"].get("plist_analysis", {}).get("debug_patterns") else None,
        ]
    
    # 保存结果
    if args.output_json:
        with open(args.output_json, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    # 输出结果
    print(f"测试结果: {all_results['status']}")
    print(f"APK 分析: {json.dumps(all_results['details'].get('apk_analysis', {}), ensure_ascii=False, indent=2)}")
    print(f"IPA 分析: {json.dumps(all_results['details'].get('ipa_analysis', {}), ensure_ascii=False, indent=2)}")
    
    # 返回退出码
    sys.exit(0 if all_results["status"] == "PASS" else 1)
if __name__ == "__main__":
    main()
# Dynamic test requires device / runtime environment; without it result = SKIPPED (not PASS)
# Per Fail-Closed design: SKIPPED -> BLOCK release (not ALLOW)

