"""E1-2 image frame resolver — slide.image_frames list 拆解 + 進度對應.

對應 docs/dynamic-visual-assets-design.md E1 候選 A (PNG frame 序列 MVP).
schema 欄位 (E1-1 已落地): step.image_frames = list[dict] | None, 每筆含:
    - path: str — PNG 路徑 (絕對 / 相對 caller 已 resolve)
    - display_ratio: float — 該 frame 顯示到的累進佔比 (0.0~1.0)

舉例 (一個 step 有 3 個 frame 漸進顯示):
    [
      {"path": "f1.png", "display_ratio": 0.33},  # 0~33% 期間顯示
      {"path": "f2.png", "display_ratio": 0.66},  # 33~66% 期間顯示
      {"path": "f3.png", "display_ratio": 1.0},   # 66~100% 期間顯示
    ]

設計原則:
- 純函式, 0 PIL / 0 ffmpeg 依賴. renderer / build_clip 才負責真畫.
- graceful fallback — 路徑壞 / display_ratio 越界 / 重複條目 / 非 list →
  靜默過濾, 不噴 error 也不擋上游流程.
- terminal_frame() 給「一步一張 PNG」過渡期路徑用 (build_clip 還沒接
  frame 序列前, SlideRenderer 拿最終 frame 當靜態圖). 真 frame 序列
  渲染等 E1-3/build_clip refactor.
- require_file_exists 預設 True (renderer 用); 給 review UI 提案階段
  顯示時可關 (frame 還沒產出來也要先預覽列表).
"""
from __future__ import annotations

from pathlib import Path


def valid_frames(
    image_frames: object,
    *,
    require_file_exists: bool = True,
) -> list[dict]:
    """過濾並排序 image_frames list, 回 [{path, display_ratio}, ...].

    過濾規則:
    - 非 list / None / [] → 回 []
    - 條目非 dict / 缺 path → 跳過
    - display_ratio 非數值 / <=0 / >1 → 跳過
    - require_file_exists=True 時, 檔案不存在 → 跳過
    - 同 display_ratio 重複 → 保留最後一筆 (caller 較新覆蓋較舊)

    回傳 list 依 display_ratio 升冪排序, 方便 select_frame 二分.
    """
    if not isinstance(image_frames, list) or not image_frames:
        return []
    cleaned: dict[float, dict] = {}
    for entry in image_frames:
        if not isinstance(entry, dict):
            continue
        path_str = entry.get("path")
        if not path_str or not isinstance(path_str, str):
            continue
        ratio_raw = entry.get("display_ratio")
        try:
            ratio = float(ratio_raw)
        except (TypeError, ValueError):
            continue
        if not (0.0 < ratio <= 1.0):
            continue
        if require_file_exists and not Path(path_str).exists():
            continue
        cleaned[ratio] = {"path": path_str, "display_ratio": ratio}
    return [cleaned[r] for r in sorted(cleaned)]


def select_frame(
    image_frames: object,
    progress: float,
    *,
    require_file_exists: bool = True,
) -> dict | None:
    """根據 progress (0.0~1.0) 選當下該顯示的 frame.

    語意: display_ratio 是「該 frame 顯示到的累進佔比上限」, 第 i 個 frame
    覆蓋 (frames[i-1].display_ratio, frames[i].display_ratio] 區間.

    progress 在 0 之前 → 回第一個 frame (含小於最小 display_ratio 的區段).
    progress 在最後 frame display_ratio 之後 (含等於 1.0) → 回最後一個 frame.
    沒有有效 frame → 回 None.
    """
    frames = valid_frames(image_frames, require_file_exists=require_file_exists)
    if not frames:
        return None
    # clamp progress to [0, 1]
    p = max(0.0, min(1.0, float(progress)))
    for f in frames:
        if p <= f["display_ratio"]:
            return f
    return frames[-1]


def terminal_frame(
    image_frames: object,
    *,
    require_file_exists: bool = True,
) -> dict | None:
    """回最後一個 (display_ratio 最大) frame.

    給 build_clip 還沒接 frame 序列前的過渡期 SlideRenderer 用 — 一步一張
    PNG 時, 拿最終 frame 當靜態圖 (敘述跑完留下完整圖, 對閱聽者直覺最佳).
    """
    frames = valid_frames(image_frames, require_file_exists=require_file_exists)
    return frames[-1] if frames else None


def frame_count(
    image_frames: object,
    *,
    require_file_exists: bool = True,
) -> int:
    """回有效 frame 數 (review UI 顯示「這頁有 N frame」用)."""
    return len(valid_frames(image_frames, require_file_exists=require_file_exists))


def summarize_for_deck(
    deck: dict,
    *,
    require_file_exists: bool = True,
) -> dict[str, dict]:
    """掃整個 deck 所有 slide.image_frames, 回傳 {slide_id: summary}.

    給 E1-4 review UI「frame preview 縮圖列」批次預覽用 — 一次跑完所有 slide,
    UI 不需要對每個 slide 分別打 API call. 純函式 0 PIL / 0 ffmpeg 依賴, 結
    果可序列化成 JSON 直接給前端. 對應 iter 106 icon_picker.suggest_for_deck
    pattern.

    Args:
        deck: 已 normalize_deck 過的 dict (有 sections[].slides[].image_frames).
        require_file_exists: True (預設) 走渲染端嚴格模式 (檔案不在的 frame
            算 invalid). False 給 review UI 提案階段 (frame 尚未產出來也要
            列在預覽).

    Returns:
        dict[str, dict]. Key 是 slide.id (normalize_deck 保證有);
        Value = {"count": int, "terminal_path": str | None, "has_frames": bool}.
        沒 image_frames 也保留 {"count": 0, "terminal_path": None,
        "has_frames": False} — 給 UI 知道「這 slide 真的沒 frame」, 跟「這
        slide 沒掃到」做出區別.
        Slide 缺 id 跳過 (防呆, normalize_deck 後不該發生).
    """
    result: dict[str, dict] = {}
    for section in deck.get("sections", []) or []:
        for slide in section.get("slides", []) or []:
            slide_id = slide.get("id") or ""
            if not slide_id:
                continue
            frames = valid_frames(
                slide.get("image_frames"),
                require_file_exists=require_file_exists,
            )
            result[slide_id] = {
                "count": len(frames),
                "terminal_path": frames[-1]["path"] if frames else None,
                "has_frames": bool(frames),
            }
    return result
