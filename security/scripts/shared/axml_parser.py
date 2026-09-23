#!/usr/bin/env python3
"""纯 Python AXML（binary AndroidManifest.xml）解析器。

aapt2 编译后的 AndroidManifest.xml 是二进制 AXML 格式，普通 XML 正则/解析器
无法读取。本模块不依赖 aapt2 / apktool / androguard，直接从 AXML 字符串池
提取 UTF-16LE 与 ASCII 字符串，重建域名、深链、组件、权限，供 NS-02/03/14 等
manifest 类脚本在无 Android SDK 环境下确定性解析。

用法：
    from axml_parser import parse_axml_manifest
    info = parse_axml_manifest(apk_path)   # 或 parse_axml_strings(path_to_manifest_bin)
"""
import os
import re
import zipfile


def _extract_string_pool(data: bytes):
    """提取 AXML 字符串（UTF-16LE 与 ASCII 两种池编码）。"""
    strs = set()
    # UTF-16LE 池：连续 [char][0x00] 段
    u16 = re.findall(rb"(?:[\x00-\xff][\x00]){3,}", data)
    for s in u16:
        t = s.decode("utf-16-le", errors="ignore")
        if t and any(c.isprintable() for c in t):
            strs.add(t)
    # ASCII 池
    ascii_runs = re.findall(rb"[\x20-\x7e]{3,}", data)
    for s in ascii_runs:
        strs.add(s.decode("latin-1"))
    return strs


def parse_axml_strings(manifest_bin: bytes):
    """返回 (raw_strings, normalized_terms) 两集合。
    normalized_terms 去掉 AXML 长度前缀噪声，转小写。"""
    raw = _extract_string_pool(manifest_bin)
    norm = set()
    for r in raw:
        for m in re.findall(r"[A-Za-z0-9\-._:]+", r):
            norm.add(m.lower())
    return raw, norm


def parse_axml_manifest(source: str):
    """source 可为 APK 路径或 binary manifest 路径。返回结构化解析结果。"""
    if source and os.path.exists(source):
        if zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as z:
                if "AndroidManifest.xml" in z.namelist():
                    data = z.read("AndroidManifest.xml")
                else:
                    data = b""
        else:
            data = open(source, "rb").read()
    else:
        data = b""

    raw, norm = parse_axml_strings(data)

    result = {
        "parsed": bool(data),
        "domains": {},
        "deep_link": {},
        "components": {},
        "permissions": [],
        "debug_components": [],
        "raw_term_count": len(norm),
    }

    # ---- 域名分类（NS-02）----
    dev_test = set()
    prod = set()
    third = set()
    for n in norm:
        if re.search(
            r"\b(dev|test|staging|local|localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168|10\.|172\.(1[6-9]|2[0-9]|3[01]))\.", n
        ) or re.search(r"\.test\.|\.dev\.|\.local$|test\.local", n):
            dev_test.add(n)
        if re.search(r"(xxai|ope)\.(com|ai|net|org)", n):
            prod.add(n)
        if re.search(r"google|firebase|gms|mlkit|crazecoder|dexterous|fluttercommunity|play\.google", n):
            third.add(n)
    result["domains"] = {
        "dev_test": sorted(dev_test - prod - third),
        "production": sorted(prod),
        "thirdparty": sorted(list(third)[:30]),
    }

    # ---- 深链（NS-03）----
    schemes = {n for n in norm if n in ("http", "https", "xxxai", "xxai", "file", "content", "intent")}
    hosts = {n for n in norm if re.fullmatch(r"[a-z0-9][a-z0-9.\-]*\.(com|ai|net|org)", n)}
    result["deep_link"] = {"schemes": sorted(schemes), "hosts": sorted(hosts)}

    # ---- 组件暴露（NS-14）----
    # 字符串池中组件全限定名形如 "dev.fluttercommunity.plus.share.sharefileprovider"
    # （1-byte 长度前缀噪声已去除）。排除第三方 SDK 自带的 debug/test 命名：
    # - dev.fluttercommunity.* 是 Flutter share_plus 第三方插件命名空间
    # - 仅把含 DebugActivity/OopsActivity 等业务调试组件标记为违规
    _THIRDPARTY_PREFIX = ("dev.fluttercommunity", "com.google", "com.dexterous",
                          "io.flutter", "com.crazecoder", "androidx")
    exported_debug = set()
    for n in norm:
        if any(n.startswith(p) for p in _THIRDPARTY_PREFIX):
            continue
        if re.search(r"(activity|service|receiver|provider)", n, re.I) and \
           re.search(r"(debug|oops|mock|test)", n, re.I):
            exported_debug.add(n)
    result["components"] = {"exported_debug": sorted(exported_debug)}
    # 业务调试组件（字符串池直接含 Debug/Oops/DevMenu/MockServer 等）
    result["debug_components"] = sorted(
        n for n in norm
        if re.search(r"(oops|devmenu|mockserver|debugactivity|debugpanel)", n, re.I)
    )
    # 权限（含敏感）
    result["permissions"] = sorted(n for n in norm if n.startswith("android.permission."))
    return result
