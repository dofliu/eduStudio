"""海報（單圖 infographic）生成（從 infoCard geminiService.generateFullInfographicImage 收編，Phase C-2）。

把內容轉成單張 4K 海報圖。後端走核心 Gemini helper（core.infocards.gemini）。

移植範圍說明:
- **prompt 建構**（style / density / HIGH_QUALITY 文字渲染要求 / aspect ratio / refinement / 內容）
  完整忠實移植，可單元測試。
- 生圖複用 gemini.generate_image_b64（response_modalities=IMAGE + base64 抽取）。原 JS 用
  imageConfig.aspectRatio/imageSize 控實際尺寸；此處先以 prompt hint 帶 aspect ratio，
  imageConfig 細節待 live 驗證後再精修（不影響 prompt 正確性）。
- 多模態 file 輸入（上傳參考圖/PDF inline）為後續加強（先支援 text/url 內容）。
"""
from __future__ import annotations

from core.infocards.gemini import generate_image_b64
from core.infocards.models import IMAGE_MODELS

# 文字渲染 + 4K 品質要求（從 geminiClient.HIGH_QUALITY_TEXT_PROMPT 原樣移植）。
HIGH_QUALITY_TEXT_PROMPT = """
【CRITICAL TEXT RENDERING REQUIREMENTS】
- ALL text in the image MUST be rendered in correct Traditional Chinese (Taiwan)
- Each Chinese character must have clear, correct strokes — NO blurry or garbled characters
- Text must be the #1 priority: never sacrifice text clarity for artistic effects
- Use high-contrast text colors against the background
- Minimum effective font size: titles 48px+, body 24px+
- Prefer well-known system fonts for Chinese: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC"

【QUALITY REQUIREMENTS】
- Entire image MUST be 4K high-resolution (3840x2160 or higher quality)
- All text MUST use correct Traditional Chinese (Taiwan) with proper stroke rendering
- The visual theme MUST perfectly align with the requested style
- Text MUST be the FIRST priority, never sacrifice text clarity for artistic effects
"""

_DENSITY_INSTRUCTION = {
    "minimal": """【CONTENT DENSITY: MINIMAL】
    - Use ONLY key phrases and bullet points, NO paragraphs
    - Maximum 20-30 Chinese characters per section
    - Prioritize ICONS and VISUALS over text
    - Leave plenty of white space""",
    "balanced": """【CONTENT DENSITY: BALANCED】
    - Mix of concise text and visual elements
    - 30-50 Chinese characters per section
    - Include both key points and brief explanations""",
    "detailed": """【CONTENT DENSITY: DETAILED】
    - Include comprehensive explanations
    - 50-80 Chinese characters per section
    - Cover all important details from source content
    - Dense but still readable layout""",
}

# aspect ratio → API 值（對齊 geminiService ratioConfig）。
_RATIO_API = {"vertical": "3:4", "horizontal": "16:9", "square": "1:1"}


def build_poster_prompt(
    text: str,
    style: str,
    *,
    custom_style_prompt: str = "",
    density: str = "balanced",
    aspect_ratio: str = "vertical",
    refinement: str = "",
) -> str:
    """建海報生圖 prompt（忠實移植 generateFullInfographicImage 的 promptText）。"""
    if style == "custom":
        style_desc = (
            f"【CRITICAL VISUAL STYLE】: {custom_style_prompt}. ABANDON ALL DEFAULTS. "
            "ENTIRE IMAGE MUST BE IN THIS STYLE."
        )
    else:
        style_desc = f"VISUAL STYLE: {style}"

    density_instruction = _DENSITY_INSTRUCTION.get(density, _DENSITY_INSTRUCTION["balanced"])
    ratio_api = _RATIO_API.get(aspect_ratio, _RATIO_API["vertical"])
    refine_line = f"USER REFINEMENT REQUEST: {refinement}" if refinement else ""

    return f"""TASK: Create a stunning professional 4K single-page infographic poster.
  {style_desc}
  ASPECT RATIO: {ratio_api}
  {density_instruction}
  {HIGH_QUALITY_TEXT_PROMPT}
  {refine_line}
  CONTENT TO INCLUDE: {text[:5000]}"""


def generate_poster(
    text: str,
    style: str,
    *,
    custom_style_prompt: str = "",
    aspect_ratio: str = "vertical",
    refinement: str = "",
    density: str = "balanced",
    image_model: str | None = None,
    api_key: str | None = None,
) -> dict:
    """內容 → 單張海報圖。回 {imageUrl(base64 data URL 或 ""), prompt}。

    預設用 pro 圖片模型（對齊 infoCard 海報模式）。
    """
    prompt = build_poster_prompt(
        text, style, custom_style_prompt=custom_style_prompt,
        density=density, aspect_ratio=aspect_ratio, refinement=refinement,
    )
    model = image_model or IMAGE_MODELS["pro"]["id"]
    image_url = generate_image_b64(prompt, model=model, api_key=api_key)
    return {"imageUrl": image_url, "prompt": prompt}
