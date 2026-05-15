"""server/runner.py — iter 53 _resolve_step_image_paths.

純函式 IO helper, 不打 ffmpeg / Gemini. 用 tmp_path 模擬 figures/ 目錄.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from server.runner import _resolve_step_image_paths


@pytest.fixture
def figures_dir(tmp_path):
    """產 figures/ 目錄, 內含幾張假 figure 檔."""
    d = tmp_path / "figures"
    d.mkdir()
    (d / "fig_p3_1.png").write_bytes(b"\x89PNG fake")
    (d / "fig_p7_2.jpeg").write_bytes(b"\xff\xd8\xff fake jpeg")
    return d


class TestResolveStepImagePaths:
    def test_valid_id_resolved_to_absolute_path(self, figures_dir):
        steps = [{"image_path": "fig_p3_1"}]
        _resolve_step_image_paths(steps, figures_dir)
        resolved = steps[0]["image_path"]
        assert resolved is not None
        assert Path(resolved).exists()
        assert Path(resolved).name == "fig_p3_1.png"
        assert Path(resolved).is_absolute()

    def test_jpeg_extension_also_found(self, figures_dir):
        steps = [{"image_path": "fig_p7_2"}]
        _resolve_step_image_paths(steps, figures_dir)
        assert steps[0]["image_path"] is not None
        assert Path(steps[0]["image_path"]).name == "fig_p7_2.jpeg"

    def test_missing_figure_set_to_none(self, figures_dir):
        """deck.json 有 image_path 但 figures/ 沒對應檔 → None (退 fallback)."""
        steps = [{"image_path": "fig_p99_99"}]
        _resolve_step_image_paths(steps, figures_dir)
        assert steps[0]["image_path"] is None

    def test_no_image_path_stays_none(self, figures_dir):
        steps = [{"image_path": None}]
        _resolve_step_image_paths(steps, figures_dir)
        assert steps[0]["image_path"] is None

    def test_missing_key_added_as_none(self, figures_dir):
        steps = [{"title": "no image"}]
        _resolve_step_image_paths(steps, figures_dir)
        assert steps[0]["image_path"] is None

    def test_path_traversal_rejected(self, figures_dir):
        """防 path traversal — image_path 內含 ../ 或 / 該被拒絕."""
        steps = [
            {"image_path": "../../etc/passwd"},
            {"image_path": "/abs/path"},
            {"image_path": "fig\\..\\evil"},
        ]
        _resolve_step_image_paths(steps, figures_dir)
        for s in steps:
            assert s["image_path"] is None

    def test_non_string_set_to_none(self, figures_dir):
        steps = [{"image_path": 12345}]
        _resolve_step_image_paths(steps, figures_dir)
        assert steps[0]["image_path"] is None

    def test_no_figures_dir_safe(self, tmp_path):
        """figures/ 不存在 (URL / md / txt job 都這樣) → 全部 image_path 設 None."""
        steps = [{"image_path": "fig_p3_1"}, {"image_path": None}]
        _resolve_step_image_paths(steps, tmp_path / "no_such_dir")
        for s in steps:
            assert s["image_path"] is None

    def test_empty_steps_safe(self, figures_dir):
        steps = []
        _resolve_step_image_paths(steps, figures_dir)
        assert steps == []

    def test_multiple_steps_each_resolved(self, figures_dir):
        steps = [
            {"image_path": "fig_p3_1"},
            {"image_path": "fig_p7_2"},
            {"image_path": "nope"},
            {"image_path": None},
        ]
        _resolve_step_image_paths(steps, figures_dir)
        assert steps[0]["image_path"] is not None
        assert steps[1]["image_path"] is not None
        assert steps[2]["image_path"] is None
        assert steps[3]["image_path"] is None
