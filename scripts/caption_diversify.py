#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
caption_diversify.py — 帖子文案差异化处理器（消除重复，确保每帖独立）

读取 moments CSV，用 caption_rewriter 为每行生成独立的不重复文案，
替换原始 content 列，确保发帖内容零雷同。

设计为发帖流水线的最后一步（在 caption_multilang 之后、publish 之前）：
    fetch → caption_multilang → caption_diversify → publish

也可独立使用，直接替换任何 CSV 的 content 列。

用法：
    # 基本用法：读入CSV，差异化所有文案，写出新CSV
    py -3 scripts/caption_diversify.py --input moments.csv --output moments_diverse.csv --lang en

    # 指定场景（影响文案风格）
    py -3 scripts/caption_diversify.py --input moments.csv --output out.csv --lang ms --scene travel

    # 与现有管线集成（管道模式，覆盖输入文件）
    py -3 scripts/caption_diversify.py --input moments.csv --output moments.csv --lang en
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from caption_rewriter import CaptionRewriter, REWRITE_TEMPLATES  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="帖子文案差异化处理器 — 确保每帖内容不重复",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("--input", required=True, help="输入 moments CSV")
    ap.add_argument("--output", required=True, help="输出 CSV（可与 input 相同，覆盖）")
    ap.add_argument("--lang", default="en", choices=list(REWRITE_TEMPLATES.keys()) + ["auto"],
                    help="文案语言（auto=读取CSV中_lang列）")
    ap.add_argument("--scene", default="travel", help="场景类型")
    args = ap.parse_args()

    # 读取
    with open(args.input, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    if not rows:
        print("[diversify] 空文件，跳过"); return 0

    # 检查原始重复度
    original_contents = [r.get('content', '') for r in rows]
    original_unique = len(set(original_contents))
    print(f"[diversify] 输入: {len(rows)} 帖, 原始唯一: {original_unique}/{len(rows)}")

    # 按语言分组生成
    if args.lang == "auto":
        # 从 _lang 列读取每行语言
        lang_groups = {}
        for i, row in enumerate(rows):
            lang = row.get('_lang', 'en') or 'en'
            if lang not in lang_groups:
                lang_groups[lang] = []
            lang_groups[lang].append(i)
    else:
        lang_groups = {args.lang: list(range(len(rows)))}

    # 为每组语言生成唯一文案
    for lang, indices in lang_groups.items():
        effective_lang = lang if lang in REWRITE_TEMPLATES else "en"
        rw = CaptionRewriter(lang=effective_lang, scene=args.scene)
        captions = rw.generate(count=len(indices))
        for j, idx in enumerate(indices):
            rows[idx]['content'] = captions[j]

    # 验证
    new_contents = [r.get('content', '') for r in rows]
    new_unique = len(set(new_contents))

    # 写出
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"[diversify] 输出: {len(rows)} 帖, 唯一: {new_unique}/{len(rows)} "
          f"{'✓' if new_unique == len(rows) else '⚠'}")
    print(f"[diversify] → {args.output}")
    return 0


if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.exit(main())
