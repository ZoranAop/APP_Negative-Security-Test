#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_default.py — 默认「混合交错」一键发布入口（科技资讯 + 图文，S3 上传图片）。

★ 这是项目推荐的默认发帖方式 ★

机制：
  1. 从 10 个科技资讯源 fetch 文本素材（RSS/HTML/curl_cffi）
  2. 下载图片并上传 S3，获取 CDN URL
  3. 按用户交错组装：文本帖(T) 与 图文帖(I) 混合
  4. 语言跟随网站/随机分配，#标签与正文语言严格一致
  5. 按发帖人角色（persona）生成第一人称文案
  6. round-robin 交错发布

核心规则（文本与标签语言一致）：
  繁体中文正文 → #科技    英文正文 → #Tech
  日文正文 → #テクノロジー  马来语/印尼语正文 → #Teknologi

用法：
    # 20 用户 × 每人 3 帖 = 60 帖
    py -3 scripts/run_default.py --accounts-csv accounts.csv --num-users 20 --posts-per-user 3 --yes

    # 只预览不发布
    py -3 scripts/run_default.py --accounts-csv accounts.csv --skip-publish

    # 指定语言
    py -3 scripts/run_default.py --accounts-csv accounts.csv --langs zh_hant,en,ja,ms
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# Import project modules
from config import config
from fetch_tech import FETCHERS, SITE_CN, SITE_LANG, ALL_SOURCES
from run_tech import (LANG_TAG, LANG_VIA, LANG_TEMPLATES, persona_for,
                      build_caption, _to_hant)
from caption_multilang import pick_template, detect_scene

# ---- 默认 10 个科技资讯源（第四/五批验证通过）----
DEFAULT_TECH_SOURCES = [
    "straitstimes", "yahoo_intl", "cnbc_world", "hket_home", "moneydj",
    "hk_investing", "wealth_tw", "bloomberg_jp", "8world", "ifnews",
]

# ---- 公共可用图片池（示例；实际部署可从 multi_source_fetch.py 获取）----
DEFAULT_IMAGE_POOL = [
    "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=600&q=80",
    "https://images.unsplash.com/photo-1519681393784-d120267933ba?w=600&q=80",
    "https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=600&q=80",
    "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=600&q=80",
    "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=600&q=80",
    "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=600&q=80",
    "https://images.unsplash.com/photo-1518837695005-2083093ee35b?w=600&q=80",
    "https://images.unsplash.com/photo-1523464862212-d6631d073194?w=600&q=80",
    "https://images.unsplash.com/photo-1502082553048-f009c37129b9?w=600&q=80",
    "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?w=600&q=80",
    "https://images.unsplash.com/photo-1504198453319-5ce911bafcde?w=600&q=80",
    "https://images.unsplash.com/photo-1469474968028-56623f02e42e?w=600&q=80",
]

# ---- 交错模式（T=文本, I=图文）----
PATTERNS_3 = [["T", "I", "T"], ["I", "T", "I"], ["T", "T", "I"], ["I", "T", "T"]]
PATTERNS_5 = [["T", "I", "T", "I", "T"], ["I", "T", "I", "T", "I"],
              ["T", "I", "T", "T", "I"], ["I", "T", "T", "I", "T"],
              ["T", "T", "I", "T", "I"]]

SUPPORTED_LANGS = ["zh_hant", "en", "ja", "ms", "id"]


def _u8():
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", write_through=True)
    except Exception:
        pass


