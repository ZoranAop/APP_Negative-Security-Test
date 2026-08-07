#!/usr/bin/env python3
"""
post_tuzi_beauty.py — 从 tuziyouwang 美女标签深页取图，匹配写真描述发布

用法:
    # 单用户发3帖，单图
    py -3 scripts/post_tuzi_beauty.py --nickname 青云街拍 --posts 3

    # 单用户发2帖，多图(2-6张)
    py -3 scripts/post_tuzi_beauty.py --nickname 青云街拍 --posts 2 --imgs-min 2 --imgs-max 6

    # 指定去重账本
    py -3 scripts/post_tuzi_beauty.py --nickname 归途快门 --posts 3 --dedupe data/tuzi_used.json

工作流:
    1) 从摄影师列表(街拍摄影师.csv)获取用户
    2) 加载去重账本，跳过已用URL
    3) 从 tuziyouwang 深页(10页起)轮换栏目取图
    4) 生成繁体中文写真风格描述(≤12字)
    5) 调用 publish_from_tokens.py 发布
"""
import argparse, csv, json, os, re, subprocess, sys, time, random, requests
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BASE = "http://tuziyouwang.com"
COLUMNS = ["meitui", "fengtun", "gengduo", "xiaoneinei", "xiongqi"]
DEDUPE_FILE_VAR = ROOT / "data" / "tuzi_used.json"
PHOTOGRAPHER_CSV = ROOT / "pre_企管用户_街拍摄影师.csv"

# 写真风格繁体文案(≤12字) + 标签
CAPTIONS = [
    ("寫真光影一瞬", "#寫真"),
    ("鏡頭定格美麗", "#人像"),
    ("街角唯美寫真", "#攝影"),
    ("寫真時光定格", "#寫真"),
    ("鏡中倩影如畫", "#人像"),
    ("光影輕撫瞬間", "#攝影"),
    ("寫真三連拍", "#寫真集"),
    ("光影四格隨拍", "#寫真攝影"),
    ("寫真三幀連拍", "#寫真集"),
    ("寫真五連拍精選", "#寫真攝影"),
    ("寫真四幀精選集", "#寫真集"),
    ("寫真六連拍合輯", "#寫真攝影"),
    ("人像寫真隨手拍", "#寫真"),
    ("光影寫真日記", "#人像攝影"),
]


def load_used(dedupe_path):
    used = set()
    if dedupe_path.exists():
        try:
            data = json.loads(dedupe_path.read_text(encoding="utf-8"))
            used = set(data.get("used_urls", []))
        except Exception:
            pass
    return used


def save_dedupe(dedupe_path, new_urls):
    existing = []
    if dedupe_path.exists():
        try:
            data = json.loads(dedupe_path.read_text(encoding="utf-8"))
            existing = data.get("used_urls", [])
        except Exception:
            pass
    for u in new_urls:
        if u not in existing:
            existing.append(u)
    dedupe_path.parent.mkdir(parents=True, exist_ok=True)
    dedupe_path.write_text(json.dumps({"used_urls": existing}, ensure_ascii=False, indent=2), encoding="utf-8")


