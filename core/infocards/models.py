"""模型設定 + 定價（從 infoCard config/models.ts 收編，Phase C-1）。

集中式：未來換模型只改此檔。id 與定價對齊 infoCard 原值。
"""
from __future__ import annotations

# ── 文字 / 邏輯模型（2026-08-18 依官方 models.list 更新）──
# 這裡只收錄能直接走本專案既有 generateContent pipeline 的型號；Live / TTS / Omni
# 需要不同 request/response 契約，不可混進一般文字角色下拉，否則選得到卻無法正常產出。
TEXT_MODELS: dict[str, dict[str, str]] = {
    # 2026-08-30 劉老師拍板: 主力遷 gemini-3.7-flash(最新)。
    # ⚠️ 此 id 尚未經本帳號 live 實測(上次 models.list 核對為 2026-08-18, 當時最新 3.6)
    #    —— 上線前先跑 `python tools/check_models.py` 確認存在, 404 時退回 flash_36。
    "flash": {
        "id": "gemini-3.7-flash",
        "label": "✦ Gemini 3.7 Flash（最新主力）",
        "description": "代理、多模態與一般內容生成的最新預設",
    },
    "flash_36": {
        "id": "gemini-3.6-flash",
        "label": "✦ Gemini 3.6 Flash（Stable）",
        "description": "前一代穩定主力，3.7 異常時的退回選項",
    },
    "flash_35": {
        "id": "gemini-3.5-flash",
        "label": "✦ Gemini 3.5 Flash（Stable）",
        "description": "高效能穩定模型，適合一般生成與程式設計",
    },
    "lite": {
        "id": "gemini-3.5-flash-lite",
        "label": "⚡ Gemini 3.5 Flash-Lite（快速省成本 · Stable）",
        "description": "高吞吐、低延遲與成本效益優先",
    },
    "lite_31": {
        "id": "gemini-3.1-flash-lite",
        "label": "⚡ Gemini 3.1 Flash-Lite（Stable）",
        "description": "效能與成本平衡的既有穩定 Lite 模型",
    },
    "pro": {
        "id": "gemini-3.1-pro-preview",
        "label": "✧ Gemini 3.1 Pro（深度推理 · Preview）",
        "description": "複雜問題、長文與進階代理工作",
    },
    "flash_preview": {
        "id": "gemini-3-flash-preview",
        "label": "✦ Gemini 3 Flash（Preview）",
        "description": "舊一代 Gemini 3 Flash 預覽型號，供相容性測試",
    },
}

# 專用 pipeline 型號：model id 已由帳號的 models.list 驗證存在，但目前不放入一般角色下拉。
# 後續若實作 Live / audio / Interactions API，可從這個目錄接線，不必再次猜 model id。
SPECIALIZED_MODELS: dict[str, dict[str, str]] = {
    "live_translate": {
        "id": "gemini-3.5-live-translate-preview",
        "label": "Gemini 3.5 Live Translate（Preview）",
        "pipeline": "Live API / bidiGenerateContent",
    },
    "live": {
        "id": "gemini-3.1-flash-live-preview",
        "label": "Gemini 3.1 Flash Live（Preview）",
        "pipeline": "Live API / bidiGenerateContent",
    },
    "tts": {
        "id": "gemini-3.1-flash-tts-preview",
        "label": "Gemini 3.1 Flash TTS（Preview）",
        "pipeline": "GenerateContent / audio output",
    },
    "omni": {
        "id": "gemini-omni-flash-preview",
        "label": "Gemini Omni Flash（Preview）",
        "pipeline": "Interactions API / video output",
    },
}

# ── 圖片生成模型（便宜 / 中等 / 貴 三種品質階層）──
# 內部 key = lite/flash/pro，對使用者呈現為 便宜/中等/貴（dict 順序＝下拉顯示順序）。
# 對齊 Gemini 官方三階 Nano Banana 2 Lite / Nano Banana 2 / Nano Banana Pro；三顆皆
# gemini-image 家族。與 2026-06 Imagen 4 淘汰公告無關（那次淘汰的是 imagen-4.0-* 端點，
# 本專案從未使用）。
# 註 1：gemini-3.1-pro-image 經實測 404 不存在，Pro 正解為 gemini-3-pro-image（GA）。
# 註 2：入門階為 gemini-3.1-flash-lite-image（Nano Banana 2 Lite）。
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
DEFAULT_TEXT_MODEL = TEXT_MODELS["flash"]["id"]    # gemini-3.7-flash
DEFAULT_IMAGE_MODEL = IMAGE_MODELS["flash"]["id"]  # gemini-3.1-flash-image

# ── 成本定價（USD，估算值）──
# 文字 2026-08-30 起分 model 計價（T3-7 部分）：per-1k「字元」估算，"default" 為
# 未知/新 model 的退路（記主力價，別再記 $0 假便宜）。⚠️ 各檔費率為估算值，
# 以 Google 官方定價頁為準；新 model（如 3.7-flash）官方價公布後在此校正。
MODEL_PRICING: dict = {
    "text": {
        "default": {
            "input_per_1k_chars": 0.00001875,   # ~$0.075 / 1M tokens
            "output_per_1k_chars": 0.000075,    # ~$0.30 / 1M tokens
        },
        TEXT_MODELS["flash"]["id"]: {           # 3.7-flash: 暫比照 flash 檔位, 待官方價
            "input_per_1k_chars": 0.00001875,
            "output_per_1k_chars": 0.000075,
        },
        TEXT_MODELS["flash_36"]["id"]: {
            "input_per_1k_chars": 0.00001875,
            "output_per_1k_chars": 0.000075,
        },
        TEXT_MODELS["flash_35"]["id"]: {
            "input_per_1k_chars": 0.00001875,
            "output_per_1k_chars": 0.000075,
        },
        TEXT_MODELS["lite"]["id"]: {            # lite 檔位 ~flash 的一半
            "input_per_1k_chars": 0.00001,
            "output_per_1k_chars": 0.00004,
        },
        TEXT_MODELS["lite_31"]["id"]: {
            "input_per_1k_chars": 0.00001,
            "output_per_1k_chars": 0.00004,
        },
        TEXT_MODELS["pro"]["id"]: {             # pro 檔位 ~flash 的 8~10x
            "input_per_1k_chars": 0.00015,
            "output_per_1k_chars": 0.0006,
        },
    },
    "image": {
        "default": 0.003,                    # 未知圖片 model → 記中等階價, 不再記 $0
        IMAGE_MODELS["lite"]["id"]: 0.002,   # 3.1-flash-lite-image（估算 · lite 階，待官方定價校正）
        IMAGE_MODELS["flash"]["id"]: 0.003,  # 3.1-flash-image
        IMAGE_MODELS["pro"]["id"]: 0.04,     # 3-pro-image
        # 舊工作紀錄仍可能引用此 model id，保留歷史用量估算相容性。
        "gemini-2.5-flash-image": 0.003,
    },
}


def text_model_options() -> list[dict[str, str]]:
    """UI 下拉用：所有文字模型選項。"""
    return list(TEXT_MODELS.values())


def image_model_options() -> list[dict[str, str]]:
    """UI 下拉用：所有圖片模型選項。"""
    return list(IMAGE_MODELS.values())


def specialized_model_options() -> list[dict[str, str]]:
    """設定頁資訊用：已核對但尚需專用 pipeline 的 Preview 型號。"""
    return list(SPECIALIZED_MODELS.values())
