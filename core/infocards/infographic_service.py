"""資訊圖卡（Infographic / 視覺站「圖卡 card」模式）生成。

從 infoCard services/geminiService.ts:generateInfographic 收編，Phase C-2 延伸。
兩步：generate_infographic_data（內容 → 結構化 InfographicData JSON：sections/statistics/
charts/conclusion）+ generate_infographic_images（逐 section 生圖填 imageUrl）。
後端走核心 Gemini helper（core.infocards.gemini），風格/promptUsed 與原版一致。

為什麼要 coerce：InfographicData 的 iconType/layout/chart.type 是 Literal（嚴格集合），
但 infoCard 原 responseSchema 只標 STRING（寬鬆）。Gemini 偶爾回集合外的值，直接
model_validate 會炸整個請求。比照 library deck-title 的防禦作法，validate 前把越界值
退到安全預設，不讓單一欄位毀掉整張圖卡。
"""
from __future__ import annotations

import json

from pydantic import BaseModel

from core.infocards.gemini import generate_image_b64, generate_json
from core.infocards.schemas import InfographicData, InfographicSection

# 允許集合（對齊 schemas.py 的 Literal）。
_ICONS = {"bulb", "chart", "list", "target", "warning", "info", "calendar", "check", "time"}
_LAYOUTS = {"grid", "timeline", "process", "comparison"}
_CHART_TYPES = {"bar", "pie"}


# 生成用 schema（約束 Gemini 輸出結構）：只含模型該產的欄位；
# style/aspectRatio 由後端補、imageUrl 之後生圖填，故不在此。iconType/layout/type 用寬鬆 str
# （對齊 infoCard responseSchema 的 STRING），越界值在 _coerce 退預設。
class _StatGen(BaseModel):
    id: str
    value: str
    label: str


class _SectionGen(BaseModel):
    id: str
    title: str
    content: str
    iconType: str = "info"
    imagePrompt: str | None = None


class _ChartItemGen(BaseModel):
    label: str
    value: float


class _ChartGen(BaseModel):
    id: str
    title: str
    type: str = "bar"
    data: list[_ChartItemGen]


class _InfographicGen(BaseModel):
    mainTitle: str
    subtitle: str
    layout: str = "grid"
    sections: list[_SectionGen]
    statistics: list[_StatGen]
    charts: list[_ChartGen] | None = None
    conclusion: str
    themeColor: str


def _coerce(data: dict) -> dict:
    """把 Gemini 回的 Literal 欄位越界值退到安全預設（in-place 改 + 回傳）。"""
    if data.get("layout") not in _LAYOUTS:
        data["layout"] = "grid"
    for sec in data.get("sections") or []:
        if sec.get("iconType") not in _ICONS:
            sec["iconType"] = "info"
    for ch in data.get("charts") or []:
        if ch.get("type") not in _CHART_TYPES:
            ch["type"] = "bar"
    return data


def _build_prompt(text: str, style: str, custom: str) -> str:
    style_clause = (
        f"【!!絕對優先風格指令!!】請完全無視專業商務預設框架，必須嚴格根據此風格設計："
        f"{custom}。請定義符合此風格的 themeColor。"
        if style == "custom" else f"視覺風格：{style}。"
    )
    return f"""你是一個天才視覺設計師。
  {style_clause}
  任務：將內容轉換為結構化 JSON（mainTitle/subtitle/layout/sections/statistics/charts/conclusion/themeColor）。
  iconType 限：bulb/chart/list/target/warning/info/calendar/check/time。layout 限：grid/timeline/process/comparison。
  請確保內容深度分析自文字。語言：繁體中文 (台灣)。
  內容：{text or '請分析內容。'}"""


def generate_infographic_data(
    text: str,
    style: str,
    *,
    custom: str = "",
    aspect_ratio: str = "vertical",
    model: str | None = None,
    files=None,
) -> InfographicData:
    """內容 → 資訊圖卡結構 InfographicData（不含圖；imageUrl 之後由 images 步驟填）。"""
    prompt = _build_prompt(text, style, custom)
    data = generate_json(prompt, model=model, response_schema=_InfographicGen, files=files)
    data = _coerce(data)
    # 對齊 infoCard：style / aspectRatio / promptUsed 由後端補（非模型輸出）。
    data["style"] = style
    data["aspectRatio"] = aspect_ratio
    data["promptUsed"] = prompt
    return InfographicData.model_validate(data)


