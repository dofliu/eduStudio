"""本機 Ollama 文字生成的單一真實來源（F9-3a）。

把打 Ollama ``/api/generate`` 的標準庫 ``urllib`` 呼叫從 ``core/translate.py`` 抽出來,
讓翻譯層(``core/translate.py``)與未來的 ``OllamaProvider``(F9-3b, ``core/providers.py``)
**共用同一條本機文字呼叫線**——單一真實來源, 零 pip 依賴(只用標準庫 ``urllib``)。

設計沿用 ``translate.py`` 既有路徑: 非串流 POST、失敗在訊息裡指引 ``ollama serve`` /
``ollama pull <model>`` 修法。``OllamaError`` 為**領域中立**的錯誤型別; 呼叫端
(翻譯層 / provider 層)各自把它包成自己的領域例外(如 ``TranslateError``), 本模組不
綁任何上層語意。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

# 本機 Ollama 服務位址(沿用既有 OLLAMA_HOST env, 零 pip 依賴)。
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_TIMEOUT = 60.0


class OllamaError(RuntimeError):
    """本機 Ollama 呼叫失敗(服務沒開 / 模型沒 pull / 逾時 / 回傳非 JSON)。

    領域中立: 呼叫端(翻譯層 / provider 層)自行包成各自的領域例外。
    """


def ollama_generate(
    prompt: str,
    *,
    model: str,
    host: str = DEFAULT_OLLAMA_HOST,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """打 Ollama ``/api/generate``(非串流), 回 ``response`` 字串。失敗丟 ``OllamaError``。

    單一真實來源: ``translate.py`` 與 ``OllamaProvider`` 共用此函式, 不各自實作 urllib 呼叫。
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
        raise OllamaError(
            f"Ollama 呼叫失敗 ({url}): {e}. "
            f"確認 `ollama serve` 已跑且已 `ollama pull {model}`."
        ) from e
    except json.JSONDecodeError as e:
        raise OllamaError(f"Ollama 回傳非 JSON ({url}): {e}") from e
    return (data.get("response") or "").strip()
