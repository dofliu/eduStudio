"""server.routes.localization 上傳硬化測試（S-4 後續：localization 檔案端點）。

驗收（比照 test_upload.py S-4 段）：
- 5 個 multipart 端點（image/pdf/meeting/song/dub）都套**副檔名白名單**（強 gate）+
  **MIME 寬鬆白名單**（輔助）。
- 合法媒體照常通過；明顯非該類別的檔案（如 .exe / 文件塞到影音端點）被擋 400。
- MIME 寬鬆：octet-stream / 空字串放行；明顯不符的 MIME（image 配 av 端點）擋下。
- dub 走 url 來源不受上傳硬化影響（沒有檔案就不驗）。
全程 monkeypatch 媒體/翻譯模組，不打真 API、不跑 ffmpeg/whisper。
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import core.translation.service as svc
import server.routes.localization as loc
from server.main import create_app


@pytest.fixture
def client(monkeypatch):
    # 攔住所有會打真 media/Gemini 的點：合法上傳走到這些 fake 才不會踩外部依賴。
    monkeypatch.setattr(
        svc.translator, "translate_image",
        lambda path, t, s: iter(["IMG_OK"]))
    monkeypatch.setattr(
        svc.translator, "translate_pdf",
        lambda path, t, s: iter(["PDF_OK"]))
    app = create_app()
    with TestClient(app) as c:
        yield c


# ---------- 副檔名強 gate（擋非該類別檔案）----------
class TestExtensionGate:
    def test_image_rejects_non_image_ext(self, client):
        r = client.post(
            "/localization/translate/image",
            files={"file": ("evil.exe", b"MZ", "application/octet-stream")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 400
        assert "副檔名" in r.json()["detail"]

    def test_image_accepts_png(self, client):
        r = client.post(
            "/localization/translate/image",
            files={"file": ("photo.png", b"\x89PNG", "image/png")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 200 and r.json()["result"] == "IMG_OK"

    def test_pdf_rejects_non_pdf_ext(self, client):
        r = client.post(
            "/localization/translate/pdf",
            files={"file": ("notes.txt", b"hi", "text/plain")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 400 and "副檔名" in r.json()["detail"]

    def test_pdf_accepts_pdf(self, client):
        r = client.post(
            "/localization/translate/pdf",
            files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 200 and r.json()["result"] == "PDF_OK"

    def test_meeting_rejects_document(self, client):
        # 文件塞到影音端點 → 擋
        r = client.post(
            "/localization/meeting/summarize",
            files={"file": ("m.pdf", b"%PDF", "application/pdf")},
            data={"language": "zh-TW"},
        )
        assert r.status_code == 400 and "副檔名" in r.json()["detail"]

    def test_song_rejects_image(self, client):
        r = client.post(
            "/localization/song/transcribe",
            files={"file": ("cover.png", b"\x89PNG", "image/png")},
            data={"song_title": "x"},
        )
        assert r.status_code == 400 and "副檔名" in r.json()["detail"]

    def test_missing_filename_rejected(self, client):
        # 無副檔名（空 / 無 ext）一律不過強 gate
        r = client.post(
            "/localization/translate/image",
            files={"file": ("noext", b"data", "image/png")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 400 and "(無)" in r.json()["detail"]


# ---------- MIME 寬鬆輔助 ----------
class TestMimeLenient:
    def test_octet_stream_passes(self, client):
        # 副檔名合法 + MIME 為瀏覽器常見 octet-stream → 放行
        r = client.post(
            "/localization/translate/image",
            files={"file": ("photo.jpg", b"\xff\xd8", "application/octet-stream")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 200

    def test_empty_mime_passes(self, client):
        r = client.post(
            "/localization/translate/image",
            files={"file": ("photo.jpg", b"\xff\xd8", "")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 200

    def test_wrong_mime_for_ext_rejected(self, client):
        # 副檔名 .jpg 但 MIME 明說是 video → 矛盾，擋下
        r = client.post(
            "/localization/translate/image",
            files={"file": ("photo.jpg", b"\xff\xd8", "video/mp4")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 400 and "MIME" in r.json()["detail"]

    def test_av_endpoint_accepts_audio_mime(self, client, monkeypatch):
        import core.meeting.summarizer as msum
        from core.meeting.summarizer import MeetingSummaryResult

        monkeypatch.setattr(
            msum.meeting_summarizer, "process_video",
            lambda *a, **k: MeetingSummaryResult(
                transcript="t", transcript_with_time="t",
                summary={"full_summary": "s"}, duration=1.0, language="zh"))
        r = client.post(
            "/localization/meeting/summarize",
            files={"file": ("rec.mp3", b"ID3", "audio/mpeg")},
            data={"language": "zh-TW"},
        )
        assert r.status_code == 200 and r.json()["summary"] == {"full_summary": "s"}


# ---------- dub：url 來源不受上傳硬化影響 ----------
class TestDubSource:
    def test_dub_url_skips_upload_validation(self, client, monkeypatch):
        class _FakeDubber:
            def process_video(self, source, src, tgt, burn_subtitles=False):
                return {"dubbed_video": "/tmp/out.mp4"}

        monkeypatch.setattr(loc, "get_video_dubber", lambda: _FakeDubber())
        r = client.post("/localization/dub", data={
            "url": "https://youtu.be/x", "target_lang": "zh-TW",
        })
        assert r.status_code == 200
        assert r.json()["results"]["dubbed_video"] == "/tmp/out.mp4"

    def test_dub_rejects_non_av_upload(self, client):
        r = client.post(
            "/localization/dub",
            files={"file": ("x.exe", b"MZ", "application/octet-stream")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 400 and "副檔名" in r.json()["detail"]

    def test_dub_accepts_mp4_upload(self, client, monkeypatch):
        class _FakeDubber:
            def process_video(self, source, src, tgt, burn_subtitles=False):
                return {"dubbed_video": "/tmp/out.mp4"}

        monkeypatch.setattr(loc, "get_video_dubber", lambda: _FakeDubber())
        r = client.post(
            "/localization/dub",
            files={"file": ("clip.mp4", b"\x00\x00", "video/mp4")},
            data={"target_lang": "zh-TW"},
        )
        assert r.status_code == 200


# ---------- 純函式單元 ----------
class TestValidatorUnit:
    def test_rejects_bad_ext(self):
        from fastapi import HTTPException, UploadFile
        import io

        up = UploadFile(filename="x.exe", file=io.BytesIO(b""))
        with pytest.raises(HTTPException) as ei:
            loc._validate_media_upload(up, loc._AV_EXTS, "影音",
                                       mime_prefixes=("video/", "audio/"))
        assert ei.value.status_code == 400

    def test_accepts_good_ext_and_prefix(self):
        from fastapi import UploadFile
        import io

        up = UploadFile(
            filename="a.mp3", file=io.BytesIO(b""),
            headers={"content-type": "audio/mpeg"})
        # 不應拋
        loc._validate_media_upload(up, loc._AV_EXTS, "影音",
                                   mime_prefixes=("video/", "audio/"))
