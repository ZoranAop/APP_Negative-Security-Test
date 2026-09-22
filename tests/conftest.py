"""
pytest fixtures 为反向安全测试提供统一的构建产物、配置和断言工具
"""

import os
import json
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 目录与产物
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def project_root():
    """项目根目录"""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def security_root(project_root):
    """仓库根目录（兼容旧 fixture 名称；实际文件在根目录而非 security/ 子目录）"""
    return project_root


@pytest.fixture(scope="session")
def build_artifacts(project_root, security_root):
    """构建产物目录（APK/IPA/symbols）"""
    artifact_env = os.environ.get("NEGATIVE_TEST_ARTIFACTS_DIR")
    if artifact_env:
        artifact_dir = Path(artifact_env)
    else:
        artifact_dir = security_root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    apk_candidates = list(artifact_dir.glob("**/app-release.apk"))
    if not apk_candidates:
        apk_candidates = list(artifact_dir.glob("**/*.apk"))
    ipa_candidates = list(artifact_dir.glob("**/*.ipa"))
    mapping_candidates = list(artifact_dir.glob("**/mapping.txt"))
    info_plist_candidates = list(artifact_dir.glob("**/Info.plist"))
    manifest_candidates = list(artifact_dir.glob("**/AndroidManifest.xml"))
    build_log_candidates = list(artifact_dir.glob("**/build.log"))
    pubspec_candidates = list(artifact_dir.glob("**/pubspec.yaml"))
    dart_lib_candidates = [p for p in artifact_dir.glob("**/lib") if p.is_dir()]
    assets_dir_candidates = [p for p in artifact_dir.glob("**/assets") if p.is_dir()]

    return {
        "apk": apk_candidates[0] if apk_candidates else None,
        "ipa": ipa_candidates[0] if ipa_candidates else None,
        "mapping": mapping_candidates[0] if mapping_candidates else None,
        "info_plist": info_plist_candidates[0] if info_plist_candidates else None,
        "manifest": manifest_candidates[0] if manifest_candidates else None,
        "build_log": build_log_candidates[0] if build_log_candidates else None,
        "pubspec": pubspec_candidates[0] if pubspec_candidates else None,
        "dart_lib": dart_lib_candidates[0] if dart_lib_candidates else None,
        "assets_dir": assets_dir_candidates[0] if assets_dir_candidates else None,
        "expected_cert_fingerprint": os.environ.get("EXPECTED_CERT_FINGERPRINT"),
        "dir": artifact_dir,
    }


@pytest.fixture(scope="session")
def build_config():
    """构建配置（从环境变量读取）"""
    return {
        "release": os.environ.get("BUILD_TYPE", "release") == "release",
        "obfuscate": os.environ.get("DART_OBFUSCATE", "true").lower() == "true",
        "split_debug_info": os.environ.get("SPLIT_DEBUG_INFO", "true").lower() == "true",
        "platform": os.environ.get("TARGET_PLATFORM", "android,ios"),
        "production_domains": os.environ.get(
            "PRODUCTION_DOMAINS",
            "api.xxai.com,feed-api.xxai.com,auth.xxai.com",
        ).split(","),
        "production_associated_domains": os.environ.get(
            "PRODUCTION_ASSOCIATED_DOMAINS", "applinks:xxai.com"
        ).split(","),
    }


@pytest.fixture(scope="session")
def test_report_dir(project_root):
    """测试结果目录"""
    report_dir = project_root / "results"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


@pytest.fixture(scope="session")
def evidence_dir(test_report_dir):
    """证据目录"""
    d = test_report_dir / "evidence"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# 环境 / CI 上下文
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def environment_profile():
    return {
        "debug": os.environ.get("BUILD_ENV", "release") == "debug",
        "staging": os.environ.get("BUILD_ENV", "release") == "staging",
        "production": os.environ.get("BUILD_ENV", "release") == "production",
    }


@pytest.fixture(scope="session")
def ci_context():
    return {
        "ci": os.environ.get("CI", "false").lower() == "true",
        "ci_name": os.environ.get("CI_NAME", "unknown"),
        "ci_build_url": os.environ.get("CI_BUILD_URL", ""),
        "git_sha": os.environ.get("GIT_SHA", "unknown"),
        "git_branch": os.environ.get("GIT_BRANCH", "unknown"),
    }


@pytest.fixture(scope="session")
def build_env():
    return {
        "name": os.environ.get("BUILD_NAME", "release"),
        "environment": os.environ.get("BUILD_ENV", "release"),
        "version": os.environ.get("BUILD_VERSION", "unknown"),
        "version_code": os.environ.get("BUILD_VERSION_CODE", "unknown"),
        "platform": os.environ.get("TARGET_PLATFORM", "android,ios"),
        "artifact_dir": os.environ.get("NEGATIVE_TEST_ARTIFACTS_DIR", "artifacts"),
    }


# ---------------------------------------------------------------------------
# 白名单 / 策略文件
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def allowlist_config(security_root):
    return security_root / "policies" / "allowlist.yaml"


@pytest.fixture(scope="session")
def opa_policy(security_root):
    return security_root / "policies" / "negative.rego"


@pytest.fixture(scope="session")
def gate_script(security_root):
    return security_root / "scripts" / "gate_decision.py"


