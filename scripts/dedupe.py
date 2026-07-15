#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dedupe.py — 统一图片/内容去重管理器

设计目标：
  - 统一所有采集脚本的去重文件格式和操作接口
  - 两阶段去重：采集标记 pending → 发布成功后确认 used
  - 发布失败的 pending 可自动释放（超时回收或手动释放）
  - 跨脚本互通：多个采集脚本可读同一去重档

文件格式（JSON）：
  {
    "used": ["id1", "id2", ...],         # 已成功发布，永久标记
    "pending": {                          # 已采集但未确认发布
      "id3": "2026-07-15T12:00:00",      # 值为采集时间戳
      "id4": "2026-07-15T12:01:00"
    },
    "meta": {
      "last_updated": "2026-07-15T12:00:00",
      "total_used": 123,
      "total_pending": 5
    }
  }

用法：
  from dedupe import DedupeManager

  dm = DedupeManager("state/seen_beauty.json")
  # 采集时：检查是否可用 + 标记为 pending
  if dm.is_available("turismo:abc:001"):
      dm.mark_pending("turismo:abc:001")
  # 发布成功后：确认为 used
  dm.confirm("turismo:abc:001")
  # 发布失败：释放回可用池
  dm.release("turismo:abc:001")
  # 保存
  dm.save()

兼容旧格式：
  自动识别并迁移以下旧格式：
  - 纯 JSON 数组 [...]
  - {"slugs": [...]}
  - {"ids": [...], "urls": [...]}
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


class DedupeManager:
    """统一去重管理器：两阶段标记（pending → used）+ 超时释放。"""

    PENDING_EXPIRE_HOURS = 24  # pending 超时时间（小时），超过自动释放

    def __init__(self, path: str | Path, auto_load: bool = True):
        self.path = Path(path)
        self.used: set[str] = set()
        self.pending: dict[str, str] = {}  # id → timestamp
        if auto_load and self.path.exists():
            self._load()

    def _load(self):
        """加载去重档，兼容所有旧格式。"""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return

        if isinstance(data, list):
            # 旧格式：纯数组
            self.used = set(data)
        elif isinstance(data, dict):
            if "used" in data:
                # 新格式
                self.used = set(data.get("used", []))
                self.pending = data.get("pending", {})
            elif "slugs" in data:
                # 旧格式：{"slugs": [...]}
                self.used = set(data["slugs"])
            elif "ids" in data or "urls" in data:
                # 旧格式：{"ids": [...], "urls": [...]}
                self.used = set(data.get("ids", []))
                self.used.update(data.get("urls", []))
            else:
                # 未知 dict 格式，尝试把所有 list 值合并
                for v in data.values():
                    if isinstance(v, list):
                        self.used.update(v)

        # 清理过期 pending
        self._expire_pending()

    def _expire_pending(self):
        """清除超时的 pending 条目（释放回可用池）。"""
        if not self.pending:
            return
        now = datetime.now()
        expired = []
        for key, ts_str in self.pending.items():
            try:
                ts = datetime.fromisoformat(ts_str)
                if now - ts > timedelta(hours=self.PENDING_EXPIRE_HOURS):
                    expired.append(key)
            except (ValueError, TypeError):
                expired.append(key)
        for key in expired:
            del self.pending[key]
        if expired:
            print(f"[dedupe] 释放 {len(expired)} 个过期 pending 条目")

    def is_available(self, key: str) -> bool:
        """检查一个 ID/URL/slug 是否可用（既不在 used 也不在 pending 中）。"""
        return key not in self.used and key not in self.pending

    def is_used(self, key: str) -> bool:
        """检查是否已被永久标记为已用。"""
        return key in self.used

    def mark_pending(self, key: str):
        """标记为 pending（已采集，等待发布确认）。"""
        if key not in self.used:
            self.pending[key] = datetime.now().isoformat(timespec="seconds")

    def mark_pending_batch(self, keys: Iterable[str]):
        """批量标记为 pending。"""
        ts = datetime.now().isoformat(timespec="seconds")
        for key in keys:
            if key not in self.used:
                self.pending[key] = ts

    def confirm(self, key: str):
        """确认发布成功，从 pending 移到 used。"""
        self.pending.pop(key, None)
        self.used.add(key)

    def confirm_batch(self, keys: Iterable[str]):
        """批量确认发布成功。"""
        for key in keys:
            self.pending.pop(key, None)
            self.used.add(key)

    def release(self, key: str):
        """释放 pending 条目（发布失败，允许后续重新采集）。"""
        self.pending.pop(key, None)

    def release_batch(self, keys: Iterable[str]):
        """批量释放。"""
        for key in keys:
            self.pending.pop(key, None)

    def save(self):
        """保存去重档到文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "used": sorted(self.used),
            "pending": self.pending,
            "meta": {
                "last_updated": datetime.now().isoformat(timespec="seconds"),
                "total_used": len(self.used),
                "total_pending": len(self.pending),
            }
        }
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    @property
    def stats(self) -> str:
        return f"used={len(self.used)} pending={len(self.pending)}"

    # ---- 兼容旧接口 ----

    def has_id(self, key: str) -> bool:
        """兼容 sources.py 的 has_id 回调。"""
        return not self.is_available(key)

    def has_url(self, url: str) -> bool:
        """兼容 sources.py 的 has_url 回调。"""
        return not self.is_available(url)