def generate_infographic_images(
    data: InfographicData,
    *,
    model: str | None = None,
    custom: str = "",
) -> InfographicData:
    """逐 section 生圖（有 imagePrompt 者），填回 section.imageUrl（base64 data URL）。"""
    for section in data.sections:
        if section.imagePrompt:
            section.imageUrl = generate_image_b64(section.imagePrompt, model=model)
    return data


# ── 逐區 refine（區域選擇 UI → 重生單一 section，U-2）──
def build_refine_section_prompt(
    section: dict,
    instruction: str,
    *,
    style: str = "professional",
    custom: str = "",
    main_title: str = "",
) -> str:
    """單一 section refine prompt（對齊 _build_prompt 的風格/語言慣例）。"""
    style_clause = (
        f"【!!絕對優先風格指令!!】請完全無視專業商務預設框架，必須嚴格根據此風格設計：{custom}。"
        if style == "custom" else f"視覺風格：{style}。"
    )
    ctx = f"（所屬資訊圖卡主題：{main_title}）" if main_title else ""
    return f"""你是一個天才視覺設計師。{style_clause}
  任務：依「修改指令」重生單一資訊圖卡區塊的 JSON（id/title/content/iconType/imagePrompt）{ctx}。
  iconType 限：bulb/chart/list/target/warning/info/calendar/check/time。
  請保持 id 不變；只調整這一個區塊，勿產生其他區塊。語言：繁體中文 (台灣)。
  修改指令：{instruction}
  原區塊：{json.dumps(section, ensure_ascii=False)}"""


def refine_infographic_section(
    data: InfographicData,
    section_id: str,
    instruction: str,
    *,
    style: str = "professional",
    custom: str = "",
    model: str | None = None,
    image_model: str | None = None,
    regenerate_image: bool = True,
) -> InfographicData:
    """依指令重生指定 section（逐區 refine），回更新後的整張 InfographicData。

    流程比照 refine_service.refine_presentation_slide：generate JSON → merge（AI 省略欄位保留原值，
    不清空）→ iconType 越界退預設（比照 _coerce）→ imagePolicy 生圖。imagePrompt 變動（或原無圖
    現有 prompt）且 regenerate_image → 重新生圖；imagePrompt 被清空 → 去掉 imageUrl。
    id 鎖死不變。找不到 section_id → ValueError（route 轉 404）。
    """
    target = next((s for s in data.sections if s.id == section_id), None)
    if target is None:
        raise ValueError(f"找不到 section：{section_id}")
    original = target.model_dump()
    prompt = build_refine_section_prompt(
        original, instruction, style=style, custom=custom, main_title=data.mainTitle)
    updated = generate_json(prompt, model=model, response_schema=_SectionGen) or {}
    # merge：AI 輸出覆蓋原值，省略（None）欄位保留原 section（避免 refine 清空未提及欄位）。
    merged = {**original, **{k: v for k, v in updated.items() if v is not None}}
    merged["id"] = section_id  # id 鎖死，不讓 AI 改 key
    if merged.get("iconType") not in _ICONS:
        merged["iconType"] = "info"

    # imagePolicy：有 imagePrompt 且要求生圖 → prompt 變動或尚無圖時重生；prompt 清空 → 去圖。
    new_prompt = merged.get("imagePrompt")
    if regenerate_image and new_prompt:
        if new_prompt != original.get("imagePrompt") or not merged.get("imageUrl"):
            merged["imageUrl"] = generate_image_b64(new_prompt, model=image_model)
    elif not new_prompt:
        merged["imageUrl"] = None

    refreshed = InfographicSection.model_validate(merged)
    data.sections = [refreshed if s.id == section_id else s for s in data.sections]
    return data
