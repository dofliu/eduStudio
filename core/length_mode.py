"""影片長度模式 — lecture (授課用 1-3 hr) vs quick (YT 快速講解 ≤15 min).

問題: 既有 outliner / scriptor prompts 硬寫「4~6 章, 8~15 分鐘」, 對「想做
1-3 小時授課影片」沒辦法. 加長度模式讓使用者選.

設計:
- LENGTH_PRESETS dict 定義各模式的數量參數 (sections / slides / narration 字數)
- outliner / scriptor 把 preset 套進 prompt template 的 {sections_range} 等
  placeholder, 讓 Gemini 依模式調整輸出規模
- 預設 "quick" — 保持既有行為 (現有 prompt 規格就是 quick 範圍).
  新加 "lecture" 走長版 (10-18 章, 每章 6-12 張投影片, 150-250 字 narration)

不在這裡決定:
- exam_pdf 不適用 (考卷由 PDF 題數決定影片數, length_mode 無意義)
- slides_pdf 不適用 (頁數由 PDF 決定)
- 兩者 caller 都不會傳 length_mode 進來, 我們只做 repo / document / url 的
"""
from __future__ import annotations

from typing import Literal


LengthMode = Literal["lecture", "quick"]


# 各模式參數 — 把硬寫的數字抽出來, prompt template 用 {} 拉
LENGTH_PRESETS: dict[str, dict[str, str | int]] = {
    "quick": {
        # YT 快速講解, 對應現有 prompt 行為 (保 backwards compat)
        "target_minutes": "8~15",
        "sections_range": "4~6",
        "slides_per_section_range": "5~10",
        "narration_chars_range": "100~200",
        "narration_seconds_range": "30~60",
        # 給 prompt 上方一段提示文字, 加強 Gemini 對「快速」的理解
        "length_directive": "請設計一份 8~15 分鐘的快速講解, 以扼要傳達核心資訊為主.",
    },
    "lecture": {
        # 詳細授課版, 1-3 hr 教學影片
        "target_minutes": "60~180",
        "sections_range": "8~15",
        "slides_per_section_range": "6~12",
        "narration_chars_range": "180~280",
        "narration_seconds_range": "60~120",
        "length_directive": (
            "請設計一份 60~180 分鐘的詳細授課影片, 適合上課使用. "
            "需要充分展開每個概念, 給範例 / 推導過程 / 對照, 讓學生跟得上."
        ),
    },
}


def preset(mode: LengthMode | str | None) -> dict:
    """取對應 mode 的 preset. 不認識的 mode 退到 quick (保預設行為)."""
    if mode and mode in LENGTH_PRESETS:
        return LENGTH_PRESETS[mode]
    return LENGTH_PRESETS["quick"]
