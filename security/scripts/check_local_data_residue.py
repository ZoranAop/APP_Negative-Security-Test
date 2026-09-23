#!/usr/bin/env python3
"""NS-17: 本地敏感数据残留（增强版，静态扫描真实逻辑）
扫描 APK 中可能残留的 SharedPreferences / Hive / SQLite / Cache / Crash dump / Clipboard 相关文件/配置
"""
import argparse, json, sys, os, zipfile, re

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--apk"); parser.add_argument("--manifest"); parser.add_argument("--output-json")
    args = parser.parse_args()
    findings = []
    if not args.apk or not os.path.exists(args.apk):
        with open(args.output_json or "/tmp/NS-17.json","w") as f: json.dump({"test_case":"NS-17","status":"SKIPPED","findings":[{"id":"no_apk","note":"无 APK"}]},f,indent=2,ensure_ascii=False)
        sys.exit(1)
    try:
        with zipfile.ZipFile(args.apk,"r") as z:
            names = z.namelist()
            # Check for common data storage filenames/patterns
            storage_patterns = ["SharedPreferences","hive",".db","sqlite","cache","crash","dump","clipboard","token","auth","credential","secret"]
            for n in names:
                lower = n.lower()
                if any(p in lower for p in storage_patterns):
                    findings.append({"id":"potential_residue_file","severity":"REVIEW","note":"发现可能残留存储文件: "+n})
            # Check for unencrypted shared pref XML patterns
            for n in names:
                if n.endswith(".xml") and ("values" in n.lower() or "pref" in n.lower()):
                    try:
                        content = z.read(n).decode("utf-8",errors="ignore")
                        if "token" in content.lower() or "password" in content.lower() or "secret" in content.lower() or "bearer" in content.lower():
                            findings.append({"id":"residue_content","severity":"HIGH","note":"发现存储内容含敏感关键字: "+n})
                    except:
                        pass
    except Exception as e:
        findings.append({"id":"parse_error","severity":"MEDIUM","note":"解析异常: "+str(e)})
    status = "FAIL" if any(f.get("severity")=="HIGH" for f in findings) else ("REVIEW" if findings else "PASS")
    res = {"test_case":"NS-17","test_name":"Local Data Residue","status":status,"findings":findings,"notes":"静态扫描已提取可能残留存储文件/内容；运行时完整验证（登录→退出→重启→再检查）需设备环境"}
    with open(args.output_json or "/tmp/NS-17.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
    sys.exit(0 if status!="FAIL" else 1)
if __name__=="__main__": main()
