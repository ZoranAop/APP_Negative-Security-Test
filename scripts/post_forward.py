#!/usr/bin/env python3
"""
post_forward.py — 动态转发（转发原帖 + 附带简短评论）发布工具

在 XXAI 广场中，「转发」是创建一条新动态，通过 media_info 里的
forwarded_post_id / forwarded_user_name / forwarded_desc 等字段引用原帖，
正文 content 写转发时附带的评论。

用法：
    # 单帖模式：从评论者 CSV 随机选 N 个用户转发同一帖子
    py -3 scripts/post_forward.py \
        --post-id 743357196930125824 \
        --commenters accounts.csv \
        --tokens result/tokens.json \
        --count 2 \
        --text "感觉不错"

    # 批量模式（指定每行用户与转发评论）
    py -3 scripts/post_forward.py \
        --batch forwards_batch.csv \
        --tokens result/tokens.json \
        --accounts accounts.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DEFAULT_FEED_API = "https://feed-api.xxai.com/api/v1/moments/"
DEFAULT_LOGIN_URL = os.getenv("LOGIN_URL", "https://api.xxai.com/login")


def load_tokens(path: str) -> dict[str, str]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_tokens(tokens: dict[str, str], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)


def load_accounts(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _build_account_map(accounts_csv: str | None) -> dict[str, str]:
    if not accounts_csv or not Path(accounts_csv).exists():
        return {}
    return {
        (r.get("邮箱") or r.get("email") or "").strip():
        (r.get("密码") or r.get("password") or "").strip()
        for r in load_accounts(accounts_csv)
    }


def _login(email: str, password: str, login_url: str, timeout: int = 15) -> str | None:
    device_id = os.getenv("POST_DEVICE_ID", "auto_poster")
    device_name = os.getenv("POST_DEVICE_NAME", "auto_poster_client")
    try:
        r = requests.post(login_url,
                          json={"email": email, "password": password,
                                "device_id": device_id, "device_name": device_name},
                          headers={"Content-Type": "application/json"}, timeout=timeout)
        if r.status_code == 200 and r.json().get("code") == 0:
            return r.json()["data"]["token"]
    except Exception:
        pass
    return None


def _base(feed_api: str) -> str:
    return feed_api.replace("/api/v1/moments/", "").replace("/api/v1/moments", "")


def get_moment_detail(token: str, post_id: int, feed_api: str) -> dict | None:
    """读取原帖详情，用于填充 forwarded_* 字段。"""
    try:
        r = requests.get(f"{_base(feed_api)}/api/v1/moments/detail?moment_id={post_id}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=15)
        j = r.json()
        if j.get("code") == 0:
            return j.get("data") or {}
    except Exception:
        pass
    return None


def post_forward(token: str, orig: dict, content: str, feed_api: str) -> tuple[bool, str]:
    """以转发形式发布一条新动态，返回 (成功与否, 失败原因)。

    转发需完整携带原帖内容：图文原帖带原图，视频原帖带视频+封面，
    文本原帖通过 forwarded_desc 携带原文（不截断）。
    """
    mi = orig.get("media_info") or {}
    media: dict = {
        "type": "text",
        "forwarded_post_id": str(orig.get("id") or ""),
        "forwarded_post_user_id": str(orig.get("user_id") or ""),
        "forwarded_user_name": orig.get("user_name") or orig.get("nickname") or "",
        "forwarded_user_avatar": orig.get("user_avatar") or "",
        "forwarded_desc": orig.get("content") or "",
    }
    if mi.get("type") == "image" and mi.get("images"):
        media["type"] = "image"
        media["images"] = mi["images"]
    elif mi.get("type") == "video":
        media["type"] = "video"
        media["video_url"] = mi.get("video_url") or ""
        media["thumbnail_url"] = mi.get("thumbnail_url") or ""
    payload = {
        "content": content,
        "visibility": 0,
        "media_info": media,
    }
    try:
        r = requests.post(feed_api, json=payload,
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json"}, timeout=15)
        j = r.json()
        if j.get("code") == 0:
            return True, str(j.get("data", {}).get("moment_id", ""))
        return False, j.get("msg", "") or r.text[:100]
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _try_forward_with_refresh(email, password, token, orig, content,
                              feed_api, login_url) -> tuple[bool, str, str | None]:
    if not token:
        if password:
            new_token = _login(email, password, login_url)
            if new_token:
                ok, reason = post_forward(new_token, orig, content, feed_api)
                return (True, reason, new_token) if ok else (False, f"login_ok_but_fail: {reason}", None)
            return False, "login_fail", None
        return False, "no_token", None
    ok, reason = post_forward(token, orig, content, feed_api)
    if ok:
        return True, reason, None
    if "token_invalid" in reason or "expired" in reason.lower() or "session has expired" in reason.lower():
        if password:
            new_token = _login(email, password, login_url)
            if new_token:
                ok2, reason2 = post_forward(new_token, orig, content, feed_api)
                return (True, reason2, new_token) if ok2 else (False, f"retry_fail: {reason2}", None)
            return False, "login_fail", None
        return False, f"token_expired: {reason[:60]}", None
    return False, reason[:80], None


def main():
    ap = argparse.ArgumentParser(description="动态转发发布工具（转发原帖 + 简短评论）")
    ap.add_argument("--post-id", type=int, help="原帖 ID（单帖模式）")
    ap.add_argument("--commenters", default="accounts.csv", help="转发者账号 CSV")
    ap.add_argument("--tokens", default="result/tokens.json", help="token JSON")
    ap.add_argument("--count", type=int, default=2, help="转发条数（单帖模式）")
    ap.add_argument("--text", help="转发评论内容（单帖模式统一文本）")
    ap.add_argument("--batch", help="批量转发 CSV（post_id,email,nickname,text）")
    ap.add_argument("--accounts", help="账号 CSV（token 过期时自动重新登录）")
    ap.add_argument("--feed-api", default=DEFAULT_FEED_API)
    ap.add_argument("--login-url", default=DEFAULT_LOGIN_URL)
    ap.add_argument("--tokens-out", help="刷新后 token 输出路径（默认覆盖 --tokens）")
    ap.add_argument("--delay", type=float, default=5.0, help="每条间隔秒数")
    args = ap.parse_args()

    tokens = load_tokens(args.tokens)
    print(f"[Token] 加载 {len(tokens)} 个 token")
    tokens_out = args.tokens_out or args.tokens
    account_map = _build_account_map(args.accounts)
    changes = 0

    def _run(email, password, orig, text):
        nonlocal changes
        token = tokens.get(email)
        ok, status, new_token = _try_forward_with_refresh(
            email, password, token, orig, text, args.feed_api, args.login_url)
        if new_token:
            tokens[email] = new_token
            changes += 1
        return ok, status

    if args.batch:
        with open(args.batch, encoding="utf-8-sig") as f:
            tasks = list(csv.DictReader(f))
        print(f"[Batch] {len(tasks)} 条转发任务")
        success = 0
        for i, t in enumerate(tasks):
            email = (t.get("email") or "").strip()
            text = (t.get("text") or t.get("content") or "").strip()
            pid = int(t.get("post_id", 0))
            password = account_map.get(email)
            token = tokens.get(email)
            orig = get_moment_detail(token, pid, args.feed_api) if token else None
            if orig is None and password:
                new_tok = _login(email, password, args.login_url)
                if new_tok:
                    tokens[email] = new_tok
                    changes += 1
                    token = new_tok
                    orig = get_moment_detail(token, pid, args.feed_api)
            if orig is None:
                print(f"  [{i+1}] {t.get('nickname', email)} 原帖读取失败")
                continue
            ok, status = _run(email, password, orig, text)
            label = t.get("nickname", email)
            print(f"  [{i+1}] {label} → {pid} {status}")
            if ok:
                success += 1
            if i < len(tasks) - 1:
                time.sleep(args.delay)
        if changes:
            _save_tokens(tokens, tokens_out)
            print(f"[Token] 刷新了 {changes} 个 token → {tokens_out}")
        print(f"\n[Result] {success}/{len(tasks)}")
        return 0 if success > 0 else 1

    # 单帖模式
    if not args.post_id:
        print("需要 --post-id 或 --batch")
        return 1

    # 用第一个可用 token 读原帖（读详情对 token 有效性不敏感，尽力即可）
    orig = None
    for email, tok in tokens.items():
        orig = get_moment_detail(tok, args.post_id, args.feed_api)
        if orig:
            break
    if orig is None:
        print("[Error] 无法读取原帖详情，请确认 post-id 与 token 有效")
        return 1

    forwarders = load_accounts(args.commenters)
    random.shuffle(forwarders)
    selected = forwarders[:args.count]

    print(f"[Target] post_id={args.post_id}")
    success = 0
    for i, c in enumerate(selected):
        email = (c.get("邮箱") or c.get("email") or "").strip()
        password = (c.get("密码") or c.get("password") or "").strip()
        text = args.text if args.text else "转发"
        ok, status = _run(email, password, orig, text)
        label = c.get("昵称", email)
        print(f"  [{i+1}] {label}: \"{text[:40]}\" {status}")
        if ok:
            success += 1
        if i < len(selected) - 1:
            time.sleep(args.delay)
    if changes:
        _save_tokens(tokens, tokens_out)
        print(f"[Token] 刷新了 {changes} 个 token → {tokens_out}")
    print(f"\n[Result] {success}/{len(selected)}")
    return 0 if success > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
