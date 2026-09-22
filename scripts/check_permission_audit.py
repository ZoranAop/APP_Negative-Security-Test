#!/usr/bin/env python3
"""NS-13: 权限审计（增强版，真实解析）
解析 AndroidManifest.xml 提取高风险权限，生成清单，标注业务映射缺失
"""
import argparse, json, sys, os, zipfile, re
DANGEROUS = ["CAMERA","RECORD_AUDIO","ACCESS_FINE_LOCATION","ACCESS_COARSE_LOCATION",
             "READ_CONTACTS","READ_SMS","CALL_PHONE","READ_PHONE_STATE",
             "REQUEST_INSTALL_PACKAGES","QUERY_ALL_PACKAGES","WRITE_EXTERNAL_STORAGE",
             "READ_EXTERNAL_STORAGE","ACCESS_BACKGROUND_LOCATION"]
def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--apk"); parser.add_argument("--manifest"); parser.add_argument("--output-json")
    args = parser.parse_args()
    findings = []
    manifest = ""
    try:
        if args.manifest and os.path.exists(args.manifest):
            manifest = open(args.manifest,"r",encoding="utf-8",errors="ignore").read()
        elif args.apk and os.path.exists(args.apk):
            with zipfile.ZipFile(args.apk,"r") as z:
                manifest = z.read("AndroidManifest.xml").decode("utf-8",errors="ignore") if "AndroidManifest.xml" in z.namelist() else ""
        else:
            raise FileNotFoundError("无 manifest 或 APK")
    except Exception as e:
        with open(args.output_json or "/tmp/NS-13.json","w") as f: json.dump({"test_case":"NS-13","status":"SKIPPED","findings":[{"id":"no_input","note":"无法读取 manifest/APK: "+str(e)}]},f,indent=2,ensure_ascii=False)
        sys.exit(1)
    # Extract permissions
    perms = re.findall(r'<uses-permission[^>]*android:name="([^"]+)"', manifest)
    dangerous = [p for p in perms if any(d in p for d in DANGEROUS)]
    if dangerous:
        findings.append({"id":"dangerous_permissions","severity":"HIGH","note":"发现高风险权限: "+",".join(dangerous)})
    # Check for missing business mapping (framework note: 需人工签字)
    findings.append({"id":"business_mapping","severity":"REVIEW","note":"权限清单已生成，但业务必要性映射需人工签字确认（见 MANUAL_TEST_MATRIX.md）"})
    status = "FAIL" if any(f.get("severity")=="HIGH" for f in findings) else "REVIEW"
    res = {"test_case":"NS-13","test_name":"Permission Audit","status":status,"findings":findings,"permissions_found":perms,"dangerous_found":dangerous,"notes":"已提取真实权限清单，缺少业务映射签字 → REVIEW"}
    with open(args.output_json or "/tmp/NS-13.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
    sys.exit(0 if status!="FAIL" else 1)
if __name__=="__main__": main()
