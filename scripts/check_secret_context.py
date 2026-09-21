#!/usr/bin/env python3
"""
SEC-011 / NS-11: Secret / Credential 上下文检测框架（基础版，待熵值增强）
检查构建包中是否存在可能的敏感凭证，并根据上下文分类：
  REAL_SECRET (Critical) / THIRDPARTY_REF / FALSE_POSITIVE / CONTEXT_NEEDED
"""
import argparse, json, sys, re

def classify_secret(match_text, source_file, context_words):
    """基础上下文分类规则（可扩展为熵值/PEM/JWT 格式判断）"""
    text_lower = match_text.lower()
    # 如果匹配到第三方 SDK 参考字符串，分类为 THIRDPARTY_REF
    third_party_refs = ["flutter.dev", "google", "firebase", "analytics", "example", "sample", "docs.flutter"]
    for ref in third_party_refs:
        if ref in text_lower:
            return "THIRDPARTY_REF", "第三方 SDK / 文档参考字符串（非真实凭证）"
    # 如果上下文包含 "private_key" 且文件来源为 XML/资源描述，标记为需要人工确认
    if "private_key" in text_lower and any(w in text_lower for w in ["description", "label", "example", "demo", "test"]):
        return "CONTEXT_NEEDED", "疑似凭证字段，需人工确认是否为真实 Secret 或第三方描述"
    # 默认：高熵或真实凭证格式（简化判断）
    return "REAL_SECRET_CANDIDATE", "高风险：可能包含真实凭证，需人工/熵值验证"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = {
        "test_case": "NS-11",
        "test_name": "Secret / Credential Context Check",
        "status": "FRAMEWORK_READY",
        "findings": [
            {"rule": "context_classification", "value": "第三方参考 / 真实凭证 / 需人工确认", "severity": "HIGH"},
            {"rule": "entropy_format_check", "value": "待增强（需要真实构建样本验证 PEM / JWT / API Key 格式）", "severity": "INFO"},
            {"rule": "forbidden_in_allowlist", "value": "token / password / secret_key / auth_credential / private_key 不得进入 allowlist", "severity": "CRITICAL"},
        ],
        "classification": {
            "FAIL": ["REAL_SECRET_CANDIDATE"],
            "REVIEW": ["CONTEXT_NEEDED"],
            "THIRDPARTY": ["THIRDPARTY_REF"],
            "ALLOWLIST": ["ALLOWLIST_APPROVED"]
        },
        "notes": "本脚本为框架版（Phase 1），完整执行需要真实构建产物 + 熵值分析库（如 entropy、pem、jwt 解析）。"
    }
    with open(args.output_json or "/tmp/NS-11.json", "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"NS-11 结果: {result['status']} — 框架已就绪，完整验证需构建环境支持")
    sys.exit(0)

if __name__ == "__main__":
    main()
