#!/usr/bin/env python3
"""
检查加密存储（Negative Security Test）
检查旧版存储格式（Hive、HydratedBloc、SharedPreferences）中是否存在明文 Token
"""

import argparse
import json
import re
import struct
import sys
from pathlib import Path

def scan_hive_files(file_path):
    """扫描 Hive 文件（旧版存储格式）"""
    results = {
        "file": str(file_path),
        "findings": [],
        "token_found": False,
        "format": None
    }
    
    try:
        content = file_path.read_bytes()
        
        # Hive 文件头检查
        if content.startswith(b'Hive'):
            results["format"] = "HIVE"
            # 简单的文本扫描
            text_content = content.decode('utf-8', errors='ignore')
            
            # 检查可能的 token/字符串
            token_patterns = [
                r'token["\']?\s*:\s*["\'][^"\']+["\']',
                r'auth[_\s]*token["\']?\s*:\s*["\'][^"\']+["\']',
                r'["\']token["\'][^\s:]*[\"\']\s*:',
                r'\b[A-Za-z0-9+/=]{20,}\b'  # Base64-like token
            ]
            
            for pattern in token_patterns:
                for match in re.finditer(pattern, text_content, re.IGNORECASE):
                    token_value = match.group(0)
                    if not any(skip in token_value.lower() for skip in ['debug', 'test', 'example']):
                        results["findings"].append({
                            "type": "potential_token",
                            "value": token_value[:100],
                            "line": file_path.name,
                            "format": "HIVE"
                        })
                        if 'token' in token_value.lower():
                            results["token_found"] = True
        
        # 检查是否为加密的 Hive 文件（通过 check') 加密验证)
        elif len(content) > 10 and content[4:9] == b'check':
            results["format"] = "HIVE_ENCRYPTED"
    
    except Exception as e:
        results["error"] = str(e)
    
    return results

def scan_hive_plugin_file(file_path):
    """扫描 Flutter Hive 插件的文件"""
    results = {
        "file": str(file_path),
        "format": None,
        "encryption_status": "UNKNOWN",
        "findings": []
    }
    
    try:
        # 检查是否为加密的 Hive 数据库文件
        # Hive 数据库文件的头通常是特定的字节序列
        with open(file_path, 'rb') as f:
            header = f.read(12)
        
        # Hive 数据库文件头检查（第 5-7 字节为特定序列）
        if len(header) >= 7 and header[4:7] == b'ch\x00':
            results["format"] = "HIVE_DATABASE"
            results["encryption_status"] = "ENCRYPTED"
        
        # 检查是否存在明文备份或未加密的 Hive 文件
        if len(header) > 0 and header[0:4] == b'Hive':
            results["format"] = "HIVE_TEXT_BACKUP"
            results["encryption_status"] = "PLAINTEXT"
            
            # 扫描可能的 token
            content = file_path.read_bytes().decode('utf-8', errors='ignore')
            
            # 查找可能的 token 字符串
            import re
            token_matches = re.findall(r'token["\']?\s*:\s*["\'][^"\']{20,}["\']', content, re.IGNORECASE)
            for token in token_matches:
                results["findings"].append({
                    "type": "plaintext_token",
                    "value": token[:100],
                    "location": file_path.name
                })
    
    except Exception as e:
        results["error"] = str(e)
    
    return results

def scan_shared_preferences(artifacts_dir, package_name):
    """扫描 SharedPreferences 文件（Android）"""
    results = {
        "findings": [],
        "encrypted_prefs_found": False,
        "plaintext_prefs_found": False
    }
    
    try:
        # 解包 APK 获取 SharedPreferences 文件
        import subprocess
        output_dir = Path(artifacts_dir) / "sp_files"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用 apktool 解包
        if (Path(artifacts_dir).parent / "app-release.apk").exists():
            apk_path = Path(artifacts_dir).parent / "app-release.apk"
            subprocess.run([
                "apktool", "d", str(apk_path), "-o", str(output_dir)
            ], check=True, capture_output=True)
        
        # 查找 SharedPreferences 文件
        for sp_file in output_dir.rglob("*.xml"):
            if "shared_prefs" in str(sp_file).lower():
                content = sp_file.read_text(errors='ignore')
                
                # 检查明文 token
                if re.search(r'token["\']?\s*:\s*["\'][^"\']+["\']', content, re.IGNORECASE):
                    results["plaintext_prefs_found"] = True
                    results["findings"].append({
                        "type": "plaintext_token_in_sp",
                        "file": str(sp_file),
                        "severity": "HIGH"
                    })
                
                # 检查是否有加密标识
                if "encrypted" in content.lower():
                    results["encrypted_prefs_found"] = True
    
    except Exception as e:
        results["error"] = str(e)
    
    return results

