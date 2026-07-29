# 历次发现归档

## 2026-07-29 Pre 环境全面测试 (7 套件 + 发帖实战 + UI 验证)

### 执行统计
| 套件 | 用例 | 通过 | 失败 | 通过率 |
|------|------|------|------|--------|
| s99_smoke | 5 | 5 | 0 | 100.0% |
| s01_eleven_issues | 11 | 11 | 0 | 100.0% |
| s02_full_regression | 93 | 91 | 2 | 97.8% |
| s03_ux_quality | 44 | 37 | 7 | 84.1% |
| s04_interactions | 44 | 38 | 6 | 86.4% |
| s05_stress_abuse | 15 | 13 | 2 | 86.7% |
| s06_video_hotlink | 33 | 20 | 13 | 60.6% |
| 发帖实战 (5用户×2帖) | 10 | 10 | 0 | 100.0% |
| 补充深入测试 (并发/私密/管线/去重) | 25 | 22 | 3 | 88.0% |
| **合计** | **280** | **247** | **33** | **88.2%** |

### 🔴 HIGH 新发现 (9项)

| ID | 来源 | 标题 | 详情 |
|----|------|------|------|
| H1 | s02 | Dashboard摘要 403 | /admin/dashboard/summary user_id=6 无权限 |
| H2a/b | s02 | 内容删除+认证审批仍未上线 | 0624→0729持续3个月 404 |
| H3 | s03 | cursor=-1 → HTTP 500 | /announcement/list?cursor=-1 |
| H4 | s03 | email明文泄露 | /admin/user/users 完整返回邮箱 |
| H5 | s03 | 内容重复污染 | 40条内容前50字完全相同 |
| H7 | s04 | room/detail非法id→500 | 非法room_id应返回400 |
| H8 | s05 | page_size=100万→500 | 公开公告巨量分页无上限保护 |
| HW-1 | UI | 钱包Tab未移除 | wallet_enabled:true, 测试计划Out of Scope |
| H6a/b | s06 | Referer indexOf绕过 + OPTIONS绕过 | CloudFront Function 2个高危绕过 |

### 🟡 MEDIUM 新发现 (8项)

| ID | 来源 | 标题 |
|----|------|------|
| M1 | s02 | 帖子详情ID在pre环境404 (dev硬编码ID) |
| M2 | s03 | 时间格式混用 (Unix int + ISO8601) |
| M3 | s05 | 后台用户size=100万响应20003ms |
| M4 | s03 | 公告无 lang/locale 字段 |
| M5 | s03 | 后台反馈/客服入口缺失 |
| M7 | s06 | Referer indexOf子串绕过 (已知局限) |
| M8 | s06 | OPTIONS预检绕过防盗链 |
| G1 | 补充 | post_moments --concurrency>1 触发429 |

### 🟢 LOW 新发现 (3项)

| ID | 来源 | 标题 |
|----|------|------|
| L1 | s04 | endpoints.json硬编码dev post_id |
| L2 | s05 | 前台读接口无限流 |
| L3 | s03 | 公告无lang字段 |

### 补充深入测试结论

| 测试项 | 结果 | 说明 |
|--------|------|------|
| --concurrency 3 并发发帖 | 3/6 | 后3帖HTTP 429, post_moments不适合并发 |
| visibility=1 私密帖 | 3/3 | 功能正常 |
| publish_from_tokens 三阶段 | 6/6 | 优于post_moments, 100% |
| --tokens-in Token复用 | 6/6 | Phase1跳过, 中断恢复可用 |
| 图片质量边界 (小图/坏图/混合AR) | 4/4 | 7步管线全部生效, 正确降级纯文本 |
| 去重验证 | ✅ | 88条记录持续积累 |

### post_moments vs publish_from_tokens 对比

| 特性 | post_moments | publish_from_tokens |
|------|-------------|---------------------|
| 429防护 | ❌ 并发触发 | ✅ 顺序登录+deburst |
| 图片质量门 | 基础尺寸 | ✅ 7步完整管线 |
| Token复用 | ❌ | ✅ --tokens-in |
| 中断恢复 | ❌ | ✅ |
| 文本降级 | ❌ 直接失败 | ✅ 自动纯文本 |

**建议: 生产统一使用 publish_from_tokens.py。**

### 本轮修复优先级

#### P0 本周必须
1. H3 cursor=-1 → 500
2. H7 room非法id → 500
3. H8 page_size=100万 → 500
4. H4 email明文泄露
5. HW-1 钱包Tab移除确认

#### P0 防盗链
6. H6a Referer indexOf → 精确匹配
7. H6b OPTIONS预检 → Function覆盖

#### P1 下迭代
8. H5 内容重复去重
9. H1 Dashboard 403权限
10. H2a/b 404接口确认排期
11. H9 无限流

#### P2 技术债
12. M1 跨环境post_id注入
13. M2 时间格式统一ISO8601
14. M4 公告国际化
15. M5 反馈入口

11 项预期结论与实测**100% 一致**:

