"""M-4 Provider adapter 介面（B-ready stub）。

把「呼叫哪個後端做文字／生圖／語音」抽象成 ``Provider`` 協定，讓 Phase 9 F9-3
（ollama / claude / 本機可插拔 provider）能 **slot-in**，呼叫端只認邏輯角色
（``core.models.resolve``）拿到 provider 名 → ``get_provider()`` 取對應實作。

**M-4 只抽介面、不換行為**：現有散落呼叫端（infocards / scriptor / outliner /
tts_backend）本輪 **不改線**，仍各自運作。本檔提供的是「未來換接的座位」：

- ``Provider`` 協定（``runtime_checkable``）：三能力面 ``generate_text`` /
  ``generate_image`` / ``tts``。
- ``GeminiProvider``：A 階段唯一的 LLM／視覺／生圖 provider。``generate_text`` 走
  google.genai、``generate_image`` 委派既有 ``core.infocards.gemini.generate_image_b64``
  （**包現有呼叫**，行為不變）。``tts`` **非其職責** → ``NotImplementedError``：本 repo
  的語音合成走獨立的 ``tts_backend`` 子系統（``resolve('tts')`` → provider ``edge`` /
  ``f5`` / ``google``），不混進 LLM provider registry。
- ``get_provider(name)`` / ``provider_for_role(role)``：依 provider 名（或角色 resolve
  出的 provider）取實作 + 該角色的 model id。未知 provider／角色 → ``ValueError``
  （type guard，禁止打錯字默默退預設）。

B 階段（F9-3）只要新增一個實作此協定的 class（例：``OllamaProvider``）並
``register_provider()``，再讓角色登錄表 ``DEFAULTS`` / 設定頁把對應角色指到該 provider，
呼叫端零改動即生效。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.models import (
    PROVIDER_GEMINI,
    PROVIDER_OLLAMA,
    TEXT_FAST,
    resolve,
    resolve_id,
)
from core.ollama_client import ollama_generate
from core.usage import record_text_now

__all__ = [
    "Provider",
    "GeminiProvider",
    "OllamaProvider",
    "register_provider",
    "get_provider",
    "provider_for_role",
]


@runtime_checkable
class Provider(Protocol):
    """模型後端的統一能力面（B-ready）。

    每個 provider 宣告 ``name``（對齊 ``core.models`` 的 provider 名），並實作三能力。
    不支援的能力應 ``raise NotImplementedError``（例：LLM provider 不做 TTS），而非
    靜默回空，讓誤接的呼叫早爆早查。
    """

    name: str

    def generate_text(self, prompt: str, *, model: str | None = None,
                      temperature: float = 0.4, station: str = "text") -> str:
        ...

    def generate_image(self, prompt: str, *, model: str | None = None,
                       station: str = "visual", files=None,
                       api_key: str | None = None) -> str:
        ...

    def tts(self, text: str, out_path) -> bool:
        ...


def _gemini_text_call(client, model: str, prompt: str, *, temperature: float) -> str:
    """唯一與 google.genai 綁定的文字呼叫。

    刻意隔離成模組層函式 = ① B 階段抽換點（換 SDK / provider 只動這裡）
    ② 測試注入點（monkeypatch 此函式即可不碰真 API / 不需裝 google-genai）。
    """
    from google.genai import types

    resp = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=temperature),
    )
    return getattr(resp, "text", None) or ""


class GeminiProvider:
    """A 階段唯一 LLM／視覺／生圖 provider（包現有 google.genai 呼叫）。

    ``client`` 可注入（測試用 fake / B 階段共用 client）；不傳則延遲建立真實 client
    （沿用 ``core.infocards.gemini._client`` 的金鑰邏輯，單一真實來源）。
    """

    name = PROVIDER_GEMINI

    def __init__(self, *, client=None, api_key: str | None = None) -> None:
        self._injected_client = client
        self._api_key = api_key

    def _ensure_client(self):
        if self._injected_client is not None:
            return self._injected_client
        from core.infocards.gemini import _client

        return _client(self._api_key)

    def generate_text(self, prompt: str, *, model: str | None = None,
                      temperature: float = 0.4, station: str = "text") -> str:
        """產文字。``model`` 未指定 → 走角色登錄表 ``text.fast``（單一真實來源）。"""
        client = self._ensure_client()
        used_model = model or resolve_id(TEXT_FAST)
        text = _gemini_text_call(client, used_model, prompt, temperature=temperature)
        record_text_now(station, used_model, prompt, text)
        return text

    def generate_image(self, prompt: str, *, model: str | None = None,
                       station: str = "visual", files=None,
                       api_key: str | None = None) -> str:
        """生圖（回 base64 data URL）。委派既有 ``generate_image_b64``——**包現有呼叫**，
        行為不變（``model`` 未指定時由它走 ``image.fast``、計帳沿用既有）。"""
        from core.infocards.gemini import generate_image_b64

        return generate_image_b64(prompt, model=model,
                                  api_key=api_key or self._api_key, files=files)

    def tts(self, text: str, out_path) -> bool:
        raise NotImplementedError(
            "GeminiProvider 不負責 TTS；語音合成走獨立的 tts_backend 子系統"
            "（resolve('tts') → provider 'edge' / 'f5' / 'google'）。"
        )


class OllamaProvider:
    """F9-3 本機可插拔 LLM provider（M 軸 Option B 的第一個非 Gemini provider）。

    讓**文字角色**（翻譯 / 旁白 / 大綱…）能跑在本機 Ollama，老師可**零雲端成本**自架
    （與翻譯層 ``core/translate.py`` 已驗過的 Ollama 路徑一脈相承）。``generate_text``
    走 F9-3a 抽出的共用 helper ``core.ollama_client.ollama_generate``（單一真實來源，
    與翻譯層共用同一條本機呼叫線，不重複實作 urllib）。

    本刀（F9-3b）**只把座位坐進去、不改任何現有呼叫端行為**：provider 已登記、可被
    ``get_provider('ollama')`` 取得，但 ``DEFAULTS`` 仍恆雲端——要把角色指到本機需
    F9-3c（``model_roles`` 帶 provider）/ F9-3d（自動退雲端）後續刀，本刀不碰。

    刻意不做（對齊 RFC 範圍）：
    - **不記雲端用量**：本機 provider 不燒額度，是賣點本身；故 **不呼叫
      ``record_text_now``**，不把本機呼叫混進雲端成本帳（避免成本面板誤計）。
    - ``generate_image`` / ``tts`` → ``NotImplementedError``：本機生圖（SD/Flux）與
      語音（F5-TTS 走獨立 ``tts_backend``）各有專屬子系統，不混進 LLM provider。
    """

    name = PROVIDER_OLLAMA

    def __init__(self, *, host: str | None = None) -> None:
        # host 不傳則由 ollama_generate 走預設（OLLAMA_HOST env / localhost:11434）。
        self._host = host

    def generate_text(self, prompt: str, *, model: str | None = None,
                      temperature: float = 0.4, station: str = "text") -> str:
        """打本機 Ollama 產文字。``model`` 為本機模型 id（如 ``translategemma`` /
        ``qwen2.5``），由角色登錄表 ``resolve()`` 帶入（F9-3c 接線後）。

        本機 provider **沒有合理的雲端預設可退**——``model`` 未指定即 ``ValueError``
        （type guard，禁止默默拿錯 id 打本機）。``temperature`` 暫不轉發（F9-3a 共用
        helper 沿用翻譯層路徑、尚未帶 sampling options，待後續刀視需要再加）。
        """
        if not (isinstance(model, str) and model.strip()):
            raise ValueError(
                "OllamaProvider.generate_text 需指定本機模型 id（如 'translategemma'）；"
                "本機 provider 無雲端預設可退。"
            )
        kwargs = {"model": model.strip()}
        if self._host is not None:
            kwargs["host"] = self._host
        return ollama_generate(prompt, **kwargs)

    def generate_image(self, prompt: str, *, model: str | None = None,
                       station: str = "visual", files=None,
                       api_key: str | None = None) -> str:
        raise NotImplementedError(
            "OllamaProvider 不負責生圖；本機生圖（SD/Flux）為獨立重型子系統，"
            "不在 LLM provider registry。"
        )

    def tts(self, text: str, out_path) -> bool:
        raise NotImplementedError(
            "OllamaProvider 不負責 TTS；語音合成走獨立的 tts_backend 子系統"
            "（F5-TTS 本就本機）。"
        )


# ── provider registry（B 階段新增實作只要 register_provider）──
_REGISTRY: dict[str, Provider] = {}


def register_provider(provider: Provider) -> None:
    """登記一個 provider（key = ``provider.name``）。重複名稱以後者覆蓋。"""
    _REGISTRY[provider.name] = provider


def get_provider(name: str) -> Provider:
    """依 provider 名取實作；未知 → ``ValueError``（type guard）。

    A 階段只登記 ``gemini``。TTS 後端（``edge`` / ``f5`` / ``google``）走獨立的
    ``tts_backend`` 子系統，**不**在此 registry。
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "（無）"
        raise ValueError(
            f"未知 provider {name!r}；已登記：{known}。"
            "（TTS 後端走 tts_backend 子系統，不在此 registry）"
        ) from None


def provider_for_role(role: str):
    """角色 → ``(provider 實作, model_id)``，給未來呼叫端用的 B-ready 座位。

    ``resolve(role)`` 拿到 ``(provider 名, model_id)``，再以 provider 名取實作。
    role 非法 → ``resolve`` 拋 ``ValueError``；provider 未登記（如 tts）→
    ``get_provider`` 拋 ``ValueError``。
    """
    provider_name, model_id = resolve(role)
    return get_provider(provider_name), model_id


# A 階段預設登記：gemini（單例，無注入 client，呼叫時延遲建真實 client）。
register_provider(GeminiProvider())
# B 階段（F9-3）座位：ollama 已就緒可被取得，但 DEFAULTS 仍恆雲端——把角色指到本機
# 需 F9-3c（model_roles 帶 provider）後續刀，本登記本身不改任何現有呼叫端行為。
register_provider(OllamaProvider())
