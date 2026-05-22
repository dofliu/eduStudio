"""SlideRenderer 行為測試 (Phase 4 split-left layout).

不真的渲染 PNG (PIL + 字型 + 底圖會讓 test 變脆), 改 mock 兩個 _render_* method
驗 dispatch 走對分支。
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

# pipeline.py 在頂部 import PIL / mutagen 等, CI 環境 (有裝 Pillow) 可以跑,
# 但 mutagen 不在必要 deps 裡 — 跟 test_hardsub.py 一致用 importorskip 跳過。
pipeline = pytest.importorskip(
    "pipeline",
    reason="pipeline.py 需要 PIL / mutagen, CI 沒裝就跳過",
)
SlideRenderer = pipeline.SlideRenderer


def _step(layout: str | None) -> dict:
    s = {"display": "x", "narration": "n", "bg_type": "slide", "bg_image": "p.png"}
    if layout is not None:
        s["layout"] = layout
    return s


@pytest.fixture
def renderer() -> SlideRenderer:
    return SlideRenderer()


class TestLayoutDispatch:
    def test_full_default_when_layout_missing(self, renderer):
        data = {"steps": [_step(None)]}
        with patch.object(renderer, "_render_full") as m_full, \
             patch.object(renderer, "_render_split_left") as m_split:
            renderer.render(data, 1, out_p="x.png", q_work="w")
            m_full.assert_called_once()
            m_split.assert_not_called()

    def test_full_explicit(self, renderer):
        data = {"steps": [_step("full")]}
        with patch.object(renderer, "_render_full") as m_full, \
             patch.object(renderer, "_render_split_left") as m_split:
            renderer.render(data, 1, out_p="x.png", q_work="w")
            m_full.assert_called_once()
            m_split.assert_not_called()

    def test_split_left(self, renderer):
        data = {"steps": [_step("split-left")]}
        with patch.object(renderer, "_render_full") as m_full, \
             patch.object(renderer, "_render_split_left") as m_split:
            renderer.render(data, 1, out_p="x.png", q_work="w")
            m_split.assert_called_once()
            m_full.assert_not_called()

    def test_layout_case_insensitive(self, renderer):
        # 容錯: SPLIT-LEFT / Split-Left 都應 dispatch 到 split-left
        data = {"steps": [_step("Split-Left")]}
        with patch.object(renderer, "_render_full") as m_full, \
             patch.object(renderer, "_render_split_left") as m_split:
            renderer.render(data, 1, out_p="x.png", q_work="w")
            m_split.assert_called_once()
            m_full.assert_not_called()

    def test_unknown_layout_falls_back_to_full(self, renderer):
        # 未知 layout (typo / 未來新增還沒接) 退到 full, 不 raise
        data = {"steps": [_step("center-stage")]}
        with patch.object(renderer, "_render_full") as m_full, \
             patch.object(renderer, "_render_split_left") as m_split:
            renderer.render(data, 1, out_p="x.png", q_work="w")
            m_full.assert_called_once()
            m_split.assert_not_called()


class TestResolveStepBg:
    """iter 105: _resolve_step_bg helper — image_frames 終端 frame fallback DRY.

    驗證兩 layout 共用同一條解析路徑, 避免日後新增 layout 漏接 (iter 104 兩處
    重複寫 import + terminal_frame call 的代價).
    """

    def test_no_image_frames_uses_bg_image(self, renderer):
        step = {"bg_image": "deck/page1.png"}
        bg_rel, bg_path = renderer._resolve_step_bg(step, step_idx=1)
        assert bg_rel == "deck/page1.png"
        assert bg_path is not None
        # _resolve_asset 給絕對路徑, 不檢驗 .exists() (測試環境沒檔)
        assert bg_path.name == "page1.png"

    def test_empty_bg_image_returns_none_path(self, renderer):
        step = {"bg_image": ""}
        bg_rel, bg_path = renderer._resolve_step_bg(step, step_idx=1)
        assert bg_rel == ""
        assert bg_path is None

    def test_missing_bg_image_key_returns_none_path(self, renderer):
        step = {}  # 完全沒 bg_image / image_frames
        bg_rel, bg_path = renderer._resolve_step_bg(step, step_idx=1)
        assert bg_rel == ""
        assert bg_path is None

    def test_image_frames_terminal_overrides_bg_image(self, renderer, tmp_path):
        # 三 frame, terminal = 最高 display_ratio. 該蓋掉 bg_image
        f1 = tmp_path / "f1.png"; f1.write_bytes(b"")
        f3 = tmp_path / "f3.png"; f3.write_bytes(b"")
        step = {
            "bg_image": "deck/should_be_overridden.png",
            "image_frames": [
                {"path": str(f1), "display_ratio": 0.3},
                {"path": str(f3), "display_ratio": 1.0},
            ],
        }
        bg_rel, bg_path = renderer._resolve_step_bg(step, step_idx=2)
        assert bg_rel == str(f3)
        assert bg_path is not None
        assert bg_path.exists()  # 真存在的 tmp 檔

    def test_invalid_image_frames_falls_back_to_bg_image(self, renderer):
        # 全部 entry 無效 (缺檔 / 越界) → terminal_frame() = None → 用 bg_image
        step = {
            "bg_image": "deck/keep_me.png",
            "image_frames": [
                {"path": "/nonexistent/x.png", "display_ratio": 0.5},  # 缺檔
                {"path": "/nonexistent/y.png", "display_ratio": 1.5},  # 越界 + 缺檔
            ],
        }
        bg_rel, bg_path = renderer._resolve_step_bg(step, step_idx=3)
        assert bg_rel == "deck/keep_me.png"
        assert bg_path.name == "keep_me.png"

    def test_none_image_frames_uses_bg_image(self, renderer):
        step = {"bg_image": "deck/page.png", "image_frames": None}
        bg_rel, bg_path = renderer._resolve_step_bg(step, step_idx=1)
        assert bg_rel == "deck/page.png"

    def test_image_frames_only_no_bg_image(self, renderer, tmp_path):
        # 沒 bg_image 但有 image_frames — terminal frame 仍生效
        f = tmp_path / "only.png"; f.write_bytes(b"")
        step = {
            "image_frames": [
                {"path": str(f), "display_ratio": 1.0},
            ],
        }
        bg_rel, bg_path = renderer._resolve_step_bg(step, step_idx=4)
        assert bg_rel == str(f)
        assert bg_path.exists()

    def test_override_prints_debug_line(self, renderer, tmp_path, capsys):
        # 過渡期 debug log — image_frames 覆蓋時印一行, 方便看 bg 來源
        f = tmp_path / "f.png"; f.write_bytes(b"")
        step = {
            "bg_image": "deck/x.png",
            "image_frames": [{"path": str(f), "display_ratio": 1.0}],
        }
        renderer._resolve_step_bg(step, step_idx=7)
        out = capsys.readouterr().out
        assert "image_frames" in out
        assert "007" in out  # step_idx zfill 3
        assert str(f) in out

    def test_no_override_no_debug_line(self, renderer, capsys):
        step = {"bg_image": "deck/x.png"}  # 沒 image_frames
        renderer._resolve_step_bg(step, step_idx=1)
        out = capsys.readouterr().out
        assert "image_frames" not in out
