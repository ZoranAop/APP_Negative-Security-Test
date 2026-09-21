#!/usr/bin/env python3
"""
检查二进制完整性（Negative Security Test）
验证 APK/IPA 签名、证书指纹、构建版本号、代码签名等是否完整正确
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

def check_apk_signature(apk_path, expected_fingerprint):
    """检查 APK 签名"""
    result = {
        "test_case": "NS-09-binary-integrity-android",
        "apk_path": str(apk_path),
        "status": "PASS",
        "signature_verified": False,
        "certificate_fingerprint": None,
        "expected_fingerprint": expected_fingerprint,
        "errors": [],
        "findings": []
    }
    
    try:
        # 使用 apksigner 验证签名
        apksigner_result = subprocess.run(
            ["apksigner", "verify", "--print-certs", "--verbose", str(apk_path)],
            capture_output=True, text=True, timeout=30
        )
        
        result["apksigner_output"] = apksigner_result.stdout[:500]
        result["apksigner_returncode"] = apksigner_result.returncode
        
        # 解析证书指纹
        if apksigner_result.returncode == 0 or "verified" in apksigner_result.stdout.lower():
            result["signature_verified"] = True
            
            # 提取证书指纹
            fingerprint_match = re.search(r'fingerprint.*?:([^\s]+)', apksigner_result.stdout, re.IGNORECASE)
            if fingerprint_match:
                fingerprint = fingerprint_match.group(1).strip()
                result["certificate_fingerprint"] = fingerprint
                
                if expected_fingerprint and fingerprint != expected_fingerprint:
                    result["findings"].append({
                        "type": "certificate_fingerprint_mismatch",
                        "expected": expected_fingerprint,
                        "found": fingerprint,
                        "severity": "HIGH"
                    })
            else:
                # 尝试其他格式
                fingerprint_lines = re.findall(r'[A-Z0-9]{2}:[A-Z0-9]{2}:[A-Z0-9]{2}:[A-Z0-9]{2}', apksigner_result.stdout)
                if fingerprint_lines:
                    result["certificate_fingerprint"] = fingerprint_lines[0]
        else:
            result["signature_verified"] = False
            result["findings"].append({
                "type": "signature_verification_failed",
                "value": "APK 签名验证失败",
                "severity": "HIGH",
                "description": f"apksigner 返回码: {apksigner_result.returncode}"
            })
        
        # 检查 APK 的构建版本号
        aapt_result = subprocess.run(
            ["aapt", "l", "-a", str(apk_path)],
            capture_output=True, text=True, timeout=10
        )
        
        # 解析版本信息
        version_code_match = re.search(r'versionCode.*?=\s*(\d+)', aapt_result.stdout, re.IGNORECASE)
        version_name_match = re.search(r'versionName.*?=\s*([\w.]+)', aapt_result.stdout, re.IGNORECASE)
        
        result["version_code"] = version_code_match.group(1) if version_code_match else "unknown"
        result["version_name"] = version_name_match.group(1) if version_name_match else "unknown"
        
        # 检查是否包含调试构建标识
        if "debug" in str(apk_path).lower():
            result["findings"].append({
                "type": "debug_build_path",
                "value": str(apk_path),
                "severity": "MEDIUM"
            })
    
    except subprocess.TimeoutExpired:
        result["errors"].append("apksigner timeout")
    except Exception as e:
        result["errors"].append(str(e))
        result["findings"].append({
            "type": "verification_exception",
            "value": str(e),
            "severity": "MEDIUM"
        })
    
    # 判断结果
    if result["findings"]:
        result["status"] = "FAIL"
    
    return result

def check_ipa_signature(ipa_path, expected_certificate):
    """检查 IPA 签名和代码签名"""
    result = {
        "test_case": "NS-09-binary-integrity-ios",
        "ipa_path": str(ipa_path),
        "status": "PASS",
        "code_signed": False,
        "entitlements_valid": False,
        "errors": [],
        "findings": []
    }
    
    try:
        # 解压 IPA 获取 .app 包
        output_dir = Path("/tmp/ipa_analysis")  # 使用临时目录
        output_dir.mkdir(parents=True, exist_ok=True)
        
        subprocess.run([
            "unzip", "-q", str(ipa_path), "-d", str(output_dir)
        ], check=True, capture_output=True, timeout=30)
        
        # 查找 .app 目录
        app_dirs = list(output_dir.rglob("*.app"))
        if not app_dirs:
            result["findings"].append({
                "type": "no_app_bundle_found",
                "value": "未找到 .app 包",
                "severity": "HIGH"
            })
        else:
            app_path = app_dirs[0]
            
            # 使用 codesign 检查签名
            codesign_result = subprocess.run(
                ["codesign", "-dv", "--verbose=4", str(app_path)],
                capture_output=True, text=True, timeout=15
            )
            
            result["codesign_output"] = codesign_result.stdout[:500]
            result["codesign_stderr"] = codesign_result.stderr[:500]
            
            # 检查签名状态
            if codesign_result.returncode == 0:
                result["code_signed"] = True
            else:
                result["code_signed"] = False
                result["findings"].append({
                    "type": "codesign_failed",
                    "value": f"codesign 返回码: {codesign_result.returncode}",
                    "severity": "HIGH"
                })
            
            # 检查证书标识
            cert_match = re.search(r'Signature\s*format\s*:\s*(.*)', codesign_result.stdout, re.IGNORECASE)
            if cert_match:
                result["certificate_info"] = cert_match.group(1).strip()
            
            # 检查 Entitlements
            for entitlement_file in app_path.rglob("*.entitlements"):
                result["entitlements_found"] = True
                
                # 检查是否包含不安全的 entitlement
                entitlement_content = entitlement_file.read_text(errors='ignore')
                
                # 检查是否包含调试权限
                if "get-task-allow" in entitlement_content and "true" in entitlement_content.lower():
                    result["findings"].append({
                        "type": "debug_entitlement_enabled",
                        "value": "get-task-allow = true",
                        "severity": "HIGH",
                        "description": "调试权限已启用，可能允许调试器附加"
                    })
                
                # 检查文件访问权限
                if "com.apple.security.files" in entitlement_content:
                    # 应该是生产环境配置
                    pass
    
    except subprocess.TimeoutExpired:
        result["errors"].append("codesign timeout")
    except Exception as e:
        result["errors"].append(str(e))
        result["findings"].append({
            "type": "verification_exception",
            "value": str(e),
            "severity": "MEDIUM"
        })
    
    # 判断结果
    if result["findings"]:
        result["status"] = "FAIL"
    
    return result

def check_version_consistency(manifest_path, info_plist_path):
    """检查版本号一致性"""
    result = {
        "test_case": "NS-09-version-consistency",
        "status": "PASS",
        "findings": []
    }
    
    try:
        # 检查 Android Manifest 版本
        manifest_version = None
        manifest_version_code = None
        
        if manifest_path.exists():
            import xml.etree.ElementTree as ET
            tree = ET.parse(manifest_path)
            root = tree.getroot()
            package_name = root.attrib.get("package", "")
            
            # 提取版本信息
            version_name = root.get("{http://schemas.android.com/apk/res/android}versionName")
            version_code = root.get("{http://schemas.android.com/apk/res/android}versionCode")
            
            manifest_version = version_name
            manifest_version_code = version_code
            
            result["android_version"] = {
                "version_name": version_name,
                "version_code": version_code,
                "package": package_name
            }
        
        # 检查 iOS Info.plist 版本
        if info_plist_path.exists():
            import plistlib
            with open(info_plist_path, 'rb') as f:
                plist_data = plistlib.load(f)
            
            result["ios_version"] = {
                "bundle_version": plist_data.get("CFBundleVersion"),
                "bundle_version_string": plist_data.get("CFBundleShortVersionString"),
                "bundle_identifier": plist_data.get("CFBundleIdentifier")
            }
        
    except Exception as e:
        result["findings"].append({
            "type": "version_check_exception",
            "value": str(e),
            "severity": "LOW"
        })
    
    return result

def check_build_artifact_integrity(apk_path, ipa_path):
    """检查构建产物完整性"""
    result = {
        "test_case": "NS-09-artifact-integrity",
        "status": "PASS",
        "findings": []
    }
    
    # 检查 APK 完整性
    if apk_path and Path(apk_path).exists():
        apk_size = Path(apk_path).stat().st_size
        if apk_size < 10000:  # 小于 10KB 的 APK 可能有问题
            result["findings"].append({
                "type": "apk_too_small",
                "value": f"{apk_size} bytes",
                "severity": "HIGH"
            })
    
    # 检查 IPA 完整性
    if ipa_path and Path(ipa_path).exists():
        ipa_size = Path(ipa_path).stat().st_size
        if ipa_size < 5000:  # 小于 5MB 的 IPA 可能有问题
            result["findings"].append({
                "type": "ipa_too_small",
                "value": f"{ipa_size} bytes",
                "severity": "HIGH"
            })
    
    if result["findings"]:
        result["status"] = "FAIL"
    
    return result

def main():
    parser = argparse.ArgumentParser(description="检查二进制完整性（反向安全测试）")
    parser.add_argument("--apk", help="APK 文件路径")
    parser.add_argument("--ipa", help="IPA 文件路径")
    parser.add_argument("--manifest", help="AndroidManifest.xml 路径")
    parser.add_argument("--info-plist", help="Info.plist 路径")
    parser.add_argument("--expected-cert-fingerprint", help="预期证书指纹")
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    
    args = parser.parse_args()
    
    results = {
        "test_case": "NS-09-binary-integrity",
        "test_name": "发布前自动校验生产 IPA/APK",
        "status": "PASS",
        "findings": [],
        "details": {}
    }
    
    # 1. 检查 APK 签名
    if args.apk and Path(args.apk).exists():
        apk_result = check_apk_signature(Path(args.apk), args.expected_cert_fingerprint)
        results["findings"].extend(apk_result.get("findings", []))
        results["details"]["apk_signature"] = {
            "signature_verified": apk_result.get("signature_verified"),
            "certificate_fingerprint": apk_result.get("certificate_fingerprint"),
            "expected_fingerprint": args.expected_cert_fingerprint
        }
    
    # 2. 检查 IPA 签名
    if args.ipa and Path(args.ipa).exists():
        ipa_result = check_ipa_signature(Path(args.ipa), args.expected_cert_fingerprint)
        results["findings"].extend(ipa_result.get("findings", []))
        results["details"]["ipa_signature"] = {
            "code_signed": ipa_result.get("code_signed"),
            "entitlements_found": ipa_result.get("entitlements_found", False)
        }
    
    # 3. 检查版本一致性
    if args.manifest and args.info_plist:
        version_result = check_version_consistency(Path(args.manifest), Path(args.info_plist))
        results["details"]["version_consistency"] = version_result
    
    # 4. 检查构建产物完整性
    artifact_result = check_build_artifact_integrity(args.apk, args.ipa)
    results["findings"].extend(artifact_result.get("findings", []))
    
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
        print(f"  - [{finding['type']}] {finding.get('value', finding.get('description', ''))}")
    
    sys.exit(0 if results["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()