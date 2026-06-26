#!/usr/bin/env python3
"""
小红书热门帖子爬取与 CSV 实时去重丰富脚本（重构版）
使用统一配置、重试机制和数据验证
支持多线程并发下载，大幅提升效率
"""

import os
import csv
import json
import time
import re
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Any, Optional
from urllib.parse import urlparse
from pathlib import Path

from config import config
from utils import (
    log_info, log_success, log_warn, log_error,
    ensure_dir, format_duration, print_section_header, print_section_separator
)
from retry import robust_request, RetryError


def parse_args():
    parser = argparse.ArgumentParser(description="小红书热门帖子批量爬取与去重脚本")
    parser.add_argument(
        "--target",
        type=int,
        default=config.CRAWL_DEFAULT_TARGET,
        help=f"目标新增不重复帖子的数量 (默认: {config.CRAWL_DEFAULT_TARGET})"
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=config.CRAWL_DEFAULT_MAX_REQUESTS,
        help=f"最大允许的 HTTP 请求次数，防止死循环 (默认: {config.CRAWL_DEFAULT_MAX_REQUESTS})"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=config.CRAWL_DEFAULT_DELAY,
        help=f"每次请求之间的冷却延迟秒数，防频控 (默认: {config.CRAWL_DEFAULT_DELAY})"
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=config.CRAWL_DEFAULT_CSV,
        help=f"目标 CSV 文件路径 (默认: {config.CRAWL_DEFAULT_CSV})"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=config.CRAWL_REQUEST_TIMEOUT,
        help=f"请求超时时间（秒） (默认: {config.CRAWL_REQUEST_TIMEOUT})"
    )
    parser.add_argument(
        "--images-dir",
        type=str,
        default="images",
        help="图片保存目录 (默认: images)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="并发下载线程数 (默认: 3，建议2-5之间)"
    )
    return parser.parse_args()


def download_image(url: str, save_dir: str, note_id: str, index: int, timeout: int) -> str:
    """下载图片到本地，返回本地路径"""
    try:
        # 确保目录存在
        ensure_dir(save_dir)

        # 提取文件扩展名
        parsed = urlparse(url)
        ext = '.jpg'  # 默认jpg
        if 'webp' in url.lower():
            ext = '.webp'
        elif 'png' in url.lower():
            ext = '.png'

        # 生成文件名: note_id_图片序号.ext
        filename = f"{note_id}_{index}{ext}"
        filepath = os.path.join(save_dir, filename)

        # 如果文件已存在，跳过下载
        if os.path.exists(filepath):
            return filepath

        # 下载图片
        response = robust_request(
            method='GET',
            url=url,
            headers=config.XHS_HEADERS,
            timeout=timeout,
            max_attempts=2
        )

        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(response.content)
            return filepath
        else:
            log_warn(f"下载图片失败: HTTP {response.status_code}")
            return ""

    except Exception as e:
        log_warn(f"下载图片异常: {e}")
        return ""


def download_video(url: str, save_dir: str, note_id: str, timeout: int) -> str:
    """下载视频到本地，返回本地路径"""
    try:
        # 确保目录存在
        ensure_dir(save_dir)

        # 生成文件名: note_id.mp4
        filename = f"{note_id}.mp4"
        filepath = os.path.join(save_dir, filename)

        # 如果文件已存在，跳过下载
        if os.path.exists(filepath):
            log_info(f"视频已存在，跳过下载: {filepath}")
            return filepath

        # 下载视频
        log_info(f"正在下载视频: {note_id}...")
        response = robust_request(
            method='GET',
            url=url,
            headers=config.XHS_HEADERS,
            timeout=timeout * 3,  # 视频文件较大，增加超时时间
            max_attempts=2
        )

        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(response.content)
            log_success(f"视频下载成功: {filepath} ({len(response.content) / 1024 / 1024:.2f} MB)")
            return filepath
        else:
            log_warn(f"下载视频失败: HTTP {response.status_code}")
            return ""

    except Exception as e:
        log_warn(f"下载视频异常: {e}")
        return ""


