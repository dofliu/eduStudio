"""POST /proposals routes 測試 (v4 階段 2 B iter 14 server route).

跟 test_upload.py 同 pattern: FastAPI TestClient + JobStore dependency override
+ PROPOSALS_PATH 指到 tmp_path. 不真打 Gemini / 不真跑 schedule_job 重型 task。
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import core.config as core_config
import server.routes.proposals as proposals_mod
from server.jobs import JobStore, get_default_store
from server.main import create_app


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def proposals_file(tmp_path, monkeypatch):
    """PROPOSALS_PATH 指到 tmp, 不污染真實 jobs/。"""
    pp = tmp_path / "proposals.json"
    monkeypatch.setattr(core_config, "PROPOSALS_PATH", pp)
    monkeypatch.setattr(proposals_mod, "PROPOSALS_PATH", pp)
    return pp


@pytest.fixture
def client(tmp_path, proposals_file, monkeypatch):
    """乾淨 TestClient + 空 JobStore."""
    # schedule_job 在 approve 流程會被 call, mock 成 noop 避免真跑 background task
    monkeypatch.setattr(
        proposals_mod, "schedule_job",
        lambda store, job_id: None,
    )

    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c


def _write_proposals(path, items):
    """Helper: 直接寫測試 proposals.json (跳過 ideate 真實流程)."""
    payload = {"generated_at": "2026-05-13T00:00:00+00:00", "proposals": items}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _sample_proposal(id_="prop_001", source_file="/tmp/a.pdf",
                      status_val="pending", job_id=None):
    return {
        "id": id_,
        "generated_at": "2026-05-13T00:00:00+00:00",
        "source_file": source_file,
        "source_type": "exam_pdf",
        "suggested_title": "材料力學 第3題",
        "suggested_chapters": [],
        "reason": "計算多步, 學生易錯",
        "estimated_duration_min": 5,
        "status": status_val,
        "job_id": job_id,
    }


# ============================================================
# Tests
# ============================================================


class TestList:
    def test_empty_when_no_file(self, client):
        # proposals_file fixture 已建路徑但沒寫檔
        resp = client.get("/proposals")
        assert resp.status_code == 200
        assert resp.json() == {"proposals": []}

    def test_lists_pending_proposals(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1"),
            _sample_proposal(id_="p2", source_file="/tmp/b.pdf"),
        ])
        resp = client.get("/proposals")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["proposals"]) == 2
        ids = [p["id"] for p in data["proposals"]]
        assert ids == ["p1", "p2"]

    def test_excludes_non_pending_by_default(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", status_val="pending"),
            _sample_proposal(id_="p2", status_val="approved"),
            _sample_proposal(id_="p3", status_val="ignored"),
            _sample_proposal(id_="p4", status_val="expired"),
        ])
        resp = client.get("/proposals")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["proposals"]]
        assert ids == ["p1"]

    def test_only_pending_false_returns_all(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", status_val="pending"),
            _sample_proposal(id_="p2", status_val="approved"),
        ])
        resp = client.get("/proposals?only_pending=false")
        assert resp.status_code == 200
        ids = sorted(p["id"] for p in resp.json()["proposals"])
        assert ids == ["p1", "p2"]


class TestApprove:
    def test_approve_creates_job_and_marks_approved(self, client, proposals_file):
        _write_proposals(proposals_file, [_sample_proposal(id_="p1")])

        resp = client.post("/proposals/p1/approve")
        assert resp.status_code == 201
        data = resp.json()
        # 回 proposal (已 approved) + job
        assert data["proposal"]["status"] == "approved"
        assert data["proposal"]["job_id"] == data["job"]["job_id"]
        assert data["job"]["state"] in ("pending", "ingesting")  # state 可能因 schedule timing 不同

        # proposals.json 已 persist
        raw = json.loads(proposals_file.read_text(encoding="utf-8"))
        assert raw["proposals"][0]["status"] == "approved"
        assert raw["proposals"][0]["job_id"] is not None

    def test_approve_missing_id_returns_404(self, client, proposals_file):
        _write_proposals(proposals_file, [])
        resp = client.post("/proposals/nope/approve")
        assert resp.status_code == 404

    def test_approve_already_approved_returns_409(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", status_val="approved", job_id="job_xxx"),
        ])
        resp = client.post("/proposals/p1/approve")
        assert resp.status_code == 409

    def test_approve_already_ignored_returns_409(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", status_val="ignored"),
        ])
        resp = client.post("/proposals/p1/approve")
        assert resp.status_code == 409

    def test_approve_bad_source_type_returns_400(self, client, proposals_file):
        bad = _sample_proposal(id_="p1")
        bad["source_type"] = "definitely_not_a_real_type"
        _write_proposals(proposals_file, [bad])
        resp = client.post("/proposals/p1/approve")
        assert resp.status_code == 400

    def test_approve_with_theme_body_sets_job_options(
        self, client, proposals_file, monkeypatch,
    ):
        """iter 40: 核准時帶 theme → 寫進 JobOptions.theme.

        document source_type 才適用主題, 用它測.
        """
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", source_file="/tmp/a.pdf"),
        ])
        # 把第一張 proposal 的 source_type 改成 document (適用 theme)
        raw = json.loads(proposals_file.read_text(encoding="utf-8"))
        raw["proposals"][0]["source_type"] = "document"
        proposals_file.write_text(json.dumps(raw), encoding="utf-8")

        # 攔 store.create 看實際送進去的 options
        captured: dict = {}
        from server.routes import proposals as proposals_mod
        real_create = proposals_mod.get_default_store().__class__.create

        def spy_create(self, req):
            captured["theme"] = req.options.theme
            captured["hardsub"] = req.options.hardsub
            return real_create(self, req)

        monkeypatch.setattr(
            proposals_mod.JobStore, "create", spy_create,
        )

        resp = client.post(
            "/proposals/p1/approve",
            json={"theme": "frieren", "hardsub": True},
        )
        assert resp.status_code == 201, resp.text
        assert captured["theme"] == "frieren"
        assert captured["hardsub"] is True

    def test_approve_without_body_uses_defaults(self, client, proposals_file):
        """沒帶 body 仍走預設 (forest / hardsub=False), 保 backwards compat."""
        _write_proposals(proposals_file, [_sample_proposal(id_="p1")])
        resp = client.post("/proposals/p1/approve")
        assert resp.status_code == 201

    def test_approve_with_invalid_theme_returns_422(self, client, proposals_file):
        """theme 不在白名單應 422 (pydantic Literal validation)."""
        _write_proposals(proposals_file, [_sample_proposal(id_="p1")])
        resp = client.post(
            "/proposals/p1/approve",
            json={"theme": "nope_not_a_theme"},
        )
        assert resp.status_code == 422


class TestIgnore:
    def test_ignore_marks_status(self, client, proposals_file):
        _write_proposals(proposals_file, [_sample_proposal(id_="p1")])

        resp = client.patch("/proposals/p1/ignore")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

        raw = json.loads(proposals_file.read_text(encoding="utf-8"))
        assert raw["proposals"][0]["status"] == "ignored"

    def test_ignore_missing_id_returns_404(self, client, proposals_file):
        _write_proposals(proposals_file, [])
        resp = client.patch("/proposals/nope/ignore")
        assert resp.status_code == 404

    def test_ignore_already_decided_returns_409(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", status_val="approved", job_id="x"),
        ])
        resp = client.patch("/proposals/p1/ignore")
        assert resp.status_code == 409


class TestScanFolder:
    """POST /proposals/scan-folder — ad-hoc 掃單一資料夾 (iter 27)."""

    def test_missing_folder_returns_ok_false(self, client):
        resp = client.post(
            "/proposals/scan-folder",
            json={"folder": "/this/does/not/exist", "source_type": "auto"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "不存在" in (data["error"] or "")

    def test_folder_is_file_returns_ok_false(self, client, tmp_path):
        f = tmp_path / "x.pdf"
        f.write_bytes(b"%PDF")
        resp = client.post(
            "/proposals/scan-folder",
            json={"folder": str(f), "source_type": "auto"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "不是資料夾" in (data["error"] or "")

    def test_invalid_source_type_returns_422(self, client, tmp_path):
        resp = client.post(
            "/proposals/scan-folder",
            json={"folder": str(tmp_path), "source_type": "nope"},
        )
        assert resp.status_code == 422

    def test_window_days_validation(self, client, tmp_path):
        # scan_window_days=0 違反 ge=1
        resp = client.post(
            "/proposals/scan-folder",
            json={"folder": str(tmp_path), "scan_window_days": 0},
        )
        assert resp.status_code == 422

    def test_happy_path_dispatches_to_run_ideate_async(self, client, tmp_path, monkeypatch):
        """正常路徑: 接 body → 組 config → run_ideate_async → 回 ScanResponse."""
        from server.routes import proposals as proposals_mod

        async def fake_run_async(config, store=None, out_path=None):
            # 確認 config 是依 request body 組好的
            assert config["watched_folders"][0]["scan_window_days"] == 7
            assert config["watched_folders"][0]["source_type"] == "exam_pdf"
            assert config["max_proposals_per_file"] == 5
            return {"ok": True, "scanned": 3, "proposed": 6, "new": 4, "error": None}

        monkeypatch.setattr(proposals_mod, "run_ideate_async", fake_run_async)

        resp = client.post(
            "/proposals/scan-folder",
            json={
                "folder": str(tmp_path),
                "source_type": "exam_pdf",
                "scan_window_days": 7,
                "max_proposals_per_file": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["scanned"] == 3
        assert data["new"] == 4


class TestScanFolderAsync:
    """POST /proposals/scan-folder/async — fire-and-forget (iter 33)."""

    def test_missing_folder_returns_400(self, client):
        resp = client.post(
            "/proposals/scan-folder/async",
            json={"folder": "/does/not/exist"},
        )
        assert resp.status_code == 400

    def test_folder_is_file_returns_400(self, client, tmp_path):
        f = tmp_path / "x.pdf"
        f.write_bytes(b"%PDF")
        resp = client.post(
            "/proposals/scan-folder/async",
            json={"folder": str(f)},
        )
        assert resp.status_code == 400

    def test_happy_path_returns_scan_id(self, client, tmp_path, monkeypatch):
        from server.routes import proposals as proposals_mod

        def fake_start(config, store=None, out_path=None):
            return "fakehex123456"
        monkeypatch.setattr(proposals_mod, "start_async_scan", fake_start)

        resp = client.post(
            "/proposals/scan-folder/async",
            json={"folder": str(tmp_path), "source_type": "auto"},
        )
        assert resp.status_code == 202
        assert resp.json() == {"scan_id": "fakehex123456"}


class TestScanStatus:
    """GET /proposals/scan-status/{scan_id} (iter 33)."""

    def test_unknown_scan_id_returns_404(self, client):
        resp = client.get("/proposals/scan-status/nope_unknown")
        assert resp.status_code == 404

    def test_running_state(self, client, monkeypatch):
        from server.routes import proposals as proposals_mod

        def fake_get(scan_id):
            return {
                "state": "running",
                "scanned": 2,
                "proposed": 0,
                "new": 0,
                "error": None,
                "message": "running gemini",
                "started_at": "2026-05-14T01:00:00+00:00",
                "ended_at": None,
            }
        monkeypatch.setattr(proposals_mod, "get_scan_state", fake_get)

        resp = client.get("/proposals/scan-status/abc")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "running"
        assert data["scanned"] == 2
        assert data["message"] == "running gemini"

    def test_done_state(self, client, monkeypatch):
        from server.routes import proposals as proposals_mod

        def fake_get(scan_id):
            return {
                "state": "done",
                "scanned": 5, "proposed": 8, "new": 3,
                "error": None, "message": "",
                "started_at": "2026-05-14T01:00:00+00:00",
                "ended_at": "2026-05-14T01:05:00+00:00",
            }
        monkeypatch.setattr(proposals_mod, "get_scan_state", fake_get)

        resp = client.get("/proposals/scan-status/abc")
        assert resp.status_code == 200
        assert resp.json()["state"] == "done"

    def test_failed_state_with_error(self, client, monkeypatch):
        from server.routes import proposals as proposals_mod

        def fake_get(scan_id):
            return {
                "state": "failed",
                "scanned": 1, "proposed": 0, "new": 0,
                "error": "Gemini quota", "message": "",
                "started_at": "2026-05-14T01:00:00+00:00",
                "ended_at": "2026-05-14T01:00:30+00:00",
            }
        monkeypatch.setattr(proposals_mod, "get_scan_state", fake_get)

        resp = client.get("/proposals/scan-status/abc")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "failed"
        assert data["error"] == "Gemini quota"
