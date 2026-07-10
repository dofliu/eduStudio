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

# ── 圖片生成模型（便宜 / 中等 / 貴 三種品質階層）──
# 內部 key = lite/flash/pro，對使用者呈現為 便宜/中等/貴（dict 順序＝下拉顯示順序）。
# 對齊 Gemini 官方三階 Nano Banana 2 Lite / Nano Banana 2 / Nano Banana Pro；三顆皆
# gemini-image 家族。與 2026-06 Imagen 4 淘汰公告無關（那次淘汰的是 imagen-4.0-* 端點，
# 本專案從未使用）。
# 註 1：gemini-3.1-pro-image 經實測 404 不存在，Pro 正解為 gemini-3-pro-image（GA）。
# 註 2：入門階 2026-07 由舊世代 gemini-2.5-flash-image 對齊為 gemini-3.1-flash-lite-image
#   （Nano Banana 2 Lite）。此 id 請於 live API 實測確認可用（沿用「先實測再上」紀律）。
#   舊 id gemini-2.5-flash-image 仍保留於 MODEL_PRICING（diagram_image_gen / song_images 仍直接用）。
# 本檔為圖片模型 id 的**單一目錄**；core/models.py 的 image.* 角色直接引用此表（不另寫一份）。
IMAGE_MODELS: dict[str, dict[str, str]] = {
    "lite": {
        "id": "gemini-3.1-flash-lite-image",
        "label": "💲 便宜 · Nano Banana 2 Lite (3.1 Flash Lite Image)",
        "description": "成本最低、速度最快，一般配圖夠用",
    },
    "flash": {
        "id": "gemini-3.1-flash-image",
        "label": "⚡ 中等 · Nano Banana 2 (3.1 Flash Image · 預設)",
        "description": "速度與品質平衡，預設選項",
    },
    "pro": {
        "id": "gemini-3-pro-image",
        "label": "👑 貴 · Nano Banana Pro (最高畫質)",
        "description": "專業品質，最高畫質繪圖",
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
        IMAGE_MODELS["lite"]["id"]: 0.002,   # 3.1-flash-lite-image（估算 · lite 階，待官方定價校正）
        IMAGE_MODELS["flash"]["id"]: 0.003,  # 3.1-flash-image
        IMAGE_MODELS["pro"]["id"]: 0.04,     # 3-pro-image
        # 舊入門模型：已非下拉選項，但 diagram_image_gen / song_images 仍直接寫死用，
        # 保留定價避免 core/usage.py 用量計帳把它記成 $0。
        "gemini-2.5-flash-image": 0.003,
    },
}


def text_model_options() -> list[dict[str, str]]:
    """UI 下拉用：所有文字模型選項。"""
    return list(TEXT_MODELS.values())


def image_model_options() -> list[dict[str, str]]:
    """UI 下拉用：所有圖片模型選項。"""
    return list(IMAGE_MODELS.values())
