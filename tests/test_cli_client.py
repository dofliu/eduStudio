"""edustudio_cli — Python client + CLI, 走 REST API (TestClient 注入, 不起 server、不碰前端)。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi")
pytest.importorskip("multipart", reason="upload 路由需要 python-multipart")

from fastapi.testclient import TestClient  # noqa: E402

import server.jobs as jobs_mod  # noqa: E402
from server.jobs import JobStore, get_default_store  # noqa: E402
from server.main import create_app  # noqa: E402
import server.routes.comics as comics_routes  # noqa: E402
import server.routes.projects as projects_routes  # noqa: E402
from core.comics import ComicStore  # noqa: E402
from core.project import ProjectStore  # noqa: E402
from edustudio_cli import EduStudioClient, EduStudioError  # noqa: E402
from edustudio_cli import cli  # noqa: E402

_needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="需要 ffmpeg")


@pytest.fixture
def env(tmp_path, monkeypatch):
    jobs_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", jobs_root)
    job_store = JobStore(root=jobs_root)
    project_store = ProjectStore(root=tmp_path / "projects")
    comic_store = ComicStore(project_root=tmp_path / "projects")
    monkeypatch.setattr(projects_routes, "_default_project_store", project_store)
    monkeypatch.setattr(comics_routes, "_default_comic_store", comic_store)
    app = create_app()
    app.dependency_overrides[get_default_store] = lambda: job_store
    app.dependency_overrides[projects_routes.get_default_project_store] = lambda: project_store
    app.dependency_overrides[comics_routes.get_default_comic_store] = lambda: comic_store
    with TestClient(app) as tc:
        client = EduStudioClient("http://testserver", token="t0k3n", session=tc)
        yield client, tc, job_store, comic_store


# ---------------- client 基本 ----------------
def test_health_and_error_mapping(env):
    client, *_ = env
    assert client.health()["status"] in ("ok", "healthy", "degraded") or client.health()
    with pytest.raises(EduStudioError) as ei:
        client.get_job("nope")
    assert ei.value.status == 404 and "nope" in ei.value.detail


def test_auth_header_and_env_defaults(monkeypatch):
    seen = {}

    class FakeSession:
        def request(self, method, url, **kw):
            seen.update(method=method, url=url, headers=kw.get("headers"))

            class R:
                status_code = 200
                content = b'{"ok": true}'

                def json(self):
                    return {"ok": True}
            return R()

    monkeypatch.setenv("EDUSTUDIO_URL", "http://box:9000/")
    monkeypatch.setenv("EDUSTUDIO_API_TOKEN", "secret")
    c = EduStudioClient(session=FakeSession())
    assert c.get("/health") == {"ok": True}
    assert seen["url"] == "http://box:9000/health" and seen["headers"]["Authorization"] == "Bearer secret"


def test_projects_roundtrip(env):
    client, *_ = env
    created = client.create_project("wind101", "離岸風電")
    assert created["project_id"] == "wind101"
    assert any(p["project_id"] == "wind101" for p in client.list_projects())


# ---------------- 影片 job: HTML 動畫 (mock, 全離線) ----------------
@_needs_ffmpeg
def test_html_video_flow_wait_and_download(env, tmp_path):
    client, *_ = env
    created = client.upload_html("https://example.com/anim", duration=1, fps=5, width=320, height=180,
                                 options={"mock": True}, title="anim")
    rec = client.wait(created["job_id"], interval=0.05, timeout=60)
    assert rec["state"] == "done", rec.get("error")
    names = {a["name"] for a in client.artifacts(created["job_id"])}
    assert "anim.mp4" in names
    paths = client.download_all(created["job_id"], tmp_path / "dl")
    assert paths and paths[0].exists() and paths[0].stat().st_size > 0
    assert client.get_log(created["job_id"], tail=5) is not None


# ---------------- review gate: 草稿 → 改 → 核准 ----------------
def test_exam_review_gate_via_client(env):
    client, tc, job_store, _ = env
    pdf = Path("sample_exam.pdf")
    if not pdf.exists():
        pytest.skip("repo 沒有 sample_exam.pdf")
    created = client.upload(pdf, "exam_pdf", options={"mock": True, "require_review": True})
    rec = client.wait(created["job_id"], interval=0.05, timeout=60)
    assert rec["state"] == "awaiting_review"
    deck = client.get_draft(created["job_id"])
    assert isinstance(deck, dict) and deck
    saved = client.put_draft(created["job_id"], deck)
    assert saved["id"] == created["job_id"]
    approved = client.approve(created["job_id"])
    assert approved["reviewed"] is True
    # 核准後 render 是背景 task; 沙箱沒 TTS 會 failed, 重點是離開 awaiting_review 進了 render 階段
    rec = client.wait(created["job_id"], until=("rendering", "done", "failed"), interval=0.05, timeout=60)
    assert rec["state"] in ("rendering", "done", "failed")


# ---------------- comics: 動態漫畫影片 (mock) ----------------
@_needs_ffmpeg
def test_comics_video_via_client(env, tmp_path):
    client, tc, job_store, comic_store = env
    client.create_project("course", "課程")
    k = client.comics("course")
    k.create_series("wind", "海風值班日誌", characters=[{"character_id": "dofu", "name": "杜夫"}])
    k.create_episode("wind", "W01", "第一話", page_count=1, learning_objectives=["x"], characters=["dofu"])
    k.update_episode("W01", {"pages": [{"page_no": 1, "image_prompt": "p", "alt_text": "a",
                                        "dialogues": [{"dialogue_id": "d1", "speaker_id": "dofu", "text": "先保留證據。"}]}],
                             "state": "STORYBOARD"})
    png = tmp_path / "s.png"
    png.write_bytes(__import__("base64").b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="))
    ep = k.upload_asset("W01", png, kind="scene", provenance="test", asset_id="scene_1")
    assert any(a["asset_id"] == "scene_1" for a in ep["assets"])
    # 連結頁面 asset (PATCH)
    k.update_episode("W01", {"pages": [{**ep["pages"][0], "image_asset_id": "scene_1"}]})
    laid = k.locate_speakers("W01", mock=True)
    assert laid["pages"][0]["speaker_positions"]
    created = k.render_video("W01", mock=True, fps=5, width=320, height=180, voices={"dofu": "default"})
    rec = client.wait(created["job_id"], until=("done", "failed"), interval=0.05, timeout=120)
    assert rec["state"] == "done", rec.get("error")
    assert any(a["name"].endswith(".mp4") for a in rec["artifacts"])


# ---------------- CLI ----------------
class _Out:
    """同 process 內 server 的第三方 lib (PyMuPDF) 會往 stdout 印 warning; 真實 CLI 是另一個 process 不會有。
    這裡只取 stdout 裡第一個 JSON 起始行之後的內容。"""

    def __init__(self, captured):
        self.err = captured.err
        lines = captured.out.splitlines()
        self.out = captured.out
        for i, line in enumerate(lines):
            if line.startswith(("{", "[")):
                candidate = "\n".join(lines[i:])
                try:
                    json.loads(candidate)
                except ValueError:
                    continue
                self.out = candidate
                break


def _run_cli(env, argv, capsys):
    client = env[0]
    code = cli.main(argv, client_factory=lambda args: client)
    return code, _Out(capsys.readouterr())


def test_cli_health_and_jobs_list(env, capsys):
    code, out = _run_cli(env, ["health"], capsys)
    assert code == 0 and json.loads(out.out)
    code, out = _run_cli(env, ["jobs", "list", "--brief"], capsys)
    assert code == 0 and json.loads(out.out) == []


def test_cli_error_codes(env, capsys):
    code, out = _run_cli(env, ["jobs", "get", "missing"], capsys)
    assert code == 1 and "404" in out.err
    code, out = _run_cli(env, ["video", "x.pdf"], capsys)          # PDF 沒給 --kind → 參數錯
    assert code == 2 and "--kind" in out.err


@_needs_ffmpeg
def test_cli_video_html_wait_download(env, capsys, tmp_path):
    code, out = _run_cli(env, ["--interval", "0.05", "video", "https://example.com/a", "--kind", "html", "--duration", "1",
                               "--mock", "--wait", "--download", str(tmp_path / "out")], capsys)
    assert code == 0, out.err
    rec = json.loads(out.out)
    assert rec["state"] == "done" and rec["downloaded"] and Path(rec["downloaded"][0]).exists()


def test_cli_draft_get_put_and_approve(env, capsys, tmp_path):
    if not Path("sample_exam.pdf").exists():
        pytest.skip("repo 沒有 sample_exam.pdf")
    code, out = _run_cli(env, ["--interval", "0.05", "video", "sample_exam.pdf", "--kind", "exam", "--mock", "--wait"], capsys)
    assert code == 0
    rec = json.loads(out.out)
    assert rec["state"] == "awaiting_review" and "awaiting_review" in out.err
    job_id = rec["id"]
    draft_file = tmp_path / "deck.json"
    code, out = _run_cli(env, ["draft", "get", job_id, "-o", str(draft_file)], capsys)
    assert code == 0 and draft_file.exists()
    code, out = _run_cli(env, ["draft", "put", job_id, str(draft_file)], capsys)
    assert code == 0
    code, out = _run_cli(env, ["jobs", "approve", job_id], capsys)
    assert code == 0 and json.loads(out.out)["reviewed"] is True
    env[0].wait(job_id, until=("rendering", "done", "failed"), interval=0.05, timeout=60)   # 讓背景 render 收尾, 不留孤兒 task


def test_cli_api_escape_hatch(env, capsys):
    code, out = _run_cli(env, ["api", "GET", "/health"], capsys)
    assert code == 0 and json.loads(out.out)
