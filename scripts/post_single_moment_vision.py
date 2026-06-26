#!/usr/bin/env python3
"""
自动分析图片/视频并生成文案，单贴发帖脚本（智能识图/视版）
"""

import os
import sys
import argparse
import base64
import requests
import subprocess
import tempfile
import time
import hashlib
from typing import Dict, Any, List, Tuple

from config import config
from utils import (
    log_info, log_success, log_warn, log_error,
    ensure_dir, print_section_header, print_section_separator, Colors
)
# 复用批量发帖中的核心登录、凭证获取、S3 上传、发帖以及账号加载函数
from post_moments import (
    login_account,
    get_aws_credentials,
    upload_image_to_s3,
    send_post,
    load_accounts,
    generate_video_thumbnail
)


class VisionLLMClient:
    """视觉大语言模型客户端，支持直出与分步（识图描述 + 文本润色）两种工作流，支持三模型配置与自动兜底"""

    def __init__(self, vl_config: dict, vision_config: dict, text_config: dict):
        self.vl_config = vl_config
        self.vision_config = vision_config
        self.text_config = text_config

    def _encode_image(self, image_path: str) -> str:
        """对本地图片进行 Base64 编码"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def _extract_video_frames(self, video_path: str, num_frames: int = 4) -> List[str]:
        """从本地视频中抽取关键帧保存为临时图片文件，以供 Vision LLM 分析"""
        temp_dir = tempfile.gettempdir()
        frames_paths = []

        try:
            # 1. 尝试使用 ffprobe 获取视频时长
            duration = 10.0  # 默认兜底时长
            cmd_duration = [
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', video_path
            ]
            res = subprocess.run(cmd_duration, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                try:
                    duration = float(res.stdout.strip())
                except ValueError:
                    pass

            log_info(f"视频时长检测为: {duration:.2f}秒，准备提取 {num_frames} 个关键帧画面...")

            # 2. 计算等间距时间点并使用 ffmpeg 截图
            time_points = [duration * (i + 1) / (num_frames + 1) for i in range(num_frames)]

            for idx, tp in enumerate(time_points):
                out_name = f"frame_{hashlib.md5(video_path.encode()).hexdigest()[:8]}_{idx}.jpg"
                out_path = os.path.join(temp_dir, out_name)
                cmd_ffmpeg = [
                    'ffmpeg', '-y', '-ss', f"{tp:.2f}", '-i', video_path,
                    '-vframes', '1', '-f', 'image2', out_path
                ]
                res_ff = subprocess.run(cmd_ffmpeg, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res_ff.returncode == 0 and os.path.exists(out_path):
                    frames_paths.append(out_path)
        except Exception as e:
            log_warn(f"使用 ffmpeg/ffprobe 命令行提取视频帧失败或未安装: {e}")

        # 3. Fallback: 如果 ffmpeg 失败或未安装，尝试使用 opencv-python
        if not frames_paths:
            try:
                import cv2
                log_info("尝试使用 OpenCV (cv2) 提取视频帧...")
                cap = cv2.VideoCapture(video_path)
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if total_frames > 0:
                    step = max(1, total_frames // (num_frames + 1))
                    for i in range(num_frames):
                        frame_id = step * (i + 1)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
                        ret, frame = cap.read()
                        if ret:
                            out_name = f"frame_{hashlib.md5(video_path.encode()).hexdigest()[:8]}_{i}.jpg"
                            out_path = os.path.join(temp_dir, out_name)
                            cv2.imwrite(out_path, frame)
                            frames_paths.append(out_path)
                cap.release()
            except ImportError:
                log_error("本地环境未安装 OpenCV (opencv-python) 且 ffmpeg 命令行工具不可用，无法抽取视频帧！")
            except Exception as ex:
                log_error(f"使用 OpenCV 提取视频帧异常: {ex}")

        return frames_paths

    def _call_llm_api(self, messages: List[Dict[str, Any]], api_key: str, api_base: str, model_name: str) -> str:
        """底层封装的 API 请求发送方法"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": 800
        }
        url = f"{api_base.rstrip('/')}/chat/completions"
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        if r.status_code == 200:
            resp_json = r.json()
            return resp_json["choices"][0]["message"]["content"].strip()
        else:
            log_error(f"大模型接口调用失败，模型: {model_name}，HTTP {r.status_code}，返回: {r.text}")
            raise RuntimeError(f"LLM API 响应错误: {r.status_code}")

    def _append_images_to_content(self, content_list: List[Dict[str, Any]], b64_images: List[Tuple[str, str]]):
        """将 Base64 编码的图片追加到请求的 content_list 中"""
        for path_name, b64_data in b64_images:
            mime_type = "image/jpeg"
            if path_name.lower().endswith(".png"):
                mime_type = "image/png"
            elif path_name.lower().endswith(".webp"):
                mime_type = "image/webp"
            elif path_name.lower().endswith(".gif"):
                mime_type = "image/gif"
            
            content_list.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{b64_data}"
                }
            })

    def generate_moment_copy(self, file_path: str, user_prompt: str = None, pipeline: str = "direct") -> str:
        """读取本地媒体文件，调用 Vision LLM 视觉分析并生成中文文案"""
        file_lower = file_path.lower()
        is_video = file_lower.endswith(('.mp4', '.mov', '.avi', '.mkv'))

        b64_images = []
        temp_files = []

        if is_video:
            log_info(f"正在对视频进行帧提取: {file_path} ...")
            temp_files = self._extract_video_frames(file_path, num_frames=4)
            if not temp_files:
                raise RuntimeError("提取视频关键帧失败，无法使用 Vision LLM 进行内容识别！")
            for tf in temp_files:
                b64_images.append((tf, self._encode_image(tf)))
        else:
            log_info(f"正在对图片进行 Base64 编码: {file_path} ...")
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            b64_images.append((file_path, self._encode_image(file_path)))

        try:
            if pipeline == "direct":
                # === 直接调用 VL 大模型一步到位管道 ===
                if not self.vl_config.get("api_key"):
                    raise ValueError("未配置通用或 VL 模型的 LLM_API_KEY，请检查配置！")
                
                log_info(f"【工作流：直出发帖文案】使用纯 VL 模型: {self.vl_config['model']}")
                base_prompt = (
                    "你是一个真实的人类，正在发一条个人朋友圈或小红书生活动态分享。请你仔细分析给出的图片（如果是多张，则为同一视频的连续帧画面），"
                    "并根据画面所传达的整体氛围、生活场景与主观心境，撰写一段自然、松弛、口语化的文案（中文）。符合以下要求：\n"
                    "1. **拒绝机器人味，像真人一样发言**：文案必须以第一人称（我、今天等）出发，分享松弛感、心情或主观体验，绝对不要像 AI 识图一样冷冰冰地罗列和提及画面里的具体物品与位置细节；\n"
                    "2. **融入生活随笔**：如果一定要提到画面里美丽的事物（如花、景物），要将它们自然融入到心情或感受的随性记录中，写得自然且有人气儿；\n"
                    "3. **短小精悍，极简口语化**：语气要像随手发的朋友圈那样轻松，多用贴切的表情符号；字数一定要短，通常 2-4 句话即可，越随性越好；\n"
                    "4. 结尾附带 2-3 个符合该生活氛围的热门话题标签；\n"
                    "5. 只返回文案内容本身，不要带有任何引言、格式标志。"
                )
                if user_prompt:
                    base_prompt += f"\n特别要求：{user_prompt}"

                content_list = [{"type": "text", "text": base_prompt}]
                self._append_images_to_content(content_list, b64_images)

                messages = [{"role": "user", "content": content_list}]
                content_text = self._call_llm_api(
                    messages, 
                    self.vl_config["api_key"], 
                    self.vl_config["api_base"], 
                    self.vl_config["model"]
                )

            else:
                # === 分步管道 ===
                log_info(f"【工作流：分步文案生成】")
                
                # 第一步：获取描述。检查视觉模型配置。
                # 如果视觉模型配置空缺，则使用 纯 VL 模型兜底进行画面识别。
                desc_prompt = (
                    "请你仔细分析给出的图片（如果是多张，则为同一视频的连续帧画面），"
                    "并用客观、清晰、具体的语言详细描述画面中出现的人物、物品、动作、背景、色彩、文字以及整体氛围。"
                    "请尽量包含细节，字数控制在 300 字以内。"
                )
                content_list = [{"type": "text", "text": desc_prompt}]
                self._append_images_to_content(content_list, b64_images)
                messages = [{"role": "user", "content": content_list}]

                if self.vision_config.get("model") and self.vision_config.get("model").strip():
                    # 使用专门的视觉模型
                    v_key = self.vision_config["api_key"]
                    v_base = self.vision_config["api_base"]
                    v_model = self.vision_config["model"].strip()
                    log_info(f"第一阶段（画面描述）：使用专门的【视觉模型】: {v_model}")
                else:
                    # 视觉模型留空，走后两个链路兜底：使用 VL 模型进行识图
                    v_key = self.vl_config["api_key"]
                    v_base = self.vl_config["api_base"]
                    v_model = self.vl_config["model"]
                    log_info(f"第一阶段（画面描述）：专门【视觉模型】留空，调用【纯 VL 模型】兜底识图: {v_model}")

                if not v_key:
                    raise ValueError("视觉识别阶段未配置有效的 API Key！")

                description_text = self._call_llm_api(messages, v_key, v_base, v_model)
                log_success("画面视觉描述生成成功！")
                
                if config.LOG_LEVEL == "DEBUG" or len(description_text) > 0:
                    log_info(f"【AI 识别画面描述】：\n{description_text}\n")

                # 第二步：调用纯 LLM 文本大模型进行文案撰写
                if not self.text_config.get("api_key"):
                    raise ValueError("文案生成阶段未配置有效的纯 LLM API Key！")

                log_info(f"第二阶段（文案撰写）：使用【纯 LLM 文本大模型】: {self.text_config['model']}")
                text_prompt = (
                    "你是一个真实的人类，准备发一条朋友圈或小红书生活动态。下面有一段关于你拍摄的图片或视频画面的文字描述。\n"
                    f"【拍摄画面描述】：\n{description_text}\n\n"
                    "请你根据这段画面描述所传达的整体氛围与主观心情，站在第一人称的角度，撰写一段非常自然、松弛、生活化的小短文（中文）。符合以下要求：\n"
                    "1. **拒绝机器人味，不要客观罗列**：绝对不能像机器人一样原样复述或罗列描述中出现的物品（不要写‘我拍到了朱顶红和狐尾蕨’这类点名式的硬性描述），要把它们转化为你当时的主观心路历程、瞬间联想或心情分享（比如写‘满眼粉橙色，被阳光治愈的午后’）；\n"
                    "2. **第一人称与生活感**：以第一人称（我、今天等）出发，突出松弛感与情感共鸣，语气要随和、亲切，像在跟老朋友分享今天随手拍到的美好瞬间；\n"
                    "3. **短小随性**：字数控制在 100 字以内，保持简短有张力，多用贴切的表情符号；\n"
                    "4. 结尾附带 2-3 个符合该生活氛围的热门话题标签；\n"
                    "5. 只返回文案内容本身，不要带有任何引言或格式标志。"
                )
                if user_prompt:
                    text_prompt += f"\n特别要求：{user_prompt}"

                messages = [{"role": "user", "content": text_prompt}]
                content_text = self._call_llm_api(
                    messages, 
                    self.text_config["api_key"], 
                    self.text_config["api_base"], 
                    self.text_config["model"]
                )

            # 过滤 Markdown 块包裹标记
            if content_text.startswith("```"):
                lines = content_text.splitlines()
                if len(lines) >= 2:
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines[-1].strip() == "```":
                        lines = lines[:-1]
                    content_text = "\n".join(lines).strip()
            
            return content_text

        finally:
            # 清理临时文件
            for tf in temp_files:
                try:
                    os.remove(tf)
                except Exception:
                    pass


