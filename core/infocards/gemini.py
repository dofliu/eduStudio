"""infoCard 生成共用 Gemini helper（Phase C-2）。

對應 infoCard services/geminiClient.ts 的 getAI/parseJsonFromResponse/generateInternalImage。
用新版 google.genai SDK + core.config 金鑰。**後端統一在此呼叫 Gemini，前端不再瀏覽器直呼**
（infoCard 原架構是 client-side，移植後改 server-side）。
"""
from __future__ import annotations

import base64
import json
import re

from core import config
from core.infocards.models import DEFAULT_IMAGE_MODEL, DEFAULT_TEXT_MODEL

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_fence(text: str) -> str:
    """去掉 LLM 可能包的 ```json ... ``` 圍欄（對齊 infoCard parseJsonFromResponse）。"""
    t = (text or "").strip()
    t = _FENCE.sub("", t)
    return t.strip()


def _client(api_key: str | None):
    key = api_key or config.get_gemini_api_key()
    if not key:
        raise RuntimeError("缺少 GEMINI_API_KEY 環境變數")
    from google import genai
    return genai.Client(api_key=key)


def _record_text(station: str, model: str, prompt: str, text: str) -> None:
    """記文字用量（成本面板）；吞例外不拖垮生成。"""
    try:
        from datetime import datetime, timezone

        from core import usage
        usage.record_text(station, len(prompt or ""), len(text or ""),
                          model=model, ts=datetime.now(timezone.utc).isoformat())
    except Exception:
        pass


def generate_json(prompt: str, *, model: str | None = None,
                  api_key: str | None = None, temperature: float = 0.4,
                  response_schema=None, station: str = "visual") -> dict:
    """呼叫 Gemini 產 JSON（response_mime_type=application/json），回 parsed dict。

    response_schema（pydantic model 或 dict）約束輸出結構 —— 對齊 infoCard 原本用
    responseSchema 強制 JSON 形狀的做法，避免模型自由發揮回錯誤鍵。解析失敗回 {}。
    station 標記成本歸屬（成本面板用，預設 visual）。
    """
    from google.genai import types

    client = _client(api_key)
    used_model = model or DEFAULT_TEXT_MODEL
    cfg: dict = {"response_mime_type": "application/json", "temperature": temperature}
    if response_schema is not None:
        cfg["response_schema"] = response_schema
    resp = client.models.generate_content(
        model=used_model,
        contents=[prompt],
        config=types.GenerateContentConfig(**cfg),
    )
    text = resp.text or "{}"
    _record_text(station, used_model, prompt, text)
    try:
        return json.loads(_strip_fence(text))
    except json.JSONDecodeError:
        return {}


def generate_image_b64(prompt: str, *, model: str | None = None,
                       api_key: str | None = None) -> str:
    """呼叫 Gemini 生圖，回 base64 data URL（前端 <img src> 可直接用）；失敗回 ""。

    沿用 autoSolver core/diagram_image_gen 的 image bytes 抽取（SDK 回 bytes 或 base64 str 都處理）。
    """
    from google.genai import types

    client = _client(api_key)
    try:
        resp = client.models.generate_content(
            model=model or DEFAULT_IMAGE_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
    except Exception:
        return ""
    from core.diagram_image_gen import _extract_image_bytes

    raw = _extract_image_bytes(resp)
    if not raw:
        return ""
    try:
        from datetime import datetime, timezone

        from core import usage
        usage.record_image("visual", model or DEFAULT_IMAGE_MODEL,
                           ts=datetime.now(timezone.utc).isoformat())
    except Exception:
        pass
    return "data:image/png;base64," + base64.b64encode(raw).decode()
