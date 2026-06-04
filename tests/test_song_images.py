"""SONG M2 生圖測試 — core/song_images.py + tools/gen_song_images.py.

純 offline: 不呼叫 Gemini (build_image_prompt 0 API; 執行包真生圖 monkeypatch)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.song_images import DEFAULT_STYLE_SUFFIX, build_image_prompt

# tools/ 不是 package + site-packages 同名 shadow → 掛 tools 目錄上 path (同 test_song_mv)
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.append(str(_TOOLS_DIR))

import gen_song_images  # noqa: E402


class TestBuildImagePrompt:
    def test_combines_style_lyrics_suffix(self):
        seg = {"id": "s1", "lines": ["舊書牆架在舊書裡", "停在你沒翻的那頁"]}
        p = build_image_prompt(seg, "賽博龐克霓虹城市夜景")
        assert "賽博龐克霓虹城市夜景" in p
        assert "舊書牆架在舊書裡 / 停在你沒翻的那頁" in p
        assert "no text" in p  # 統一 suffix (圖不帶字, 歌詞由渲染層燒)

    def test_existing_image_prompt_wins(self):
        # 人工 review 修過的 image_prompt 優先, 不被歌詞覆蓋 (idempotent)
        seg = {"id": "s1", "lines": ["歌詞"], "image_prompt": "人工指定的精準 prompt"}
        assert build_image_prompt(seg, "風格") == "人工指定的精準 prompt"

    def test_empty_lyrics_still_has_style_and_suffix(self):
        p = build_image_prompt({"id": "s1", "lines": []}, "水墨風")
        assert "水墨風" in p
        assert DEFAULT_STYLE_SUFFIX in p

    def test_custom_suffix(self):
        p = build_image_prompt({"id": "s1", "lines": ["x"]}, "style", style_suffix="ZZZ")
        assert p.endswith("ZZZ")


def _song(tmp_path, *, style="霓虹夜景"):
    song = {
        "track_type": "song",
        "song_title": "測試",
        "visual_style": style,
        "segments": [
            {"id": "s1", "lines": ["第一段歌詞"], "start": 0, "end": 5},
            {"id": "s2", "lines": ["第二段歌詞"], "start": 5, "end": 10},
        ],
    }
    p = tmp_path / "song.json"
    p.write_text(json.dumps(song, ensure_ascii=False), encoding="utf-8")
    return p


class TestGenSongImagesDryRun:
    def test_dry_run_prints_prompts_no_api(self, tmp_path, capsys, monkeypatch):
        # 確保 dry-run 絕不呼叫生圖
        monkeypatch.setattr(
            gen_song_images, "generate_segment_image",
            lambda *a, **k: pytest.fail("dry-run 不該呼叫生圖"),
        )
        sp = _song(tmp_path)
        rc = gen_song_images.main([str(sp)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "霓虹夜景" in out  # visual_style 進 prompt
        assert "第一段歌詞" in out and "第二段歌詞" in out
        assert "沒燒額度" in out

    def test_dry_run_style_override(self, tmp_path, capsys):
        sp = _song(tmp_path, style="原始風格")
        gen_song_images.main([str(sp), "--style", "覆寫風格"])
        out = capsys.readouterr().out
        assert "覆寫風格" in out and "原始風格" not in out

    def test_dry_run_does_not_write_song_json(self, tmp_path):
        sp = _song(tmp_path)
        before = sp.read_text(encoding="utf-8")
        gen_song_images.main([str(sp)])
        assert sp.read_text(encoding="utf-8") == before  # song.json 沒被改


class TestGenSongImagesValidation:
    def test_missing_song_json(self, tmp_path, capsys):
        rc = gen_song_images.main([str(tmp_path / "nope.json")])
        assert rc == 2
        assert "找不到 song.json" in capsys.readouterr().err

    def test_not_song_schema(self, tmp_path, capsys):
        p = tmp_path / "deck.json"
        p.write_text(json.dumps({"deck_title": "x", "sections": []}), encoding="utf-8")
        rc = gen_song_images.main([str(p)])
        assert rc == 2

    def test_only_unknown_segment(self, tmp_path, capsys):
        sp = _song(tmp_path)
        rc = gen_song_images.main([str(sp), "--only", "nope"])
        assert rc == 2


class TestGenSongImagesExecute:
    def test_execute_writes_back_image_path_and_review_flag(self, tmp_path, monkeypatch, capsys):
        # monkeypatch 生圖: 假裝成功 (不真呼 Gemini)
        def fake_gen(prompt, out_path, **k):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"\x89PNG")
            return (True, "")
        monkeypatch.setattr(gen_song_images, "generate_segment_image", fake_gen)

        sp = _song(tmp_path)
        rc = gen_song_images.main([str(sp), "--execute"])
        assert rc == 0
        song = json.loads(sp.read_text(encoding="utf-8"))
        for seg in song["segments"]:
            # image_path 寫回 + reviewed=false (停 review, 不自動標 true)
            assert seg["image_path"] == f"images/seg_{seg['id']}.png"
            assert seg["reviewed"] is False
        # 圖真寫出
        assert (tmp_path / "images" / "seg_s1.png").exists()

    def test_execute_partial_failure_returns_1(self, tmp_path, monkeypatch):
        def fake_gen(prompt, out_path, **k):
            # s1 成功, s2 失敗
            if "第一段" in prompt:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"x")
                return (True, "")
            return (False, "safety filter")
        monkeypatch.setattr(gen_song_images, "generate_segment_image", fake_gen)
        sp = _song(tmp_path)
        rc = gen_song_images.main([str(sp), "--execute"])
        assert rc == 1  # 有失敗 → return 1

    def test_execute_does_not_auto_review_true(self, tmp_path, monkeypatch):
        # 硬規則: 生圖後 reviewed 一律 false, 不自動標 true
        monkeypatch.setattr(
            gen_song_images, "generate_segment_image",
            lambda prompt, out_path, **k: (out_path.parent.mkdir(parents=True, exist_ok=True), out_path.write_bytes(b"x"), (True, ""))[-1],
        )
        sp = _song(tmp_path)
        gen_song_images.main([str(sp), "--execute"])
        song = json.loads(sp.read_text(encoding="utf-8"))
        assert all(seg["reviewed"] is False for seg in song["segments"])
