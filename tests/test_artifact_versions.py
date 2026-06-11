"""F9-4 影片版本管理 — JobStore.archive_artifacts + runner 重 render 歸檔。

重 render 一個已完成的 job 前, 應把現有 artifacts/ 快照進 artifact_history/v<N>/
不覆蓋, 避免「重 render 蓋掉還能用的好版本」。全 tmp 隔離不打 API (offline-first)。
"""
from __future__ import annotations

from pathlib import Path

import pytest

import server.jobs as jobs_mod
import server.runner as runner_mod
from server.jobs import JobStore
from server.runner import _run_render_phase
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


@pytest.fixture
def job_id(store: JobStore) -> str:
    rec = store.create(CreateJobRequest(
        source_type=SourceType.EXAM_PDF,
        source=JobSource(path="/fake.pdf"),
        options=JobOptions(),
    ))
    store.update(rec.id, reviewed=True)
    store.artifacts_dir(rec.id).mkdir(parents=True, exist_ok=True)
    return rec.id


def _write_artifacts(store: JobStore, job_id: str, **files: bytes) -> None:
    d = store.artifacts_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        # name 用 __ 代替 . (kwargs 不能帶點), 還原成副檔名
        (d / name.replace("__", ".")).write_bytes(data)


# ---------------------------------------------------------------- archive_artifacts

class TestArchiveArtifacts:
    def test_empty_artifacts_returns_none(self, store, job_id):
        """沒可保留的舊版 (artifacts/ 空) → no-op 回 None, 不建歷史目錄。"""
        assert store.archive_artifacts(job_id) is None
        rec = store.get(job_id)
        assert rec.artifact_versions == []
        assert not (store.job_dir(job_id) / "artifact_history").exists()

    def test_missing_artifacts_dir_returns_none(self, store, job_id):
        """連 artifacts/ 都不存在 → 不炸, 回 None。"""
        import shutil
        shutil.rmtree(store.artifacts_dir(job_id))
        assert store.archive_artifacts(job_id) is None

    def test_snapshot_copies_files_non_destructive(self, store, job_id):
        """歸檔是 copy 非 move: artifacts/ 原檔仍在, 歷史目錄拿到一份。"""
        _write_artifacts(store, job_id, final__mp4=b"video-v1", final__srt=b"subs-v1")
        rec = store.archive_artifacts(job_id)
        assert rec is not None
        # 原 artifacts/ 不動
        assert (store.artifacts_dir(job_id) / "final.mp4").read_bytes() == b"video-v1"
        # 歷史目錄拿到一份
        hist = store.job_dir(job_id) / "artifact_history" / "v1"
        assert (hist / "final.mp4").read_bytes() == b"video-v1"
        assert (hist / "final.srt").read_bytes() == b"subs-v1"

    def test_version_record_fields(self, store, job_id):
        _write_artifacts(store, job_id, final__mp4=b"video-v1")
        rec = store.archive_artifacts(job_id, note="手動測試")
        snap = rec.artifact_versions[-1]
        assert snap.version == 1
        assert snap.path == "artifact_history/v1"
        assert snap.note == "手動測試"
        assert snap.archived_at is not None and snap.created_at is not None
        names = {a.name for a in snap.artifacts}
        assert names == {"final.mp4"}
        a = snap.artifacts[0]
        assert a.kind == "mp4"
        assert a.size_bytes == len(b"video-v1")
        # path 相對於 jobs/ = "<id>/artifact_history/v1/final.mp4"
        assert a.path == f"{job_id}/artifact_history/v1/final.mp4"
        assert "\\" not in a.path

    def test_kind_classification(self, store, job_id):
        _write_artifacts(store, job_id, a__mp4=b"x", b__srt=b"x", c__json=b"x",
                         d__png=b"x", e__txt=b"x")
        rec = store.archive_artifacts(job_id)
        kinds = {a.name: a.kind for a in rec.artifact_versions[0].artifacts}
        assert kinds == {"a.mp4": "mp4", "b.srt": "srt", "c.json": "json",
                         "d.png": "png", "e.txt": "other"}

    def test_multiple_versions_increment(self, store, job_id):
        """連兩次歸檔 → v1, v2 各自獨立保留不同內容。"""
        _write_artifacts(store, job_id, final__mp4=b"video-v1")
        store.archive_artifacts(job_id)
        # 覆蓋成新內容再歸檔
        _write_artifacts(store, job_id, final__mp4=b"video-v2")
        rec = store.archive_artifacts(job_id)
        assert [v.version for v in rec.artifact_versions] == [1, 2]
        v1 = store.job_dir(job_id) / "artifact_history" / "v1" / "final.mp4"
        v2 = store.job_dir(job_id) / "artifact_history" / "v2" / "final.mp4"
        assert v1.read_bytes() == b"video-v1"
        assert v2.read_bytes() == b"video-v2"

    def test_persisted_across_reload(self, store, job_id):
        """artifact_versions 寫盤, 換一個 store 重讀仍在 (state.json 持久化)。"""
        _write_artifacts(store, job_id, final__mp4=b"video-v1")
        store.archive_artifacts(job_id)
        reloaded = JobStore(root=store.root)
        rec = reloaded.get(job_id)
        assert len(rec.artifact_versions) == 1
        assert rec.artifact_versions[0].version == 1

    def test_unknown_job_raises(self, store):
        with pytest.raises(KeyError):
            store.archive_artifacts("nope")


