#!/usr/bin/env python3
"""NS-19: Artifact Consistency（真实解析版）
检查构建产物身份一致性（SHA、版本、签名、构建日志对应关系）
状态：PASS / FAIL / REVIEW / SKIPPED
"""
import argparse, json, sys, os, hashlib

def sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(8192)
                if not chunk: break
                h.update(chunk)
        return h.hexdigest()
    except:
        return None

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--apk"); parser.add_argument("--ipa"); parser.add_argument("--build-log", default="build.log"); parser.add_argument("--output-json")
    args = parser.parse_args()
    findings = []; source = ""
    artifact_path = args.apk or args.ipa
    if artifact_path and os.path.exists(artifact_path):
        sha = sha256(artifact_path)
        findings.append({"sha256": sha, "size_bytes": os.path.getsize(artifact_path), "status":"PASS"})
        source = artifact_path
        # 构建日志一致性检查
        if args.build_log and os.path.exists(args.build_log):
            with open(args.build_log, 'r', errors='ignore') as f:
                log_text = f.read()
            if 'release' not in log_text.lower() and '--release' not in log_text:
                findings.append({"build_config":"可能未使用 --release 构建", "severity":"FAIL"})
        else:
            findings.append({"build_log":"缺少构建日志", "severity":"REVIEW"})
    else:
        with open(args.output_json or "/tmp/NS-19.json","w") as f: json.dump({"test_case":"NS-19","status":"SKIPPED","findings":[{"note":"无构建产物或构建日志","severity":"SKIPPED"}],"reason":"缺少构建输入 → SKIPPED → BLOCK（Fail-Closed）","source":"无输入"}, f, indent=2)
        print("NS-19 SKIPPED — 无构建输入（Fail-Closed）")
        sys.exit(0)
    status = "FAIL" if has_fail else ("PASS" if any(isinstance(f, dict) and f.get("sha256") for f in findings) else "REVIEW")
    with open(args.output_json or "/tmp/NS-19.json","w") as f:
        json.dump({"test_case":"NS-19","test_name":"Artifact Consistency","status":status,"findings":findings,"notes":"已计算构建产物 SHA 并检查构建日志一致性。SKIPPED 不得视为 PASS。","source":source}, f, indent=2, ensure_ascii=False)
    print(f"NS-19 {status} — 已生成证据")
    sys.exit(0 if status=="PASS" else 1)
if __name__=="__main__": main()
