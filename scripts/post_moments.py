#!/usr/bin/env python3
"""
自动发送帖子（朋友圈）脚本（重构版）
使用统一配置、重试机制和数据验证
"""

import os
import sys
import csv
import time
import argparse
import requests
import random
import concurrent.futures
from typing import Dict, Any, List, Tuple
import boto3

from config import config
from utils import (
    log_info, log_success, log_warn, log_error,
    ensure_dir, format_duration, format_percentage,
    print_section_header, print_section_separator, Colors
)
from retry import robust_request, RetryError
from validation import (
    validate_csv_file, validate_account_csv,
    validate_moments_csv_row, validate_post_payload,
    validate_login_response, validate_post_response,
    sanitize_image_urls
)


def parse_args():
    parser = argparse.ArgumentParser(description="自动发布朋友圈/帖子脚本")
    parser.add_argument(
        "--csv",
        type=str,
        default=config.POST_DEFAULT_CSV,
        help=f"CSV 数据文件路径 (默认: {config.POST_DEFAULT_CSV})"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=config.MOMENTS_API_URL,
        help=f"朋友圈发布接口 URL (默认: {config.MOMENTS_API_URL})"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=config.POST_DEFAULT_DELAY,
        help=f"每次发送帖子之间的间隔时间，仅在并发数为 1 时生效，单位为秒 (默认: {config.POST_DEFAULT_DELAY})"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=config.POST_DEFAULT_CONCURRENCY,
        help=f"并发发送线程数量。当并发数 > 1 时，忽略延时进行并发测试 (默认: {config.POST_DEFAULT_CONCURRENCY})"
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default="",
        help="测试结果输出的 CSV 文件路径 (默认: 自动生成包含参数和时间戳的文件名)"
    )
    parser.add_argument(
        "--accounts-csv",
        type=str,
        default=config.POST_DEFAULT_ACCOUNTS_CSV,
        help=f"账号 CSV 文件路径 (默认: {config.POST_DEFAULT_ACCOUNTS_CSV})"
    )
    parser.add_argument(
        "--num-accounts",
        type=int,
        default=0,
        help="随机选择进行登录的账号数量 (默认 0 表示使用文件中所有账号)"
    )
    parser.add_argument(
        "--num-posts",
        type=int,
        default=0,
        help="总共需要发送的帖子数量 (默认 0 表示发送全部帖子)"
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="配合 --num-posts 使用，表示选择最新的 N 条帖子进行发送（即 CSV 末尾的数据），而不是随机选择"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=config.POST_REQUEST_TIMEOUT,
        help=f"请求超时时间（秒） (默认: {config.POST_REQUEST_TIMEOUT})"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="开启调试模式，将打印每条记录的原始 image_urls 与解析后的列表"
    )

    return parser.parse_args()


def build_payload(row: Dict[str, str]) -> Dict[str, Any]:
    """根据 CSV 的行数据构造 PostMomentReq 负载"""
    content = row.get("content", "").strip()
    if not content:
        return {}

    payload = {
        "content": content
    }

    # 可见性解析
    visibility_str = row.get("visibility", "").strip()
    if visibility_str:
        try:
            payload["visibility"] = int(visibility_str)
        except ValueError:
            log_warn(f"无效的 visibility 值 '{visibility_str}'，将使用默认值")

    # 房间ID
    room_id = row.get("room_id", "").strip()
    if room_id:
        payload["room_id"] = room_id

    # 媒体信息 - 优先级：视频 > 图片 > 纯文本
    video_url_str = row.get("video_url", "").strip()
    thumbnail_url_str = row.get("thumbnail_url", "").strip()

    if video_url_str:
        # 视频类型
        payload["media_info"] = {
            "type": "video",
            "video_url": video_url_str,
            "thumbnail_url": thumbnail_url_str if thumbnail_url_str else ""
        }
    else:
        # 图片类型
        image_urls_str = row.get("image_urls", "").strip()
        if image_urls_str:
            cleaned_urls = sanitize_image_urls(image_urls_str, config.POST_MAX_IMAGES)
            if cleaned_urls:
                payload["media_info"] = {
                    "type": "image",
                    "images": cleaned_urls
                }
            else:
                payload["media_info"] = {
                    "type": "text"
                }
        else:
            # 纯文本类型
            payload["media_info"] = {
                "type": "text"
            }

    # 地理位置解析
    loc_name = row.get("location_name", "").strip()
    loc_address = row.get("location_address", "").strip()
    loc_lat_str = row.get("location_lat", "").strip()
    loc_lon_str = row.get("location_lon", "").strip()

    if loc_name or loc_address:
        location = {
            "name": loc_name or "未知地点",
            "address": loc_address or "未知地址",
            "latitude": 0.0,
            "longitude": 0.0
        }
        if loc_lat_str:
            try:
                location["latitude"] = float(loc_lat_str)
            except ValueError:
                pass
        if loc_lon_str:
            try:
                location["longitude"] = float(loc_lon_str)
            except ValueError:
                pass
        payload["location"] = location

    return payload


