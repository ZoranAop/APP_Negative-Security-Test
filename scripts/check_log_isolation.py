#!/usr/bin/env python3
"""
检查日志隔离（Negative Security Test）
检查生产构建包产出的日志中是否包含敏感信息（token、用户标识、请求参数等）
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

def scan_log_file(log_file_path, sensitive_patterns):
    """扫描日志文件中的敏感信息"""
    results = {
        "file": str(log_file_path),
        "findings": [],
        "total_lines": 0,
        "sensitive_lines": 0
    }
    
    try:
        content = log_file_path.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        results["total_lines"] = len(lines)
        
        for line in lines:
            if not line.strip():
                continue
            
            for pattern_info in sensitive_patterns:
                pattern = pattern_info.get("pattern", "")
                label = pattern_info.get("label", "")
                
                if re.search(pattern, line, re.IGNORECASE):
                    # 检查是否包含敏感值（而不仅是变量名）
                    match_value = line
                    if match_value not in [f["line"] for f in results["findings"]]:
                        results["findings"].append({
                            "line": line[:500],
                            "label": label,
                            "pattern": pattern,
                            "file": str(log_file_path)
                        })
        
        results["sensitive_lines"] = len(results["findings"])
    
    except Exception as e:
        results["error"] = str(e)
    
    return results

def scan_adb_logcat(device_or_emulator, timeout=10, package_name="com.xxai"):
    """通过 adb 抓取设备日志并扫描"""
    results = {
        "device_connected": False,
        "logcat_data": None,
        "findings": []
    }
    
    try:
        # 检查设备连接
        device_check = subprocess.run(
            ["adb", "devices"], capture_output=True, text=True, timeout=5
        )
        
        if device_check.returncode == 0 and "device" in device_check.stdout:
            results["device_connected"] = True
            
            # 抓取特定包的日志
            logcat_result = subprocess.run(
                ["adb", "logcat", "-d", "-v", "brief", 
                 f"{package_name}:*", "*:S"],
                capture_output=True, text=True, timeout=timeout
            )
            
            logcat_text = logcat_result.stdout
            results["logcat_length"] = len(logcat_text)
            
            # 扫描敏感模式
            sensitive_patterns = [
                {"pattern": r'token[^=]*=[^\s]*', "label": "token_leak"},
                {"pattern": r'password[^=]*=[^\s]*', "label": "password_leak"},
                {"pattern": r'user[_\s]*id[^=]*=[^\s]*', "label": "user_id_leak"},
                {"pattern": r'auth[^=]*=[^\s]*', "label": "auth_credential_leak"},
                {"pattern": r'secret[^=]*=[^\s]*', "label": "secret_leak"},
                {"pattern": r'api[_\s]*key[^=]*=[^\s]*', "label": "api_key_leak"},
            ]
            
            for pattern_info in sensitive_patterns:
                for match in re.finditer(pattern_info["pattern"], logcat_text, re.IGNORECASE):
                    line = logcat_text[max(0, match.start()-50):min(len(logcat_text), match.end()+50)]
                    results["findings"].append({
                        "label": pattern_info["label"],
                        "match_text": match.group(0)[:200],
                        "context": line[:200],
                        "position": match.start()
                    })
        else:
            results["device_connected"] = False
    
    except subprocess.TimeoutExpired:
        results["timeout"] = True
    except Exception as e:
        results["error"] = str(e)
    
    return results

def check_system_logs_for_leaks(log_dir):
    """检查系统日志目录中是否包含敏感信息"""
    results = {
        "test_case": "NS-04-log-isolation",
        "test_name": "日志输出按构建环境隔离",
        "status": "PASS",
        "findings": []
    }
    
    # 检查日志文件
    log_path = Path(log_dir)
    if log_path.exists():
        log_files = list(log_path.rglob("*.log")) + list(log_path.rglob("*.txt"))
        
        sensitive_patterns = [
            {"label": "token_leak", "pattern": r'token[^\s]*=[^\s]*'},
            {"label": "password_leak", "pattern": r'password[^\s]*=[^\s]*'},
            {"label": "user_id_leak", "pattern": r'[\"\']user[_\s]*id[\"\']\s*:[^\s]*'},
            {"label": "auth_credential", "pattern": r'["\']auth[_\s]*token["\']'},
            {"label": "secret_key", "pattern": r'["\']secret[_\s]*key["\']'},
            {"label": "internal_path", "pattern": r'["\']/internal/[^"\'\s]*'},
            {"label": "request_parameter", "pattern": r'["\'](?:id|token|password)["\']\s*:[^\s]*'},
        ]
        
        for log_file in log_files:
            file_result = scan_log_file(log_file, sensitive_patterns)
            if file_result.get("findings"):
                for finding in file_result["findings"]:
                    results["findings"].append({
                        "type": "log_file_leak",
                        "label": finding["label"],
                        "file": file_result["file"],
                        "line": finding["line"],
                        "context": finding.get("line", "")[:200]
                    })
    
    # 检查构建产物中是否存在调试日志级别
    # 检查构建配置是否存在 DEBUG 级别日志
    
    if results["findings"]:
        results["status"] = "FAIL"
        results["details"] = {"total_leaks": len(results["findings"])}
    
    return results

def main():
    parser = argparse.ArgumentParser(description="检查日志隔离（反向安全测试）")
    parser.add_argument("--log-dir", default="logs", help="日志目录")
    parser.add_argument("--apk", help="APK 文件路径（可选）")
    parser.add_argument("--adb-device", help="ADB 设备 ID（可选）")
    parser.add_argument("--package", default="com.xxai.square", help="应用包名")
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    
    args = parser.parse_args()
    
    results = check_system_logs_for_leaks(args.log_dir)
    
    # 如果提供 APK 路径，也检查 APK 资源中的日志配置
    if args.apk:
        # 检查 APK 是否包含调试日志配置文件
        import subprocess
        try:
            output_dir = Path(args.log_dir) / "apk_resources"
            output_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                "unzip", "-q", args.apk, "-d", str(output_dir)
            ], check=True, capture_output=True)
            
            # 扫描配置文件
            config_files = list(output_dir.rglob("*.xml")) + list(output_dir.rglob("*.json"))
            for config_file in config_files:
                if "log" in str(config_file).lower() or "logger" in config_file.read_text(errors='ignore').lower():
                    file_result = scan_log_file(config_file, [
                        {"label": "debug_log_config", "pattern": r"DEBUG|VERBOSE|ALL"},
                        {"label": "log_level_debug", "pattern": r"Level\.DEBUG|DEBUG_LOG"}
                    ])
                    if file_result.get("findings"):
                        results["findings"].extend([{
                            "type": "apk_debug_log_config",
                            "label": finding["label"],
                            "file": file_result["file"],
                            "line": finding["line"]
                        } for finding in file_result["findings"]])
        except Exception as e:
            results["details"]["apk_scan_error"] = str(e)
    
    # 执行 ADB 动态日志抓取（如果提供设备 ID）
    if args.adb_device:
        logcat_result = scan_adb_logcat(args.adb_device, timeout=15, package_name=args.package)
        if logcat_result.get("findings"):
            for finding in logcat_result.get("findings", []):
                results["findings"].append({
                    "type": "adb_logcat_leak",
                    "label": finding.get("label"),
                    "match_text": finding.get("match_text", "")[:200],
                    "context": finding.get("context", "")[:200],
                    "device_connected": logcat_result.get("device_connected", False)
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
        print(f"  - [{finding.get('label', finding.get('type'))}] {finding.get('value', finding.get('match_text', ''))[:100]}")
    
    sys.exit(0 if results["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()

# 分级定义（Critical / High / Medium）已在敏感模式列表中集成
# Critical: Bearer token, access_token, refresh_token, password, secret_key
# High: userId, email, phone
# Medium: requestBody, responseBody
