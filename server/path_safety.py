"""共用 path-traversal 防護 helper (S-3)。

各 route 過去各自寫「拒 / \\ .. 」字元檢查, 但只有 slides.py 有做 resolve 後的
containment 二次防護。集中成一個 safe_join, 統一「字元檢查 + resolve + 限定在 base 內」
三道, 避免端點各自漏掉某一道。

設計:
- 純粹做「把使用者碎片安全地接到固定 base 目錄下」, **不檢查存在性**(caller 自己決定
  404 還是建檔)。
- 違規一律 raise HTTPException(400), 讓 route 直接往外丟。
- base_dir 必須是程式控制的固定目錄, 不可由使用者輸入(否則防護無意義)。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, status


def _is_bad_part(part: str) -> bool:
    """單一路徑碎片是否危險: 空字串 / 含分隔符 / .. / 以 . 開頭(隱藏檔或相對逃脫)。"""
    return (
        not part
        or "/" in part
        or "\\" in part
        or ".." in part
        or part.startswith(".")
    )


def safe_join(base_dir: Path, *parts: str) -> Path:
    """把使用者提供的 *parts 安全地接到 base_dir 下並回傳 resolve 後的絕對路徑。

    三道防護:
      1. 每個碎片做字元檢查 (拒 `/` `\\` `..` 前導 `.` 與空字串)
      2. join 後 `.resolve()` 正規化 (連 symlink 一起解)
      3. 驗證結果仍 `relative_to(base_dir)` — resolve 後逃出 base 一律擋

    任一道失敗 → HTTPException(400)。不檢查檔案是否存在。
    """
    for part in parts:
        if _is_bad_part(part):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法路徑碎片")

    base_resolved = base_dir.resolve()
    target = base_resolved.joinpath(*parts).resolve()
    try:
        target.relative_to(base_resolved)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "路徑逃脫偵測")
    return target
