# -*- coding: utf-8 -*-
import json
import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# 从 git 恢复原始数据
import subprocess
result = subprocess.run(
    ['git', 'show', 'feature/customs-links:sources/customs_images.json'],
    capture_output=True, encoding='utf-8', errors='replace'
)
data = json.loads(result.stdout)
print(f"Restored {data.get('total_unique', 0)} images from git")

# 保存
OUTPUT = Path("sources/customs_images.json")
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# 生成 CSV 素材
IMAGES = data.get("images", [])
GROUP_SIZE = 4
LIMIT = 20

with open("moments_gleezy_final.csv", "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["content", "visibility", "room_id", "image_urls"])
    writer.writeheader()
    captions = [
        "分享一组美图给大家～喜欢的朋友扣 1 📸",
        "今日份福利 🎁 看看有没有你喜欢的？",
        "这些照片太美了，忍不住分享给你们 ✨",
        "姐妹们，这组写真你们打几分？💯",
        "周末好心情，分享一波美图 🌸",
    ]
    for i in range(0, min(len(IMAGES), LIMIT), GROUP_SIZE):
        group = IMAGES[i:i+GROUP_SIZE]
        urls = ",".join(img["url"] for img in group)
        caption = captions[(i // GROUP_SIZE) % len(captions)]
        writer.writerow({
            "content": caption,
            "visibility": "0",
            "room_id": "",
            "image_urls": urls,
        })

print(f"Generated moments_gleezy_final.csv ({len(IMAGES)//GROUP_SIZE} posts)")
