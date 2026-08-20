"""server.routes.localization HTTP route 測試（eduStudio 合併 Phase B-2）。

驗收：
- 語言碼邊界轉換：對外傳 canonical 'zh-TW'，服務內部收到底線式 'zh_TW'（唯一邊界）。
- text 翻譯 + 學習端點走 Gemini 服務（monkeypatch _gemini_complete 不打真 API）。
- GET /localization/languages 回 canonical 連字號碼。
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import core.translation.service as svc
from server.main import create_app


@pytest.fixture
def client(monkeypatch):
    # 所有 LLM 呼叫攔在 _gemini_complete，回可辨識字串，不打真 Gemini。
    monkeypatch.setattr(svc, "_gemini_complete", lambda prompt: f"[GEMINI]{prompt[:0]}OK")
    app = create_app()
    with TestClient(app) as c:
        yield c


class TestLanguages:
    def test_list_languages_canonical_hyphen(self, client):
        r = client.get("/localization/languages")
        assert r.status_code == 200
        codes = [x["code"] for x in r.json()["languages"]]
        assert "zh-TW" in codes
        # 核心 canonical 不得有底線式
        assert all("_" not in c for c in codes)


class TestTranslate:
    def test_translate_boundary_converts_to_underscore(self, client, monkeypatch):
        """對外 zh-TW，服務 translate() 實際收到底線式 zh_TW（唯一邊界轉換）。"""
        seen = {}

        def fake_translate(text, source_code, target_code, glossary="", style=""):
            seen["source"] = source_code
            seen["target"] = target_code
            return "譯文"

        monkeypatch.setattr(svc.translator, "translate", fake_translate)
        r = client.post("/localization/translate", json={
            "text": "hello", "target_lang": "zh-TW", "source_lang": "en-US",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["translated_text"] == "譯文"
        assert body["target_lang"] == "zh-TW"      # 對外仍連字號
        assert seen["target"] == "zh_TW"           # 服務內部收到底線式
        assert seen["source"] == "en_US"

    def test_translate_auto_source_passthrough(self, client, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            svc.translator, "translate",
            lambda text, source_code, target_code, glossary="", style="":
                seen.update(source=source_code) or "x",
        )
        client.post("/localization/translate", json={
            "text": "hi", "target_lang": "ja-JP",
        })
        assert seen["source"] == "auto"  # auto 無分隔符，原樣


class TestLearningEndpoints:
    def test_flashcards(self, client, monkeypatch):
        monkeypatch.setattr(svc, "_gemini_complete", lambda p: "CARDS")
        r = client.post("/localization/learning/flashcards", json={
            "text": "vocab", "target_lang": "zh-TW", "count": 3,
        })
        assert r.status_code == 200 and r.json()["result"] == "CARDS"

    def test_writing_correction(self, client, monkeypatch):
        monkeypatch.setattr(svc, "_gemini_complete", lambda p: "FIXED")
        r = client.post("/localization/learning/writing-correction", json={
            "text": "I has apple", "lang": "en-US", "native_lang": "zh-TW",
        })
        assert r.status_code == 200 and r.json()["result"] == "FIXED"

    def test_dictation_check_empty_inputs(self, client):
        r = client.post("/localization/learning/dictation-check", json={
            "original": "", "user_input": "", "target_lang": "zh-TW",
        })
        assert r.status_code == 200 and "請提供" in r.json()["result"]


# ---------- 檔案端點（mock 模組，不打真 media/Gemini）----------
class TestFileEndpoints:
    def test_translate_image_boundary_and_result(self, client, monkeypatch):
        seen = {}

        def fake_image(path, target_code, source_code):
            seen["target"] = target_code
            seen["source"] = source_code
            yield "OCR+翻譯結果"

        monkeypatch.setattr(svc.translator, "translate_image", fake_image)
        r = client.post(
            "/localization/translate/image",
            files={"file": ("x.png", b"fakepng", "image/png")},
            data={"target_lang": "zh-TW", "source_lang": "en-US"},
        )
        assert r.status_code == 200
        assert r.json()["result"] == "OCR+翻譯結果"
        assert seen["target"] == "zh_TW"  # 邊界轉底線
        assert seen["source"] == "en_US"

    def test_translate_pdf(self, client, monkeypatch):
        monkeypatch.setattr(
            svc.translator, "translate_pdf",
            lambda path, t, s: iter(["PDF 翻譯完成"]),
        )
        r = client.post(
            "/localization/translate/pdf",
            files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 200 and r.json()["result"] == "PDF 翻譯完成"

    def test_meeting_summarize(self, client, monkeypatch):
        import core.meeting.summarizer as msum
        from core.meeting.summarizer import MeetingSummaryResult

        def fake_process(video_path, language, summary_types):
            return MeetingSummaryResult(
                transcript="逐字稿", transcript_with_time="[00:00] 逐字稿",
                summary={"full_summary": "摘要"}, duration=12.5, language="zh",
            )

        monkeypatch.setattr(msum.meeting_summarizer, "process_video", fake_process)
        r = client.post(
            "/localization/meeting/summarize",
            files={"file": ("m.mp4", b"fake", "video/mp4")},
            data={"language": "zh-TW", "summary_types": "full_summary"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["summary"] == {"full_summary": "摘要"}
        assert body["duration"] == 12.5

    def test_dub_requires_source(self, client):
        # 不給 url 也不給 file → error
        r = client.post("/localization/dub", data={"target_lang": "zh-TW"})
        assert r.status_code == 200 and "error" in r.json()

    def test_dub_with_url_mocked(self, client, monkeypatch):
        import server.routes.localization as loc

        class _FakeDubber:
            def process_video(self, source, src, tgt, burn_subtitles=False):
                return {"dubbed_video": "/tmp/out.mp4", "_args": [source, src, tgt]}

        monkeypatch.setattr(loc, "get_video_dubber", lambda: _FakeDubber())
        r = client.post("/localization/dub", data={
            "url": "https://youtu.be/x", "target_lang": "zh-TW", "source_lang": "auto",
        })
        assert r.status_code == 200
        results = r.json()["results"]
        assert results["dubbed_video"] == "/tmp/out.mp4"
        assert results["_args"] == ["https://youtu.be/x", "auto", "zh_TW"]  # 邊界轉換

    def test_song_runtime_error_is_json_503(self, client, monkeypatch):
        """第三方 STT/model 失敗不能退成 Starlette 純文字 Internal Server Error。"""
        import core.song_build as song_build

        def fail_transcribe(*args, **kwargs):
            raise RuntimeError("Whisper model cache missing")

        monkeypatch.setattr(song_build, "build_song_json_from_media", fail_transcribe)
        r = client.post(
            "/localization/song/transcribe",
            files={"file": ("song.mp3", b"ID3", "audio/mpeg")},
        )
        assert r.status_code == 503
        assert "Whisper model cache missing" in r.json()["detail"]
