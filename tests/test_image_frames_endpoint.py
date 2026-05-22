"""E1-4 backend (iter 109): GET /jobs/{id}/image-frames endpoint.

包 core.image_frames.summarize_for_deck 給 review UI 一次拿全 deck frame summary.

測試重點:
- happy path: deck 有 sections.slides.image_frames, 該命中的命中 (terminal_path 是 str)
- exam_pdf schema (problems, 沒 sections.slides) → summary={}
- deck.json 不存在 → 404
- 沒 image_frames 的 slide 仍保留 entry (count=0, has_frames=False)
- query param require_file_exists 透傳 (true 嚴格 vs false 寬鬆)
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
def fake_frames(tmp_path: Path):
    """建幾個假 PNG 給 valid_frames require_file_exists=True 可命中."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    paths = {}
    for name in ("f1.png", "f2.png", "f3.png"):
        p = frames_dir / name
        p.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic only, 內容不重要
        paths[name] = str(p)
    return paths


class TestImageFramesHappyPath:
    def test_deck_with_frames_returns_summary(
        self, client, make_job_with_deck, fake_frames
    ):
        """有效 image_frames → count / terminal_path / has_frames 都正確."""
        deck = {
            "deck_title": "demo",
            "sections": [
                {
                    "id": "intro",
                    "title": "介紹",
                    "slides": [
                        {
                            "id": "intro_1",
                            "title": "三 frame slide",
                            "narration": "...",
                            "image_frames": [
                                {"path": fake_frames["f1.png"], "display_ratio": 0.33},
                                {"path": fake_frames["f2.png"], "display_ratio": 0.66},
                                {"path": fake_frames["f3.png"], "display_ratio": 1.0},
                            ],
                        },
                    ],
                }
            ],
        }
        make_job_with_deck("job1", deck=deck)
        r = client.get("/jobs/job1/image-frames")
        assert r.status_code == 200
        body = r.json()
        assert "summary" in body
        s = body["summary"]
        assert set(s.keys()) == {"intro_1"}
        assert s["intro_1"]["count"] == 3
        assert s["intro_1"]["has_frames"] is True
        # terminal 是 display_ratio 最大那筆 (f3.png), Path → str 序列化過
        assert isinstance(s["intro_1"]["terminal_path"], str)
        assert s["intro_1"]["terminal_path"].endswith("f3.png")

    def test_slide_without_frames_preserves_entry(
        self, client, make_job_with_deck
    ):
        """沒 image_frames 的 slide 仍保留 — count=0 / terminal=None / has=False
        (跟「沒掃到」做出區別)."""
        deck = {
            "deck_title": "x",
            "sections": [
                {
                    "id": "s",
                    "title": "t",
                    "slides": [
                        {"id": "no_frames", "title": "t", "narration": "..."},
                    ],
                }
            ],
        }
        make_job_with_deck("job2", deck=deck)
        r = client.get("/jobs/job2/image-frames")
        assert r.status_code == 200
        s = r.json()["summary"]
        assert s == {
            "no_frames": {"count": 0, "terminal_path": None, "has_frames": False},
        }

    def test_multi_section_preserves_all_ids(
        self, client, make_job_with_deck, fake_frames
    ):
        """跨多 section, 每個 slide 都該在 summary 出現."""
        deck = {
            "deck_title": "x",
            "sections": [
                {
                    "id": "a",
                    "title": "A",
                    "slides": [
                        {
                            "id": "a1",
                            "title": "t",
                            "narration": "n",
                            "image_frames": [
                                {"path": fake_frames["f1.png"], "display_ratio": 1.0}
                            ],
                        },
                        {"id": "a2", "title": "t", "narration": "n"},
                    ],
                },
                {
                    "id": "b",
                    "title": "B",
                    "slides": [
                        {"id": "b1", "title": "t", "narration": "n",
                         "image_frames": None},
                    ],
                },
            ],
        }
        make_job_with_deck("job3", deck=deck)
        r = client.get("/jobs/job3/image-frames")
        assert r.status_code == 200
        s = r.json()["summary"]
        assert set(s.keys()) == {"a1", "a2", "b1"}
        assert s["a1"]["count"] == 1
        assert s["a1"]["has_frames"] is True
        assert s["a2"]["count"] == 0
        assert s["a2"]["has_frames"] is False
        assert s["b1"]["count"] == 0
        assert s["b1"]["has_frames"] is False


class TestImageFramesExamSchema:
    def test_exam_pdf_deck_returns_empty(
        self, client, make_job_with_deck
    ):
        """v1 exam schema (problems, 沒 sections.slides) → summary={}."""
        exam_deck = {
            "exam_title": "材力期中",
            "problems": [
                {"id": "q1", "number": "第 1 題", "problem": "...", "steps": []},
            ],
        }
        make_job_with_deck("exam1", deck=exam_deck)
        r = client.get("/jobs/exam1/image-frames")
        assert r.status_code == 200
        assert r.json() == {"summary": {}}


class TestImageFramesErrors:
    def test_no_deck_returns_404(self, client, make_job_with_deck):
        make_job_with_deck("no_deck")  # 不寫 deck.json
        r = client.get("/jobs/no_deck/image-frames")
        assert r.status_code == 404

    def test_nonexistent_job_returns_404(self, client):
        r = client.get("/jobs/doesnotexist/image-frames")
        assert r.status_code == 404


class TestImageFramesQueryParams:
    def test_require_file_exists_false_includes_missing(
        self, client, make_job_with_deck, tmp_path
    ):
        """require_file_exists=false → 檔不存在的 frame 仍算進 count.

        嚴格 (預設 true): 缺檔 entry 被 valid_frames 過濾, count=0
        寬鬆 (false): 缺檔 entry 算數, count > 0 + terminal_path 是缺檔路徑
        — review UI 提案階段顯示「將會」有的 frame.
        """
        missing_path = str(tmp_path / "ghost.png")  # 故意不寫檔
        deck = {
            "deck_title": "x",
            "sections": [
                {
                    "id": "s",
                    "title": "t",
                    "slides": [
                        {
                            "id": "ghost",
                            "title": "t",
                            "narration": "n",
                            "image_frames": [
                                {"path": missing_path, "display_ratio": 1.0},
                            ],
                        },
                    ],
                }
            ],
        }
        make_job_with_deck("miss", deck=deck)

        # 預設嚴格 → 過濾掉
        r1 = client.get("/jobs/miss/image-frames")
        assert r1.status_code == 200
        assert r1.json()["summary"]["ghost"] == {
            "count": 0, "terminal_path": None, "has_frames": False,
        }

        # 寬鬆 → 仍回, terminal 是缺檔路徑
        r2 = client.get("/jobs/miss/image-frames?require_file_exists=false")
        assert r2.status_code == 200
        gh = r2.json()["summary"]["ghost"]
        assert gh["count"] == 1
        assert gh["has_frames"] is True
        assert gh["terminal_path"] == missing_path

    def test_empty_sections_returns_empty_summary(
        self, client, make_job_with_deck
    ):
        """sections=[] (合法 deck 雛形) → summary={}."""
        make_job_with_deck("empty", deck={"deck_title": "x", "sections": []})
        r = client.get("/jobs/empty/image-frames")
        assert r.status_code == 200
        assert r.json() == {"summary": {}}
