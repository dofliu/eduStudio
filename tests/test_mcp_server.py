"""edustudio_cli.mcp_server — MCP tools 包 EduStudioClient (in-memory MCP client ↔ TestClient-backed 後端, 不起 server、不碰前端)。
mcp 1.x (FastMCP, CallToolResult.isError) 與 2.x (MCPServer, is_error) 都要能跑。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi")
pytest.importorskip("multipart", reason="upload 路由需要 python-multipart")
pytest.importorskip("mcp", reason="需要 MCP Python SDK (pip install mcp)")
try:
    from mcp.client import Client as _Client  # mcp >= 2: in-process client

    def MCPClient(server):
        return _Client(server)
except ImportError:  # mcp 1.x: FastMCP 直接接 in-memory session
    from mcp.shared.memory import create_connected_server_and_client_session

    def MCPClient(server):
        return create_connected_server_and_client_session(server)

from fastapi.testclient import TestClient  # noqa: E402

import server.jobs as jobs_mod  # noqa: E402
from server.jobs import JobStore, get_default_store  # noqa: E402
from server.main import create_app  # noqa: E402
import server.routes.comics as comics_routes  # noqa: E402
import server.routes.projects as projects_routes  # noqa: E402
from core.comics import ComicStore  # noqa: E402
from core.project import ProjectStore  # noqa: E402
from edustudio_cli import EduStudioClient  # noqa: E402
from edustudio_cli import mcp_server  # noqa: E402

_needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="需要 ffmpeg")
pytestmark = pytest.mark.asyncio


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
        yield client, mcp_server.build_server(client)


def _field(obj, snake, camel):
    """mcp 2.x 用 snake_case 屬性, 1.x 用 camelCase。"""
    return getattr(obj, snake, None) if hasattr(obj, snake) else getattr(obj, camel, None)


async def _call(mc, name, **args):
    """呼叫 tool, 回 (is_error, 解析後的 JSON 或原文)。每個 tool 都回單一 dict (清單類 → {"count","items"})。"""
    r = await mc.call_tool(name, args)
    text = "".join(getattr(c, "text", "") for c in r.content)
    if _field(r, "is_error", "isError"):
        return True, text
    structured = _field(r, "structured_content", "structuredContent")
    if structured is not None:
        return False, structured
    try:
        return False, json.loads(text)
    except ValueError:
        return False, text


# ---------------- 註冊 / 描述 ----------------
async def test_tools_registered_with_descriptions(env):
    _, server = env
    async with MCPClient(server) as mc:
        tools = {t.name: t for t in (await mc.list_tools()).tools}
    for name in ("edustudio_health", "list_jobs", "wait_job", "upload_pptx", "pptx_to_video", "upload_video_source",
                 "get_draft", "put_draft", "approve_job", "download_artifacts", "publish_youtube",
                 "comics_render_video", "comics_locate_speakers", "api_request"):
        assert name in tools, name
        assert tools[name].description and len(tools[name].description) > 10
    assert "核准" in tools["approve_job"].description          # review gate 說明要在 tool 描述裡
    assert "job_id" in _field(tools["get_job"], "input_schema", "inputSchema")["required"]
    ro = tools["get_job"].annotations
    assert ro is not None and (getattr(ro, "read_only_hint", None) or getattr(ro, "readOnlyHint", None))
    assert "awaiting_review" in mcp_server.INSTRUCTIONS


async def test_server_builds_without_backend(monkeypatch):
    """server 沒起來也能建 MCP、列 tool (client 是 lazy 的)。"""
    monkeypatch.setenv("EDUSTUDIO_URL", "http://127.0.0.1:1")
    server = mcp_server.build_server()
    assert server is not None
    args = mcp_server.make_parser().parse_args(["--server", "http://x:1", "--transport", "stdio"])
    assert args.server == "http://x:1" and args.transport == "stdio"


# ---------------- 基本 / 錯誤傳遞 ----------------
async def test_health_projects_and_error_text(env):
    _, server = env
    async with MCPClient(server) as mc:
        err, health = await _call(mc, "edustudio_health")
        assert not err and health
        err, created = await _call(mc, "create_project", project_id="wind101", title="離岸風電")
        assert not err and created["project_id"] == "wind101"
        err, projects = await _call(mc, "list_projects")
        assert not err and any(p["project_id"] == "wind101" for p in projects["items"])
        err, jobs = await _call(mc, "list_jobs")
        assert not err and jobs == {"count": 0, "items": []}
        # 404 → is_error, 且狀態碼 + detail 原樣給模型
        err, text = await _call(mc, "get_job", job_id="nope")
        assert err and "404" in text and "nope" in text
        # 參數錯 (kind) 也要是可讀的 tool error, 不是 crash
        err, text = await _call(mc, "upload_video_source", file_path="x.pdf", kind="banana")
        assert err and "kind" in text
        # escape hatch
        err, h = await _call(mc, "api_request", method="get", path="/health")
        assert not err and h


# ---------------- HTML 動畫 job (mock) → wait → download ----------------
@_needs_ffmpeg
async def test_html_job_wait_and_download(env, tmp_path):
    _, server = env
    async with MCPClient(server) as mc:
        err, created = await _call(mc, "upload_html_animation", source="https://example.com/anim", duration=1,
                                   fps=5, width=320, height=180, mock=True, title="anim")
        assert not err, created
        err, rec = await _call(mc, "wait_job", job_id=created["job_id"], interval=0.05, timeout=60)
        assert not err and rec["state"] == "done", rec
        err, arts = await _call(mc, "list_artifacts", job_id=created["job_id"])
        assert not err and any(a["name"] == "anim.mp4" for a in arts["items"])
        err, dl = await _call(mc, "download_artifacts", job_id=created["job_id"], dest_dir=str(tmp_path / "dl"))
        assert not err and dl["files"] and Path(dl["files"][0]).exists()
        err, log = await _call(mc, "get_job_log", job_id=created["job_id"], tail=5)
        assert not err
        err, gone = await _call(mc, "delete_job", job_id=created["job_id"])
        assert not err and gone["deleted"] == created["job_id"]
        err, _ = await _call(mc, "get_job", job_id=created["job_id"])
        assert err


# ---------------- review gate: 停在 awaiting_review, approve 才走 ----------------
async def test_exam_review_gate(env):
    client, server = env
    if not Path("sample_exam.pdf").exists():
        pytest.skip("repo 沒有 sample_exam.pdf")
    async with MCPClient(server) as mc:
        err, created = await _call(mc, "upload_video_source", file_path="sample_exam.pdf", kind="exam", mock=True)
        assert not err, created
        job_id = created["job_id"]
        err, rec = await _call(mc, "wait_job", job_id=job_id, interval=0.05, timeout=60)
        assert not err and rec["state"] == "awaiting_review"
        err, deck = await _call(mc, "get_draft", job_id=job_id)
        assert not err and isinstance(deck, dict) and deck
        err, saved = await _call(mc, "put_draft", job_id=job_id, deck=deck)
        assert not err and saved["id"] == job_id
        # 沒 approve 就還是 awaiting_review
        err, rec = await _call(mc, "get_job", job_id=job_id)
        assert rec["state"] == "awaiting_review"
        err, approved = await _call(mc, "approve_job", job_id=job_id)
        assert not err and approved["reviewed"] is True
        err, rec = await _call(mc, "wait_job", job_id=job_id, until=["rendering", "done", "failed"], interval=0.05, timeout=60)
        assert not err and rec["state"] in ("rendering", "done", "failed")
    client.wait(job_id, until=("rendering", "done", "failed"), interval=0.05, timeout=60)   # 讓背景 render 收尾


# ---------------- comics: 建系列 → 素材 → 定位 → 動態漫畫影片 (mock) ----------------
@_needs_ffmpeg
async def test_comics_flow_to_video(env, tmp_path):
    _, server = env
    png = tmp_path / "s.png"
    png.write_bytes(__import__("base64").b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="))
    async with MCPClient(server) as mc:
        await _call(mc, "create_project", project_id="course", title="課程")
        err, _ = await _call(mc, "comics_create_series", project_id="course", series_id="wind", title="海風值班日誌",
                             characters=[{"character_id": "dofu", "name": "杜夫"}])
        assert not err
        err, _ = await _call(mc, "comics_create_episode", project_id="course", series_id="wind", story_id="W01", title="第一話",
                             fields={"page_count": 1, "learning_objectives": ["x"], "characters": ["dofu"]})
        assert not err
        err, _ = await _call(mc, "comics_update_episode", project_id="course", story_id="W01", updates={
            "pages": [{"page_no": 1, "image_prompt": "p", "alt_text": "a",
                       "dialogues": [{"dialogue_id": "d1", "speaker_id": "dofu", "text": "先保留證據。"}]}],
            "state": "STORYBOARD"})
        assert not err
        err, ep = await _call(mc, "comics_upload_asset", project_id="course", story_id="W01", file_path=str(png),
                              kind="scene", provenance="test", asset_id="scene_1")
        assert not err and any(a["asset_id"] == "scene_1" for a in ep["assets"])
        err, _ = await _call(mc, "comics_update_episode", project_id="course", story_id="W01",
                             updates={"pages": [{**ep["pages"][0], "image_asset_id": "scene_1"}]})
        assert not err
        err, laid = await _call(mc, "comics_locate_speakers", project_id="course", story_id="W01", mock=True)
        assert not err and laid["pages"][0]["speaker_positions"]
        err, v = await _call(mc, "comics_validation", project_id="course", story_id="W01")
        assert not err
        err, created = await _call(mc, "comics_render_video", project_id="course", story_id="W01", mock=True,
                                   fps=5, width=320, height=180, voices={"dofu": "default"})
        assert not err, created
        err, rec = await _call(mc, "wait_job", job_id=created["job_id"], until=["done", "failed"], interval=0.05, timeout=120)
        assert not err and rec["state"] == "done", rec.get("error") if isinstance(rec, dict) else rec
        assert any(a["name"].endswith(".mp4") for a in rec["artifacts"])
