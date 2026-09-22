#!/usr/bin/env python3
"""负向安全测试门禁的自测用例。

本文件只验证 fail-closed 行为，不模拟真实构建产物。
"""

import json
import subprocess
import sys
from pathlib import Path


SECURITY_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = SECURITY_ROOT / "scripts" / "gate_decision.py"


def run_gate(evidence_dir: Path):
    """运行门禁脚本并返回退出码与 JSON 结果。"""
    output = evidence_dir / "gate_decision.json"
    cmd = [
        sys.executable,
        str(GATE_SCRIPT),
        "--evidence-dir",
        str(evidence_dir),
        "--policy-dir",
        str(SECURITY_ROOT / "policies"),
        "--platform",
        "android,ios",
        "--output-json",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    return result.returncode, data


def test_gate_blocks_bad_states(tmp_path):
    """SKIPPED / FRAMEWORK_READY / REVIEW / FAIL 必须触发 BLOCK。"""
    for state in ["SKIPPED", "FRAMEWORK_READY", "REVIEW", "FAIL", "UNKNOWN"]:
        evidence_dir = tmp_path / state
        evidence_dir.mkdir()
        (evidence_dir / "NS-01.json").write_text(
            json.dumps({"status": state, "test_case": "NS-01"}),
            encoding="utf-8",
        )
        returncode, data = run_gate(evidence_dir)
        assert returncode == 0
        assert data.get("decision") == "BLOCK", state


def test_bundle_complete_required(tmp_path):
    """缺少证据或证据不完整时，门禁必须 BLOCK。"""
    evidence_dir = tmp_path / "incomplete"
    evidence_dir.mkdir()
    (evidence_dir / "NS-01.json").write_text(
        json.dumps({"status": "PASS", "test_case": "NS-01"}),
        encoding="utf-8",
    )
    returncode, data = run_gate(evidence_dir)
    assert returncode == 0
    assert data.get("decision") == "BLOCK"


def test_gate_allows_complete_bundle(tmp_path):
    """所有必需证据均为 PASS 时，门禁允许发布。"""
    evidence_dir = tmp_path / "complete"
    evidence_dir.mkdir()
    for index in range(1, 22):
        (evidence_dir / f"NS-{index:02d}.json").write_text(
            json.dumps({"status": "PASS", "test_case": f"NS-{index:02d}"}),
            encoding="utf-8",
        )
    (evidence_dir / "SEC-012.json").write_text(
        json.dumps({"status": "PASS", "test_case": "SEC-012"}),
        encoding="utf-8",
    )
    returncode, data = run_gate(evidence_dir)
    assert returncode == 0
    assert data.get("decision") == "ALLOW"
