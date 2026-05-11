"""core/visuals.py 集中 layout 常數 — 鎖值 + 跨檔 import 一致性。

這支不是要測渲染輸出 (那是 visual integration 範圍), 純粹確保:
1. 常數值穩定 (改值要先改測試, 等同 review gate)
2. pipeline.py / core.render.pptx_style 都 import 同一份常數
   (防 Round 2 lessons-learned #3 那種 "改一處忘改另一處" 再復發)
"""
from __future__ import annotations


class TestConstants:
    def test_subtitle_band_height(self):
        from core.visuals import SUBTITLE_BAND_HEIGHT
        assert SUBTITLE_BAND_HEIGHT == 180

    def test_content_bottom_derived_from_video_height(self):
        from core.config import VIDEO_HEIGHT
        from core.visuals import CONTENT_BOTTOM, SUBTITLE_BAND_HEIGHT
        assert CONTENT_BOTTOM == VIDEO_HEIGHT - SUBTITLE_BAND_HEIGHT
        assert CONTENT_BOTTOM == 900  # 鎖死當前 1920×1080 layout

    def test_subtitle_strip_color_is_black(self):
        from core.visuals import SUBTITLE_STRIP_COLOR
        assert SUBTITLE_STRIP_COLOR == (0, 0, 0)


class TestCrossModuleConsistency:
    """改 visuals.py 常數值前, 所有 renderer 應該都拉同一個。"""

    def test_pipeline_uses_central_constants(self):
        """pipeline.py 不該再有自己 SUBTITLE_BAND=180 區域變數版本。"""
        import pipeline
        from core.visuals import CONTENT_BOTTOM, SUBTITLE_STRIP_COLOR
        # 兩條常數實際被引用 (import 沒被刪除)
        assert pipeline.CONTENT_BOTTOM == CONTENT_BOTTOM
        assert pipeline.SUBTITLE_STRIP_COLOR == SUBTITLE_STRIP_COLOR

    def test_pptx_style_height_alias_matches(self):
        """pptx_style.SUBTITLE_STRIP_HEIGHT 是 core.visuals 的別名 (向後相容)。"""
        from core.render import pptx_style
        from core.visuals import SUBTITLE_BAND_HEIGHT
        assert pptx_style.SUBTITLE_STRIP_HEIGHT == SUBTITLE_BAND_HEIGHT

    def test_pptx_style_content_bottom_matches(self):
        from core.render import pptx_style
        from core.visuals import CONTENT_BOTTOM
        assert pptx_style.CONTENT_BOTTOM == CONTENT_BOTTOM

    def test_pptx_style_strip_color_matches(self):
        from core.render import pptx_style
        from core.visuals import SUBTITLE_STRIP_COLOR
        assert pptx_style.SUBTITLE_STRIP == SUBTITLE_STRIP_COLOR
