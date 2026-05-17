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


class TestBuildClipDynamicAvatar:
    """iter 94: dynamic_avatar 走 build_clip / ffmpeg overlay 不經
    overlay_teacher_photo. override 也要擋這條路徑."""

    def test_build_clip_skips_dynamic_avatar_when_off(self, monkeypatch, tmp_path):
        """talking_head=off 時, ffmpeg 命令不該有 avatar concat input."""
        from pathlib import Path
        import pipeline as pl

        # mock pipeline_config 把 dynamic_avatar 開到 enabled=True
        monkeypatch.setattr(
            pl, "_get_pipeline_config",
            lambda: {
                "dynamic_avatar": {"enabled": True, "size": 220, "margin": 40, "border_width": 3},
                "chalk_sfx": {"enabled": False},
            },
        )
        # 假裝 avatar_closed.png 已存在 (走 dynamic 路徑的必要條件)
        avatar_png = pl.WORK_DIR / "avatar_closed.png"
        pl.WORK_DIR.mkdir(parents=True, exist_ok=True)
        avatar_png.write_bytes(b"fake_png_for_test")

        # 攔截 ffmpeg subprocess + _build_avatar_concat (不真跑)
        captured_cmd = []
        monkeypatch.setattr(pl.subprocess, "run", lambda cmd, **kw: captured_cmd.append(cmd))
        monkeypatch.setattr(pl, "_build_avatar_concat", lambda *a, **kw: None)

        f_p = tmp_path / "frame.png"
        f_p.write_bytes(b"x")
        a_p = tmp_path / "audio.mp3"
        a_p.write_bytes(b"x")
        out_p = tmp_path / "clip.mp4"

        try:
            # 1. 不開 override → 應該有 avatar concat input
            captured_cmd.clear()
            pl.build_clip(f_p, a_p, 5.0, out_p, tmp_path)
            cmd1 = captured_cmd[0]
            assert "concat" in cmd1, "預設應該接 dynamic avatar concat"

            # 2. override=off → ffmpeg 命令不該再有 avatar concat
            captured_cmd.clear()
            with talking_head_override("off"):
                pl.build_clip(f_p, a_p, 5.0, out_p, tmp_path)
            cmd2 = captured_cmd[0]
            assert "concat" not in cmd2, (
                f"override=off 該 skip dynamic avatar, 但 cmd 仍含 concat: {cmd2}"
            )

            # 3. override=long_form_only + 短片 → 也該 skip
            captured_cmd.clear()
            with talking_head_override("long_form_only", is_short_form=True):
                pl.build_clip(f_p, a_p, 5.0, out_p, tmp_path)
            cmd3 = captured_cmd[0]
            assert "concat" not in cmd3, (
                "short_form + long_form_only 該 skip dynamic avatar"
            )
        finally:
            avatar_png.unlink(missing_ok=True)
