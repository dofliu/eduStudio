"""pipeline._get_tts_backend — tts_config 改過要重載（修『換聲音不生效』）。"""
from __future__ import annotations

import pipeline


def test_reloads_when_tts_config_mtime_changes(monkeypatch):
    """換聲音(tts_config mtime 變)→ 重載 backend；同 mtime → 沿用快取。"""
    loads = []
    monkeypatch.setattr(pipeline, "load_tts_backend", lambda: (loads.append(1), object())[1])
    pipeline._TTS_BACKEND = None
    pipeline._TTS_CONFIG_MTIME = None
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


def test_missing_config_still_loads_once(monkeypatch):
    """tts_config 不存在(getmtime OSError)→ 仍載一次，不炸。"""
    loads = []
    monkeypatch.setattr(pipeline, "load_tts_backend", lambda: (loads.append(1), object())[1])
    pipeline._TTS_BACKEND = None
    pipeline._TTS_CONFIG_MTIME = None

    def _boom(p):
        raise OSError("no file")
    monkeypatch.setattr(pipeline.os.path, "getmtime", _boom)

    pipeline._get_tts_backend()
    pipeline._get_tts_backend()
    assert len(loads) >= 1

    pipeline._TTS_BACKEND = None
    pipeline._TTS_CONFIG_MTIME = None
