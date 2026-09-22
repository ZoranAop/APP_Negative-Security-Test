#!/usr/bin/env python3
"""
检查 Mock 数据移除（Negative Security Test）
检查生产构建包中是否存在 mock/fixture/test 数据
"""

import argparse
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

def scan_apk_resources(apk_path, mock_patterns):
    """扫描 APK 中的资源文件"""
    results = {
        "test_case": "NS-07-mock-data-removal",
        "test_name": "移除生产包 mock 数据",
        "status": "PASS",
        "findings": [],
        "mock_files": [],
        "mock_strings": [],
        "details": {}
    }
    
    try:
        # 解压 APK
        with zipfile.ZipFile(apk_path, 'r') as apk_zip:
            all_files = apk_zip.namelist()
            
            # 扫描资源文件
            for file_path in all_files:
                if not file_path.startswith("assets/"):
                    continue
                
                # 检查文件名
                for pattern in mock_patterns:
                    if re.search(pattern, file_path, re.IGNORECASE):
                        results["mock_files"].append({
                            "file": file_path,
                            "pattern": pattern
                        })
                        results["findings"].append({
                            "type": "mock_resource_found",
                            "file": file_path,
                            "pattern": pattern,
                            "severity": "HIGH"
                        })
                
                # 扫描文件内容
                try:
                    content = apk_zip.read(file_path).decode('utf-8', errors='ignore')
                    
                    for pattern in mock_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            # 找到匹配的字符串
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            for match in matches[:5]:  # 限制数量
                                results["mock_strings"].append({
                                    "file": file_path,
                                    "pattern": pattern,
                                    "match": str(match)[:200]
                                })
                                results["findings"].append({
                                    "type": "mock_content_found",
                                    "file": file_path,
                                    "pattern": pattern,
                                    "match": str(match)[:100],
                                    "severity": "HIGH"
                                })
                
                except Exception as e:
                    continue
            
            # 检查 assets 目录结构
            asset_dirs = set()
            for file_path in all_files:
                if file_path.startswith("assets/"):
                    parts = file_path.split("/")
                    if len(parts) > 1:
                        asset_dirs.add(parts[1])
            
            results["details"]["asset_subdirs"] = list(asset_dirs)
            results["details"]["total_asset_files"] = len(all_files)

    except Exception as e:
        results["error"] = str(e)
        results["findings"].append({
            "type": "apk_read_error",
            "value": str(e),
            "severity": "MEDIUM"
        })
    
    # 判断结果
    if results["findings"]:
        results["status"] = "FAIL"
        results["details"]["total_findings"] = len(results["findings"])
    
    return results

def scan_dart_code(dart_files, mock_patterns):
    """扫描 Dart 源代码中的 mock 数据引用"""
    results = {
        "test_case": "NS-07-dart-mock-scan",
        "test_name": "检查 Dart 代码中的 Mock 数据",
        "status": "PASS",
        "findings": [],
        "mock_imports": []
    }
    
    for dart_file in dart_files:
        try:
            content = dart_file.read_text(encoding='utf-8', errors='ignore')
            
            for pattern in mock_patterns:
                matches = list(re.finditer(pattern, content, re.IGNORECASE))
                if matches:
                    for match in matches:
                        # 找到所在行
                        lines = content.split('\n')
                        line_num = content[:match.start()].count('\n') + 1
                        line = lines[line_num - 1].strip()[:200] if line_num <= len(lines) else ""
                        
                        results["findings"].append({
                            "type": "mock_code_reference",
                            "file": str(dart_file),
                            "pattern": pattern,
                            "line": line_num,
                            "line_content": line,
                            "severity": "HIGH"
                        })
                        results["mock_imports"].append({
                            "file": str(dart_file),
                            "line": line_num,
                            "match": match.group(0)[:100]
                        })
        
        except Exception as e:
            continue
    
    if results["findings"]:
        results["status"] = "FAIL"
    
    return results

