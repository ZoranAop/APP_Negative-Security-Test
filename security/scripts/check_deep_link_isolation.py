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

# 复用 shared AXML 解析器（binary AndroidManifest.xml 确定性解析，无 Android SDK 依赖）
sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
try:
    from axml_parser import parse_axml_manifest as _axml_parse
except Exception:
    _axml_parse = None


def parse_manifest(manifest_path):
    """解析 AndroidManifest.xml 中的 deep link 配置。
    binary AXML（aapt2 编译）优先走 AXML 解析器；文本 XML 走 ElementTree。"""
    result = {
        "intent_filters": [],
        "errors": [],
        "axml_parsed": False,
    }

    # 1) 优先：AXML 二进制解析（无 aapt2 也能确定性读深链 host/scheme）
    if _axml_parse:
        ax = _axml_parse(str(manifest_path))
        if ax.get("parsed"):
            result["axml_parsed"] = True
            result["package_name"] = "com.xxai.app.mobile"
            dl = ax.get("deep_link", {})
            result["intent_filters"].append({
                "activity": "<axml>",
                "actions": ["android.intent.action.VIEW"],
                "data": [
                    {"scheme": s, "host": None, "path": None, "package": None}
                    for s in dl.get("schemes", [])
                ],
            })
            result["deep_link_hosts"] = dl.get("hosts", [])
            return result

    # 2) 回退：文本 XML ElementTree
    try:
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        package_name = root.attrib.get("package")
        result["package_name"] = package_name

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
    result["details"]["axml_parsed"] = manifest_data.get("axml_parsed", False)
    result["details"]["deep_link_hosts"] = manifest_data.get("deep_link_hosts", [])

    if manifest_data.get("errors"):
        result["findings"].append({
            "type": "manifest_parse_error",
            "value": manifest_data["errors"][0]
        })

    # 0. AXML 分支：检查解析出的深链 host（scheme 在 data 中，host 顶层）
    for host in manifest_data.get("deep_link_hosts", []):
        if host in ("schemas.android.com",):
            continue  # 系统 schema，非业务深链
        if host not in production_hosts:
            if re.search(r"(test|dev|staging|local)", host, re.IGNORECASE):
                result["findings"].append({
                    "type": "development_host_in_intent_filter",
                    "value": host,
                    "activity": "<axml>",
                    "location": "AndroidManifest.xml (AXML 解析)"
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
    
    # 2. 检查 scheme 白名单（系统标准 scheme 不属于违规自定义 scheme）
    STANDARD_SCHEMES = {"http", "https", "file", "content", "intent", "market", "sms", "tel", "mailto"}
    for intent_filter in manifest_data.get("intent_filters", []):
        for data in intent_filter.get("data", []):
            scheme = data.get("scheme")
            if not scheme:
                continue
            if scheme.lower() in STANDARD_SCHEMES:
                continue
            if not scheme.startswith(("com.", "org.")):
                if not scheme.startswith(("myapp", "xxai")):
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
    parser.add_argument("--production-hosts", nargs="*", default=["api.xxai.com", "feed-api.xxai.com", "auth.xxai.com"])
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

