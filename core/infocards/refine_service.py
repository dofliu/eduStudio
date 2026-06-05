"""單頁簡報微調 refine（從 infoCard refineSlidePrompt.ts + speakerNotesPrompt.ts +
presentationService.ts:refinePresentationSlide 收編，Phase C）。

純 prompt 組裝（persona/slide-content/refine）+ refine 主流程：依修改指令重生單頁，
經規則引擎校正版型、chart_focus 回填、imagePolicy 生圖、教學 budget 裁切——與
generate_presentation_data 後處理一致。character sheet 角色一致性暫略（eduStudio UI 未用）。
"""
from __future__ import annotations

import json

from core.infocards.chart_suggester import (
    build_chart_data_for_slide,
    is_renderable_chart_data,
)
from core.infocards.gemini import generate_image_b64, generate_json
from core.infocards.layout_rules import analyze_outline_slide, reconcile_layout
from core.infocards.presentation_service import needs_ai_image
from core.infocards.schemas import Slide
from core.infocards.slide_budget import enforce_teaching_layout_budget_dict


# ── 純 prompt 組裝（對齊 speakerNotesPrompt.ts / refineSlidePrompt.ts）──
def build_persona_block(persona: dict | None) -> str:
    """persona → 單行「語氣／受眾／目的」區塊（以「；」分隔，全空回空字串）。"""
    if not persona:
        return ""
    parts = [
        f"語氣：{persona['tone']}" if persona.get("tone") else None,
        f"目標受眾：{persona['audience']}" if persona.get("audience") else None,
        f"簡報目的：{persona['purpose']}" if persona.get("purpose") else None,
    ]
    return "；".join(p for p in parts if p)


def build_slide_content_block(slide: dict) -> str:
    """投影片 → 「本頁內容」文字（標題 + content/bulletPoints + sections 攤平）。"""
    section_texts = " ".join(
        str(x) for sec in (slide.get("sections") or [])
        for x in [sec.get("content"), *(sec.get("bulletPoints") or [])] if x
    )
    parts = [
        f"標題：{slide.get('title', '')}",
        f"內容：{slide['content']}" if slide.get("content") else "",
        f"要點：{' / '.join(slide['bulletPoints'])}" if slide.get("bulletPoints") else "",
        section_texts,
    ]
    return "\n".join(p for p in parts if p)


def build_refine_slide_prompt(slide: dict, instruction: str, persona: dict | None = None) -> str:
    """單頁 refine prompt。無 persona 時逐字對齊歷史行為；有 persona 時插入風格區塊。"""
    persona_block = build_persona_block(persona) if persona else ""
    persona_instruction = (
        f"\n【個人簡報風格設定 — 修改時必須維持此風格】{persona_block}" if persona_block else ""
    )
    return (
        f'Refine this slide based on: "{instruction}".{persona_instruction} '
        f"Data: {json.dumps(slide, ensure_ascii=False)}"
    )


def build_speaker_notes_prompt(slide: dict, context: dict, persona: dict | None) -> str:
    """講者備忘稿 prompt（末頁收尾／其餘過渡）。"""
    persona_block = build_persona_block(persona)
    slide_content = build_slide_content_block(slide)
    idx = context.get("slideIndex", 0)
    total = context.get("totalSlides", 1)
    is_last = idx == total - 1
    head = f"【個人風格設定】{persona_block}\n" if persona_block else ""
    tail = "最後句：總結全場、感謝或鼓勵行動" if is_last else "最後句：自然銜接到下一頁的過渡語"
    return (
        f"你是一位專業簡報講師，請為以下投影片撰寫 3-5 句講者備忘稿。\n"
        f"{head}【簡報主題】{context.get('mainTitle', '')}"
        f"（共 {total} 頁，這是第 {idx + 1} 頁）\n"
        f"【本頁內容】\n{slide_content}\n\n"
        f"【要求】\n"
        f"- 第一句：引導觀眾注意力的開場銜接（自然口語，不要「這頁我們將…」模板語）\n"
        f"- 中間句：補充投影片文字以外的例子、背景或互動提問\n"
        f"- {tail}\n"
        f"- 語氣自然口語，如同真實演講；純文字，不要 markdown 格式"
    )


def refine_presentation_slide(
    slide: dict,
    instruction: str,
    *,
    style: str = "professional",
    custom: str = "",
    persona: dict | None = None,
    slide_index: int | None = None,
    total_slides: int | None = None,
    model: str | None = None,
    image_model: str | None = None,
) -> Slide:
    """依指令重生單頁，套用與整份生成一致的後處理，回 Slide。

    流程對齊 presentationService.ts:refinePresentationSlide：
    generate JSON → reconcile 版型 → chart_focus 回填 → imagePolicy 生圖 → teaching budget。
    AI 省略的欄位以原 slide 補回（merge），避免 refine 把未提及欄位清空。
    """
    prompt = build_refine_slide_prompt(slide, instruction, persona)
    updated = generate_json(prompt, model=model)  # 對齊原版：無 responseSchema
    # merge：AI 輸出覆蓋原 slide，省略欄位保留原值。
    merged = {**slide, **{k: v for k, v in (updated or {}).items() if v is not None}}

    # 規則引擎校正版型。
    title = merged.get("title", "")
    content = merged.get("content") or ""
    signals = analyze_outline_slide(title, content)
    target_layout = reconcile_layout(
        slide_index=slide_index, total_slides=total_slides,
        title=title, content=content,
        ai_hint=merged.get("layout") or slide.get("layout"), **signals)
    merged["layout"] = target_layout

    # chart_focus 回填（不覆蓋有效數據）。
    if target_layout == "chart_focus" and not is_renderable_chart_data(merged.get("chartData")):
        slide_text = "\n".join(
            str(x) for x in [merged.get("title"), merged.get("content"), *(merged.get("bulletPoints") or [])] if x
        )
        inferred = build_chart_data_for_slide(target_layout, slide_text)
        if inferred:
            merged["chartData"] = inferred

    # imagePolicy：允許版型且有 imagePrompt → 生圖；否則丟棄殘留 imagePrompt。
    if merged.get("imagePrompt") and needs_ai_image(target_layout):
        if not merged.get("imageUrl"):
            merged["imageUrl"] = generate_image_b64(merged["imagePrompt"], model=image_model)
    elif merged.get("imagePrompt"):
        merged["imagePrompt"] = None

    enforce_teaching_layout_budget_dict(merged)
    return Slide.model_validate(merged)