def generate_video_thumbnail(video_path: str, note_id: str, images_dir: str) -> str:
    """从视频中提取缩略图，返回本地路径"""
    import subprocess

    try:
        ensure_dir(images_dir)

        # 生成缩略图文件名
        thumb_filename = f"{note_id}_thumb.jpg"
        thumb_path = os.path.join(images_dir, thumb_filename)

        # 如果缩略图已存在，直接返回
        if os.path.exists(thumb_path):
            return thumb_path

        # 使用ffmpeg提取第一帧（保持宽高比：横视频 1280xH，竖视频 Wx1280，避免画面扁掉/变形）
        subprocess.run([
            'ffmpeg',
            '-i', video_path,
            '-ss', '00:00:01',
            '-vframes', '1',
            '-vf', "scale='if(gt(iw,ih),1280,-2)':'if(gt(iw,ih),-2,1280)'",
            '-q:v', '2',
            '-y',
            thumb_path
        ], check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

        log_success(f"从视频提取缩略图: {thumb_path}")
        return thumb_path

    except subprocess.CalledProcessError as e:
        log_warn(f"ffmpeg提取缩略图失败，尝试下载封面图...")
        return ""
    except FileNotFoundError:
        log_warn(f"未找到ffmpeg，尝试下载封面图...")
        return ""
    except Exception as e:
        log_warn(f"生成缩略图异常: {e}")
        return ""


def fetch_note_detail(note_id: str, xsec_token: str, timeout: int, images_dir: str) -> Tuple[str, str, str, str, bool]:
    """
    根据 note_id 爬取笔记详情，获取完整正文(Title+Desc)及下载全部图片/视频
    返回: (content, image_paths, video_url, thumbnail_url, success)
    """
    url = config.XHS_NOTE_URL_TEMPLATE.format(note_id=note_id)
    if xsec_token:
        url += f"?xsec_token={xsec_token}&xsec_source=pc_feed"

    try:
        response = robust_request(
            method='GET',
            url=url,
            headers=config.XHS_HEADERS,
            timeout=timeout,
            max_attempts=2  # 详情页失败影响不大，只重试1次
        )

        if response.status_code != 200:
            log_warn(f"详情页HTTP状态码异常: {response.status_code} (可能是反爬限制)")
            return "", "", "", "", False

        # 提取 window.__INITIAL_STATE__
        start_str = 'window.__INITIAL_STATE__='
        start_idx = response.text.find(start_str)
        if start_idx == -1:
            log_warn(f"页面中找不到数据结构 (可能页面改版或帖子已删除)")
            return "", "", "", "", False

        json_start = start_idx + len(start_str)
        brace_count = 0
        json_end = json_start
        for i in range(json_start, len(response.text)):
            char = response.text[i]
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break

        json_data = response.text[json_start:json_end]
        json_data_clean = json_data.replace(':undefined', ':null').replace(': undefined', ': null')
        state = json.loads(json_data_clean)

        note_detail = state.get('note', {}).get('noteDetailMap', {}).get(note_id, {}).get('note', {})
        if not note_detail:
            log_warn(f"找不到笔记详情数据结构 (可能是私密帖子或数据异常)")
            return "", "", "", "", False

        # 提取标题和描述正文
        title = note_detail.get('title', '').strip()
        desc = note_detail.get('desc', '').strip()

        # 拼接 Title & Desc
        content = title
        if desc:
            if content:
                content += "\n" + desc
            else:
                content = desc

        # 转换小红书话题标签格式：#话题[话题]# → #话题
        content = re.sub(r'#([^#\[]+)\[话题\]#', r'#\1', content)

        # 删除小红书表情：[xxxR]
        content = re.sub(r'\[[^\]]+R\]', '', content)

        # 删除@提及：@用户名（用户名为中文/英文/数字/下划线组合）
        content = re.sub(r'@[\w一-龥]+', '', content)

        # 清理多余空格和换行
        content = re.sub(r' +', ' ', content)  # 多个空格变一个
        content = re.sub(r'\n+', '\n', content)  # 多个换行变一个
        content = content.strip()

        # 判断帖子类型
        note_type = note_detail.get('type', '').lower()

        video_url = ""
        thumbnail_url = ""
        image_paths_str = ""

        if note_type == 'video':
            # 视频笔记：下载视频和生成缩略图
            video = note_detail.get('video', {})
            if video:
                # 提取视频播放地址（取第一个可用的）
                media = video.get('media', {})
                stream = media.get('stream', {})
                video_remote_url = ""
                thumbnail_remote_url = ""

                if stream:
                    # 尝试h264流
                    h264_list = stream.get('h264', [])
                    if h264_list and len(h264_list) > 0:
                        video_remote_url = h264_list[0].get('masterUrl', '') or h264_list[0].get('backupUrl', '')

                # 提取封面
                cover = video.get('image', {})
                if cover:
                    thumbnail_remote_url = cover.get('urlDefault', '') or cover.get('url', '')

                # 下载视频到本地 media/ 目录
                if video_remote_url:
                    media_dir = "media"
                    local_video_path = download_video(video_remote_url, media_dir, note_id, timeout)
                    if local_video_path:
                        video_url = local_video_path

                        # 从本地视频生成缩略图
                        local_thumb_path = generate_video_thumbnail(local_video_path, note_id, images_dir)
                        if local_thumb_path:
                            thumbnail_url = local_thumb_path
                        elif thumbnail_remote_url:
                            # ffmpeg失败，则下载封面图作为缩略图
                            log_info(f"尝试下载封面图作为缩略图...")
                            local_thumb_path = download_image(thumbnail_remote_url, images_dir, note_id, 999, timeout)
                            if local_thumb_path:
                                thumbnail_url = local_thumb_path
                    else:
                        log_warn(f"视频下载失败，跳过该视频帖子")
                        return "", "", "", "", False

            log_info(f"📹 检测到视频帖子: {note_id} (已下载到本地)")
        else:
            # 图文笔记：提取全部图片URL
            images = note_detail.get('imageList', [])
            img_urls = []
            for img in images:
                url_str = img.get('urlDefault') or img.get('urlPre') or img.get('url', '')
                if url_str:
                    img_urls.append(url_str.strip())

            # 下载图片到本地
            local_paths = []
            for idx, img_url in enumerate(img_urls):
                local_path = download_image(img_url, images_dir, note_id, idx, timeout)
                if local_path:
                    local_paths.append(local_path)

            image_paths_str = ",".join(local_paths)

        return content, image_paths_str, video_url, thumbnail_url, True

    except RetryError as e:
        log_warn(f"爬取笔记详情 {note_id} 重试失败: {e}")
        return "", "", "", "", False
    except Exception as e:
        log_warn(f"爬取笔记详情 {note_id} 异常: {e}")
        return "", "", "", "", False


def fetch_xhs_explore_feeds(timeout: int) -> List[Dict[str, Any]]:
    """爬取小红书 explore 探索发现页的推荐笔记基本数据"""
    try:
        response = robust_request(
            method='GET',
            url=config.XHS_EXPLORE_URL,
            headers=config.XHS_HEADERS,
            timeout=timeout,
            max_attempts=config.MAX_RETRY_ATTEMPTS
        )

        if response.status_code != 200:
            raise Exception(f"请求小红书 Explore 页面失败，HTTP 状态码: {response.status_code}")

        # 提取 window.__INITIAL_STATE__
        start_str = 'window.__INITIAL_STATE__='
        start_idx = response.text.find(start_str)
        if start_idx == -1:
            raise Exception("未在页面中找到 window.__INITIAL_STATE__ 的数据")

        json_start = start_idx + len(start_str)
        brace_count = 0
        json_end = json_start
        for i in range(json_start, len(response.text)):
            char = response.text[i]
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break

        json_data = response.text[json_start:json_end]
        json_data_clean = json_data.replace(':undefined', ':null').replace(': undefined', ': null')

        try:
            state = json.loads(json_data_clean)
        except Exception as e:
            raise Exception(f"JSON 解析失败: {e}")

        feeds = state.get('feed', {}).get('feeds', [])

        notes_brief = []
        for feed in feeds:
            note_id = feed.get('id')
            xsec_token = feed.get('xsecToken')
            note_card = feed.get('noteCard', {})

            # 现在支持视频和图文两种类型
            note_type = note_card.get('type', '').lower()

            title = note_card.get('displayTitle', '').strip()
            if not note_id:
                continue

            # 提取封面大图 URL 作为 fallback
            image_url = ""
            cover = note_card.get('cover', {})
            if cover:
                image_url = cover.get('urlDefault') or cover.get('urlPre') or ""
                if not image_url and cover.get('infoList'):
                    for img in cover.get('infoList'):
                        if img.get('imageScene') == 'WB_DFT':
                            image_url = img.get('url')
                            break
                    if not image_url:
                        image_url = cover.get('infoList')[0].get('url', '')

            notes_brief.append({
                'id': note_id,
                'xsec_token': xsec_token,
                'fallback_title': title,
                'fallback_image': image_url,
                'note_type': note_type
            })

        return notes_brief

    except RetryError as e:
        raise Exception(f"抓取列表重试失败: {e}")


def load_existing_data(csv_path: str) -> Tuple[set, set]:
    """读取已有的 CSV，获取已有帖子内容和note_id的集合进行去重"""
    existing_contents = set()
    existing_note_ids = set()
    if os.path.exists(csv_path):
        try:
            with open(csv_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    content = row.get('content', '').strip()
                    if content:
                        existing_contents.add(content)
                    # 从image_urls字段提取note_id（格式: images/note_id_0.jpg）
                    image_urls = row.get('image_urls', '').strip()
                    if image_urls:
                        for img_path in image_urls.split(','):
                            # 提取 note_id（文件名格式: note_id_0.jpg）
                            filename = os.path.basename(img_path.strip())
                            if '_' in filename:
                                note_id = filename.rsplit('_', 1)[0]
                                existing_note_ids.add(note_id)
            log_info(f"读取到现有素材库中已有 {len(existing_contents)} 条帖子（{len(existing_note_ids)} 个不重复note_id）")
        except Exception as e:
            log_warn(f"读取现有 CSV 文件失败: {e}，将直接创建新文件")
    return existing_contents, existing_note_ids


# 线程安全的CSV写入锁
csv_lock = threading.Lock()


def append_notes_to_csv(csv_path: str, new_notes: List[Dict[str, str]]) -> int:
    """线程安全的追加写入新的笔记到 CSV 文件"""
    fieldnames = ['content', 'visibility', 'room_id', 'image_urls', 'video_url', 'thumbnail_url', 'location_name', 'location_address', 'location_lat', 'location_lon']

    added_count = 0
    with csv_lock:  # 线程安全锁
        try:
            file_exists = os.path.exists(csv_path)
            # 确保目录存在
            csv_dir = os.path.dirname(csv_path)
            if csv_dir:
                ensure_dir(csv_dir)

            with open(csv_path, mode='a', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                # 如果文件为空或者不存在，写入表头
                if not file_exists or os.path.getsize(csv_path) == 0:
                    writer.writeheader()

                for note in new_notes:
                    writer.writerow({
                        'content': note['content'],
                        'visibility': 0,
                        'room_id': '',
                        'image_urls': note.get('image_url', ''),
                        'video_url': note.get('video_url', ''),
                        'thumbnail_url': note.get('thumbnail_url', ''),
                        'location_name': '',
                        'location_address': '',
                        'location_lat': '',
                        'location_lon': ''
                    })
                    added_count += 1
        except Exception as e:
            log_error(f"写入 CSV 文件失败: {e}")

    return added_count


def process_single_note(brief: Dict, existing_contents: set, timeout: int, images_dir: str,
                       delay: float, csv_path: str) -> Optional[Dict[str, Any]]:
    """处理单个笔记的下载任务（用于多线程）"""
    note_id = brief['id']
    xsec_token = brief['xsec_token']

    # 获取详情前的延迟，避免请求频率过快
    time.sleep(delay)
    log_info(f"[线程-{threading.current_thread().name}] 正在获取笔记详情: {note_id}...")
    content, image_paths, video_url, thumbnail_url, success = fetch_note_detail(note_id, xsec_token, timeout, images_dir)

    # 详情页请求失败，直接跳过（不使用兜底，避免不完整数据）
    if not success:
        log_warn(f"⏭️  跳过笔记 {note_id}：详情页获取失败，数据不完整")
        return None

    # 没有内容也跳过
    if not content:
        log_warn(f"⏭️  跳过笔记 {note_id}：没有正文内容")
        return None

    # 内容级别的去重检查
    if content in existing_contents:
        log_info(f"跳过内容重复帖子: {note_id}")
        return None

    note_item = {
        'content': content,
        'image_url': image_paths,
        'video_url': video_url,
        'thumbnail_url': thumbnail_url,
        'note_id': note_id
    }

    # 实时写入CSV（线程安全）
    append_notes_to_csv(csv_path, [note_item])

    # 生成日志信息
    if video_url:
        log_success(f"✅ 新增视频素材: '{content[:15]}...' (视频URL已保存)")
    else:
        img_count = len(image_paths.split(',')) if image_paths else 0
        log_success(f"✅ 新增素材: '{content[:15]}...' (已下载图片: {img_count} 张)")

    return note_item


def main():
    start_time = time.time()
    args = parse_args()
    csv_path = args.csv
    target = args.target
    max_requests = args.max_requests
    delay = args.delay
    timeout = args.timeout
    images_dir = args.images_dir
    workers = args.workers

    print_section_header("小红书素材抓取任务启动")

    # 1. 加载现有素材
    existing_contents, existing_note_ids = load_existing_data(csv_path)

    # 记录初始数量，用于最终统计
    initial_count = len(existing_contents)

    # 用于记录本次会话中已处理的note_id，避免重复请求
    processed_note_ids = set()

    collected_notes = []
    added_in_session = 0
    requests_count = 0
    skipped_duplicate_count = 0  # 统计跳过的重复帖子数量

    log_info(f"开始批量获取小红书推荐帖子。目标新增不重复数量: {target} 条...")
    log_info(f"图片将下载到: {os.path.abspath(images_dir)}")
    log_info(f"🚀 使用 {workers} 个并发线程加速下载")

    # 2. 循环爬取
    while added_in_session < target and requests_count < max_requests:
        requests_count += 1
        log_info(f"[{requests_count}/{max_requests}] 正在发起小红书列表抓取请求...")

        try:
            notes_brief = fetch_xhs_explore_feeds(timeout)
            if not notes_brief:
                log_warn("本次列表请求未抓取到有效帖子，重试中...")
                time.sleep(2)
                continue

            # ⚡ 优化：提前过滤重复的note_id
            unique_briefs = []
            for brief in notes_brief:
                note_id = brief['id']
                if note_id in existing_note_ids or note_id in processed_note_ids:
                    skipped_duplicate_count += 1
                    log_info(f"⏭️  跳过重复帖子: {note_id}")
                    continue
                processed_note_ids.add(note_id)
                unique_briefs.append(brief)

            if not unique_briefs:
                log_warn("本批次全部为重复帖子，继续下一轮...")
                time.sleep(delay)
                continue

            log_info(f"📦 本批次待处理 {len(unique_briefs)} 条新帖子，开始多线程下载...")

            # 使用线程池并发处理
            newly_found_count = 0
            with ThreadPoolExecutor(max_workers=workers) as executor:
                # 提交所有任务
                future_to_brief = {
                    executor.submit(
                        process_single_note,
                        brief,
                        existing_contents,
                        timeout,
                        images_dir,
                        delay,
                        csv_path
                    ): brief for brief in unique_briefs
                }

                # 收集结果
                for future in as_completed(future_to_brief):
                    if added_in_session >= target:
                        break

                    try:
                        note_item = future.result()
                        if note_item:
                            collected_notes.append(note_item)
                            existing_contents.add(note_item['content'])  # 添加到已有内容集合
                            newly_found_count += 1
                            added_in_session += 1
                    except Exception as e:
                        log_error(f"处理笔记时出错: {e}")

            log_success(f"第 {requests_count} 次列表抓取批处理完成：成功新增入库 {newly_found_count} 条，累计已获取 {added_in_session}/{target} 条")

            # 冷却延迟，防风控
            if added_in_session < target:
                time.sleep(delay)

        except Exception as e:
            log_error(f"抓取过程中出错: {e}")
            time.sleep(2)

    # 3. 写入文件
    if collected_notes:
        log_success(f"已在此次会话中实时同步并保存了 {len(collected_notes)} 条全新帖子至素材库！")
    else:
        log_warn("本次执行没有新增任何独特帖子。")

    duration = time.time() - start_time
    total_after = initial_count + len(collected_notes)

    # 4. 生成汇总报告
    summary_path = os.path.join(config.RESULT_DIR, "crawl_summary.txt")
    try:
        ensure_dir(config.RESULT_DIR)

        summary_content = (
            "============================================================\n"
            "爬取与去重任务参数及结果报告 (Crawl Summary)\n"
            "============================================================\n"
            f"执行时间 (Timestamp): {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"任务总耗时 (Duration): {format_duration(duration)}\n\n"
            "--- 运行参数 (Run Parameters) ---\n"
            f"目标新增不重复数量 (Target New Notes): {target}\n"
            f"最大请求限制 (Max Requests): {max_requests}\n"
            f"请求冷却延时 (Delay): {delay} 秒\n"
            f"请求超时时间 (Timeout): {timeout} 秒\n"
            f"素材库 CSV 路径 (Output CSV): {os.path.abspath(csv_path)}\n\n"
            "--- 执行统计 (Execution Metrics) ---\n"
            f"发起抓取请求次数 (HTTP Requests): {requests_count} 次\n"
            f"本地已有帖子数量 (Existing Before): {initial_count} 条\n"
            f"本次跳过重复帖子 (Skipped Duplicates): {skipped_duplicate_count} 条\n"
            f"本次成功去重新增入库 (Newly Added): {len(collected_notes)} 条\n"
            f"当前素材库总帖子数 (Total After): {total_after} 条\n"
            "============================================================\n"
        )
        with open(summary_path, mode='w', encoding='utf-8') as sf:
            sf.write(summary_content)
        log_success(f"爬取汇总与运行参数已成功保存至: {os.path.abspath(summary_path)}")
    except Exception as e:
        log_error(f"保存爬取汇总报告失败: {e}")

    # 5. 打印最终报告
    print_section_header("数据同步与去重报告")
    print(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 总耗时: {format_duration(duration)}")
    print(f"目标新增: {target} | 最大请求: {max_requests} | 冷却延时: {delay} 秒")
    print_section_separator()
    print(f"执行爬取请求次数: {requests_count} 次")
    print(f"本地已有帖子数量: {initial_count} 条")
    print(f"本次跳过重复帖子: {skipped_duplicate_count} 条 (节省了大量时间!)")
    print(f"成功去重新增入库: {len(collected_notes)} 条")
    print(f"当前素材库总帖子数: {total_after} 条")
    print(f"素材库文件路径: {os.path.abspath(csv_path)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
