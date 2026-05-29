"""server.routes.voices HTTP route 測試 (iter 114).

test_voices.py 已覆蓋 _read_current_voice / _write_current_voice helper 純函式,
但 GET /voices / POST /voices / GET /voices/{id}/sample 三個 HTTP route 從 PR-3l
上線後沒對應測試 — 任何 refactor 不小心動 route 介面 (response shape /
status code / 路徑解析) 就直接上線. 補測 = 安全鎖, 跟 iter 111
slide_images_route / iter 112 upload helper / iter 113 editor route 思路一致.

monkeypatch TTS_CONFIG_PATH + VOICE_SAMPLE_DIR 到 tmp_path, 不污染 user 設定
也不依賴真 voices/samples/*.mp3 存在.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import server.routes.voices as voices_mod
from server.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """乾淨 TestClient + 隔離 tts_config.json + 隔離 sample dir.

    為什麼 patch attribute 不是 module: route module 內
    `from core.config import TTS_CONFIG_PATH` / `from core.config import PROJECT_ROOT`
    把 reference 捕到 server.routes.voices.{TTS_CONFIG_PATH, VOICE_SAMPLE_DIR},
    patch core.config.* 不會反映到 route module.
    """
    cfg_path = tmp_path / "tts_config.json"
    cfg_path.write_text(json.dumps({
        "backend": "edge",
        "edge": {"voice": "zh-TW-HsiaoChenNeural", "rate": "-5%"},
        "f5": {"ref_audio": "voices/teacher_ref.wav"},
    }, ensure_ascii=False), encoding="utf-8")
    sample_dir = tmp_path / "samples"
    sample_dir.mkdir()
    monkeypatch.setattr(voices_mod, "TTS_CONFIG_PATH", cfg_path)
    monkeypatch.setattr(voices_mod, "VOICE_SAMPLE_DIR", sample_dir)
    app = create_app()
    with TestClient(app) as c:
        yield c, cfg_path, sample_dir


# ---------- GET /voices ----------

class TestListVoices:
    def test_returns_nine_voices(self, client):
        # 5 edge + 1 F5 + 3 google (S 軸 S2)
        c, _, _ = client
        resp = c.get("/voices")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["voices"]) == 9

    def test_current_reflects_config(self, client):
        c, _, _ = client
        resp = c.get("/voices")
        body = resp.json()
        assert body["current"] == "zh-TW-HsiaoChenNeural"

    def test_voice_info_shape(self, client):
        """每個 voice 該帶 id / label / sample_url, sample_url 該指向 /voices/{id}/sample."""
        c, _, _ = client
        body = c.get("/voices").json()
        for v in body["voices"]:
            assert set(v.keys()) == {"id", "label", "sample_url"}
            assert v["sample_url"] == f"/voices/{v['id']}/sample"

    def test_current_falls_back_when_config_missing(self, client, tmp_path, monkeypatch):
        """沒 tts_config.json 不該爆 500, 該回第一個 voice (跟 _read_current_voice 對齊)."""
        c, _, _ = client
        # 重 patch 到一個不存在的路徑
        monkeypatch.setattr(voices_mod, "TTS_CONFIG_PATH", tmp_path / "nope.json")
        body = c.get("/voices").json()
        assert body["current"] == voices_mod.VOICES[0]["id"]

    def test_current_f5_when_backend_f5(self, client):
        """backend=f5 時 current 該回 'f5:teacher' (跟 _read_current_voice 對齊)."""
        c, cfg_path, _ = client
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["backend"] = "f5"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
        body = c.get("/voices").json()
        assert body["current"] == "f5:teacher"


# ---------- POST /voices ----------

class TestSetVoice:
    def test_switches_to_edge_voice(self, client):
        c, cfg_path, _ = client
        resp = c.post("/voices", json={"voice_id": "zh-CN-YunyangNeural"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["current"] == "zh-CN-YunyangNeural"
        # 落盤驗
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert cfg["backend"] == "edge"
        assert cfg["edge"]["voice"] == "zh-CN-YunyangNeural"

    def test_switches_to_f5_voice(self, client):
        c, cfg_path, _ = client
        resp = c.post("/voices", json={"voice_id": "f5:teacher"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["current"] == "f5:teacher"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert cfg["backend"] == "f5"

    def test_f5_switch_preserves_f5_subblock(self, client):
        """切到 f5 不該動 f5.ref_audio 等 user 設定 (跟 helper 邏輯一致)."""
        c, cfg_path, _ = client
        before = json.loads(cfg_path.read_text(encoding="utf-8"))["f5"]
        c.post("/voices", json={"voice_id": "f5:teacher"})
        after = json.loads(cfg_path.read_text(encoding="utf-8"))["f5"]
        assert after == before

    def test_unknown_voice_returns_400(self, client):
        c, _, _ = client
        resp = c.post("/voices", json={"voice_id": "fake-voice-id"})
        assert resp.status_code == 400
        assert "fake-voice-id" in resp.json()["detail"]

    def test_unknown_voice_does_not_modify_config(self, client):
        c, cfg_path, _ = client
        before = cfg_path.read_text(encoding="utf-8")
        c.post("/voices", json={"voice_id": "fake-voice-id"})
        after = cfg_path.read_text(encoding="utf-8")
        assert before == after

    def test_missing_voice_id_field_returns_422(self, client):
        """pydantic v2 缺必填欄位該 422 (FastAPI 預設驗證錯誤)."""
        c, _, _ = client
        resp = c.post("/voices", json={})
        assert resp.status_code == 422

    def test_extra_fields_accepted(self, client):
        """SetVoiceRequest model_config 設 extra='allow', 帶額外欄位不該 422."""
        c, _, _ = client
        resp = c.post("/voices", json={
            "voice_id": "zh-CN-XiaoxiaoNeural",
            "future_field": "ignored",
        })
        assert resp.status_code == 200

    def test_round_trip_via_http(self, client):
        """POST → GET 該回到剛切的 voice."""
        c, _, _ = client
        c.post("/voices", json={"voice_id": "zh-CN-XiaoxiaoNeural"})
        body = c.get("/voices").json()
        assert body["current"] == "zh-CN-XiaoxiaoNeural"


# ---------- GET /voices/{id}/sample ----------

class TestVoiceSample:
    def test_serves_mp3(self, client):
        """sample 檔存在該回 200 + audio/mpeg + 原始 bytes."""
        c, _, sample_dir = client
        content = b"\xff\xfb\x90\x00fake-mp3-bytes"
        (sample_dir / "voice_tw_hsiaochen_F.mp3").write_bytes(content)
        resp = c.get("/voices/zh-TW-HsiaoChenNeural/sample")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"
        assert resp.content == content

    def test_serves_f5_voice_with_colon(self, client):
        """:path converter 該讓 voice id 含冒號 (f5:teacher) 也能解析,
        不該被普通 str converter 視為違法."""
        c, _, sample_dir = client
        content = b"\xff\xfb\x90\x00f5-sample"
        (sample_dir / "voice_f5_teacher_M.mp3").write_bytes(content)
        resp = c.get("/voices/f5:teacher/sample")
        assert resp.status_code == 200
        assert resp.content == content

    def test_unknown_voice_returns_404(self, client):
        c, _, _ = client
        resp = c.get("/voices/totally-fake/sample")
        assert resp.status_code == 404
        assert "totally-fake" in resp.json()["detail"]

    def test_known_voice_missing_sample_file_returns_404(self, client):
        """voice id 在 VOICES 但 sample 檔沒放在 voices/samples/ — 404 不是 500."""
        c, _, sample_dir = client
        # sample_dir 完全空 — 該回有提示的 404
        resp = c.get("/voices/zh-TW-HsiaoYuNeural/sample")
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert "voice_tw_hsiaoyu_F.mp3" in detail
        assert "voices/samples" in detail
