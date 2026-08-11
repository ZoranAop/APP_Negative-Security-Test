#!/usr/bin/env python3
"""
网络请求重试模块
提供带有指数退避的自动重试功能
"""

import time
import random
import requests
from typing import Callable, Optional, Any, Dict
from functools import wraps

from config import config
from utils import log_warn, log_debug


class RetryError(Exception):
    """重试失败异常"""
    pass


def exponential_backoff_retry(
    func: Callable,
    max_attempts: Optional[int] = None,
    initial_delay: Optional[float] = None,
    backoff_factor: Optional[float] = None,
    max_delay: Optional[float] = None,
    exceptions: tuple = (requests.exceptions.RequestException,),
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
) -> Any:
    """
    使用指数退避策略重试函数

    Args:
        func: 要重试的函数
        max_attempts: 最大尝试次数
        initial_delay: 初始延迟（秒）
        backoff_factor: 退避因子
        max_delay: 最大延迟（秒）
        exceptions: 需要重试的异常类型元组
        on_retry: 重试时的回调函数 (attempt, exception, delay)

    Returns:
        函数执行结果

    Raises:
        RetryError: 重试次数耗尽后抛出
    """
    max_attempts = max_attempts or config.MAX_RETRY_ATTEMPTS
    initial_delay = initial_delay or config.RETRY_INITIAL_DELAY
    backoff_factor = backoff_factor or config.RETRY_BACKOFF_FACTOR
    max_delay = max_delay or config.RETRY_MAX_DELAY

    delay = initial_delay
    last_exception = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except exceptions as e:
            last_exception = e

            if attempt >= max_attempts:
                break

            # 计算下次延迟（含 jitter 避免惊群效应）
            current_delay = min(delay * (0.5 + random.random()), max_delay)

            # 调用回调
            if on_retry:
                on_retry(attempt, e, current_delay)
            else:
                log_warn(f"请求失败 (尝试 {attempt}/{max_attempts}): {e}，{current_delay:.1f} 秒后重试...")

            time.sleep(current_delay)
            delay *= backoff_factor

    # 所有重试都失败
    error_msg = f"重试 {max_attempts} 次后仍然失败: {last_exception}"
    raise RetryError(error_msg) from last_exception


def retry_on_network_error(
    max_attempts: Optional[int] = None,
    initial_delay: Optional[float] = None,
    backoff_factor: Optional[float] = None,
    max_delay: Optional[float] = None,
):
    """
    装饰器：网络错误时自动重试

    使用示例:
        @retry_on_network_error(max_attempts=3)
        def fetch_data():
            return requests.get(url)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            def _func():
                return func(*args, **kwargs)

            return exponential_backoff_retry(
                _func,
                max_attempts=max_attempts,
                initial_delay=initial_delay,
                backoff_factor=backoff_factor,
                max_delay=max_delay,
                exceptions=(
                    requests.exceptions.RequestException,
                    requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError,
                )
            )
        return wrapper
    return decorator


def robust_request(
    method: str,
    url: str,
    max_attempts: Optional[int] = None,
    timeout: Optional[int] = None,
    on_retry: Optional[Callable] = None,
    **kwargs
) -> requests.Response:
    """
    健壮的 HTTP 请求，自动重试

    Args:
        method: HTTP 方法 (GET/POST/PUT/DELETE)
        url: 请求 URL
        max_attempts: 最大尝试次数
        timeout: 超时时间
        on_retry: 重试回调
        **kwargs: 传递给 requests 的其他参数

    Returns:
        Response 对象

    Raises:
        RetryError: 重试耗尽后抛出
    """
    timeout = timeout or config.POST_REQUEST_TIMEOUT

    def _request():
        response = requests.request(
            method=method,
            url=url,
            timeout=timeout,
            **kwargs
        )
        # 检查 HTTP 状态码，429/5xx 错误应该重试
        if response.status_code == 429 or 500 <= response.status_code < 600:
            raise requests.exceptions.HTTPError(
                f"Server error: {response.status_code}"
            )
        return response

    return exponential_backoff_retry(
        _request,
        max_attempts=max_attempts,
        on_retry=on_retry,
        exceptions=(
            requests.exceptions.RequestException,
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
        )
    )


def safe_request(
    method: str,
    url: str,
    default_response: Optional[Any] = None,
    log_errors: bool = True,
    **kwargs
) -> Optional[requests.Response]:
    """
    安全的 HTTP 请求，失败时返回默认值而不抛异常

    Args:
        method: HTTP 方法
        url: 请求 URL
        default_response: 失败时返回的默认值
        log_errors: 是否记录错误日志
        **kwargs: 传递给 requests 的其他参数

    Returns:
        Response 对象或默认值
    """
    try:
        kwargs.setdefault("timeout", config.POST_REQUEST_TIMEOUT)
        return requests.request(method=method, url=url, **kwargs)
    except Exception as e:
        if log_errors:
            log_warn(f"请求失败: {url}, 错误: {e}")
        return default_response


class RequestStats:
    """请求统计器"""

    def __init__(self):
        self.total_requests = 0
        self.success_requests = 0
        self.failed_requests = 0
        self.retry_count = 0

    def record_success(self):
        self.total_requests += 1
        self.success_requests += 1

    def record_failure(self):
        self.total_requests += 1
        self.failed_requests += 1

    def record_retry(self):
        self.retry_count += 1

    def get_success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.success_requests / self.total_requests * 100

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total': self.total_requests,
            'success': self.success_requests,
            'failed': self.failed_requests,
            'retries': self.retry_count,
            'success_rate': self.get_success_rate()
        }
