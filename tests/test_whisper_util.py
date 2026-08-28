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


def _force_uncached(monkeypatch):
    from core import whisper_util
    monkeypatch.setattr(
        whisper_util, "resolve_whisper_model_source",
        lambda model=None: (None, "not_cached"),
    )


def _make_snapshot(root, model="large-v3"):
    snapshot = root / "hub" / f"models--Systran--faster-whisper-{model}" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "model.bin").write_bytes(b"model")
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "tokenizer.json").write_text("{}", encoding="utf-8")
    return snapshot


def test_prefers_cuda(monkeypatch):
    from core.whisper_util import load_whisper_model
    _force_uncached(monkeypatch)
    calls = _fake_faster_whisper(monkeypatch)
    load_whisper_model()
    assert calls[0][1] == "cuda" and calls[0][0] == "large-v3"   # 先試 cuda + large-v3


def test_falls_back_to_cpu(monkeypatch):
    from core.whisper_util import load_whisper_model
    _force_uncached(monkeypatch)
    calls = _fake_faster_whisper(monkeypatch, fail_devices=("cuda",))
    load_whisper_model()
    assert [c[1] for c in calls] == ["cuda", "cpu"]   # cuda 失敗 → 退 cpu


def test_env_overrides_model_and_device(monkeypatch):
    from core.whisper_util import load_whisper_model
    _force_uncached(monkeypatch)
    monkeypatch.setenv("WHISPER_MODEL", "base")
    monkeypatch.setenv("WHISPER_DEVICE", "cpu")
    calls = _fake_faster_whisper(monkeypatch)
    load_whisper_model()
    assert calls == [("base", "cpu", "int8")]   # env 強制 base + cpu，不試 cuda


def test_raises_when_all_fail(monkeypatch):
    from core.whisper_util import load_whisper_model
    _force_uncached(monkeypatch)
    _fake_faster_whisper(monkeypatch, fail_devices=("cuda", "cpu"))
    with pytest.raises(RuntimeError):
        load_whisper_model()


def test_hf_home_snapshot_is_detected_and_used(tmp_path, monkeypatch):
    from core.whisper_util import get_whisper_model_status, load_whisper_model
    snapshot = _make_snapshot(tmp_path)
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    calls = _fake_faster_whisper(monkeypatch)

    status = get_whisper_model_status()
    load_whisper_model()

    assert status["cached"] is True
    assert status["cache_source"] == "HF_HOME"
    assert calls[0] == (str(snapshot.resolve()), "cuda", "float16")


def test_hf_hub_cache_takes_precedence(tmp_path, monkeypatch):
    from core.whisper_util import resolve_whisper_model_source
    hub = tmp_path / "direct-hub"
    snapshot = _make_snapshot(tmp_path / "ignored")
    direct = hub / snapshot.parent.parent.name / "snapshots" / "direct"
    direct.mkdir(parents=True)
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (direct / name).write_bytes((snapshot / name).read_bytes())
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "wrong-home"))

    resolved, source = resolve_whisper_model_source("large-v3")
    assert resolved == direct.resolve()
    assert source == "HF_HUB_CACHE"


def test_incomplete_snapshot_is_not_reported_cached(tmp_path, monkeypatch):
    from core.whisper_util import get_whisper_model_status
    snapshot = tmp_path / "hub" / "models--Systran--faster-whisper-large-v3" / "snapshots" / "partial"
    snapshot.mkdir(parents=True)
    (snapshot / "model.bin").write_bytes(b"partial")
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)

    status = get_whisper_model_status()
    assert status["cached"] is False
    assert status["cache_source"] == "not_cached"
