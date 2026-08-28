"""共用 faster-whisper 模型載入器。

為什麼集中：原本 meeting/dubber/translation 各自 hardcode `WhisperModel("base",
device="cpu", compute_type="int8")`。現在統一預設 large-v3，並優先走 GPU；模型若尚未
存在於 Hugging Face cache，faster-whisper 會在第一次使用時下載。

模型/裝置可用 env 覆寫：WHISPER_MODEL、WHISPER_DEVICE。模型 cache 依 Hugging Face
官方優先序讀取 HF_HUB_CACHE／HF_HOME／XDG_CACHE_HOME，讓整包 cache 搬到新電腦後
不必依賴 import-time 全域常數或重新下載。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

# 預設 large-v3；實際 cache 狀態由 get_whisper_model_status() 動態檢查。
_DEFAULT_MODEL = "large-v3"
_REQUIRED_MODEL_FILES = ("model.bin", "config.json")


def get_whisper_model_name() -> str:
    """目前會載入的模型名稱（供 health/selfcheck 與 loader 共用）。"""
    return os.environ.get("WHISPER_MODEL") or _DEFAULT_MODEL


def _is_complete_model_dir(path: Path) -> bool:
    """只把可實際載入的 snapshot 視為 cache，避免半下載檔案回報 cached=true。"""
    if not path.is_dir():
        return False
    if not all((path / name).is_file() and (path / name).stat().st_size > 0
               for name in _REQUIRED_MODEL_FILES):
        return False
    return any(
        (path / name).is_file() and (path / name).stat().st_size > 0
        for name in ("tokenizer.json", "vocabulary.json")
    )


def _hf_hub_roots() -> Iterator[tuple[Path, str]]:
    """動態解析 Hugging Face cache；env 在 process 啟動後設定也能被 health 看見。"""
    candidates: list[tuple[Path, str]] = []
    if value := os.environ.get("HF_HUB_CACHE"):
        candidates.append((Path(value).expanduser(), "HF_HUB_CACHE"))
    # 舊名稱仍接受，方便既有電腦遷移；新設定一律建議 HF_HUB_CACHE。
    if value := os.environ.get("HUGGINGFACE_HUB_CACHE"):
        candidates.append((Path(value).expanduser(), "HUGGINGFACE_HUB_CACHE"))
    if value := os.environ.get("HF_HOME"):
        candidates.append((Path(value).expanduser() / "hub", "HF_HOME"))
    elif value := os.environ.get("XDG_CACHE_HOME"):
        candidates.append((Path(value).expanduser() / "huggingface" / "hub", "XDG_CACHE_HOME"))
    else:
        candidates.append((Path.home() / ".cache" / "huggingface" / "hub", "default"))

    seen: set[str] = set()
    for root, source in candidates:
        key = os.path.normcase(str(root.resolve(strict=False)))
        if key not in seen:
            seen.add(key)
            yield root, source


def _repo_cache_name(model: str) -> str:
    repo_id = model if "/" in model else f"Systran/faster-whisper-{model}"
    return "models--" + repo_id.replace("/", "--")


def resolve_whisper_model_source(model: str | None = None) -> tuple[Path | None, str]:
    """回傳完整本機 model directory 與來源；找不到時不觸發網路。"""
    name = model or get_whisper_model_name()
    explicit = Path(name).expanduser()
    if explicit.is_dir():
        return (explicit.resolve(), "explicit_model_path") if _is_complete_model_dir(explicit) else (None, "explicit_incomplete")

    repo_name = _repo_cache_name(name)
    for hub_root, source in _hf_hub_roots():
        repo_root = hub_root / repo_name
        snapshots = repo_root / "snapshots"
        preferred: list[Path] = []
        main_ref = repo_root / "refs" / "main"
        try:
            revision = main_ref.read_text(encoding="utf-8").strip()
            if revision:
                preferred.append(snapshots / revision)
        except OSError:
            pass
        if snapshots.is_dir():
            try:
                preferred.extend(sorted(
                    (p for p in snapshots.iterdir() if p.is_dir()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ))
            except OSError:
                pass
        seen: set[Path] = set()
        for candidate in preferred:
            resolved = candidate.resolve(strict=False)
            if resolved in seen:
                continue
            seen.add(resolved)
            if _is_complete_model_dir(candidate):
                return candidate.resolve(), source
    return None, "not_cached"


def get_whisper_model_status() -> dict:
    """不觸發下載地檢查 faster-whisper model 是否已在本機完整 cache。"""
    name = get_whisper_model_name()
    cached_path, cache_source = resolve_whisper_model_source(name)
    return {
        "model": name,
        "cached": cached_path is not None,
        "cache_source": cache_source,
        "device_preference": os.environ.get("WHISPER_DEVICE") or "cuda_then_cpu",
    }


def load_whisper_model(model: str | None = None):
    """載 faster-whisper 模型：依序試 cuda(float16) → cpu(int8)，回第一個成功的。

    model 未給時用 env WHISPER_MODEL 或預設 large-v3。指定 WHISPER_DEVICE=cpu 可強制 cpu。
    全失敗才把最後的例外丟出（呼叫端原本就會 graceful 處理）。
    """
    from faster_whisper import WhisperModel

    name = model or get_whisper_model_name()
    cached_path, _ = resolve_whisper_model_source(name)
    source = str(cached_path) if cached_path is not None else name
    forced = os.environ.get("WHISPER_DEVICE")
    candidates = [("cpu", "int8")] if forced == "cpu" else [("cuda", "float16"), ("cpu", "int8")]
    last_err: Exception | None = None
    for dev, ct in candidates:
        try:
            return WhisperModel(source, device=dev, compute_type=ct)
        except Exception as e:  # cuda 不可用 / 模型缺 → 試下一個
            last_err = e
    raise last_err if last_err else RuntimeError("無法載入 whisper 模型")