def _get(url, ref):
    r = requests.get(url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": ref})
    r.raise_for_status()
    r.encoding = 'gb2312'
    return r.text


def fetch_images(want: int, used: set):
    images, seen_id = [], set()
    start_page = max(10, len(used) // 3)
    for col in COLUMNS:
        for page in range(start_page, start_page + 30):
            url = f"{BASE}/{col}/index_{page}.html"
            try:
                txt = _get(url, f"{BASE}/{col}/")
                ids = re.findall(rf"/{col}/(\d+)\.html", txt)
            except Exception:
                continue
            for aid in ids:
                if aid in seen_id:
                    continue
                seen_id.add(aid)
                try:
                    detail = _get(f"{BASE}/{col}/{aid}.html", f"{BASE}/{col}/")
                    imgs = re.findall(r'<img[^>]+src="([^"]+)"[^>]*>', detail)
                    for img in imgs:
                        if not img.lower().endswith(('.jpg', '.jpeg', '.png')):
                            continue
                        if '/d/file/' not in img:
                            continue
                        full = img if img.startswith('http') else f"{BASE}{img}"
                        if full in used:
                            continue
                        images.append(full)
                        used.add(full)
                        break
                except Exception:
                    continue
                if len(images) >= want:
                    break
            if len(images) >= want:
                break
        if len(images) >= want:
            break
    return images


def find_photographer(nickname: str):
    if not PHOTOGRAPHER_CSV.exists():
        print(f"[error] 摄影师列表不存在: {PHOTOGRAPHER_CSV}", file=sys.stderr)
        sys.exit(1)
    with open(PHOTOGRAPHER_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row["昵称"].strip() == nickname:
                return row
    print(f"[error] 未找到摄影师: {nickname}", file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="tuziyouwang 美女标签 → 写真描述 → 发布")
    ap.add_argument("--nickname", required=True, help="摄影师昵称(街拍摄影师列表)")
    ap.add_argument("--posts", type=int, default=3, help="发帖数")
    ap.add_argument("--imgs-min", type=int, default=1, help="每帖最少图片数")
    ap.add_argument("--imgs-max", type=int, default=1, help="每帖最多图片数")
    ap.add_argument("--dedupe", default=str(DEDUPE_FILE_VAR), help="去重文件路径")
    ap.add_argument("--delay-min", type=float, default=60, help="帖间最小延迟秒")
    ap.add_argument("--delay-max", type=float, default=150, help="帖间最大延迟秒")
    ap.add_argument("--skip-publish", action="store_true", help="仅生成CSV不发布")
    args = ap.parse_args()

    dedupe_path = Path(args.dedupe)

    # 1. 获取摄影师
    pg = find_photographer(args.nickname)
    print(f"[user] {pg['昵称']} ({pg['邮箱']})")

    # 2. 加载去重
    used = load_used(dedupe_path)
    print(f"[dedupe] 已加载 {len(used)} 条去重记录")

    # 3. 取图
    total_imgs = args.posts * args.imgs_max
    images = fetch_images(total_imgs, used)
    print(f"[fetch] 获取 {len(images)} 张新图")

    if len(images) < args.posts * args.imgs_min:
        print(f"[error] 图片不足: 需要≥{args.posts * args.imgs_min}, 实际{len(images)}", file=sys.stderr)
        sys.exit(1)

    # 4. 构建帖子
    ts = time.strftime("%Y%m%d_%H%M%S")
    acc_csv = ROOT / f"result/acc_{args.nickname}_{ts}.csv"
    moments_csv = ROOT / f"result/moments_tuzi_{ts}.csv"

    # 账号CSV
    with open(acc_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["序号", "邮箱", "用户名", "昵称", "密码", "pincode"])
        w.writerow([pg["序号"], pg["邮箱"], pg["用户名"], pg["昵称"], pg["密码"], pg["pincode"]])
    print(f"[account] → {acc_csv}")

    # 分配图片到帖子
    used_captions = set()
    rows = []
    idx = 0
    for p in range(args.posts):
        n = random.randint(args.imgs_min, min(args.imgs_max, len(images) - idx))
        post_imgs = images[idx:idx + n]
        idx += n

        # 随机选描述(不重复)
        available = [c for c in CAPTIONS if c[0] not in used_captions]
        if not available:
            used_captions.clear()
            available = CAPTIONS
        caption, tag = random.choice(available)
        used_captions.add(caption)

        content = f"{caption} {tag}"
        rows.append({
            "content": content,
            "visibility": 0,
            "room_id": "",
            "image_urls": ",".join(post_imgs),
            "location_name": "",
            "location_address": "",
            "location_lat": "",
            "location_lon": "",
        })

    with open(moments_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["content", "visibility", "room_id", "image_urls", "location_name", "location_address", "location_lat", "location_lon"])
        for r in rows:
            w.writerow([r["content"], r["visibility"], r["room_id"], r["image_urls"],
                        r["location_name"], r["location_address"], r["location_lat"], r["location_lon"]])
    print(f"[moments] → {moments_csv} ({len(rows)} 帖)")

    # 5. 发布
    if args.skip_publish:
        print("[skip] --skip-publish，CSV 已生成")
        return 0

    py = sys.executable
    cmd = [
        py, str(HERE / "publish_from_tokens.py"),
        "--accounts-csv", str(acc_csv),
        "--csv", str(moments_csv),
        "--concurrency", "1",
        "--post-delay-min", str(args.delay_min),
        "--post-delay-max", str(args.delay_max),
    ]
    print(f"[publish] {' '.join(cmd)}")
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        print(f"[error] 发布失败 (rc={rc})", file=sys.stderr)
        return rc

    # 6. 更新去重
    save_dedupe(dedupe_path, images)
    print(f"[dedupe] 已更新 → {dedupe_path} (total {len(load_used(dedupe_path))})")
    print("[done]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
