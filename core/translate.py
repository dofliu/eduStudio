"""雙語字幕翻譯層 — 把 narration 翻成第二語言,預設用雲端 Gemini。

劉老師 2026-06-04 定案(推翻當天稍早的 Ollama 決定): 翻譯後端**預設改用雲端
Gemini API**。理由: 解除「全系統須本地」限制讓 core/RAG/Shell 能上雲;且 autoSolver
本就用 Gemini(Vision 讀題、outline、diagram),Ollama 本地翻譯是整個棧唯一的本地 AI
異類。narration / bullet 級文字用量小,成本可忽略。產出的 `narration_secondary`
餵 core.srt.build_bilingual_srt_tracks 出第二語言 SRT 軌(格式 B, 雙獨立軌)。

後端切換: 環境變數 TRANSLATION_BACKEND(預設 'gemini')。設 'ollama' 走本機
translategemma fallback(保留一個 release 週期作離線退路);Ollama 路徑用標準庫
urllib 打 /api/generate,需本機 `ollama serve` 且已 `ollama pull translategemma`。

語言碼 canonical = 'zh-TW'(BCP-47 連字號);底線式 zh_TW 只在 translateGemma 服務
邊界出現,本模組一律用連字號。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from core.config import get_gemini_api_key, get_gemini_model

# 翻譯後端切換: 預設 gemini,設 TRANSLATION_BACKEND=ollama 走本機 fallback。
_BACKEND_ENV = "TRANSLATION_BACKEND"


def _resolve_backend() -> str:
    return os.environ.get(_BACKEND_ENV, "gemini").strip().lower()


# Ollama fallback 設定(標準庫 urllib, 不加 pip dep)。
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = "translategemma"

# target_lang code → prompt 用的語言全名。canonical 用 BCP-47 連字號(zh-TW)。
_LANG_NAMES = {
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "zh": "Chinese (Simplified)",
    "zh-TW": "Traditional Chinese",  # canonical 連字號;不接受底線式 zh_TW
}


class TranslateError(RuntimeError):
    """翻譯呼叫失敗(Gemini 金鑰缺 / API 錯,或 Ollama 服務沒開 / 模型缺 / 逾時)。"""


def _lang_name(target_lang: str) -> str:
    return _LANG_NAMES.get(target_lang, target_lang)


def _build_prompt(text: str, target_lang: str) -> str:
    """通用翻譯 instruction prompt(繁中 → 目標語)。Gemini / Ollama 共用。"""
    return (
        f"Translate the following Traditional Chinese text to {_lang_name(target_lang)}. "
        f"Output only the translation, no explanation, no quotes:\n\n{text}"
    )


def translate_with_gemini(
    text: str | None,
    *,
    target_lang: str = "zh-TW",
    api_key: str | None = None,
) -> str:
    """用雲端 Gemini 翻譯一段文字到 target_lang。空 / None 原樣回 ""(不浪費呼叫)。

    沿用本 repo 既有 Gemini 呼叫模式(outliner.py / diagram_gen.py):
    `from google import genai` → `genai.Client(api_key=)` → `client.models.generate_content`。
    溫度壓低(0.1)讓翻譯穩定。例外統一包成 TranslateError,且**不把 api_key 寫進訊息**(防外洩)。
    """
    text = (text or "").strip()
    if not text:
        return ""
    key = api_key or get_gemini_api_key()
    if not key:
        raise TranslateError("缺少 GEMINI_API_KEY 環境變數(或傳 api_key)")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    try:
        resp = client.models.generate_content(
            model=get_gemini_model(),
            contents=[_build_prompt(text, target_lang)],
            config=types.GenerateContentConfig(temperature=0.1),
        )
    except Exception as e:  # SDK 各種 API 錯統一包成 TranslateError(不洩 key)
        raise TranslateError(f"Gemini 翻譯失敗: {e}") from e
    return (resp.text or "").strip()


def _call_ollama(
    prompt: str,
    *,
    model: str,
    host: str,
    timeout: float,
) -> str:
    """打 Ollama /api/generate(非串流), 回 response 字串。失敗丟 TranslateError。

    fallback 路徑(TRANSLATION_BACKEND=ollama 時才走);預設後端為 Gemini。
    """
    url = host.rstrip("/") + "/api/generate"
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise TranslateError(
            f"Ollama 呼叫失敗 ({url}): {e}. "
            f"確認 `ollama serve` 已跑且已 `ollama pull {model}`."
        ) from e
    except json.JSONDecodeError as e:
        raise TranslateError(f"Ollama 回傳非 JSON ({url}): {e}") from e
    return (data.get("response") or "").strip()


def translate_text(
    text: str | None,
    *,
    target_lang: str = "zh-TW",
    backend: str | None = None,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    timeout: float = 60.0,
) -> str:
    """翻譯一段文字到 target_lang。空 / None 原樣回 ""(不浪費呼叫)。

    backend 預設讀 TRANSLATION_BACKEND(預設 'gemini');'ollama' 走本機 fallback。
    model / host / timeout 只在 ollama backend 生效(gemini 不用)。
    """
    text = (text or "").strip()
    if not text:
        return ""
    backend = backend or _resolve_backend()
    if backend == "ollama":
        return _call_ollama(
            _build_prompt(text, target_lang), model=model, host=host, timeout=timeout
        )
    return translate_with_gemini(text, target_lang=target_lang, api_key=api_key)


def translate_steps(
    steps: list[dict],
    *,
    target_lang: str = "zh-TW",
    field: str = "narration",
    out_field: str = "narration_secondary",
    backend: str | None = None,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    timeout: float = 60.0,
) -> list[dict]:
    """逐 step 翻譯 `field` → 填 `out_field`, 回新 list (不就地改傳入 dict)。

    - 空 narration 的 step 跳過 (不寫 out_field) → build_bilingual_srt_tracks 對
      缺 out_field 的 step 第二軌無 cue, 時間軸仍對齊 (向後相容)。
    - 已有非空 out_field 的 step 跳過 (idempotent: 不重複翻譯 / 不覆蓋人工修過的)。
    - 任一 step 翻譯失敗會讓 TranslateError 往上拋 (呼叫端決定是否整批中止) —
      不靜默吞掉, 避免「以為翻好了其實半套」。
    """
    out: list[dict] = []
    for step in steps:
        new = dict(step)
        src = (new.get(field) or "").strip()
        existing = (new.get(out_field) or "").strip()
        if src and not existing:
            new[out_field] = translate_text(
                src,
                target_lang=target_lang,
                backend=backend,
                api_key=api_key,
                model=model,
                host=host,
                timeout=timeout,
            )
        out.append(new)
    return out
