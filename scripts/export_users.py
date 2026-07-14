#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_users.py —— 从 XXAI 商户后台批量导出企管用户账号（含密码 / pincode）

用途：
    为广场发布工具（post_moments.py / publish_from_tokens.py）生成账号池 CSV。
    产出列与 templates/accounts.example.csv 一致：
        序号,user_id,邮箱,用户名,昵称,密码,pincode

数据来源（商户端 API，baseURL 见 XXAI_API_BASE）：
    1. GET  /user/pool-users?page=&page_size=   用户池列表（约 10000，含 email）
       GET  /user/users?page=&page_size=        企管注册用户列表（约 21）
       —— 两个列表接口都【不返回】password / pin_code
    2. POST /user/assume {"user_id": <id>}       逐用户获取凭证
       —— 返回 data.{localpart, token, password, pin_code, device_id}
          这正是后台「用户列表 → 编辑」弹窗里展示、可复制的密码与 pincode

鉴权：
    需商户端 Bearer Token（登录后台后从浏览器请求头 Authorization 复制）。
    通过环境变量 / .env 提供，切勿硬编码或提交到仓库。

用法：
    py -3 scripts/export_users.py                          # 用 .env 默认参数
    py -3 scripts/export_users.py --count 2000 --source pool
    py -3 scripts/export_users.py --count 500 --no-credentials --out accounts_500.csv

依赖：requests, python-dotenv（见 scripts/requirements.txt）
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ==================== 配置（环境变量优先） ====================

def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


API_BASE = _env("XXAI_API_BASE", "https://merchant-api.xxai.com").rstrip("/")
TOKEN = _env("XXAI_TOKEN", "")

SOURCE_ENDPOINTS = {
    "pool": "/user/pool-users",      # 用户池
    "register": "/user/users",       # 企管注册用户
}

# 导出列顺序，与 templates/accounts.example.csv 保持一致
CSV_HEADER = ["序号", "user_id", "邮箱", "用户名", "昵称", "密码", "pincode"]


# ==================== HTTP ====================

def _headers() -> dict:
    if not TOKEN:
        sys.exit("[FATAL] 缺少 XXAI_TOKEN，请在 .env 或环境变量中配置商户端 Bearer Token")
    return {"Authorization": f"Bearer {TOKEN}"}


def fetch_user_list(source: str, count: int, page_size: int = 200, timeout: int = 30) -> list:
    """分页拉取用户列表，最多 count 条。"""
    endpoint = SOURCE_ENDPOINTS.get(source)
    if not endpoint:
        sys.exit(f"[FATAL] 未知 source: {source}（可选：{'/'.join(SOURCE_ENDPOINTS)}）")

    url = f"{API_BASE}{endpoint}"
    users: list = []
    page = 1
    while len(users) < count:
        resp = requests.get(
            url,
            headers=_headers(),
            params={"page": page, "page_size": page_size},
            timeout=timeout,
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            sys.exit(f"[FATAL] 列表接口返回错误 page={page}: {body.get('msg')}")
        data = body.get("data") or {}
        lst = data.get("list") or []
        if not lst:
            break
        for u in lst:
            users.append(u)
            if len(users) >= count:
                break
        total = data.get("total")
        print(f"  page {page} -> 已拉取 {len(users)} / 目标 {count}（可用 total={total}）")
        page += 1
    return users


# 每个线程独立 session，避免并发共享问题
_local = threading.local()


def _session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        _local.session = s
    return s


def fetch_credentials(user_id, retries: int = 4, timeout: int = 20) -> dict:
    """
    调用 POST /user/assume 获取单个用户凭证。
    返回 {"password": str, "pin_code": str, "localpart": str, "ok": bool, "err": str}
    """
    url = f"{API_BASE}/user/assume"
    headers = {**_headers(), "Content-Type": "application/json"}
    out = {"user_id": user_id, "password": "", "pin_code": "", "localpart": "", "ok": False, "err": ""}
    for attempt in range(1, retries + 1):
        try:
            resp = _session().post(url, headers=headers, json={"user_id": user_id}, timeout=timeout)
            body = resp.json()
            if body.get("code") == 0 and body.get("data"):
                d = body["data"]
                out["password"] = str(d.get("password", ""))
                out["pin_code"] = str(d.get("pin_code", ""))
                out["localpart"] = str(d.get("localpart", ""))
                out["ok"] = True
                return out
            out["err"] = f"code={body.get('code')} {body.get('msg')}"
        except Exception as exc:  # noqa: BLE001
            out["err"] = str(exc)
        time.sleep(0.3 * attempt)
    return out


def fetch_all_credentials(user_ids: list, concurrency: int = 8) -> dict:
    """并发拉取所有用户凭证，返回 {user_id: creds}。"""
    result: dict = {}
    done = 0
    total = len(user_ids)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(fetch_credentials, uid): uid for uid in user_ids}
        for fut in as_completed(futures):
            creds = fut.result()
            result[creds["user_id"]] = creds
            done += 1
            if done % 200 == 0 or done == total:
                ok = sum(1 for c in result.values() if c["ok"])
                print(f"  凭证进度 {done}/{total}（成功 {ok}）")
    return result


