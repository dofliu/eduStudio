"""共用 faster-whisper 模型載入器。

為什麼集中：原本 meeting/dubber/translation 各自 hardcode `WhisperModel("base",
device="cpu", compute_type="int8")`。但本機 base 模型 snapshot 不完整且抓不回來
（HF head-call error），而 large-v3 已完整 cache → 改用 large-v3，並優先走 GPU
（劉老師 RTX 4080，large-v3 在 cuda 約 2 秒轉一段，cpu 要 ~28 秒）。

模型/裝置可用 env 覆寫：WHISPER_MODEL、WHISPER_DEVICE。
"""
from __future__ import annotations

import os

# 預設 large-v3：本機已完整 cache；base snapshot 殘缺且 HF 抓不回。
_DEFAULT_MODEL = "large-v3"


def load_whisper_model(model: str | None = None):
    """載 faster-whisper 模型：依序試 cuda(float16) → cpu(int8)，回第一個成功的。

    model 未給時用 env WHISPER_MODEL 或預設 large-v3。指定 WHISPER_DEVICE=cpu 可強制 cpu。
    全失敗才把最後的例外丟出（呼叫端原本就會 graceful 處理）。
    """
    from faster_whisper import WhisperModel

    name = model or os.environ.get("WHISPER_MODEL") or _DEFAULT_MODEL
    forced = os.environ.get("WHISPER_DEVICE")
    candidates = [("cpu", "int8")] if forced == "cpu" else [("cuda", "float16"), ("cpu", "int8")]
    last_err: Exception | None = None
    for dev, ct in candidates:
        try:
            return WhisperModel(name, device=dev, compute_type=ct)
        except Exception as e:  # cuda 不可用 / 模型缺 → 試下一個
            last_err = e
    raise last_err if last_err else RuntimeError("無法載入 whisper 模型")
