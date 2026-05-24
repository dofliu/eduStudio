"""server.runner._prepare_intro_for_problems / _prepare_outro_for_problems
— iter 41 + iter 66 helper 安全鎖.

iter 41 上線後沒對應直接測試: 核心 `video_concat.normalize_intro_audio` /
`video_concat.get_video_duration` 純函式在 test_video_concat.py 都有覆蓋,
但 runner 內這層 helper (檔不存在防呆 + AudioSpec(96000, 1, 'aac') 寫死 +
normalize_intro_audio 透傳 ASSETS_DIR + get_video_duration 接 normalize 後
路徑 + 例外吞掉) 從沒打 — 任何 refactor 不小心動 AudioSpec 參數 / 防呆早期
return / 例外傳播 (被改成 raise) 就直接上線, 跟 iter 111-127 同思路.

iter 66 _prepare_outro_for_problems 既有 1 個 test (test_outro_video_qr.py
TestPrepareOutroForProblems::test_returns_none_when_outro_file_missing)
只驗 outro 檔不存在的 None tuple, 沒鎖 AudioSpec / 訊息字串 / 例外吞掉.

例外吞掉是 design intent (intro/outro 串接是 nice-to-have, 主影片成品已存在,
不該因這個整 job 死), 該被測試鎖住, 避免未來 refactor 誤改成 raise.

intro vs outro 訊息該對比: intro 是「將串接到 N 支主影片前」, outro 是
「將串到 N 支主影片後」— 兩者方向不同, 鎖住兩段訊息防止被合併或被偷改.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from server.runner import (
    _prepare_intro_for_problems,
    _prepare_outro_for_problems,
)


@pytest.fixture
def stub_video_concat(monkeypatch):
    """monkeypatch core.video_concat.{normalize_intro_audio,get_video_duration}.

    回 counters dict 給 test 驗呼叫次數 + 引數. 預設行為:
    - normalize_intro_audio: 回 input_path.with_suffix('.normalized.mp4')
      模擬 normalize 成功 (寫個假檔到 tmp)
    - get_video_duration: 回 5.5 (預設) — test 可覆寫
    """
    import core.video_concat

    counters: dict = {
        "normalize_calls": [],   # list of (input_path, target_spec, assets_dir)
        "duration_calls": [],    # list of paths
        "duration_return": 5.5,
    }

    def fake_normalize(input_path, target_spec, assets_dir):
        counters["normalize_calls"].append(
            (Path(input_path), target_spec, Path(assets_dir)),
        )
        out = Path(input_path).with_suffix(".normalized.mp4")
        out.write_bytes(b"NORMALIZED_SENTINEL")
        return out

    def fake_duration(video_path):
        counters["duration_calls"].append(Path(video_path))
        return counters["duration_return"]

    monkeypatch.setattr(
        core.video_concat, "normalize_intro_audio", fake_normalize,
    )
    monkeypatch.setattr(
        core.video_concat, "get_video_duration", fake_duration,
    )
    return counters


@pytest.fixture
def intro_file(tmp_path, monkeypatch):
    """在 tmp_path 寫個假 intro 檔, monkeypatch get_intro_video_path 指過去."""
    intro = tmp_path / "intro.mp4"
    intro.write_bytes(b"FAKE_INTRO_MP4")
    import core.config
    monkeypatch.setattr(
        core.config, "get_intro_video_path", lambda: str(intro),
    )
    return intro


@pytest.fixture
def outro_file(tmp_path, monkeypatch):
    """在 tmp_path 寫個假 outro 檔, monkeypatch get_outro_video_path 指過去."""
    outro = tmp_path / "outro.mp4"
    outro.write_bytes(b"FAKE_OUTRO_MP4")
    import core.config
    monkeypatch.setattr(
        core.config, "get_outro_video_path", lambda: str(outro),
    )
    return outro


def _make_problems(n: int) -> list[dict]:
    """造 n 個假 problem dict, 只給長度 — helper 只用 len(problems) 寫進 log."""
    return [{"id": f"p{i}", "number": f"第 {i} 題"} for i in range(1, n + 1)]


# =========================================================================
#                     _prepare_intro_for_problems tests
# =========================================================================

class TestIntroNoOpPath:
    """intro 檔不存在 — 不該炸, 不該 call normalize, 該 log warning."""

    def test_missing_intro_file_skips_silently(
        self, tmp_path, stub_video_concat, monkeypatch, caplog,
    ):
        """get_intro_video_path 指向不存在的路徑 → (None, 0.0) +
        warning 含「intro 檔不存在」+「跳過 intro 串接」+ normalize /
        get_video_duration 都沒被叫 (鎖 early return 不被改成 fall-through).
        """
        import core.config
        nonexistent = tmp_path / "does_not_exist_intro.mp4"
        monkeypatch.setattr(
            core.config, "get_intro_video_path", lambda: str(nonexistent),
        )

        with caplog.at_level(logging.WARNING, logger="server.runner"):
            result = _prepare_intro_for_problems(_make_problems(3), tmp_path)

        assert result == (None, 0.0)
        # normalize / get_video_duration 都不該被叫 (鎖防呆早期 return)
        assert stub_video_concat["normalize_calls"] == []
        assert stub_video_concat["duration_calls"] == []
        # warning 該含關鍵字串 — 鎖訊息格式不被偷改
        assert any(
            "intro 檔不存在" in rec.message and "跳過 intro 串接" in rec.message
            for rec in caplog.records
        )


class TestIntroHappyPath:
    """intro 檔在 → normalize + get_video_duration 都跑, 回 (path, duration)."""

    def test_returns_normalized_path_and_duration(
        self, tmp_path, intro_file, stub_video_concat,
    ):
        """正常路徑: 回 (normalized_path, duration) + normalize 收到正確
        AudioSpec(96000, 1, 'aac') + 第三 arg 是 ASSETS_DIR (鎖 spec 不被偷改).
        """
        stub_video_concat["duration_return"] = 7.25

        result_path, result_duration = _prepare_intro_for_problems(
            _make_problems(2), tmp_path,
        )

        # 回傳 normalize 後 path + duration
        assert result_path is not None
        assert result_path.read_bytes() == b"NORMALIZED_SENTINEL"
        assert result_duration == 7.25

        # normalize 收到正確 AudioSpec(96000 / 1 / aac) — 鎖規格不被偷改
        # (改規格會跟主影片 audio spec 不對齊, ffmpeg concat 會炸 / 噪音)
        assert len(stub_video_concat["normalize_calls"]) == 1
        input_path, spec, _assets_dir = stub_video_concat["normalize_calls"][0]
        assert input_path == intro_file
        assert spec.sample_rate == 96000
        assert spec.channels == 1
        assert spec.codec == "aac"

        # get_video_duration 收到的是 normalize 後的 path (不是原 intro)
        # — 鎖 normalize → probe 順序, 真實 duration 該量 normalized 後版本
        assert len(stub_video_concat["duration_calls"]) == 1
        assert stub_video_concat["duration_calls"][0] == result_path

    def test_zero_duration_passes_through(
        self, tmp_path, intro_file, stub_video_concat,
    ):
        """get_video_duration 回 0.0 不該被當作失敗 — 該透傳給 caller,
        caller 用此值決定下游 SRT padding 雙閘 (iter 127 鎖了 > 0 條件).

        鎖: helper 不該偷做「duration<=0 → 視為失敗回 None」邏輯,
        那會讓 SRT 雙閘失去作用 (本層該透傳, 雙閘該交給 caller).
        """
        stub_video_concat["duration_return"] = 0.0

        result_path, result_duration = _prepare_intro_for_problems(
            _make_problems(1), tmp_path,
        )

        # path 仍回 (不該因 duration=0 變 None)
        assert result_path is not None
        assert result_duration == 0.0

    def test_info_log_contains_intro_direction_keyword(
        self, tmp_path, intro_file, stub_video_concat, caplog,
    ):
        """logger.info 該含「intro 已 normalize」+「將串接到 N 支主影片前」.

        鎖「前」字 vs outro 的「後」字 (兩 helper 對稱但訊息方向不同,
        合併兩段訊息會讓 UX 含糊不清).
        """
        with caplog.at_level(logging.INFO, logger="server.runner"):
            _prepare_intro_for_problems(_make_problems(5), tmp_path)

        # 訊息含「intro 已 normalize」+「將串接到」+「5 支主影片前」
        # — 5 是 problems 數量, 鎖 len() 字串化進訊息
        assert any(
            "intro 已 normalize" in rec.message
            and "5" in rec.message
            and "前" in rec.message
            for rec in caplog.records
        )


class TestIntroFailureSwallowed:
    """例外吞掉是 design intent (intro 串接 nice-to-have, 不擋主影片成品)."""

    def test_normalize_raise_does_not_propagate(
        self, tmp_path, intro_file, monkeypatch, caplog,
    ):
        """normalize_intro_audio raise → (None, 0.0) + logger.exception 留紀錄.

        鎖: get_video_duration 不該被叫 (normalize 失敗該早 return, 不該對
        不存在的 normalized 路徑做 probe — 否則炸 FileNotFoundError 又被吞,
        日誌會出現兩段誤導性 exception).
        """
        import core.video_concat

        duration_called = []

        def boom_normalize(input_path, target_spec, assets_dir):
            raise RuntimeError("ffmpeg normalize fail")

        def fake_duration(video_path):
            duration_called.append(video_path)
            return 5.5

        monkeypatch.setattr(
            core.video_concat, "normalize_intro_audio", boom_normalize,
        )
        monkeypatch.setattr(
            core.video_concat, "get_video_duration", fake_duration,
        )

        with caplog.at_level(logging.ERROR, logger="server.runner"):
            # 不該 raise
            result = _prepare_intro_for_problems(_make_problems(2), tmp_path)

        assert result == (None, 0.0)
        # get_video_duration 該完全沒被叫
        assert duration_called == []
        # logger.exception 留紀錄, 含「intro 準備失敗」+「跳過 intro 串接」
        assert any(
            "intro 準備失敗" in rec.message and "跳過 intro 串接" in rec.message
            for rec in caplog.records
        )

    def test_get_duration_raise_does_not_propagate(
        self, tmp_path, intro_file, monkeypatch, caplog,
    ):
        """normalize 成功但 get_video_duration raise → (None, 0.0).

        鎖: except Exception 範圍夠大 (包到 get_video_duration), 不是只
        try normalize 那段. probe 失敗很實際 (corrupt mp4 / ffprobe missing).
        """
        import core.video_concat

        def fake_normalize(input_path, target_spec, assets_dir):
            out = Path(input_path).with_suffix(".normalized.mp4")
            out.write_bytes(b"NORMALIZED_SENTINEL")
            return out

        def boom_duration(video_path):
            raise ValueError("ffprobe returned malformed duration")

        monkeypatch.setattr(
            core.video_concat, "normalize_intro_audio", fake_normalize,
        )
        monkeypatch.setattr(
            core.video_concat, "get_video_duration", boom_duration,
        )

        with caplog.at_level(logging.ERROR, logger="server.runner"):
            result = _prepare_intro_for_problems(_make_problems(1), tmp_path)

        assert result == (None, 0.0)
        assert any(
            "intro 準備失敗" in rec.message
            for rec in caplog.records
        )


# =========================================================================
#                     _prepare_outro_for_problems tests
# =========================================================================

class TestOutroNoOpPath:
    """outro 檔不存在 — 不該炸, 不該 call normalize, 該 log warning."""

    def test_missing_outro_file_skips_silently(
        self, tmp_path, stub_video_concat, monkeypatch, caplog,
    ):
        """get_outro_video_path 指向不存在的路徑 → (None, 0.0) +
        warning 含「outro 檔不存在」+「跳過 outro 串接」+ normalize /
        get_video_duration 都沒被叫.

        (跟 test_outro_video_qr.py 既有 1 test 概念重疊, 但既有 test
        只驗 return tuple, 沒鎖訊息字串跟 normalize/duration 沒被叫 —
        這 test 補強訊息對齊跟 early return 防禦.)
        """
        import core.config
        nonexistent = tmp_path / "does_not_exist_outro.mp4"
        monkeypatch.setattr(
            core.config, "get_outro_video_path", lambda: str(nonexistent),
        )

        with caplog.at_level(logging.WARNING, logger="server.runner"):
            result = _prepare_outro_for_problems(_make_problems(3), tmp_path)

        assert result == (None, 0.0)
        assert stub_video_concat["normalize_calls"] == []
        assert stub_video_concat["duration_calls"] == []
        assert any(
            "outro 檔不存在" in rec.message and "跳過 outro 串接" in rec.message
            for rec in caplog.records
        )


class TestOutroHappyPath:
    """outro 檔在 → normalize + get_video_duration 都跑, 回 (path, duration)."""

    def test_returns_normalized_path_with_locked_audio_spec(
        self, tmp_path, outro_file, stub_video_concat,
    ):
        """outro normalize 收到的 AudioSpec 該跟 intro 完全一致.

        鎖: intro 跟 outro 都接到主影片, 兩者 audio spec 不一致會讓 ffmpeg
        concat filter 重採樣或炸 — 兩 helper 該共用同一組 (96000, 1, 'aac').
        """
        stub_video_concat["duration_return"] = 4.0

        result_path, result_duration = _prepare_outro_for_problems(
            _make_problems(2), tmp_path,
        )

        assert result_path is not None
        assert result_path.read_bytes() == b"NORMALIZED_SENTINEL"
        assert result_duration == 4.0

        # AudioSpec 跟 intro 一致 — 鎖兩 helper 同 spec, 不被偷改成不同值
        assert len(stub_video_concat["normalize_calls"]) == 1
        input_path, spec, _assets_dir = stub_video_concat["normalize_calls"][0]
        assert input_path == outro_file
        assert spec.sample_rate == 96000
        assert spec.channels == 1
        assert spec.codec == "aac"

    def test_info_log_contains_outro_direction_keyword(
        self, tmp_path, outro_file, stub_video_concat, caplog,
    ):
        """logger.info 該含「outro 已 normalize」+「將串到 N 支主影片後」.

        鎖「後」字 vs intro 的「前」字. 兩 helper 對稱但訊息方向不同,
        若兩段訊息被合併或被偷改成同字, UX 會混淆「intro/outro 接哪一端」.
        """
        with caplog.at_level(logging.INFO, logger="server.runner"):
            _prepare_outro_for_problems(_make_problems(4), tmp_path)

        assert any(
            "outro 已 normalize" in rec.message
            and "4" in rec.message
            and "後" in rec.message
            for rec in caplog.records
        )


class TestOutroFailureSwallowed:
    """例外吞掉是 design intent (跟 intro 對稱)."""

    def test_normalize_raise_does_not_propagate(
        self, tmp_path, outro_file, monkeypatch, caplog,
    ):
        """normalize_intro_audio raise → (None, 0.0) + logger.exception.

        鎖 except 範圍 + 不該擋整 job — outro 跟 intro 都是 nice-to-have.
        """
        import core.video_concat

        def boom_normalize(input_path, target_spec, assets_dir):
            raise RuntimeError("ffmpeg normalize fail")

        monkeypatch.setattr(
            core.video_concat, "normalize_intro_audio", boom_normalize,
        )

        with caplog.at_level(logging.ERROR, logger="server.runner"):
            result = _prepare_outro_for_problems(_make_problems(2), tmp_path)

        assert result == (None, 0.0)
        assert any(
            "outro 準備失敗" in rec.message and "跳過 outro 串接" in rec.message
            for rec in caplog.records
        )
