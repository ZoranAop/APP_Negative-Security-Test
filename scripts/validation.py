#!/usr/bin/env python3
"""
数据验证模块
提供 CSV 数据和 API 请求/响应的验证功能
"""

from typing import Dict, Any, List, Optional, Tuple
import csv
import os

from config import config
from utils import log_error, log_warn


class ValidationError(Exception):
    """验证错误异常"""
    pass


def validate_csv_file(file_path: str, required_fields: List[str]) -> Tuple[bool, Optional[str]]:
    """
    验证 CSV 文件是否存在且包含必需字段

    Args:
        file_path: CSV 文件路径
        required_fields: 必需的字段列表

    Returns:
        (是否有效, 错误信息)
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        return False, f"文件不存在: {file_path}"

    # 检查文件是否可读
    if not os.access(file_path, os.R_OK):
        return False, f"文件无读取权限: {file_path}"

    # 检查文件是否为空
    if os.path.getsize(file_path) == 0:
        return False, f"文件为空: {file_path}"

    # 检查 CSV 字段
    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return False, f"CSV 文件没有表头: {file_path}"

            # 检查必需字段
            missing_fields = []
            for field in required_fields:
                if field not in reader.fieldnames:
                    missing_fields.append(field)

            if missing_fields:
                return False, f"CSV 文件缺少必需字段: {', '.join(missing_fields)}"

        return True, None

    except Exception as e:
        return False, f"读取 CSV 文件失败: {e}"


def validate_account_csv(file_path: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    验证账号 CSV 文件并返回字段映射

    Returns:
        (是否有效, 错误信息, 邮箱字段名, 密码字段名)
    """
    if not os.path.exists(file_path):
        return False, f"账号文件不存在: {file_path}", None, None

    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return False, "账号 CSV 文件没有表头", None, None

            # 查找邮箱字段
            email_field = None
            for field in config.ACCOUNTS_CSV_EMAIL_FIELDS:
                if field in reader.fieldnames:
                    email_field = field
                    break

            # 查找密码字段
            password_field = None
            for field in config.ACCOUNTS_CSV_PASSWORD_FIELDS:
                if field in reader.fieldnames:
                    password_field = field
                    break

            if not email_field:
                return False, f"未找到邮箱字段，期望字段: {', '.join(config.ACCOUNTS_CSV_EMAIL_FIELDS)}", None, None

            if not password_field:
                return False, f"未找到密码字段，期望字段: {', '.join(config.ACCOUNTS_CSV_PASSWORD_FIELDS)}", None, None

            return True, None, email_field, password_field

    except Exception as e:
        return False, f"读取账号 CSV 失败: {e}", None, None


def validate_moments_csv_row(row: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    """
    验证素材 CSV 的单行数据

    Returns:
        (是否有效, 错误信息)
    """
    # 检查必需字段
    content = row.get('content', '').strip()
    if not content:
        return False, "content 字段为空"

    # 验证 visibility 字段（如果存在）
    visibility_str = row.get('visibility', '').strip()
    if visibility_str:
        try:
            visibility = int(visibility_str)
            if visibility < 0:
                return False, f"visibility 值无效: {visibility}，应为非负整数"
        except ValueError:
            return False, f"visibility 值格式错误: {visibility_str}，应为整数"

    # 验证地理位置字段（如果存在）
    lat_str = row.get('location_lat', '').strip()
    lon_str = row.get('location_lon', '').strip()

    if lat_str:
        try:
            lat = float(lat_str)
            if not -90 <= lat <= 90:
                return False, f"latitude 值超出范围: {lat}，应在 [-90, 90] 之间"
        except ValueError:
            return False, f"latitude 格式错误: {lat_str}，应为浮点数"

    if lon_str:
        try:
            lon = float(lon_str)
            if not -180 <= lon <= 180:
                return False, f"longitude 值超出范围: {lon}，应在 [-180, 180] 之间"
        except ValueError:
            return False, f"longitude 格式错误: {lon_str}，应为浮点数"

    return True, None


def validate_post_payload(payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    验证发帖请求负载

    Returns:
        (是否有效, 错误信息)
    """
    # 检查必需字段
    if 'content' not in payload or not payload['content']:
        return False, "缺少 content 字段或内容为空"

    # 检查 media_info
    if 'media_info' in payload:
        media_info = payload['media_info']
        if not isinstance(media_info, dict):
            return False, "media_info 必须是字典类型"

        media_type = media_info.get('type')
        if media_type not in ('text', 'image', 'video'):
            return False, f"无效的 media_info.type: {media_type}"

        if media_type == 'image':
            images = media_info.get('images', [])
            if not isinstance(images, list):
                return False, "media_info.images 必须是列表类型"

            if len(images) > config.POST_MAX_IMAGES:
                return False, f"图片数量超过限制: {len(images)} > {config.POST_MAX_IMAGES}"

    # 检查 location
    if 'location' in payload:
        location = payload['location']
        if not isinstance(location, dict):
            return False, "location 必须是字典类型"

        required_location_fields = ['name', 'address', 'latitude', 'longitude']
        for field in required_location_fields:
            if field not in location:
                return False, f"location 缺少必需字段: {field}"

    return True, None


def validate_login_response(response_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    验证登录响应

    Returns:
        (是否成功, 错误信息, token)
    """
    if not isinstance(response_data, dict):
        return False, "响应数据格式错误", None

    code = response_data.get('code')
    if code != 0:
        msg = response_data.get('msg', '未知错误')
        return False, f"登录失败: {msg}", None

    data = response_data.get('data')
    if not data or not isinstance(data, dict):
        return False, "响应缺少 data 字段", None

    token = data.get('token')
    if not token:
        return False, "响应缺少 token 字段", None

    return True, None, token


def validate_post_response(response_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    验证发帖响应

    Returns:
        (是否成功, 错误信息, moment_id)
    """
    if not isinstance(response_data, dict):
        return False, "响应数据格式错误", None

    # 尝试多种格式提取 moment_id
    moment_id = response_data.get('moment_id')
    if not moment_id:
        data = response_data.get('data')
        if isinstance(data, dict):
            moment_id = data.get('moment_id')

    if not moment_id:
        # 检查是否有错误信息
        error_msg = response_data.get('msg') or response_data.get('message') or "未知错误"
        return False, error_msg, None

    return True, None, str(moment_id)


def sanitize_image_urls(image_urls_str: str, max_count: Optional[int] = None) -> List[str]:
    """
    清理和验证图片 URL 列表

    Args:
        image_urls_str: 逗号或分号分隔的 URL 字符串
        max_count: 最大图片数量

    Returns:
        清理后的 URL 列表
    """
    if not image_urls_str:
        return []

    max_count = max_count or config.POST_MAX_IMAGES

    # 支持逗号或分号分隔
    raw_urls = [url.strip() for url in image_urls_str.replace(";", ",").split(",") if url.strip()]

    # 去除 URL 参数（'!' 之后的部分）
    cleaned_urls = [url.split('!')[0] for url in raw_urls]

    # 去重并限制数量
    unique_urls = []
    seen = set()
    for url in cleaned_urls:
        if url not in seen:
            unique_urls.append(url)
            seen.add(url)
            if len(unique_urls) >= max_count:
                break

    return unique_urls


def validate_url(url: str) -> bool:
    """简单的 URL 验证"""
    return url.startswith(('http://', 'https://'))


def count_csv_rows(file_path: str) -> int:
    """统计 CSV 文件行数（不含表头）"""
    if not os.path.exists(file_path):
        return 0

    try:
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return sum(1 for _ in reader)
    except Exception:
        return 0
