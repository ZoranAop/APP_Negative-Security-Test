#!/usr/bin/env python3
"""
检查域名隔离（Negative Security Test）
检查 Info.plist、Associated Domains 及网络配置中是否包含非生产域名
"""

import argparse
import json
import plistlib
import re
import sys
from pathlib import Path

# 复用 shared AXML 解析器（binary AndroidManifest.xml 确定性解析，无 Android SDK 依赖）
sys.path.insert(0, str(Path(__file__).resolve().parent / "shared"))
try:
    from axml_parser import parse_axml_manifest as _axml_parse
except Exception:
    _axml_parse = None


def parse_plist(plist_path):
    """解析 plist 文件"""
    try:
        with open(plist_path, 'rb') as f:
            return plistlib.load(f)
    except Exception as e:
        return {"error": str(e), "data": None}

def parse_android_manifest(manifest_path):
    """解析 AndroidManifest.xml。
    优先用 AXML 解析器处理 binary manifest（aapt2 编译产物）；
    若解析失败且文件为普通文本 XML，回退到正则。"""
    result = {"domains": [], "urls": [], "net_config": {}, "axml_parsed": False}
    try:
        p = Path(manifest_path)
        if not p.exists():
            return {"error": f"manifest 不存在: {p}", "data": None, "axml_parsed": False}

        # 1) 优先：AXML 二进制解析（无 aapt2 也可确定性读 manifest 域名/深链/组件）
        if _axml_parse:
            ax = _axml_parse(str(p))
            if ax.get("parsed"):
                result["axml_parsed"] = True
                # 合并生产/开发域名与深链 host（过滤字符串池噪声：长度前缀、组件全限定名）
                prod = [d for d in ax["domains"].get("production", []) if re.fullmatch(r"[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}", d)]
                dl_hosts = ax["deep_link"].get("hosts", [])
                result["domains"] = sorted(set(prod) | set(dl_hosts))
                result["urls"] = ax["deep_link"].get("schemes", [])
                result["dev_test_domains"] = ax["domains"].get("dev_test", [])
                result["thirdparty_domains"] = ax["domains"].get("thirdparty", [])
                return result

        # 2) 回退：普通文本 XML 正则
        content = p.read_text(encoding='utf-8', errors='ignore')
        url_pattern = r'android:value\s*=\s*["\']([^"\']+)["\']'
        for match in re.finditer(url_pattern, content):
            url = match.group(1)
            if any(scheme in url for scheme in ['http', 'https', 'flutter', 'ws']):
                result["urls"].append(url)
        host_pattern = r'<data[^>]*android:host=["\']([^"\']+)["\']'
        for match in re.finditer(host_pattern, content):
            result["domains"].append(match.group(1))
        scheme_pattern = r'<data[^>]*android:scheme=["\']([^"\']+)["\']'
        for match in re.finditer(scheme_pattern, content):
            result["domains"].append(match.group(1))
        return result
    except Exception as e:
        return {"error": str(e), "data": None, "axml_parsed": False}

def check_associated_domains(plist_path):
    """检查 Associated Domains 配置"""
    result = {
        "has_associated_domains": False,
        "applinks": [],
        "activities": [],
        "errors": []
    }
    
    plist_data = parse_plist(plist_path)
    if plist_data.get("error"):
        result["errors"].append(plist_data["error"])
        return result
    
    data = plist_data.get("data", {})
    
    # 检查 Associated Domains
    if "AssociatedDomains" in data:
        result["has_associated_domains"] = True
        for domain in data["AssociatedDomains"]:
            if domain.startswith("applinks:"):
                result["applinks"].append(domain)
            elif domain.startswith("activity"):
                result["activities"].append(domain)
    
    return result

