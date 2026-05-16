"""C1 iter 79: narration 長度驗證器.

問題: Gemini 偶爾把 narration 寫太長, 超出 length_mode 預算 (實測截斷率
~22% on quick mode). 字幕帶 + TTS 都會被卡.

治本策略 (本檔案是 step 1):
  1. 後處理驗證 (本檔案): 渲染前掃 deck.json, 統計每張 slide narration
     字數, 跟 length_mode preset 對照, 超出就 log warning + 標記.
  2. Prompt 強化 (見 prompts/*.txt iter 79): 在 LLM call 前加更明確
     字數約束 + 範例.

本檔案不自動截斷 / retry — 截斷會破壞語意, retry 燒 API quota. 改用
「flag + 用戶手動調」: review 階段 UI 顯示 over-budget 警告, 用戶決定要
不要在 SlideEditor 內縮短.

純函式, 沒 LLM call, 沒 IO. 純 dict in / dict out.
"""
from __future__ import annotations

from core.length_mode import LENGTH_PRESETS, preset


def _parse_range_high(range_str: str | None) -> int:
    """從 "60~80" / "180~280" 等字串拆出上限. 失敗回 999."""
    if not range_str:
        return 999
    try:
        return int(range_str.split("~")[-1])
    except (ValueError, AttributeError):
        return 999


def validate_slide_narration(
    narration: str | None, max_chars: int,
) -> dict:
    """檢查單一 slide narration 長度.

    回 dict:
        length: int             實際字數
        max: int                length_mode preset 上限
        over: bool              是否超出
        ratio: float            length / max (1.0 = 剛好)
        excess: int             超出字數 (over=False 時 0)
    """
    n = (narration or "").strip()
    length = len(n)
    over = length > max_chars
    return {
        "length": length,
        "max": max_chars,
        "over": over,
        "ratio": round(length / max_chars, 2) if max_chars > 0 else 0.0,
        "excess": max(0, length - max_chars),
    }


def check_deck_narration_lengths(
    deck: dict, length_mode: str | None = None,
) -> dict:
    """掃 deck 全部 slide narration, 回 summary report.

    支援兩種 schema:
      - 新 deck (sections / slides)
      - v1 exam (problems / steps)

    回 dict:
        total_slides: int           掃過的 slide 數
        over_budget_count: int      超出字數的 slide 數
        over_budget_ratio: float    over_budget_count / total_slides
        max_chars: int              當前 mode 上限
        worst_slide: dict | None    最嚴重超出的 slide info
        slides: list[dict]          每張 slide 的詳細統計 (含 slide_id, section_id, ...)
    """
    p = preset(length_mode)
    max_chars = _parse_range_high(p.get("narration_chars_range"))

    slides_out: list[dict] = []
    sections = deck.get("sections") or deck.get("problems") or []
    for sec_idx, sec in enumerate(sections):
        sec_id = str(sec.get("id") or f"sec{sec_idx + 1}")
        items = sec.get("slides") or sec.get("steps") or []
        for slide_idx, sl in enumerate(items):
            slide_id = str(sl.get("id") or f"{sec_id}_{slide_idx + 1}")
            # 跳過 cover / outro section (narration 是模板, 不受 length_mode 限制)
            if sec_id.startswith("_"):
                continue
            stat = validate_slide_narration(sl.get("narration"), max_chars)
            stat["slide_id"] = slide_id
            stat["section_id"] = sec_id
            slides_out.append(stat)

    over_slides = [s for s in slides_out if s["over"]]
    worst = max(over_slides, key=lambda s: s["excess"], default=None)
    total = len(slides_out)
    return {
        "total_slides": total,
        "over_budget_count": len(over_slides),
        "over_budget_ratio": round(len(over_slides) / total, 2) if total > 0 else 0.0,
        "max_chars": max_chars,
        "worst_slide": worst,
        "slides": slides_out,
    }


def format_validation_report(report: dict, length_mode: str | None = None) -> str:
    """把 report dict 轉成人類可讀的 log line (給 runner.logger 用)."""
    total = report["total_slides"]
    over = report["over_budget_count"]
    ratio = report["over_budget_ratio"]
    max_c = report["max_chars"]
    if total == 0:
        return f"narration 長度驗證: 0 slides (deck 空 / cover-only)"
    msg = (
        f"narration 長度驗證 ({length_mode or 'quick'}): {over}/{total} slides "
        f"超出 {max_c} 字 ({ratio:.0%})"
    )
    worst = report.get("worst_slide")
    if worst:
        msg += (
            f", 最嚴重 {worst['section_id']}/{worst['slide_id']} "
            f"= {worst['length']} 字 (+{worst['excess']})"
        )
    return msg
