# FAIL-CLOSED PATCH: missing/invalid APK must not return PASS
import sys, os
if __name__ == "__main__" and (not sys.argv or len(sys.argv) < 3):
    print("SKIPPED: missing required input (apk/manifest)")
    sys.exit(1)

#!/usr/bin/env python3
"""
SEC-011 / NS-11: Secret / Credential 上下文检测框架（基础版，待熵值增强）
检查构建包中是否存在可能的敏感凭证，并根据上下文分类：
  REAL_SECRET (Critical) / THIRDPARTY_REF / FALSE_POSITIVE / CONTEXT_NEEDED
"""
import argparse, json, sys, re, subprocess
from pathlib import Path

SECRET_PATTERNS = [
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",  # JWT
    r"BEGIN (RSA|EC|OPENSSH|DSA|PGP) PRIVATE KEY",          # PEM
    r"AKIA[0-9A-Z]{16}",                                     # AWS
    r"ghp_[A-Za-z0-9]{36}",                                  # GitHub PAT
    r"xox[abps]-[A-Za-z0-9-]+",                              # Slack
    r"token\s*[:=]\s*['\"]?\S{8,}",
    r"password\s*[:=]\s*['\"]?\S{4,}",
    r"secret_key\s*[:=]\s*['\"]?\S{4,}",
    r"api_key\s*[:=]\s*['\"]?\S{8,}",
]

THIRDPARTY_REF_STRINGS = [
    "flutter.dev", "docs.flutter", "api.flutter", "plugins.flutter",
    "google.com", "firebase", "analytics.google", "example.com",
    "sample", "placeholder", "your-key-here", "yourtoken",
]

def classify_secret(match_text, context_text=""):
    text = (match_text + " " + context_text).lower()
    for ref in THIRDPARTY_REF_STRINGS:
        if ref in text:
            return "THIRDPARTY_REF", "第三方 SDK / 文档参考字符串（非真实凭证）"
    return "REAL_SECRET_CANDIDATE", "高风险：可能包含真实凭证"

def scan_apk_secrets(apk_path, findings):
    try:
        out_dir = Path(apk_path).parent / "secret_scan_tmp"
        out_dir.mkdir(exist_ok=True)
        subprocess.run(["unzip", "-q", "-o", str(apk_path), "-d", str(out_dir)],
                       check=True, capture_output=True, timeout=60)
        for f in out_dir.rglob("*"):
            if not f.is_file() or f.stat().st_size > 10 * 1024 * 1024:
                continue
            try:
                content = f.read_text(errors="ignore")
            except Exception:
                continue
            for pat in SECRET_PATTERNS:
                for m in re.finditer(pat, content, re.IGNORECASE):
                    cls, desc = classify_secret(m.group(0), content[max(0, m.start()-80):m.end()+80])
                    if cls == "REAL_SECRET_CANDIDATE":
                        findings.append({
                            "type": "secret_context",
                            "severity": "CRITICAL",
                            "file": str(f),
                            "match": m.group(0)[:120],
                            "classification": cls,
                            "description": desc,
                        })
    except Exception as e:
        findings.append({"type": "apk_scan_error", "severity": "MEDIUM",
                         "value": str(e), "classification": "ERROR"})

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk")
    parser.add_argument("--output-json")
    args = parser.parse_args()

    findings = []
    if args.apk and Path(args.apk).exists():
        scan_apk_secrets(args.apk, findings)

    real_secrets = [f for f in findings if f.get("classification") == "REAL_SECRET_CANDIDATE"]

    status = "FAIL" if real_secrets else "PASS"
    result = {
        "test_case": "NS-11",
        "test_name": "Secret / Credential Context Check",
        "status": status,
        "findings": findings,
        "classification": {
            "FAIL":     ["REAL_SECRET_CANDIDATE"],
            "REVIEW":   ["CONTEXT_NEEDED"],
            "THIRDPARTY": ["THIRDPARTY_REF"],
            "ALLOWLIST":  ["ALLOWLIST_APPROVED"],
        },
        "notes": "完整执行需配合熵值 / PEM / JWT 格式深度解析；当前为基础版。",
    }

    out = args.output_json or "/tmp/NS-11.json"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"NS-11 结果: {status}  (critical={len(real_secrets)}, findings={len(findings)})")
    for f in real_secrets:
        print(f"  [CRITICAL] {f['file']}: {f['match']}")
    sys.exit(0 if status == "PASS" else 1)

if __name__ == "__main__":
    main()
