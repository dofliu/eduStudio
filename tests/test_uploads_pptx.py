"""POST /upload/pptx — PPTX 原檔就地補圖路由測試。

驗證: 非 .pptx → 400; 空檔 → 400; happy path (建 job + 背景補圖, mock) — happy
path 需 LibreOffice (pptx→pdf), 無 soffice 則 skip。
"""
from __future__ import annotations

import io
import shutil

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi")
pytest.importorskip("multipart", reason="需要 python-multipart")
pytest.importorskip("pptx", reason="需要 python-pptx")

from fastapi.testclient import TestClient

import server.jobs as jobs_mod
from server.jobs import JobStore, get_default_store
from server.main import create_app

_HAS_SOFFICE = bool(shutil.which("soffice") or shutil.which("libreoffice"))


def _pptx_bytes(n=2):
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    for i in range(n):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(5), Inches(1)).text_frame.text = f"頁 {i+1}"
    buf = io.BytesIO(); prs.save(buf); return buf.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    jobs_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", jobs_root)
    app = create_app()
    store = JobStore(root=jobs_root)
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


class TestValidation:
    def test_non_pptx_rejected(self, client):
        c, _ = client
        r = c.post("/upload/pptx", files={"file": ("x.pdf", b"%PDF", "application/pdf")})
        assert r.status_code == 400

    def test_empty_rejected(self, client):
        c, _ = client
        r = c.post("/upload/pptx", files={"file": ("x.pptx", b"", "application/vnd.openxmlformats-officedocument.presentationml.presentation")})
        assert r.status_code == 400


@pytest.mark.skipif(not _HAS_SOFFICE, reason="需要 LibreOffice 做 pptx→pdf")
class TestHappyPath:
    def test_creates_job_and_augments(self, client):
        c, store = client
        r = c.post(
            "/upload/pptx",
            files={"file": ("deck.pptx", _pptx_bytes(2), "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
            data={"only_missing": "true", "options_json": '{"mock": true}'},
        )
        assert r.status_code == 201, r.text
        job_id = r.json()["job_id"]
        assert store.get(job_id).source_type.value == "pptx"
        # 背景 task 在 TestClient 結束時應已跑完 (mock 很快); 輪詢 deck 不適用, 檢查 state
        import time
        for _ in range(50):
            rec = store.get(job_id)
            if rec.state.value in ("done", "failed"):
                break
            time.sleep(0.1)
        rec = store.get(job_id)
        assert rec.state.value == "done", rec.error
        names = [a.name for a in rec.artifacts]
        assert any(n.endswith("_augmented.pptx") for n in names), names
