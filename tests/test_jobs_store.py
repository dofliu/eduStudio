"""server.jobs.JobStore 測試 — 用 tmp_path 隔離每個 test 的 jobs/ 目錄。

JobStore 是核心狀態, 一旦壞掉所有 server 行為都崩, 所以這層 test 一定要有。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import server.jobs as jobs_mod
from server.jobs import JobStore
from server.schemas import (
    Artifact,
    CreateJobRequest,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
    StageInfo,
    YoutubeUpload,
    YoutubeUploadState,
)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    """每個 test 自己的乾淨 JobStore, 不影響真實 jobs/ 目錄。

    JobStore 內部 helpers (_job_dir / _state_path) 用 module-level JOBS_DIR
    全域常數 (不是 self.root), 所以要 monkeypatch 那個 module attribute
    才能真的隔離。self.root 也跟著改保持一致。
    """
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


@pytest.fixture
def basic_request() -> CreateJobRequest:
    return CreateJobRequest(
        source_type=SourceType.EXAM_PDF,
        source=JobSource(path="/fake.pdf"),
        options=JobOptions(),
    )


# ---------- Create / Get ----------

class TestCreateAndGet:
    def test_create_returns_record_with_id(self, store, basic_request):
        rec = store.create(basic_request)
        assert rec.id and len(rec.id) == 12  # uuid hex 12 chars
        assert rec.state == JobState.PENDING
        assert rec.source_type == SourceType.EXAM_PDF

    def test_create_persists_to_disk(self, store, basic_request):
        rec = store.create(basic_request)
        state_file = store.root / rec.id / "state.json"
        assert state_file.exists()

    def test_create_creates_artifacts_dir(self, store, basic_request):
        rec = store.create(basic_request)
        assert (store.root / rec.id / "artifacts").exists()

    def test_get_returns_record(self, store, basic_request):
        rec = store.create(basic_request)
        got = store.get(rec.id)
        assert got is not None
        assert got.id == rec.id

    def test_get_returns_none_for_missing(self, store):
        assert store.get("nonexistent") is None

    def test_create_assigns_unique_ids(self, store, basic_request):
        ids = {store.create(basic_request).id for _ in range(5)}
        assert len(ids) == 5

    def test_exam_pdf_default_require_review_true(self, store):
        # 硬規則 #1: AI 答案必須人工 review
        req = CreateJobRequest(
            source_type=SourceType.EXAM_PDF,
            source=JobSource(path="/fake.pdf"),
            options=JobOptions(),  # 不指定 require_review
        )
        rec = store.create(req)
        assert rec.options.require_review is True

    def test_slides_pdf_default_require_review_false(self, store):
        req = CreateJobRequest(
            source_type=SourceType.SLIDES_PDF,
            source=JobSource(path="/fake.pdf"),
            options=JobOptions(),
        )
        rec = store.create(req)
        assert rec.options.require_review is False

    def test_explicit_require_review_overrides_default(self, store):
        req = CreateJobRequest(
            source_type=SourceType.EXAM_PDF,
            source=JobSource(path="/fake.pdf"),
            options=JobOptions(require_review=False),
        )
        rec = store.create(req)
        assert rec.options.require_review is False    # 強制 False 也認


# ---------- List ----------

class TestList:
    def test_empty_initially(self, store):
        assert store.list() == []

    def test_lists_in_created_at_desc(self, store, basic_request):
        import time
        rec1 = store.create(basic_request)
        time.sleep(0.002)   # utc_now 微秒級時間戳, sleep 防同時間戳排序不穩
        rec2 = store.create(basic_request)
        time.sleep(0.002)
        rec3 = store.create(basic_request)
        listed = store.list()
        assert len(listed) == 3
        # 新到舊 (rec3 → rec2 → rec1)
        assert listed[0].id == rec3.id
        assert listed[2].id == rec1.id


    def test_list_mixes_naive_and_aware_state_jsons(self, store, basic_request):
        # Regression (2026-05-10): 既存 state.json 是舊版 utc_now 的 naive datetime,
        # 新建 job 的 created_at 是 aware (P0 #4 fix). store.list() 要能 sort
        # 兩種混存而不 TypeError. 修法是 schemas AwareDatetime AfterValidator 統一補 UTC.
        import json
        # 先建一個 aware (走正常 store.create 路徑)
        rec_aware = store.create(basic_request)
        # 再手寫一份 naive 的 state.json 模擬舊資料
        legacy_id = "abc123def456"
        legacy_dir = store.root / legacy_id
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy = {
            "id": legacy_id,
            "source_type": "exam_pdf",
            "source": {"path": "/legacy.pdf", "url": None},
            "options": {},
            "state": "done",
            # 沒帶 tz 字尾 (naive ISO), 模擬 P0 #4 之前的格式
            "created_at": "2026-05-09T10:00:00.000000",
            "updated_at": "2026-05-09T10:30:00.000000",
            "stages": [], "artifacts": [],
        }
        (legacy_dir / "state.json").write_text(
            json.dumps(legacy), encoding="utf-8",
        )
        # 重新從磁碟 load → list(), 應該能 sort 兩筆 (一 naive 一 aware) 不 TypeError
        new_store = JobStore(root=store.root)
        listed = new_store.list()
        assert len(listed) == 2
        # 新建 job 比 legacy 晚, 應該排第一 (新到舊)
        assert listed[0].id == rec_aware.id
        assert listed[1].id == legacy_id
        # legacy record 的 datetime 也已被 normalize 成 aware
        assert listed[1].created_at.tzinfo is not None


# ---------- Update ----------

class TestUpdate:
    def test_update_changes_field(self, store, basic_request):
        rec = store.create(basic_request)
        updated = store.update(rec.id, state=JobState.RENDERING)
        assert updated.state == JobState.RENDERING

    def test_update_bumps_updated_at(self, store, basic_request):
        rec = store.create(basic_request)
        original_updated = rec.updated_at
        # 等一下避免時間戳同一 microsecond
        import time
        time.sleep(0.001)
        updated = store.update(rec.id, state=JobState.RENDERING)
        assert updated.updated_at > original_updated

    def test_update_persists_to_disk(self, store, basic_request):
        rec = store.create(basic_request)
        store.update(rec.id, state=JobState.DONE)
        # 重新建 store 從磁碟讀, 應該看到 DONE
        new_store = JobStore(root=store.root)
        reloaded = new_store.get(rec.id)
        assert reloaded.state == JobState.DONE

    def test_update_unknown_raises(self, store):
        with pytest.raises(KeyError):
            store.update("nonexistent", state=JobState.DONE)


# ---------- Stages ----------

class TestStages:
    def test_add_stage(self, store, basic_request):
        rec = store.create(basic_request)
        store.add_stage(rec.id, StageInfo(
            name="ingest", state="running", started_at=datetime.utcnow(),
        ))
        got = store.get(rec.id)
        assert len(got.stages) == 1
        assert got.stages[0].name == "ingest"

    def test_update_last_stage(self, store, basic_request):
        rec = store.create(basic_request)
        store.add_stage(rec.id, StageInfo(
            name="ingest", state="running", started_at=datetime.utcnow(),
        ))
        store.update_last_stage(rec.id, state="done", ended_at=datetime.utcnow())
        got = store.get(rec.id)
        assert got.stages[-1].state == "done"
        assert got.stages[-1].ended_at is not None

    def test_update_last_stage_no_stages_raises(self, store, basic_request):
        rec = store.create(basic_request)
        with pytest.raises(ValueError, match="沒有 stage"):
            store.update_last_stage(rec.id, state="done")


# ---------- Delete ----------

class TestDelete:
    def test_delete_removes_from_cache(self, store, basic_request):
        rec = store.create(basic_request)
        assert store.delete(rec.id) is True
        assert store.get(rec.id) is None

    def test_delete_removes_from_disk(self, store, basic_request):
        rec = store.create(basic_request)
        job_dir = store.root / rec.id
        store.delete(rec.id)
        assert not job_dir.exists()

    def test_delete_unknown_returns_false(self, store):
        assert store.delete("nonexistent") is False


# ---------- Artifacts ----------

class TestArtifacts:
    def test_scan_artifacts_empty(self, store, basic_request):
        rec = store.create(basic_request)
        assert store.scan_artifacts(rec.id) == []

    def test_scan_artifacts_picks_up_files(self, store, basic_request):
        rec = store.create(basic_request)
        artifacts_dir = store.root / rec.id / "artifacts"
        # 寫幾個檔
        (artifacts_dir / "q1.mp4").write_bytes(b"fake")
        (artifacts_dir / "q1.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        (artifacts_dir / "q1.json").write_text("{}", encoding="utf-8")
        (artifacts_dir / "thumbnail.png").write_bytes(b"png")
        artifacts = store.scan_artifacts(rec.id)
        kinds = {a.kind: a for a in artifacts}
        assert "mp4" in kinds
        assert "srt" in kinds
        assert "json" in kinds
        assert "png" in kinds

    def test_unknown_extension_kind_other(self, store, basic_request):
        rec = store.create(basic_request)
        (store.root / rec.id / "artifacts" / "weird.xyz").write_bytes(b"x")
        artifacts = store.scan_artifacts(rec.id)
        assert artifacts[0].kind == "other"

    def test_refresh_artifacts_updates_record(self, store, basic_request):
        rec = store.create(basic_request)
        (store.root / rec.id / "artifacts" / "q1.mp4").write_bytes(b"fake_data")
        updated = store.refresh_artifacts(rec.id)
        assert len(updated.artifacts) == 1
        assert updated.artifacts[0].name == "q1.mp4"


# ---------- YouTube uploads (PR-3f) ----------

class TestYoutubeUploads:
    def test_set_youtube_upload_creates_entry(self, store, basic_request):
        rec = store.create(basic_request)
        upload = YoutubeUpload(state=YoutubeUploadState.UPLOADING, title="test")
        updated = store.set_youtube_upload(rec.id, "q1.mp4", upload)
        assert updated.youtube_uploads["q1.mp4"].title == "test"
        assert updated.youtube_uploads["q1.mp4"].state == YoutubeUploadState.UPLOADING

    def test_patch_youtube_upload_partial(self, store, basic_request):
        rec = store.create(basic_request)
        # 先 set 一個基本的
        store.set_youtube_upload(rec.id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.UPLOADING, title="old",
        ))
        # patch 只動 progress
        store.patch_youtube_upload(rec.id, "q1.mp4", progress_percent=50)
        updated = store.get(rec.id)
        upload = updated.youtube_uploads["q1.mp4"]
        assert upload.progress_percent == 50
        assert upload.title == "old"      # 原欄位保留

    def test_patch_youtube_upload_creates_if_missing(self, store, basic_request):
        rec = store.create(basic_request)
        # 從未 set 過, 直接 patch
        store.patch_youtube_upload(rec.id, "q1.mp4", title="new", progress_percent=10)
        updated = store.get(rec.id)
        upload = updated.youtube_uploads["q1.mp4"]
        assert upload.title == "new"
        assert upload.progress_percent == 10
        assert upload.state == YoutubeUploadState.PENDING  # default

    def test_youtube_uploads_persists_across_reloads(self, store, basic_request):
        rec = store.create(basic_request)
        store.set_youtube_upload(rec.id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.DONE,
            video_id="abc123",
            url="https://youtu.be/abc123",
        ))
        # 重建 store 從磁碟
        new_store = JobStore(root=store.root)
        reloaded = new_store.get(rec.id)
        upload = reloaded.youtube_uploads["q1.mp4"]
        assert upload.state == YoutubeUploadState.DONE
        assert upload.video_id == "abc123"


# ---------- Reload from disk (corruption tolerance) ----------

class TestReloadFromDisk:
    def test_loads_existing_state_files(self, store, basic_request):
        rec = store.create(basic_request)
        rec2 = store.create(basic_request)
        # 重建 store
        new_store = JobStore(root=store.root)
        ids = {r.id for r in new_store.list()}
        assert rec.id in ids
        assert rec2.id in ids

    def test_skips_corrupt_state_file(self, store, basic_request, capsys):
        rec = store.create(basic_request)
        # 弄壞一個 state.json
        bad_dir = store.root / "broken_id"
        bad_dir.mkdir()
        (bad_dir / "state.json").write_text("not valid json", encoding="utf-8")
        # 重建 — 壞的應該被略過, 好的仍載入
        new_store = JobStore(root=store.root)
        ids = {r.id for r in new_store.list()}
        assert rec.id in ids
        assert "broken_id" not in ids
        # 印警告 (不擋啟動)
        captured = capsys.readouterr()
        assert "broken_id" in captured.out
