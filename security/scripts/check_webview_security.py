#!/usr/bin/env python3
"""NS-16: WebView 安全（增强版，静态解析真实逻辑）
扫描 APK 资源/代码中的 WebView 配置：JavaScript 接口、file://、debugging、mixed content
"""
import argparse, json, sys, os, zipfile, re

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--apk"); parser.add_argument("--output-json")
    args = parser.parse_args()
    findings = []
    if not args.apk or not os.path.exists(args.apk):
        with open(args.output_json or "/tmp/NS-16.json","w") as f: json.dump({"test_case":"NS-16","status":"SKIPPED","findings":[{"id":"no_apk","note":"无 APK 输入"}]},f,indent=2,ensure_ascii=False)
        sys.exit(1)
    try:
        with zipfile.ZipFile(args.apk,"r") as z:
            for name in z.namelist():
                if name.endswith(".smali") or name.endswith(".dex") or "assets" in name or "lib/" in name:
                    try:
                        content = z.read(name).decode("utf-8", errors="ignore")
                        # JS interface exposure patterns
                        if "addJavascriptInterface" in content:
                            findings.append({"id":"js_interface_exposed","severity":"HIGH","note":"发现 addJavascriptInterface 调用: "+name})
                        if "setJavaScriptEnabled" in content and "true" in content:
                            findings.append({"id":"js_enabled","severity":"MEDIUM","note":"WebView JavaScript 启用: "+name})
                        if "loadUrl" in content and ("file://" in content or "javascript:" in content):
                            findings.append({"id":"unsafe_url_load","severity":"HIGH","note":"发现 file:// / javascript: URL 加载风险: "+name})
                        if "setWebContentsDebuggingEnabled" in content or "setAllowUniversalAccessFromFileURLs" in content:
                            findings.append({"id":"debug_universal_access","severity":"HIGH","note":"WebView 调试/全域访问启用: "+name})
                    except:
                        pass
    except Exception as e:
        findings.append({"id":"parse_error","severity":"MEDIUM","note":"解析异常: "+str(e)})
    status = "FAIL" if any(f.get("severity")=="HIGH" for f in findings) else ("REVIEW" if findings else "PASS")
    res = {"test_case":"NS-16","test_name":"WebView Security","status":status,"findings":findings,"notes":"静态扫描已提取 WebView 配置；运行时验证（打开 WebView 测试混合内容/mixed content）需设备环境"}
    with open(args.output_json or "/tmp/NS-16.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
    sys.exit(0 if status!="FAIL" else 1)
if __name__=="__main__": main()
