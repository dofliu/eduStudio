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
from core.models import IMAGE_FAST, TEXT_FAST, resolve_id

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_fence(text: str) -> str:
    """去掉 LLM 可能包的 ```json ... ``` 圍欄（對齊 infoCard parseJsonFromResponse）。"""
    t = (text or "").strip()
    t = _FENCE.sub("", t)
    return t.strip()


def _image_mime(raw: bytes) -> str:
    """依影像檔頭判斷 data URL MIME；未知格式維持既有 PNG fallback。

    Gemini image model 可能回 JPEG。若一律標成 ``image/png``，瀏覽器雖常會自動
    sniff，PPTX 匯出或嚴格解碼器仍可能因 MIME 與內容不一致而失敗。
    """
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


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


def _build_contents(prompt: str, files):
    """組多模態 contents：把上傳檔（PDF/圖片 base64）當 inline part + prompt 文字。

    files: [{mimeType, data(base64 str 或 bytes)}]。無檔則回 [prompt]（純文字，行為不變）。
    """
    if not files:
        return [prompt]
    from google.genai import types

    parts = []
    for f in files:
        data = f.get("data") if isinstance(f, dict) else None
        if not data:
            continue
        raw = base64.b64decode(data) if isinstance(data, str) else data
        mime = (f.get("mimeType") if isinstance(f, dict) else None) or "application/octet-stream"
        parts.append(types.Part.from_bytes(data=raw, mime_type=mime))
    parts.append(types.Part.from_text(text=prompt))
    return parts


def generate_json(prompt: str, *, model: str | None = None,
                  api_key: str | None = None, temperature: float = 0.4,
                  response_schema=None, station: str = "visual", files=None) -> dict:
    """呼叫 Gemini 產 JSON（response_mime_type=application/json），回 parsed dict。

    response_schema（pydantic model 或 dict）約束輸出結構 —— 對齊 infoCard 原本用
    responseSchema 強制 JSON 形狀的做法，避免模型自由發揮回錯誤鍵。解析失敗回 {}。
    station 標記成本歸屬（成本面板用，預設 visual）。
    files：多模態參考檔（PDF/圖片 inline data），讓生成讀取使用者真實教材而非只靠標題。
    """
    from google.genai import types

    client = _client(api_key)
    # M-2: model id 走角色登錄表（text.fast）而非寫死常數；caller 顯式傳 model 則優先。
    used_model = model or resolve_id(TEXT_FAST)
    cfg: dict = {"response_mime_type": "application/json", "temperature": temperature}
    if response_schema is not None:
        cfg["response_schema"] = response_schema
    resp = client.models.generate_content(
        model=used_model,
        contents=_build_contents(prompt, files),
        config=types.GenerateContentConfig(**cfg),
    )
    text = resp.text or "{}"
    _record_text(station, used_model, prompt, text)
    try:
        return json.loads(_strip_fence(text))
    except json.JSONDecodeError:
        return {}


def generate_image_b64(prompt: str, *, model: str | None = None,
                       api_key: str | None = None, files=None) -> str:
    """呼叫 Gemini 生圖，回 base64 data URL（前端 <img src> 可直接用）；失敗回 ""。

    沿用 autoSolver core/diagram_image_gen 的 image bytes 抽取（SDK 回 bytes 或 base64 str 都處理）。
    files：多模態參考檔（上傳的 PDF/圖片 inline data），讓生圖讀使用者真實內容而非只靠標題。
    """
    from google.genai import types

    client = _client(api_key)
    # M-2: 生圖 id 走角色登錄表（image.fast）；caller 顯式傳 model 則優先。
    used_model = model or resolve_id(IMAGE_FAST)
    try:
        resp = client.models.generate_content(
            model=used_model,
            contents=_build_contents(prompt, files),
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
        usage.record_image("visual", used_model,
                           ts=datetime.now(timezone.utc).isoformat())
    except Exception:
        pass
    return f"data:{_image_mime(raw)};base64," + base64.b64encode(raw).decode()