def check_pubspec_for_mock(pubspec_path):
    """检查 pubspec.yaml 是否包含 mock 依赖"""
    result = {
        "test_case": "NS-07-pubspec-check",
        "pubspec_path": str(pubspec_path),
        "mock_dependencies": [],
        "status": "PASS"
    }
    
    try:
        if not pubspec_path.exists():
            result["error"] = "pubspec.yaml 不存在"
            return result
        
        content = pubspec_path.read_text(encoding='utf-8', errors='ignore')
        
        # 检查 mock 相关依赖
        mock_dependencies = [
            r'mockito',  # 常见测试框架
            r'fake_[^/]+',  # 精确假数据包
            r'data_mock_[^/]+',
            r'fixture_[^/]+',
            r'dummy_[^/]+',
            r'mock_[^/]+\.dart'  # 精确 mock 数据文件
        ]
        
        for dep_pattern in mock_dependencies:
            # 在 dependencies 或 dev_dependencies 块中检查
            if re.search(rf'^\s*{dep_pattern}', content, re.IGNORECASE | re.MULTILINE):
                result["mock_dependencies"].append(dep_pattern)
        
        if result["mock_dependencies"]:
            result["status"] = "FAIL"
    
    except Exception as e:
        result["error"] = str(e)
    
    return result

def main():
    parser = argparse.ArgumentParser(description="检查 Mock 数据移除（反向安全测试）")
    parser.add_argument("--apk", help="APK 文件路径")
    parser.add_argument("--ipa", help="IPA 文件路径")
    parser.add_argument("--pubspec", help="pubspec.yaml 路径")
    parser.add_argument("--dart-lib", help="Dart lib 目录路径")
    parser.add_argument("--assets-dir", help="assets 目录路径")
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    
    args = parser.parse_args()
    
    # FAIL-CLOSED: 无构建输入必须不返回 PASS
    if not args.apk and not args.ipa and not args.pubspec:
        results = {"test_case":"NS-07","status":"SKIPPED","findings":[{"note":"缺少 --apk/--ipa/--pubspec 输入","severity":"SKIPPED"}],"reason":"Fail-Closed: 无输入 → SKIPPED → BLOCK"}
        if args.output_json:
            with open(args.output_json, 'w', encoding='utf-8') as f: json.dump(results, f, indent=2)
        print("NS-07 SKIPPED — 无构建输入（Fail-Closed → BLOCK）")
        sys.exit(1)
    
    results = {
        "test_case": "NS-07-mock-data-removal",
        "test_name": "移除生产包 mock 数据",
        "status": "PASS",
        "findings": [],
        "details": {}
    }
    
    # Mock 检测模式
    mock_patterns = [
        # 文件路径级精确匹配：避免泛匹配第三方 SDK 字符串
        r'mock_[^/]+\.json$|mock_[^/]+\.json',
        r'fixture_[^/]+\.json$|fixture_[^/]+\.json',
        r'dummy_[^/]+\.json$|dummy_[^/]+\.json',
        r'test_announcement[^/]*\.json$',
        r'fake_[^/]+\.json$',
        r'mock_server',
        r'internal_test_data',
        r'debug_test',
        r'test_api_[^/]*\.json$',
        r'fake_response_[^/]*\.json$'
    ]
    
    # 1. 检查 APK 资源
    if args.apk:
        apk_path = Path(args.apk)
        if apk_path.exists():
            apk_result = scan_apk_resources(apk_path, mock_patterns)
            results["findings"].extend(apk_result["findings"])
            results["details"]["apk_analysis"] = apk_result["details"]
    
    # 2. 检查 Dart 代码
    if args.dart_lib:
        dart_lib = Path(args.dart_lib)
        if dart_lib.exists():
            dart_files = list(dart_lib.rglob("*.dart"))
            dart_result = scan_dart_code(dart_files, mock_patterns)
            results["findings"].extend(dart_result["findings"])
            results["details"]["dart_analysis"] = dart_result["details"]
    
    # 3. 检查 pubspec.yaml
    if args.pubspec:
        pubspec_path = Path(args.pubspec)
        pubspec_result = check_pubspec_for_mock(pubspec_path)
        results["findings"].extend([{
            "type": f"mock_dependency_{dep}",
            "value": dep,
            "severity": "MEDIUM"
        } for dep in pubspec_result.get("mock_dependencies", [])])
        results["details"]["pubspec_analysis"] = pubspec_result
    
    # 4. 检查 assets 目录
    if args.assets_dir:
        assets_path = Path(args.assets_dir)
        if assets_path.exists():
            for asset_file in assets_path.rglob("*"):
                if asset_file.is_file():
                    content = asset_file.read_text(encoding='utf-8', errors='ignore')
                    for pattern in mock_patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            results["findings"].append({
                                "type": "mock_content_in_asset",
                                "file": str(asset_file),
                                "pattern": pattern,
                                "severity": "HIGH"
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
        print(f"  - [{finding['type']}] {finding.get('file', finding.get('value', ''))}")
    
    sys.exit(0 if results["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()