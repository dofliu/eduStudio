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
