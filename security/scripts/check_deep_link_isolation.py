#!/usr/bin/env python3
"""
检查 Android 深链域名隔离（Negative Security Test）
检查 AndroidManifest.xml 中的 intent-filter 是否只包含生产域名
"""

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

def parse_manifest(manifest_path):
    """解析 AndroidManifest.xml 中的 deep link 配置"""
    result = {
        "intent_filters": [],
        "errors": []
    }
    
    try:
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        package_name = root.attrib.get("package")
        result["package_name"] = package_name
        
        # 遍历所有 activity 的 intent-filter
        for activity in root.iter("activity"):
            activity_name = activity.attrib.get("android:name")
            for intent_filter in activity.findall("intent-filter"):
                actions = []
                data_elements = []
                
                for action in intent_filter.findall("action"):
                    actions.append(action.attrib.get("android:name"))
                
                for data in intent_filter.findall("data"):
                    data_elements.append({
                        "scheme": data.attrib.get("android:scheme"),
                        "host": data.attrib.get("android:host"),
                        "path": data.attrib.get("android:path"),
                        "package": data.attrib.get("android:package")
                    })
                
                if "android.intent.action.VIEW" in actions:
                    result["intent_filters"].append({
                        "activity": activity_name,
                        "actions": actions,
                        "data": data_elements
                    })
    
    except Exception as e:
        result["errors"].append(str(e))
    
    return result

def check_deep_link_config(manifest_path, production_hosts):
    """检查深链配置是否符合生产白名单"""
    result = {
        "test_case": "NS-03-android-deep-link-isolation",
        "test_name": "Android 深链域名按构建环境隔离",
        "status": "PASS",
        "findings": [],
        "details": {}
    }
    
    manifest_data = parse_manifest(manifest_path)
    result["details"]["manifest_package"] = manifest_data.get("package_name")
    result["details"]["intent_filters"] = manifest_data.get("intent_filters", [])
    
    if manifest_data.get("errors"):
        result["findings"].append({
            "type": "manifest_parse_error",
            "value": manifest_data["errors"][0]
        })
    
    # 1. 检查每个 intent-filter 的 host
    for intent_filter in manifest_data.get("intent_filters", []):
        for data in intent_filter.get("data", []):
            host = data.get("host")
            if not host:
                continue
            
            # 检查是否为非生产域名
            if host not in production_hosts:
                # 检查是否包含测试/开发模式
                if re.search(r"(test|dev|staging|local)", host, re.IGNORECASE):
                    result["findings"].append({
                        "type": "development_host_in_intent_filter",
                        "value": host,
                        "activity": intent_filter.get("activity"),
                        "location": "AndroidManifest.xml"
                    })
            
            # 检查是否包含通配符（生产环境不应允许）
            if host == "*":
                result["findings"].append({
                    "type": "wildcard_host_in_intent_filter",
                    "value": host,
                    "activity": intent_filter.get("activity")
                })
            
            # 检查是否包含非生产端口
            if ":" in host:
                result["findings"].append({
                    "type": "non_production_port_in_host",
                    "value": host,
                    "activity": intent_filter.get("activity")
                })
    
    # 2. 检查 scheme 白名单
    for intent_filter in manifest_data.get("intent_filters", []):
        for data in intent_filter.get("data", []):
            scheme = data.get("scheme")
            if scheme and not scheme.startswith(("com.", "org.")):
                # 自定义 scheme 应该是 app 的包名形式
                if not scheme.startswith(("myapp", "target_app")):
                    result["findings"].append({
                        "type": "unexpected_scheme",
                        "value": scheme,
                        "activity": intent_filter.get("activity")
                    })
    
    # 3. 检查 package 限定
    for intent_filter in manifest_data.get("intent_filters", []):
        for data in intent_filter.get("data", []):
            package = data.get("package")
            if package and package != manifest_data.get("package_name"):
                result["findings"].append({
                    "type": "package_mismatch_in_intent_filter",
                    "value": package,
                    "expected": manifest_data.get("package_name"),
                    "activity": intent_filter.get("activity")
                })
    
    # 判断结果
    if result["findings"]:
        result["status"] = "FAIL"
        result["details"]["total_findings"] = len(result["findings"])
    
    return result

def main():
    parser = argparse.ArgumentParser(description="检查 Android 深链域名隔离（反向安全测试）")
    parser.add_argument("--manifest", required=True, help="AndroidManifest.xml 路径")
    parser.add_argument("--production-hosts", nargs="*", default=["api.target_app.com", "feed-api.target_app.com", "auth.target_app.com"])
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    
    args = parser.parse_args()
    
    results = check_deep_link_config(args.manifest, args.production_hosts)
    
    if args.output_json:
        with open(args.output_json, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"测试结果: {results['status']}")
    print(f"发现 {len(results['findings'])} 个问题:")
    for finding in results["findings"]:
        print(f"  - [{finding['type']}] {finding['value']}")
    
    sys.exit(0 if results["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()
# Dynamic test requires device / runtime environment; without it result = SKIPPED (not PASS)
# Per Fail-Closed design: SKIPPED -> BLOCK release (not ALLOW)