def scan_keychain_usage(file_path, package_name):
    """检查 Keychain 使用情况（iOS）"""
    results = {
        "findings": [],
        "secure_storage_found": False,
        "insecure_storage_found": False
    }
    
    try:
        # 解包 IPA
        import subprocess
        output_dir = Path(file_path).parent / "ipa_contents"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        subprocess.run([
            "unzip", "-q", str(file_path), "-d", str(output_dir)
        ], check=True, capture_output=True)
        
        # 查找 Info.plist 或 entitlements 文件
        for plist_file in output_dir.rglob("Info.plist"):
            # 解析 plist
            import plistlib
            with open(plist_file, 'rb') as f:
                plist_data = plistlib.load(f)
            
            # 检查 Keychain 使用策略
            if "NSKeychainAccessGroup" in plist_data:
                results["secure_storage_found"] = True
            
            # 检查文件共享设置
            if plist_data.get("UIFileSharingEnabled", False):
                results["insecure_storage_found"] = True
                results["findings"].append({
                    "type": "insecure_file_sharing",
                    "file": str(plist_file),
                    "setting": "UIFileSharingEnabled = YES"
                })
    
    except Exception as e:
        results["error"] = str(e)
    
    return results

def main():
    parser = argparse.ArgumentParser(description="检查加密存储（反向安全测试）")
    parser.add_argument("--hive-files", nargs="*", help="Hive 文件路径列表")
    parser.add_argument("--apk", help="APK 文件路径（用于 SharedPreferences 检查）")
    parser.add_argument("--ipa", help="IPA 文件路径（用于 Keychain 检查）")
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    
    args = parser.parse_args()
    
    # FAIL-CLOSED: 无构建输入必须不返回 PASS
    if not args.apk and not args.ipa and not args.hive_files:
        results = {"test_case":"NS-05","status":"SKIPPED","findings":[{"note":"缺少 --apk/--ipa/--hive-files 输入","severity":"SKIPPED"}],"reason":"Fail-Closed: 无输入 → SKIPPED → BLOCK"}
        if args.output_json:
            with open(args.output_json, 'w', encoding='utf-8') as f: json.dump(results, f, indent=2)
        print("NS-05 SKIPPED — 无构建输入（Fail-Closed → BLOCK）")
        sys.exit(1)
    
    results = {
        "test_case": "NS-05-encryption-storage",
        "test_name": "登录态迁移至 Keychain/加密存储",
        "status": "PASS",
        "findings": [],
        "details": {}
    }
    
    # 1. 检查 Hive 文件
    if args.hive_files:
        for hive_file in args.hive_files:
            hive_path = Path(hive_file)
            if hive_path.exists():
                hive_result = scan_hive_files(hive_path)
                if hive_result.get("token_found"):
                    results["findings"].append({
                        "type": "plaintext_token_in_hive",
                        "file": hive_result["file"],
                        "severity": "HIGH",
                        "format": hive_result.get("format")
                    })
                results["details"]["hive_files"] = results.get("details", {}).get("hive_files", [])
    
    # 2. 检查 Hive 插件文件
    hive_plugin_files = Path("./").rglob("*.hive")
    for hive_plugin in hive_plugin_files:
        if hive_plugin.is_file():
            plugin_result = scan_hive_plugin_file(hive_plugin)
            if plugin_result.get("findings"):
                results["findings"].extend(plugin_result["findings"])
            
            # 检查加密状态
            if plugin_result.get("encryption_status") == "PLAINTEXT":
                results["details"]["plaintext_hive_found"] = True
            elif plugin_result.get("encryption_status") == "ENCRYPTED":
                results["details"]["encrypted_hive_found"] = True
    
    # 3. 检查 SharedPreferences
    if args.apk:
        sp_result = scan_shared_preferences(Path(args.apk).parent, "com.target_app")
        if sp_result.get("findings"):
            results["findings"].extend(sp_result["findings"])
        results["details"]["shared_prefs"] = sp_result
    
    # 4. 检查 iOS Keychain
    if args.ipa:
        keychain_result = scan_keychain_usage(Path(args.ipa), "com.target_app")
        if keychain_result.get("findings"):
            results["findings"].extend(keychain_result["findings"])
        results["details"]["keychain"] = keychain_result
    
    # 5. 检查 Flutter 应用中的日志文件
    # 检查日志文件
    log_files = Path("logs").rglob("*.log")
    for log_file in log_files:
        if log_file.is_file():
            log_content = log_file.read_text(errors='ignore')
            if re.search(r'token["\']?\s*:\s*["\'][^"\']{20,}["\']', log_content, re.IGNORECASE):
                results["findings"].append({
                    "type": "token_in_log",
                    "file": str(log_file),
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
        print(f"  - [{finding['type']}] {finding['severity'] if 'severity' in finding else ''}: {finding['file']}")
    
    sys.exit(0 if results["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()
# Dynamic test requires device / runtime environment; without it result = SKIPPED (not PASS)
# Per Fail-Closed design: SKIPPED -> BLOCK release (not ALLOW)

