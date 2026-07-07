"""google_photos ingest 分支 + /google-photos/* 路由測試 (全 mock, 不需 OAuth)。"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("PIL", reason="需要 Pillow")
pytest.importorskip("fastapi.testclient", reason="需要 fastapi")

from fastapi.testclient import TestClient

import server.jobs as jobs_mod
from server.jobs import JobStore, get_default_store
from server.main import create_app
from server.schemas import CreateJobRequest, JobOptions, JobSource, SourceType


def _photo(path, color=(90, 140, 90)):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 900), color).save(path, format="JPEG")
    return path


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", tmp_path / "jobs")
    return JobStore(root=tmp_path / "jobs")


class TestIngestPhotos:
    def test_mock_builds_photo_deck(self, store):
        from server.runner import _run_ingest_photos
        rec = store.create(CreateJobRequest(
            source_type=SourceType.GOOGLE_PHOTOS,
            source=JobSource(session_id="s1"),
            options=JobOptions(mock=True, photo_title_hint="宜蘭之旅"),
        ))
        photos_dir = store.job_dir(rec.id) / "photos"
        for i in range(3):
            _photo(photos_dir / f"p{i}.jpg")

        deck = asyncio.run(_run_ingest_photos(store, rec, store.deck_path(rec.id), True))
        assert deck["source_type"] == "photos"
        assert deck["deck_title"] == "宜蘭之旅"
        assert len(deck["sections"][0]["slides"]) == 3
        assert store.deck_path(rec.id).exists()

    def test_no_photos_raises(self, store):
        from server.runner import _run_ingest_photos
        rec = store.create(CreateJobRequest(
            source_type=SourceType.GOOGLE_PHOTOS,
            source=JobSource(session_id="s1"), options=JobOptions(mock=True)))
        store.job_dir(rec.id).joinpath("photos").mkdir(parents=True)
        with pytest.raises(RuntimeError):
            asyncio.run(_run_ingest_photos(store, rec, store.deck_path(rec.id), True))


@pytest.fixture
def client(store):
    app = create_app()
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


class TestRoutes:
    def test_status_unauthorized(self, client, monkeypatch):
        c, _ = client
        import core.google_photos as gp
        def _raise(**k):
            raise gp.OAuthBootstrapRequired("no token")
        monkeypatch.setattr(gp, "get_photos_credentials", _raise)
        r = c.get("/google-photos/status")
        assert r.status_code == 200 and r.json()["authorized"] is False

    def test_status_authorized(self, client, monkeypatch):
        c, _ = client
        import core.google_photos as gp
        monkeypatch.setattr(gp, "get_photos_credentials", lambda **k: object())
        r = c.get("/google-photos/status")
        assert r.json()["authorized"] is True

    def test_session_412_when_unauthorized(self, client, monkeypatch):
        c, _ = client
        import core.google_photos as gp
        def _raise(**k):
            raise gp.OAuthBootstrapRequired("no token")
        monkeypatch.setattr(gp, "create_session", _raise)
        assert c.post("/google-photos/session").status_code == 412

    def test_generate_creates_job(self, client, monkeypatch):
        c, store = client
        import server.routes.google_photos as route
        monkeypatch.setattr(route, "schedule_job", lambda store, jid: None)
        r = c.post("/google-photos/generate",
                   json={"session_id": "sess-abc", "title_hint": "家庭日", "mock": True})
        assert r.status_code == 201, r.text
        job_id = r.json()["job_id"]
        rec = store.get(job_id)
        assert rec.source_type.value == "google_photos"
        assert rec.source.session_id == "sess-abc"
