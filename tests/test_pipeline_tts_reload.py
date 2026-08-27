"""pipeline._get_tts_backend — tts_config 改過要重載（修『換聲音不生效』）。"""
from __future__ import annotations

import pipeline


def test_reloads_when_tts_config_mtime_changes(monkeypatch):
    """換聲音(tts_config mtime 變)→ 重載 backend；同 mtime → 沿用快取。"""
    loads = []
    monkeypatch.setattr(pipeline, "load_tts_backend", lambda: (loads.append(1), object())[1])
    pipeline._TTS_BACKEND = None
    pipeline._TTS_CONFIG_MTIME = None
    pipeline._TTS_PROVIDER_KEY = None
    monkeypatch.delenv("TTS_PROVIDER", raising=False)
    times = iter([100.0, 100.0, 200.0])
    monkeypatch.setattr(pipeline.os.path, "getmtime", lambda p: next(times))

    b1 = pipeline._get_tts_backend()   # mtime 100 → load
    b2 = pipeline._get_tts_backend()   # mtime 100 → 快取
    b3 = pipeline._get_tts_backend()   # mtime 200 → 重載

    assert len(loads) == 2            # 只在第 1 次與 mtime 變時載
    assert b1 is b2                   # 同 config 沿用同一 backend
    assert b3 is not b1               # 換聲音後是新 backend

    pipeline._TTS_BACKEND = None
    pipeline._TTS_CONFIG_MTIME = None
    pipeline._TTS_PROVIDER_KEY = None


def test_missing_config_still_loads_once(monkeypatch):
    """tts_config 不存在(getmtime OSError)→ 仍載一次，不炸。"""
    loads = []
    monkeypatch.setattr(pipeline, "load_tts_backend", lambda: (loads.append(1), object())[1])
    pipeline._TTS_BACKEND = None
    pipeline._TTS_CONFIG_MTIME = None
    pipeline._TTS_PROVIDER_KEY = None
    monkeypatch.delenv("TTS_PROVIDER", raising=False)

    def _boom(p):
        raise OSError("no file")
    monkeypatch.setattr(pipeline.os.path, "getmtime", _boom)

    pipeline._get_tts_backend()
    pipeline._get_tts_backend()
    assert len(loads) >= 1

    pipeline._TTS_BACKEND = None
    pipeline._TTS_CONFIG_MTIME = None
    pipeline._TTS_PROVIDER_KEY = None


def test_reloads_when_per_job_provider_changes(monkeypatch):
    """同一長駐 server 由 F5 job 切到 Edge job時，backend cache 必須失效。"""
    loads = []
    monkeypatch.setattr(pipeline, "load_tts_backend", lambda: (loads.append(1), object())[1])
    monkeypatch.setattr(pipeline.os.path, "getmtime", lambda p: 100.0)
    pipeline._TTS_BACKEND = None
    pipeline._TTS_CONFIG_MTIME = None
    pipeline._TTS_PROVIDER_KEY = None

    monkeypatch.setenv("TTS_PROVIDER", "f5")
    first = pipeline._get_tts_backend()
    monkeypatch.setenv("TTS_PROVIDER", "edge")
    second = pipeline._get_tts_backend()

    assert len(loads) == 2
    assert second is not first

    pipeline._TTS_BACKEND = None
    pipeline._TTS_CONFIG_MTIME = None
    pipeline._TTS_PROVIDER_KEY = None