def upload_image_to_s3(image_url: str, token: str, *, images_dir: Path) -> str:
    """下载图片 → 上传 S3 → 返回 CDN URL。失败时回退到原始 URL。"""
    try:
        import boto3
    except ImportError:
        return image_url

    # 获取 S3 凭证
    creds_url = os.getenv("UPLOAD_CREDENTIALS_URL", config.UPLOAD_CREDENTIALS_URL)
    try:
        r = requests.post(creds_url,
                          headers={"Authorization": f"Bearer {token}"},
                          timeout=15)
        if r.status_code != 200 or r.json().get("code") != 0:
            return image_url
        creds = r.json()["data"]
    except Exception:
        return image_url

    # 下载图片
    try:
        img_r = requests.get(image_url, timeout=30,
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                      "AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"})
        if img_r.status_code != 200 or len(img_r.content) < 1000:
            return image_url
    except Exception:
        return image_url

    # 上传到 S3
    url_hash = hashlib.md5(image_url.encode()).hexdigest()[:12]
    ext = ".jpg"
    for e in (".png", ".webp", ".gif"):
        if e in image_url.lower():
            ext = e
            break
    date_path = time.strftime("%Y/%m/%d")
    key = f"square/original/{date_path}/mixed_{url_hash}{ext}"

    images_dir.mkdir(parents=True, exist_ok=True)
    local = images_dir / f"dl_{url_hash}{ext}"
    local.write_bytes(img_r.content)

    try:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=creds["access_key_id"],
            aws_secret_access_key=creds["secret_access_key"],
            aws_session_token=creds["session_token"],
            region_name=creds.get("region", "ap-northeast-1"),
        )
        ct = "image/jpeg" if ext == ".jpg" else f"image/{ext.strip('.')}"
        s3.upload_file(str(local), creds["bucket"], key,
                       ExtraArgs={"ContentType": ct,
                                  "CacheControl": "public, max-age=31536000, immutable"})
    except Exception:
        local.unlink(missing_ok=True)
        return image_url

    local.unlink(missing_ok=True)
    domain = creds.get("domain", "teststatic-x.tp-ex.com")
    return f"https://{domain}/{key}"


