"""模型設定 + 定價（從 infoCard config/models.ts 收編，Phase C-1）。

集中式：未來換模型只改此檔。id 與定價對齊 infoCard 原值。
"""
from __future__ import annotations

# ── 文字 / 邏輯模型（2026-06 劉老師更新為 Gemini 3 系列；2.5 將逐步停止支援）──
# id 均經 live API 實測可用（gemini-3.1-pro 不存在→正解 gemini-3.1-pro-preview）。
TEXT_MODELS: dict[str, dict[str, str]] = {
    "flash": {
        "id": "gemini-3.5-flash",
        "label": "⚡ 3.5 Flash (主力 · 速度品質兼顧)",
        "description": "一般生成主力，速度與品質平衡",
    },
    "lite": {
        "id": "gemini-3.1-flash-lite",
        "label": "🪶 3.1 Flash Lite (最省)",
        "description": "最低成本，簡單任務適用",
    },
    "pro": {
        "id": "gemini-3.1-pro-preview",
        "label": "🚀 3.1 Pro (深度推理)",
        "description": "最強推理，複雜內容/長文",
    },
}

# ── 圖片生成模型 ──
# 註：劉老師列的 gemini-3.1-pro-image 經實測 404 不存在，正解為 gemini-3-pro-image-preview。
IMAGE_MODELS: dict[str, dict[str, str]] = {
    "flash": {
        "id": "gemini-3.1-flash-image",
        "label": "⚡ 3.1 Flash Image (主力 · 快速)",
        "description": "快速生圖主力，低延遲",
    },
    "pro": {
        # 註：劉老師網頁看到 gemini-3.1-pro-image，但本 key 的 API models.list 無此 id（404）；
        # 實際可用的 pro 圖片模型是 gemini-3-pro-image（GA）。3.1-pro-image 未經 API 開放再換。
        "id": "gemini-3-pro-image",
        "label": "👑 Pro Image (最高畫質)",
        "description": "專業品質，最高畫質繪圖",
    },
    "legacy": {
        "id": "gemini-2.5-flash-image",
        "label": "🕘 2.5 Flash Image (舊版 · 將停用)",
        "description": "舊版，Google 預計逐步停止支援",
    },
}

# ── 預設模型 ──
DEFAULT_TEXT_MODEL = TEXT_MODELS["flash"]["id"]    # gemini-3.5-flash
DEFAULT_IMAGE_MODEL = IMAGE_MODELS["flash"]["id"]  # gemini-3.1-flash-image

# ── 成本定價（USD，估算值）──
MODEL_PRICING: dict = {
    "text": {
        "input_per_1k_chars": 0.00001875,   # ~$0.075 / 1M tokens
        "output_per_1k_chars": 0.000075,    # ~$0.30 / 1M tokens
    },
    "image": {
        IMAGE_MODELS["flash"]["id"]: 0.003,
        IMAGE_MODELS["pro"]["id"]: 0.04,
        IMAGE_MODELS["legacy"]["id"]: 0.003,
    },
}


def text_model_options() -> list[dict[str, str]]:
    """UI 下拉用：所有文字模型選項。"""
    return list(TEXT_MODELS.values())


def image_model_options() -> list[dict[str, str]]:
    """UI 下拉用：所有圖片模型選項。"""
    return list(IMAGE_MODELS.values())
