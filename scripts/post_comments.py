#!/usr/bin/env python3
"""
post_comments.py — 自然口吻评论发布工具

在指定帖子下用不同用户发表评论，消除 AI 感。

用法：
    py -3 scripts/post_comments.py \
        --post-id 739388370119036928 \
        --commenters accounts.csv \
        --tokens result/tokens.json \
        --count 3

    py -3 scripts/post_comments.py \
        --batch comments_batch.csv \
        --tokens result/tokens.json
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# ============================================================
# 评论语料库 — 按话题分类，消除 AI 感
# ============================================================
COMMENT_BANKS = {
    "tech_ai": [
        "真的吗？我还在用老方法……求推荐工具 😂",
        "试了一下确实好用，感谢分享",
        "同感！！我们组也在推这个，效率提升太明显了",
        "观望了好久不敢用，看完你这帖子决定试一下",
        "现在不用AI感觉都跟不上节奏了",
        "我们公司还在纠结要不要上，看到你这数据我明天就去push老板",
        "确实，我之前也是半信半疑，用了两个月回不去了",
        "好奇问下，收费吗？免费的话我也整一个",
    ],
    "finance": [
        "上周刚入了一点，瑟瑟发抖中……",
        "我妈也跟我说这个了，中国大妈的信息源比我快 😅",
        "已经亏了20%了，心态很稳（装的）",
        "观望中，等回调再上车",
        "这时候入手会不会太高了",
        "跟着你买了点，赚了请你喝奶茶",
        "长期看好，短期波动无所谓",
    ],
    "entertainment": [
        "我也刚看完！！第二季真的比第一季好看太多了",
        "还没看，被你这么一说今晚就开追",
        "同感！看完之后又剧荒了 😭",
        "票根本抢不到啊，你们都怎么抢到的……",
        "去了现场，氛围真的炸裂",
        "张若昀这部演技确实在线",
        "看完大结局缓了好几天",
        "这部剧我二刷了，细节太多了",
    ],
    "tech_device": [
        "续航这么强？我的旧手机半天就没电了……",
        "折叠屏太重了吧，单手操作方便吗",
        "刚下单了，期待！",
        "用了三个月，屏幕折痕还行吗",
        "在纠结买哪个颜色，纠结了一周了",
        "信号怎么样？地铁里能用吗",
    ],
    "lifestyle": [
        "同款！我也在用这个，真的香",
        "种草了，周末去看看",
        "看完你这个我决定不纠结了，冲",
        "实用贴，收藏了",
        "好巧，我也刚搬完家，累死了",
        "羡慕，我也想要这样的生活",
        "简单真实，喜欢这种分享",
    ],
    "general": [
        "涨知识了，谢谢分享",
        "第一次听说，有点意思",
        "感觉还不错诶",
        "收藏了，以后用得上",
        "说得好，就是这个理",
        "今天的心情跟你这个帖子很搭",
    ],
}

# ============================================================
# 核心函数
# ============================================================

def load_tokens(path: str) -> dict[str, str]:
    """加载已保存的 token 映射 {email: token}。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_accounts(path: str) -> list[dict]:
    """加载账号 CSV（序号,昵称,邮箱,密码）。"""
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def pick_comment(topic: str) -> str:
    """从语料库随机选一条自然评论。"""
    bank = COMMENT_BANKS.get(topic, COMMENT_BANKS["general"])
    return random.choice(bank)


def post_comment(token: str, post_id: int, content: str, feed_api: str) -> bool:
    """在指定帖子下发表评论。"""
    base = feed_api.replace("/api/v1/moments/", "").replace("/api/v1/moments", "")
    url = f"{base}/api/v1/comments"
    r = requests.post(url,
        json={"moment_id": post_id, "content": content},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=15)
    return r.status_code in (200, 201) and r.json().get("code") == 0


# ============================================================
# 命令行入口
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="自然口吻评论发布工具")
    ap.add_argument("--post-id", type=int, help="目标帖子 ID（单帖模式）")
    ap.add_argument("--commenters", default="accounts.csv", help="评论者账号 CSV")
    ap.add_argument("--tokens", default="result/tokens.json", help="已保存的 token JSON")
    ap.add_argument("--count", type=int, default=2, help="评论条数（单帖模式）")
    ap.add_argument("--topic", default="general", help="话题类型: tech_ai/finance/entertainment/tech_device/lifestyle/general")
    ap.add_argument("--text", help="手动指定评论内容（覆盖随机生成）")
    ap.add_argument("--batch", help="批量评论 CSV（post_id,email,topic,text）")
    ap.add_argument("--delay", type=float, default=5.0, help="评论间隔秒数")
    ap.add_argument("--feed-api", default="https://feed-api.xxai.com/api/v1/moments/")
    args = ap.parse_args()

    tokens = load_tokens(args.tokens)
    print(f"[Token] 加载 {len(tokens)} 个 token")

    if args.batch:
        # 批量模式
        with open(args.batch, encoding="utf-8-sig") as f:
            tasks = list(csv.DictReader(f))
        print(f"[Batch] {len(tasks)} 条评论任务")
        success = 0
        for i, t in enumerate(tasks):
            email = t.get("email", "").strip()
            token = tokens.get(email)
            if not token:
                print(f"  [{i+1}] {email} — 无token，跳过")
                continue
            text = (t.get("text") or t.get("content") or "").strip()
            if not text:
                topic = t.get("topic", "general").strip()
                text = pick_comment(topic)
            pid = int(t.get("post_id", 0))
            ok = post_comment(token, pid, text, args.feed_api)
            status = "OK" if ok else "FAIL"
            print(f"  [{i+1}] {t.get('nickname',email)} → {pid} {status}")
            if ok:
                success += 1
            if i < len(tasks) - 1:
                time.sleep(args.delay)
        print(f"\n[Result] {success}/{len(tasks)}")
        return 0 if success > 0 else 1

    # 单帖模式
    if not args.post_id:
        print("需要 --post-id 或 --batch")
        return 1

    commenters = load_accounts(args.commenters)
    random.shuffle(commenters)
    selected = commenters[:args.count]

    print(f"[Target] post_id={args.post_id}")
    success = 0
    for i, c in enumerate(selected):
        email = (c.get("邮箱") or c.get("email") or "").strip()
        token = tokens.get(email)
        if not token:
            print(f"  [{i+1}] {c.get('昵称','?')} — 无token，跳过")
            continue
        text = args.text if args.text else pick_comment(args.topic)
        ok = post_comment(token, args.post_id, text, args.feed_api)
        status = "OK" if ok else "FAIL"
        print(f"  [{i+1}] {c.get('昵称',email)}: \"{text[:40]}...\" {status}")
        if ok:
            success += 1
        if i < len(selected) - 1:
            time.sleep(args.delay)
    print(f"\n[Result] {success}/{len(selected)}")
    return 0 if success > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
