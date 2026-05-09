"""server.routes.voices 測試 — 聲音設定 read/write (PR-3l)。

monkeypatch TTS_CONFIG_PATH 隔離真實的 tts_config.json, 不污染 user 設定。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import server.routes.voices as voices_mod
from server.routes.voices import (
    VOICE_IDS,
    VOICES,
    _read_current_voice,
    _write_current_voice,
)


@pytest.fixture
def fake_tts_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """每個 test 自己的 tts_config.json, 預設是 edge backend + HsiaoChen."""
    cfg_path = tmp_path / "tts_config.json"
    cfg_path.write_text(json.dumps({
        "backend": "edge",
        "edge": {"voice": "zh-TW-HsiaoChenNeural", "rate": "-5%"},
        "f5": {"ref_audio": "voices/teacher_ref.wav"},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(voices_mod, "TTS_CONFIG_PATH", cfg_path)
    return cfg_path


# ---------- VOICES list ----------

class TestVoicesList:
    def test_six_voices(self):
        # 5 edge + 1 F5
        assert len(VOICES) == 6

    def test_voice_ids_unique(self):
        ids = [v["id"] for v in VOICES]
        assert len(ids) == len(set(ids))

    def test_each_voice_has_required_fields(self):
        for v in VOICES:
            assert "id" in v and v["id"]
            assert "label" in v and v["label"]
            assert "sample" in v and v["sample"].endswith(".mp3")

    def test_has_one_f5_voice(self):
        f5_voices = [v for v in VOICES if v["id"].startswith("f5:")]
        assert len(f5_voices) == 1


# ---------- _read_current_voice ----------

class TestReadCurrentVoice:
    def test_reads_edge_voice(self, fake_tts_config):
        assert _read_current_voice() == "zh-TW-HsiaoChenNeural"

    def test_reads_f5_when_backend_f5(self, fake_tts_config):
        # 改 cfg 為 f5 backend
        cfg = json.loads(fake_tts_config.read_text(encoding="utf-8"))
        cfg["backend"] = "f5"
        fake_tts_config.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        assert _read_current_voice() == "f5:teacher"

    def test_returns_default_when_no_config(self, tmp_path, monkeypatch):
        # 沒 tts_config.json 也不爆, 回第一個 voice
        monkeypatch.setattr(voices_mod, "TTS_CONFIG_PATH", tmp_path / "missing.json")
        result = _read_current_voice()
        assert result == VOICES[0]["id"]

    def test_returns_default_when_corrupt(self, fake_tts_config):
        fake_tts_config.write_text("not json", encoding="utf-8")
        result = _read_current_voice()
        assert result == VOICES[0]["id"]


# ---------- _write_current_voice ----------

class TestWriteCurrentVoice:
    def test_write_edge_voice_updates_cfg(self, fake_tts_config):
        ok = _write_current_voice("zh-CN-YunyangNeural")
        assert ok is True
        cfg = json.loads(fake_tts_config.read_text(encoding="utf-8"))
        assert cfg["backend"] == "edge"
        assert cfg["edge"]["voice"] == "zh-CN-YunyangNeural"

    def test_write_f5_voice_switches_backend(self, fake_tts_config):
        ok = _write_current_voice("f5:teacher")
        assert ok is True
        cfg = json.loads(fake_tts_config.read_text(encoding="utf-8"))
        assert cfg["backend"] == "f5"

    def test_write_f5_preserves_f5_subblock(self, fake_tts_config):
        # 切 f5 不該動 f5 區塊 (ref_audio / ref_text 等使用者參數)
        before = json.loads(fake_tts_config.read_text(encoding="utf-8"))["f5"]
        _write_current_voice("f5:teacher")
        after = json.loads(fake_tts_config.read_text(encoding="utf-8"))["f5"]
        assert after == before

    def test_write_unknown_voice_returns_false(self, fake_tts_config):
        ok = _write_current_voice("fake-voice")
        assert ok is False
        # cfg 不該被改
        cfg = json.loads(fake_tts_config.read_text(encoding="utf-8"))
        assert cfg["edge"]["voice"] == "zh-TW-HsiaoChenNeural"

    def test_round_trip(self, fake_tts_config):
        # write → read 應該回到同一個 voice
        _write_current_voice("zh-CN-XiaoxiaoNeural")
        assert _read_current_voice() == "zh-CN-XiaoxiaoNeural"
        _write_current_voice("f5:teacher")
        assert _read_current_voice() == "f5:teacher"
