#!/usr/bin/env python3
"""
检查 Dart 混淆（Negative Security Test）
验证 release 构建是否启用了 Dart 混淆，并检查符号文件是否留存
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

def check_dart_obfuscation_enabled(apk_path, artifacts_dir):
    """检查 APK 中是否启用了 Dart 混淆"""
    result = {
        "test_case": "NS-08-dart-obfuscation",
        "test_name": "Flutter Release 启用 Dart 混淆",
        "status": "PASS",
        "findings": [],
        "details": {
            "obfuscation_enabled": False,
            "class_names_readable": [],
            "mapping_file_found": False,
            "mapping_file_path": None
        }
    }
    
    try:
        # 检查是否提供了混淆构建产物
        mapping_dir = Path(artifacts_dir) / "symbols" / "dart"
        
        # 1. 检查 mapping 文件是否存在
        mapping_files = []
        for pattern in ["mapping.txt", "obfuscation_map.json"]:
            mapping_files.extend(artifacts_dir.rglob(pattern))
        
        if mapping_files:
            result["details"]["mapping_file_found"] = True
            result["details"]["mapping_file_path"] = str(mapping_files[0])
            
            # 验证 mapping 文件内容
            mapping_content = mapping_files[0].read_text(errors='ignore')
            
            # 检查 mapping 文件格式是否正确
            if len(mapping_content) > 100 and "flutter" in mapping_content.lower():
                result["details"]["mapping_valid"] = True
            else:
                result["findings"].append({
                    "type": "mapping_file_invalid",
                    "file": str(mapping_files[0]),
                    "severity": "HIGH"
                })
                result["details"]["mapping_valid"] = False
        else:
            result["findings"].append({
                "type": "mapping_file_missing",
                "severity": "HIGH",
                "description": "未找到混淆符号文件（mapping.txt），生产崩溃无法还原堆栈"
            })
        
        # 2. 检查 APK 中的类名是否被混淆
        # 通过 jadx 反编译 APK 检查类名可读性
        output_dir = Path(artifacts_dir) / "jadx_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        subprocess.run([
            "jadx", "--show-bad-code", str(apk_path), "-d", str(output_dir)
        ], check=True, capture_output=True, timeout=120)
        
        # 统计可读类名数量
        readable_classes = []
        total_classes = 0
        
        for java_file in output_dir.rglob("*.java"):
            total_classes += 1
            try:
                content = java_file.read_text(errors='ignore')
                
                # 检查类名是否可读（非混淆）
                class_name = java_file.name.replace('.java', '')
                
                # 混淆后的类名通常很短（1-3个字符）
                # 可读类名通常包含有意义的单词
                if len(class_name) > 3:
                    # 检查是否是可读的类名
                    readable_patterns = [
                        r'[A-Z][a-z]+[A-Z][a-z]+',  # CamelCase
                        r'[_a-z]+',  # snake_case
                    ]
                    
                    for pattern in readable_patterns:
                        if re.search(pattern, class_name) and not class_name.startswith('_'):
                            readable_classes.append({
                                "class": class_name,
                                "file": str(java_file)
                            })
                            break
            except Exception:
                continue
        
        result["details"]["total_classes"] = total_classes
        result["details"]["readable_classes"] = readable_classes[:10]  # 限制输出
        
        if readable_classes:
            result["findings"].append({
                "type": "readable_class_names_found",
                "count": len(readable_classes),
                "severity": "MEDIUM",
                "description": f"发现 {len(readable_classes)} 个可读类名，混淆可能不完整"
            })
            result["details"]["obfuscation_enabled"] = False
        else:
            result["details"]["obfuscation_enabled"] = True
    
    except subprocess.TimeoutExpired:
        result["findings"].append({
            "type": "jadx_timeout",
            "severity": "LOW"
        })
    except Exception as e:
        result["error"] = str(e)
        result["findings"].append({
            "type": "analysis_error",
            "value": str(e),
            "severity": "HIGH"
        })
    
    # 判断结果
    if result["findings"]:
        result["status"] = "FAIL"
        result["details"]["total_findings"] = len(result["findings"])
    
    return result

def check_symbol_files(artifacts_dir):
    """检查符号文件是否留存"""
    result = {
        "test_case": "NS-08-symbol-files",
        "symbol_files_found": [],
        "symbol_files_count": 0
    }
    
    try:
        # 查找所有符号文件
        symbol_patterns = [
            "mapping.txt",
            "obfuscation_map.json",
            "symbols.txt",
            "*.dSYM",
            "*.map"
        ]
        
        for pattern in symbol_patterns:
            result["symbol_files_found"].extend(artifacts_dir.rglob(pattern))
        
        result["symbol_files_count"] = len(result["symbol_files_found"])
        
        # 检查符号文件完整性
        for symbol_file in result["symbol_files_found"]:
            if symbol_file.is_file():
                content = symbol_file.read_text(errors='ignore')
                
                # 检查文件大小（空文件说明有问题）
                if symbol_file.stat().st_size < 100:
                    result["symbol_files_found"].remove(symbol_file)
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def check_flutter_build_flags(build_log_path):
    """检查 Flutter 构建日志中的混淆标志"""
    result = {
        "test_case": "NS-08-build-flags",
        "obfuscation_flag_found": False,
        "build_mode": None,
        "split_debug_info_found": False,
        "obfuscate_flag": None
    }
    
    if not build_log_path.exists():
        return result
    
    try:
        content = build_log_path.read_text(errors='ignore')
        
        # 检查 --obfuscate 标志
        if "--obfuscate" in content:
            result["obfuscation_flag_found"] = True
            result["obfuscate_flag"] = "--obfuscate"
        
        # 检查 --split-debug-info 标志
        if "--split-debug-info" in content:
            result["split_debug_info_found"] = True
        
        # 检查构建模式
        if "--release" in content:
            result["build_mode"] = "release"
        elif "--debug" in content:
            result["build_mode"] = "debug"
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def main():
    parser = argparse.ArgumentParser(description="检查 Dart 混淆（反向安全测试）")
    parser.add_argument("--apk", help="APK 文件路径")
    parser.add_argument("--ipa", help="IPA 文件路径")
    parser.add_argument("--artifacts-dir", required=True, help="构建产物目录")
    parser.add_argument("--build-log", help="Flutter 构建日志文件")
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    
    args = parser.parse_args()
    
    results = {
        "test_case": "NS-08-dart-obfuscation",
        "test_name": "Flutter Release 启用 Dart 混淆与符号文件留存",
        "status": "PASS",
        "findings": [],
        "details": {}
    }
    
    # 1. 检查混淆符号文件
    symbol_result = check_symbol_files(Path(args.artifacts_dir))
    results["details"]["symbol_files"] = {
        "count": symbol_result["symbol_files_count"],
        "files": [str(f) for f in symbol_result["symbol_files_found"]]
    }
    
    # 2. 检查混淆是否启用
    if args.apk and Path(args.apk).exists():
        apk_result = check_dart_obfuscation_enabled(Path(args.apk), args.artifacts_dir)
        results["findings"].extend(apk_result["findings"])
        results["details"]["obfuscation_analysis"] = apk_result["details"]
        
        # 检查符号文件
        if not symbol_result["symbol_files_found"]:
            results["findings"].append({
                "type": "symbol_file_missing",
                "severity": "HIGH",
                "description": "APK 构建产物中未找到符号文件，无法还原崩溃堆栈"
            })
    
    # 3. 检查构建日志
    if args.build_log and Path(args.build_log).exists():
        build_result = check_flutter_build_flags(Path(args.build_log))
        results["details"]["build_flags"] = build_result
        
        if not build_result["obfuscation_flag_found"]:
            results["findings"].append({
                "type": "obfuscation_flag_not_found",
                "severity": "HIGH",
                "description": "构建日志中未发现 --obfuscate 标志"
            })
        
        if not build_result["split_debug_info_found"]:
            results["findings"].append({
                "type": "split_debug_info_flag_not_found",
                "severity": "HIGH",
                "description": "构建日志中未发现 --split-debug-info 标志"
            })
    
    # 判断结果
    if results["findings"]:
        results["status"] = "FAIL"
        results["details"]["total_findings"] = len(results["findings"])
    
    # 保存结果
    if args.output_json:
        with open(args.output_json, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"测试结果: {results['status']}")
    print(f"发现 {len(results['findings'])} 个问题:")
    for finding in results["findings"]:
        print(f"  - [{finding['type']}] {finding.get('description', '')}")
    
    sys.exit(0 if results["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()