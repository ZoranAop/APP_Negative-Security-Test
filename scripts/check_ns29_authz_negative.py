#!/usr/bin/env python3
"""
NS-29: Authentication & Authorization Negative Security Test
目标：验证业务动态越权（不同角色访问不同资源）是否被正确拒绝；不是简单“认证测试”，而是“认证 + 授权负向测试”
标准流程：建立角色矩阵 → 建立资源/操作矩阵 → 静态提取（角色定义/权限配置）→ 动态业务越权测试 → 证据收集 → 人工 REVIEW → PASS/FAIL/REVIEW/SKIP
状态严格区分：PASS（已完成规定测试，证据满足安全要求）/ FAIL（已确认存在问题）/ REVIEW（测试没有足够证据完成最终判断）/ SKIP（当前产品不适用）
工具/环境不足（无真实账户/无设备/无业务环境）→ REVIEW 或 SKIP，不得直接判 PASS/FAIL
"""
import argparse, os, sys, json
from pathlib import Path
from datetime import datetime, timezone


def ensure_dir(p):
    Path(p).mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="NS-29 Auth & Authorization Negative Security Test")
    parser.add_argument("--output-dir", default="results/NS-29", help="输出目录")
    parser.add_argument("--platform", default="android,ios", help="测试平台")
    args = parser.parse_args()

    ensure_dir(args.output_dir)
    ensure_dir(os.path.join(args.output_dir, "raw"))

    timestamp = datetime.now(timezone.utc).isoformat()
    result = {
        "id": "NS-29",
        "test_name": "Authentication & Authorization Negative Security Test",
        "status": "REVIEW",
        "reason": "",
        "timestamp": timestamp,
        "checks": {
            "role_matrix_established": "REVIEW",
            "resource_matrix_established": "REVIEW",
            "guest_access_denied": "REVIEW",
            "user_self_access_pass": "REVIEW",
            "user_other_access_denied": "REVIEW",
            "group_owner_access_pass": "REVIEW",
            "group_member_access_denied_if_not_owner": "REVIEW",
            "admin_api_access_denied_for_non_admin": "REVIEW",
            "dynamic_negative_validation": "REVIEW"
        },
        "test_mode": "STATIC + DYNAMIC + MANUAL",
        "evidence": {},
        "raw_files": [],
        "notes": []
    }

    # 第一阶段：建立角色矩阵（标准化结构）
    role_matrix = {
        "Guest": {"description": "未登录用户", "permissions": ["public_content_read"], "restricted": ["profile_write", "post_write", "group_manage", "admin_api"]},
        "User": {"description": "普通登录用户", "permissions": ["self_profile_rw", "self_post_rw", "public_content_read"], "restricted": ["other_profile_rw", "other_post_rw", "group_manage", "admin_api"]},
        "VIP": {"description": "VIP 用户", "permissions": ["self_profile_rw", "self_post_rw", "vip_content_read"], "restricted": ["other_profile_rw", "group_manage", "admin_api"]},
        "Group_Member": {"description": "群成员", "permissions": ["group_read", "group_post_read"], "restricted": ["group_manage", "admin_api", "other_user_profile_write"]},
        "Group_Owner": {"description": "群主", "permissions": ["group_read_write", "group_manage", "group_member_manage"], "restricted": ["admin_api", "other_owner_group_manage_if_not_owner"]},
        "Admin": {"description": "平台管理员", "permissions": ["all_user_read", "admin_api_access", "system_config_read"], "restricted": ["should_not_access_unauthorized_business_resources"]},
        "Enterprise_Admin": {"description": "企业管理员", "permissions": ["enterprise_user_read", "enterprise_config_rw"], "restricted": ["other_enterprise_admin_unauthorized_access"]}
    }
    result["evidence"]["role_matrix"] = role_matrix
    result["checks"]["role_matrix_established"] = "PASS"

    # 第二阶段：资源/操作矩阵（标准化）
    resource_matrix = {
        "self_profile": {"Guest": "DENIED", "User": "ALLOWED", "VIP": "ALLOWED", "Group_Member": "ALLOWED", "Group_Owner": "ALLOWED", "Admin": "ALLOWED", "Enterprise_Admin": "ALLOWED"},
        "other_profile": {"Guest": "DENIED", "User": "DENIED", "VIP": "DENIED", "Group_Member": "DENIED", "Group_Owner": "DENIED", "Admin": "ALLOWED", "Enterprise_Admin": "ALLOWED"},
        "self_post": {"Guest": "DENIED", "User": "ALLOWED", "VIP": "ALLOWED", "Group_Member": "ALLOWED", "Group_Owner": "ALLOWED", "Admin": "ALLOWED", "Enterprise_Admin": "ALLOWED"},
        "other_post": {"Guest": "DENIED", "User": "DENIED", "VIP": "DENIED", "Group_Member": "DENIED", "Group_Owner": "DENIED", "Admin": "ALLOWED", "Enterprise_Admin": "ALLOWED"},
        "group_manage": {"Guest": "DENIED", "User": "DENIED", "VIP": "DENIED", "Group_Member": "DENIED", "Group_Owner": "ALLOWED", "Admin": "ALLOWED", "Enterprise_Admin": "DENIED"},
        "admin_api": {"Guest": "DENIED", "User": "DENIED", "VIP": "DENIED", "Group_Member": "DENIED", "Group_Owner": "DENIED", "Admin": "ALLOWED", "Enterprise_Admin": "DENIED"}
    }
    result["evidence"]["resource_matrix"] = resource_matrix
    result["checks"]["resource_matrix_established"] = "PASS"

    # 第三阶段：静态提取（角色定义/权限配置文件）
    # 当前脚本记录标准框架，真实业务静态提取（如从后端配置/API 文档/代码中提取角色定义）需根据实际项目补充
    result["notes"].append("静态提取阶段：已建立标准化角色矩阵与资源矩阵。真实项目应从后端配置/代码提取实际角色与权限规则，并与本矩阵对比。")
    result["checks"]["guest_access_denied"] = "REVIEW"
    result["checks"]["user_self_access_pass"] = "REVIEW"
    result["checks"]["user_other_access_denied"] = "REVIEW"
    result["checks"]["group_owner_access_pass"] = "REVIEW"
    result["checks"]["group_member_access_denied_if_not_owner"] = "REVIEW"
    result["checks"]["admin_api_access_denied_for_non_admin"] = "REVIEW"

    # 第四阶段：动态业务越权测试（标准化计划）
    # 当前脚本生成标准化测试计划，真实执行需要真实业务环境（真实账户、真实设备、真实数据）
    dynamic_plan = """# NS-29 动态业务越权测试计划（标准化）

## 测试角色与环境
- 测试账户：Guest（未登录）、User（普通用户 A）、VIP、Group_Member（B）、Group_Owner（C）、Admin、Enterprise_Admin
- 测试环境：真实业务服务器 + 真实设备 / 模拟器

## 测试矩阵（示例）

### 自己 Profile
- User A 访问自己的 Profile → 允许（PASS）
- User B 访问 User A 的 Profile（非 Admin）→ 拒绝（FAIL 处理）
- Guest 访问 User A 的 Profile → 拒绝

### 他人 Profile
- User 访问他人 Profile（无授权关系）→ 拒绝
- Admin 访问任意 Profile → 允许
- Enterprise_Admin 访问非本企业用户 Profile → 拒绝

### 自己帖子
- User A 操作自己的帖子（RW）→ 允许
- User B 操作 User A 的帖子（无授权）→ 拒绝

### 他人帖子
- User 访问他人帖子（无授权）→ 拒绝
- Admin 访问任意帖子（RW）→ 允许

### 群管理
- Group_Member 尝试管理群（修改群设置、删除成员）→ 拒绝
- Group_Owner 执行群管理 → 允许
- User（非群成员）访问群管理 API → 拒绝
- Admin 执行群管理（平台级）→ 允许（根据业务定义）

### Admin API
- User / VIP / Group_Member / Group_Owner 访问 Admin API → 拒绝
- Admin 访问 Admin API → 允许
- Enterprise_Admin 访问非企业 Admin API → 拒绝

## 测试执行要求
1. 每项动态测试必须产生：请求记录（API Path + 参数）、响应状态码、响应内容片段、测试账户信息、时间戳。
2. 测试失败（发现越权）必须记录具体资源、具体角色、具体操作，并保存为 `evidence.json` 中的 `findings` 列表。
3. 测试通过（正确拒绝或允许）同样必须保存证据，以证明测试已执行而非跳过。
4. 无真实业务环境时，状态为 `REVIEW` 或 `SKIP`（根据是否适用），**不得直接判 PASS**（因为未执行规定测试）。
"""
    with open(os.path.join(args.output_dir, "raw", "dynamic_negative_plan.md"), "w", encoding="utf-8") as f:
        f.write(dynamic_plan)
    result["raw_files"].append("raw/dynamic_negative_plan.md")
    result["checks"]["dynamic_negative_validation"] = "REVIEW"
    result["notes"].append("动态业务越权测试计划已生成。真实执行需要真实业务环境（真实账户、真实设备、真实数据）。无真实环境时，状态必须为 REVIEW（已生成计划并记录标准框架），不得直接判 PASS。")

    # 最终状态判定规则（根据用户要求标准化）
    # 1. 已完成规定测试 + 证据满足安全要求 → PASS
    # 2. 已确认存在问题 → FAIL
    # 3. 测试没有足够证据完成最终判断 → REVIEW
    # 4. 当前产品不适用 → SKIP
    # 当前脚本：已完成静态框架和标准化矩阵，动态测试无真实环境证据，因此必须为 REVIEW
    result["status"] = "REVIEW"
    result["reason"] = "requires_real_business_dynamic_authorization_validation"
    result["notes"].append("根据标准化状态定义：无真实业务动态越权测试证据时，不能判 PASS（未完成规定测试），也不能直接判 FAIL（无证据确认问题存在），因此必须为 REVIEW。")
    result["notes"].append("如果真实业务动态测试发现越权（如 User 可访问他人 Profile / Admin API 对非 Admin 不拒绝 / Group_Member 可执行群管理），应将状态调整为 FAIL 并记录具体 `findings`。")

    # 写入文件
    evidence_bundle = {
        "test_case": "NS-29",
        "test_name": "Authentication & Authorization Negative Security Test",
        "status": result["status"],
        "reason": result["reason"],
        "timestamp": timestamp,
        "test_mode": result["test_mode"],
        "checks": result["checks"],
        "notes": result["notes"],
        "evidence_summary": {
            "role_matrix": result["evidence"]["role_matrix"],
            "resource_matrix": result["evidence"]["resource_matrix"]
        },
        "manual_review_required": True,
        "recommendation": "执行完整验证：在真实业务环境中，使用真实账户执行角色矩阵中的所有访问场景，记录每项请求与响应。发现越权 → FAIL；正确拒绝/允许且有完整证据 → PASS。无真实环境时保持 REVIEW。"
    }
    with open(os.path.join(args.output_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.output_dir, "evidence.json"), "w", encoding="utf-8") as f:
        json.dump(evidence_bundle, f, ensure_ascii=False, indent=2)

    report_md = f"""# NS-29 报告 — Authentication / Authorization 负向测试

## 测试状态
- **状态**: `{result['status']}`
- **原因**: `{result['reason']}`
- **时间戳**: `{timestamp}`
- **测试模式**: `{result['test_mode']}`

## 流程执行（标准化）
1. 测试准备: 完成
2. 提取测试对象: 已建立标准化角色矩阵（Guest / User / VIP / Group_Member / Group_Owner / Admin / Enterprise_Admin）
3. 基础静态检查: 已建立资源/操作矩阵（Profile / Post / Group / Admin API）
4. 专项规则检查: 标准化矩阵已完成；真实业务静态提取（从后端配置/代码）需人工补充
5. 必要动态验证: **REVIEW**（无真实业务环境证据，无法完成最终判断）
6. 证据收集: `evidence.json` + `summary.json` + `raw/dynamic_negative_plan.md`
7. 规则化判定: 完成（标准化状态：无证据 → REVIEW；有证据 → PASS/FAIL）
8. 人工 REVIEW: **必需**（执行真实业务动态越权测试并确认结果）
9. 最终判定: `{result['status']}`

## 角色矩阵（标准化）
{json.dumps(role_matrix, ensure_ascii=False, indent=2)}

## 资源矩阵（标准化）
{json.dumps(resource_matrix, ensure_ascii=False, indent=2)}

## 检查结果
| 检查项 | 状态 | 说明 |
|---|---|---|
| role_matrix_established | PASS | 标准化角色矩阵已建立 |
| resource_matrix_established | PASS | 标准化资源矩阵已建立 |
| guest_access_denied | REVIEW | 需真实业务动态测试 |
| user_self_access_pass | REVIEW | 需真实业务动态测试 |
| user_other_access_denied | REVIEW | 需真实业务动态测试 |
| group_owner_access_pass | REVIEW | 需真实业务动态测试 |
| group_member_access_denied_if_not_owner | REVIEW | 需真实业务动态测试 |
| admin_api_access_denied_for_non_admin | REVIEW | 需真实业务动态测试 |
| dynamic_negative_validation | REVIEW | 需要真实环境执行标准化测试计划 |

## 状态判定规则（重申）
- `PASS`: 已经完成规定测试，证据满足安全要求（包括完整动态测试记录）。
- `FAIL`: 已经确认存在问题（如发现越权访问的完整请求/响应证据）。
- `REVIEW`: 测试没有足够证据完成最终判断（如当前脚本状态：已完成框架，但无真实业务动态测试证据）。
- `SKIP`: 当前产品不适用（如产品无群功能时，群管理相关测试可标记 SKIP）。
- **工具执行失败 ≠ 安全 FAIL**：环境不足时必须为 REVIEW/SKIP，并记录 `reason`。

## 建议的下一步
在真实业务环境执行 `raw/dynamic_negative_plan.md` 中的标准化测试计划，并将每项测试结果（请求、响应、结果）写入 `results/NS-29/evidence.json` 的 `findings` 字段，然后重新运行本脚本（或直接由人工 REVIEW 更新状态为 PASS/FAIL）。
"""
    with open(os.path.join(args.output_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"[NS-29] 完成。状态={result['status']}, 原因={result['reason']}, 输出={args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
