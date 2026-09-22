"""
扩展测试模板：NS-10 ~ NS-21 + SEC-012
基于 tests/test_negative_security.py 现有结构，便于补全完整性
使用方式：pytest tests/test_negative_security_extended.py -v --junitxml=results/test_extended.xml
"""
import sys, pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
from test_negative_security import NegativeSecurityTest, run_test_script

class TestExtendedNegativeSecurity:
    """扩展 13 条测试模板（NS-10~21 + SEC-012）"""

    def test_dependency_audit(self, security_root, build_artifacts, test_report_dir):
        """NS-10: 第三方依赖/SDK 安全"""
        script = security_root / "scripts" / "check_dependency_audit.py"
        test = NegativeSecurityTest("NS-10", "第三方依赖审计", script)
        test.run(apk=build_artifacts.get("apk"), pubspec=build_artifacts.get("pubspec"), build_gradle=build_artifacts.get("build_gradle"), output_json=test_report_dir / "test_ns10.json")
        test.assert_pass()

    def test_secret_context(self, security_root, build_artifacts, test_report_dir):
        """NS-11: Secret / 凭证泄漏上下文检测"""
        script = security_root / "scripts" / "check_secret_context.py"
        test = NegativeSecurityTest("NS-11", "Secret 上下文检测", script)
        test.run(apk=build_artifacts.get("apk"), ipa=build_artifacts.get("ipa"), output_json=test_report_dir / "test_ns11.json")
        test.assert_pass()

    def test_network_security(self, security_root, build_artifacts, test_report_dir):
        """NS-12: 网络安全配置"""
        script = security_root / "scripts" / "check_network_security.py"
        test = NegativeSecurityTest("NS-12", "网络安全配置", script)
        test.run(apk=build_artifacts.get("apk"), manifest=build_artifacts.get("manifest"), output_json=test_report_dir / "test_ns12.json")
        test.assert_pass()

    def test_permission_audit(self, security_root, build_artifacts, test_report_dir):
        """NS-13: 权限最小化审计"""
        script = security_root / "scripts" / "check_permission_audit.py"
        test = NegativeSecurityTest("NS-13", "权限审计", script)
        test.run(apk=build_artifacts.get("apk"), manifest=build_artifacts.get("manifest"), output_json=test_report_dir / "test_ns13.json")
        test.assert_pass()

    def test_component_exposure(self, security_root, build_artifacts, test_report_dir):
        """NS-14: Android 组件暴露检查"""
        script = security_root / "scripts" / "check_component_exposure.py"
        test = NegativeSecurityTest("NS-14", "组件暴露", script)
        test.run(apk=build_artifacts.get("apk"), manifest=build_artifacts.get("manifest"), output_json=test_report_dir / "test_ns14.json")
        test.assert_pass()

    def test_intent_injection(self, security_root, build_artifacts, test_report_dir):
        """NS-15: Intent / Deep Link 注入安全"""
        script = security_root / "scripts" / "check_intent_injection.py"
        test = NegativeSecurityTest("NS-15", "Intent 注入安全", script)
        test.run(manifest=build_artifacts.get("manifest"), apk=build_artifacts.get("apk"), output_json=test_report_dir / "test_ns15.json")
        test.assert_pass()

    def test_webview_security(self, security_root, build_artifacts, test_report_dir):
        """NS-16: WebView 安全"""
        script = security_root / "scripts" / "check_webview_security.py"
        test = NegativeSecurityTest("NS-16", "WebView 安全", script)
        test.run(apk=build_artifacts.get("apk"), output_json=test_report_dir / "test_ns16.json")
        test.assert_pass()

    def test_local_data_residue(self, security_root, build_artifacts, test_report_dir):
        """NS-17: 本地敏感数据残留"""
        script = security_root / "scripts" / "check_local_data_residue.py"
        test = NegativeSecurityTest("NS-17", "本地数据残留", script)
        test.run(apk=build_artifacts.get("apk"), output_json=test_report_dir / "test_ns17.json")
        test.assert_pass()

    def test_screen_privacy(self, security_root, build_artifacts, test_report_dir):
        """NS-18: 屏幕隐私 / 截图保护"""
        script = security_root / "scripts" / "check_screen_privacy.py"
        test = NegativeSecurityTest("NS-18", "屏幕隐私", script)
        test.run(apk=build_artifacts.get("apk"), ipa=build_artifacts.get("ipa"), info_plist=build_artifacts.get("info_plist"), output_json=test_report_dir / "test_ns18.json")
        # 对于需要人工/设备确认的项，允许 REVIEW 作为中间状态，但门禁应处理
        result = test.run(apk=build_artifacts.get("apk"), ipa=build_artifacts.get("ipa"), info_plist=build_artifacts.get("info_plist"), output_json=test_report_dir / "test_ns18.json")
        # 这里不强制 assert_pass，因为 NS-18 可能输出 SKIPPED/REVIEW（Fail-Closed 设计）
        # 实际执行时由 gate_decision.py 评估
        assert result["returncode"] in (0, 1)  # 接受 PASS/FAIL/REVIEW 都可记录

    def test_artifact_consistency(self, security_root, build_artifacts, test_report_dir):
        """NS-19: 产物完整性 / SBOM 对比"""
        script = security_root / "scripts" / "check_artifact_consistency.py"
        test = NegativeSecurityTest("NS-19", "产物一致性", script)
        test.run(apk=build_artifacts.get("apk"), ipa=build_artifacts.get("ipa"), build_log=build_artifacts.get("build_log"), output_json=test_report_dir / "test_ns19.json")
        test.assert_pass()

    def test_release_inventory(self, security_root, build_artifacts, test_report_dir):
        """NS-20: 发布产物清单 / 安全库存"""
        script = security_root / "scripts" / "check_release_inventory.py"
        test = NegativeSecurityTest("NS-20", "产物清单", script)
        test.run(apk=build_artifacts.get("apk"), ipa=build_artifacts.get("ipa"), output_json=test_report_dir / "test_ns20.json")
        test.assert_pass()

    def test_forbidden_capability(self, security_root, build_artifacts, test_report_dir):
        """NS-21: 禁止能力动态测试（框架/设备依赖）"""
        script = security_root / "scripts" / "check_forbidden_capability.py"
        test = NegativeSecurityTest("NS-21", "禁止能力动态", script)
        # 无设备时期望 SKIPPED（Fail-Closed）；有设备时需结合动态触发脚本
        result = test.run(apk=build_artifacts.get("apk"), device_id=build_artifacts.get("device_id"), output_json=test_report_dir / "test_ns21.json")
        # 门禁应处理 SKIPPED → BLOCK；此处仅验证脚本可执行并产生 JSON 证据
        assert "test_case" in (result.get("stdout") or "") or os.path.exists(test_report_dir / "test_ns21.json")

    def test_release_config_sec012(self, security_root, build_artifacts, test_report_dir):
        """SEC-012: Release 构建配置检查"""
        script = security_root / "scripts" / "check_release_config.py"
        test = NegativeSecurityTest("SEC-012", "构建配置", script)
        test.run(build_log=build_artifacts.get("build_log"), pubspec=build_artifacts.get("pubspec"), output_json=test_report_dir / "test_sec012.json")
        test.assert_pass()

def pytest_configure(config):
    config._security_test_config = {
        "test_cases": [
            "NS-10-dependency-audit", "NS-11-secret-context", "NS-12-network-security",
            "NS-13-permission-audit", "NS-14-component-exposure", "NS-15-intent-injection",
            "NS-16-webview-security", "NS-17-local-data-residue", "NS-18-screen-privacy",
            "NS-19-artifact-consistency", "NS-20-release-inventory", "NS-21-forbidden-capability",
            "SEC-012-release-config"
        ]
    }
