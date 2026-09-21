#!/usr/bin/env python3
"""
检查 iOS 文件共享（Negative Security Test）
检查 UIFileSharingEnabled 是否为 NO，以及是否存在通过 Finder/iTunes 等渠道直接读取 Documents 的风险
"""

import argparse
import json
import plistlib
import re
import subprocess
import sys
from pathlib import Path

def parse_info_plist(info_plist_path):
    """解析 Info.plist 文件"""
    result = {
        "file_path": str(info_plist_path),
        "parsing_error": None,
        "data": {}
    }
    
    try:
        with open(info_plist_path, 'rb') as f:
            result["data"] = plistlib.load(f)
    except Exception as e:
        result["parsing_error"] = str(e)
    
    return result

def check_file_sharing_settings(plist_data):
    """检查文件共享相关设置"""
    result = {
        "test_case": "NS-06-ios-file-sharing",
        "test_name": "关闭 iOS Documents 文件共享",
        "status": "PASS",
        "findings": [],
        "details": {}
    }
    
    # 检查 UIFileSharingEnabled
    ui_file_sharing = plist_data.get("UIFileSharingEnabled")
    if ui_file_sharing is None:
        # 默认应该是 NO，但如果没有设置也需要检查子域名访问
        result["details"]["UIFileSharingEnabled"] = "NOT_SET"
    elif ui_file_sharing:
        result["findings"].append({
            "type": "insecure_file_sharing_enabled",
            "value": "YES",
            "severity": "HIGH",
            "location": "Info.plist",
            "description": "UIFileSharingEnabled = YES，允许通过 Finder/iTunes 访问应用 Document 文件"
        })
        result["details"]["UIFileSharingEnabled"] = "YES"
    else:
        result["details"]["UIFileSharingEnabled"] = "NO"
    
    # 检查 CFBundleURLTypes 配置
    url_types = plist_data.get("CFBundleURLTypes", [])
    if url_types:
        result["details"]["CFBundleURLTypes_count"] = len(url_types)
        
        for i, url_type in enumerate(url_types):
            schemes = url_type.get("CFBundleURLSchemes", [])
            for scheme in schemes:
                # 检查是否允许测试/开发方案
                if scheme.endswith(".test") or scheme.endswith(".dev") or \
                   scheme.endswith("-test") or scheme.endswith("-dev"):
                    result["findings"].append({
                        "type": "insecure_url_scheme",
                        "value": scheme,
                        "severity": "MEDIUM",
                        "location": f"CFBundleURLTypes[{i}].CFBundleURLSchemes",
                        "description": f"可能允许意外的 URL 方案：{scheme}"
                    })
    
    # 检查 Document 目录权限
    doc_types = plist_data.get("CFBundleDocumentTypes", [])
    if doc_types:
        result["details"]["CFBundleDocumentTypes_count"] = len(doc_types)
        for doc_type in doc_types:
            if doc_type.get("LSAllowWhiteListedDocuments", False):
                result["findings"].append({
                    "type": "document_white_list_allowed",
                    "value": "LSAllowWhiteListedDocuments = YES",
                    "severity": "MEDIUM",
                    "location": f"CFBundleDocumentTypes 条目",
                    "description": "允许白名单文档，可能存在安全风险"
                })
    
    # 检查数据保护策略
    if "NSFileProtection" in plist_data:
        protection_level = plist_data["NSFileProtection"]
        if protection_level != "NSFileProtectionComplete":
            result["findings"].append({
                "type": "insufficient_file_protection",
                "value": protection_level,
                "severity": "MEDIUM",
                "location": "NSFileProtection",
                "description": "文件保护级别不足，可能导致 Document 内容被泄露"
            })
    
    # 检查是否允许备份
    if plist_data.get("NSBackupUseEncryption", False) is False:
        result["findings"].append({
            "type": "backup_encryption_disabled",
            "value": "NSBackupUseEncryption = NO",
            "severity": "MEDIUM",
            "location": "Info.plist",
            "description": "禁用备份加密，可能导致 Document 内容在备份中暴露"
        })
    
    # 判断结果
    if result["findings"]:
        result["status"] = "FAIL"
        result["details"]["total_findings"] = len(result["findings"])
    
    return result