def get_aws_credentials(token: str, timeout: int = 15) -> Dict[str, Any]:
    """使用账号 token 获取 AWS 临时上传凭证"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}" if not token.lower().startswith("bearer ") else token
    }
    url = "https://devapi-x.tp-ex.com/file/upload/credentials"
    try:
        response = robust_request(
            method='POST',
            url=url,
            headers=headers,
            timeout=timeout,
            max_attempts=config.MAX_RETRY_ATTEMPTS
        )
        if response.status_code == 200:
            res_data = response.json()
            if res_data.get("code") == 0 and "data" in res_data:
                return res_data["data"]
            else:
                log_error(f"获取 AWS 凭证失败: {res_data.get('msg', '未知错误')}")
        else:
            log_error(f"获取 AWS 凭证 HTTP 错误: {response.status_code}")
    except Exception as e:
        log_error(f"获取 AWS 凭证异常: {e}")
    return {}


def upload_media_to_s3(file_path: str, credentials_data: Dict[str, Any]) -> str:
    """上传本地媒体文件（图片或视频）到 AWS S3，成功则返回公网 URL，失败返回空字符串"""
    if not os.path.exists(file_path):
        log_error(f"本地媒体文件不存在: {file_path}")
        return ""

    access_key = credentials_data.get("access_key_id")
    secret_key = credentials_data.get("secret_access_key")
    session_token = credentials_data.get("session_token")
    region = credentials_data.get("region", "ap-northeast-1")
    bucket = credentials_data.get("bucket")
    domain = credentials_data.get("domain")

    if not all([access_key, secret_key, session_token, bucket]):
        log_error("S3 临时凭证关键字段缺失")
        return ""

    try:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
            region_name=region
        )

        filename = os.path.basename(file_path)
        # 获取当前 YYYY/MM/DD 格式的日期路径 (根据最新要求带上天)
        date_path = time.strftime("%Y/%m/%d")
        # S3 key 使用 square/original/YYYY/MM/DD/{filename}
        s3_key = f"square/original/{date_path}/{filename}"

        # 根据文件扩展名判断 content_type
        filename_lower = filename.lower()
        if filename_lower.endswith((".mp4", ".mov", ".avi", ".mkv")):
            content_type = "video/mp4"
            media_type = "视频"
        elif filename_lower.endswith(".webp"):
            content_type = "image/webp"
            media_type = "图片"
        elif filename_lower.endswith(".png"):
            content_type = "image/png"
            media_type = "图片"
        elif filename_lower.endswith(".gif"):
            content_type = "image/gif"
            media_type = "图片"
        else:
            content_type = "image/jpeg"
            media_type = "图片"

        log_info(f"正在上传本地{media_type} {file_path} 到 S3 路径 {s3_key}...")
        s3_client.upload_file(
            file_path,
            bucket,
            s3_key,
            ExtraArgs={
                "ContentType": content_type,
                "CacheControl": "public, max-age=31536000, immutable"
            }
        )

        # 拼接返回公网 URL
        if domain:
            protocol = "https" if not domain.startswith("http") else ""
            if protocol:
                url = f"https://{domain}/{s3_key}"
            else:
                url = f"{domain}/{s3_key}"
        else:
            url = f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"

        log_success(f"{media_type}上传成功! AWS URL: {url}")
        return url

    except Exception as e:
        log_error(f"上传{media_type}到 S3 异常: {e}")
        return ""


def upload_image_to_s3(file_path: str, credentials_data: Dict[str, Any]) -> str:
    """向后兼容的函数名，直接调用 upload_media_to_s3"""
    return upload_media_to_s3(file_path, credentials_data)


def download_external_image(url: str, save_dir: str = "images", timeout: int = 15) -> str:
    """将外部网络图片下载并备份到本地，返回本地路径，失败返回空"""
    try:
        ensure_dir(save_dir)
        response = robust_request("GET", url, timeout=timeout, max_attempts=2)
        if response.status_code == 200:
            import hashlib
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            ext = ".jpg"
            if "webp" in url.lower():
                ext = ".webp"
            elif "png" in url.lower():
                ext = ".png"

            filename = f"downloaded_{url_hash}{ext}"
            filepath = os.path.join(save_dir, filename)

            with open(filepath, "wb") as f:
                f.write(response.content)

            log_success(f"外部图片下载成功: {url} -> {filepath}")
            return filepath
        else:
            log_error(f"下载外部图片失败 (HTTP {response.status_code}): {url}")
            return ""
    except Exception as e:
        log_error(f"下载外部图片异常: {e}, URL: {url}")
        return ""


def generate_video_thumbnail(video_path: str, save_dir: str = "images") -> str:
    """从视频中提取第一帧作为缩略图，返回本地路径"""
    import subprocess
    import hashlib

    try:
        ensure_dir(save_dir)

        # 生成唯一文件名
        video_hash = hashlib.md5(video_path.encode()).hexdigest()[:12]
        thumb_path = os.path.join(save_dir, f"thumb_{video_hash}.jpg")

        # 如果缩略图已存在，直接返回
        if os.path.exists(thumb_path):
            log_info(f"缩略图已存在: {thumb_path}")
            return thumb_path

        # 使用ffmpeg提取第一帧（保持宽高比：横视频 1280xH，竖视频 Wx1280，避免画面扁掉/变形）
        subprocess.run([
            'ffmpeg',
            '-i', video_path,
            '-ss', '00:00:01',  # 从1秒处截取（避免黑屏）
            '-vframes', '1',
            '-vf', "scale='if(gt(iw,ih),1280,-2)':'if(gt(iw,ih),-2,1280)'",
            '-q:v', '2',  # 高质量
            '-y',  # 覆盖已存在文件
            thumb_path
        ], check=True, stderr=subprocess.PIPE)

        log_success(f"从视频中提取缩略图成功: {thumb_path}")
        return thumb_path

    except subprocess.CalledProcessError as e:
        log_warn(f"ffmpeg提取失败: {e.stderr.decode()}")
        log_warn("将使用PIL生成黑色占位图作为备选...")
        # 降级方案：黑色占位图
        try:
            from PIL import Image
            thumb = Image.new('RGB', (1280, 720), color='black')
            thumb_path_png = thumb_path.replace('.jpg', '.png')
            thumb.save(thumb_path_png)
            return thumb_path_png
        except Exception as pil_e:
            log_error(f"生成占位图也失败: {pil_e}")
            return ""
    except FileNotFoundError:
        log_warn("未找到ffmpeg，使用PIL生成占位图...")
        try:
            from PIL import Image
            thumb = Image.new('RGB', (1280, 720), color='black')
            thumb_path_png = thumb_path.replace('.jpg', '.png')
            thumb.save(thumb_path_png)
            return thumb_path_png
        except Exception as pil_e:
            log_error(f"生成占位图失败: {pil_e}")
            return ""
    except Exception as e:
        log_error(f"生成视频缩略图异常: {e}")
        return ""
        ensure_dir(save_dir)
        # 去除 url 里的后缀及 query 参数
        clean_url = url.split('!')[0].split('?')[0]
        parts = clean_url.split('/')
        filename = parts[-1] if parts else ""
        if not filename:
            # 兜底生成一个 MD5 文件名
            import hashlib
            filename = hashlib.md5(url.encode('utf-8')).hexdigest() + ".jpg"
        
        # 确保文件名有后缀
        if "." not in filename:
            filename += ".jpg"
            
        filepath = os.path.join(save_dir, filename)
        
        # 如果文件已存在，直接返回
        if os.path.exists(filepath):
            return filepath
            
        log_info(f"正在下载外部图片: {url} ...")
        # 伪造 Headers 绕过防盗链限制
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.xiaohongshu.com/"
        }
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(r.content)
            log_success(f"外部图片下载成功，保存至: {filepath}")
            return filepath
        else:
            log_error(f"下载外部图片失败: HTTP {r.status_code}")
    except Exception as e:
        log_error(f"下载外部图片异常: {e}")
    return ""


def login_account(email: str, password: str, timeout: int) -> str:
    """自动登录获取 Token，登录成功返回 token，失败返回空字符串"""
    payload = {
        "email": email.strip(),
        "password": password.strip(),
        "device_id": config.POST_DEVICE_ID,
        "device_name": config.POST_DEVICE_NAME
    }
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = robust_request(
            method='POST',
            url=config.LOGIN_URL,
            json=payload,
            headers=headers,
            timeout=timeout,
            max_attempts=config.MAX_RETRY_ATTEMPTS
        )

        if response.status_code == 200:
            res_data = response.json()
            success, error_msg, token = validate_login_response(res_data)
            if success:
                return token
            else:
                log_warn(f"账号 {email} 登录返回错误: {error_msg}")
        else:
            log_warn(f"账号 {email} 登录失败, HTTP 状态码: {response.status_code}")

    except RetryError as e:
        log_warn(f"账号 {email} 登录重试失败: {e}")
    except Exception as e:
        log_warn(f"账号 {email} 登录网络异常: {e}")

    return ""


def send_post(item: Tuple[int, Dict[str, Any], str, str], api_url: str, timeout: int) -> Tuple[int, int, str, str, str, str]:
    """向 API 接口发送单条动态"""
    csv_line, payload, username, token = item

    # 验证负载
    valid, error_msg = validate_post_payload(payload)
    if not valid:
        return csv_line, -1, f"负载验证失败: {error_msg}", "", error_msg, username

    headers = {
        "Content-Type": "application/json"
    }
    if token:
        if not token.lower().startswith("bearer "):
            headers["Authorization"] = f"Bearer {token}"
        else:
            headers["Authorization"] = token

    try:
        response = robust_request(
            method='POST',
            url=api_url,
            json=payload,
            headers=headers,
            timeout=timeout,
            max_attempts=config.MAX_RETRY_ATTEMPTS
        )

        if response.status_code in (200, 201):
            resp_json = response.json()
            success, error_msg, moment_id = validate_post_response(resp_json)
            if success:
                return csv_line, 200, f"发送成功! 朋友圈ID: {moment_id}", moment_id, "", username
            else:
                return csv_line, response.status_code, f"发送失败: {error_msg}", "", error_msg, username
        else:
            err_msg = response.text
            return csv_line, response.status_code, f"发送失败! HTTP {response.status_code}, 错误详情: {err_msg}", "", err_msg, username

    except RetryError as e:
        return csv_line, -1, f"网络请求重试失败: {e}", "", str(e), username
    except requests.exceptions.RequestException as e:
        return csv_line, -1, f"网络发送异常: {e}", "", str(e), username


def load_accounts(accounts_csv: str, num_accounts: int) -> List[Tuple[str, str]]:
    """加载并可选随机采样账号"""
    # 验证账号文件
    valid, error_msg, email_field, password_field = validate_account_csv(accounts_csv)
    if not valid:
        log_error(error_msg)
        return []

    raw_accounts = []
    try:
        with open(accounts_csv, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                email = row.get(email_field, "").strip()
                password = row.get(password_field, "").strip()
                if email and password:
                    raw_accounts.append((email, password))
        log_info(f"从文件中读取到 {len(raw_accounts)} 个账号。")
    except Exception as e:
        log_error(f"读取账号 CSV 失败: {e}")
        return []

    # 随机筛选账号
    if num_accounts > 0 and len(raw_accounts) > 0:
        sample_size = min(num_accounts, len(raw_accounts))
        raw_accounts = random.sample(raw_accounts, sample_size)
        log_info(f"根据参数 --num-accounts，已随机选择 {sample_size} 个账号...")

    return raw_accounts


def login_accounts(accounts: List[Tuple[str, str]], timeout: int) -> List[Tuple[str, str]]:
    """批量登录账号"""
    active_accounts = []
    log_info("正在登录账号获取 Token...")

    for email, password in accounts:
        token_val = login_account(email, password, timeout)
        if token_val:
            active_accounts.append((email, token_val))
            log_success(f"账号 {email} 登录成功。")
        else:
            log_error(f"账号 {email} 登录失败，跳过该账号。")

    log_info(f"完成登录验证。成功登录账号数: {len(active_accounts)}/{len(accounts)}")
    return active_accounts


def load_posts(csv_path: str, num_posts: int, latest: bool = False) -> List[Tuple[int, Dict[str, Any]]]:
    """加载帖子数据"""
    # 验证素材文件
    valid, error_msg = validate_csv_file(csv_path, config.MOMENTS_CSV_REQUIRED_FIELDS)
    if not valid:
        log_error(error_msg)
        sys.exit(1)

    log_info(f"开始读取 CSV 文件: {csv_path}")
    posts_to_send = []

    try:
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for idx, row in enumerate(reader, 1):
                # 验证行数据
                valid, error_msg = validate_moments_csv_row(row)
                if not valid:
                    log_warn(f"第 {idx} 行数据验证失败: {error_msg}，已跳过")
                    continue

                payload = build_payload(row)
                if payload:
                    posts_to_send.append((idx, payload))
                else:
                    log_warn(f"第 {idx} 行内容为空，已跳过")
    except Exception as e:
        log_error(f"读取 CSV 文件失败: {e}")
        sys.exit(1)

    # 限制发送帖子数量（可选：最新或随机）
    if num_posts > 0 and len(posts_to_send) > 0:
        limit_size = min(num_posts, len(posts_to_send))
        if latest:
            posts_to_send = posts_to_send[-limit_size:]
            log_info(f"根据参数 --latest，已选择最新的 {limit_size} 条帖子（CSV末尾数据）进行发送。")
        else:
            posts_to_send = random.sample(posts_to_send, limit_size)
            log_info(f"根据参数 --num-posts，已随机选择 {limit_size} 条帖子进行发送。")

    return posts_to_send


def distribute_posts_round_robin(
    posts: List[Tuple[int, Dict[str, Any]]],
    accounts: List[Tuple[str, str]]
) -> List[Tuple[int, Dict[str, Any], str, str]]:
    """轮询（Round-Robin）分配帖子给已成功登录的账号"""
    num_accounts = len(accounts)
    distributed_posts = []

    for i, (idx, payload) in enumerate(posts):
        username, acc_token = accounts[i % num_accounts]
        distributed_posts.append((idx, payload, username, acc_token))

    return distributed_posts


def send_posts_sequential(
    distributed_posts: List[Tuple[int, Dict[str, Any], str, str]],
    api_url: str,
    delay: float,
    timeout: int
) -> Tuple[int, int, List, List]:
    """顺序发送帖子"""
    total_posts = len(distributed_posts)
    success_count = 0
    fail_count = 0
    failed_details = []
    test_results = []

    log_info(f"共分发 {total_posts} 条帖子，准备顺序发送（延迟: {delay} 秒）...")

    for current_idx, item in enumerate(distributed_posts, 1):
        csv_line, payload, username, acc_token = item
        content_preview = payload["content"][:20] + "..." if len(payload["content"]) > 20 else payload["content"]
        log_info(f"[{current_idx}/{total_posts}] 账号 [{username}] 正在发送第 {csv_line} 行帖子: '{content_preview}'")

        line, status_code, detail_msg, moment_id, err_detail, poster_account = send_post(item, api_url, timeout)

        # 搜集测试结果
        test_results.append({
            'csv_line': line,
            'content': payload["content"],
            'status': 'success' if status_code == 200 else 'fail',
            'status_code': status_code,
            'moment_id': moment_id,
            'error_detail': err_detail,
            'poster_account': poster_account,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        })

        if status_code == 200:
            log_success(detail_msg)
            success_count += 1
        else:
            log_error(detail_msg)
            fail_count += 1
            failed_details.append((csv_line, content_preview, detail_msg))

        if current_idx < total_posts and delay > 0:
            time.sleep(delay)

    return success_count, fail_count, failed_details, test_results


def send_posts_concurrent(
    distributed_posts: List[Tuple[int, Dict[str, Any], str, str]],
    api_url: str,
    concurrency: int,
    timeout: int
) -> Tuple[int, int, List, List]:
    """并发发送帖子"""
    total_posts = len(distributed_posts)
    success_count = 0
    fail_count = 0
    failed_details = []
    test_results = []

    log_info(f"共分发 {total_posts} 条帖子，准备以并发数 {concurrency} 进行多线程发送...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        # 提交全部发送请求任务
        futures = {
            executor.submit(send_post, item, api_url, timeout): item
            for item in distributed_posts
        }

        # 按执行完毕先后顺序回收并打印日志
        for current_idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
            item = futures[future]
            csv_line, payload, username, acc_token = item
            content_preview = payload["content"][:20] + "..." if len(payload["content"]) > 20 else payload["content"]

            try:
                line, status_code, detail_msg, moment_id, err_detail, poster_account = future.result()
                test_results.append({
                    'csv_line': line,
                    'content': payload["content"],
                    'status': 'success' if status_code == 200 else 'fail',
                    'status_code': status_code,
                    'moment_id': moment_id,
                    'error_detail': err_detail,
                    'poster_account': poster_account,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                })

                if status_code == 200:
                    log_success(f"[{current_idx}/{total_posts}] 账号 [{poster_account}] (第 {csv_line} 行) '{content_preview}': {detail_msg}")
                    success_count += 1
                else:
                    log_error(f"[{current_idx}/{total_posts}] 账号 [{poster_account}] (第 {csv_line} 行) '{content_preview}': {detail_msg}")
                    fail_count += 1
                    failed_details.append((csv_line, content_preview, detail_msg))
            except Exception as e:
                log_error(f"[{current_idx}/{total_posts}] 账号 [{username}] (第 {csv_line} 行) '{content_preview}': 线程执行捕获异常: {e}")
                fail_count += 1
                failed_details.append((csv_line, content_preview, f"线程捕获异常: {e}"))
                test_results.append({
                    'csv_line': csv_line,
                    'content': payload["content"],
                    'status': 'fail',
                    'status_code': -1,
                    'moment_id': '',
                    'error_detail': f"线程捕获异常: {e}",
                    'poster_account': username,
                    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                })

    return success_count, fail_count, failed_details, test_results


def save_results(
    test_results: List[Dict],
    output_path: str,
    args: argparse.Namespace,
    active_accounts: List[Tuple[str, str]],
    duration: float,
    success_count: int,
    fail_count: int
):
    """保存测试结果和汇总报告"""
    if not test_results:
        return

    total_posts = len(test_results)

    # 按 CSV 原始行号排序
    test_results.sort(key=lambda x: x['csv_line'])

    try:
        ensure_dir(os.path.dirname(output_path))

        # 添加运行参数到每行结果
        for result in test_results:
            result['concurrency'] = args.concurrency
            result['delay'] = args.delay
            result['api_url'] = args.api_url
            result['input_csv'] = args.csv

        # 保存 CSV 结果
        fieldnames = ['csv_line', 'content', 'status', 'status_code', 'moment_id', 'error_detail',
                     'concurrency', 'delay', 'api_url', 'input_csv', 'poster_account', 'timestamp']
        with open(output_path, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(test_results)
        log_success(f"测试结果已成功保存至: {os.path.abspath(output_path)}")

        # 保存汇总报告
        summary_path = os.path.splitext(output_path)[0] + "_summary.txt"
        success_rate = format_percentage(success_count, total_posts)
        active_usernames = [uname for uname, _ in active_accounts]

        summary_content = (
            "============================================================\n"
            "任务执行参数与结果汇总报告 (Execution Summary)\n"
            "============================================================\n"
            f"执行时间 (Timestamp): {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"任务总耗时 (Duration): {format_duration(duration)}\n\n"
            "--- 运行参数 (Run Parameters) ---\n"
            f"输入 CSV 素材库 (Input CSV): {args.csv}\n"
            f"账号 CSV 数据库 (Accounts CSV): {args.accounts_csv if args.accounts_csv else '未配置'}\n"
            f"随机选择的账号数量 (Num Accounts Arg): {args.num_accounts} (实际登录成功: {len(active_accounts)})\n"
            f"限制发送帖子数量 (Num Posts Arg): {args.num_posts} (实际分发发送: {total_posts})\n"
            f"输出 CSV 结果表 (Output CSV): {output_path}\n"
            f"接口地址 (API URL): {args.api_url}\n"
            f"并发线程数 (Concurrency): {args.concurrency}\n"
            f"延时时间 (Delay): {args.delay} 秒" + (f" (注意: 并发数 > 1 时延时参数已被忽略)" if args.concurrency > 1 else "") + "\n"
            f"请求超时时间 (Timeout): {args.timeout} 秒\n"
            f"登录成功的账号池 (Logged-in Accounts): {', '.join(active_usernames)}\n\n"
            "--- 执行统计 (Execution Metrics) ---\n"
            f"总计帖子数 (Total Posts): {total_posts} 条\n"
            f"成功发送数 (Success Count): {success_count} 条\n"
            f"发送失败数 (Failure Count): {fail_count} 条\n"
            f"发送成功率 (Success Rate): {success_rate}\n"
            "============================================================\n"
        )

        with open(summary_path, mode='w', encoding='utf-8') as sf:
            sf.write(summary_content)
        log_success(f"执行汇总与运行参数已成功保存至: {os.path.abspath(summary_path)}")

    except Exception as e:
        log_error(f"保存测试结果或汇总报告失败: {e}")


def print_final_report(
    args: argparse.Namespace,
    active_accounts: List[Tuple[str, str]],
    duration: float,
    total_posts: int,
    success_count: int,
    fail_count: int,
    failed_details: List
):
    """打印最终报告"""
    print_section_header("任务执行参数与结果汇总报告")
    print(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 总耗时: {format_duration(duration)}")
    print(f"输入素材: {args.csv} | 并发数: {args.concurrency} | 延时: {args.delay} 秒")

    active_usernames = [uname for uname, _ in active_accounts]
    print(f"使用账号: {', '.join(active_usernames[:5])}{' ... 等' if len(active_usernames) > 5 else ''} (共 {len(active_usernames)} 个)")
    print(f"接口地址: {args.api_url}")

    print_section_separator()
    print(f"总计帖子: {total_posts} 条")
    print(f"成功发送: {Colors.GREEN}{success_count}{Colors.ENDC} 条")
    print(f"发送失败: {Colors.FAIL if fail_count > 0 else Colors.GREEN}{fail_count}{Colors.ENDC} 条")

    success_rate_val = (success_count / total_posts * 100) if total_posts > 0 else 0.0
    print(f"发送成功率: {Colors.GREEN if success_rate_val == 100 else Colors.WARNING}{success_rate_val:.2f}%{Colors.ENDC}")

    if failed_details:
        print("\n" + "=" * 10 + f" {Colors.FAIL}发送失败详细信息列表 ({len(failed_details)} 条){Colors.ENDC} " + "=" * 10)
        for line, preview, err in failed_details:
            print(f"第 {line} 行 | 预览: '{preview}' | 原因: {err}")

    print("=" * 60)


def main():
    start_time = time.time()
    args = parse_args()

    print_section_header("多账号发帖任务启动")

    # 1. 加载账号并登录
    # 加载并登录账号
    if not args.accounts_csv:
        log_error(f"必须指定账号 CSV 文件路径 (--accounts-csv)")
        sys.exit(1)

    if not os.path.exists(args.accounts_csv):
        log_error(f"账号 CSV 文件不存在: {args.accounts_csv}")
        sys.exit(1)

    log_info(f"检测到账号文件: {args.accounts_csv}，开始加载账号...")
    accounts = load_accounts(args.accounts_csv, args.num_accounts)

    if not accounts:
        log_error("未能从账号 CSV 中加载任何账号！")
        sys.exit(1)

    active_accounts = login_accounts(accounts, args.timeout)

    if not active_accounts:
        log_error("所有账号登录失败，无法开始任务！")
        sys.exit(1)

    # 2. 加载帖子数据
    posts_to_send = load_posts(args.csv, args.num_posts, args.latest)
    total_posts = len(posts_to_send)

    if total_posts == 0:
        log_error("没有有效的帖子数据可发送！")
        sys.exit(1)

    # === 本地媒体文件（图片/视频）与外部小红书图片 AWS S3 预上传逻辑 ===
    first_email, first_token = active_accounts[0]
    s3_creds = get_aws_credentials(first_token, args.timeout)
    if not s3_creds:
        log_error("无法获取 AWS S3 上传凭证，预上传失败！终止任务。")
        sys.exit(1)

    aws_domain = s3_creds.get("domain", "teststatic-x.tp-ex.com")

    # 扫描并分类媒体文件
    local_images = set()
    local_videos = set()
    local_thumbnails = set()
    external_images = set()

    for idx, payload in posts_to_send:
        media_info = payload.get("media_info", {})
        if media_info.get("type") == "image":
            for img in media_info.get("images", []):
                if not img:
                    continue
                if img.startswith(("http://", "https://")):
                    if aws_domain not in img:
                        external_images.add(img)
                else:
                    local_images.add(img)
        elif media_info.get("type") == "video":
            # 处理视频URL
            video_url = media_info.get("video_url", "")
            if video_url and not video_url.startswith(("http://", "https://")):
                local_videos.add(video_url)
            # 处理缩略图URL
            thumb_url = media_info.get("thumbnail_url", "")
            if thumb_url:
                if not thumb_url.startswith(("http://", "https://")):
                    local_thumbnails.add(thumb_url)
            else:
                # 如果没有缩略图，自动从视频生成
                if video_url and not video_url.startswith(("http://", "https://")):
                    log_info(f"检测到视频 {video_url} 没有缩略图，正在自动生成...")
                    thumb_path = generate_video_thumbnail(video_url)
                    if thumb_path:
                        # 更新payload中的thumbnail_url
                        payload["media_info"]["thumbnail_url"] = thumb_path
                        local_thumbnails.add(thumb_path)
                        log_success(f"已为视频生成缩略图: {thumb_path}")
                    else:
                        log_warn(f"为视频 {video_url} 生成缩略图失败，将使用空缩略图")

    # 自动下载外部图片到本地备份
    download_mapping = {}
    if external_images:
        log_info(f"检测到共有 {len(external_images)} 张外部网络图片需要下载并托管到 AWS S3...")
        for ext_url in sorted(list(external_images)):
            local_path = download_external_image(ext_url, "images", args.timeout)
            if local_path:
                download_mapping[ext_url] = local_path
                local_images.add(local_path)
            else:
                log_error(f"外部图片下载失败: {ext_url}，终止任务防止发帖破损。")
                sys.exit(1)

    # 统一上传所有本地媒体文件至 S3（图片+视频+缩略图）
    upload_mapping = {}
    all_local_media = local_images | local_videos | local_thumbnails

    if all_local_media:
        log_info(f"检测到共有 {len(all_local_media)} 个本地媒体文件需要上传至 AWS S3...")
        log_info(f"  - 图片: {len(local_images)} 张")
        log_info(f"  - 视频: {len(local_videos)} 个")
        log_info(f"  - 缩略图: {len(local_thumbnails)} 张")

        failed_uploads = []
        for media_path in sorted(list(all_local_media)):
            aws_url = upload_media_to_s3(media_path, s3_creds)
            if aws_url:
                upload_mapping[media_path] = aws_url
            else:
                log_error(f"媒体文件 {media_path} 上传 S3 失败！")
                failed_uploads.append(media_path)

        if failed_uploads:
            log_error(f"共有 {len(failed_uploads)} 个媒体文件上传 S3 失败，终止任务。")
            sys.exit(1)

        # 在内存中替换 payload 中的所有本地路径及外部 URL 为 AWS 链接
        for idx, payload in posts_to_send:
            media_info = payload.get("media_info", {})
            if media_info.get("type") == "image":
                updated_images = []
                for img in media_info.get("images", []):
                    if img in download_mapping:
                        local_path = download_mapping[img]
                        updated_images.append(upload_mapping.get(local_path, img))
                    elif img in upload_mapping:
                        updated_images.append(upload_mapping[img])
                    else:
                        updated_images.append(img)
                payload["media_info"]["images"] = updated_images
            elif media_info.get("type") == "video":
                # 替换视频URL
                video_url = media_info.get("video_url", "")
                if video_url in upload_mapping:
                    payload["media_info"]["video_url"] = upload_mapping[video_url]
                # 替换缩略图URL
                thumb_url = media_info.get("thumbnail_url", "")
                if thumb_url in upload_mapping:
                    payload["media_info"]["thumbnail_url"] = upload_mapping[thumb_url]

        log_success("所有本地媒体文件及外部网络图片均已成功托管至 AWS S3 并替换为 AWS URL！")

    # 3. 分配帖子
    distributed_posts = distribute_posts_round_robin(posts_to_send, active_accounts)

    # 4. 发送帖子
    concurrency = max(1, args.concurrency)

    if concurrency == 1:
        success_count, fail_count, failed_details, test_results = send_posts_sequential(
            distributed_posts, args.api_url, args.delay, args.timeout
        )
    else:
        success_count, fail_count, failed_details, test_results = send_posts_concurrent(
            distributed_posts, args.api_url, concurrency, args.timeout
        )

    duration = time.time() - start_time

    # 5. 保存结果
    output_path = args.output_csv
    if not output_path:
        timestamp_str = time.strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(
            config.RESULT_DIR,
            f"post_results_{timestamp_str}_c{concurrency}_d{args.delay:.1f}.csv"
        )

    save_results(
        test_results, output_path, args, active_accounts,
        duration, success_count, fail_count
    )

    # 6. 打印最终报告
    print_final_report(
        args, active_accounts, duration, total_posts,
        success_count, fail_count, failed_details
    )


if __name__ == "__main__":
    main()
