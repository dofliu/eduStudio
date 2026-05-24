"""server.runner._apply_intro_postprocess — iter 41 IO wrapper 安全鎖.

iter 41 上線後沒對應直接測試: 核心 `video_concat.concat_videos` /
`video_concat.offset_srt` 純函式都有自己的 module test (test_video_concat.py),
但 runner 內這層 IO wrapper (主影片不存在防呆 / merged.replace(main) /
SRT exists + duration > 0 雙閘 / concat 失敗吞例外 / SRT 失敗吞例外)
從沒打 — 任何 refactor 不小心動防呆順序 / SRT 雙閘條件 / 例外傳播
就直接上線, 跟 iter 111-125 同思路 (route / helper safety lock).

例外吞掉是 design intent (intro 串接是 nice-to-have, 主影片成品已存在
不該因為這個整 job 死), 該被測試鎖住, 避免未來 refactor 誤改成 raise.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from server.runner import _apply_intro_postprocess


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    """把 core.config.OUTPUT_DIR 指到 tmp_path.

    runner._apply_intro_postprocess 內 `from core.config import OUTPUT_DIR`,
    每次 call 都重新 import — patch core.config.OUTPUT_DIR 就行 (function-
    local import 不會被 module-level capture 鎖住).
    """
    import core.config
    monkeypatch.setattr(core.config, "OUTPUT_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def stub_video_concat(monkeypatch):
    """monkeypatch core.video_concat 的 concat_videos / offset_srt.

    回傳一個 counters dict 給 test 驗呼叫次數 + 引數. 預設行為:
    - concat_videos: 寫 sentinel bytes 到 output, 模擬真合成成功
    - offset_srt: 把字串前面加 "[+N]" 標記, 模擬 offset 邏輯被觸發
    """
    import core.video_concat

    counters = {
        "concat_calls": [],   # list of (parts_list, output)
        "offset_calls": [],   # list of (text, seconds)
    }

    def fake_concat(parts, output):
        counters["concat_calls"].append((list(parts), Path(output)))
        Path(output).write_bytes(b"MERGED_SENTINEL")

    def fake_offset(text, seconds):
        counters["offset_calls"].append((text, seconds))
        return f"[+{seconds}]\n{text}"

    monkeypatch.setattr(core.video_concat, "concat_videos", fake_concat)
    monkeypatch.setattr(core.video_concat, "offset_srt", fake_offset)
    return counters


def _write_main_files(output_dir: Path, unique_name: str,
                      with_srt: bool = True) -> tuple[Path, Path]:
    """預建主 mp4 (+ optional SRT)."""
    main_mp4 = output_dir / f"{unique_name}.mp4"
    main_mp4.write_bytes(b"ORIGINAL_MAIN_MP4")
    main_srt = output_dir / f"{unique_name}.srt"
    if with_srt:
        main_srt.write_text(
            "1\n00:00:01,000 --> 00:00:02,000\n字幕一\n",
            encoding="utf-8",
        )
    return main_mp4, main_srt


# ---------------------------------------------------------------- TestNoOpPath

class TestNoOpPath:
    """主影片不在 — 不該炸, 不該 call concat, 該 log warning."""

    def test_missing_main_mp4_skips_silently(
        self, output_dir, stub_video_concat, caplog,
    ):
        # 沒寫 main_mp4
        intro = output_dir / "intro_normalized.mp4"
        intro.write_bytes(b"INTRO")

        with caplog.at_level(logging.WARNING, logger="server.runner"):
            _apply_intro_postprocess("nothing", intro, 3.5)

        # concat / offset 都不該被叫
        assert stub_video_concat["concat_calls"] == []
        assert stub_video_concat["offset_calls"] == []
        # warning 該含「主影片不存在」字串 (鎖訊息格式不被偷改)
        assert any(
            "主影片不存在" in rec.message and "nothing.mp4" in rec.message
            for rec in caplog.records
        )


# ---------------------------------------------------------------- TestHappyPath

class TestHappyPath:
    """主 mp4 + SRT 都在 → concat + replace + SRT shift 全跑."""

    def test_concat_called_with_intro_then_main_in_order(
        self, output_dir, stub_video_concat,
    ):
        """parts 順序鎖: intro 在前, main 在後 (不可顛倒, 否則 intro 變結尾)."""
        intro = output_dir / "intro_normalized.mp4"
        intro.write_bytes(b"INTRO")
        main_mp4, _ = _write_main_files(output_dir, "q1")

        _apply_intro_postprocess("q1", intro, 3.5)

        assert len(stub_video_concat["concat_calls"]) == 1
        parts, _output = stub_video_concat["concat_calls"][0]
        assert parts == [intro, main_mp4]

    def test_merged_replaces_main_mp4(
        self, output_dir, stub_video_concat,
    ):
        """merged.replace(main_mp4) 該真把假 merged 內容覆蓋進主檔.

        驗 OUTPUT_DIR/q1.mp4 內容 = MERGED_SENTINEL (fake_concat 寫的),
        而不是原本的 ORIGINAL_MAIN_MP4. with_intro.mp4 過渡檔該被 rename 掉.
        """
        intro = output_dir / "intro_normalized.mp4"
        intro.write_bytes(b"INTRO")
        main_mp4, _ = _write_main_files(output_dir, "q1")

        _apply_intro_postprocess("q1", intro, 3.5)

        assert main_mp4.read_bytes() == b"MERGED_SENTINEL"
        # 過渡檔該被 .replace() 搬掉, 不留在 OUTPUT_DIR
        assert not (output_dir / "q1.with_intro.mp4").exists()

    def test_srt_shifted_when_intro_duration_positive(
        self, output_dir, stub_video_concat,
    ):
        """SRT 該被 offset_srt 處理 + 寫回原檔."""
        intro = output_dir / "intro_normalized.mp4"
        intro.write_bytes(b"INTRO")
        _, main_srt = _write_main_files(output_dir, "q1")
        original_srt = main_srt.read_text(encoding="utf-8")

        _apply_intro_postprocess("q1", intro, 3.5)

        # offset_srt 該被叫一次, 引數透傳
        assert len(stub_video_concat["offset_calls"]) == 1
        text, seconds = stub_video_concat["offset_calls"][0]
        assert text == original_srt
        assert seconds == 3.5
        # 寫回的內容 = fake_offset 加 prefix 後的結果
        assert main_srt.read_text(encoding="utf-8").startswith("[+3.5]")


# ----------------------------------------------------------- TestSrtSkipBranches

class TestSrtSkipBranches:
    """SRT exists + intro_duration > 0 雙閘 — 任一不滿足都該 skip."""

    def test_no_srt_file_does_not_call_offset(
        self, output_dir, stub_video_concat,
    ):
        """SRT 不存在 → concat OK, offset_srt 不該被叫, 不該炸."""
        intro = output_dir / "intro_normalized.mp4"
        intro.write_bytes(b"INTRO")
        _write_main_files(output_dir, "q1", with_srt=False)

        _apply_intro_postprocess("q1", intro, 3.5)

        assert len(stub_video_concat["concat_calls"]) == 1
        assert stub_video_concat["offset_calls"] == []

    def test_intro_duration_zero_skips_srt_shift(
        self, output_dir, stub_video_concat,
    ):
        """intro_duration=0.0 → SRT 存在仍該 skip (避免 noop offset 還寫一次盤)."""
        intro = output_dir / "intro_normalized.mp4"
        intro.write_bytes(b"INTRO")
        _, main_srt = _write_main_files(output_dir, "q1")
        original_srt = main_srt.read_text(encoding="utf-8")

        _apply_intro_postprocess("q1", intro, 0.0)

        assert stub_video_concat["offset_calls"] == []
        # SRT 該保留原樣 — 沒被寫回
        assert main_srt.read_text(encoding="utf-8") == original_srt

    def test_intro_duration_negative_skips_srt_shift(
        self, output_dir, stub_video_concat,
    ):
        """defensive: negative duration → skip (條件是 > 0 不是 != 0)."""
        intro = output_dir / "intro_normalized.mp4"
        intro.write_bytes(b"INTRO")
        _write_main_files(output_dir, "q1")

        _apply_intro_postprocess("q1", intro, -1.0)

        assert stub_video_concat["offset_calls"] == []


# ---------------------------------------------------------- TestFailureSwallowed

class TestFailureSwallowed:
    """例外吞掉是 design intent (intro 是 nice-to-have, 不擋主影片成品)."""

    def test_concat_raise_does_not_propagate(
        self, output_dir, monkeypatch, caplog,
    ):
        """concat raise → 函式正常 return, logger.exception 留紀錄.

        鎖: 主影片成品已存在不該炸整 job, except Exception 不可被 refactor
        改成 raise.
        """
        import core.video_concat

        def boom_concat(parts, output):
            raise RuntimeError("ffmpeg returned non-zero")

        monkeypatch.setattr(core.video_concat, "concat_videos", boom_concat)

        intro = output_dir / "intro_normalized.mp4"
        intro.write_bytes(b"INTRO")
        main_mp4, _ = _write_main_files(output_dir, "q1")

        with caplog.at_level(logging.ERROR, logger="server.runner"):
            _apply_intro_postprocess("q1", intro, 3.5)   # 不該 raise

        # logger.exception 該留紀錄
        assert any(
            "intro 串接失敗" in rec.message and "保留無 intro 版本" in rec.message
            for rec in caplog.records
        )
        # 主影片該保留原樣 (沒被 replace 掉)
        assert main_mp4.read_bytes() == b"ORIGINAL_MAIN_MP4"

    def test_concat_failure_does_not_touch_srt(
        self, output_dir, monkeypatch, stub_video_concat,
    ):
        """concat 失敗 → 早 return, SRT 不該被 offset / 不該被寫回."""
        import core.video_concat

        def boom_concat(parts, output):
            raise RuntimeError("ffmpeg fail")

        monkeypatch.setattr(core.video_concat, "concat_videos", boom_concat)

        intro = output_dir / "intro_normalized.mp4"
        intro.write_bytes(b"INTRO")
        _, main_srt = _write_main_files(output_dir, "q1")
        original_srt = main_srt.read_text(encoding="utf-8")

        _apply_intro_postprocess("q1", intro, 3.5)

        # offset_srt 該完全沒被叫 (fixture 的 stub 仍 active 對 offset 計數)
        assert stub_video_concat["offset_calls"] == []
        assert main_srt.read_text(encoding="utf-8") == original_srt

    def test_offset_srt_raise_does_not_propagate(
        self, output_dir, stub_video_concat, monkeypatch, caplog,
    ):
        """offset_srt raise → 不 propagate, 主 mp4 仍為 concat 後的 sentinel.

        鎖: SRT 偏移失敗只該記 log, 不該擋住已完成的 intro 串接成品.
        """
        import core.video_concat

        def boom_offset(text, seconds):
            raise ValueError("malformed srt timestamp")

        monkeypatch.setattr(core.video_concat, "offset_srt", boom_offset)

        intro = output_dir / "intro_normalized.mp4"
        intro.write_bytes(b"INTRO")
        main_mp4, _ = _write_main_files(output_dir, "q1")

        with caplog.at_level(logging.ERROR, logger="server.runner"):
            _apply_intro_postprocess("q1", intro, 3.5)   # 不該 raise

        assert any(
            "SRT 偏移失敗" in rec.message and "主影片已串好 intro" in rec.message
            for rec in caplog.records
        )
        # concat 那段已成功 — 主 mp4 已被 merged 蓋掉
        assert main_mp4.read_bytes() == b"MERGED_SENTINEL"
