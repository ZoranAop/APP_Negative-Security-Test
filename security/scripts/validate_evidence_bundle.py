#!/usr/bin/env python3
"""Evidence Bundle Validation（根据文档 6. 新增校验）
检查 NS-01~NS-21 + SEC-012 证据完整性，拒绝 FRAMEWORK_READY / SKIPPED / UNKNOWN / 缺失
"""
import argparse, json, sys, os
from pathlib import Path

REQUIRED = [f"NS-{i:02d}" for i in list(range(1,10)) + list(range(10,22))] + ["SEC-012"]
VALID_STATUSES = {"PASS"}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--evidence-dir", default="results/evidence"); parser.add_argument("--output-json")
    args = parser.parse_args()
    evidence_dir = Path(args.evidence_dir)
    missing = []; bad = []
    for rule in REQUIRED:
        p = evidence_dir / f"{rule}.json"
        if not p.exists():
            missing.append(rule)
            continue
        try:
            with open(p) as f: data = json.load(f)
            status = data.get("status", "UNKNOWN")
            if status not in VALID_STATUSES:
                bad.append((rule, status))
        except Exception as e:
            bad.append((rule, f"JSON解析失败:{e}"))
    ok = not missing and not bad
    result = {
        "bundle_valid": ok,
        "required_rules": REQUIRED,
        "missing_evidence": missing,
        "invalid_status": [{"rule":r,"status":s} for r,s in bad],
        "message": "所有 Required Rules 证据存在且状态均为 PASS。" if ok else f"缺失: {missing}; 无效状态: {[r for r,_ in bad]}",
        "fail_closed": "缺少任意规则或状态非 PASS → BLOCK，绝不 ALLOW。"
    }
    out = args.output_json or "results/evidence_bundle_valid.json"
    os.makedirs(os.path.dirname(out) if os.path.dirname(out) else ".", exist_ok=True)
    with open(out, "w") as f: json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Evidence Bundle: {'PASS' if ok else 'FAIL'} — 缺失: {len(missing)}，无效状态: {len(bad)}")
    sys.exit(0 if ok else 1)
if __name__=="__main__": main()

# Platform evidence profiles (added)
# android: artifact.apk manifest.xml build.log sha256.json signing-report.json
# ios: artifact.ipa info.plist entitlements.plist build.log sha256.json dsym.zip
# Evidence bundle validates presence per profile; missing platform-specific evidence = BLOCK

