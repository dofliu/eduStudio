"""iter 63a regression test: pipeline._RENDERERS 該認得所有 deck schema
會出現的 bg_type, 不該 raise '未知的 bg_type'.

背景: iter 62 加封面 (bg_type=cover) + iter 63 加結尾 (bg_type=outro),
但 pipeline._RENDERERS 一直只有 blackboard / slide / pptx_slide. 跑全
pipeline 時就會踩 ValueError. 加這條測試避免回頭.
"""
from __future__ import annotations

import pipeline


class TestRenderersDispatch:
    """所有 deck schema 會塞進 bg_type 的值, 都該在 _RENDERERS 找得到."""

    def test_blackboard_registered(self):
        assert pipeline._RENDERERS.get("blackboard") is not None

    def test_slide_registered(self):
        assert pipeline._RENDERERS.get("slide") is not None

    def test_pptx_slide_registered(self):
        assert pipeline._RENDERERS.get("pptx_slide") is not None

    def test_cover_registered(self):
        """iter 62: 封面 slide 走 pptx renderer."""
        assert pipeline._RENDERERS.get("cover") is not None

    def test_outro_registered(self):
        """iter 63: 結尾 slide 走 pptx renderer."""
        assert pipeline._RENDERERS.get("outro") is not None

    def test_cover_outro_share_pptx_renderer(self):
        """cover / outro / pptx_slide 該是同一個 instance (省記憶體 + 行為一致)."""
        assert pipeline._RENDERERS["cover"] is pipeline._RENDERERS["pptx_slide"]
        assert pipeline._RENDERERS["outro"] is pipeline._RENDERERS["pptx_slide"]

    def test_unknown_bg_type_raises(self):
        """未登錄的 bg_type 應 raise ValueError (defensive, 抓 typo)."""
        import pytest
        from pathlib import Path
        data = {
            "steps": [{
                "bg_type": "nonexistent_renderer_xyz",
                "title": "t", "bullets": [], "narration": "n",
            }],
        }
        with pytest.raises(ValueError, match="未知的 bg_type"):
            pipeline.render_frame(data, 1, Path("/tmp/x.png"), Path("/tmp"))
