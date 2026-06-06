"""漫畫生成（從 infoCard services/comicService.ts 收編，Phase C-2）。

兩步：generate_comic_script（內容 → 分鏡 ComicData JSON）+ generate_comic_images（逐格生圖）。
後端走核心 Gemini helper（core.infocards.gemini）；風格/promptUsed 與原版一致。
"""
from __future__ import annotations

from pydantic import BaseModel

from core.infocards.gemini import generate_image_b64, generate_json
from core.infocards.schemas import ComicData


# 生成用 schema（約束 Gemini 輸出結構）：只含模型該產的欄位；
# style/promptUsed 由後端補、imageUrl 之後生圖填，故不在此。
class _PanelGen(BaseModel):
    id: str
    panelNumber: int
    description: str
    dialogue: str
    cameraDetail: str
    imagePrompt: str


class _ComicGen(BaseModel):
    title: str
    storySummary: str
    characterVisualBible: str
    panels: list[_PanelGen]


def _build_comic_prompt(text: str, style: str, custom: str, panels: int) -> str:
    style_header = f"ART STYLE: {custom}" if style == "custom" else f"STYLE: {style}"
    return f"""你是一個專業漫畫分鏡師。請根據以下內容生成一份 {panels} 格漫畫的 JSON 資料。

要求：
1. 語言：繁體中文（台灣）
2. 風格：{style_header}
3. 每個 panel 需包含：id（字串如 "panel_1"）、panelNumber（數字）、description（場景描述）、dialogue（對話）、cameraDetail（鏡頭如 "特寫"、"遠景"）、imagePrompt（英文圖像生成提示）
4. characterVisualBible 需描述角色外貌特徵以保持一致性

內容：{text}"""


def generate_comic_script(
    text: str,
    style: str,
    *,
    custom: str = "",
    panels: int = 4,
    model: str | None = None,
    files=None,
) -> ComicData:
    """內容 → 漫畫分鏡 ComicData（不含圖；imageUrl 之後由 generate_comic_images 填）。"""
    prompt = _build_comic_prompt(text, style, custom, panels)
    data = generate_json(prompt, model=model, response_schema=_ComicGen, files=files)
    # 對齊 infoCard：style / promptUsed 由後端補（非模型輸出）。
    data["style"] = style
    data["promptUsed"] = prompt
    return ComicData.model_validate(data)


def generate_comic_images(
    data: ComicData,
    *,
    model: str | None = None,
    custom: str = "",
) -> ComicData:
    """逐格生圖，填回每個 panel.imageUrl（base64 data URL）。"""
    for panel in data.panels:
        panel.imageUrl = generate_image_b64(panel.imagePrompt, model=model)
    return data