# ==================== 组装 & 写出 ====================

def build_rows(users: list, creds: dict | None) -> list:
    rows = []
    for idx, u in enumerate(users, start=1):
        uid = u.get("user_id") or u.get("id")
        c = (creds or {}).get(uid, {})
        rows.append({
            "序号": idx,
            "user_id": uid,
            "邮箱": u.get("email", ""),
            "用户名": u.get("username", ""),
            "昵称": u.get("nickname", ""),
            "密码": c.get("password", ""),
            "pincode": c.get("pin_code", ""),
        })
    return rows


def write_csv(rows: list, out_path: str) -> None:
    # utf-8-sig 带 BOM，Excel 打开中文不乱码
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(rows)


# ==================== CLI ====================

def main() -> None:
    parser = argparse.ArgumentParser(description="导出 XXAI 企管用户账号（含密码/pincode）")
    parser.add_argument("--source", default=_env("XXAI_SOURCE", "pool"),
                        choices=list(SOURCE_ENDPOINTS), help="用户来源：pool（用户池）/ register（企管注册）")
    parser.add_argument("--count", type=int, default=int(_env("XXAI_COUNT", "2000")),
                        help="导出数量（默认 2000）")
    parser.add_argument("--concurrency", type=int, default=int(_env("XXAI_CONCURRENCY", "8")),
                        help="/user/assume 并发数（默认 8）")
    parser.add_argument("--no-credentials", action="store_true",
                        help="仅导出账号/邮箱/昵称，跳过密码/pincode")
    parser.add_argument("--out", default="", help="输出 CSV 路径（默认 accounts_<source>_<count>.csv）")
    args = parser.parse_args()

    fetch_creds_flag = not args.no_credentials
    out_path = args.out or f"accounts_{args.source}_{args.count}.csv"

    print(f"[1/3] 拉取用户列表：source={args.source} count={args.count}")
    users = fetch_user_list(args.source, args.count)
    print(f"      共获取 {len(users)} 个用户")

    creds = None
    if fetch_creds_flag:
        print(f"[2/3] 拉取密码/pincode（POST /user/assume，并发 {args.concurrency}）")
        ids = [u.get("user_id") or u.get("id") for u in users]
        creds = fetch_all_credentials(ids, concurrency=args.concurrency)
        ok = sum(1 for c in creds.values() if c["ok"])
        fail = len(creds) - ok
        print(f"      凭证获取完成：成功 {ok}，失败 {fail}")
        if fail:
            failed_ids = [str(uid) for uid, c in creds.items() if not c["ok"]]
            print(f"      失败 user_id: {', '.join(failed_ids)}")
    else:
        print("[2/3] 跳过凭证获取（--no-credentials）")

    print(f"[3/3] 写出 CSV -> {out_path}")
    rows = build_rows(users, creds)
    write_csv(rows, out_path)
    with_pw = sum(1 for r in rows if r["密码"])
    print(f"完成：{len(rows)} 行，含密码/pincode {with_pw} 行 -> {out_path}")


if __name__ == "__main__":
    main()
