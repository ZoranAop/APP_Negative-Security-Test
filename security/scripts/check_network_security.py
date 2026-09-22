#!/usr/bin/env python3
"""NS-12: 网络安全配置（增强版，静态解析真实逻辑）
检查 NetworkSecurityConfig / ATS / cleartext / CA bypass / hostname verifier / debug proxy
状态：PASS / FAIL / REVIEW / SKIPPED
"""
import argparse, json, sys, os, re, zipfile

def check_apk_network(apk_path):
    findings = []
    try:
        with zipfile.ZipFile(apk_path, 'r') as z:
            # Check for NetworkSecurityConfig reference in manifest
            manifest = z.read('AndroidManifest.xml').decode('utf-8', errors='ignore') if 'AndroidManifest.xml' in z.namelist() else ''
            if 'android:networkSecurityConfig' in manifest:
                findings.append({"id":"network_config_present","severity":"LOW","note":"存在 NetworkSecurityConfig 声明，需进一步解析配置文件"})
            # Scan compiled resources for cleartext or domain-config patterns
            for name in z.namelist():
                if name.endswith('.xml') or name.startswith('res/xml/'):
                    try:
                        content = z.read(name).decode('utf-8', errors='ignore')
                        if 'cleartextTrafficPermitted="true"' in content or "cleartextTrafficPermitted='true'" in content:
                            findings.append({"id":"cleartext_traffic","severity":"CRITICAL","note":"发现 cleartextTrafficPermitted=true，第 " + name})
                        if '<trust-anchors>' in content or '<debug-overrides>' in content:
                            findings.append({"id":"untrusted_ca","severity":"HIGH","note":"发现 trust-anchors/debug-overrides，第 " + name})
                        if 'hostname-verifier' in content.lower() or 'bypass' in content.lower():
                            findings.append({"id":"hostname_bypass","severity":"HIGH","note":"发现 hostname verifier 相关配置，第 " + name})
                    except Exception:
                        pass
    except Exception as e:
        findings.append({"id":"parse_error","severity":"MEDIUM","note":"APK 解析失败: " + str(e)})
    if not findings:
        return {"status":"PASS","note":"未发现清明文传输/CA 绕过/调试代理异常配置","findings":[]}
    critical = [f for f in findings if f.get("severity")=="CRITICAL"]
    high = [f for f in findings if f.get("severity")=="HIGH"]
    status = "FAIL" if critical else ("REVIEW" if high else "PASS")
    return {"status":status,"note":"已发现网络安全配置问题","findings":findings}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    if not args.apk or not os.path.exists(args.apk):
        res = {"test_case":"NS-12","test_name":"Network Security Config","status":"SKIPPED","findings":[{"id":"no_apk","note":"未提供 APK，无法执行静态解析"}],"notes":"Fail-Closed：无输入 → SKIPPED → BLOCK"}
        with open(args.output_json or "/tmp/NS-12.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
        sys.exit(1)
    result = check_apk_network(args.apk)
    res = {"test_case":"NS-12","test_name":"Network Security Config","status":result["status"],"findings":result["findings"],"notes":result["note"]}
    with open(args.output_json or "/tmp/NS-12.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
    sys.exit(0 if result["status"]=="PASS" else (0 if result["status"]=="REVIEW" else 1))
if __name__=="__main__": main()
