#!/usr/bin/env python3
"""
caption_dedupe.py — 发帖文案跨批次去重工具（整个仓库统一复用）

背景：
    从固定文案池/模板池选文案的脚本（run_*.py、caption_multilang.py 等）在每次
    运行时索引/随机种子会重新开始，导致跨批次发布完全相同的文案。本模块提供一套
    统一的持久化去重机制，让所有文本类发帖脚本共用，避免任何文案重复。

核心机制：
    - JSON 账本持久化「已发布过的最终文案文本」（跨批次保留）。
    - pick_caption() 从候选文案中选一条未用过的；全部用过时加序号后缀兜底，
      保证永不产出完全相同的文案。

用法：
    from caption_dedupe import load_used_captions, save_used_captions, pick_caption

    used = load_used_captions("state/seen_xxx_captions.json")

    # 1) 固定文案池（无占位符）
    caption = pick_caption(DAY_CAPTIONS, used)

    # 2) 模板池（带 {title}/{tag} 占位符）：先格式化，再从候选中选未用过的
    candidates = [t.format(title=title, tag=tag) for t in templates]
    caption = pick_caption(candidates, used)

    save_used_captions(used, "state/seen_xxx_captions.json")
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Set, Union


def load_used_captions(dedupe_file: Union[str, Path]) -> Set[str]:
    """读取已用文案账本；文件不存在或损坏时返回空集合。"""
    p = Path(dedupe_file)
    if not p.exists():
        return set()
    try:
        return {str(x) for x in json.loads(p.read_text(encoding="utf-8"))}
    except Exception:  # noqa: BLE001
        return set()


def save_used_captions(used: Iterable[str], dedupe_file: Union[str, Path]) -> None:
    """把已用文案集合写回账本（排序后按 JSON 持久化）。"""
    p = Path(dedupe_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(set(used)), ensure_ascii=False, indent=2), encoding="utf-8")


def pick_caption(candidates: Iterable[str], used: Set[str]) -> str:
    """从候选文案中选一条未用过的，并将其标记为已用。

    - 优先返回候选里第一条不在 ``used`` 中的文案；
    - 候选全部用过时，给第一条候选加 `` (2)`` `` (3)`` … 序号后缀兜底，
      保证返回的文案一定与已用文案不同。
    """
    cands = [str(c) for c in candidates]
    for cap in cands:
        if cap not in used:
            used.add(cap)
            return cap
    base = cands[0]
    i = 2
    while f"{base} ({i})" in used:
        i += 1
    cap = f"{base} ({i})"
    used.add(cap)
    return cap