# ---------------------------------------------------------------- runner 整合

class TestRenderArchiveIntegration:
    """_run_render_phase 重 render 一個 DONE job 前自動歸檔, 其餘狀態不歸檔。"""

    @pytest.fixture
    def stub_render(self, monkeypatch: pytest.MonkeyPatch):
        """stub _run_render — no-op, 不真跑 ffmpeg/TTS。"""
        async def fake_run_render(store, rec, *, section_id=None):
            return None
        monkeypatch.setattr(runner_mod, "_run_render", fake_run_render)

    @pytest.fixture
    def stub_log(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(runner_mod, "attach_job_log", lambda *a, **k: None)
        monkeypatch.setattr(runner_mod, "detach_job_log", lambda *a, **k: None)

    @pytest.mark.asyncio
    async def test_rerender_of_done_archives(self, store, job_id, stub_render, stub_log):
        """DONE job 重 render → 舊 artifacts 被歸檔成 v1。"""
        _write_artifacts(store, job_id, final__mp4=b"good-version")
        store.update(job_id, state=JobState.DONE)
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert rec.state == JobState.DONE
        assert len(rec.artifact_versions) == 1
        hist = store.job_dir(job_id) / "artifact_history" / "v1" / "final.mp4"
        assert hist.read_bytes() == b"good-version"

    @pytest.mark.asyncio
    async def test_first_render_does_not_archive(self, store, job_id, stub_render, stub_log):
        """首次 render (非 DONE, 這裡 PENDING) 不歸檔 — 沒有舊版要保留。"""
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert rec.artifact_versions == []

    @pytest.mark.asyncio
    async def test_failed_retry_does_not_archive(self, store, job_id, stub_render, stub_log):
        """FAILED retry 不歸檔 — 失敗的 render 沒有可保留的好版本。"""
        _write_artifacts(store, job_id, partial__mp4=b"broken")
        store.update(job_id, state=JobState.FAILED, error="上次 ffmpeg 炸")
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert rec.artifact_versions == []

    @pytest.mark.asyncio
    async def test_rerender_done_but_empty_artifacts_no_archive(
        self, store, job_id, stub_render, stub_log
    ):
        """DONE 但 artifacts/ 空 → archive_artifacts no-op, 不留空版本。"""
        store.update(job_id, state=JobState.DONE)
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert rec.artifact_versions == []
