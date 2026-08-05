#!/usr/bin/env python3
"""
公共工具模块
提供日志、颜色输出、文件操作等通用功能
"""

import io
import logging
import os
import sys
from typing import Optional

# ANSI 颜色定义
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""

    COLORS = {
        'DEBUG': Colors.CYAN,
        'INFO': Colors.BLUE,
        'WARNING': Colors.WARNING,
        'ERROR': Colors.FAIL,
        'CRITICAL': Colors.FAIL + Colors.BOLD,
    }

    def format(self, record):
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}[{levelname}]{Colors.ENDC}"
        return super().format(record)


def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None,
    console: bool = True
) -> logging.Logger:
    """
    配置并返回一个 logger

    Args:
        name: logger 名称
        level: 日志级别
        log_file: 日志文件路径（可选）
        console: 是否输出到控制台

    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    # 控制台输出
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_formatter = ColoredFormatter(
            '%(levelname)s %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # 文件输出
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


# 兼容旧代码的简单日志函数
def log_info(msg: str):
    print(f"{Colors.BLUE}[INFO]{Colors.ENDC} {msg}")

def log_success(msg: str):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.ENDC} {msg}")

def log_warn(msg: str):
    print(f"{Colors.WARNING}[WARN]{Colors.ENDC} {msg}")

def log_error(msg: str):
    print(f"{Colors.FAIL}[ERROR]{Colors.ENDC} {msg}")

def log_debug(msg: str):
    print(f"{Colors.CYAN}[DEBUG]{Colors.ENDC} {msg}")


def ensure_dir(path: str) -> None:
    """确保目录存在，不存在则创建"""
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def format_duration(seconds: float) -> str:
    """格式化时间显示"""
    if seconds < 60:
        return f"{seconds:.2f} 秒"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes} 分 {secs:.1f} 秒"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours} 小时 {minutes} 分"


def format_timestamp(timestamp: float) -> str:
    """格式化时间戳"""
    import time
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))


def print_section_header(title: str, width: int = 60, char: str = "="):
    """打印章节标题"""
    print("\n" + char * width)
    print(f"{Colors.BOLD}{title}{Colors.ENDC}")
    print(char * width)


def print_section_separator(width: int = 60, char: str = "-"):
    """打印分隔线"""
    print(char * width)


def format_percentage(value: float, total: float, decimals: int = 2) -> str:
    """格式化百分比"""
    if total == 0:
        return "0.00%"
    percentage = (value / total) * 100
    return f"{percentage:.{decimals}f}%"


# ============================================================
# 跨脚本共享工具（审计后提取，消除重复）
# ============================================================

def ensure_utf8_stdout():
    """将 stdout/stderr 包装为 UTF-8 编码，避免 Windows GBK 乱码。"""
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


def run_cmd(cmd: list[str], *, cwd: str | None = None, env_extra: dict | None = None) -> int:
    """执行子进程命令，返回退出码。自动设置 PYTHONIOENCODING=utf-8。"""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    import subprocess
    return subprocess.call(cmd, cwd=cwd, env=env)


def strip_source_attribution(text: str, known_sites: set[str] | None = None) -> str:
    """移除文案中的来源/出处标记，使帖子看起来像用户原创。

    由 run_tech.py / run_us_life.py / run_jp_life.py / run_tw_life.py 等脚本共享。
    各脚本传入不同的 known_sites 集合即可。
    """
    import re as _re
    if not text:
        return text
    # 1. 中文括号来源
    text = _re.sub(r'[（(]\s*[來来]源\s*[:：]?\s*[^）)]+[）)]', '', text)
    # 2. 英文/日文括号 via/source/出典
    text = _re.sub(r'\(\s*(?:via|source|sumber|出典)\s*[:：]?\s*[^)]+\)', '', text)
    # 3/4. 方括号前缀
    if known_sites:
        _escaped = [_re.escape(n) for n in known_sites if n]
        if _escaped:
            _pat = '|'.join(sorted(_escaped, key=len, reverse=True))
            text = _re.sub(r'【(?:' + _pat + r')(?:速報|ニュース|新闻)?】', '', text)
            text = _re.sub(r'\[(?:' + _pat + r')\]\s*', '', text)
            # 5. 行内 via/出典 + 站名
            text = _re.sub(r'(?:出典|via|來源|来源|from|reported by|courtesy of)\s*[:：]?\s*(?:' + _pat + r')', '', text, flags=_re.IGNORECASE)
            # 6. 引述
            text = _re.sub(r'(?:' + _pat + r')\s*(?:より|から|報道|レポート|报道|report)', '', text)
    # 7. 清理残留
    text = _re.sub(r'[ \t]{2,}', ' ', text)
    text = _re.sub(r'[（(]\s*[）)]', '', text)
    text = _re.sub(r'\[\s*\]', '', text)
    text = _re.sub(r'^\s*[,.\-—;:]+\s*', '', text)
    text = _re.sub(r' {2,}', ' ', text)
    return text.strip()
