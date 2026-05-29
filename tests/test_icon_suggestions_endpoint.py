"""E2-6 backend (iter 107): GET /jobs/{id}/icon-suggestions endpoint.

包 core.icon_picker.suggest_for_deck 給 review UI 一次拿全 deck icon 建議.

測試重點:
- happy path: deck 有 sections.slides, 該命中的命中 (序列化正確, Path → str)
- exam_pdf schema (problems, 沒 sections.slides) → suggestions={}
- deck.json 不存在 → 404
- query params (require_file_exists / max_icons) 透傳
- max_icons 範圍驗證 (1~20, FastAPI Query)
- 沒命中也保留 slide_id key=[] (給 UI「這 slide 沒建議」狀態)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.jobs import JobStore, get_default_store
from server.main import create_app


@pytest.fixture
def store_with_tmp(tmp_path):
    """JobStore 接 tmp_path, app inject 進 dependency_overrides."""
    store = JobStore(root=tmp_path / "jobs")
    app = create_app()
    app.dependency_overrides[get_default_store] = lambda: store
    return store, app


@pytest.fixture
def client(store_with_tmp):
    _, app = store_with_tmp
    return TestClient(app)


@pytest.fixture
def make_job_with_deck(store_with_tmp):
    """建 job_dir + 寫 deck.json."""
    store, _ = store_with_tmp

    def _make(job_id: str, deck: dict | None = None) -> Path:
        job_dir = store.root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        if deck is not None:
            (job_dir / "deck.json").write_text(
                json.dumps(deck, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return job_dir
    return _make


@pytest.fixture
def fake_icon_library(tmp_path: Path, monkeypatch):
    """Patch icon_picker module-level path 到 tmp_path 假 library, 隔離真 manifest.

    建立 manifest + 兩 svg 檔, 對應 keyword 'wind' / 'pid'.
    """
    library_root = tmp_path / "fake_lib"
    library_root.mkdir()
    # 假 svg 檔
    (library_root / "wind").mkdir()
    (library_root / "wind" / "wind_turbine.svg").write_text("<svg/>", encoding="utf-8")
    (library_root / "control").mkdir()
    (library_root / "control" / "pid_block.svg").write_text("<svg/>", encoding="utf-8")
    # manifest
    manifest = {
        "_schema_version": 1,
        "icons": {
            "wind_turbine": {
                "icon": "wind/wind_turbine.svg",
                "keywords": ["wind turbine", "風機"],
                "position": "top-right",
                "size_ratio": 0.12,
                "domain": "wind",
            },
            "pid_block": {
                "icon": "control/pid_block.svg",
                "keywords": ["PID", "閉迴路"],
                "position": "bottom-right",
                "size_ratio": 0.10,
                "domain": "control",
            },
        },
    }
    manifest_path = library_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    from core import icon_picker
    monkeypatch.setattr(icon_picker, "ICON_LIBRARY_ROOT", library_root)
    monkeypatch.setattr(icon_picker, "MANIFEST_PATH", manifest_path)
    return library_root


class TestIconSuggestionsHappyPath:
    def test_deck_with_matching_narration_returns_suggestions(
        self, client, make_job_with_deck, fake_icon_library
    ):
        """deck slide narration 含 keyword → 該 slide_id 有 IconMatch."""
        deck = {
            "deck_title": "風能控制系統",
            "sections": [
                {
                    "id": "intro",
                    "title": "介紹",
                    "slides": [
                        {
                            "id": "intro_1",
                            "title": "風機概念",
                            "narration": "今天介紹風機的基本概念.",
                        },
                        {
                            "id": "intro_2",
                            "title": "PID 控制",
                            "narration": "PID 是常用控制器.",
                        },
                    ],
                }
            ],
        }
        make_job_with_deck("job1", deck=deck)
        r = client.get("/jobs/job1/icon-suggestions")
        assert r.status_code == 200
        body = r.json()
        assert "suggestions" in body
        sug = body["suggestions"]
        # 兩 slide 都該有 key
        assert set(sug.keys()) == {"intro_1", "intro_2"}
        # intro_1 命中 wind, intro_2 命中 pid
        assert len(sug["intro_1"]) == 1
        assert sug["intro_1"][0]["key"] == "wind_turbine"
        assert sug["intro_1"][0]["matched_keyword"] == "風機"
        assert sug["intro_1"][0]["domain"] == "wind"
        assert sug["intro_1"][0]["file_exists"] is True
        # icon path 是 str (不是 PosixPath JSON dump 不下)
        assert isinstance(sug["intro_1"][0]["icon"], str)
        assert "wind_turbine.svg" in sug["intro_1"][0]["icon"]
        # intro_2
        assert sug["intro_2"][0]["key"] == "pid_block"

    def test_slide_with_no_match_preserves_empty_list(
        self, client, make_job_with_deck, fake_icon_library
    ):
        """沒命中也保留 slide_id=[] — 跟「沒掃到」做出區別."""
        deck = {
            "deck_title": "x",
            "sections": [
                {
                    "id": "s1",
                    "title": "t",
                    "slides": [
                        {
                            "id": "slide_a",
                            "title": "a",
                            "narration": "完全沒有關鍵字的句子",
                        },
                    ],
                }
            ],
        }
        make_job_with_deck("job2", deck=deck)
        r = client.get("/jobs/job2/icon-suggestions")
        assert r.status_code == 200
        sug = r.json()["suggestions"]
        assert sug == {"slide_a": []}


class TestIconSuggestionsSerialization:
    """endpoint 親手組的 payload dict (jobs.py) — position / size_ratio 兩欄
    沒被 happy path 鎖過, 純靠 endpoint 從 IconMatch.position / .size_ratio
    搬過來. 若有人重構漏掉這兩欄, 前端 alpha_composite 疊圖位置 / 大小就錯,
    但既有測試不會紅. 這裡把『全 7 欄都序列化正確』鎖死."""

    def test_payload_includes_position_and_size_ratio(
        self, client, make_job_with_deck, fake_icon_library
    ):
        """命中的 IconMatch position / size_ratio 要原樣出現在 payload."""
        deck = {
            "deck_title": "x",
            "sections": [
                {
                    "id": "s",
                    "title": "t",
                    "slides": [
                        {"id": "wind", "title": "t", "narration": "介紹風機"},
                        {"id": "ctrl", "title": "t", "narration": "PID 控制器"},
                    ],
                }
            ],
        }
        make_job_with_deck("ser", deck=deck)
        r = client.get("/jobs/ser/icon-suggestions")
        assert r.status_code == 200
        sug = r.json()["suggestions"]
        # fake_icon_library: wind_turbine position=top-right size_ratio=0.12
        w = sug["wind"][0]
        assert w["position"] == "top-right"
        assert w["size_ratio"] == 0.12
        # 7 欄全在 (前端契約)
        assert set(w.keys()) == {
            "key", "icon", "matched_keyword", "position",
            "size_ratio", "domain", "file_exists",
        }
        # pid_block position=bottom-right size_ratio=0.10
        c = sug["ctrl"][0]
        assert c["position"] == "bottom-right"
        assert c["size_ratio"] == 0.10


class TestIconSuggestionsMaxIconsBoundary:
    """max_icons ge=1 le=20 — 既有只測界外 (0 / 21 → 422), 沒測界內值被接受.
    鎖 ge/le 是『含端點』(1 與 20 該 200 不該 422), 防有人改成 gt/lt."""

    def test_max_icons_lower_bound_accepted(
        self, client, make_job_with_deck, fake_icon_library
    ):
        make_job_with_deck("lo", deck={"deck_title": "x", "sections": []})
        r = client.get("/jobs/lo/icon-suggestions?max_icons=1")
        assert r.status_code == 200

    def test_max_icons_upper_bound_accepted(
        self, client, make_job_with_deck, fake_icon_library
    ):
        make_job_with_deck("hi", deck={"deck_title": "x", "sections": []})
        r = client.get("/jobs/hi/icon-suggestions?max_icons=20")
        assert r.status_code == 200


class TestIconSuggestionsExamSchema:
    def test_exam_pdf_deck_returns_empty(
        self, client, make_job_with_deck, fake_icon_library
    ):
        """v1 exam schema (problems, 沒 sections.slides) → suggestions={}."""
        exam_deck = {
            "exam_title": "材力期中",
            "problems": [
                {"id": "q1", "number": "第 1 題", "problem": "...", "steps": []},
            ],
        }
        make_job_with_deck("exam1", deck=exam_deck)
        r = client.get("/jobs/exam1/icon-suggestions")
        assert r.status_code == 200
        assert r.json() == {"suggestions": {}}


class TestIconSuggestionsErrors:
    def test_no_deck_returns_404(self, client, make_job_with_deck):
        make_job_with_deck("no_deck")  # 不寫 deck.json
        r = client.get("/jobs/no_deck/icon-suggestions")
        assert r.status_code == 404

    def test_nonexistent_job_returns_404(self, client):
        r = client.get("/jobs/doesnotexist/icon-suggestions")
        assert r.status_code == 404

    def test_max_icons_below_range_422(
        self, client, make_job_with_deck, fake_icon_library
    ):
        make_job_with_deck("j", deck={"deck_title": "x", "sections": []})
        r = client.get("/jobs/j/icon-suggestions?max_icons=0")
        assert r.status_code == 422

    def test_max_icons_above_range_422(
        self, client, make_job_with_deck, fake_icon_library
    ):
        make_job_with_deck("j", deck={"deck_title": "x", "sections": []})
        r = client.get("/jobs/j/icon-suggestions?max_icons=21")
        assert r.status_code == 422


class TestIconSuggestionsQueryParams:
    def test_max_icons_caps_results(
        self, client, make_job_with_deck, fake_icon_library
    ):
        """max_icons=1 → 同 narration 命中 wind + pid 只回第一個."""
        deck = {
            "deck_title": "x",
            "sections": [
                {
                    "id": "s",
                    "title": "t",
                    "slides": [
                        {
                            "id": "both",
                            "title": "b",
                            "narration": "風機跟 PID 同時提到",
                        }
                    ],
                }
            ],
        }
        make_job_with_deck("cap", deck=deck)
        r = client.get("/jobs/cap/icon-suggestions?max_icons=1")
        assert r.status_code == 200
        assert len(r.json()["suggestions"]["both"]) == 1

    def test_require_file_exists_false_includes_missing(
        self, client, make_job_with_deck, tmp_path, monkeypatch
    ):
        """require_file_exists=false → SVG 缺檔的 entry 仍回, file_exists=False."""
        library_root = tmp_path / "lib_missing"
        library_root.mkdir()
        # 不建 svg, manifest 指向缺檔
        manifest = {
            "_schema_version": 1,
            "icons": {
                "missing_icon": {
                    "icon": "nope/ghost.svg",
                    "keywords": ["ghost"],
                    "position": "center",
                    "size_ratio": 0.15,
                    "domain": "generic",
                },
            },
        }
        manifest_path = library_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        from core import icon_picker
        monkeypatch.setattr(icon_picker, "ICON_LIBRARY_ROOT", library_root)
        monkeypatch.setattr(icon_picker, "MANIFEST_PATH", manifest_path)

        deck = {
            "deck_title": "x",
            "sections": [
                {
                    "id": "s",
                    "title": "t",
                    "slides": [
                        {"id": "gh", "title": "t", "narration": "ghost in the shell"},
                    ],
                }
            ],
        }
        make_job_with_deck("miss", deck=deck)

        # 預設 require_file_exists=true → 過濾掉
        r1 = client.get("/jobs/miss/icon-suggestions")
        assert r1.status_code == 200
        assert r1.json()["suggestions"]["gh"] == []

        # false → 仍回, file_exists=False
        r2 = client.get("/jobs/miss/icon-suggestions?require_file_exists=false")
        assert r2.status_code == 200
        gh = r2.json()["suggestions"]["gh"]
        assert len(gh) == 1
        assert gh[0]["key"] == "missing_icon"
        assert gh[0]["file_exists"] is False
