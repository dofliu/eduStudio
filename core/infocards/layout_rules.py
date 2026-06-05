"""規則式版型選擇器（從 infoCard services/layoutSelector.ts 收編，Phase C 兩階段大綱）。

純函式、零 API、可離線測：給「結構化內容描述」依 config/layouts.ts triggers 評分選版型，
校正 AI 的版型選擇。本批只移植大綱校正用到的規則引擎子集（不含 UI 的 userLayout 切換 /
preview helper）。triggers 表逐字對齊 layouts.ts。
"""
from __future__ import annotations

import re

# 版型 triggers（對齊 layouts.ts LAYOUTS；保留宣告順序給 tie-break）。
# 每筆：(id, is_structural, triggers)。triggers 鍵：keywords/requires_number/is_code/bullet_range/priority。
_LAYOUTS: list[tuple[str, bool, dict]] = [
    ("title_cover", True, {}),
    ("section_header", True, {}),
    ("bullet_list", False, {"bullet_range": (3, 5), "priority": 50}),
    ("text_and_image", False, {}),
    ("big_number", False, {"requires_number": True, "priority": 40}),
    ("quote", False, {"keywords": ["名言", "引用", "說過", "提到"], "priority": 60}),
    ("diagram_image", False, {}),
    ("conclusion", True, {}),
    ("two_column", False, {"keywords": ["比較", "優缺", "vs", "pros cons", "對比", "差異"], "priority": 30}),
    ("process_steps", False, {"keywords": ["步驟", "流程", "依序", "操作", "如何", "step", "process"], "priority": 20}),
    ("timeline", False, {"keywords": ["年份", "里程碑", "歷史", "發展", "沿革", "timeline"], "priority": 25}),
    ("chart_focus", False, {"keywords": ["數據", "統計", "佔比", "比例", "成長率"], "requires_number": True, "priority": 35}),
    ("full_image", False, {}),
    ("worked_example", False, {"keywords": ["推導", "計算", "解題", "範例", "代入", "example"], "priority": 15}),
    ("exercise", False, {"keywords": ["練習", "習題", "試求", "exercise", "problem"], "priority": 15}),
    ("code_block", False, {"is_code": True, "priority": 10}),
    ("swot_analysis", False, {"keywords": ["SWOT", "優勢", "劣勢", "機會", "威脅", "四象限"], "priority": 20}),
    ("pyramid_diagram", False, {"keywords": ["階層", "金字塔", "層級", "架構層次", "優先順序", "pyramid"], "priority": 20}),
    ("comparison_table", False, {"keywords": ["規格", "方案對比", "詳細對比", "比較表"], "priority": 28}),
]
_BY_ID = {lid: (struct, trig) for lid, struct, trig in _LAYOUTS}
_VALID = set(_BY_ID)


def is_valid_layout(value) -> bool:
    return isinstance(value, str) and value in _VALID


def _matches_keywords(text: str, keywords) -> bool:
    if not keywords:
        return False
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)


def _score_layout(trig: dict, *, title="", content="", has_numbers=False,
                  is_code=False, bullet_count=None) -> float:
    if not trig:
        return 0.0
    text = f"{title or ''}\n{content or ''}"
    score = 0.0
    if _matches_keywords(text, trig.get("keywords")):
        score += 10
    if trig.get("requires_number") and has_numbers:
        score += 6
    if trig.get("is_code") and is_code:
        score += 20
    br = trig.get("bullet_range")
    if br and bullet_count is not None and br[0] <= bullet_count <= br[1]:
        score += 4
    # priority 越小越優先 → 折成 0-3 分 tie-breaker（命中時才加）。
    if score > 0 and isinstance(trig.get("priority"), (int, float)):
        score += max(0.0, (100 - trig["priority"]) / 50)
    return score


def _detect_structural(slide_index, total_slides):
    if slide_index == 1:
        return "title_cover"
    if slide_index is not None and total_slides is not None and slide_index == total_slides:
        return "conclusion"
    return None


def pick_layout(*, slide_index=None, total_slides=None, title="", content="",
                has_numbers=False, is_code=False, bullet_count=None, ai_hint=None) -> str:
    structural = _detect_structural(slide_index, total_slides)
    if structural:
        return structural
    best_layout, best_score = "bullet_list", -1.0
    for lid, struct, trig in _LAYOUTS:
        if struct:
            continue
        score = _score_layout(trig, title=title, content=content, has_numbers=has_numbers,
                              is_code=is_code, bullet_count=bullet_count)
        if ai_hint == lid:
            score += 5
        if score > best_score:
            best_score, best_layout = score, lid
    return best_layout


def reconcile_layout(*, slide_index=None, total_slides=None, title="", content="",
                     has_numbers=False, is_code=False, bullet_count=None, ai_hint=None) -> str:
    """校正 AI 的版型選擇：規則訊號明確（命中分 ≥10）才覆蓋 aiHint，否則尊重 AI。"""
    kw = dict(slide_index=slide_index, total_slides=total_slides, title=title, content=content,
              has_numbers=has_numbers, is_code=is_code, bullet_count=bullet_count)
    if not ai_hint:
        return pick_layout(**kw)
    rule_choice = pick_layout(**kw)  # ai_hint=None 預設
    if rule_choice == ai_hint:
        return ai_hint
    _, rule_trig = _BY_ID.get(rule_choice, (False, {}))
    rule_score = _score_layout(rule_trig, title=title, content=content, has_numbers=has_numbers,
                              is_code=is_code, bullet_count=bullet_count)
    if rule_score >= 10:
        return rule_choice
    return ai_hint


_NUMBER_PATTERN = re.compile(r"\d{2,}|\d+(?:\.\d+)?\s*[%％]|\$\s*\d+|\d+(?:\.\d+)+")
_CODE_HINTS = ["```", "python", "matlab", "javascript", "typescript",
               "function ", "def ", "class ", " import ", "console.log", "#!/"]


def analyze_outline_slide(title: str, summary: str) -> dict:
    """從大綱純文字（title + summary）抽結構訊號供 reconcile_layout 校正。"""
    text = f"{title}\n{summary}"
    lower = text.lower()
    has_numbers = bool(_NUMBER_PATTERN.search(text))
    is_code = any(h in lower for h in _CODE_HINTS)
    separators = len(re.findall(r"[•・；;]", summary or ""))
    bullet_count = separators + 1 if separators > 0 else None
    return {"has_numbers": has_numbers, "is_code": is_code, "bullet_count": bullet_count}
