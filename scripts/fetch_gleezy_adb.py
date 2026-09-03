# -*- coding: utf-8 -*-
"""
fetch_gleezy_adb.py — 通过 ADB 连接 MuMu 模拟器，提取 GLEEZY PRO 应用数据。
"""
import os
import sys
import json
import subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# MuMu ADB 路径
ADB_PATH = os.path.join(r"D:\程序", "模拟器", "MuMuPlayer", "nx_main", "adb.exe")

def run(cmd, capture=True):
    """运行命令，返回 (stdout, stderr, returncode)"""
    result = subprocess.run(
        cmd, shell=True, capture_output=capture,
        encoding="utf-8", errors="replace"
    )
    return result.stdout, result.stderr, result.returncode

def main():
    print(f"[ADB] 使用: {ADB_PATH}")
    print(f"[ADB] 存在: {os.path.exists(ADB_PATH)}")

    # 1. 检查设备连接
    print("\n=== Step 1: 检查设备连接 ===")
    stdout, stderr, rc = run(f'"{ADB_PATH}" devices')
    print(stdout)
    if "device" not in stdout.lower():
        print("[error] 未检测到设备，请先启动 MuMu 模拟器")
        return 1

    # 2. 查找 GLEEZY PRO 包名
    print("\n=== Step 2: 查找 GLEEZY PRO 应用 ===")
    stdout, _, _ = run(f'"{ADB_PATH}" shell pm list packages')
    gleezy_pkgs = [l.strip() for l in stdout.split('\n') if 'gleezy' in l.lower()]
    print(f"GLEEZY packages: {gleezy_pkgs}")

    # 也搜索可能的包名
    candidates = ['com.gleezy.pro', 'com.gleezy.app', 'com.gleezychat']
    found_pkg = None
    for pkg in candidates:
        stdout, _, _ = run(f'"{ADB_PATH}" shell pm path {pkg}')
        if 'package:' in stdout:
            found_pkg = pkg
            print(f"[found] 包名: {pkg}")
            break

    if not found_pkg and gleezy_pkgs:
        # 从列出的包名中提取
        found_pkg = gleezy_pkgs[0].split(':')[1] if ':' in gleezy_pkgs[0] else gleezy_pkgs[0]
        print(f"[using] {found_pkg}")

    if not found_pkg:
        print("[warn] 未找到 GLEEZY PRO，尝试列出所有包...")
        # 列出所有包
        for line in stdout.split('\n')[:50]:
            print(f"  {line.strip()}")
        return 1

    # 3. 导出应用数据
    print(f"\n=== Step 3: 导出 {found_pkg} 数据 ===")
    data_dir = Path("gleezy_dump")
    data_dir.mkdir(exist_ok=True)

    # 3.1 导出数据库
    db_paths = [
        f"/data/data/{found_pkg}/databases",
        f"/data/data/{found_pkg}/files",
    ]
    for db_path in db_paths:
        stdout, _, _ = run(f'"{ADB_PATH}" shell ls {db_path}')
        if stdout.strip():
            print(f"\n[{db_path}]:")
            for line in stdout.strip().split('\n'):
                fname = line.strip()
                if not fname:
                    continue
                remote = f"{db_path}/{fname}"
                local = data_dir / fname
                print(f"  拉取: {remote}")
                _, _, rc = run(f'"{ADB_PATH}" pull "{remote}" "{local}"')
                if rc == 0 and local.exists():
                    print(f"    -> {local} ({local.stat().st_size} bytes)")

    # 3.2 导出 SharedPreferences
    prefs_dir = f"/data/data/{found_pkg}/shared_prefs"
    stdout, _, _ = run(f'"{ADB_PATH}" shell ls {prefs_dir}')
    if stdout.strip():
        print(f"\n[{prefs_dir}]:")
        for line in stdout.strip().split('\n'):
            fname = line.strip()
            if not fname:
                continue
            remote = f"{prefs_dir}/{fname}"
            local = data_dir / fname
            _, _, rc = run(f'"{ADB_PATH}" pull "{remote}" "{local}"')
            if rc == 0 and local.exists():
                print(f"  -> {local}")

    # 3.3 导出应用 APK（可选）
    print(f"\n[APK] 获取安装包路径...")
    stdout, _, _ = run(f'"{ADB_PATH}" shell pm path {found_pkg}')
    for line in stdout.strip().split('\n'):
        if 'package:' in line:
            apk_remote = line.split('package:')[1].strip()
            apk_local = data_dir / f"{found_pkg.split('.')[-1]}.apk"
            print(f"  拉取: {apk_remote} -> {apk_local}")
            _, _, rc = run(f'"{ADB_PATH}" pull "{apk_remote}" "{apk_local}"')
            if rc == 0 and apk_local.exists():
                print(f"    -> {apk_local} ({apk_local.stat().st_size/1024/1024:.1f} MB)")

    print(f"\n[done] 数据已导出到: {data_dir.absolute()}")
    print("[next] 解析数据库内容，更新 sources/customs_images.json")
    return 0

if __name__ == "__main__":
    sys.exit(main())
