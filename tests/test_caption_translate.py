"""core/caption_translate + POST /jobs/{id}/artifacts/{name}/captions 測試（多語字幕軌）。

純 SRT 解析/翻譯零 API;路由測試 mock 翻譯 + upload_captions(避開 OAuth)。
"""
from __future__ import annotations

import pytest

import core.caption_translate as ct

_SRT = """1
00:00:00,000 --> 00:00:02,000
你好世界

2
00:00:02,000 --> 00:00:04,500
這是第二句
"""


class TestParseBuild:
    def test_parse(self):
        cues = ct.parse_srt(_SRT)
        assert len(cues) == 2
        assert cues[0]["time"] == "00:00:00,000 --> 00:00:02,000"
        assert cues[0]["lines"] == ["你好世界"]

    def test_parse_tolerates_missing_index(self):
        cues = ct.parse_srt("00:00:00,000 --> 00:00:01,000\nhi")
        assert len(cues) == 1 and cues[0]["lines"] == ["hi"]

    def test_build_roundtrip_renumbers(self):
        cues = ct.parse_srt(_SRT)
        out = ct.build_srt(cues)
        assert "00:00:00,000 --> 00:00:02,000" in out
        assert out.strip().startswith("1")


class TestTranslateSrt:
    def test_translates_each_cue_keeps_time(self):
        fn = lambda text, s, t: f"[{t}]{text}"
        out = ct.translate_srt(_SRT, "zh-TW", "en-US", fn)
        cues = ct.parse_srt(out)
        assert cues[0]["lines"] == ["[en-US]你好世界"]
        assert cues[1]["time"] == "00:00:02,000 --> 00:00:04,500"  # 時間碼不變

    def test_failed_cue_keeps_original(self):
        def fn(text, s, t):
            raise RuntimeError("translate boom")
        out = ct.translate_srt(_SRT, "zh-TW", "ja-JP", fn)
        assert "你好世界" in out  # 失敗保留原文


class TestCaptionsRoute:
    @pytest.fixture
    def client(self, tmp_path):
        pytest.importorskip("fastapi.testclient")
        pytest.importorskip("multipart")
        from fastapi.testclient import TestClient

        from server.jobs import JobStore, get_default_store
        from server.main import create_app
        from server.schemas import (
            Artifact, CreateJobRequest, JobOptions, JobSource, JobState,
            SourceType, YoutubeUpload, YoutubeUploadState,
        )

        app = create_app()
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.EXAM_PDF, source=JobSource(path="/tmp/fake.pdf"),
            options=JobOptions(require_review=False)))
        adir = store.artifacts_dir(rec.id)
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "q1.mp4").write_bytes(b"fake mp4")
        (adir / "q1.srt").write_text(_SRT, encoding="utf-8")
        (adir / "q2.mp4").write_bytes(b"fake mp4")  # 沒上傳過的 artifact（測 409）
        (adir / "q2.srt").write_text(_SRT, encoding="utf-8")
        store.update(rec.id, state=JobState.DONE, artifacts=[
            Artifact(name="q1.mp4", path=str(adir / "q1.mp4"), size_bytes=8, kind="mp4"),
            Artifact(name="q2.mp4", path=str(adir / "q2.mp4"), size_bytes=8, kind="mp4"),
        ])
        store.set_youtube_upload(rec.id, "q1.mp4",
                                 YoutubeUpload(state=YoutubeUploadState.DONE, video_id="vid123"))
        app.dependency_overrides[get_default_store] = lambda: store
        with TestClient(app) as c:
            yield c, rec.id

    def test_add_captions_ok(self, client, monkeypatch):
        c, job_id = client
        import core.youtube as yt
        import core.translation.service as svc
        monkeypatch.setattr(yt, "upload_captions",
                            lambda video_id, caps: [{"language": cp["language"], "caption_id": "cap_" + cp["language"]} for cp in caps])
        monkeypatch.setattr(svc.translator, "translate", lambda text, s, t: "TR:" + text)
        r = c.post(f"/jobs/{job_id}/artifacts/q1.mp4/captions",
                   json={"languages": ["en-US", "ja-JP"], "source_lang": "zh-TW"})
        assert r.status_code == 202
        body = r.json()
        assert body["video_id"] == "vid123"
        assert {x["language"] for x in body["captions"]} == {"en-US", "ja-JP"}

    def test_requires_published_video_409(self, client):
        """q2.mp4 沒上傳過 YouTube → 409（要先傳影片才能加字幕軌）。"""
        c, job_id = client
        r = c.post(f"/jobs/{job_id}/artifacts/q2.mp4/captions", json={"languages": ["en-US"]})
        assert r.status_code == 409

    def test_missing_languages_400(self, client, monkeypatch):
        c, job_id = client
        r = c.post(f"/jobs/{job_id}/artifacts/q1.mp4/captions", json={"languages": []})
        assert r.status_code == 400
