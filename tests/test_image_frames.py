"""core.image_frames — E1-2 frame resolver 單元測試.

對應 docs/dynamic-visual-assets-design.md E1 候選 A.
schema E1-1 已落地 (slide.image_frames list[dict] | None), 此處驗純函式
過濾 / 排序 / 進度對應, 不動 PIL / ffmpeg.
"""
from __future__ import annotations

import pytest

from core.image_frames import (
    frame_count,
    select_frame,
    terminal_frame,
    valid_frames,
)


@pytest.fixture
def existing_pngs(tmp_path):
    """產三個假 PNG 檔案路徑, 給 require_file_exists=True 路徑驗證用."""
    f1 = tmp_path / "f1.png"
    f2 = tmp_path / "f2.png"
    f3 = tmp_path / "f3.png"
    for f in (f1, f2, f3):
        f.write_bytes(b"")  # 內容不重要, 只要 .exists() True
    return [str(f1), str(f2), str(f3)]


class TestValidFrames:
    def test_none_returns_empty(self):
        assert valid_frames(None) == []

    def test_empty_list_returns_empty(self):
        assert valid_frames([]) == []

    def test_non_list_input_returns_empty(self):
        # 防呆: dict / str / int 都當 noop
        assert valid_frames({"path": "x.png", "display_ratio": 0.5}) == []
        assert valid_frames("x.png") == []
        assert valid_frames(42) == []

    def test_basic_pass_through(self, existing_pngs):
        frames = [
            {"path": existing_pngs[0], "display_ratio": 0.33},
            {"path": existing_pngs[1], "display_ratio": 0.66},
            {"path": existing_pngs[2], "display_ratio": 1.0},
        ]
        result = valid_frames(frames)
        assert len(result) == 3
        assert [f["display_ratio"] for f in result] == [0.33, 0.66, 1.0]

    def test_sorted_by_display_ratio_ascending(self, existing_pngs):
        # caller 給亂序也該 sort
        frames = [
            {"path": existing_pngs[2], "display_ratio": 1.0},
            {"path": existing_pngs[0], "display_ratio": 0.33},
            {"path": existing_pngs[1], "display_ratio": 0.66},
        ]
        result = valid_frames(frames)
        assert [f["display_ratio"] for f in result] == [0.33, 0.66, 1.0]

    def test_invalid_ratio_out_of_range_dropped(self, existing_pngs):
        # 0.0 (含) 跟 >1.0 都該 drop, 因為 display_ratio 是「累進佔比上限」
        frames = [
            {"path": existing_pngs[0], "display_ratio": 0.0},
            {"path": existing_pngs[1], "display_ratio": 0.5},
            {"path": existing_pngs[2], "display_ratio": 1.5},
        ]
        result = valid_frames(frames)
        assert len(result) == 1
        assert result[0]["display_ratio"] == 0.5

    def test_missing_path_dropped(self, existing_pngs):
        frames = [
            {"display_ratio": 0.5},  # 缺 path
            {"path": existing_pngs[0], "display_ratio": 1.0},
        ]
        result = valid_frames(frames)
        assert len(result) == 1

    def test_non_dict_entry_dropped(self, existing_pngs):
        frames = [
            "not a dict",
            {"path": existing_pngs[0], "display_ratio": 1.0},
        ]
        result = valid_frames(frames)
        assert len(result) == 1

    def test_non_numeric_ratio_dropped(self, existing_pngs):
        frames = [
            {"path": existing_pngs[0], "display_ratio": "half"},
            {"path": existing_pngs[1], "display_ratio": 1.0},
        ]
        result = valid_frames(frames)
        assert len(result) == 1
        assert result[0]["display_ratio"] == 1.0

    def test_duplicate_ratio_keeps_later_entry(self, existing_pngs):
        # 同 ratio 重複: 保留 caller 後送進來那筆 (newer overrides older)
        frames = [
            {"path": existing_pngs[0], "display_ratio": 0.5},
            {"path": existing_pngs[1], "display_ratio": 0.5},
        ]
        result = valid_frames(frames)
        assert len(result) == 1
        assert result[0]["path"] == existing_pngs[1]

    def test_missing_file_dropped_when_required(self, tmp_path):
        # require_file_exists=True 預設 — 檔案不存在的條目該過濾掉
        missing = str(tmp_path / "nope.png")
        frames = [{"path": missing, "display_ratio": 1.0}]
        assert valid_frames(frames) == []

    def test_missing_file_kept_when_not_required(self, tmp_path):
        # require_file_exists=False — 給 review UI 提案階段預覽用,
        # frame 還沒產出來也要顯示列表
        missing = str(tmp_path / "nope.png")
        frames = [{"path": missing, "display_ratio": 1.0}]
        result = valid_frames(frames, require_file_exists=False)
        assert len(result) == 1
        assert result[0]["path"] == missing


