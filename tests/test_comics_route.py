"""Comic Production API offline integration tests。"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi")
pytest.importorskip("multipart", reason="server.main upload routes 需要")

from fastapi.testclient import TestClient

from core.comics import ComicStore
from core.project import ProjectStore
from server.main import create_app
import server.routes.comics as comics_routes
import server.routes.projects as projects_routes


@pytest.fixture
def client(tmp_path):
    app = create_app()
    project_store = ProjectStore(tmp_path / "projects")
    comic_store = ComicStore(tmp_path / "projects")
    app.dependency_overrides[projects_routes.get_default_project_store] = lambda: project_store
    app.dependency_overrides[comics_routes.get_default_comic_store] = lambda: comic_store
    with TestClient(app) as test_client:
        yield test_client, project_store, comic_store


def _bootstrap(client: TestClient) -> None:
    assert client.post("/projects", json={"project_id": "p", "title": "課程"}).status_code == 201
    assert client.post("/projects/p/comics/series", json={
        "series_id": "series_1",
        "title": "教學漫畫",
        "characters": [{
            "character_id": "teacher",
            "name": "老師",
            "role": "Instructor",
            "visual_lock": "adult teacher, navy jacket",
        }],
    }).status_code == 201
    assert client.post("/projects/p/comics/episodes", json={
        "series_id": "series_1",
        "story_id": "W01_C01",
        "title": "第一話",
        "page_count": 2,
        "story_brief": "解釋 evidence gate",
        "learning_objectives": ["理解 evidence gate"],
        "characters": ["teacher"],
    }).status_code == 201


def test_crud_and_offline_generation(client) -> None:
    c, *_ = client
    _bootstrap(c)
    assert c.get("/projects/p/comics/capabilities").json()["file_first"] is True
    assert len(c.get("/projects/p/comics/series").json()) == 1

    script = c.post("/projects/p/comics/episodes/W01_C01/generate/script", json={"mock": True})
    assert script.status_code == 200 and script.json()["story_summary"].startswith("MOCK")
    storyboard = c.post("/projects/p/comics/episodes/W01_C01/generate/storyboard", json={"mock": True})
    assert storyboard.status_code == 200 and len(storyboard.json()["pages"]) == 2
    prompts = c.post("/projects/p/comics/episodes/W01_C01/compose-prompts")
    assert prompts.status_code == 200 and prompts.json()["pages"][0]["image_prompt"]
    images = c.post("/projects/p/comics/episodes/W01_C01/generate/images", json={"mock": True})
    assert images.status_code == 200 and images.json()["generated"] == [1, 2]
    layout = c.post("/projects/p/comics/episodes/W01_C01/auto-layout")
    assert layout.status_code == 200 and layout.json()["state"] == "LAYOUT"
    first_dialogue = layout.json()["pages"][0]["dialogues"][0]
    assert first_dialogue["bubble_style"] == "rounded_callout"
    assert first_dialogue["tail_x"] is not None and first_dialogue["tail_y"] is not None

    report = c.get("/projects/p/comics/episodes/W01_C01/validation").json()
    assert report["publish_ready"] is False
    assert any(item["check"] == "asset_provenance" and item["result"] == "FAIL" for item in report["items"])


def test_current_and_publish_are_gated(client) -> None:
    c, *_ = client
    _bootstrap(c)
    current = c.post("/projects/p/comics/episodes/W01_C01/state", json={"target": "CURRENT"})
    assert current.status_code == 422
    publish = c.post("/projects/p/comics/episodes/W01_C01/publish", json={"published_by": "teacher"})
    assert publish.status_code == 422


def test_source_export_is_downloadable(client) -> None:
    c, *_ = client
    _bootstrap(c)
    response = c.post("/projects/p/comics/episodes/W01_C01/exports/source")
    assert response.status_code == 200
    link = response.json()["download_url"]
    downloaded = c.get(link)
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"PK")


def test_discovery_missing_path_is_reported(client) -> None:
    c, *_ = client
    _bootstrap(c)
    response = c.post("/projects/p/comics/discover", json={
        "series_id": "series_1",
        "package_path": "Z:/does-not-exist",
    })
    assert response.status_code == 400


def test_locate_speakers_mock_writes_positions_and_relayouts(client) -> None:
    c, _, comic_store = client
    _bootstrap(c)
    from core.comics import ComicPage, Dialogue
    pages = [ComicPage(page_no=n, dialogues=[Dialogue(dialogue_id=f"p{n}d1", speaker_id="teacher", text="先看證據。")],
                       image_prompt="p", alt_text="a") for n in (1, 2)]
    comic_store.update_episode("p", "W01_C01", "v0.1", {"pages": pages, "state": "STORYBOARD"})
    from core.comics import make_mock_scene, decode_data_url
    for n in (1, 2):
        raw, suffix = decode_data_url(make_mock_scene(n))
        comic_store.attach_asset("p", "W01_C01", "v0.1", filename=f"s{n}{suffix}", data=raw, kind="scene",
                                 provenance="mock_placeholder", asset_id=f"scene_{n}")
        comic_store.set_page_asset("p", "W01_C01", "v0.1", n, f"scene_{n}")
    r = c.post("/projects/p/comics/episodes/W01_C01/locate-speakers?version=v0.1", json={"mock": True, "page_numbers": [1]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pages"][0]["speaker_positions"] == {"teacher": [0.5, 0.42]}
    assert body["pages"][1]["speaker_positions"] == {}
    d = body["pages"][0]["dialogues"][0]
    assert (d["tail_x"], d["tail_y"]) == (0.5, 0.42)
