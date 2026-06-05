"""模型設定 + 定價（從 infoCard config/models.ts 收編，Phase C-1）。

集中式：未來換模型只改此檔。id 與定價對齊 infoCard 原值。
"""
from __future__ import annotations

# ── 文字 / 邏輯模型 ──
# 註：原 infoCard 用 preview model id（gemini-3-flash-preview 等），未必 GA；改用 autoSolver
# 已驗證可用的 gemini-2.5 系列（與 core.config.GEMINI_MODEL 一致），確保實際呼叫成功。
TEXT_MODELS: dict[str, dict[str, str]] = {
    "flash": {
        "id": "gemini-2.5-flash",
        "label": "⚡ Flash (速度優先)",
        "description": "一般邏輯處理，高速回應",
    },
    "pro": {
        "id": "gemini-2.5-pro",
        "label": "🚀 Pro (深度推理)",
        "description": "深度邏輯處理，進階推理能力",
    },
}

# ── 圖片生成模型 ──
IMAGE_MODELS: dict[str, dict[str, str]] = {
    "flash": {
        "id": "gemini-2.5-flash-image",
        "label": "⚡ Flash Image (快速)",
        "description": "速度優先，低延遲",
    },
    "balanced": {
        "id": "gemini-3.1-flash-image-preview",
        "label": "🎨 Flash Image 2 (效能均衡)",
        "description": "效能與品質兼顧",
    },
    "pro": {
        "id": "gemini-3-pro-image-preview",
        "label": "👑 Pro Image (最高畫質)",
        "description": "專業品質，進階推理繪圖",
    },
}

# ── 預設模型 ──
DEFAULT_TEXT_MODEL = TEXT_MODELS["flash"]["id"]
DEFAULT_IMAGE_MODEL = IMAGE_MODELS["flash"]["id"]

# ── 成本定價（USD）──
MODEL_PRICING: dict = {
    "text": {
        "input_per_1k_chars": 0.00001875,   # ~$0.075 / 1M tokens
        "output_per_1k_chars": 0.000075,    # ~$0.30 / 1M tokens
    },
    "image": {
        IMAGE_MODELS["flash"]["id"]: 0.003,
        IMAGE_MODELS["balanced"]["id"]: 0.008,
        IMAGE_MODELS["pro"]["id"]: 0.04,
    },
}


def text_model_options() -> list[dict[str, str]]:
    """UI 下拉用：所有文字模型選項。"""
    return list(TEXT_MODELS.values())


def image_model_options() -> list[dict[str, str]]:
    """UI 下拉用：所有圖片模型選項。"""
    return list(IMAGE_MODELS.values())
