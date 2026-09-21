"""
pytest fixtures 为反向安全测试提供统一的构建产物、配置和断言工具
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def project_root():
    """项目根目录"""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def security_root(project_root):
    """security 目录"""
    return project_root / "security"


@pytest.fixture(scope="session")
def build_artifacts(project_root, security_root):
    """构建产物目录（APK/IPA/symbols）"""
    # 优先使用环境变量指定的目录
    artifact_env = os.environ.get("NEGATIVE_TEST_ARTIFACTS_DIR")
    if artifact_env:
        artifact_dir = Path(artifact_env)
    else:
        artifact_dir = security_root / "artifacts"
    
    # 确保目录存在
    artifact_dir.mkdir(parents=True, exist_ok=True)
    
    # 查找构建产物
    apk_candidates = list(artifact_dir.glob("**/app-release.apk"))
    if not apk_candidates:
        apk_candidates = list(artifact_dir.glob("**/*.apk"))
    
    ipa_candidates = list(artifact_dir.glob("**/*.ipa"))
    
    mapping_candidates = list(artifact_dir.glob("**/mapping.txt"))
    
    return {
        "apk": apk_candidates[0] if apk_candidates else None,
        "ipa": ipa_candidates[0] if ipa_candidates else None,
        "mapping": mapping_candidates[0] if mapping_candidates else None,
        "dir": artifact_dir
    }


@pytest.fixture(scope="session")
def build_config(project_root, security_root):
    """构建配置（从环境变量读取）"""
    return {
        "release": os.environ.get("BUILD_TYPE", "release") == "release",
        "obfuscate": os.environ.get("DART_OBFUSCATE", "true").lower() == "true",
        "split_debug_info": os.environ.get("SPLIT_DEBUG_INFO", "true").lower() == "true",
        "platform": os.environ.get("TARGET_PLATFORM", "android,ios"),
        "production_domains": os.environ.get("PRODUCTION_DOMAINS", "api.xxai.com,feed-api.xxai.com,auth.xxai.com").split(","),
        "production_associated_domains": os.environ.get(
            "PRODUCTION_ASSOCIATED_DOMAINS", "applinks:xxai.com"
        ).split(",")
    }


@pytest.fixture(scope="session")
def test_report_dir(project_root):
    """测试结果目录"""
    report_dir = project_root / "results"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


@pytest.fixture(scope="session")
def runner_command():
    """pytest 测试运行器"""
    return [sys.executable, "-m", "pytest"]


@pytest.fixture(scope="session")
def environment_profile():
    """构建环境配置"""
    return {
        "debug": os.environ.get("BUILD_ENV", "release") == "debug",
        "staging": os.environ.get("BUILD_ENV", "release") == "staging",
        "production": os.environ.get("BUILD_ENV", "release") == "production"
    }


@pytest.fixture(scope="session")
def allowlist_config(security_root):
    """白名单配置"""
    return security_root / "policies" / "allowlist.yaml"


@pytest.fixture(scope="session")
def opa_policy(security_root):
    """OPA 策略文件"""
    return security_root / "policies" / "negative.rego"


@pytest.fixture(scope="session")
def negative_test_suite(security_root):
    """反向安全测试套件"""
    return security_root / "tests"


@pytest.fixture(scope="session")
def gate_script(security_root):
    """发布门禁脚本"""
    return security_root / "scripts" / "gate_decision.py"


@pytest.fixture(scope="session")
def binary_integrity_script(security_root):
    """二进制完整性检查脚本"""
    return security_root / "scripts" / "check_binary_integrity.py"


@pytest.fixture(scope="session")
def dart_obfuscation_script(security_root):
    """Dart 混淆检查脚本"""
    return security_root / "scripts" / "check_dart_obfuscation.py"


@pytest.fixture(scope="session")
def mock_data_removal_script(security_root):
    """Mock 数据移除检查脚本"""
    return security_root / "scripts" / "check_mock_data_removal.py"


@pytest.fixture(scope="session")
def encryption_storage_script(security_root):
    """加密存储检查脚本"""
    return security_root / "scripts" / "check_encryption_storage.py"


@pytest.fixture(scope="session")
def log_isolation_script(security_root):
    """日志隔离检查脚本"""
    return security_root / "scripts" / "check_log_isolation.py"


@pytest.fixture(scope="session")
def ios_file_sharing_script(security_root):
    """iOS 文件共享检查脚本"""
    return security_root / "scripts" / "check_ios_file_sharing.py"


@pytest.fixture(scope="session")
def deep_link_isolation_script(security_root):
    """Android 深链隔离检查脚本"""
    return security_root / "scripts" / "check_deep_link_isolation.py"


@pytest.fixture(scope="session")
def domain_isolation_script(security_root):
    """域名隔离检查脚本"""
    return security_root / "scripts" / "check_domain_isolation.py"


@pytest.fixture(scope="session")
def debug_isolation_script(security_root):
    """调试隔离检查脚本"""
    return security_root / "scripts" / "check_debug_isolation.py"


@pytest.fixture(scope="session")
def test_artifacts_dir(test_report_dir):
    """测试产物目录"""
    return test_report_dir / "artifacts"


@pytest.fixture(scope="session")
def evidence_dir(test_report_dir):
    """证据目录"""
    return test_report_dir / "evidence"


@pytest.fixture(scope="session")
def junit_xml_path(test_report_dir):
    """JUnit XML 结果路径"""
    return test_report_dir / "negative_tests.xml"


@pytest.fixture(scope="session")
def sarif_path(test_report_dir):
    """SARIF 结果路径"""
    return test_report_dir / "negative_tests.sarif"


@pytest.fixture(scope="session")
def policy_decision_path(test_report_dir):
    """策略评估结果路径"""
    return test_report_dir / "policy_decision.json"


@pytest.fixture(scope="session")
def gate_decision_path(test_report_dir):
    """门禁决策结果路径"""
    return test_report_dir / "gate_decision.json"


@pytest.fixture(scope="session")
def run_command():
    """运行外部命令的辅助函数"""
    def run(command, timeout=120):
        """执行外部命令并返回结果"""
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": command
        }
    
    return run


@pytest.fixture(scope="session")
def assert_result_status(result):
    """统一的结果状态断言"""
    def assert_status(status, expected):
        """断言测试结果状态"""
        assert status == expected, f"Expected status {expected}, got {status}"
    
    return assert_status


@pytest.fixture(scope="session")
def fail_on_any_finding(result):
    """统一的结果判定函数"""
    def check(result):
        """检查测试结果是否通过"""
        return result.get("status") == "PASS"
    
    return check


@pytest.fixture(scope="session")
def collect_finding_count(result):
    """收集测试结果的 finding 数量"""
    def count(result):
        """计算 finding 数量"""
        findings = result.get("findings", [])
        return len(findings)
    
    return count


@pytest.fixture(scope="session")
def build_env():
    """构建环境信息"""
    return {
        "name": os.environ.get("BUILD_NAME", "release"),
        "environment": os.environ.get("BUILD_ENV", "release"),
        "version": os.environ.get("BUILD_VERSION", "unknown"),
        "version_code": os.environ.get("BUILD_VERSION_CODE", "unknown"),
        "platform": os.environ.get("TARGET_PLATFORM", "android,ios"),
        "artifact_dir": os.environ.get("NEGATIVE_TEST_ARTIFACTS_DIR", "security/artifacts")
    }


@pytest.fixture(scope="session")
def ci_context():
    """CI 上下文"""
    return {
        "ci": os.environ.get("CI", "false").lower() == "true",
        "ci_name": os.environ.get("CI_NAME", "unknown"),
        "ci_build_url": os.environ.get("CI_BUILD_URL", ""),
        "git_sha": os.environ.get("GIT_SHA", "unknown"),
        "git_branch": os.environ.get("GIT_BRANCH", "unknown")
    }


@pytest.fixture(scope="session")
def security_test_manifest():
    """反向安全测试清单（9 条规则）"""
    return [
        {
            "id": "NS-01",
            "name": "调试面板/抓包隔离",
            "script": "check_debug_isolation.py"
        },
        {
            "id": "NS-02",
            "name": "接口/域名/Associated Domains 隔离",
            "script": "check_domain_isolation.py"
        },
        {
            "id": "NS-03",
            "name": "Android 深链域名按构建环境隔离",
            "script": "check_deep_link_isolation.py"
        },
        {
            "id": "NS-04",
            "name": "日志输出按构建环境隔离",
            "script": "check_log_isolation.py"
        },
        {
            "id": "NS-05",
            "name": "登录态迁移至 Keychain/加密存储",
            "script": "check_encryption_storage.py"
        },
        {
            "id": "NS-06",
            "name": "关闭 iOS Documents 文件共享",
            "script": "check_ios_file_sharing.py"
        },
        {
            "id": "NS-07",
            "name": "移除生产包 mock 数据",
            "script": "check_mock_data_removal.py"
        },
        {
            "id": "NS-08",
            "name": "Flutter Release 启用 Dart 混淆与符号文件留存",
            "script": "check_dart_obfuscation.py"
        },
        {
            "id": "NS-09",
            "name": "发布前自动校验生产 IPA/APK",
            "script": "check_binary_integrity.py"
        }
    ]


@pytest.fixture(scope="session")
def security_test_rules(security_test_manifest):
    """安全测试规则列表"""
    return security_test_manifest


@pytest.fixture(scope="session")
def test_environment():
    """测试环境信息"""
    return {
        "ci": os.environ.get("CI", "false"),
        "platform": os.environ.get("TARGET_PLATFORM", "android,ios"),
        "artifacts_dir": os.environ.get("NEGATIVE_TEST_ARTIFACTS_DIR"),
        "build_type": os.environ.get("BUILD_TYPE", "release")
    }


@pytest.fixture(scope="session")
def gate_policy():
    """发布门禁策略"""
    return {
        "allow": False,
        "rules": [
            {
                "id": "NS-01",
                "name": "调试面板/抓包隔离",
                "status": "PASS"
            },
            {
                "id": "NS-02",
                "name": "接口/域名/Associated Domains 隔离",
                "status": "PASS"
            },
            {
                "id": "NS-03",
                "name": "Android 深链域名按构建环境隔离",
                "status": "PASS"
            },
            {
                "id": "NS-04",
                "name": "日志输出按构建环境隔离",
                "status": "PASS"
            },
            {
                "id": "NS-05",
                "name": "登录态迁移至 Keychain/加密存储",
                "status": "PASS"
            },
            {
                "id": "NS-06",
                "name": "关闭 iOS Documents 文件共享",
                "status": "PASS"
            },
            {
                "id": "NS-07",
                "name": "移除生产包 mock 数据",
                "status": "PASS"
            },
            {
                "id": "NS-08",
                "name": "Flutter Release 启用 Dart 混淆与符号文件留存",
                "status": "PASS"
            },
            {
                "id": "NS-09",
                "name": "发布前自动校验生产 IPA/APK",
                "status": "PASS"
            }
        ]
    }


@pytest.fixture(scope="session")
def negative_test_framework():
    """反向安全测试框架"""
    return {
        "scripts_dir": os.path.dirname(os.path.abspath(__file__)),
        "fixtures_dir": os.path.dirname(os.path.abspath(__file__)),
        "test_manifest": security_test_manifest,
        "gate_policy": gate_policy
    }


@pytest.fixture(scope="session")
def pytest_addoption(parser):
    """自定义 pytest 参数"""
    parser.addoption(
        "--negative-test-output",
        action="store",
        default=None,
        help="反向安全测试输出目录"
    )
    
    parser.addoption(
        "--negative-test-artifacts",
        action="store",
        default=None,
        help="构建产物目录"
    )
    
    parser.addoption(
        "--negative-test-platform",
        action="store",
        default="android,ios",
        help="测试平台（android/ios/android,ios）"
    )


@pytest.fixture(scope="session")
def pytest_configure(config):
    """pytest 配置钩子"""
    config._security_test_config = {
        "output_dir": os.environ.get("NEGATIVE_TEST_OUTPUT_DIR", "results"),
        "artifacts_dir": os.environ.get("NEGATIVE_TEST_ARTIFACTS_DIR", "security/artifacts"),
        "platform": os.environ.get("TARGET_PLATFORM", "android,ios")
    }


@pytest.fixture(scope="session")
def security_test_config():
    """安全测试配置"""
    return {
        "output_dir": os.environ.get("NEGATIVE_TEST_OUTPUT_DIR", "results"),
        "artifacts_dir": os.environ.get("NEGATIVE_TEST_ARTIFACTS_DIR", "security/artifacts"),
        "platform": os.environ.get("TARGET_PLATFORM", "android,ios"),
        "build_type": os.environ.get("BUILD_TYPE", "release")
    }


@pytest.fixture(scope="session")
def artifact_manifest():
    """构建产物清单"""
    return {
        "apk": None,
        "ipa": None,
        "mapping": None,
        "evidence": {}
    }


@pytest.fixture(scope="session")
def negative_test_results():
    """反向安全测试结果汇总"""
    return {
        "test_cases": [],
        "platforms": {},
        "status": "PASS",
        "total_findings": 0
    }


@pytest.fixture(scope="session")
def gate_input():
    """OPA 策略评估输入"""
    return {
        "platforms": ["android", "ios"],
        "required_rules": {
            "android": [f"NS-{i:02d}" for i in range(1, 10)],
            "ios": [f"NS-{i:02d}" for i in range(1, 10)]
        },
        "evidence": {
            "android": {
                "status": "PASS",
                "rules": [],
                "artifacts": {}
            },
            "ios": {
                "status": "PASS",
                "rules": [],
                "artifacts": {}
            }
        }
    }


@pytest.fixture(scope="session")
def sarif_builder():
    """SARIF 结果构建器"""
    def build_sarif(test_results, rules):
        """构建 SARIF 结果"""
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "informationUri": "https://github.com/xxai/security",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                                "defaultConfiguration": {
                                    "level": "error"
                                }
                            }
                            for rule in rules
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": rule["id"],
                        "level": "error",
                        "message": {
                            "text": f"{rule['name']} 未通过"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": rule.get("file", "security")
                                    }
                                }
                            }
                        ]
                    }
                    for rule in rules if rule.get("status") != "PASS"
                ]
            }]
        }
        
        return sarif
    
    return build_sarif


@pytest.fixture(scope="session")
def junit_builder():
    """JUnit XML 结果构建器"""
    def build_junit(test_results):
        """构建 JUnit XML 结果"""
        import xml.etree.ElementTree as ET
        
        testsuite = ET.Element("testsuite", {
            "name": "Negative Security Test",
            "tests": str(len(test_results)),
            "failures": str(sum(1 for r in test_results if r.get("status") != "PASS")),
            "errors": "0",
            "time": "0"
        })
        
        for result in test_results:
            testcase = ET.SubElement(
                testsuite,
                "testcase",
                {
                    "classname": result.get("test_case", "negative_security"),
                    "name": result.get("test_name", "unknown"),
                    "time": "0"
                }
            )
            
            if result.get("status") != "PASS":
                failure = ET.SubElement(
                    testcase,
                    "failure",
                    {
                        "message": "反向安全测试失败",
                        "type": result.get("test_case", "unknown")
                    }
                )
                failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        
        return ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    
    return build_junit


@pytest.fixture(scope="session")
def policy_input_builder():
    """策略评估输入构建器"""
    def build_policy_input(test_results, platform):
        """构建策略评估输入"""
        platform_evidence = {
            "status": "PASS",
            "rules": [
                {
                    "id": rule.get("id"),
                    "name": rule.get("name"),
                    "status": rule.get("status", "PASS"),
                    "evidence_file": rule.get("file", "security"),
                    "details": rule.get("details", {})
                }
                for rule in test_results
            ],
            "artifacts": {
                "apk": "build/app/outputs/flutter-apk/app-release.apk",
                "mapping_file": "build/symbols/android/mapping.txt"
            }
        }
        
        return {
            "platforms": [platform],
            "required_rules": {
                platform: [f"NS-{i:02d}" for i in range(1, 10)]
            },
            "evidence": {
                platform: platform_evidence
            }
        }
    
    return build_policy_input


@pytest.fixture(scope="session")
def sarif_rules():
    """SARIF 规则列表"""
    return [
        {
            "id": "NS-01",
            "name": "调试面板/抓包隔离",
            "status": "PASS"
        },
        {
            "id": "NS-02",
            "name": "接口/域名/Associated Domains 隔离",
            "status": "PASS"
        },
        {
            "id": "NS-03",
            "name": "Android 深链域名按构建环境隔离",
            "status": "PASS"
        },
        {
            "id": "NS-04",
            "name": "日志输出按构建环境隔离",
            "status": "PASS"
        },
        {
            "id": "NS-05",
            "name": "登录态迁移至 Keychain/加密存储",
            "status": "PASS"
        },
        {
            "id": "NS-06",
            "name": "关闭 iOS Documents 文件共享",
            "status": "PASS"
        },
        {
            "id": "NS-07",
            "name": "移除生产包 mock 数据",
            "status": "PASS"
        },
        {
            "id": "NS-08",
            "name": "Flutter Release 启用 Dart 混淆与符号文件留存",
            "status": "PASS"
        },
        {
            "id": "NS-09",
            "name": "发布前自动校验生产 IPA/APK",
            "status": "PASS"
        }
    ]


@pytest.fixture(scope="session")
def junit_rules():
    """JUnit 规则列表"""
    return sarif_rules


@pytest.fixture(scope="session")
def policy_rules():
    """策略规则列表"""
    return sarif_rules


@pytest.fixture(scope="session")
def sarif_rule_builder():
    """SARIF 规则构建器"""
    def build_sarif_rule(rule):
        """构建 SARIF 规则"""
        return {
            "id": rule["id"],
            "name": rule["name"],
            "shortDescription": {"text": rule["name"]},
            "defaultConfiguration": {
                "level": "error"
            }
        }
    
    return build_sarif_rule


@pytest.fixture(scope="session")
def junit_testcase_builder():
    """JUnit testcase 构建器"""
    def build_junit_testcase(result):
        """构建 JUnit testcase"""
        return {
            "classname": result.get("test_case", "negative_security"),
            "name": result.get("test_name", "unknown"),
            "time": "0"
        }
    
    return build_junit_testcase


@pytest.fixture(scope="session")
def junit_failure_builder():
    """JUnit failure 构建器"""
    def build_junit_failure(result):
        """构建 JUnit failure"""
        return {
            "message": "反向安全测试失败",
            "type": result.get("test_case", "unknown")
        }
    
    return build_junit_failure


@pytest.fixture(scope="session")
def sarif_result_builder():
    """SARIF result 构建器"""
    def build_sarif_result(rule):
        """构建 SARIF result"""
        return {
            "ruleId": rule["id"],
            "level": "error",
            "message": {
                "text": f"{rule['name']} 未通过"
            },
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": rule.get("file", "security")
                        }
                    }
                }
            ]
        }
    
    return build_sarif_result


@pytest.fixture(scope="session")
def junit_testcase_xml():
    """JUnit testcase XML 构建器"""
    def build_junit_testcase_xml(result):
        """构建 JUnit testcase XML"""
        import xml.etree.ElementTree as ET
        
        testcase = ET.Element("testcase", junit_testcase_builder(result))
        
        if result.get("status") != "PASS":
            failure = ET.SubElement(testcase, "failure", junit_failure_builder(result))
            failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        
        return testcase
    
    return build_junit_testcase_xml


@pytest.fixture(scope="session")
def policy_decision_builder():
    """策略评估结果构建器"""
    def build_policy_decision(policy_input, policy_result):
        """构建策略评估结果"""
        return {
            "policy": "negative.rego",
            "decision": policy_result,
            "input": policy_input,
            "evaluated_at": "now"
        }
    
    return build_policy_decision


@pytest.fixture(scope="session")
def gate_decision_builder():
    """门禁决策构建器"""
    def build_gate_decision(policy_decision, test_results):
        """构建门禁决策"""
        all_pass = all(result.get("status") == "PASS" for result in test_results)
        
        return {
            "decision": "ALLOW" if all_pass and policy_decision.get("allow") else "BLOCK",
            "policy_decision": policy_decision,
            "test_results": test_results,
            "evaluated_at": "now"
        }
    
    return build_gate_decision


@pytest.fixture(scope="session")
def test_report():
    """测试报告"""
    return {
        "generated_at": "now",
        "tests": [],
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0
        }
    }


@pytest.fixture(scope="session")
def test_result_collector():
    """测试结果收集器"""
    def collect(result, test_case, test_name):
        """收集测试结果"""
        return {
            "test_case": test_case,
            "test_name": test_name,
            "status": result.get("status", "UNKNOWN"),
            "details": result.get("details", {}),
            "findings": result.get("findings", [])
        }
    
    return collect


@pytest.fixture(scope="session")
def gate_fail_on_any_finding():
    """门禁失败判定"""
    def fail_on_any_finding(results):
        """任意 finding 即失败"""
        return any(result.get("findings") for result in results)
    
    return fail_on_any_finding


@pytest.fixture(scope="session")
def gate_allow_only_all_pass():
    """全部通过才允许"""
    def allow_only_all_pass(results):
        """全部通过才允许"""
        return all(result.get("status") == "PASS" for result in results)
    
    return allow_only_all_pass


@pytest.fixture(scope="session")
def gate_decision():
    """门禁决策结果"""
    return {
        "decision": "BLOCK",
        "policy_decision": None,
        "test_results": [],
        "evaluated_at": "now"
    }


@pytest.fixture(scope="session")
def sarif_report():
    """SARIF 报告"""
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "Negative Security Test",
                    "informationUri": "https://github.com/xxai/security",
                    "rules": []
                }
            },
            "results": []
        }]
    }


@pytest.fixture(scope="session")
def junit_report():
    """JUnit 报告"""
    return {
        "testsuite": {
            "name": "Negative Security Test",
            "tests": 0,
            "failures": 0,
            "errors": 0
        }
    }


@pytest.fixture(scope="session")
def policy_input():
    """策略评估输入"""
    return {
        "platforms": ["android", "ios"],
        "required_rules": {
            "android": [f"NS-{i:02d}" for i in range(1, 10)],
            "ios": [f"NS-{i:02d}" for i in range(1, 10)]
        },
        "evidence": {
            "android": {
                "status": "PASS",
                "rules": [],
                "artifacts": {}
            },
            "ios": {
                "status": "PASS",
                "rules": [],
                "artifacts": {}
            }
        }
    }


@pytest.fixture(scope="session")
def policy_decision():
    """策略评估结果"""
    return {
        "allow": False,
        "decision": "BLOCK"
    }


@pytest.fixture(scope="session")
def gate_output():
    """门禁输出"""
    return {
        "decision": "BLOCK",
        "policy_decision": None,
        "test_results": [],
        "evaluated_at": "now"
    }


@pytest.fixture(scope="session")
def sarif_builder_v2():
    """SARIF 构建器 v2"""
    def build_sarif_v2(results, rules):
        """构建 SARIF v2 结果"""
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                                "defaultConfiguration": {
                                    "level": "error"
                                }
                            }
                            for rule in rules
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": rule["id"],
                        "level": "error",
                        "message": {
                            "text": f"{rule['name']} 未通过"
                        }
                    }
                    for rule in rules if rule.get("status") != "PASS"
                ]
            }]
        }
        
        return sarif
    
    return build_sarif_v2


@pytest.fixture(scope="session")
def junit_builder_v2():
    """JUnit 构建器 v2"""
    def build_junit_v2(results):
        """构建 JUnit v2 结果"""
        import xml.etree.ElementTree as ET
        
        testsuite = ET.Element("testsuite", {
            "name": "Negative Security Test",
            "tests": str(len(results)),
            "failures": str(sum(1 for r in results if r.get("status") != "PASS")),
            "errors": "0",
            "time": "0"
        })
        
        for result in results:
            testcase = ET.SubElement(
                testsuite,
                "testcase",
                {
                    "classname": result.get("test_case", "negative_security"),
                    "name": result.get("test_name", "unknown"),
                    "time": "0"
                }
            )
            
            if result.get("status") != "PASS":
                failure = ET.SubElement(
                    testcase,
                    "failure",
                    {
                        "message": "反向安全测试失败",
                        "type": result.get("test_case", "unknown")
                    }
                )
                failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        
        return ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    
    return build_junit_v2


@pytest.fixture(scope="session")
def policy_input_builder_v2():
    """策略评估输入构建器 v2"""
    def build_policy_input_v2(results, platform):
        """构建策略评估输入 v2"""
        platform_evidence = {
            "status": "PASS",
            "rules": [
                {
                    "id": result.get("test_case", "NS-01"),
                    "name": result.get("test_name", "unknown"),
                    "status": result.get("status", "PASS"),
                    "evidence_file": result.get("file", "security"),
                    "details": result.get("details", {})
                }
                for result in results
            ],
            "artifacts": {
                "apk": "build/app/outputs/flutter-apk/app-release.apk",
                "mapping_file": "build/symbols/android/mapping.txt"
            }
        }
        
        return {
            "platforms": [platform],
            "required_rules": {
                platform: [f"NS-{i:02d}" for i in range(1, 10)]
            },
            "evidence": {
                platform: platform_evidence
            }
        }
    
    return build_policy_input_v2


@pytest.fixture(scope="session")
def policy_decision_builder_v2():
    """策略评估结果构建器 v2"""
    def build_policy_decision_v2(policy_input, policy_result):
        """构建策略评估结果 v2"""
        return {
            "policy": "negative.rego",
            "decision": policy_result,
            "input": policy_input,
            "evaluated_at": "now"
        }
    
    return build_policy_decision_v2


@pytest.fixture(scope="session")
def gate_decision_builder_v2():
    """门禁决策构建器 v2"""
    def build_gate_decision_v2(policy_decision, test_results):
        """构建门禁决策 v2"""
        all_pass = all(result.get("status") == "PASS" for result in test_results)
        
        return {
            "decision": "ALLOW" if all_pass and policy_decision.get("allow") else "BLOCK",
            "policy_decision": policy_decision,
            "test_results": test_results,
            "evaluated_at": "now"
        }
    
    return build_gate_decision_v2


@pytest.fixture(scope="session")
def sarif_builder_v3():
    """SARIF 构建器 v3"""
    def build_sarif_v3(results, rules):
        """构建 SARIF v3 结果"""
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                                "defaultConfiguration": {
                                    "level": "error"
                                }
                            }
                            for rule in rules
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": rule["id"],
                        "level": "error",
                        "message": {
                            "text": f"{rule['name']} 未通过"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": rule.get("file", "security")
                                    }
                                }
                            }
                        ]
                    }
                    for rule in rules if rule.get("status") != "PASS"
                ]
            }]
        }
        
        return sarif
    
    return build_sarif_v3


@pytest.fixture(scope="session")
def junit_builder_v3():
    """JUnit 构建器 v3"""
    def build_junit_v3(results):
        """构建 JUnit v3 结果"""
        import xml.etree.ElementTree as ET
        
        testsuite = ET.Element("testsuite", {
            "name": "Negative Security Test",
            "tests": str(len(results)),
            "failures": str(sum(1 for r in results if r.get("status") != "PASS")),
            "errors": "0",
            "time": "0"
        })
        
        for result in results:
            testcase = ET.SubElement(
                testsuite,
                "testcase",
                {
                    "classname": result.get("test_case", "negative_security"),
                    "name": result.get("test_name", "unknown"),
                    "time": "0"
                }
            )
            
            if result.get("status") != "PASS":
                failure = ET.SubElement(
                    testcase,
                    "failure",
                    {
                        "message": "反向安全测试失败",
                        "type": result.get("test_case", "unknown")
                    }
                )
                failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        
        return ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    
    return build_junit_v3


@pytest.fixture(scope="session")
def policy_input_builder_v3():
    """策略评估输入构建器 v3"""
    def build_policy_input_v3(results, platform):
        """构建策略评估输入 v3"""
        platform_evidence = {
            "status": "PASS",
            "rules": [
                {
                    "id": result.get("test_case", "NS-01"),
                    "name": result.get("test_name", "unknown"),
                    "status": result.get("status", "PASS"),
                    "evidence_file": result.get("file", "security"),
                    "details": result.get("details", {})
                }
                for result in results
            ],
            "artifacts": {
                "apk": "build/app/outputs/flutter-apk/app-release.apk",
                "mapping_file": "build/symbols/android/mapping.txt"
            }
        }
        
        return {
            "platforms": [platform],
            "required_rules": {
                platform: [f"NS-{i:02d}" for i in range(1, 10)]
            },
            "evidence": {
                platform: platform_evidence
            }
        }
    
    return build_policy_input_v3


@pytest.fixture(scope="session")
def policy_decision_builder_v3():
    """策略评估结果构建器 v3"""
    def build_policy_decision_v3(policy_input, policy_result):
        """构建策略评估结果 v3"""
        return {
            "policy": "negative.rego",
            "decision": policy_result,
            "input": policy_input,
            "evaluated_at": "now"
        }
    
    return build_policy_decision_v3


@pytest.fixture(scope="session")
def gate_decision_builder_v3():
    """门禁决策构建器 v3"""
    def build_gate_decision_v3(policy_decision, test_results):
        """构建门禁决策 v3"""
        all_pass = all(result.get("status") == "PASS" for result in test_results)
        
        return {
            "decision": "ALLOW" if all_pass and policy_decision.get("allow") else "BLOCK",
            "policy_decision": policy_decision,
            "test_results": test_results,
            "evaluated_at": "now"
        }
    
    return build_gate_decision_v3


@pytest.fixture(scope="session")
def sarif_builder_v4():
    """SARIF 构建器 v4"""
    def build_sarif_v4(results, rules):
        """构建 SARIF v4 结果"""
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                                "defaultConfiguration": {
                                    "level": "error"
                                }
                            }
                            for rule in rules
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": rule["id"],
                        "level": "error",
                        "message": {
                            "text": f"{rule['name']} 未通过"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": rule.get("file", "security")
                                    }
                                }
                            }
                        ]
                    }
                    for rule in rules if rule.get("status") != "PASS"
                ]
            }]
        }
        
        return sarif
    
    return build_sarif_v4


@pytest.fixture(scope="session")
def junit_builder_v4():
    """JUnit 构建器 v4"""
    def build_junit_v4(results):
        """构建 JUnit v4 结果"""
        import xml.etree.ElementTree as ET
        
        testsuite = ET.Element("testsuite", {
            "name": "Negative Security Test",
            "tests": str(len(results)),
            "failures": str(sum(1 for r in results if r.get("status") != "PASS")),
            "errors": "0",
            "time": "0"
        })
        
        for result in results:
            testcase = ET.SubElement(
                testsuite,
                "testcase",
                {
                    "classname": result.get("test_case", "negative_security"),
                    "name": result.get("test_name", "unknown"),
                    "time": "0"
                }
            )
            
            if result.get("status") != "PASS":
                failure = ET.SubElement(
                    testcase,
                    "failure",
                    {
                        "message": "反向安全测试失败",
                        "type": result.get("test_case", "unknown")
                    }
                )
                failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        
        return ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    
    return build_junit_v4


@pytest.fixture(scope="session")
def policy_input_builder_v4():
    """策略评估输入构建器 v4"""
    def build_policy_input_v4(results, platform):
        """构建策略评估输入 v4"""
        platform_evidence = {
            "status": "PASS",
            "rules": [
                {
                    "id": result.get("test_case", "NS-01"),
                    "name": result.get("test_name", "unknown"),
                    "status": result.get("status", "PASS"),
                    "evidence_file": result.get("file", "security"),
                    "details": result.get("details", {})
                }
                for result in results
            ],
            "artifacts": {
                "apk": "build/app/outputs/flutter-apk/app-release.apk",
                "mapping_file": "build/symbols/android/mapping.txt"
            }
        }
        
        return {
            "platforms": [platform],
            "required_rules": {
                platform: [f"NS-{i:02d}" for i in range(1, 10)]
            },
            "evidence": {
                platform: platform_evidence
            }
        }
    
    return build_policy_input_v4


@pytest.fixture(scope="session")
def policy_decision_builder_v4():
    """策略评估结果构建器 v4"""
    def build_policy_decision_v4(policy_input, policy_result):
        """构建策略评估结果 v4"""
        return {
            "policy": "negative.rego",
            "decision": policy_result,
            "input": policy_input,
            "evaluated_at": "now"
        }
    
    return build_policy_decision_v4


@pytest.fixture(scope="session")
def gate_decision_builder_v4():
    """门禁决策构建器 v4"""
    def build_gate_decision_v4(policy_decision, test_results):
        """构建门禁决策 v4"""
        all_pass = all(result.get("status") == "PASS" for result in test_results)
        
        return {
            "decision": "ALLOW" if all_pass and policy_decision.get("allow") else "BLOCK",
            "policy_decision": policy_decision,
            "test_results": test_results,
            "evaluated_at": "now"
        }
    
    return build_gate_decision_v4


@pytest.fixture(scope="session")
def sarif_builder_v5():
    """SARIF 构建器 v5"""
    def build_sarif_v5(results, rules):
        """构建 SARIF v5 结果"""
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                                "defaultConfiguration": {
                                    "level": "error"
                                }
                            }
                            for rule in rules
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": rule["id"],
                        "level": "error",
                        "message": {
                            "text": f"{rule['name']} 未通过"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": rule.get("file", "security")
                                    }
                                }
                            }
                        ]
                    }
                    for rule in rules if rule.get("status") != "PASS"
                ]
            }]
        }
        
        return sarif
    
    return build_sarif_v5


@pytest.fixture(scope="session")
def junit_builder_v5():
    """JUnit 构建器 v5"""
    def build_junit_v5(results):
        """构建 JUnit v5 结果"""
        import xml.etree.ElementTree as ET
        
        testsuite = ET.Element("testsuite", {
            "name": "Negative Security Test",
            "tests": str(len(results)),
            "failures": str(sum(1 for r in results if r.get("status") != "PASS")),
            "errors": "0",
            "time": "0"
        })
        
        for result in results:
            testcase = ET.SubElement(
                testsuite,
                "testcase",
                {
                    "classname": result.get("test_case", "negative_security"),
                    "name": result.get("test_name", "unknown"),
                    "time": "0"
                }
            )
            
            if result.get("status") != "PASS":
                failure = ET.SubElement(
                    testcase,
                    "failure",
                    {
                        "message": "反向安全测试失败",
                        "type": result.get("test_case", "unknown")
                    }
                )
                failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        
        return ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    
    return build_junit_v5


@pytest.fixture(scope="session")
def policy_input_builder_v5():
    """策略评估输入构建器 v5"""
    def build_policy_input_v5(results, platform):
        """构建策略评估输入 v5"""
        platform_evidence = {
            "status": "PASS",
            "rules": [
                {
                    "id": result.get("test_case", "NS-01"),
                    "name": result.get("test_name", "unknown"),
                    "status": result.get("status", "PASS"),
                    "evidence_file": result.get("file", "security"),
                    "details": result.get("details", {})
                }
                for result in results
            ],
            "artifacts": {
                "apk": "build/app/outputs/flutter-apk/app-release.apk",
                "mapping_file": "build/symbols/android/mapping.txt"
            }
        }
        
        return {
            "platforms": [platform],
            "required_rules": {
                platform: [f"NS-{i:02d}" for i in range(1, 10)]
            },
            "evidence": {
                platform: platform_evidence
            }
        }
    
    return build_policy_input_v5


@pytest.fixture(scope="session")
def policy_decision_builder_v5():
    """策略评估结果构建器 v5"""
    def build_policy_decision_v5(policy_input, policy_result):
        """构建策略评估结果 v5"""
        return {
            "policy": "negative.rego",
            "decision": policy_result,
            "input": policy_input,
            "evaluated_at": "now"
        }
    
    return build_policy_decision_v5


@pytest.fixture(scope="session")
def gate_decision_builder_v5():
    """门禁决策构建器 v5"""
    def build_gate_decision_v5(policy_decision, test_results):
        """构建门禁决策 v5"""
        all_pass = all(result.get("status") == "PASS" for result in test_results)
        
        return {
            "decision": "ALLOW" if all_pass and policy_decision.get("allow") else "BLOCK",
            "policy_decision": policy_decision,
            "test_results": test_results,
            "evaluated_at": "now"
        }
    
    return build_gate_decision_v5


@pytest.fixture(scope="session")
def sarif_builder_v6():
    """SARIF 构建器 v6"""
    def build_sarif_v6(results, rules):
        """构建 SARIF v6 结果"""
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                                "defaultConfiguration": {
                                    "level": "error"
                                }
                            }
                            for rule in rules
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": rule["id"],
                        "level": "error",
                        "message": {
                            "text": f"{rule['name']} 未通过"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": rule.get("file", "security")
                                    }
                                }
                            }
                        ]
                    }
                    for rule in rules if rule.get("status") != "PASS"
                ]
            }]
        }
        
        return sarif
    
    return build_sarif_v6


@pytest.fixture(scope="session")
def junit_builder_v6():
    """JUnit 构建器 v6"""
    def build_junit_v6(results):
        """构建 JUnit v6 结果"""
        import xml.etree.ElementTree as ET
        
        testsuite = ET.Element("testsuite", {
            "name": "Negative Security Test",
            "tests": str(len(results)),
            "failures": str(sum(1 for r in results if r.get("status") != "PASS")),
            "errors": "0",
            "time": "0"
        })
        
        for result in results:
            testcase = ET.SubElement(
                testsuite,
                "testcase",
                {
                    "classname": result.get("test_case", "negative_security"),
                    "name": result.get("test_name", "unknown"),
                    "time": "0"
                }
            )
            
            if result.get("status") != "PASS":
                failure = ET.SubElement(
                    testcase,
                    "failure",
                    {
                        "message": "反向安全测试失败",
                        "type": result.get("test_case", "unknown")
                    }
                )
                failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        
        return ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    
    return build_junit_v6


@pytest.fixture(scope="session")
def policy_input_builder_v6():
    """策略评估输入构建器 v6"""
    def build_policy_input_v6(results, platform):
        """构建策略评估输入 v6"""
        platform_evidence = {
            "status": "PASS",
            "rules": [
                {
                    "id": result.get("test_case", "NS-01"),
                    "name": result.get("test_name", "unknown"),
                    "status": result.get("status", "PASS"),
                    "evidence_file": result.get("file", "security"),
                    "details": result.get("details", {})
                }
                for result in results
            ],
            "artifacts": {
                "apk": "build/app/outputs/flutter-apk/app-release.apk",
                "mapping_file": "build/symbols/android/mapping.txt"
            }
        }
        
        return {
            "platforms": [platform],
            "required_rules": {
                platform: [f"NS-{i:02d}" for i in range(1, 10)]
            },
            "evidence": {
                platform: platform_evidence
            }
        }
    
    return build_policy_input_v6


@pytest.fixture(scope="session")
def policy_decision_builder_v6():
    """策略评估结果构建器 v6"""
    def build_policy_decision_v6(policy_input, policy_result):
        """构建策略评估结果 v6"""
        return {
            "policy": "negative.rego",
            "decision": policy_result,
            "input": policy_input,
            "evaluated_at": "now"
        }
    
    return build_policy_decision_v6


@pytest.fixture(scope="session")
def gate_decision_builder_v6():
    """门禁决策构建器 v6"""
    def build_gate_decision_v6(policy_decision, test_results):
        """构建门禁决策 v6"""
        all_pass = all(result.get("status") == "PASS" for result in test_results)
        
        return {
            "decision": "ALLOW" if all_pass and policy_decision.get("allow") else "BLOCK",
            "policy_decision": policy_decision,
            "test_results": test_results,
            "evaluated_at": "now"
        }
    
    return build_gate_decision_v6


@pytest.fixture(scope="session")
def sarif_builder_v7():
    """SARIF 构建器 v7"""
    def build_sarif_v7(results, rules):
        """构建 SARIF v7 结果"""
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                                "defaultConfiguration": {
                                    "level": "error"
                                }
                            }
                            for rule in rules
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": rule["id"],
                        "level": "error",
                        "message": {
                            "text": f"{rule['name']} 未通过"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": rule.get("file", "security")
                                    }
                                }
                            }
                        ]
                    }
                    for rule in rules if rule.get("status") != "PASS"
                ]
            }]
        }
        
        return sarif
    
    return build_sarif_v7


@pytest.fixture(scope="session")
def junit_builder_v7():
    """JUnit 构建器 v7"""
    def build_junit_v7(results):
        """构建 JUnit v7 结果"""
        import xml.etree.ElementTree as ET
        
        testsuite = ET.Element("testsuite", {
            "name": "Negative Security Test",
            "tests": str(len(results)),
            "failures": str(sum(1 for r in results if r.get("status") != "PASS")),
            "errors": "0",
            "time": "0"
        })
        
        for result in results:
            testcase = ET.SubElement(
                testsuite,
                "testcase",
                {
                    "classname": result.get("test_case", "negative_security"),
                    "name": result.get("test_name", "unknown"),
                    "time": "0"
                }
            )
            
            if result.get("status") != "PASS":
                failure = ET.SubElement(
                    testcase,
                    "failure",
                    {
                        "message": "反向安全测试失败",
                        "type": result.get("test_case", "unknown")
                    }
                )
                failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        
        return ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    
    return build_junit_v7


@pytest.fixture(scope="session")
def policy_input_builder_v7():
    """策略评估输入构建器 v7"""
    def build_policy_input_v7(results, platform):
        """构建策略评估输入 v7"""
        platform_evidence = {
            "status": "PASS",
            "rules": [
                {
                    "id": result.get("test_case", "NS-01"),
                    "name": result.get("test_name", "unknown"),
                    "status": result.get("status", "PASS"),
                    "evidence_file": result.get("file", "security"),
                    "details": result.get("details", {})
                }
                for result in results
            ],
            "artifacts": {
                "apk": "build/app/outputs/flutter-apk/app-release.apk",
                "mapping_file": "build/symbols/android/mapping.txt"
            }
        }
        
        return {
            "platforms": [platform],
            "required_rules": {
                platform: [f"NS-{i:02d}" for i in range(1, 10)]
            },
            "evidence": {
                platform: platform_evidence
            }
        }
    
    return build_policy_input_v7


@pytest.fixture(scope="session")
def policy_decision_builder_v7():
    """策略评估结果构建器 v7"""
    def build_policy_decision_v7(policy_input, policy_result):
        """构建策略评估结果 v7"""
        return {
            "policy": "negative.rego",
            "decision": policy_result,
            "input": policy_input,
            "evaluated_at": "now"
        }
    
    return build_policy_decision_v7


@pytest.fixture(scope="session")
def gate_decision_builder_v7():
    """门禁决策构建器 v7"""
    def build_gate_decision_v7(policy_decision, test_results):
        """构建门禁决策 v7"""
        all_pass = all(result.get("status") == "PASS" for result in test_results)
        
        return {
            "decision": "ALLOW" if all_pass and policy_decision.get("allow") else "BLOCK",
            "policy_decision": policy_decision,
            "test_results": test_results,
            "evaluated_at": "now"
        }
    
    return build_gate_decision_v7


@pytest.fixture(scope="session")
def sarif_builder_v8():
    """SARIF 构建器 v8"""
    def build_sarif_v8(results, rules):
        """构建 SARIF v8 结果"""
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                                "defaultConfiguration": {
                                    "level": "error"
                                }
                            }
                            for rule in rules
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": rule["id"],
                        "level": "error",
                        "message": {
                            "text": f"{rule['name']} 未通过"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": rule.get("file", "security")
                                    }
                                }
                            }
                        ]
                    }
                    for rule in rules if rule.get("status") != "PASS"
                ]
            }]
        }
        
        return sarif
    
    return build_sarif_v8


@pytest.fixture(scope="session")
def junit_builder_v8():
    """JUnit 构建器 v8"""
    def build_junit_v8(results):
        """构建 JUnit v8 结果"""
        import xml.etree.ElementTree as ET
        
        testsuite = ET.Element("testsuite", {
            "name": "Negative Security Test",
            "tests": str(len(results)),
            "failures": str(sum(1 for r in results if r.get("status") != "PASS")),
            "errors": "0",
            "time": "0"
        })
        
        for result in results:
            testcase = ET.SubElement(
                testsuite,
                "testcase",
                {
                    "classname": result.get("test_case", "negative_security"),
                    "name": result.get("test_name", "unknown"),
                    "time": "0"
                }
            )
            
            if result.get("status") != "PASS":
                failure = ET.SubElement(
                    testcase,
                    "failure",
                    {
                        "message": "反向安全测试失败",
                        "type": result.get("test_case", "unknown")
                    }
                )
                failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        
        return ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    
    return build_junit_v8


@pytest.fixture(scope="session")
def policy_input_builder_v8():
    """策略评估输入构建器 v8"""
    def build_policy_input_v8(results, platform):
        """构建策略评估输入 v8"""
        platform_evidence = {
            "status": "PASS",
            "rules": [
                {
                    "id": result.get("test_case", "NS-01"),
                    "name": result.get("test_name", "unknown"),
                    "status": result.get("status", "PASS"),
                    "evidence_file": result.get("file", "security"),
                    "details": result.get("details", {})
                }
                for result in results
            ],
            "artifacts": {
                "apk": "build/app/outputs/flutter-apk/app-release.apk",
                "mapping_file": "build/symbols/android/mapping.txt"
            }
        }
        
        return {
            "platforms": [platform],
            "required_rules": {
                platform: [f"NS-{i:02d}" for i in range(1, 10)]
            },
            "evidence": {
                platform: platform_evidence
            }
        }
    
    return build_policy_input_v8


@pytest.fixture(scope="session")
def policy_decision_builder_v8():
    """策略评估结果构建器 v8"""
    def build_policy_decision_v8(policy_input, policy_result):
        """构建策略评估结果 v8"""
        return {
            "policy": "negative.rego",
            "decision": policy_result,
            "input": policy_input,
            "evaluated_at": "now"
        }
    
    return build_policy_decision_v8


@pytest.fixture(scope="session")
def gate_decision_builder_v8():
    """门禁决策构建器 v8"""
    def build_gate_decision_v8(policy_decision, test_results):
        """构建门禁决策 v8"""
        all_pass = all(result.get("status") == "PASS" for result in test_results)
        
        return {
            "decision": "ALLOW" if all_pass and policy_decision.get("allow") else "BLOCK",
            "policy_decision": policy_decision,
            "test_results": test_results,
            "evaluated_at": "now"
        }
    
    return build_gate_decision_v8


@pytest.fixture(scope="session")
def sarif_builder_v9():
    """SARIF 构建器 v9"""
    def build_sarif_v9(results, rules):
        """构建 SARIF v9 结果"""
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                                "defaultConfiguration": {
                                    "level": "error"
                                }
                            }
                            for rule in rules
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": rule["id"],
                        "level": "error",
                        "message": {
                            "text": f"{rule['name']} 未通过"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": rule.get("file", "security")
                                    }
                                }
                            }
                        ]
                    }
                    for rule in rules if rule.get("status") != "PASS"
                ]
            }]
        }
        
        return sarif
    
    return build_sarif_v9


@pytest.fixture(scope="session")
def junit_builder_v9():
    """JUnit 构建器 v9"""
    def build_junit_v9(results):
        """构建 JUnit v9 结果"""
        import xml.etree.ElementTree as ET
        
        testsuite = ET.Element("testsuite", {
            "name": "Negative Security Test",
            "tests": str(len(results)),
            "failures": str(sum(1 for r in results if r.get("status") != "PASS")),
            "errors": "0",
            "time": "0"
        })
        
        for result in results:
            testcase = ET.SubElement(
                testsuite,
                "testcase",
                {
                    "classname": result.get("test_case", "negative_security"),
                    "name": result.get("test_name", "unknown"),
                    "time": "0"
                }
            )
            
            if result.get("status") != "PASS":
                failure = ET.SubElement(
                    testcase,
                    "failure",
                    {
                        "message": "反向安全测试失败",
                        "type": result.get("test_case", "unknown")
                    }
                )
                failure.text = json.dumps(result, ensure_ascii=False, indent=2)
        
        return ET.tostring(testsuite, encoding="utf-8", xml_declaration=True)
    
    return build_junit_v9


@pytest.fixture(scope="session")
def policy_input_builder_v9():
    """策略评估输入构建器 v9"""
    def build_policy_input_v9(results, platform):
        """构建策略评估输入 v9"""
        platform_evidence = {
            "status": "PASS",
            "rules": [
                {
                    "id": result.get("test_case", "NS-01"),
                    "name": result.get("test_name", "unknown"),
                    "status": result.get("status", "PASS"),
                    "evidence_file": result.get("file", "security"),
                    "details": result.get("details", {})
                }
                for result in results
            ],
            "artifacts": {
                "apk": "build/app/outputs/flutter-apk/app-release.apk",
                "mapping_file": "build/symbols/android/mapping.txt"
            }
        }
        
        return {
            "platforms": [platform],
            "required_rules": {
                platform: [f"NS-{i:02d}" for i in range(1, 10)]
            },
            "evidence": {
                platform: platform_evidence
            }
        }
    
    return build_policy_input_v9


@pytest.fixture(scope="session")
def policy_decision_builder_v9():
    """策略评估结果构建器 v9"""
    def build_policy_decision_v9(policy_input, policy_result):
        """构建策略评估结果 v9"""
        return {
            "policy": "negative.rego",
            "decision": policy_result,
            "input": policy_input,
            "evaluated_at": "now"
        }
    
    return build_policy_decision_v9


@pytest.fixture(scope="session")
def gate_decision_builder_v9():
    """门禁决策构建器 v9"""
    def build_gate_decision_v9(policy_decision, test_results):
        """构建门禁决策 v9"""
        all_pass = all(result.get("status") == "PASS" for result in test_results)
        
        return {
            "decision": "ALLOW" if all_pass and policy_decision.get("allow") else "BLOCK",
            "policy_decision": policy_decision,
            "test_results": test_results,
            "evaluated_at": "now"
        }
    
    return build_gate_decision_v9


@pytest.fixture(scope="session")
def sarif_builder_v10():
    """SARIF 构建器 v10"""
    def build_sarif_v10(results, rules):
        """构建 SARIF v10 结果"""
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "Negative Security Test",
                        "rules": [
                            {
                                "id": rule["id"],
                                "name": rule["name"],
                                "shortDescription": {"text": rule["name"]},
                                "defaultConfiguration": {
                                    "level": "error"
                                }
                            }
                            for rule in rules
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": rule["id"],
                        "level": "error",
                        "message": {
                            "text": f"{rule['name']} 未通过"
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {
                                        "uri": rule.get("file", "security")
                                    }
                                }
                            }
                        ]
                    }
                    for rule in rules if rule.get("status") != "PASS"
                ]
            }]
        }
        
        return sarif
    
    return build_sarif_v10


@pytest.fixture(scope="session")
def junit_builder_v10():
    """JUnit 构建器 v10"""
    def build_junit_v10(results):
        """构建 JUnit