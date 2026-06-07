"""core/whisper_util — 模型載入 fallback（cuda→cpu）。mock WhisperModel,不載真模型。"""
from __future__ import annotations

import sys
import types

import pytest


def _fake_faster_whisper(monkeypatch, fail_devices=()):
    """注入假 faster_whisper.WhisperModel，記錄被以哪個 device 建立。"""
    calls = []

    class _FakeModel:
        def __init__(self, name, device="cpu", compute_type="int8"):
            calls.append((name, device, compute_type))
            if device in fail_devices:
                raise RuntimeError(f"{device} unavailable")

    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = _FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)
    return calls


def test_prefers_cuda(monkeypatch):
    from core.whisper_util import load_whisper_model
    calls = _fake_faster_whisper(monkeypatch)
    load_whisper_model()
    assert calls[0][1] == "cuda" and calls[0][0] == "large-v3"   # 先試 cuda + large-v3


def test_falls_back_to_cpu(monkeypatch):
    from core.whisper_util import load_whisper_model
    calls = _fake_faster_whisper(monkeypatch, fail_devices=("cuda",))
    load_whisper_model()
    assert [c[1] for c in calls] == ["cuda", "cpu"]   # cuda 失敗 → 退 cpu


def test_env_overrides_model_and_device(monkeypatch):
    from core.whisper_util import load_whisper_model
    monkeypatch.setenv("WHISPER_MODEL", "base")
    monkeypatch.setenv("WHISPER_DEVICE", "cpu")
    calls = _fake_faster_whisper(monkeypatch)
    load_whisper_model()
    assert calls == [("base", "cpu", "int8")]   # env 強制 base + cpu，不試 cuda


def test_raises_when_all_fail(monkeypatch):
    from core.whisper_util import load_whisper_model
    _fake_faster_whisper(monkeypatch, fail_devices=("cuda", "cpu"))
    with pytest.raises(RuntimeError):
        load_whisper_model()
