#!/usr/bin/env python3
"""
gitlab_pull.py — 在无 git 环境下，通过 GitLab REST API 拉取 tester/auto-poster 的文件。

用法：
    py -3 scripts/gitlab_pull.py \
        --files post_moments.py config.py utils.py retry.py validation.py requirements.txt .env.example \
        --out  ./pulled

环境变量（取自 .env）：
    GITLAB_BASE_URL       默认 http://100.64.0.45:8999
    GITLAB_USERNAME       OAuth password grant 用户名
    GITLAB_PASSWORD       OAuth password grant 密码
    GITLAB_TOKEN          Personal Access Token（如果设置则优先用它，绕过密码模式）
    GITLAB_PROJECT_ID     默认 207
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_token() -> str:
    pat = os.getenv("GITLAB_TOKEN")
    if pat:
        return pat

    base = os.getenv("GITLAB_BASE_URL", "http://100.64.0.45:8999").rstrip("/")
    username = os.getenv("GITLAB_USERNAME")
    password = os.getenv("GITLAB_PASSWORD")
    if not (username and password):
        sys.exit("[FATAL] 需要在 .env 设置 GITLAB_TOKEN，或同时设置 GITLAB_USERNAME + GITLAB_PASSWORD")

    r = requests.post(
        f"{base}/oauth/token",
        json={"grant_type": "password", "username": username, "password": password},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def download(token: str, file_path: str, ref: str, out_dir: Path) -> Path:
    base = os.getenv("GITLAB_BASE_URL", "http://100.64.0.45:8999").rstrip("/")
    project_id = os.getenv("GITLAB_PROJECT_ID", "207")
    # PAT 用 PRIVATE-TOKEN，OAuth 用 Authorization: Bearer
    headers = (
        {"PRIVATE-TOKEN": token}
        if token.startswith("glpat-")
        else {"Authorization": f"Bearer {token}"}
    )
    url = (
        f"{base}/api/v4/projects/{project_id}/repository/files/"
        f"{quote(file_path, safe='')}/raw?ref={ref}"
    )
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / file_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(r.content)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--files",
        nargs="+",
        required=True,
        help="GitLab 仓库内的文件路径列表",
    )
    ap.add_argument("--ref", default="main")
    ap.add_argument("--out", default="./pulled")
    args = ap.parse_args()

    token = get_token()
    out_dir = Path(args.out)
    for fp in args.files:
        try:
            dst = download(token, fp, args.ref, out_dir)
            print(f"[OK]  {fp}  ->  {dst}  ({dst.stat().st_size} B)")
        except Exception as e:  # noqa: BLE001
            print(f"[ERR] {fp}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
