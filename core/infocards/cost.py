"""成本估算（從 infoCard utils/costCalculator.ts 收編，Phase C-1）。

純算術，定價取自 models.MODEL_PRICING。回傳 dict 的鍵維持 camelCase 對齊前端 AICost 契約。
"""
from __future__ import annotations

from core.infocards.models import DEFAULT_IMAGE_MODEL, MODEL_PRICING


def estimate_cost(
    input_char_count: int,
    output_char_count: int,
    image_count: int,
    image_model: str,
) -> dict:
    """估算一次 API 呼叫費用（USD），回 AICost 形狀（camelCase 鍵）。"""
    input_cost = (input_char_count / 1000) * MODEL_PRICING["text"]["input_per_1k_chars"]
    output_cost = (output_char_count / 1000) * MODEL_PRICING["text"]["output_per_1k_chars"]
    # 未知模型 fallback 到 flash 定價（對齊 TS 的 || 預設）。
    image_unit_cost = MODEL_PRICING["image"].get(
        image_model, MODEL_PRICING["image"][DEFAULT_IMAGE_MODEL]
    )
    image_cost = image_count * image_unit_cost
    total_cost = input_cost + output_cost + image_cost

    return {
        "totalCost": round(total_cost, 5),   # 保留 5 位小數（極小金額）
        "currency": "USD",
        "breakdown": {
            "textInput": round(input_cost, 5),
            "textOutput": round(output_cost, 5),
            "imageGeneration": round(image_cost, 5),
            "imageCount": image_count,
            "imageModel": image_model,
        },
    }
