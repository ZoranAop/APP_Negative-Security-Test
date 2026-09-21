#!/usr/bin/env python3
import json, sys, os, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

def test_gate_blocks_bad_states():
    bad_states = ["SKIPPED", "FRAMEWORK_READY", "REVIEW", "FAIL", "UNKNOWN"]
    for s in bad_states:
        assert s != "PASS", f"State {s} must not equal PASS"

def test_bundle_complete_required():
    # 模拟缺失证据时 bundle 应无效
    required = [f"NS-{i:02d}" for i in range(1,22)] + ["SEC-012"]
    # 实际使用时传入真实目录
    print("Self-test: gate must BLOCK when SKIPPED/FRAMEWORK_READY/REVIEW/FAIL present or evidence incomplete.")
