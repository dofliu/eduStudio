"""教學版型內容預算校正（從 infoCard services/slideContentBudget.ts 收編）。

純函式、零 API：教學版型（worked_example/exercise/code_block）在固定模板下 bulletPoints
空間有限，AI 偶爾超量。本模組只裁「數量」不裁「文字」（截斷公式/程式碼會破壞語意），
把 bulletPoints 裁到 config 定義的 bulletMax，讓渲染器拿到不溢出的資料。

bulletMax 對齊 infoCard config/layouts.ts limits：worked_example=6 / exercise=4 / code_block=5。
"""
from __future__ import annotations

# 教學版型 → bulletPoints 數量上限（對齊 layouts.ts limits.bulletMax）。
_TEACHING_BULLET_MAX = {
    "worked_example": 6,
    "exercise": 4,
    "code_block": 5,
}

TEACHING_LAYOUTS = frozenset(_TEACHING_BULLET_MAX)


def is_teaching_layout(layout: str) -> bool:
    return layout in TEACHING_LAYOUTS


def enforce_teaching_layout_budget_dict(slide: dict) -> dict:
    """對單張教學版型投影片 dict 套用 bulletMax，超量則裁切前 N 項（in-place 改 + 回傳）。

    非教學版型 / 無 bulletPoints / 未超量 → 原樣回傳。只裁數量不動文字與其他欄位。
    """
    bullet_max = _TEACHING_BULLET_MAX.get(slide.get("layout"))
    if bullet_max is None:
        return slide
    bullets = slide.get("bulletPoints")
    if isinstance(bullets, list) and len(bullets) > bullet_max:
        slide["bulletPoints"] = bullets[:bullet_max]
    return slide