def check_network_security_config(manifest_path, artifacts_dir):
    """检查 Android 网络安全配置"""
    result = {
        "cleartext_traffic": False,
        "debug_http_host": [],
        "custom_ca": []
    }
    
    try:
        # 解压 APK 获取网络配置
        import subprocess
        output_dir = Path(artifacts_dir) / "network_config"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用 apktool 解包
        subprocess.run([
            "apktool", "d", str(manifest_path.parent), "-o", str(output_dir)
        ], check=True, capture_output=True)
        
        # 查找 network_security_config.xml
        for config_file in output_dir.rglob("network_security_config.xml"):
            content = config_file.read_text(errors='ignore')
            
            # 检查 cleartext traffic 策略
            if "cleartextTrafficPermitted" in content and "true" in content:
                result["cleartext_traffic"] = True
            
            # 检查 debug 主机
            if "debug" in content.lower():
                # 提取 host
                host_pattern = r'<host\s+name=["\']([^"\']+)["\']'
                for match in re.finditer(host_pattern, content):
                    result["debug_http_host"].append(match.group(1))
            
            # 检查自定义 CA
            if "ca-file-uris" in content:
                result["custom_ca"].append(str(config_file))
    
    except Exception as e:
        result["error"] = str(e)
    
    return result

def scan_for_domain_patterns(file_path):
    """扫描文件中出现的域名模式"""
    result = {
        "domains_found": [],
        "suspicious_urls": [],
        "api_endpoints": []
    }
    
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        
        # 匹配 URL
        url_pattern = r'https?://([a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,})(/[^\s"<>]*)?'
        for match in re.finditer(url_pattern, content):
            domain = match.group(1)
            url = match.group(0)
            if domain not in result["domains_found"]:
                result["domains_found"].append(domain)
            result["suspicious_urls"].append(url)
            
            # 提取 API 端点
            if any(kw in url for kw in ['api', 'v1', 'v2', 'endpoint', 'service']):
                result["api_endpoints"].append(url)
                
    except Exception as e:
        result["error"] = str(e)
    
    return result