def analyze_ipa_contents(ipa_path, artifacts_dir):
    """分析 IPA 文件内容"""
    result = {
        "ipa_path": str(ipa_path),
        "analysis_complete": False,
        "findings": [],
        "details": {}
    }
    
    try:
        # 解压 IPA 文件
        output_dir = Path(artifacts_dir) / "ipa_analysis"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        subprocess.run([
            "unzip", "-q", str(ipa_path), "-d", str(output_dir)
        ], check=True, capture_output=True)
        
        # 检查 Document 目录
        doc_dir = output_dir / "Payload" / "*.app" / "Documents"
        for doc_path in doc_dir.rglob("*"):
            if doc_path.is_file():
                # 检查文件权限
                file_stat = doc_path.stat()
                
                # 检查文件是否可读
                if (file_stat.st_mode & 0o004):  # 其他用户可读
                    # 检查文件是否可能包含敏感数据
                    file_content = doc_path.read_bytes()[:1024]  # 只读取前 1KB
                    
                    # 简单的 token/密码检查
                    if b'token' in file_content.lower() or b'password' in file_content.lower():
                        result["findings"].append({
                            "type": "sensitive_file_in_documents",
                            "value": str(doc_path.relative_to(output_dir)),
                            "severity": "HIGH",
                            "description": "Documents 目录包含可能的敏感信息"
                        })
        
        # 检查 Info.plist
        info_plist = output_dir / "Payload" / "*.app" / "Info.plist"
        for plist_file in info_plist.rglob("*"):
            if plist_file.is_file():
                plist_result = parse_info_plist(plist_file)
                if plist_result.get("parsing_error"):
                    result["findings"].append({
                        "type": "plist_parse_error",
                        "value": plist_result["parsing_error"],
                        "severity": "LOW"
                    })
                else:
                    plist_analysis = check_file_sharing_settings(plist_result["data"])
                    result["findings"].extend(plist_analysis["findings"])
        
        result["analysis_complete"] = True
        result["details"]["files_found"] = len(list(doc_dir.rglob("*")))
    
    except Exception as e:
        result["error"] = str(e)
        result["findings"].append({
            "type": "analysis_error",
            "value": str(e),
            "severity": "HIGH"
        })
    
    return result

def main():
    parser = argparse.ArgumentParser(description="检查 iOS 文件共享（反向安全测试）")
    parser.add_argument("--info-plist", required=True, help="Info.plist 文件路径")
    parser.add_argument("--ipa", help="IPA 文件路径（可选，用于内容分析）")
    parser.add_argument("--artifacts-dir", default="results/artifacts", help="输出目录")
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    
    args = parser.parse_args()
    
    results = {
        "test_case": "NS-06-ios-file-sharing",
        "test_name": "关闭 iOS Documents 文件共享",
        "status": "PASS",
        "findings": [],
        "details": {}
    }
    
    # 1. 检查 Info.plist
    info_plist_path = Path(args.info_plist)
    if info_plist_path.exists():
        plist_result = parse_info_plist(info_plist_path)
        
        if plist_result.get("parsing_error"):
            results["findings"].append({
                "type": "plist_parse_error",
                "value": plist_result["parsing_error"],
                "severity": "HIGH"
            })
        else:
            plist_analysis = check_file_sharing_settings(plist_result["data"])
            results["findings"].extend(plist_analysis["findings"])
            results["details"]["info_plist_analysis"] = plist_analysis["details"]
    
    # 2. 分析 IPA 内容
    if args.ipa:
        ipa_path = Path(args.ipa)
        if ipa_path.exists():
            ipa_result = analyze_ipa_contents(ipa_path, args.artifacts_dir)
            results["findings"].extend(ipa_result.get("findings", []))
            results["details"]["ipa_analysis"] = ipa_result["details"]
    
    # 3. 检查构建产物中的所有 .plist 文件
    artifacts_dir = Path(args.artifacts_dir)
    if artifacts_dir.exists():
        for plist_file in artifacts_dir.rglob("*.plist"):
            if plist_file.is_file():
                plist_result = parse_info_plist(plist_file)
                if plist_result.get("parsing_error"):
                    continue
                
                plist_analysis = check_file_sharing_settings(plist_result["data"])
                if plist_analysis["status"] == "FAIL":
                    # 记录每个失败的文件
                    results["findings"].append({
                        "type": "invalid_plist_in_artifacts",
                        "value": str(plist_file),
                        "severity": "MEDIUM",
                        "details": plist_analysis["findings"]
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
        print(f"  - [{finding['type']}] {finding.get('value', '')}")
    
    sys.exit(0 if results["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()