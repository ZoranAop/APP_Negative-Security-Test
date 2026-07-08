#!/usr/bin/env python3
"""
配置管理模块
统一管理项目配置、API 地址、默认参数等
"""

import os
from typing import Optional

# 载入 .env 配置文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # 优雅降级：若未安装 python-dotenv 且存在 .env，进行手动简易解析
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as env_file:
                for line in env_file:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip().strip('"').strip("'")
        except Exception:
            pass


class Config:
    """全局配置类"""

    # ==================== API 配置 ====================
    # 登录 API
    LOGIN_URL: str = os.getenv(
        "LOGIN_URL",
        "https://devapi-x.tp-ex.com/login"
    )

    # 朋友圈发布 API
    MOMENTS_API_URL: str = os.getenv(
        "MOMENTS_API_URL",
        "http://100.64.0.47:8889/api/v1/moments/"
    )


    # ==================== 小红书爬虫配置 ====================
    # 小红书探索页 URL
    XHS_EXPLORE_URL: str = "https://www.xiaohongshu.com/explore"

    # 小红书笔记详情 URL 模板
    XHS_NOTE_URL_TEMPLATE: str = "https://www.xiaohongshu.com/explore/{note_id}"

    # 请求头配置
    XHS_USER_AGENT: str = os.getenv(
        "XHS_USER_AGENT",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    XHS_HEADERS = {
        'User-Agent': XHS_USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.xiaohongshu.com/'
    }

    # ==================== 爬虫默认参数 ====================
    # 默认目标新增数量
    CRAWL_DEFAULT_TARGET: int = int(os.getenv("CRAWL_DEFAULT_TARGET", "200"))

    # 默认最大请求次数
    CRAWL_DEFAULT_MAX_REQUESTS: int = int(os.getenv("CRAWL_DEFAULT_MAX_REQUESTS", "30"))

    # 默认请求延迟（秒）
    CRAWL_DEFAULT_DELAY: float = float(os.getenv("CRAWL_DEFAULT_DELAY", "1.5"))

    # 默认 CSV 路径
    CRAWL_DEFAULT_CSV: str = os.getenv("CRAWL_DEFAULT_CSV", "moments.csv")

    # 请求超时时间（秒）
    CRAWL_REQUEST_TIMEOUT: int = int(os.getenv("CRAWL_REQUEST_TIMEOUT", "15"))

    # ==================== 发帖默认参数 ====================
    # 默认账号 CSV 路径
    POST_DEFAULT_ACCOUNTS_CSV: str = os.getenv(
        "POST_DEFAULT_ACCOUNTS_CSV",
        "企管用户_邮箱密码pincode_200.csv"
    )

    # 默认素材 CSV 路径
    POST_DEFAULT_CSV: str = os.getenv("POST_DEFAULT_CSV", "moments.csv")

    # 默认并发数
    POST_DEFAULT_CONCURRENCY: int = int(os.getenv("POST_DEFAULT_CONCURRENCY", "1"))

    # 默认延迟（秒）
    POST_DEFAULT_DELAY: float = float(os.getenv("POST_DEFAULT_DELAY", "2.0"))

    # 最大图片数量限制
    POST_MAX_IMAGES: int = int(os.getenv("POST_MAX_IMAGES", "9"))

    # 登录设备信息
    POST_DEVICE_ID: str = os.getenv("POST_DEVICE_ID", "auto_poster")
    POST_DEVICE_NAME: str = os.getenv("POST_DEVICE_NAME", "auto_poster_client")

    # 请求超时时间（秒）
    POST_REQUEST_TIMEOUT: int = int(os.getenv("POST_REQUEST_TIMEOUT", "15"))

    # 顺序登录间隔（秒）- publish_from_tokens 使用
    # 实测经验：并发登录 20 账号 -> 12/20 触发 429；
    # 顺序 + 2.5s 间距 -> 20/20 通过
    LOGIN_SPACING: float = float(os.getenv("LOGIN_SPACING", "2.5"))

    # ==================== 上传 / 素材站 ====================
    # S3 临时凭证接口
    UPLOAD_CREDENTIALS_URL: str = os.getenv(
        "UPLOAD_CREDENTIALS_URL",
        "https://devapi-x.tp-ex.com/file/upload/credentials"
    )

    # OpenNana 素材源
    OPENNANA_API_BASE: str = os.getenv("OPENNANA_API_BASE", "https://api.opennana.com")

    # open-prompts.com 素材源
    OPENPROMPTS_API_BASE: str = os.getenv(
        "OPENPROMPTS_API_BASE", "https://www.open-prompts.com/api"
    )

    # lovimg.com 素材源
    LOVIMG_BASE: str = os.getenv("LOVIMG_BASE", "https://lovimg.com")

    # 多源采集默认（multi_source_fetch.py）
    MULTI_SOURCE_DEFAULT: str = os.getenv(
        "MULTI_SOURCE_DEFAULT", "opennana,openprompts,lovimg"
    )

    # 默认过滤广告
    MULTI_SOURCE_EXCLUDE_ADS_DEFAULT: bool = os.getenv(
        "MULTI_SOURCE_EXCLUDE_ADS_DEFAULT", "true"
    ).lower() in ("1", "true", "yes")

    # 默认主题
    MULTI_SOURCE_THEME_DEFAULT: str = os.getenv(
        "MULTI_SOURCE_THEME_DEFAULT", "beauty"
    )

    # ==================== 多语言文案 ====================
    # 生成 caption 时使用的语言组合（逗号分隔）
    # 支持：en / zh / zh_hant / ja
    CAPTION_LANGS_DEFAULT: str = os.getenv("CAPTION_LANGS_DEFAULT", "en,zh_hant,ja")

    # ==================== 重试配置 ====================
    # 最大重试次数
    MAX_RETRY_ATTEMPTS: int = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))

    # 重试初始延迟（秒）
    RETRY_INITIAL_DELAY: float = float(os.getenv("RETRY_INITIAL_DELAY", "1.0"))

    # 重试指数退避因子
    RETRY_BACKOFF_FACTOR: float = float(os.getenv("RETRY_BACKOFF_FACTOR", "2.0"))

    # 重试最大延迟（秒）
    RETRY_MAX_DELAY: float = float(os.getenv("RETRY_MAX_DELAY", "10.0"))

    # ==================== 输出配置 ====================
    # 结果目录
    RESULT_DIR: str = os.getenv("RESULT_DIR", "result")

    # 日志目录
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")

    # 日志级别
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ==================== Vision LLM 配置 ====================
    # 通用/默认配置：即 2. 视觉模型 (Vision-only / Specialized Vision Model) 配置
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")

    # 1. 纯 VL 模型 (Vision-Language) 配置 (若留空/未配置，兜底使用通用配置)
    LLM_VL_API_KEY: str = os.getenv("LLM_VL_API_KEY") if os.getenv("LLM_VL_API_KEY") is not None else LLM_API_KEY
    LLM_VL_API_BASE: str = os.getenv("LLM_VL_API_BASE") if os.getenv("LLM_VL_API_BASE") is not None else LLM_API_BASE
    LLM_VL_MODEL: str = os.getenv("LLM_VL_MODEL") if os.getenv("LLM_VL_MODEL") is not None else LLM_MODEL

    # 3. 纯 LLM 文本模型 (Pure Text LLM) 配置 (若留空/未配置，兜底使用通用配置)
    LLM_TEXT_API_KEY: str = os.getenv("LLM_TEXT_API_KEY") if os.getenv("LLM_TEXT_API_KEY") is not None else LLM_API_KEY
    LLM_TEXT_API_BASE: str = os.getenv("LLM_TEXT_API_BASE") if os.getenv("LLM_TEXT_API_BASE") is not None else LLM_API_BASE
    LLM_TEXT_MODEL: str = os.getenv("LLM_TEXT_MODEL") if os.getenv("LLM_TEXT_MODEL") is not None else LLM_MODEL

    # ==================== CSV 字段映射 ====================
    # 账号 CSV 字段映射
    ACCOUNTS_CSV_EMAIL_FIELDS = ["邮箱", "email", "username", "Email", "Username"]
    ACCOUNTS_CSV_PASSWORD_FIELDS = ["密码", "password", "Password"]

    # 素材 CSV 必需字段
    MOMENTS_CSV_REQUIRED_FIELDS = ["content"]

    # 素材 CSV 可选字段
    MOMENTS_CSV_OPTIONAL_FIELDS = [
        "visibility", "room_id", "is_async", "is_vip_group", "image_urls",
        "video_url", "thumbnail_url",
        "location_name", "location_address",
        "location_lat", "location_lon"
    ]

    @classmethod
    def get_retry_delays(cls) -> list:
        """获取重试延迟序列"""
        delays = []
        delay = cls.RETRY_INITIAL_DELAY
        for _ in range(cls.MAX_RETRY_ATTEMPTS):
            delays.append(min(delay, cls.RETRY_MAX_DELAY))
            delay *= cls.RETRY_BACKOFF_FACTOR
        return delays

    @classmethod
    def validate(cls) -> bool:
        """验证配置是否有效"""
        # 可以添加配置验证逻辑
        return True


# 创建全局配置实例
config = Config()


def get_config() -> Config:
    """获取全局配置实例"""
    return config