def main():
    parser = argparse.ArgumentParser(description="检查域名隔离（反向安全测试）")
    parser.add_argument("--manifest", required=True, help="AndroidManifest.xml 路径")
    parser.add_argument("--info-plist", required=True, help="iOS Info.plist 路径")
    parser.add_argument("--artifacts-dir", default="results/artifacts", help="输出目录")
    parser.add_argument("--output-json", help="输出 JSON 结果文件")
    parser.add_argument("--production-domains", nargs="*", default=[
        "api.xxai.com", "feed-api.xxai.com", "auth.xxai.com", "xxai.com"
    ], help="生产域名白名单")
    parser.add_argument("--production-associated-domains", nargs="*", default=[
        "applinks:xxai.com"
    ], help="生产 Associated Domains 白名单")
    
    args = parser.parse_args()
    
    # 结果结构
    results = {
        "test_case": "NS-02-domain-isolation",
        "test_name": "接口/域名/Associated Domains 隔离",
        "status": "PASS",
        "details": {},
        "findings": []
    }
    
    production_domains = set(args.production_domains)
    production_associated_domains = set(args.production_associated_domains)
    
    # 1. 检查 Android Manifest
    # 系统/框架允许的域名与 scheme（NS-02 白名单扩展，避免 AXML 解析产物误报）
    SYSTEM_DOMAIN_WHITELIST = {
        "schemas.android.com", "android", "schemas.android", "com.android", "com.google.android",
        "xxai", "https", "http", "file", "content", "intent", "flutter",
    }

    manifest_path = Path(args.manifest)
    manifest_data = {"domains": [], "urls": []}
    if manifest_path.exists():
        manifest_data = parse_android_manifest(manifest_path)
        results["details"]["android_manifest"] = manifest_data

        # 检查发现的域名
        for domain in manifest_data.get("domains", []):
            dnorm = domain.lower()
            if dnorm in SYSTEM_DOMAIN_WHITELIST:
                continue
            if domain not in production_domains and not domain.startswith(("com.example", "org.example")):
                results["findings"].append({
                    "type": "android_domain_not_in_whitelist",
                    "value": domain
                })

        for url in manifest_data.get("urls", []):
            # AXML 分支的 urls 实为 schemes（xxai/https/intent 等），直接跳过；
            # 文本 XML 分支的 urls 形如 https://xxai.com，按 host 校验
            if "://" in url:
                parsed_url = url.split("://")[1].split("/")[0]
                if parsed_url not in production_domains:
                    results["findings"].append({
                        "type": "android_url_not_in_whitelist",
                        "value": url
                    })
    
    # 2. 检查 iOS Info.plist
    info_plist_path = Path(args.info_plist)
    if info_plist_path.exists():
        plist_data = parse_plist(info_plist_path)
        
        # 检查 Associated Domains
        assoc_domains_result = check_associated_domains(info_plist_path)
        results["details"]["ios_associated_domains"] = assoc_domains_result
        
        for applink in assoc_domains_result.get("applinks", []):
            if applink not in production_associated_domains:
                results["findings"].append({
                    "type": "ios_applink_not_in_whitelist",
                    "value": applink,
                    "location": "AssociatedDomains"
                })
        
        # 检查 NSAppTransportSecurity 中的异常配置
        plist_content = plist_data.get("data", {})
        if "NSAppTransportSecurity" in plist_content:
            ats = plist_content["NSAppTransportSecurity"]
            if ats.get("NSAllowsArbitraryLoads"):
                results["findings"].append({
                    "type": "ios_allows_arbitrary_loads",
                    "value": ats.get("NSAllowsArbitraryLoads")
                })
    
    # 3. 扫描构建产物中的所有文件（APK/IPA 解压后的文件）
    # 排除框架/系统/开源 SDK 自带域名（Info.plist 等系统资源），避免误报
    SYSTEM_DOMAIN_ALLOWLIST = {
        "apple.com", "www.apple.com", "apple-dns-scripts.com", "apple.com.cn",
        "llvm.googlesource.com", "googlesource.com", "google.com", "golang.org",
        "flutter.dev", "flutter.dev.", "api.flutter.dev", "plugins.flutter.dev",
        "fluttercommunity.dev", "dev.fluttercommunity", "firebase.google.com",
    }
    artifacts_dir = Path(args.artifacts_dir)
    if artifacts_dir.exists():
        for file_type in ["*.xml", "*.plist", "*.json", "*.dart"]:
            for file_path in artifacts_dir.rglob(file_type):
                scan_result = scan_for_domain_patterns(file_path)
                for domain in scan_result.get("domains_found", []):
                    dnorm = domain.lower()
                    if dnorm in SYSTEM_DOMAIN_ALLOWLIST:
                        continue
                    if any(dnorm.endswith(s.lstrip(".").lower()) for s in SYSTEM_DOMAIN_ALLOWLIST if "." in s):
                        continue
                    if domain not in production_domains:
                        results["findings"].append({
                            "type": "unexpected_domain_in_assets",
                            "value": domain,
                            "file": str(file_path)
                        })
    
    # 4. 检查开发/测试域名模式
    dev_domain_patterns = [
        r"dev\.", r"test\.", r"local\.", r"staging\.",
        r"\.local$", r"-test$", r"-dev$", r"\.test\."
    ]
    
    all_domains = (manifest_data.get("domains", []) + 
                   manifest_data.get("urls", []))
    
    for domain in all_domains:
        for pattern in dev_domain_patterns:
            if re.search(pattern, domain, re.IGNORECASE):
                results["findings"].append({
                    "type": "development_domain_detected",
                    "value": domain,
                    "pattern": pattern
                })
    
    # 判断结果
    if results["findings"]:
        results["status"] = "FAIL"
        results["details"]["total_findings"] = len(results["findings"])
    
    # 保存结果
    if args.output_json:
        with open(args.output_json, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    
    # 输出摘要
    print(f"测试结果: {results['status']}")
    print(f"发现 {len(results['findings'])} 个问题:")
    for finding in results["findings"]:
        print(f"  - [{finding['type']}] {finding['value']}")
    
    sys.exit(0 if results["status"] == "PASS" else 1)

if __name__ == "__main__":
    main()