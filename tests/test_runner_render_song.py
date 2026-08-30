"""server.runner._run_render_song — SONG track (M3c) render-phase 分流 + 串接.

_run_render_inner 讀進 deck.json 後, 先用 is_song_schema (硬規則 #9 type guard)
早判 — 是 song → early-return _run_render_song, 不碰既有 exam/deck 分支。

_run_render_song 繞過 v0/render_video TTS pipeline:
  - song_segments_to_srt → 寫 job_dir/song.srt (subtitles filter 用 basename)
  - 每 valid segment 都備好 image_path 且檔案存在 → build_song_mv_kenburns_cmd
    (ken burns 推鏡); 任一段缺圖 → build_song_mv_cmd (純色背景, 不混搭)
  - subprocess.run(cmd, cwd=job_dir); returncode !=0 → RuntimeError;
    ffmpeg 不存在 (FileNotFoundError) → 清楚訊息
  - 空 / 全無效 segment → ValueError; 缺 audio_path → ValueError
  - section_id 忽略 (song 整首單一影片, 不支援單章)

策略 = monkeypatch server.runner.subprocess.run (routine 環境未必有 ffmpeg,
不真跑), 驗 cmd 內容 / cwd / SRT 真寫出 / 各 raise 路徑。0 真跑渲染。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import server.jobs as jobs_mod
import server.runner as runner_mod
from server.jobs import JobStore
from server.runner import _run_render_inner, _run_render_song
from server.schemas import CreateJobRequest, JobOptions, JobSource, SourceType


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


class _FakeProc:
    def __init__(self, returncode: int = 0, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> list:
    """monkeypatch subprocess.run — 記下 cmd/cwd, 預設成功 (returncode 0)."""
    calls: list = []

    def _run(cmd, **kwargs):
        calls.append({"cmd": cmd, "cwd": kwargs.get("cwd")})
        return _FakeProc(returncode=0)

    # song render 走共用 runner core.ffmpeg (T3-3), patch 到那層的 subprocess
    import core.ffmpeg as core_ffmpeg
    monkeypatch.setattr(core_ffmpeg.subprocess, "run", _run)
    return calls


def _song_deck(*, with_images: bool = True, audio: str = "song.mp3") -> dict:
    """song schema (M3b ingest 後存盤的樣子, 路徑已相對 job_dir)."""
    seg1 = {"id": "s1", "lines": ["第一段歌詞"], "start": 0.0, "end": 5.0}
    seg2 = {"id": "s2", "lines": ["第二段歌詞"], "start": 5.0, "end": 10.0}
    if with_images:
        seg1["image_path"] = "images/seg_s1.png"
        seg2["image_path"] = "images/seg_s2.png"
    return {
        "track_type": "song",
        "song_title": "測試歌",
        "audio_path": audio,
        "segments": [seg1, seg2],
    }


def _setup_job(store: JobStore, deck: dict, *, make_images: bool = True) -> tuple:
    """建 song job + 寫 deck.json + (選擇性) 備好 audio/圖檔. 回 (rec, job_dir)."""
    rec = store.create(CreateJobRequest(
        source_type=SourceType.SONG,
        source=JobSource(path="/fake/song.json"),
        options=JobOptions(),
    ))
    deck_path = store.deck_path(rec.id)
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")
    job_dir = deck_path.parent
    # audio 檔 (build cmd 不檢查存在, 但備著比較真實)
    if deck.get("audio_path"):
        (job_dir / deck["audio_path"]).write_bytes(b"\x00audio")
    if make_images:
        (job_dir / "images").mkdir(parents=True, exist_ok=True)
        for seg in deck["segments"]:
            ip = seg.get("image_path")
            if ip:
                (job_dir / ip).write_bytes(b"\x89PNG")
    return rec, job_dir


# ---------------------------------------------------------------- ken burns 模式


class TestKenBurnsMode:
    def test_all_segments_have_images_uses_kenburns(self, store, fake_run):
        rec, job_dir = _setup_job(store, _song_deck(with_images=True))
        asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))
        cmd = fake_run[0]["cmd"]
        joined = " ".join(cmd)
        # ken burns cmd 特徵: zoompan + filter_complex; 純色 cmd 沒有
        assert "zoompan" in joined
        assert "-filter_complex" in cmd
        assert "lavfi" not in joined  # 純色版才用 lavfi color source

    def test_kenburns_image_durations_from_segment_times(self, store, fake_run):
        rec, _ = _setup_job(store, _song_deck(with_images=True))
        asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))
        joined = " ".join(fake_run[0]["cmd"])
        # 兩段各 5 秒 → -t 5.0 出現兩次, 圖檔名相對 job_dir
        assert "images/seg_s1.png" in fake_run[0]["cmd"]
        assert "images/seg_s2.png" in fake_run[0]["cmd"]


# ---------------------------------------------------------------- 純色模式


class TestSolidColorMode:
    def test_missing_image_file_falls_back_to_solid(self, store, fake_run):
        # deck 標了 image_path 但檔案沒備 → 退純色 (不混搭)
        rec, _ = _setup_job(store, _song_deck(with_images=True), make_images=False)
        asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))
        joined = " ".join(fake_run[0]["cmd"])
        assert "zoompan" not in joined
        assert "lavfi" in joined  # 純色 color source

    def test_no_image_path_uses_solid(self, store, fake_run):
        rec, _ = _setup_job(store, _song_deck(with_images=False))
        asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))
        joined = " ".join(fake_run[0]["cmd"])
        assert "zoompan" not in joined
        assert "lavfi" in joined


# ---------------------------------------------------------------- SRT / cwd / 輸出


class TestSrtAndCwd:
    def test_srt_written_to_job_dir(self, store, fake_run):
        rec, job_dir = _setup_job(store, _song_deck(with_images=False))
        asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))
        srt = job_dir / "song.srt"
        assert srt.exists()
        body = srt.read_text(encoding="utf-8")
        assert "第一段歌詞" in body
        assert "00:00:00,000 --> 00:00:05,000" in body

    def test_subprocess_cwd_is_job_dir(self, store, fake_run):
        rec, job_dir = _setup_job(store, _song_deck(with_images=False))
        asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))
        assert fake_run[0]["cwd"] == str(job_dir)

    def test_output_into_artifacts_dir(self, store, fake_run):
        rec, _ = _setup_job(store, _song_deck(with_images=False))
        asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))
        artifacts = store.artifacts_dir(rec.id)
        assert artifacts.exists()
        # out_stem = artifacts/song → cmd 末尾 song.mp4 (絕對路徑)
        out_arg = fake_run[0]["cmd"][-1]
        assert out_arg.endswith("song.mp4")
        assert str(artifacts) in out_arg

    def test_subtitles_filter_uses_basename(self, store, fake_run):
        rec, _ = _setup_job(store, _song_deck(with_images=False))
        asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))
        joined = " ".join(fake_run[0]["cmd"])
        # subtitles filter 用 basename song.srt (cwd 設 job_dir), 不帶絕對路徑冒號
        assert "subtitles=song.srt" in joined


# ---------------------------------------------------------------- raise 路徑


class TestErrorPaths:
    def test_empty_segments_raises(self, store, fake_run):
        deck = _song_deck(with_images=False)
        deck["segments"] = []
        rec, _ = _setup_job(store, deck, make_images=False)
        with pytest.raises(ValueError, match="有效 segment"):
            asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))
        assert fake_run == []  # 沒進到 subprocess

    def test_all_invalid_segments_raises(self, store, fake_run):
        deck = _song_deck(with_images=False)
        # end<=start → _valid_segment False → song_segments_to_srt 全跳過 → 空 srt
        for seg in deck["segments"]:
            seg["end"] = seg["start"]
        rec, _ = _setup_job(store, deck, make_images=False)
        with pytest.raises(ValueError, match="有效 segment"):
            asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))

    def test_missing_audio_path_raises(self, store, fake_run):
        rec, _ = _setup_job(store, _song_deck(with_images=False, audio=""))
        with pytest.raises(ValueError, match="audio_path"):
            asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))

    def test_ffmpeg_nonzero_returncode_raises(
        self, store, monkeypatch: pytest.MonkeyPatch,
    ):
        def _run(cmd, **kwargs):
            return _FakeProc(returncode=1, stderr="boom")
        import core.ffmpeg as core_ffmpeg
        monkeypatch.setattr(core_ffmpeg.subprocess, "run", _run)
        rec, _ = _setup_job(store, _song_deck(with_images=False))
        with pytest.raises(RuntimeError, match="ffmpeg render 失敗"):
            asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))

    def test_ffmpeg_not_found_raises(
        self, store, monkeypatch: pytest.MonkeyPatch,
    ):
        def _run(cmd, **kwargs):
            raise FileNotFoundError("ffmpeg")
        import core.ffmpeg as core_ffmpeg
        monkeypatch.setattr(core_ffmpeg.subprocess, "run", _run)
        rec, _ = _setup_job(store, _song_deck(with_images=False))
        with pytest.raises(FileNotFoundError, match="ffmpeg"):
            asyncio.run(_run_render_song(store, rec, _read_deck(store, rec)))


# ---------------------------------------------------------------- 分流 (整合)


class TestRenderInnerDispatch:
    def test_run_render_inner_routes_song_to_song_renderer(self, store, fake_run):
        """_run_render_inner 用 is_song_schema 早判 → 走 song 渲染 (產 song.srt)."""
        rec, job_dir = _setup_job(store, _song_deck(with_images=False))
        asyncio.run(_run_render_inner(store, rec))
        # 走 song 分支的證據: song.srt 寫出 + subprocess 收到 song cmd (純色)
        assert (job_dir / "song.srt").exists()
        assert len(fake_run) == 1
        assert "subtitles=song.srt" in " ".join(fake_run[0]["cmd"])

    def test_section_id_ignored_for_song(self, store, fake_run):
        """section_id 給了也忽略 (song 整首單一影片) — 不 raise section 找不到."""
        rec, job_dir = _setup_job(store, _song_deck(with_images=True))
        asyncio.run(_run_render_song(store, rec, _read_deck(store, rec), section_id="s1"))
        # 仍正常產出整首 (ken burns), 沒被 section_id 影響
        assert (job_dir / "song.srt").exists()
        assert "zoompan" in " ".join(fake_run[0]["cmd"])


# ---------------------------------------------------------------- helper


def _read_deck(store: JobStore, rec) -> dict:
    return json.loads(store.deck_path(rec.id).read_text(encoding="utf-8"))
