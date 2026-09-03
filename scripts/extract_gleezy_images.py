# -*- coding: utf-8 -*-
import sqlite3
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = Path("gleezy_dump/wk_ad580b8704fb47b1b9c46e4cbe7ccad9.db")
OUTPUT_JSON = Path("sources/customs_images.json")

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 获取频道信息
    cursor.execute("SELECT channel_id, channel_name, channel_type FROM channel")
    channels = {row[0]: {"name": row[1] or row[0], "type": row[2]} for row in cursor.fetchall()}
    print(f"[channels] {len(channels)} channels")

    # 获取所有消息
    cursor.execute("SELECT message_id, channel_id, type, content, timestamp FROM message ORDER BY timestamp DESC")
    messages = cursor.fetchall()
    print(f"[messages] {len(messages)} total")

    # 统计消息类型
    from collections import Counter
    type_counts = Counter(msg[2] for msg in messages)
    print(f"[types] {dict(type_counts)}")

    # 提取图片 URL
    images = []
    seen_urls = set()

    for msg_id, ch_id, msg_type, content, timestamp in messages:
        try:
            data = json.loads(content) if content else {}
            url = ""

            # type=3: 图片消息
            if msg_type == 3:
                url = data.get("url", "")
            # type=1: 文本消息，提取 URL
            elif msg_type == 1:
                text = data.get("content", "")
                # 提取所有 URL
                urls = re.findall(r'https?://[^\s<>"\']+', text)
                for u in urls:
                    if 'gleezy' in u or 'fileproxy' in u or 'preview' in u:
                        if u not in seen_urls:
                            seen_urls.add(u)
                            images.append({
                                "url": u,
                                "source_channel": channels.get(ch_id, {}).get("name", ch_id),
                                "channel_id": ch_id,
                                "timestamp": timestamp,
                                "message_id": msg_id,
                            })
                continue

            if url and url not in seen_urls:
                seen_urls.add(url)
                # 构建完整 URL
                if url.startswith("file/"):
                    full_url = f"https://fileproxy.gleezy.net/api/v1/{url}"
                elif "fileproxy.gleezy.net" not in url and "gleezy.org" not in url:
                    full_url = f"https://fileproxy.gleezy.net/api/v1/{url}"
                else:
                    full_url = url

                images.append({
                    "url": full_url,
                    "source_channel": channels.get(ch_id, {}).get("name", ch_id),
                    "channel_id": ch_id,
                    "timestamp": timestamp,
                    "message_id": msg_id,
                })
        except Exception as e:
            pass

    print(f"[extracted] {len(images)} unique images")

    # 按频道统计
    ch_counts = Counter(img["source_channel"] for img in images)
    print("\n[channel distribution]:")
    for ch, cnt in ch_counts.most_common(10):
        print(f"  {cnt:4d}  {ch}")

    # 保存
    output = {
        "tag": "风俗习惯",
        "source": "GLEEZY PRO (ADB extracted)",
        "extracted_at": "2026-09-03",
        "total_unique": len(images),
        "images": images,
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[saved] {OUTPUT_JSON}")

    # 生成 CSV
    import csv
    csv_path = Path("moments_gleezy_adb.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["content", "visibility", "room_id", "image_urls"])
        writer.writeheader()
        for i in range(0, min(len(images), 20), 4):
            group = images[i:i+4]
            urls = ",".join(img["url"] for img in group)
            writer.writerow({
                "content": "分享一组美图给大家～喜欢的朋友扣 1 📸",
                "visibility": "0",
                "room_id": "",
                "image_urls": urls,
            })
    print(f"[saved] {csv_path} ({len(images)//4} posts)")

    conn.close()

if __name__ == "__main__":
    main()
