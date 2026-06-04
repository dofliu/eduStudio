"""SONG M0b helper CLI 測試 — tools/song_mv.py.

純 offline: dry-run 路徑不真跑 ffmpeg; 真跑路徑 monkeypatch subprocess.run。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# tools/ 不是 package, 且 site-packages 有同名 `tools` 套件會 shadow `import tools.X`.
# 比照 test_gen_icon_svgs.py: 掛 tools 目錄上 path 當 top-level module 載入.
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.append(str(_TOOLS_DIR))

import song_mv  # noqa: E402


def _write_song(tmp_path, segments, *, audio="song.mp3", title="測試歌"):
    song = {
        "track_type": "song",
        "song_title": title,
        "audio_path": audio,
        "segments": segments,
    }
    p = tmp_path / "song.json"
    p.write_text(json.dumps(song, ensure_ascii=False), encoding="utf-8")
    return p


_SEGS = [
    {"id": "s1", "lines": ["第一行"], "start": 0.0, "end": 5.0},
    {"id": "s2", "lines": ["第二行"], "start": 5.0, "end": 10.0},
]


class TestDryRun:
    def test_dry_run_prints_srt_and_cmd_returns_0(self, tmp_path, capsys):
        sp = _write_song(tmp_path, _SEGS)
        rc = song_mv.main([str(sp), "--dry-run"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "第一行" in out and "第二行" in out
        assert "ffmpeg" in out and "subtitles=song.srt" in out
        assert "2 cue" in out

    def test_dry_run_does_not_write_srt(self, tmp_path):
        sp = _write_song(tmp_path, _SEGS)
        song_mv.main([str(sp), "--dry-run"])
        assert not (tmp_path / "song.srt").exists()

    def test_dry_run_custom_style_in_cmd(self, tmp_path, capsys):
        sp = _write_song(tmp_path, _SEGS)
        song_mv.main([str(sp), "--dry-run", "--bg", "navy", "--font-size", "48"])
        out = capsys.readouterr().out
        assert "color=c=navy" in out and "FontSize=48" in out


class TestValidation:
    def test_missing_song_json_returns_2(self, tmp_path, capsys):
        rc = song_mv.main([str(tmp_path / "nope.json"), "--dry-run"])
        assert rc == 2
        assert "找不到 song.json" in capsys.readouterr().err

    def test_not_song_schema_returns_2(self, tmp_path, capsys):
        p = tmp_path / "deck.json"
        p.write_text(json.dumps({"deck_title": "x", "sections": []}), encoding="utf-8")
        rc = song_mv.main([str(p), "--dry-run"])
        assert rc == 2
        assert "song schema" in capsys.readouterr().err

    def test_all_invalid_segments_returns_2(self, tmp_path, capsys):
        sp = _write_song(tmp_path, [{"lines": [], "start": 0, "end": 1}])
        rc = song_mv.main([str(sp), "--dry-run"])
        assert rc == 2
        assert "有效 segment" in capsys.readouterr().err


class TestResolveAudio:
    def test_relative_audio_resolved_against_song_dir(self, tmp_path):
        sp = _write_song(tmp_path, _SEGS, audio="music/track.mp3")
        song = song_mv.load_song(sp)
        resolved = song_mv.resolve_audio(song, sp)
        assert resolved == (tmp_path / "music" / "track.mp3").resolve()

    def test_absolute_audio_kept(self, tmp_path):
        abs = (tmp_path / "abs.mp3").resolve()
        sp = _write_song(tmp_path, _SEGS, audio=str(abs))
        song = song_mv.load_song(sp)
        assert song_mv.resolve_audio(song, sp) == abs


class TestRealRun:
    def test_real_run_writes_srt_and_invokes_ffmpeg(self, tmp_path, monkeypatch, capsys):
        # 準備 audio 檔 (真跑前會檢查存在)
        (tmp_path / "song.mp3").write_bytes(b"\x00")
        sp = _write_song(tmp_path, _SEGS)

        calls = {}

        class _Proc:
            returncode = 0

        def fake_run(cmd, cwd=None):
            calls["cmd"] = cmd
            calls["cwd"] = cwd
            return _Proc()

        monkeypatch.setattr(song_mv.subprocess, "run", fake_run)
        rc = song_mv.main([str(sp)])
        assert rc == 0
        # srt 真寫出
        assert (tmp_path / "song.srt").exists()
        assert "第一行" in (tmp_path / "song.srt").read_text(encoding="utf-8")
        # ffmpeg 被呼叫, cwd = song.json 目錄
        assert calls["cmd"][0] == "ffmpeg"
        assert calls["cwd"] == str(tmp_path.resolve())

    def test_missing_audio_returns_2(self, tmp_path, capsys):
        sp = _write_song(tmp_path, _SEGS, audio="missing.mp3")
        rc = song_mv.main([str(sp)])  # 非 dry-run, audio 不存在
        assert rc == 2
        assert "找不到歌曲音檔" in capsys.readouterr().err

    def test_ffmpeg_not_found_returns_3(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "song.mp3").write_bytes(b"\x00")
        sp = _write_song(tmp_path, _SEGS)

        def boom(cmd, cwd=None):
            raise FileNotFoundError("ffmpeg")

        monkeypatch.setattr(song_mv.subprocess, "run", boom)
        rc = song_mv.main([str(sp)])
        assert rc == 3
        assert "找不到 ffmpeg" in capsys.readouterr().err

    def test_ffmpeg_failure_propagates_returncode(self, tmp_path, monkeypatch):
        (tmp_path / "song.mp3").write_bytes(b"\x00")
        sp = _write_song(tmp_path, _SEGS)

        class _Proc:
            returncode = 1

        monkeypatch.setattr(song_mv.subprocess, "run", lambda cmd, cwd=None: _Proc())
        assert song_mv.main([str(sp)]) == 1