def parse_args():
    parser = argparse.ArgumentParser(description="智能识图/视文案生成并单贴发布脚本")
    parser.add_argument(
        "--file",
        type=str,
        required=True,
        help="本地待发布的图片或视频文件路径"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="",
        help="给大语言模型文案生成的补充微调提示词（可选）"
    )
    parser.add_argument(
        "--pipeline",
        type=str,
        choices=["direct", "two-stage"],
        default=None,
        help="工作流管道类型: direct (直接调用视觉模型一步生成), two-stage (先识图获取文字描述, 再调文本大语言模型写文案。未指定时根据 .env 自动识别)"
    )
    parser.add_argument(
        "--email",
        type=str,
        default="",
        help="指定用于发帖的邮箱账号（可选，若不指定则从 CSV 随机选一个）"
    )
    parser.add_argument(
        "--password",
        type=str,
        default="",
        help="指定账号的密码（可选，仅当指定 --email 时生效）"
    )
    parser.add_argument(
        "--accounts-csv",
        type=str,
        default=config.POST_DEFAULT_ACCOUNTS_CSV,
        help=f"账号 CSV 文件路径 (默认: {config.POST_DEFAULT_ACCOUNTS_CSV})"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=config.MOMENTS_API_URL,
        help=f"朋友圈发布接口 URL (默认: {config.MOMENTS_API_URL})"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=config.POST_REQUEST_TIMEOUT,
        help=f"网络请求超时时间（秒） (默认: {config.POST_REQUEST_TIMEOUT})"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="开启调试输出"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print_section_header("智能视觉发帖任务启动")

    # 1. 检查本地输入文件是否存在
    if not os.path.exists(args.file):
        log_error(f"找不到指定的本地媒体文件: {args.file}")
        sys.exit(1)

    file_lower = args.file.lower()
    is_video = file_lower.endswith(('.mp4', '.mov', '.avi', '.mkv'))
    is_image = file_lower.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif'))

    if not is_video and not is_image:
        log_error(f"不支持的媒体类型: {args.file}。仅支持图片 (.jpg/.png/...) 或视频 (.mp4/...)。")
        sys.exit(1)

    # 2. 账号加载与登录
    email = args.email.strip()
    password = args.password.strip()

    if not email:
        # 如果没有指定 email，从账号 CSV 随机挑选一个
        if not os.path.exists(args.accounts_csv):
            log_error(f"账号 CSV 数据库不存在: {args.accounts_csv}，无法随机选择账号")
            sys.exit(1)
        
        accounts = load_accounts(args.accounts_csv, 0)
        if not accounts:
            log_error("从账号 CSV 中未加载到任何账号！")
            sys.exit(1)
        
        import random
        random.seed(int(time.time()))
        email, password = random.choice(accounts)
        log_info(f"未指定发帖账号，已从库中随机选择账号: {email}")
    else:
        # 如果指定了 email 但没有指定 password，尝试在 CSV 中寻找匹配密码
        if not password:
            if os.path.exists(args.accounts_csv):
                accounts = load_accounts(args.accounts_csv, 0)
                for acc_email, acc_pwd in accounts:
                    if acc_email.lower() == email.lower():
                        password = acc_pwd
                        log_info(f"已自动从 CSV 库中匹配到账号 {email} 的密码。")
                        break
            if not password:
                log_error(f"指定了发帖账号 {email}，但未提供密码且在 CSV 库中匹配失败！")
                sys.exit(1)

    # 登录获取发帖 Token
    log_info(f"正在登录发帖账号: {email}...")
    token = login_account(email, password, args.timeout)
    if not token:
        log_error("账号登录失败，终止任务。")
        sys.exit(1)
    log_success(f"账号 {email} 登录成功。")

    # 准备三个模型的配置字典，2. 视觉模型 作为通用/默认配置，1. 纯 VL 模型 和 3. 纯 LLM 默认向其兜底
    vision_config = {
        "api_key": config.LLM_API_KEY,
        "api_base": config.LLM_API_BASE,
        "model": config.LLM_MODEL
    }
    
    vl_config = {
        "api_key": config.LLM_VL_API_KEY,
        "api_base": config.LLM_VL_API_BASE,
        "model": config.LLM_VL_MODEL
    }
    
    text_config = {
        "api_key": config.LLM_TEXT_API_KEY,
        "api_base": config.LLM_TEXT_API_BASE,
        "model": config.LLM_TEXT_MODEL
    }

    # 动态判定默认工作流
    pipeline = args.pipeline
    if not pipeline:
        is_vision_model_empty = not config.LLM_MODEL or not config.LLM_MODEL.strip()
        if is_vision_model_empty:
            pipeline = "two-stage"
            log_info("检测到通用/视觉模型 (LLM_MODEL) 留空，自动启用分步链路 (two-stage)")
        else:
            pipeline = "direct"
            log_info("未指定链路类型，默认启用直出链路 (direct)")
    else:
        log_info(f"手动指定工作流链路: {pipeline}")

    # 验证 API 凭证完整性
    if pipeline == "direct" and not vl_config["api_key"]:
        log_error("未配通用的或 VL 专属的 LLM_API_KEY，请检查 `.env` 配置！")
        sys.exit(1)
    elif pipeline == "two-stage":
        v_key = vision_config["api_key"] if (vision_config["model"] and vision_config["model"].strip()) else vl_config["api_key"]
        t_key = text_config["api_key"]
        if not v_key or not t_key:
            log_error("分步链路配置不完整！第一阶段识别 key 或第二阶段文本 key 留空，请检查 `.env` 配置！")
            sys.exit(1)

    client = VisionLLMClient(
        vl_config=vl_config,
        vision_config=vision_config,
        text_config=text_config
    )

    try:
        content_text = client.generate_moment_copy(args.file, args.prompt, pipeline)
    except Exception as e:
        log_error(f"生成发帖文案失败: {e}")
        sys.exit(1)

    print_section_separator()
    print(f"{Colors.BOLD}【AI 智能生成的发帖文案】：{Colors.ENDC}")
    print(f"{Colors.GREEN}{content_text}{Colors.ENDC}")
    print_section_separator()

    # 4. 获取 AWS S3 上传临时凭证
    log_info("正在获取 AWS S3 临时上传凭证...")
    s3_creds = get_aws_credentials(token, args.timeout)
    if not s3_creds:
        log_error("获取 AWS S3 上传凭证失败，托管中止。")
        sys.exit(1)

    # 5. 上传本地媒体文件到 S3，并处理视频缩略图
    upload_mapping = {}
    files_to_upload = [args.file]
    thumb_local_path = ""

    if is_video:
        log_info("正在自动生成视频缩略图...")
        thumb_local_path = generate_video_thumbnail(args.file)
        if thumb_local_path and os.path.exists(thumb_local_path):
            files_to_upload.append(thumb_local_path)
            log_success(f"视频缩略图生成成功，保存至: {thumb_local_path}")
        else:
            log_warn("自动生成视频缩略图失败，发帖时将不携带缩略图。")

    # 批量上传
    for filepath in files_to_upload:
        aws_url = upload_image_to_s3(filepath, s3_creds)
        if aws_url:
            upload_mapping[filepath] = aws_url
        else:
            log_error(f"媒体文件 {filepath} 上传 S3 失败！终止发帖。")
            sys.exit(1)

    log_success("所有本地媒体文件已成功上传至 AWS S3 托管！")

    # 6. 构建发布 Payload
    payload = {
        "content": content_text,
        "visibility": 0  # 默认公开
    }

    if is_video:
        video_s3_url = upload_mapping.get(args.file, "")
        thumb_s3_url = upload_mapping.get(thumb_local_path, "")
        payload["media_info"] = {
            "type": "video",
            "video_url": video_s3_url,
            "thumbnail_url": thumb_s3_url
        }
    else:
        image_s3_url = upload_mapping.get(args.file, "")
        payload["media_info"] = {
            "type": "image",
            "images": [image_s3_url]
        }

    # 7. 发送帖子
    log_info(f"正在通过 API 发送动态帖子...")
    post_item = (1, payload, email, token)
    line, status_code, detail_msg, moment_id, err_detail, poster_account = send_post(
        post_item, args.api_url, args.timeout
    )

    if status_code == 200:
        log_success(f"【发帖成功！】朋友圈 ID: {moment_id}")
    else:
        log_error(f"发帖失败！状态码: {status_code}，详情: {detail_msg}")
        sys.exit(1)

    print("=" * 60)


if __name__ == "__main__":
    main()
