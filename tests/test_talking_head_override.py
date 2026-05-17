"""iter 92: talking_head_override context manager + 三段策略邏輯測試.

不實際畫頭像 (需 PIL + 圖檔), 只測 _should_skip_by_runtime_override 決策
跟 context manager 進出 restore 行為.
"""
from __future__ import annotations

import pytest

from core import photo_overlay
from core.photo_overlay import (
    _should_skip_by_runtime_override,
    talking_head_override,
)


class TestRuntimeOverrideDecision:
    def test_no_override_returns_false(self):
        """mode=None → 不覆寫, caller 走 pipeline_config 行為."""
        assert _should_skip_by_runtime_override() is False

    def test_off_always_skips(self):
        with talking_head_override("off"):
            assert _should_skip_by_runtime_override() is True

    def test_off_skips_even_for_long_form(self):
        with talking_head_override("off", is_short_form=False):
            assert _should_skip_by_runtime_override() is True

    def test_always_never_skips(self):
        with talking_head_override("always"):
            assert _should_skip_by_runtime_override() is False

    def test_always_does_not_skip_for_short(self):
        """用戶選 always 即使短影片也要畫."""
        with talking_head_override("always", is_short_form=True):
            assert _should_skip_by_runtime_override() is False

    def test_long_form_only_skips_short(self):
        with talking_head_override("long_form_only", is_short_form=True):
            assert _should_skip_by_runtime_override() is True

    def test_long_form_only_shows_for_long(self):
        with talking_head_override("long_form_only", is_short_form=False):
            assert _should_skip_by_runtime_override() is False


class TestContextManagerRestore:
    def test_exits_restore_state(self):
        """context manager 離開應 restore 到 None 預設."""
        assert photo_overlay._RUNTIME_TALKING_HEAD_MODE is None
        with talking_head_override("off"):
            assert photo_overlay._RUNTIME_TALKING_HEAD_MODE == "off"
        assert photo_overlay._RUNTIME_TALKING_HEAD_MODE is None

    def test_exits_restore_short_form_flag(self):
        assert photo_overlay._RUNTIME_IS_SHORT_FORM is False
        with talking_head_override("long_form_only", is_short_form=True):
            assert photo_overlay._RUNTIME_IS_SHORT_FORM is True
        assert photo_overlay._RUNTIME_IS_SHORT_FORM is False

    def test_nested_overrides_restore_outer(self):
        """巢狀 context, 內層出去該還原到外層 state."""
        with talking_head_override("always"):
            assert photo_overlay._RUNTIME_TALKING_HEAD_MODE == "always"
            with talking_head_override("off"):
                assert photo_overlay._RUNTIME_TALKING_HEAD_MODE == "off"
            # 內層出去, 還原外層
            assert photo_overlay._RUNTIME_TALKING_HEAD_MODE == "always"
        # 全部出去, 還原 None
        assert photo_overlay._RUNTIME_TALKING_HEAD_MODE is None

    def test_exception_in_block_still_restores(self):
        """block 內 exception 也要 restore (finally 行為驗證)."""
        with pytest.raises(ValueError):
            with talking_head_override("off"):
                raise ValueError("test")
        assert photo_overlay._RUNTIME_TALKING_HEAD_MODE is None


class TestOverlayShortCircuit:
    """直接驗 overlay_teacher_photo 被 override skip 不執行 PIL 操作."""

    def test_overlay_skipped_when_off(self, monkeypatch):
        """mode=off → load_pipeline_config 不被呼叫 (early return)."""
        from core.photo_overlay import overlay_teacher_photo

        called = []
        monkeypatch.setattr(
            "core.photo_overlay.load_pipeline_config",
            lambda: called.append(1) or {},
        )
        # 用 None 當 img, 因為該 early return 不會碰 img
        with talking_head_override("off"):
            overlay_teacher_photo(None)  # type: ignore[arg-type]
        assert called == [], "off 模式應該 early return, 不該讀 config"

    def test_overlay_skipped_for_short_with_long_form_only(self, monkeypatch):
        from core.photo_overlay import overlay_teacher_photo

        called = []
        monkeypatch.setattr(
            "core.photo_overlay.load_pipeline_config",
            lambda: called.append(1) or {},
        )
        with talking_head_override("long_form_only", is_short_form=True):
            overlay_teacher_photo(None)  # type: ignore[arg-type]
        assert called == [], "short_form + long_form_only 該 skip"