| # | 问题 | 预期 | 实测 |
|---|---|---|---|
| 1 | 通知 | ⚠️ 待接入 | ⚠️ 维持 (后台无用户通知菜单,仅运营 msg/push) |
| 2 | 后台加 V | ❌ 未实现 | ❌ 维持 (仅实名认证 cert/approve,无独立加V) |
| 3 | 小秘书总结 UI | ❌ 未实现 | ❌ 维持 (后端就绪,前端无总结 UI 页面) |
| 4 | 后台帖子列表可删除 | ❌ 未实现 | ❌ 维持 (列表 9863 条+is_deleted字段已有,但 delete 接口全 404) |
| 5 | Feed/主页背景 | ✅ 后端已接入 | ✅ 确认 (POST /api/v1/user/feed_background) |
| 6 | 帖子图标 UI | ⚠️ 待UI人工 | ⚠️ 维持 (PostModel 字段齐全) |
| 7 | 分享第一行加入 X | ❌ 未完成 | ❌ 维持 (反编译分享菜单无X渠道) |
| 8 | 个人页显示收费群 | ✅ 完成 | ✅ 确认 (exclusiveProfile + room/list) |
| 9 | 收费群 | ✅ 完成 | ✅ 确认 (FeeDetailCubit + 1093 个房间) |
| 10 | 公告 | ✅ 完成 | ✅ 确认 (前后台一致, total=51) |
| 11 | 收费群发帖同步广场 | ✅ 完成 | ✅ 确认 (syncToSquare + room_moments API) |

## 2026-06-26 第二轮 (0624 文档全量回归)

### 关键发现
| 改善/反转 | 项 | 原结论 | 实测 |
|---|---|---|---|
| ✨ 改善 | RECHECK-005 announcement/logs | 参数未对齐 | `?announcement_id=65` HTTP 200, 已对齐 |
| 🔴 反转 | /admin/cert/approve | 0624: 反编译确认已落地 | 实际 404, 未实现 |
| 🔴 反转 | /admin/content/delete | 0624: 反编译确认已落地 | 实际 404, 未实现 |
| ⚠️ 修正 | RECHECK-001 4 菜单 mock | 前端 mock | 修正为"前端 UI 文件存在但被隐藏 (show_link=false)" |
| 🔴 维持 | RECHECK-002 公告 payload | 4 条未清 | 维持 (本轮再次确认) |

### 通过率
- A 板块 (App API 端点): 23/23 ✅
- B 板块 (后台 API): 26/28 ✅
- C 板块 (/mock/): 5/5 全 404 (符合 mock 约定)
- D 板块 (BUG/ISSUE): 19/19 复测
- E 板块 (RECHECK): 6/6 复测
- F 板块 (安全): 9/10 通过 (SEC-07 有 XSS)

## 2026-06-26 第三轮 (UX 视角 14 个新发现)

### P0 (4)
| ID | 标题 | 详情 |
|---|---|---|
| NEW-UX-01 | 推荐流刷屏 | 100 条里 52% 同作者, 萤川悠歌一人 11 条 |
| NEW-UX-03 | cursor=负数 触发 500 | `?cursor=-1` 返 "服务升级中" (实际服务正常) |
| NEW-UX-05 | 公告 XSS payload 升级 | 第 5 条 `<img onerror=alert(cookie)>` |
| NEW-UX-06 | 用户列表 email 明文 | 19.8 万真实邮箱直接返回 |

### P1 (4)
| ID | 标题 | 详情 |
|---|---|---|
| NEW-UX-02 | 内容重复污染 | 100 条里 5 组前 50 字完全相同 |
| NEW-UX-04 | 公告空白污染 | id=30/43 全空格标题 |
| NEW-UX-07 | 头像 0% 普及 | 50 条用户全部 avatar="" |
| NEW-UX-09 | 错误暴露技术栈 | `strconv.ParseInt: parsing "abc"` 外泄 |

### P2/P3 (6)
| ID | 标题 |
|---|---|
| NEW-UX-08 | 时间格式跨接口混用 (int + ISO8601) |
| NEW-UX-10 | 用户列表性能临界 (P50=508ms) |
| NEW-UX-11 | 审计日志偏慢 (P50=551ms) |
| NEW-UX-12 | 5 个隐藏菜单 (推荐标签库管理等) |
| NEW-UX-13 | 公告无 lang 字段 |
| NEW-UX-14 | 状态码 10/20/30 语义不直观 |

## 修复优先级 (累计 3 轮)

### P0 必须修
1. NEW-UX-01 推荐流加 user_id 多样性约束
2. NEW-UX-05 立即清理公告 id=62
3. NEW-UX-06 后台用户列表 email 脱敏
4. NEW-UX-03 公告 cursor 负数兜底
5. RECHECK-002 公告 4 条恶意 payload 清理
6. /admin/cert/approve 与 /admin/content/delete 落地 (与 0624 矛盾)

### P1 高优
7. NEW-UX-02 发帖/Feed 内容去重
8. NEW-UX-04 公告 trim + 非空校验
9. NEW-UX-07 默认头像兜底
10. NEW-UX-09 错误消息建 i18n key
11. Q04 后台帖子删除接口补齐

### P2 中
12. NEW-UX-08 时间格式统一
13. NEW-UX-10/11 性能优化
14. Q03 小秘书总结 UI 前端补齐

### P3 低
15. NEW-UX-12 隐藏菜单清理
16. NEW-UX-13 公告加 lang
17. NEW-UX-14 状态码加 status_text