def load_accounts(path: Path, num: int) -> list[dict]:
    """加载账号 CSV（兼容多种列名）。"""
    with path.open("r", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    accts = []
    for r in rows:
        email = (r.get("邮箱") or r.get("email") or r.get("用户邮箱") or "").strip()
        pw = (r.get("密码") or r.get("password") or r.get("用户密码") or "").strip()
        nick = (r.get("昵称") or r.get("用户昵称") or r.get("nickname") or "").strip()
        if email and pw:
            accts.append({"email": email, "password": pw, "nick": nick})
    if num > 0 and len(accts) > num:
        random.shuffle(accts)
        accts = accts[:num]
    return accts


def main() -> int:
    _u8()
    ap = argparse.ArgumentParser(
        description="默认混合交错发布：科技文本 + 图文(S3) + 角色文案 + 标签一致",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--accounts-csv", required=True, help="账号 CSV")
    ap.add_argument("--num-users", type=int, default=20, help="选择用户数")
    ap.add_argument("--posts-per-user", type=int, default=3, help="每用户帖数(3或5)")
    ap.add_argument("--tech-sources", default=",".join(DEFAULT_TECH_SOURCES))
    ap.add_argument("--per-site", type=int, default=8, help="每个科技源取多少条")
    ap.add_argument("--image-csv", default="", help="图文素材 CSV (含 image_urls 列)；留空使用内置图片池")
    ap.add_argument("--langs", default="zh_hant,en,ja,ms", help="语言列表(逗号分隔)")
    ap.add_argument("--login-spacing", type=float, default=5.0)
    ap.add_argument("--post-delay", type=float, default=0.8)
    ap.add_argument("--skip-publish", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed or int(time.time()))
    langs = [l.strip() for l in args.langs.split(",") if l.strip() in SUPPORTED_LANGS]
    if not langs:
        langs = ["zh_hant", "en"]

    # ---- Step 1: Fetch tech news ----
    print("\n=== Step 1: 采集科技资讯 ===")
    sources = [s.strip() for s in args.tech_sources.split(",") if s.strip() in FETCHERS]
    all_text_items = []
    for src in sources:
        try:
            items = FETCHERS[src](args.per_site)
            lang = SITE_LANG.get(src, "en")
            for it in items:
                it["lang"] = lang
                it["_site"] = it["site"]
                it["_title"] = it["title"]
            all_text_items.extend(items)
            print(f"  [{src}] {len(items)} items (lang={lang})")
        except Exception as e:
            print(f"  [{src}] ERR: {e}")
    print(f"  Total text items: {len(all_text_items)}")

    # ---- Step 2: Prepare image pool ----
    print("\n=== Step 2: 准备图片素材 ===")
    image_pool = list(DEFAULT_IMAGE_POOL)
    if args.image_csv and Path(args.image_csv).exists():
        with open(args.image_csv, "r", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                urls = (row.get("image_urls") or "").strip()
                if urls:
                    image_pool.append(urls.split(",")[0].strip())
    print(f"  Image pool: {len(image_pool)} URLs")

    # ---- Step 3: Load accounts & login ----
    print(f"\n=== Step 3: 加载 {args.num_users} 个用户并登录 ===")
    acc_path = ROOT / args.accounts_csv
    if not acc_path.exists():
        print(f"ERROR: 账号文件不存在: {acc_path}", file=sys.stderr)
        return 2
    accts = load_accounts(acc_path, args.num_users)
    print(f"  Loaded: {len(accts)} accounts")

    tokens = {}
    for i, acc in enumerate(accts):
        r = requests.post(config.LOGIN_URL, json={
            "email": acc["email"], "password": acc["password"],
            "device_id": config.POST_DEVICE_ID, "device_name": config.POST_DEVICE_NAME,
        }, timeout=config.POST_REQUEST_TIMEOUT)
        if r.status_code == 200 and r.json().get("code") == 0:
            tokens[acc["email"]] = r.json()["data"]["token"]
            print(f"  [{i+1}/{len(accts)}] OK: {acc['nick']}")
        elif r.status_code == 429:
            print(f"  [{i+1}/{len(accts)}] 429, waiting 30s...")
            time.sleep(30)
            r = requests.post(config.LOGIN_URL, json={
                "email": acc["email"], "password": acc["password"],
                "device_id": config.POST_DEVICE_ID, "device_name": config.POST_DEVICE_NAME,
            }, timeout=config.POST_REQUEST_TIMEOUT)
            if r.status_code == 200 and r.json().get("code") == 0:
                tokens[acc["email"]] = r.json()["data"]["token"]
                print(f"  [{i+1}/{len(accts)}] OK (retry): {acc['nick']}")
            else:
                print(f"  [{i+1}/{len(accts)}] FAILED")
        else:
            print(f"  [{i+1}/{len(accts)}] FAILED ({r.status_code})")
        time.sleep(args.login_spacing)

    print(f"\n  Logged in: {len(tokens)}/{len(accts)}")
    if not tokens:
        print("ERROR: 无法登录任何账号", file=sys.stderr)
        return 1

    # ---- Step 4: Upload images to S3 ----
    print("\n=== Step 4: 上传图片到 S3 ===")
    first_token = list(tokens.values())[0]
    images_dir = ROOT / "tech_run" / "images"
    cdn_urls = []
    need_imgs = (args.num_users * args.posts_per_user) // 2 + 5
    for img_url in image_pool[:need_imgs]:
        cdn_url = upload_image_to_s3(img_url, first_token, images_dir=images_dir)
        cdn_urls.append(cdn_url)
    print(f"  Prepared: {len(cdn_urls)} image CDN URLs")

    # ---- Step 5: 组装混合帖子 ----
    print(f"\n=== Step 5: 组装 {len(tokens)} 用户 × {args.posts_per_user} 帖 ===")
    patterns = PATTERNS_3 if args.posts_per_user <= 3 else PATTERNS_5

    # 语言分配：按用户轮询
    user_langs = []
    for i in range(len(tokens)):
        user_langs.append(langs[i % len(langs)])
    rng.shuffle(user_langs)

    text_idx = 0
    img_idx = 0
    tmpl_used = {}
    seen_caps: set[str] = set()
    per_user_posts: list[list[dict]] = []

    for u in range(len(tokens)):
        lang = user_langs[u]
        pattern = patterns[u % len(patterns)][:args.posts_per_user]
        posts = []
        for slot, kind in enumerate(pattern):
            if kind == "T":
                # 文本帖：科技资讯 + 角色文案
                item = all_text_items[text_idx % len(all_text_items)]
                text_idx += 1
                site_lang = item.get("lang", lang)
                persona = persona_for(u * args.posts_per_user + slot, site_lang)
                caption = build_caption(item, site_lang, persona, seen=seen_caps)
                posts.append({"content": caption, "image_urls": "", "ptype": "text", "lang": site_lang})
            else:
                # 图文帖：S3 CDN 图片 + 场景文案
                scene = rng.choice(["portrait", "selfie", "ootd", "cafe", "street", "travel"])
                caption = pick_template(scene, lang, tmpl_used)
                img_url = cdn_urls[img_idx % len(cdn_urls)] if cdn_urls else ""
                img_idx += 1
                posts.append({"content": caption, "image_urls": img_url, "ptype": "image", "lang": lang})
        per_user_posts.append(posts)

    # Round-robin 交错：slot0 all users → slot1 all users → ...
    interleaved = []
    for slot in range(args.posts_per_user):
        for u in range(len(tokens)):
            interleaved.append({"user_idx": u, **per_user_posts[u][slot]})

    ptype_dist = Counter(p["ptype"] for p in interleaved)
    lang_dist = Counter(p["lang"] for p in interleaved)
    print(f"  Total: {len(interleaved)} posts")
    print(f"  Types: {dict(ptype_dist)}")
    print(f"  Langs: {dict(lang_dist)}")

    if args.skip_publish:
        print("\n[--skip-publish] 仅预览，不发布。")
        for i, p in enumerate(interleaved[:10]):
            flag = "IMG" if p["ptype"] == "image" else "TXT"
            print(f"  [{flag}/{p['lang']}] {p['content'][:60]}")
        return 0

    if not args.yes:
        if input(f"\n  确认发布 {len(interleaved)} 帖？(y/n): ").strip().lower() not in ("y", "yes"):
            print("已取消。")
            return 0

    # ---- Step 6: 发布 ----
    print(f"\n=== Step 6: 发布 {len(interleaved)} 帖 (round-robin) ===")
    token_list = list(tokens.values())
    success, fail = 0, 0

    for i, post in enumerate(interleaved):
        token = token_list[post["user_idx"] % len(token_list)]
        if post["ptype"] == "image" and post["image_urls"]:
            payload = {"content": post["content"], "visibility": 0,
                       "media_info": {"type": "image", "images": [post["image_urls"]]}}
        else:
            payload = {"content": post["content"], "visibility": 0,
                       "media_info": {"type": "text"}}

        try:
            r = requests.post(config.MOMENTS_API_URL, json=payload,
                              headers={"Authorization": f"Bearer {token}",
                                       "Content-Type": "application/json"},
                              timeout=config.POST_REQUEST_TIMEOUT)
            if r.status_code == 200 and r.json().get("code") == 0:
                success += 1
                if i < 5 or i % 20 == 0:
                    flag = "IMG" if post["ptype"] == "image" else "TXT"
                    print(f"  [{i+1}/{len(interleaved)}] OK [{flag}/{post['lang']}] "
                          f"{post['content'][:50]}")
            else:
                fail += 1
                if fail <= 3:
                    print(f"  [{i+1}/{len(interleaved)}] FAIL: {r.text[:80]}")
        except Exception as e:
            fail += 1

        time.sleep(args.post_delay)

    print(f"\n{'=' * 60}")
    print(f"  RESULT: {success}/{len(interleaved)} success, {fail} failed")
    print(f"  Types: {dict(ptype_dist)}  Langs: {dict(lang_dist)}")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