# ---------------------------------------------------------------------------
# 测试清单（9 条 NS 规则）
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def security_test_manifest():
    return [
        {"id": "NS-01", "name": "调试面板/抓包隔离",      "script": "check_debug_isolation.py"},
        {"id": "NS-02", "name": "接口/域名/Associated Domains 隔离", "script": "check_domain_isolation.py"},
        {"id": "NS-03", "name": "Android 深链域名按构建环境隔离", "script": "check_deep_link_isolation.py"},
        {"id": "NS-04", "name": "日志输出按构建环境隔离",  "script": "check_log_isolation.py"},
        {"id": "NS-05", "name": "登录态迁移至 Keychain/加密存储", "script": "check_encryption_storage.py"},
        {"id": "NS-06", "name": "关闭 iOS Documents 文件共享", "script": "check_ios_file_sharing.py"},
        {"id": "NS-07", "name": "移除生产包 mock 数据",    "script": "check_mock_data_removal.py"},
        {"id": "NS-08", "name": "Flutter Release 启用 Dart 混淆与符号文件留存", "script": "check_dart_obfuscation.py"},
        {"id": "NS-09", "name": "发布前自动校验生产 IPA/APK", "script": "check_binary_integrity.py"},
    ]


@pytest.fixture(scope="session")
def security_test_rules(security_test_manifest):
    return security_test_manifest


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def run_command():
    def run(command, timeout=120):
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": command,
        }
    return run


@pytest.fixture(scope="session")
def assert_result_status():
    def assert_status(status, expected):
        assert status == expected, f"Expected status {expected}, got {status}"
    return assert_status


@pytest.fixture(scope="session")
def fail_on_any_finding():
    def check(result):
        return result.get("status") == "PASS"
    return check


@pytest.fixture(scope="session")
def collect_finding_count():
    def count(result):
        return len(result.get("findings", []))
    return count


@pytest.fixture(scope="session")
def security_test_config():
    return {
        "output_dir": os.environ.get("NEGATIVE_TEST_OUTPUT_DIR", "results"),
        "artifacts_dir": os.environ.get("NEGATIVE_TEST_ARTIFACTS_DIR", "artifacts"),
        "platform": os.environ.get("TARGET_PLATFORM", "android,ios"),
        "build_type": os.environ.get("BUILD_TYPE", "release"),
    }


# ---------------------------------------------------------------------------
# OPA / SARIF / JUnit 构建器
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def policy_input_builder():
    def build_policy_input(test_results, platform):
        platform_evidence = {
            "status": "PASS",
            "rules": [
                {
                    "id": r.get("test_case", f"NS-{i:02d}"),
                    "name": r.get("test_name", "unknown"),
                    "status": r.get("status", "PASS"),
                        "evidence_file": r.get("evidence_file", "results/evidence"),
                    "details": r.get("details", {}),
                }
                for i, r in enumerate(test_results, 1)
            ],
            "artifacts": {
                "apk": "build/app/outputs/flutter-apk/app-release.apk",
                "mapping_file": "build/symbols/android/mapping.txt",
            },
        }
        return {
            "platforms": [platform],
            "required_rules": {platform: [f"NS-{i:02d}" for i in range(1, 10)]},
            "evidence": {platform: platform_evidence},
        }
    return build_policy_input


@pytest.fixture(scope="session")
def sarif_builder():
    def build_sarif(test_results, rules):
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "informationUri": "http://<INTERNAL_GIT_URL>/<INTERNAL_USER>/xxai_app_negative-security-test",
                        "rules": [
                            {
                                "id": r["id"],
                                "name": r["name"],
                                "shortDescription": {"text": r["name"]},
                                "defaultConfiguration": {"level": "error"},
                            }
                            for r in rules
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": r.get("id", r.get("test_case", "unknown")),
                        "level": "error",
                        "message": {"text": f"{r.get('test_name', r.get('id','unknown'))} 未通过"},
                        "locations": [{
                            "physicalLocation": {
                                "artifactLocation": {"uri": r.get("evidence_file", "results/evidence")}
                            }
                        }],
                    }
                    for r in test_results
                    if r.get("status") != "PASS"
                ],
            }],
        }
        return sarif
    return build_sarif


@pytest.fixture(scope="session")
def junit_builder():
    def build_junit(test_results):
        import xml.etree.ElementTree as ET

        testsuite = ET.Element("testsuite", {
            "name": "Negative Security Test",
            "tests": str(len(test_results)),
            "failures": str(sum(1 for r in test_results if r.get("status") != "PASS")),
            "errors": "0",
            "time": "0",
        })
        for result in test_results:
            testcase = ET.SubElement(testsuite, "testcase", {
                "classname": result.get("test_case", "negative_security"),
                "name": result.get("test_name", "unknown"),
                "time": "0",
            })
            if result.get("status") != "PASS":
                failure = ET.SubElement(testcase, "failure", {
                    "message": "反向安全测试失败",
                    "type": result.get("test_case", "unknown"),
                })
                failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        return ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    return build_junit


@pytest.fixture(scope="session")
def gate_decision_builder():
    def build_gate_decision(policy_decision, test_results):
        all_pass = all(r.get("status") == "PASS" for r in test_results)
        return {
            "decision": "ALLOW" if all_pass and policy_decision.get("allow") else "BLOCK",
            "policy_decision": policy_decision,
            "test_results": test_results,
        }
    return build_gate_decision

