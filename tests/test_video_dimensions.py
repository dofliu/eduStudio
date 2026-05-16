"""iter 83 (B1+B2 Option B): 影片尺寸 runtime 切換."""
from __future__ import annotations

import pytest

from core import config
from core.config import (
    VIDEO_DIMENSIONS,
    resolve_video_dimensions,
    video_dimensions_override,
)


class TestResolveVideoDimensions:
    def test_default_landscape_1080p(self):
        assert resolve_video_dimensions() == (1920, 1080)

    def test_portrait_1080p(self):
        assert resolve_video_dimensions("9:16", "1080p") == (1080, 1920)

    def test_landscape_4k(self):
        assert resolve_video_dimensions("16:9", "4K") == (3840, 2160)

    def test_portrait_4k(self):
        assert resolve_video_dimensions("9:16", "4K") == (2160, 3840)

    def test_landscape_1440p(self):
        assert resolve_video_dimensions("16:9", "1440p") == (2560, 1440)

    def test_invalid_combo_falls_back_to_1080p_landscape(self):
        assert resolve_video_dimensions("nope", "garbage") == (1920, 1080)
        assert resolve_video_dimensions("16:9", "8K") == (1920, 1080)


class TestVideoDimensionsOverride:
    """context manager 該 patch module attrs + restore."""

    def test_default_state(self):
        # 預設 16:9 1080p
        assert config.VIDEO_WIDTH == 1920
        assert config.VIDEO_HEIGHT == 1080

    def test_portrait_patches_dimensions(self):
        with video_dimensions_override("9:16", "1080p"):
            assert config.VIDEO_WIDTH == 1080
            assert config.VIDEO_HEIGHT == 1920
        # 出 with 後 restore
        assert config.VIDEO_WIDTH == 1920
        assert config.VIDEO_HEIGHT == 1080

    def test_4k_landscape_patches(self):
        with video_dimensions_override("16:9", "4K"):
            assert config.VIDEO_WIDTH == 3840
            assert config.VIDEO_HEIGHT == 2160
        assert config.VIDEO_WIDTH == 1920

    def test_visuals_module_also_patched(self):
        from core import visuals
        with video_dimensions_override("9:16", "1080p"):
            assert visuals.VIDEO_WIDTH == 1080
            assert visuals.VIDEO_HEIGHT == 1920
            # CONTENT_BOTTOM 也該重算 (1920 - 180 字幕帶)
            assert visuals.CONTENT_BOTTOM == 1920 - visuals.SUBTITLE_BAND_HEIGHT
        # restore
        assert visuals.VIDEO_WIDTH == 1920

    def test_pipeline_module_also_patched(self):
        import pipeline
        with video_dimensions_override("9:16", "1080p"):
            assert pipeline.WIDTH == 1080
            assert pipeline.HEIGHT == 1920
        assert pipeline.WIDTH == 1920

    def test_restore_on_exception(self):
        """exception 也該 restore."""
        try:
            with video_dimensions_override("9:16", "1080p"):
                assert config.VIDEO_WIDTH == 1080
                raise RuntimeError("test")
        except RuntimeError:
            pass
        assert config.VIDEO_WIDTH == 1920
        assert config.VIDEO_HEIGHT == 1080

    def test_returns_dimensions_from_enter(self):
        with video_dimensions_override("9:16", "1440p") as (w, h):
            assert w == 1440
            assert h == 2560

    def test_nested_override_outer_restored(self):
        """先 patch portrait, 內層 patch 4K landscape, 結束內層 restore portrait,
        結束外層 restore 預設."""
        with video_dimensions_override("9:16", "1080p"):
            assert config.VIDEO_WIDTH == 1080
            with video_dimensions_override("16:9", "4K"):
                assert config.VIDEO_WIDTH == 3840
            assert config.VIDEO_WIDTH == 1080
        assert config.VIDEO_WIDTH == 1920


class TestJobOptionsAspectResolution:
    """JobOptions 接受新欄位."""

    def test_default_none(self):
        from server.schemas import JobOptions
        opts = JobOptions()
        assert opts.aspect_ratio is None
        assert opts.resolution is None

    def test_portrait_4k(self):
        from server.schemas import JobOptions
        opts = JobOptions(aspect_ratio="9:16", resolution="4K")
        assert opts.aspect_ratio == "9:16"
        assert opts.resolution == "4K"


class TestVideoDimensionsTable:
    """確認 6 個組合都有 mapping."""

    def test_all_combos_present(self):
        expected_keys = {
            ("16:9", "1080p"), ("16:9", "1440p"), ("16:9", "4K"),
            ("9:16", "1080p"), ("9:16", "1440p"), ("9:16", "4K"),
        }
        assert set(VIDEO_DIMENSIONS.keys()) == expected_keys

    def test_portrait_swaps_landscape(self):
        """9:16 should = 16:9 swapped (w/h reversed)."""
        for resolution in ("1080p", "1440p", "4K"):
            landscape = VIDEO_DIMENSIONS[("16:9", resolution)]
            portrait = VIDEO_DIMENSIONS[("9:16", resolution)]
            assert portrait == (landscape[1], landscape[0]), (
                f"{resolution}: portrait {portrait} != landscape swapped {landscape}"
            )
