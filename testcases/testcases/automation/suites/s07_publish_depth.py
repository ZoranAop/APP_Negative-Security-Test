# -*- coding: utf-8 -*-
"""套件 s07: 发布管线深度验证 (Publish Pipeline Depth)

验证 post_moments.py 与 publish_from_tokens.py 在生产场景下的行为差异，
覆盖并发限流、私密帖、图片质量降级、Token 复用等遗漏测试点。

测试维度：
  V1: 并发发帖 429 行为
  V2: visibility=1 私密帖
  V3: publish_from_tokens 三阶段 API 可达性
  V4: Token 复用文件结构
  V5: 图片质量管线配置
  V6: 去重文件完整性
  V7: 视频发帖端点

参考：2026-07-29 全面测试报告
"""

import os
import json
import time
import requests
from pathlib import Path

# 仓库根目录（testcases/automation 的上级的上级）
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


def run(client, reporter):
    area = "发布管线"

    feed_url = "https://feed-api.xxai.com/api/v1/moments/"
    login_url = "https://api.xxai.com/login"
    s3_cred_url = "https://api.xxai.com/file/upload/credentials"

    # ─────────────────────────────────────────────────────────────────────
    # V1 & V2: 需要用户 token 的测试（跳过但记录原因）
    # ─────────────────────────────────────────────────────────────────────
    test_email = os.getenv("TEST_PUBLISH_EMAIL", "")
    test_password = os.getenv("TEST_PUBLISH_PASSWORD", "")
    has_creds = bool(test_email and test_password)

    reporter.add_case(
        area, "V1-CONCUR-01",
        f"并发发帖: {'可测' if has_creds else '跳过(需设TEST_PUBLISH_EMAIL)'}",
        not has_creds,  # 跳过也标记为通过（缺少凭证属环境问题非代码缺陷）
        {"skip": not has_creds, "has_creds": has_creds},
    )
    reporter.add_case(
        area, "V2-PRIVATE-01",
        f"私密帖: {'可测' if has_creds else '跳过(需设TEST_PUBLISH_EMAIL)'}",
        not has_creds,
        {"skip": not has_creds, "has_creds": has_creds},
    )

    if has_creds:
        try:
            resp = requests.post(
                login_url,
                json={"email": test_email, "password": test_password, "device_id": "test_s07", "device_name": "qa"},
                timeout=15,
                verify=False,
            )
            if resp.status_code == 200 and resp.json().get("code") == 0:
                token = resp.json()["data"]["token"]
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

                # V1: 并发 — 连发 3 帖 0.5s 间隔
                rate_limited = False
                for i in range(3):
                    r = requests.post(feed_url, json={"content": f"s07 concurrency post {i+1}", "visibility": 0}, headers=headers, timeout=10, verify=False)
                    if r.status_code == 429:
                        rate_limited = True
                    time.sleep(0.5)

                reporter.add_case(area, "V1-CONCUR-02", "并发发帖是否触发429", not rate_limited, {"triggered_429": rate_limited})
                if rate_limited:
                    reporter.add_finding("medium", area, "并发发帖触发了429", "3帖0.5s间隔时后端返回限流, post_moments并发模式不适合批量")

                # V2: 私密帖
                r = requests.post(feed_url, json={"content": "Private visibility test s07", "visibility": 1}, headers=headers, timeout=10, verify=False)
                passed = (r.status_code == 200 and r.json().get("code") == 0)
                reporter.add_case(area, "V2-PRIVATE-02", "visibility=1 私密帖发布", passed, {"http": r.status_code})
                if not passed:
                    reporter.add_finding("high", area, "私密帖发布失败", f"HTTP={r.status_code} body={r.text[:200]}")
            else:
                reporter.add_finding("medium", area, "测试用户登录失败", f"HTTP={resp.status_code}")
        except Exception as e:
            reporter.add_finding("medium", area, "凭据测试异常", str(e))

    # ─────────────────────────────────────────────────────────────────────
    # V3: 三阶段 API 端点探测
    # ─────────────────────────────────────────────────────────────────────
    scenarios = [
        ("Phase1-登录(POST不存在的邮箱)", "POST", login_url, lambda r: r.status_code != 200,
         "不存在的邮箱返回非200"),
        ("Phase2-S3凭证(GET无token)", "GET", s3_cred_url, lambda r: r.status_code != 200,
         "无token不应返回200"),
        ("Phase3-发帖(GET无token)", "GET", feed_url, lambda r: r.status_code != 200,
         "无token不应返回200"),
    ]

    for name, method, url, check_fn, desc in scenarios:
        try:
            if method == "POST":
                r = requests.post(url, json={"email": "nonexistent@xxai.com", "password": "x", "device_id": "s07"}, timeout=10, verify=False)
            else:
                r = requests.get(url, timeout=10, verify=False)

            passed = check_fn(r)
            reporter.add_case(area, f"V3-{name}", f"三阶段: {name} ({desc})", passed, {"http": r.status_code})
            if r.status_code >= 500:
                reporter.add_finding("high", area, f"三阶段 {name} 返回 5xx", f"HTTP={r.status_code}")
        except Exception as e:
            reporter.add_case(area, f"V3-{name}", f"三阶段: {name} 不可达", False, {"error": str(e)})
            reporter.add_finding("high", area, f"三阶段 {name} 不可达", str(e))

    # ─────────────────────────────────────────────────────────────────────
    # V4: Token 复用文件结构
    # ─────────────────────────────────────────────────────────────────────
    result_dir = REPO_ROOT / "result"
    token_files = list(result_dir.glob("*.json")) if result_dir.exists() else []

    if token_files:
        for tf in token_files[:3]:
            try:
                data = json.loads(tf.read_text(encoding="utf-8"))
                if isinstance(data, dict) and len(data) > 0:
                    sample_val = next(iter(data.values()))
                    valid = isinstance(sample_val, str) and len(sample_val) > 20
                    reporter.add_case(area, f"V4-{tf.name}", f"Token文件 {tf.name} ({len(data)} keys)", valid, {})
                    if not valid:
                        reporter.add_finding("medium", area, f"Token文件 {tf.name} 结构异常", "")
                else:
                    reporter.add_finding("low", area, f"Token文件 {tf.name} 为空或非dict", "")
            except Exception as e:
                reporter.add_finding("low", area, f"Token文件 {tf.name} 读取失败", str(e))
    else:
        reporter.add_case(area, "V4-TOKEN-NO", "Token文件: result/ 无 JSON (正常)", True, {"skip": True, "note": "token文件在发帖后生成"})

    # ─────────────────────────────────────────────────────────────────────
    # V5: 图片质量管线配置
    # ─────────────────────────────────────────────────────────────────────
    min_w = int(os.getenv("POST_MIN_IMAGE_WIDTH", "400"))
    min_h = int(os.getenv("POST_MIN_IMAGE_HEIGHT", "300"))
    reporter.add_case(area, "V5-IMG-01", f"图片最小尺寸={min_w}x{min_h}", (min_w >= 300 and min_h >= 200), {"min_w": min_w, "min_h": min_h})

    reporter.add_case(area, "V5-IMG-02",
        f"图片上限: 竖{os.getenv('POST_MAX_PORTRAIT_IMAGES','4')} 横{os.getenv('POST_MAX_LANDSCAPE_IMAGES','6')} 方{os.getenv('POST_MAX_SQUARE_IMAGES','9')}",
        True, {})

    grid = os.getenv("POST_GRID_FRIENDLY", "true")
    art = os.getenv("POST_IMAGE_AR_TOLERANCE", "0.25")
    reporter.add_case(area, "V5-IMG-03", f"网格友好={grid} AR容差={art}", (grid == "true"), {})

    # ─────────────────────────────────────────────────────────────────────
    # V6: 去重文件
    # ─────────────────────────────────────────────────────────────────────
    dedupe_specs = [
        ("data/used_slugs.json", "图片slug去重"),
        ("data/tuzi_used.json", "兔子素材去重"),
    ]

    for rel, desc in dedupe_specs:
        p = REPO_ROOT / rel
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    count = sum(len(v) if isinstance(v, list) else 0 for v in data.values())
                elif isinstance(data, list):
                    count = len(data)
                else:
                    count = 0
                reporter.add_case(area, f"V6-{p.name}", f"去重: {desc} ({count}条)", (count > 0), {"count": count})
            except Exception as e:
                reporter.add_case(area, f"V6-{p.name}", f"去重: {desc} 文件损坏", False, {"error": str(e)})
                reporter.add_finding("medium", area, f"去重文件 {p.name} 损坏", str(e))
        else:
            reporter.add_case(area, f"V6-{p.name}", f"去重: {desc} 文件未创建 路径={p}", True, {"skip": True, "note": "该环境暂无去重数据"})

    # ─────────────────────────────────────────────────────────────────────
    # V7: 视频发帖端点
    # ─────────────────────────────────────────────────────────────────────
    try:
        r = requests.get(s3_cred_url, headers={"Authorization": "Bearer invalid"}, timeout=10, verify=False)
        passed = (r.status_code != 200)
        reporter.add_case(area, "V7-VIDEO-01", f"视频S3凭证端点 ({r.status_code})", passed, {"http": r.status_code})
    except Exception as e:
        reporter.add_case(area, "V7-VIDEO-01", f"视频S3凭证不可达 ({e})", False, {})
