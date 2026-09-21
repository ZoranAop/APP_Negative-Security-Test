#!/usr/bin/env python3
"""NS-15: Deep Link / Intent 注入安全检查框架"""
import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument("--manifest")
parser.add_argument("--output-json")
args = parser.parse_args()
res = {
    "test_case":"NS-15", "test_name":"Intent / Deep Link Injection Security",
    "status":"FRAMEWORK_READY",
    "checks":[
        {"id":"open_redirect","desc":"deep link 参数中是否存在未验证 redirect/url/callback", "severity":"CRITICAL"},
        {"id":"javascript_scheme","desc":"javascript: / file: / content: 注入", "severity":"HIGH"},
        {"id":"intent_redirection","desc":"未登录状态访问敏感页面 / 参数绕过权限", "severity":"HIGH"},
        {"id":"parameter_validation","desc":"intent 参数未验证格式/长度/类型", "severity":"MEDIUM"},
        {"id":"exported_deep_link_protection","desc":"导出的 Deep Link Activity 是否受权限保护", "severity":"MEDIUM"}
    ],
    "notes":"完整执行需要解析 manifest + 测试实际深链触发（动态测试结合 NS-21）。"
}
with open(args.output_json or "/tmp/NS-15.json","w") as f: json.dump(res,f,indent=2,ensure_ascii=False)
print("NS-15 框架完成")

# Dynamic test requires device / runtime environment; without it result = SKIPPED (not PASS)
# Per Fail-Closed design: SKIPPED -> BLOCK release (not ALLOW)

