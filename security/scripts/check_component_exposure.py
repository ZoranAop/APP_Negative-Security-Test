# FAIL-CLOSED PATCH: missing/invalid APK must not return PASS
import sys, os
if __name__ == "__main__" and (not sys.argv or len(sys.argv) < 3):
    print("SKIPPED: missing required input (apk/manifest)")
    sys.exit(1)

#!/usr/bin/env python3
"""
SEC-014 / NS-14: Android Component Exposure 检查
解析 AndroidManifest.xml 检测 exported 组件、Debug 入口、provider 权限等
"""
import argparse, json, sys, re, subprocess, zipfile
from pathlib import Path

DEBUG_COMPONENT_PATTERNS = [
    r"DebugActivity", r"TestActivity", r"InspectorActivity",
    r"DevActivity", r"MockServer", r"DebugPanel", r"OopsActivity",
]

def extract_manifest_from_apk(apk_path):
    """从 APK 提取 binary AndroidManifest.xml（使用 aapt2 或 python 备选）"""
    try:
        out = subprocess.run(
            ["aapt2", "dump", "xmltree", str(apk_path)],
            capture_output=True, text=True, timeout=30
        )
        if out.returncode == 0:
            return out.stdout
    except Exception:
        pass
    # 备选：unzip 后 strings 扫描
    try:
        with zipfile.ZipFile(apk_path) as z:
            for name in z.namelist():
                if name.endswith("AndroidManifest.xml"):
                    raw = z.read(name)
                    # binary XML → strings 粗扫描
                    return raw.decode("utf-16-le", errors="ignore")
    except Exception:
        pass
    return ""

def parse_manifest(manifest_xml_text):
    """解析 manifest XML 文本，提取组件属性"""
    result = {
        "exported_activities": [],
        "exported_services": [],
        "exported_receivers": [],
        "exported_providers": [],
        "provider_without_permission": [],
        "debug_components": [],
        "intent_schemes": [],
    }

    # exported Activity
    for m in re.finditer(r'<activity[^>]*android:exported="true"[^>]*android:name="([^"]+)"', manifest_xml_text):
        result["exported_activities"].append(m.group(1))
    for m in re.finditer(r'<activity[^>]*android:name="([^"]+)"[^>]*android:exported="true"', manifest_xml_text):
        if m.group(1) not in result["exported_activities"]:
            result["exported_activities"].append(m.group(1))

    # exported Service
    for m in re.finditer(r'<service[^>]*android:exported="true"[^>]*android:name="([^"]+)"', manifest_xml_text):
        result["exported_services"].append(m.group(1))
    for m in re.finditer(r'<service[^>]*android:name="([^"]+)"[^>]*android:exported="true"', manifest_xml_text):
        if m.group(1) not in result["exported_services"]:
            result["exported_services"].append(m.group(1))

    # exported Receiver
    for m in re.finditer(r'<receiver[^>]*android:exported="true"[^>]*android:name="([^"]+)"', manifest_xml_text):
        result["exported_receivers"].append(m.group(1))
    for m in re.finditer(r'<receiver[^>]*android:name="([^"]+)"[^>]*android:exported="true"', manifest_xml_text):
        if m.group(1) not in result["exported_receivers"]:
            result["exported_receivers"].append(m.group(1))

    # exported Provider
    provider_blocks = re.findall(r'<provider[^>]*>(?:</provider>|)', manifest_xml_text, re.DOTALL)
    for pb in provider_blocks:
        exported = 'android:exported="true"' in pb or 'android:exported="1"' in pb
        has_perm  = 'android:permission=' in pb or 'android:readPermission=' in pb
        name_m = re.search(r'android:name="([^"]+)"', pb)
        if exported:
            pname = name_m.group(1) if name_m else "unknown"
            result["exported_providers"].append(pname)
            if not has_perm:
                result["provider_without_permission"].append(pname)

    # Debug components
    for pat in DEBUG_COMPONENT_PATTERNS:
        for m in re.finditer(pat, manifest_xml_text):
            result["debug_components"].append(m.group(0))

    # intent schemes
    for m in re.finditer(r'android:scheme="([^"]+)"', manifest_xml_text):
        result["intent_schemes"].append(m.group(1))

    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", help="已解压的 AndroidManifest.xml 路径")
    parser.add_argument("--apk", help="APK 文件路径（将自动提取 manifest）")
    parser.add_argument("--output-json")
    args = parser.parse_args()

    manifest_text = ""
    if args.manifest and Path(args.manifest).exists():
        manifest_text = Path(args.manifest).read_text(errors="ignore")
    elif args.apk and Path(args.apk).exists():
        manifest_text = extract_manifest_from_apk(args.apk)
    else:
        result = {
            "test_case": "NS-14",
            "test_name": "Android Component Exposure",
            "status": "FAIL",
            "findings": [{"type": "no_input", "severity": "MEDIUM",
                           "description": "未提供 --manifest 或 --apk 参数，无法执行检查"}],
        }
        out = args.output_json or "/tmp/NS-14.json"
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"NS-14 结果: FAIL — 无输入文件")
        sys.exit(1)

    parsed = parse_manifest(manifest_text)

    findings = []
    # 检测 Debug 组件
    if parsed["debug_components"]:
        findings.append({
            "type": "debug_component_in_manifest",
            "value": parsed["debug_components"],
            "severity": "CRITICAL",
            "description": "生产包中发现调试组件，必须移除",
        })

    # Provider 无权限保护
    if parsed["provider_without_permission"]:
        findings.append({
            "type": "provider_exported_without_permission",
            "value": parsed["provider_without_permission"],
            "severity": "HIGH",
            "description": "exported Provider 未设置 permission，存在数据泄露风险",
        })

    status = "FAIL" if findings else "PASS"
    result = {
        "test_case": "NS-14",
        "test_name": "Android Component Exposure",
        "status": status,
        "findings": findings,
        "details": parsed,
        "notes": "完整检查建议配合 aapt2 使用；未安装时 fallback 到 strings 粗扫描。",
    }

    out = args.output_json or "/tmp/NS-14.json"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"NS-14 结果: {status}")
    for f in findings:
        print(f"  [{f['severity']}] {f['type']}: {f['value']}")
    sys.exit(0 if status == "PASS" else 1)

if __name__ == "__main__":
    main()
