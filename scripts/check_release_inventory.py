#!/usr/bin/env python3
"""NS-20: 发布构建产物清单 / 安全库存检查
扫描构建产物目录，生成资源路径清单，检查禁止路径是否存在
"""
import argparse, json, sys
from pathlib import Path

FORBIDDEN_PATH_PATTERNS = [
    "mock_", "fixture_", "debug_", "test_",
    "/mock/", "/test/", "/debug/", "/fixture/",
]

RESOURCE_CATEGORIES = {
    "dex":           [".dex"],
    "native_lib":    [".so"],
    "assets":        [".png", ".jpg", ".webp", ".gif", ".svg"],
    "flutter_assets":["flutter_assets"],
    "config":        [".xml", ".plist", ".json"],
    "certificates":  [".cer", ".p12", ".pfx", ".pem", ".keystore"],
}

def scan_directory(build_dir):
    inventory = {"categories": {}, "forbidden_paths": [], "total_files": 0}
    if not build_dir.exists():
        return inventory
    for f in build_dir.rglob("*"):
        if not f.is_file():
            continue
        inventory["total_files"] += 1
        rel = str(f).lower()
        # 检查禁止路径
        for pat in FORBIDDEN_PATH_PATTERNS:
            if pat in rel:
                inventory["forbidden_paths"].append({
                    "file": str(f),
                    "matched_pattern": pat,
                })
                break
        # 归类
        suffix = f.suffix.lower()
        for cat, exts in RESOURCE_CATEGORIES.items():
            if suffix in exts or any(ext in rel for ext in exts if ext.startswith("/")):
                inventory["categories"].setdefault(cat, []).append(str(f))
                break
    return inventory

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", default="build", help="构建产物目录")
    parser.add_argument("--apk", help="APK 文件路径")
    parser.add_argument("--output-json")
    args = parser.parse_args()

    build_dir = Path(args.build_dir)
    scan_targets = [build_dir]
    if args.apk and Path(args.apk).exists():
        scan_targets.append(Path(args.apk))

    findings = []
    all_inventory = {}

    for target in scan_targets:
        inv = scan_directory(target)
        all_inventory[str(target)] = inv
        if inv["forbidden_paths"]:
            for fp in inv["forbidden_paths"]:
                findings.append({
                    "type": "forbidden_path_in_artifact",
                    "file": fp["file"],
                    "matched_pattern": fp["matched_pattern"],
                    "severity": "CRITICAL",
                })
        if inv["total_files"] == 0:
            findings.append({
                "type": "empty_build_directory",
                "file": str(target),
                "severity": "MEDIUM",
                "description": "构建目录为空或未提供",
            })

    status = "FAIL" if findings else "PASS"
    result = {
        "test_case": "NS-20",
        "test_name": "Release Artifact Inventory",
        "status": status,
        "findings": findings,
        "inventory": all_inventory,
        "notes": "检查禁止路径（mock_/test_/debug_/fixture_）及资源类别统计。",
    }

    out = args.output_json or "/tmp/NS-20.json"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"NS-20 结果: {status}  (forbidden={len(findings)})")
    for f in findings:
        print(f"  [{f['severity']}] {f['type']}: {f['file']}")
    sys.exit(0 if status == "PASS" else 1)

if __name__ == "__main__":
    main()
