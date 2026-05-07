"""Adapters — 把不同來源 (repo / document / url) 轉成統一的 raw_content
給下游 outliner / scriptor 使用。

各 adapter 輸出統一帶 source_kind 區分:
- "repo"     -> repo 資料夾 (檔樹 + key_files, 給 code-walkthrough 用)
- "document" -> PDF / MD / TXT 單檔 (long-form text)
- "url"      -> 靜態 HTML 文章 (long-form text)
"""
from __future__ import annotations

from .document import scan_document
from .repo import scan_repo
from .url import scan_url

__all__ = ["scan_repo", "scan_document", "scan_url"]
