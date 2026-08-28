"""共用 faster-whisper 模型載入器。

為什麼集中：原本 meeting/dubber/translation 各自 hardcode `WhisperModel("base",
device="cpu", compute_type="int8")`。現在統一預設 large-v3，並優先走 GPU；模型若尚未
存在於 Hugging Face cache，faster-whisper 會在第一次使用時下載。

模型/裝置可用 env 覆寫：WHISPER_MODEL、WHISPER_DEVICE。
"""
from __future__ import annotations

import os
from pathlib import Path

# 預設 large-v3；實際 cache 狀態由 get_whisper_model_status() 動態檢查。
_DEFAULT_MODEL = "large-v3"


def get_whisper_model_name() -> str:
    """目前會載入的模型名稱（供 health/selfcheck 與 loader 共用）。"""
    return os.environ.get("WHISPER_MODEL") or _DEFAULT_MODEL


def get_whisper_model_status() -> dict:
    """不觸發下載地檢查 faster-whisper model 是否已在本機完整 cache。"""
    name = get_whisper_model_name()
    model_path = Path(name)
    cached_path = ""
    if model_path.is_dir():
        candidate = model_path / "model.bin"
        if candidate.is_file() and candidate.stat().st_size > 0:
            cached_path = str(candidate)
    else:
        try:
            from huggingface_hub import try_to_load_from_cache

            candidate = try_to_load_from_cache(
                f"Systran/faster-whisper-{name}", "model.bin")
            if (
                isinstance(candidate, str)
                and Path(candidate).is_file()
                and Path(candidate).stat().st_size > 0
            ):
                cached_path = candidate
        except Exception:
            cached_path = ""
    return {
        "model": name,
        "cached": bool(cached_path),
        "device_preference": os.environ.get("WHISPER_DEVICE") or "cuda_then_cpu",
    }


def load_whisper_model(model: str | None = None):
    """載 faster-whisper 模型：依序試 cuda(float16) → cpu(int8)，回第一個成功的。

    model 未給時用 env WHISPER_MODEL 或預設 large-v3。指定 WHISPER_DEVICE=cpu 可強制 cpu。
    全失敗才把最後的例外丟出（呼叫端原本就會 graceful 處理）。
    """
    from faster_whisper import WhisperModel

    name = model or get_whisper_model_name()
    forced = os.environ.get("WHISPER_DEVICE")
    candidates = [("cpu", "int8")] if forced == "cpu" else [("cuda", "float16"), ("cpu", "int8")]
    last_err: Exception | None = None
    for dev, ct in candidates:
        try:
            return WhisperModel(name, device=dev, compute_type=ct)
        except Exception as e:  # cuda 不可用 / 模型缺 → 試下一個
            last_err = e
    raise last_err if last_err else RuntimeError("無法載入 whisper 模型")
