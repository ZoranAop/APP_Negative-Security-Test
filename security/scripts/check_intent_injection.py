#!/usr/bin/env python3
"""NS-15: Deep Link / Intent 注入安全（增强版，静态解析真实逻辑）
解析 manifest intent-filter，检查非生产 host / 注入模式
"""
import argparse, json, sys, os, zipfile, re

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest"); parser.add_argument("--apk"); parser.add_argument("--output-json")
    args = parser.parse_args()
    manifest = ""
    try:
        if args.manifest and os.path.exists(args.manifest): manifest = open(args.manifest,"r",encoding="utf-8",errors="ignore").read()
        elif args.apk and os.path.exists(args.apk):
            with zipfile.ZipFile(args.apk,"r") as z:
                manifest = z.read("AndroidManifest.xml").decode("utf-8",errors="ignore") if "AndroidManifest.xml" in z.namelist() else ""
        else: raise FileNotFoundError("无输入")
    except Exception as e:
        with open(args.output_json or "/tmp/NS-15.json","w") as f: json.dump({"test_case":"NS-15","status":"SKIPPED","findings":[{"id":"no_input","note":"无法解析 manifest/APK: "+str(e)}]},f,indent=2,ensure_ascii=False)
        sys.exit(1)
    findings = []
    # Extract intent filters with actions and data schemes
    filters = re.findall(r'<intent-filter[^>]*>(.*?)</intent-filter>', manifest, re.DOTALL)
    for block in filters:
        hosts = re.findall(r'android:host="([^"]+)"', block)
        schemes = re.findall(r'android:scheme="([^"]+)"', block)
        for h in hosts:
            if "dev." in h or "test." in h or "staging." in h or "localhost" in h or "mock" in h.lower():
                findings.append({"id":"non_prod_host","severity":"HIGH","host":h,"note":"发现非生产 host 注册"})
        for s in schemes:
            if s in ["javascript","intent","file","content","data"]:
                findings.append({"id":"dangerous_scheme","severity":"HIGH","scheme":s,"note":"发现高风险 scheme 注册"})
    # Check for open redirect / unvalidated redirect patterns (basic regex)
    redirect_patterns = re.findall(r'(?i)(redirect|redirecturi|url|return_url|callback)[=:/][^\s"\'<>]*', manifest)
    if redirect_patterns:
        findings.append({"id":"potential_redirect","severity":"MEDIUM","note":"发现潜在重定向参数模式，需人工确认业务映射"})
    status = "FAIL" if any(f.get("severity")=="HIGH" for f in findings) else ("REVIEW" if findings else "PASS")
    res = {"test_case":"NS-15","test_name":"Intent Injection Security","status":status,"findings":findings,"notes":"静态解析已完成；动态注入验证需设备环境执行（adb start -d ...）"}
    with open(args.output_json or "/tmp/NS-15.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
    sys.exit(0 if status in ["PASS","REVIEW"] else 1)
if __name__=="__main__": main()
