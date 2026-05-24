"""server.runner._merge_sections_to_final — iter 45 IO wrapper 安全鎖.

iter 45 上線後沒對應直接測試: 核心 `video_concat.concat_videos` /
`video_concat.merge_srts` 純函式都有自己的 module test (test_video_concat.py),
但 runner 內這層合成 wrapper (intro/outro/sections parts 順序組裝 / SRT padding
條件 `> 0` 雙閘 / concat 失敗早 return / merge_srts 失敗吞例外) 從沒打 —
任何 refactor 不小心動 parts 順序 / padding 條件 / 例外傳播 (被改成 raise)
就直接上線, 跟 iter 111-126 同思路 (route / helper safety lock).

例外吞掉是 design intent (final.mp4 是 nice-to-have 統一交付, 各章 mp4
仍是有效成品, 合成失敗不該整 job 死), 該被測試鎖住.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from server.runner import _merge_sections_to_final


@pytest.fixture
def stub_video_concat(monkeypatch):
    """monkeypatch core.video_concat 的 concat_videos / merge_srts.

    回傳 counters dict 給 test 驗呼叫次數 + 引數. 預設行為:
    - concat_videos: 寫 sentinel bytes 到 output, 模擬真合成成功
    - merge_srts: 回固定 sentinel 字串, 模擬合併結果

    runner 用 `from core import video_concat` (function-local), 每次呼叫
    重新 lookup attribute, patch core.video_concat.X 直接生效.
    """
    import core.video_concat

    counters = {
        "concat_calls": [],     # list of (parts_list, output)
        "merge_calls": [],      # list of srt_parts_list
    }

    def fake_concat(parts, output):
        counters["concat_calls"].append((list(parts), Path(output)))
        Path(output).write_bytes(b"FINAL_MP4_SENTINEL")

    def fake_merge_srts(parts):
        counters["merge_calls"].append(list(parts))
        return "MERGED_SRT_SENTINEL"

    monkeypatch.setattr(core.video_concat, "concat_videos", fake_concat)
    monkeypatch.setattr(core.video_concat, "merge_srts", fake_merge_srts)
    return counters


def _make_section_files(tmp_path: Path, n: int) -> tuple[list[Path], list[tuple[str, float]]]:
    """造 n 個 fake section mp4 + section_srts tuple."""
    mp4s = []
    srts = []
    for i in range(1, n + 1):
        mp4 = tmp_path / f"ch{i}.mp4"
        mp4.write_bytes(f"CH{i}_MP4".encode())
        mp4s.append(mp4)
        srts.append((f"1\n00:00:0{i},000 --> 00:00:0{i+1},000\n字幕 ch{i}\n", float(i + 1)))
    return mp4s, srts


# ---------------------------------------------------------------- TestHappyPath

class TestHappyPath:
    """parts 順序 + final.mp4 / final.srt 落盤鎖."""

    def test_parts_order_intro_sections_outro(
        self, tmp_path, stub_video_concat,
    ):
        """parts 順序鎖: [intro, ch1, ch2, outro] — 顛倒 = intro 變結尾."""
        intro = tmp_path / "intro.mp4"
        intro.write_bytes(b"INTRO")
        outro = tmp_path / "outro.mp4"
        outro.write_bytes(b"OUTRO")
        section_mp4s, section_srts = _make_section_files(tmp_path, 2)

        _merge_sections_to_final(
            section_mp4s, section_srts, tmp_path,
            intro_path=intro, intro_duration=3.0,
            outro_path=outro, outro_duration=2.0,
        )

        assert len(stub_video_concat["concat_calls"]) == 1
        parts, output = stub_video_concat["concat_calls"][0]
        assert parts == [intro, section_mp4s[0], section_mp4s[1], outro]
        assert output == tmp_path / "final.mp4"
        # final.mp4 真被寫進 artifacts_dir
        assert (tmp_path / "final.mp4").read_bytes() == b"FINAL_MP4_SENTINEL"

    def test_no_intro_no_outro_only_sections(
        self, tmp_path, stub_video_concat,
    ):
        """intro=None outro=None → parts 只含 sections (不該硬塞 None)."""
        section_mp4s, section_srts = _make_section_files(tmp_path, 3)

        _merge_sections_to_final(
            section_mp4s, section_srts, tmp_path,
            intro_path=None, intro_duration=0.0,
        )

        parts, _ = stub_video_concat["concat_calls"][0]
        assert parts == section_mp4s
        # 默認 outro 也是 None, 不該出現在 parts
        assert None not in parts

    def test_intro_only_no_outro(
        self, tmp_path, stub_video_concat,
    ):
        """intro 在 outro 不在 → parts == [intro, ...sections]."""
        intro = tmp_path / "intro.mp4"
        intro.write_bytes(b"INTRO")
        section_mp4s, section_srts = _make_section_files(tmp_path, 2)

        _merge_sections_to_final(
            section_mp4s, section_srts, tmp_path,
            intro_path=intro, intro_duration=3.0,
        )

        parts, _ = stub_video_concat["concat_calls"][0]
        assert parts == [intro, *section_mp4s]

    def test_final_srt_written_with_merged_content(
        self, tmp_path, stub_video_concat,
    ):
        """merge_srts 回非空字串 → 寫進 final.srt (UTF-8 encoded)."""
        section_mp4s, section_srts = _make_section_files(tmp_path, 1)

        _merge_sections_to_final(
            section_mp4s, section_srts, tmp_path,
            intro_path=None, intro_duration=0.0,
        )

        final_srt = tmp_path / "final.srt"
        assert final_srt.exists()
        assert final_srt.read_text(encoding="utf-8") == "MERGED_SRT_SENTINEL"


# ---------------------------------------------------------- TestSrtPaddingGate

class TestSrtPaddingGate:
    """SRT 端的 padding 由 (path is not None) AND (duration > 0) 雙閘控制."""

    def test_srt_parts_include_intro_padding_when_duration_positive(
        self, tmp_path, stub_video_concat,
    ):
        """intro 存在 + duration > 0 → srt_parts 前面塞 ("", intro_duration)."""
        intro = tmp_path / "intro.mp4"
        intro.write_bytes(b"INTRO")
        section_mp4s, section_srts = _make_section_files(tmp_path, 1)

        _merge_sections_to_final(
            section_mp4s, section_srts, tmp_path,
            intro_path=intro, intro_duration=3.5,
        )

        srt_parts = stub_video_concat["merge_calls"][0]
        # 第一個 tuple 該是 intro padding
        assert srt_parts[0] == ("", 3.5)
        # 後面接 section_srts
        assert srt_parts[1:] == section_srts

    def test_intro_duration_zero_excluded_from_srt_parts(
        self, tmp_path, stub_video_concat,
    ):
        """intro_path 存在但 duration=0.0 → 不該塞 intro padding (避免 cue 對齊錯).

        鎖: 條件是 `intro_duration > 0`, 不是 `intro_path is not None` 單獨判斷.
        """
        intro = tmp_path / "intro.mp4"
        intro.write_bytes(b"INTRO")
        section_mp4s, section_srts = _make_section_files(tmp_path, 1)

        _merge_sections_to_final(
            section_mp4s, section_srts, tmp_path,
            intro_path=intro, intro_duration=0.0,
        )

        srt_parts = stub_video_concat["merge_calls"][0]
        # srt_parts 純 section_srts, 沒前綴 padding
        assert srt_parts == section_srts

    def test_outro_duration_zero_excluded_from_srt_parts(
        self, tmp_path, stub_video_concat,
    ):
        """outro_path 存在但 outro_duration=0.0 → 不該塞 outro padding."""
        outro = tmp_path / "outro.mp4"
        outro.write_bytes(b"OUTRO")
        section_mp4s, section_srts = _make_section_files(tmp_path, 1)

        _merge_sections_to_final(
            section_mp4s, section_srts, tmp_path,
            intro_path=None, intro_duration=0.0,
            outro_path=outro, outro_duration=0.0,
        )

        srt_parts = stub_video_concat["merge_calls"][0]
        # 末段不該有 outro padding
        assert srt_parts == section_srts


# ---------------------------------------------------------- TestEmptyMergedSrt

class TestEmptyMergedSrt:
    """merge_srts 回空字串 → 不該寫 final.srt (避免空檔誤導 UI 認為有字幕)."""

    def test_empty_merged_srt_skips_final_srt_write(
        self, tmp_path, monkeypatch,
    ):
        """merge_srts 回 "" → final.srt 不該被建立."""
        import core.video_concat

        def fake_concat(parts, output):
            Path(output).write_bytes(b"FINAL_MP4")

        def fake_empty_merge(parts):
            return ""

        monkeypatch.setattr(core.video_concat, "concat_videos", fake_concat)
        monkeypatch.setattr(core.video_concat, "merge_srts", fake_empty_merge)

        section_mp4s, section_srts = _make_section_files(tmp_path, 1)

        _merge_sections_to_final(
            section_mp4s, section_srts, tmp_path,
            intro_path=None, intro_duration=0.0,
        )

        # final.mp4 該存在 (concat 段成功), 但 final.srt 不該被寫
        assert (tmp_path / "final.mp4").exists()
        assert not (tmp_path / "final.srt").exists()


# ---------------------------------------------------------- TestFailureSwallowed

class TestFailureSwallowed:
    """例外吞掉是 design intent (final.mp4 失敗時各章仍可用, 不擋整 job)."""

    def test_concat_raise_does_not_propagate_and_skips_srt(
        self, tmp_path, monkeypatch, caplog,
    ):
        """concat raise → 函式 return, merge_srts 不該被叫, logger.exception 留紀錄.

        鎖兩件事: 不 raise (except 不可被 refactor 改成 raise) + concat 失敗早
        return (不可 fall-through 進 SRT 段, 否則對沒生成的 final.mp4 還繼續處理
        SRT 是浪費且誤導).
        """
        import core.video_concat

        merge_called = []

        def boom_concat(parts, output):
            raise RuntimeError("ffmpeg returned non-zero")

        def fake_merge(parts):
            merge_called.append(parts)
            return "SRT"

        monkeypatch.setattr(core.video_concat, "concat_videos", boom_concat)
        monkeypatch.setattr(core.video_concat, "merge_srts", fake_merge)

        section_mp4s, section_srts = _make_section_files(tmp_path, 1)

        with caplog.at_level(logging.ERROR, logger="server.runner"):
            _merge_sections_to_final(
                section_mp4s, section_srts, tmp_path,
                intro_path=None, intro_duration=0.0,
            )   # 不該 raise

        # logger.exception 該留紀錄含「final.mp4 合成失敗」+「各章 mp4 仍可用」
        assert any(
            "final.mp4 合成失敗" in rec.message and "各章 mp4 仍可用" in rec.message
            for rec in caplog.records
        )
        # merge_srts 完全沒被叫 (concat 失敗早 return)
        assert merge_called == []
        # final.mp4 / final.srt 都不該存在
        assert not (tmp_path / "final.mp4").exists()
        assert not (tmp_path / "final.srt").exists()

    def test_merge_srts_raise_does_not_propagate(
        self, tmp_path, monkeypatch, caplog,
    ):
        """merge_srts raise → 不 propagate, final.mp4 仍存在 (concat 段已成功).

        鎖: SRT 合併失敗只該記 log, 不該擋住已完成的 final.mp4 成品.
        """
        import core.video_concat

        def fake_concat(parts, output):
            Path(output).write_bytes(b"FINAL_MP4")

        def boom_merge(parts):
            raise ValueError("malformed srt block")

        monkeypatch.setattr(core.video_concat, "concat_videos", fake_concat)
        monkeypatch.setattr(core.video_concat, "merge_srts", boom_merge)

        section_mp4s, section_srts = _make_section_files(tmp_path, 1)

        with caplog.at_level(logging.ERROR, logger="server.runner"):
            _merge_sections_to_final(
                section_mp4s, section_srts, tmp_path,
                intro_path=None, intro_duration=0.0,
            )   # 不該 raise

        assert any(
            "final.srt 合併失敗" in rec.message and "final.mp4 已存在" in rec.message
            for rec in caplog.records
        )
        # final.mp4 仍存在 (concat 成功), final.srt 沒寫 (merge 段炸了)
        assert (tmp_path / "final.mp4").exists()
        assert not (tmp_path / "final.srt").exists()
