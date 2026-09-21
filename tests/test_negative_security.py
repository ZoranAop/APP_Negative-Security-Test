"""
负向安全测试框架 - pytest 测试用例
"""

import sys
import json
import pytest
import subprocess
from pathlib import Path


def run_test_script(script_path, **kwargs):
    """运行单项测试脚本"""
    cmd = [sys.executable, str(script_path)]
    for key, value in kwargs.items():
        if value is not None:
            cmd.append(f"--{key.replace('_', '-')}")
            cmd.append(str(value))
    result = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "path": str(script_path)
    }


class NegativeSecurityTest:
    """负向安全测试基类"""

    def __init__(self, test_case, test_name, script_path):
        self.test_case = test_case
        self.test_name = test_name
        self.script_path = script_path
        self.result = None

    def run(self, **kwargs):
        """运行测试"""
        self.result = run_test_script(self.script_path, **kwargs)
        return self.result

    def assert_pass(self):
        """断言通过"""
        assert self.result["returncode"] == 0, (
            f"{self.test_name} 失败: {self.result['stderr']}"
        )

    def assert_fail(self):
        """断言失败"""
        assert self.result["returncode"] != 0, (
            f"{self.test_name} 应该失败，但实际返回 0: {self.result['stdout']}"
        )


class TestNegativeSecurity:
    """负向安全测试集"""

    def test_debug_isolation(self, security_root, build_artifacts, test_report_dir):
        """NS-01: 调试面板/抓包隔离"""
        script_path = security_root / "scripts" / "check_debug_isolation.py"
        test = NegativeSecurityTest("NS-01", "调试面板/抓包隔离", script_path)
        result = test.run(
            apk=build_artifacts.get("apk"),
            ipa=build_artifacts.get("ipa"),
            manifest=build_artifacts.get("manifest"),
            info_plist=build_artifacts.get("info_plist"),
            output_json=test_report_dir / "test_debug.json"
        )
        test.assert_pass()

    def test_domain_isolation(self, security_root, build_artifacts, test_report_dir):
        """NS-02: 接口/域名/Associated Domains 隔离"""
        script_path = security_root / "scripts" / "check_domain_isolation.py"
        test = NegativeSecurityTest("NS-02", "接口/域名/Associated Domains 隔离", script_path)
        result = test.run(
            manifest=build_artifacts.get("manifest"),
            info_plist=build_artifacts.get("info_plist"),
            artifacts_dir=build_artifacts.get("dir"),
            output_json=test_report_dir / "test_domain.json"
        )
        test.assert_pass()

    def test_deep_link_isolation(self, security_root, build_artifacts, test_report_dir):
        """NS-03: Android 深链域名按构建环境隔离"""
        script_path = security_root / "scripts" / "check_deep_link_isolation.py"
        test = NegativeSecurityTest("NS-03", "Android 深链域名按构建环境隔离", script_path)
        result = test.run(
            manifest=build_artifacts.get("manifest"),
            output_json=test_report_dir / "test_deep_link.json"
        )
        test.assert_pass()

    def test_log_isolation(self, security_root, build_artifacts, test_report_dir):
        """NS-04: 日志输出按构建环境隔离"""
        script_path = security_root / "scripts" / "check_log_isolation.py"
        test = NegativeSecurityTest("NS-04", "日志输出按构建环境隔离", script_path)
        result = test.run(
            log_dir="logs",
            apk=build_artifacts.get("apk"),
            output_json=test_report_dir / "test_log.json"
        )
        test.assert_pass()

    def test_encryption_storage(self, security_root, build_artifacts, test_report_dir):
        """NS-05: 登录态迁移至 Keychain/加密存储"""
        script_path = security_root / "scripts" / "check_encryption_storage.py"
        test = NegativeSecurityTest("NS-05", "登录态迁移至 Keychain/加密存储", script_path)
        result = test.run(
            apk=build_artifacts.get("apk"),
            ipa=build_artifacts.get("ipa"),
            hive_files=list(Path("build/symbols/ios").glob("*.hive")) if Path("build/symbols/ios").exists() else None,
            output_json=test_report_dir / "test_encryption.json"
        )
        test.assert_pass()

    def test_ios_file_sharing(self, security_root, build_artifacts, test_report_dir):
        """NS-06: 关闭 iOS Documents 文件共享"""
        script_path = security_root / "scripts" / "check_ios_file_sharing.py"
        test = NegativeSecurityTest("NS-06", "关闭 iOS Documents 文件共享", script_path)
        result = test.run(
            info_plist=build_artifacts.get("info_plist"),
            ipa=build_artifacts.get("ipa"),
            artifacts_dir=build_artifacts.get("dir"),
            output_json=test_report_dir / "test_ios_sharing.json"
        )
        test.assert_pass()

    def test_mock_data_removal(self, security_root, build_artifacts, test_report_dir):
        """NS-07: 移除生产包 mock 数据"""
        script_path = security_root / "scripts" / "check_mock_data_removal.py"
        test = NegativeSecurityTest("NS-07", "移除生产包 mock 数据", script_path)
        result = test.run(
            apk=build_artifacts.get("apk"),
            ipa=build_artifacts.get("ipa"),
            pubspec=build_artifacts.get("pubspec"),
            dart_lib=build_artifacts.get("dart_lib"),
            assets_dir=build_artifacts.get("assets_dir"),
            output_json=test_report_dir / "test_mock.json"
        )
        test.assert_pass()

    def test_dart_obfuscation(self, security_root, build_artifacts, test_report_dir):
        """NS-08: Flutter Release 启用 Dart 混淆与符号文件留存"""
        script_path = security_root / "scripts" / "check_dart_obfuscation.py"
        test = NegativeSecurityTest("NS-08", "Flutter Release 启用 Dart 混淆与符号文件留存", script_path)
        result = test.run(
            apk=build_artifacts.get("apk"),
            ipa=build_artifacts.get("ipa"),
            artifacts_dir=build_artifacts.get("dir"),
            build_log=build_artifacts.get("build_log"),
            output_json=test_report_dir / "test_obfuscation.json"
        )
        test.assert_pass()

    def test_binary_integrity(self, security_root, build_artifacts, test_report_dir):
        """NS-09: 发布前自动校验生产 IPA/APK"""
        script_path = security_root / "scripts" / "check_binary_integrity.py"
        test = NegativeSecurityTest("NS-09", "发布前自动校验生产 IPA/APK", script_path)
        result = test.run(
            apk=build_artifacts.get("apk"),
            ipa=build_artifacts.get("ipa"),
            manifest=build_artifacts.get("manifest"),
            info_plist=build_artifacts.get("info_plist"),
            expected_cert_fingerprint=build_artifacts.get("expected_cert_fingerprint"),
            output_json=test_report_dir / "test_binary.json"
        )
        test.assert_pass()


