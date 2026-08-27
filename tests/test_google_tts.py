"""iter 92: GoogleTTS backend 測試.

不真的 call GCP API (要 service account JSON + 計費), 全部 mock
google.cloud.texttospeech module / client. 驗:
- import 失敗 (沒裝 lib) → synthesize 回 False, 不爆
- 認證失敗 / API 失敗 → 回 False
- 成功路徑: 寫檔, 預設參數正確, fallback 機制觸發
- load_tts_backend(backend="google") 回 FallbackTTS(GoogleTTS, EdgeTTS)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tts_backend import (
    EdgeTTS,
    FallbackTTS,
    GoogleTTS,
    load_tts_backend,
)


def _run(coro):
    """test helper — run async coroutine sync (avoid pytest-asyncio dep)."""
    return asyncio.get_event_loop().run_until_complete(coro) \
        if not asyncio.iscoroutine(coro) else asyncio.run(coro)


class TestGoogleTTSConstruction:
    def test_default_voice_is_zh_tw_wavenet_a(self):
        g = GoogleTTS()
        assert g.voice == "cmn-TW-Wavenet-A"
        assert g.language_code == "zh-TW"
        assert g.speaking_rate == 1.0
        assert g.pitch == 0.0
        assert g.audio_encoding == "MP3"

    def test_custom_voice_param(self):
        g = GoogleTTS(voice="cmn-TW-Wavenet-B", speaking_rate=0.9, pitch=-2.0)
        assert g.voice == "cmn-TW-Wavenet-B"
        assert g.speaking_rate == 0.9
        assert g.pitch == -2.0

    def test_backend_name(self):
        assert GoogleTTS.name == "google"
        assert GoogleTTS().name == "google"

    def test_lazy_client_starts_as_none(self):
        g = GoogleTTS()
        assert g._client is None


class TestGoogleTTSSynthesize:
    def test_empty_text_returns_false(self, tmp_path):
        g = GoogleTTS()
        ok = asyncio.run(g.synthesize("", tmp_path / "out.mp3"))
        assert ok is False
        ok = asyncio.run(g.synthesize("   \n  ", tmp_path / "out.mp3"))
        assert ok is False

    def test_missing_library_returns_false(self, tmp_path, monkeypatch):
        """沒裝 google-cloud-texttospeech → import error → 回 False (不爆)."""
        g = GoogleTTS()
        # 模擬 import 失敗: 把 google.cloud.texttospeech 弄壞
        # 用 sys.modules 注入會 raise ImportError 的假 module
        real_modules = dict(sys.modules)

        def cleanup():
            sys.modules.clear()
            sys.modules.update(real_modules)

        # 直接刪掉, 讓 import 走 importlib 機制找不到
        for k in list(sys.modules):
            if k.startswith("google.cloud.texttospeech"):
                del sys.modules[k]
        # patch importer to raise
        with patch.dict(sys.modules, {"google.cloud.texttospeech": None}):
            try:
                ok = asyncio.run(g.synthesize("你好", tmp_path / "out.mp3"))
                assert ok is False, "lib 失敗該回 False 不爆"
            finally:
                cleanup()

    def test_successful_synthesize_writes_file(self, tmp_path):
        """mock client → 寫出 mp3 → 回 True."""
        g = GoogleTTS()
        # 預先 inject mock client + types module 避開 import
        fake_response = MagicMock()
        fake_response.audio_content = b"FAKE_MP3_BYTES"
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = fake_response
        # _lazy_init 會設 _client / _types — 我們直接預設, 並 patch _lazy_init
        # 成空操作避開 google-cloud-texttospeech import
        g._client = mock_client
        g._types = MagicMock()
        g._types.AudioEncoding.MP3 = "MP3_ENUM"
        # 把 lazy_init 變 noop, 避免真去 import
        with patch.object(g, "_lazy_init"):
            out = tmp_path / "out.mp3"
            ok = asyncio.run(g.synthesize("你好世界", out))
        assert ok is True
        assert out.exists()
        assert out.read_bytes() == b"FAKE_MP3_BYTES"
        # 該有真的呼叫 client
        mock_client.synthesize_speech.assert_called_once()

    def test_api_exception_returns_false(self, tmp_path):
        """API call 拋 exception → 回 False (不擋 pipeline)."""
        g = GoogleTTS()
        mock_client = MagicMock()
        mock_client.synthesize_speech.side_effect = RuntimeError("API quota")
        g._client = mock_client
        g._types = MagicMock()
        with patch.object(g, "_lazy_init"):
            ok = asyncio.run(g.synthesize("test", tmp_path / "out.mp3"))
        assert ok is False


class TestLoadTTSBackend:
    def test_env_override_takes_priority_over_config(self, tmp_path, monkeypatch):
        """per-job TTS_PROVIDER=edge 必須覆蓋持久設定的 f5。"""
        cfg = {"backend": "f5", "f5": {"ref_audio": "x.wav", "ref_text": "hi"}}
        cfg_path = tmp_path / "tts_config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        monkeypatch.setenv("TTS_PROVIDER", "edge")
        assert isinstance(load_tts_backend(cfg_path), EdgeTTS)

    def test_invalid_env_override_fails_explicitly(self, tmp_path, monkeypatch):
        cfg_path = tmp_path / "tts_config.json"
        cfg_path.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("TTS_PROVIDER", "unknown")
        with pytest.raises(ValueError, match="TTS_PROVIDER"):
            load_tts_backend(cfg_path)

    def test_backend_google_returns_fallback_wrapper(self, tmp_path):
        """tts_config.json backend=google → FallbackTTS(GoogleTTS, EdgeTTS)."""
        cfg = {
            "backend": "google",
            "google": {"voice": "cmn-TW-Wavenet-B", "speaking_rate": 0.95},
        }
        cfg_path = tmp_path / "tts_config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        backend = load_tts_backend(cfg_path)
        assert isinstance(backend, FallbackTTS)
        assert isinstance(backend.primary, GoogleTTS)
        assert isinstance(backend.fallback, EdgeTTS)
        assert backend.primary.voice == "cmn-TW-Wavenet-B"
        assert backend.primary.speaking_rate == 0.95

    def test_backend_google_with_no_google_section_uses_defaults(self, tmp_path):
        cfg = {"backend": "google"}
        cfg_path = tmp_path / "tts_config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        backend = load_tts_backend(cfg_path)
        assert isinstance(backend.primary, GoogleTTS)
        assert backend.primary.voice == "cmn-TW-Wavenet-A"

    def test_backend_edge_unchanged(self, tmp_path):
        """既有 backend=edge / 未指定 → 不該有 wrapper."""
        cfg_path = tmp_path / "tts_config.json"
        cfg_path.write_text("{}", encoding="utf-8")
        backend = load_tts_backend(cfg_path)
        assert isinstance(backend, EdgeTTS)

    def test_backend_f5_unchanged(self, tmp_path):
        """既有 f5 路徑沒被新分支影響."""
        cfg = {"backend": "f5", "f5": {"ref_audio": "x.wav", "ref_text": "hi"}}
        cfg_path = tmp_path / "tts_config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        backend = load_tts_backend(cfg_path)
        assert isinstance(backend, FallbackTTS)
        assert backend.primary.name == "f5"