class TestSelectFrame:
    def test_none_input_returns_none(self):
        assert select_frame(None, 0.5) is None

    def test_empty_list_returns_none(self):
        assert select_frame([], 0.5) is None

    def test_first_frame_for_progress_below_first_ratio(self, existing_pngs):
        frames = [
            {"path": existing_pngs[0], "display_ratio": 0.33},
            {"path": existing_pngs[1], "display_ratio": 0.66},
            {"path": existing_pngs[2], "display_ratio": 1.0},
        ]
        # progress 0.1 落在 (0, 0.33] 區段 → frame 1
        result = select_frame(frames, 0.1)
        assert result["path"] == existing_pngs[0]

    def test_middle_frame_for_progress_in_middle_bucket(self, existing_pngs):
        frames = [
            {"path": existing_pngs[0], "display_ratio": 0.33},
            {"path": existing_pngs[1], "display_ratio": 0.66},
            {"path": existing_pngs[2], "display_ratio": 1.0},
        ]
        # progress 0.5 落在 (0.33, 0.66] 區段 → frame 2
        result = select_frame(frames, 0.5)
        assert result["path"] == existing_pngs[1]

    def test_last_frame_for_progress_one(self, existing_pngs):
        frames = [
            {"path": existing_pngs[0], "display_ratio": 0.33},
            {"path": existing_pngs[1], "display_ratio": 0.66},
            {"path": existing_pngs[2], "display_ratio": 1.0},
        ]
        result = select_frame(frames, 1.0)
        assert result["path"] == existing_pngs[2]

    def test_progress_clamped_above_one(self, existing_pngs):
        # caller 傳 1.5 (異常) → 視為 1.0, 仍回最後 frame
        frames = [
            {"path": existing_pngs[0], "display_ratio": 1.0},
        ]
        result = select_frame(frames, 1.5)
        assert result["path"] == existing_pngs[0]

    def test_progress_clamped_below_zero(self, existing_pngs):
        # caller 傳 -0.2 (異常) → 視為 0, 回第一 frame
        frames = [
            {"path": existing_pngs[0], "display_ratio": 0.5},
            {"path": existing_pngs[1], "display_ratio": 1.0},
        ]
        result = select_frame(frames, -0.2)
        assert result["path"] == existing_pngs[0]

    def test_progress_at_ratio_boundary_inclusive(self, existing_pngs):
        # progress 剛好等於某 frame 的 display_ratio → 該 frame
        # (區段是 (prev, current] 半開, current 屬於 current frame)
        frames = [
            {"path": existing_pngs[0], "display_ratio": 0.5},
            {"path": existing_pngs[1], "display_ratio": 1.0},
        ]
        result = select_frame(frames, 0.5)
        assert result["path"] == existing_pngs[0]


class TestTerminalFrame:
    def test_none_returns_none(self):
        assert terminal_frame(None) is None

    def test_picks_highest_ratio(self, existing_pngs):
        frames = [
            {"path": existing_pngs[0], "display_ratio": 0.33},
            {"path": existing_pngs[1], "display_ratio": 1.0},
            {"path": existing_pngs[2], "display_ratio": 0.66},
        ]
        result = terminal_frame(frames)
        assert result["path"] == existing_pngs[1]
        assert result["display_ratio"] == 1.0

    def test_single_frame(self, existing_pngs):
        frames = [{"path": existing_pngs[0], "display_ratio": 0.5}]
        result = terminal_frame(frames)
        assert result["path"] == existing_pngs[0]

    def test_all_invalid_returns_none(self, tmp_path):
        # 全部 frames 檔案不存在 → terminal 也回 None (graceful)
        missing = str(tmp_path / "nope.png")
        frames = [{"path": missing, "display_ratio": 1.0}]
        assert terminal_frame(frames) is None


class TestFrameCount:
    def test_none_zero(self):
        assert frame_count(None) == 0

    def test_counts_valid_only(self, existing_pngs, tmp_path):
        # 一個有效 + 一個檔案不在 + 一個 ratio 越界 → count=1
        missing = str(tmp_path / "nope.png")
        frames = [
            {"path": existing_pngs[0], "display_ratio": 0.5},
            {"path": missing, "display_ratio": 0.8},
            {"path": existing_pngs[1], "display_ratio": 1.5},
        ]
        assert frame_count(frames) == 1

    def test_count_review_mode_includes_missing(self, tmp_path):
        # require_file_exists=False (review UI 模式) → 檔案不存在也算
        missing = str(tmp_path / "nope.png")
        frames = [{"path": missing, "display_ratio": 1.0}]
        assert frame_count(frames, require_file_exists=False) == 1
