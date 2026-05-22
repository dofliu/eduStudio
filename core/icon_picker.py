"""E2-3 icon picker — narration keyword grep → manifest 對照 → overlay 指令.

對應 docs/dynamic-visual-assets-design.md E2 候選 A (keyword grep MVP).
純文字 grep, 0 LLM call, 0 cost — 給 review UI 「自動建議 icon」列用,
人工確認後才進 slide_renderer alpha_composite (E2-5).

設計原則:
- graceful fallback — SVG 檔不在 (E2-2 還沒產 / 例外被刪) 該 entry 跳過,
  不噴 error, 不阻擋既有流程
- 不可繞 require_review=True — 此模組純建議, 真正進渲染前由 review UI 勾選
- 結果可解釋 — IconMatch 帶 matched_keyword, 給 UI 顯示「為什麼建議」
- case-insensitive — 容忍用戶 narration 寫 "pid" 對應 manifest "PID"
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.config import PROJECT_ROOT


ICON_LIBRARY_ROOT = PROJECT_ROOT / "assets" / "icon_library"
MANIFEST_PATH = ICON_LIBRARY_ROOT / "manifest.json"


@dataclass(frozen=True)
class IconMatch:
    """Icon 建議結果. 給 review UI 顯示 + 渲染端 overlay 用.

    matched_keyword 帶第一個命中的詞 (給「為什麼建議這個 icon?」說明).
    file_exists=False 表 SVG 檔還沒進 repo (E2-2 未完成或例外被刪),
    渲染端該跳過 (graceful fallback).
    """

    key: str
    icon_path: Path
    matched_keyword: str
    position: str
    size_ratio: float
    domain: str
    file_exists: bool


def load_manifest(path: Path | None = None) -> dict:
    """讀 manifest.json 原始 dict. 不快取 — 測試 / 熱載入方便."""
    target = path or MANIFEST_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def pick_icons(
    narration: str,
    *,
    manifest_path: Path | None = None,
    library_root: Path | None = None,
    max_icons: int = 3,
    require_file_exists: bool = True,
) -> list[IconMatch]:
    """掃 narration, 回傳 keyword 命中的 icon 建議列表.

    Args:
        narration: 一段 slide 的口語 narration (預期 60~200 字)
        manifest_path: 自訂 manifest 路徑 (測試用), 預設 MANIFEST_PATH
        library_root: 自訂 library root (測試用), 預設 ICON_LIBRARY_ROOT
        max_icons: 同段 narration 最多回幾個 icon. 預設 3, 避免畫面太雜
        require_file_exists: True (預設) 過濾掉 SVG 檔不存在的 entry.
            False 給 review UI「提案階段就顯示, 渲染前再過濾」用.

    Returns:
        IconMatch list, 同一 entry 只回一筆, 至多 max_icons 個.
        Order: 按 manifest 中 entry 出現順序 (manifest 順序意味 priority).
        narration 空 / 非 str / 沒命中 → []
    """
    if not isinstance(narration, str) or not narration.strip():
        return []

    manifest = load_manifest(manifest_path)
    root = library_root or ICON_LIBRARY_ROOT
    narration_lc = narration.lower()

    matches: list[IconMatch] = []
    for key, entry in manifest.get("icons", {}).items():
        # 找第一個命中的 keyword (case-insensitive substring 即可,
        # manifest 的 test_no_duplicate_keyword_across_entries 保證 keyword 跨 entry 唯一)
        hit_kw: str | None = None
        for kw in entry["keywords"]:
            if kw.lower() in narration_lc:
                hit_kw = kw
                break
        if hit_kw is None:
            continue

        icon_path = root / entry["icon"]
        exists = icon_path.exists()
        if require_file_exists and not exists:
            continue

        matches.append(
            IconMatch(
                key=key,
                icon_path=icon_path,
                matched_keyword=hit_kw,
                position=entry["position"],
                size_ratio=float(entry["size_ratio"]),
                domain=entry["domain"],
                file_exists=exists,
            )
        )

        if len(matches) >= max_icons:
            break

    return matches


def suggest_for_deck(
    deck: dict,
    *,
    manifest_path: Path | None = None,
    library_root: Path | None = None,
    max_icons: int = 3,
    require_file_exists: bool = True,
) -> dict[str, list[IconMatch]]:
    """掃整個 deck 所有 slide narration, 回傳 {slide_id: IconMatch list}.

    給 E2-6 review UI「自動建議 icon 勾選列」批次預覽用 — 一次跑完所有 slide,
    UI 不需要對每個 slide 分別打 API call. 跟 pick_icons 同樣 0 LLM call /
    0 cost, 純文字 grep.

    Args:
        deck: 已 normalize_deck 過的 dict (有 sections[].slides[].narration).
        manifest_path / library_root / max_icons / require_file_exists:
            同 pick_icons, 一律透傳給每一個 slide 的 call.

    Returns:
        dict[str, list[IconMatch]]. Key 是 slide.id (normalize_deck 保證有);
        Value 是該 slide narration 的建議 icon list. 沒命中也保留空 list —
        給 UI 知道「這 slide 真的沒建議」, 跟「這 slide 沒掃到」做出區別.
        Slide 缺 id 跳過 (防呆, normalize_deck 後不該發生).
    """
    result: dict[str, list[IconMatch]] = {}
    for section in deck.get("sections", []) or []:
        for slide in section.get("slides", []) or []:
            slide_id = slide.get("id") or ""
            if not slide_id:
                continue
            narration = slide.get("narration") or ""
            result[slide_id] = pick_icons(
                narration,
                manifest_path=manifest_path,
                library_root=library_root,
                max_icons=max_icons,
                require_file_exists=require_file_exists,
            )
    return result
