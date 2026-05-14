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
        # YT 快速講解, ≤15 分鐘.
        # iter 46: 收緊範圍 — 實測用戶選 quick 拿到 5 章 × 7-9 slides × 200 字
        # narration = 34-43 分鐘. LLM 看到「4-6」「5-10」會取中上限.
        # 改成更窄的下限範圍逼 LLM 取小.
        "target_minutes": "8~15",
        "sections_range": "3~4",
        "slides_per_section_range": "4~5",
        "narration_chars_range": "80~120",
        "narration_seconds_range": "20~35",
        # narration 字數硬上限 (整份), 給 prompt 算總預算用
        "total_narration_budget_chars": 2500,
        "length_directive": (
            "★ 硬上限: 整份影片 ≤ 15 分鐘. 全部 narration 加總 ≤ 2500 字. "
            "請先估算總字數預算後再分章, 寧可短不可長. 不要為了補章節數而灌水."
        ),
    },
    "lecture": {
        # 詳細授課版, 1-3 hr 教學影片
        "target_minutes": "60~180",
        "sections_range": "8~15",
        "slides_per_section_range": "6~12",
        "narration_chars_range": "180~280",
        "narration_seconds_range": "60~120",
        "total_narration_budget_chars": 20000,
        "length_directive": (
            "請設計一份 60~180 分鐘的詳細授課影片, 適合上課使用. "
            "需要充分展開每個概念, 給範例 / 推導過程 / 對照, 讓學生跟得上. "
            "整份 narration 字數預算約 20000 字."
        ),
    },
}


def preset(mode: LengthMode | str | None) -> dict:
    """取對應 mode 的 preset. 不認識的 mode 退到 quick (保預設行為)."""
    if mode and mode in LENGTH_PRESETS:
        return LENGTH_PRESETS[mode]
    return LENGTH_PRESETS["quick"]
