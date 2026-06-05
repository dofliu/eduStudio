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

from pydantic import BaseModel

from core.infocards.gemini import generate_image_b64, generate_json
from core.infocards.schemas import InfographicData

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
) -> InfographicData:
    """內容 → 資訊圖卡結構 InfographicData（不含圖；imageUrl 之後由 images 步驟填）。"""
    prompt = _build_prompt(text, style, custom)
    data = generate_json(prompt, model=model, response_schema=_InfographicGen)
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
