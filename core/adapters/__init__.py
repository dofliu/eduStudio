"""Adapters — 把不同來源 (repo / pdf / url / md / txt) 轉成統一的 raw_content.json
給下游 outliner / scriptor 使用。

PR-2b-i 只實作 repo adapter, 其他類型留給後續。
"""
from __future__ import annotations

from .repo import scan_repo

__all__ = ["scan_repo"]
