"""雙語字幕翻譯層 — 呼叫本機 Ollama translategemma 把 narration 翻成第二語言。

劉老師 2026-06-04 決定: 翻譯後端用**本機 Ollama** translategemma (不是雲端
Gemini / GCP) → 本機推論不燒雲端額度, offline-first 約束不擋。產出的
`narration_secondary` 餵 core.srt.build_bilingual_srt_tracks 出第二語言 SRT 軌
(格式 B, 雙獨立軌)。第二語言字幕軌**跳過 review** (用戶授權, 屬附加產出);
中文主軌的 require_review 不動 (學術誠信底線)。

只用標準庫 urllib 打 Ollama HTTP API (/api/generate), **不加 pip dep**。Ollama
服務需在本機跑 (`ollama serve`) 且已 `ollama pull translategemma`。

注意 (待劉老師本機實測調整): translategemma 的最佳 prompt 格式我未實測, 這裡
用通用 instruction prompt + 可配置 (translate_text 的 prompt_template), 本機跑
過確認翻譯品質後再調 _build_prompt 預設。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# Ollama 標準 env (OLLAMA_HOST), 退預設本機 port
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = "translategemma"

# target_lang code → prompt 用的語言全名
_LANG_NAMES = {
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}


class TranslateError(RuntimeError):
    """Ollama 呼叫失敗 (服務沒開 / 模型缺 / 逾時 / 回傳異常)。"""


def _lang_name(target_lang: str) -> str:
    return _LANG_NAMES.get(target_lang, target_lang)


def _build_prompt(text: str, target_lang: str) -> str:
    """通用翻譯 instruction prompt (繁中 → 目標語)。待本機對 translategemma 實測調整。"""
    return (
        f"Translate the following Traditional Chinese text to {_lang_name(target_lang)}. "
        f"Output only the translation, no explanation, no quotes:\n\n{text}"
    )


def _call_ollama(
    prompt: str,
    *,
    model: str,
    host: str,
    timeout: float,
) -> str:
    """打 Ollama /api/generate (非串流), 回 response 字串。失敗丟 TranslateError。"""
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
    target_lang: str = "en",
    model: str = DEFAULT_MODEL,
    host: str = DEFAULT_OLLAMA_HOST,
    timeout: float = 60.0,
) -> str:
    """翻譯一段文字到 target_lang。空 / None 原樣回 "" (不浪費呼叫)。"""
    text = (text or "").strip()
    if not text:
        return ""
    return _call_ollama(
        _build_prompt(text, target_lang), model=model, host=host, timeout=timeout
    )


def translate_steps(
    steps: list[dict],
    *,
    target_lang: str = "en",
    field: str = "narration",
    out_field: str = "narration_secondary",
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
                src, target_lang=target_lang, model=model, host=host, timeout=timeout
            )
        out.append(new)
    return out
