# -*- coding: utf-8 -*-
"""检查 GLEEZY PRO 各群中的图片等内容"""
import sqlite3
import json
import sys
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = Path("gleezy_dump/wk_ad580b8704fb47b1b9c46e4cbe7ccad9.db")

def main():
    if not DB_PATH.exists():
        print("[error] 数据库不存在，请先运行 fetch_gleezy_adb.py 导出")
        return 1

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. 频道统计
    cursor.execute("SELECT channel_id, channel_name, channel_type FROM channel")
    channels = {}
    for row in cursor.fetchall():
        channels[row[0]] = {
            "name": row[1] or "未知",
            "type": row[2],  # 1=私聊，2=群聊
        }

    print(f"[channels] 共 {len(channels)} 个频道")
    group_count = sum(1 for c in channels.values() if c["type"] == 2)
    pm_count = sum(1 for c in channels.values() if c["type"] == 1)
    print(f"  群聊: {group_count}, 私聊: {pm_count}")

    # 2. 消息统计
    cursor.execute("SELECT type, COUNT(*) FROM message GROUP BY type")
    msg_types = dict(cursor.fetchall())
    total_msgs = sum(msg_types.values())
    print(f"\n[messages] 共 {total_msgs} 条消息")
    type_names = {1: "文本", 2: "图片", 3: "图片", 4: "视频", 5: "视频", 2000: "机器人"}
    for t, cnt in msg_types.items():
        name = type_names.get(t, f"类型{t}")
        print(f"  {name}: {cnt}")

    # 3. 各群消息分布
    cursor.execute("""
        SELECT channel_id, type, COUNT(*)
        FROM message
        GROUP BY channel_id, type
        ORDER BY channel_id
    """)
    channel_msgs = {}
    for ch_id, msg_type, cnt in cursor.fetchall():
        if ch_id not in channel_msgs:
            channel_msgs[ch_id] = {}
        channel_msgs[ch_id][msg_type] = cnt

    print(f"\n[channel distribution]:")
    for ch_id, types in sorted(channel_msgs.items(), key=lambda x: -sum(x[1].values()))[:15]:
        ch_name = channels.get(ch_id, {}).get("name", ch_id)
        total = sum(types.values())
        imgs = types.get(3, 0) + types.get(2, 0)
        vids = types.get(4, 0) + types.get(5, 0)
        texts = types.get(1, 0)
        print(f"  {ch_name[:25]:25}  total={total:3d}  text={texts:2d}  img={imgs:2d}  vid={vids:2d}")

    # 4. 图片 URL 提取
    cursor.execute("SELECT channel_id, type, content, timestamp FROM message ORDER BY timestamp DESC")
    images = []
    seen_urls = set()
    for ch_id, msg_type, content, ts in cursor.fetchall():
        try:
            data = json.loads(content) if content else {}
            url = ""
            if msg_type in (3,):  # 图片
                url = data.get("url", "")
            elif msg_type in (4, 5):  # 视频
                url = data.get("url", "")
            elif msg_type == 1:  # 文本，提取 URL
                import re
                text = data.get("content", "")
                urls = re.findall(r'https?://[^\s<>"\']+', text)
                for u in urls:
                    if 'gleezy' in u or 'fileproxy' in u:
                        if u not in seen_urls:
                            seen_urls.add(u)
                            images.append({"url": u, "channel": ch_id})
                continue

            if url and url not in seen_urls:
                seen_urls.add(url)
                full_url = url
                if full_url.startswith("file/"):
                    full_url = f"https://fileproxy.gleezy.net/api/v1/{full_url}"
                images.append({
                    "url": full_url,
                    "channel": ch_id,
                    "type": "image" if msg_type == 3 else "video",
                })
        except:
            pass

    print(f"\n[images extracted] {len(images)} unique URLs")
    img_count = sum(1 for i in images if i["type"] == "image")
    vid_count = sum(1 for i in images if i["type"] == "video")
    print(f"  图片: {img_count}, 视频: {vid_count}")

    # 5. 缓存图片
    cache_db = Path("gleezy_dump/libCachedImageData.db")
    if cache_db.exists():
        cconn = sqlite3.connect(cache_db)
        ccursor = cconn.cursor()
        ccursor.execute("SELECT COUNT(*) FROM cacheObject")
        cache_count = ccursor.fetchone()[0]
        cconn.close()
        print(f"\n[cache] {cache_count} cached objects")

    conn.close()

    # 6. 与历史数据对比
    history_path = Path("sources/customs_images.json")
    if history_path.exists():
        try:
            with open(history_path, encoding="utf-8-sig") as f:
                history = json.load(f)
            hist_count = history.get("total_unique", 0)
            print(f"\n[historical data] {hist_count} images from previous extraction")
            print(f"[status] Current DB has {len(images)} images, historical has {hist_count}")
            if hist_count > len(images):
                print(f"[note] Current simulator data is a subset. Using historical data for publishing.")
        except:
            pass

    return 0

if __name__ == "__main__":
    sys.exit(main())
