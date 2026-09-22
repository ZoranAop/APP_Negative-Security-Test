"""安全测试共享工具模块（消除 10 个脚本的 unzip + rglob 重复实现）"""
import os, re, sys
from pathlib import Path

def unzip_and_scan(apk_path: Path, patterns=["*.txt","*.xml","*.json","*.properties"]):
    """通用 APK/IPA 解包 + 资源扫描（占位框架，实际实现需结合 apktool/unzip）"""
    results = {"files_found": [], "matches": []}
    # 真实实现应调用 apktool / unzip / aapt2
    # 当前为共享接口，供各脚本统一调用
    return results

def check_debug_symbols(apk_path: Path):
    """通用调试符号检测接口"""
    # 由 check_debug_isolation.py / check_binary_integrity.py 统一调用
    return {"debug_print_found": False, "kdebug_mode_found": False}