def pytest_configure(config):
    """pytest 配置钩子"""
    config._security_test_config = {
        "test_cases": [
            "NS-01-debug-isolation",
            "NS-02-domain-isolation",
            "NS-03-deep-link-isolation",
            "NS-04-log-isolation",
            "NS-05-encryption-storage",
            "NS-06-ios-file-sharing",
            "NS-07-mock-data-removal",
            "NS-08-dart-obfuscation",
            "NS-09-binary-integrity"
        ]
    }


@pytest.fixture(scope="session")
def all_negative_test_cases():
    """所有负向测试用例"""
    return [
        {"id": "NS-01", "name": "调试面板/抓包隔离"},
        {"id": "NS-02", "name": "接口/域名/Associated Domains 隔离"},
        {"id": "NS-03", "name": "Android 深链域名按构建环境隔离"},
        {"id": "NS-04", "name": "日志输出按构建环境隔离"},
        {"id": "NS-05", "name": "登录态迁移至 Keychain/加密存储"},
        {"id": "NS-06", "name": "关闭 iOS Documents 文件共享"},
        {"id": "NS-07", "name": "移除生产包 mock 数据"},
        {"id": "NS-08", "name": "Flutter Release 启用 Dart 混淆与符号文件留存"},
        {"id": "NS-09", "name": "发布前自动校验生产 IPA/APK"}
    ]


@pytest.fixture(scope="session")
def security_test_summary(test_report_dir):
    """安全测试汇总结果"""
    summary = {
        "total": 9,
        "passed": 0,
        "failed": 0,
        "details": []
    }
    return summary


def pytest_sessionfinish(session, exitstatus):
    """测试会话结束钩子"""
    # 生成汇总报告
    test_report_dir = Path("results")
    test_report_dir.mkdir(parents=True, exist_ok=True)
    
    summary_file = test_report_dir / "negative_test_summary.json"
    if summary_file.exists():
        with open(summary_file, 'r', encoding='utf-8') as f:
            summary = json.load(f)
    else:
        summary = {
            "total": 9,
            "passed": 0,
            "failed": 0,
            "details": []
        }
    
    # 写入汇总
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)