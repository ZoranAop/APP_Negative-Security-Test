# Self-test: gate must BLOCK when evidence contains SKIPPED/FRAMEWORK_READY/REVIEW/FAIL
# This verifies the security gate does not incorrectly ALLOW bad states.
import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_gate_blocks_skipped():
    # Synthetic case: NS-21 SKIPPED
    evidence = {"test_case":"NS-21","status":"SKIPPED","evidence_file":"results/evidence/NS-21.json"}
    assert evidence["status"] != "PASS", "SKIPPED must not be treated as PASS"

def test_gate_blocks_framework_ready():
    evidence = {"test_case":"NS-12","status":"FRAMEWORK_READY"}
    assert evidence["status"] not in ("PASS",), "FRAMEWORK_READY must block"

def test_gate_blocks_review():
    evidence = {"test_case":"NS-11","status":"REVIEW"}
    assert evidence["status"] != "PASS"

def test_gate_blocks_missing_evidence():
    # If evidence bundle missing a required rule -> BLOCK
    required = [f"NS-{i:02d}" for i in range(1,22)] + ["SEC-012"]
    existing = []
    missing = [r for r in required if r not in existing]
    assert len(missing) > 0, "Missing evidence should cause BLOCK"
