"""GET /library 測試 (PR-3m library page + iter 47 final.mp4 優先).

不真打 Gemini / 不真 render, 用 fake JobRecord + scan_artifacts 注入測試.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

from server.jobs import JobStore, get_default_store
from server.main import create_app
from server.routes.library import _read_deck_title
from server.schemas import (
    Artifact,
    CreateJobRequest,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
    YoutubeUpload,
    YoutubeUploadState,
)


@pytest.fixture
def client(tmp_path):
    """乾淨 TestClient + 空 JobStore."""
    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


def _make_done_job(store: JobStore, artifact_names: list[str]) -> str:
    """建一個 state=done 的 job, 注入指定 artifact 名稱."""
    rec = store.create(CreateJobRequest(
        source_type=SourceType.DOCUMENT,
        source=JobSource(path="/tmp/fake.pdf"),
        options=JobOptions(require_review=False),
    ))
    artifacts = [
        Artifact(name=name, path=f"jobs/{rec.id}/artifacts/{name}",
                 size_bytes=1024 * 1024, kind="mp4")
        for name in artifact_names
    ]
    store.update(rec.id, state=JobState.DONE, artifacts=artifacts)
    return rec.id


class TestLibraryFinalMp4Priority:
    """iter 47: 有 final.mp4 時 library 只列 final.mp4, 不列各章."""

    def test_job_with_final_mp4_lists_only_final(self, client):
        c, store = client
        _make_done_job(store, ["ch1.mp4", "ch2.mp4", "ch3.mp4", "final.mp4"])
        resp = c.get("/library")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["artifact_name"] == "final.mp4"

    def test_job_without_final_mp4_lists_all(self, client):
        """沒 final.mp4 (例: 單章 deck / exam_pdf 逐題) 走原 logic 全列."""
        c, store = client
        _make_done_job(store, ["q1.mp4", "q2.mp4", "q3.mp4"])
        resp = c.get("/library")
        items = resp.json()["items"]
        names = sorted(i["artifact_name"] for i in items)
        assert names == ["q1.mp4", "q2.mp4", "q3.mp4"]

    def test_single_mp4_job_lists_it(self, client):
        """單一 mp4 (不叫 final.mp4) 也要列出."""
        c, store = client
        _make_done_job(store, ["q1.mp4"])
        resp = c.get("/library")
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["artifact_name"] == "q1.mp4"

    def test_only_final_mp4_lists_it(self, client):
        """只有 final.mp4 (理論上不會發生但防呆)."""
        c, store = client
        _make_done_job(store, ["final.mp4"])
        resp = c.get("/library")
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["artifact_name"] == "final.mp4"

    def test_no_mp4_job_skipped(self, client):
        """沒任何 mp4 的 job (失敗 / ingesting) 不該出現在 library."""
        c, store = client
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
            options=JobOptions(require_review=False),
        ))
        store.update(rec.id, state=JobState.DONE, artifacts=[])
        resp = c.get("/library")
        assert resp.json()["items"] == []

    def test_multiple_jobs_mixed(self, client):
        """多 job: 有 final 的列 final, 沒 final 的列全部."""
        c, store = client
        _make_done_job(store, ["ch1.mp4", "final.mp4"])
        _make_done_job(store, ["q1.mp4", "q2.mp4"])
        resp = c.get("/library")
        items = resp.json()["items"]
        names = sorted(i["artifact_name"] for i in items)
        # final + q1 + q2 = 3 個 (ch1 被 final 取代)
        assert names == ["final.mp4", "q1.mp4", "q2.mp4"]


class TestReadDeckTitle:
    """iter 115: _read_deck_title fallback chain — deck.json 不存在 / 壞掉 /
    缺鍵 / 兩個 title key 並存. helper 直接 unit test, 不繞 HTTP."""

    def test_no_deck_json_falls_back_to_job_id(self, tmp_path):
        """deck.json 不存在 → 退 job_id (job 還沒 ingest 完的常態)."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        assert _read_deck_title(store, rec.id) == rec.id

    def test_invalid_json_falls_back_to_job_id(self, tmp_path):
        """deck.json 內容壞掉 → except Exception 退 job_id, 不該 500."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text("{not valid json", encoding="utf-8")
        assert _read_deck_title(store, rec.id) == rec.id

    def test_exam_title_preferred(self, tmp_path):
        """exam_title 優先於 deck_title (v1 exam schema 主軌)."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.EXAM_PDF,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(
            json.dumps({"exam_title": "材料力學期中考", "deck_title": "ignored"}),
            encoding="utf-8",
        )
        assert _read_deck_title(store, rec.id) == "材料力學期中考"

    def test_deck_title_when_no_exam_title(self, tmp_path):
        """exam_title 缺 → 用 deck_title (repo / document / url 路徑)."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.REPO,
            source=JobSource(path="/tmp/repo"),
        ))
        store.deck_path(rec.id).write_text(
            json.dumps({"deck_title": "風能 SCADA 系統介紹"}),
            encoding="utf-8",
        )
        assert _read_deck_title(store, rec.id) == "風能 SCADA 系統介紹"

    def test_neither_title_falls_back_to_job_id(self, tmp_path):
        """兩個 title key 都缺 → 退 job_id (deck 壞掉但 JSON 可解析)."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(
            json.dumps({"sections": []}),
            encoding="utf-8",
        )
        assert _read_deck_title(store, rec.id) == rec.id

    def test_title_is_stripped(self, tmp_path):
        """前後空白 strip — Gemini 偶爾吐多餘空白, 不該帶進 library 顯示."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.EXAM_PDF,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(
            json.dumps({"exam_title": "  材料力學  \n"}),
            encoding="utf-8",
        )
        assert _read_deck_title(store, rec.id) == "材料力學"

    def test_empty_exam_title_falls_through_to_deck_title(self, tmp_path):
        """exam_title 空字串 → falsy, 該退 deck_title (or 取真實有值的那個)."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(
            json.dumps({"exam_title": "", "deck_title": "fallback 標題"}),
            encoding="utf-8",
        )
        assert _read_deck_title(store, rec.id) == "fallback 標題"


class TestReadDeckTitleEdgeCases:
    """iter 121: _read_deck_title 三層防呆 + 邊角型別補測 — 保 try/except Exception
    swallow 對 UnicodeDecodeError / 0-byte 檔 / null title 都能 graceful 退 job_id,
    不該炸 500. 跟 iter 111-120 思路 (route 安全鎖)."""

    def test_binary_bytes_non_utf8_falls_back(self, tmp_path):
        """deck.json 是 binary (非 UTF-8) → read_text 該 UnicodeDecodeError,
        但 try/except Exception 仍吞, 退 job_id. 防 disk 損毀 / 誤寫 bin 進來."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        # \xff\xfe 是 UTF-16 BOM, 後面接 BMP 無法 UTF-8 解碼的 byte
        store.deck_path(rec.id).write_bytes(b"\xff\xfe\x00\x01\x02\x03binary garbage")
        assert _read_deck_title(store, rec.id) == rec.id

    def test_zero_byte_file_falls_back(self, tmp_path):
        """deck.json 是 0-byte 空檔 → json.loads('') JSONDecodeError → 退 job_id.
        ingest 中途斷電 / 半寫入情境."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_bytes(b"")
        assert _read_deck_title(store, rec.id) == rec.id

    def test_both_titles_null_falls_back_to_job_id(self, tmp_path):
        """exam_title / deck_title 都明確 null → None 是 falsy, or 鏈走到 job_id."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(
            json.dumps({"exam_title": None, "deck_title": None}),
            encoding="utf-8",
        )
        assert _read_deck_title(store, rec.id) == rec.id

    def test_whitespace_only_title_strips_to_empty(self, tmp_path):
        """全空白 title (空格 / tab / newline) — `"   "` 在 Python 是 truthy 不會被 or 跳過,
        然後 .strip() 變空字串. 文檔行為 (UI 顯示空白 deck_title, 不該炸).
        future 真要修可考慮: 把 falsy 從 truthy check 改成 .strip() 後 truthy check."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(
            json.dumps({"exam_title": "   \n\t  "}),
            encoding="utf-8",
        )
        assert _read_deck_title(store, rec.id) == ""

    def test_utf8_bom_prefix_is_handled(self, tmp_path):
        """deck.json 帶 UTF-8 BOM (\\xef\\xbb\\xbf) — read_text(encoding='utf-8')
        會保留 BOM 進 json string, json.loads 該 raise → except 退 job_id.
        (要支援 BOM 應用 encoding='utf-8-sig', 目前不支援 — graceful 退就好不該炸.)"""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        # BOM + valid JSON. read_text 把 BOM 當成字元留進 string, json.loads 該炸.
        store.deck_path(rec.id).write_bytes(
            b"\xef\xbb\xbf" + json.dumps({"exam_title": "BOM 開頭"}).encode("utf-8")
        )
        # 不檢具體值 — 行為要嘛 graceful 退 job_id (json.loads fail), 要嘛 BOM 解出
        # 進 exam_title; 都不該炸 500. 鎖「不會 raise」這條最小契約.
        result = _read_deck_title(store, rec.id)
        assert isinstance(result, str)
        assert result  # 非空 (job_id fallback 或合法 title)

    def test_deck_top_level_is_list_falls_back(self, tmp_path):
        """deck.json 頂層是 list (非 dict) → deck.get AttributeError, 修前 500.
        try 範圍擴大後該 graceful 退 job_id (見 ROUTINE_FINDINGS 2026-05-24)."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert _read_deck_title(store, rec.id) == rec.id

    def test_deck_top_level_is_string_falls_back(self, tmp_path):
        """deck.json 頂層是 JSON string (非 dict) → 同樣 deck.get 炸 → 退 job_id."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(json.dumps("just a string"), encoding="utf-8")
        assert _read_deck_title(store, rec.id) == rec.id

    def test_non_str_int_title_falls_back(self, tmp_path):
        """exam_title 是 int (Gemini 偶爾偏差 / 用戶手改錯) → or 鏈回 truthy 42,
        .strip() AttributeError, 修前 500. 擴大 try 後 graceful 退 job_id."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(
            json.dumps({"exam_title": 42}), encoding="utf-8",
        )
        assert _read_deck_title(store, rec.id) == rec.id

    def test_non_str_list_title_falls_back(self, tmp_path):
        """deck_title 是 list (truthy non-str) → .strip() 炸 → 退 job_id."""
        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(
            json.dumps({"deck_title": ["a", "b"]}), encoding="utf-8",
        )
        assert _read_deck_title(store, rec.id) == rec.id


class TestLibraryItemFields:
    """iter 115: LibraryItem 各欄位 — URL 格式 / srt_exists / source_type /
    mp4_size_bytes / deck_title 從 deck.json 抓. 補測試 = 安全鎖防 PR-3m 後
    任何 refactor 把欄位寫錯."""

    def test_artifact_url_format(self, client):
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        items = c.get("/library").json()["items"]
        assert items[0]["artifact_url"] == f"/jobs/{job_id}/artifacts/q1.mp4"

    def test_publish_url_format(self, client):
        # U-4: legacy /ui 退場 → 發布入口一律指 /app 發布站
        c, store = client
        _make_done_job(store, ["q1.mp4"])
        items = c.get("/library").json()["items"]
        assert items[0]["publish_url"] == "/app/"

    def test_mp4_size_bytes_passthrough(self, client):
        c, store = client
        _make_done_job(store, ["q1.mp4"])
        items = c.get("/library").json()["items"]
        assert items[0]["mp4_size_bytes"] == 1024 * 1024

    def test_source_type_passthrough(self, client):
        """source_type 直接從 JobRecord 透傳, 給前端依類型 filter."""
        c, store = client
        _make_done_job(store, ["q1.mp4"])
        items = c.get("/library").json()["items"]
        assert items[0]["source_type"] == "document"

    def test_deck_title_from_deck_json(self, client):
        """deck_title 走 _read_deck_title — 真有 deck.json 時該抓 exam_title."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        store.deck_path(job_id).write_text(
            json.dumps({"exam_title": "中考 2026"}),
            encoding="utf-8",
        )
        items = c.get("/library").json()["items"]
        assert items[0]["deck_title"] == "中考 2026"

    def test_deck_title_fallback_to_job_id_when_no_deck(self, client):
        """沒 deck.json → deck_title = job_id (防呆)."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        items = c.get("/library").json()["items"]
        assert items[0]["deck_title"] == job_id

    def test_srt_exists_true_when_file_present(self, client):
        """同名 .srt 存在 → srt_exists=True, 上傳能帶字幕."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        (store.artifacts_dir(job_id) / "q1.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        items = c.get("/library").json()["items"]
        assert items[0]["srt_exists"] is True

    def test_srt_exists_false_when_file_absent(self, client):
        """沒 .srt → False, 前端可顯示 (無字幕) badge."""
        c, store = client
        _make_done_job(store, ["q1.mp4"])
        items = c.get("/library").json()["items"]
        assert items[0]["srt_exists"] is False

    def test_total_matches_items_length(self, client):
        """total 該等於 items 數, 不該漂移."""
        c, store = client
        _make_done_job(store, ["q1.mp4", "q2.mp4"])
        _make_done_job(store, ["q3.mp4"])
        body = c.get("/library").json()
        assert body["total"] == len(body["items"]) == 3


class TestLibraryYoutubeField:
    """iter 115: youtube 欄位透傳 — 沒上傳 / 各狀態 / 帶 video_id 都該對應出來."""

    def test_youtube_none_when_no_upload(self, client):
        """沒上傳過 → youtube=None, 前端顯示 [上傳] 按鈕."""
        c, store = client
        _make_done_job(store, ["q1.mp4"])
        items = c.get("/library").json()["items"]
        assert items[0]["youtube"] is None

    def test_youtube_done_state_passthrough(self, client):
        """上傳成功 → state=done + video_id + url 透傳, 前端顯示 [看影片]."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        store.set_youtube_upload(job_id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.DONE,
            video_id="abc123",
            url="https://youtube.com/watch?v=abc123",
            title="期中考第一題",
        ))
        items = c.get("/library").json()["items"]
        yt = items[0]["youtube"]
        assert yt["state"] == "done"
        assert yt["video_id"] == "abc123"
        assert yt["url"] == "https://youtube.com/watch?v=abc123"
        assert yt["title"] == "期中考第一題"

    def test_youtube_failed_state_passthrough(self, client):
        """上傳失敗 → state=failed + error, 前端顯示 [重試] 按鈕."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        store.set_youtube_upload(job_id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.FAILED,
            error="quota exceeded",
        ))
        yt = c.get("/library").json()["items"][0]["youtube"]
        assert yt["state"] == "failed"
        assert yt["error"] == "quota exceeded"

    def test_youtube_uploading_state_passthrough(self, client):
        """上傳中 → progress_percent 透傳, 前端顯示進度條."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        store.set_youtube_upload(job_id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.UPLOADING,
            progress_percent=42,
        ))
        yt = c.get("/library").json()["items"][0]["youtube"]
        assert yt["state"] == "uploading"
        assert yt["progress_percent"] == 42

    def test_youtube_only_for_matching_artifact(self, client):
        """multi-artifact job: 只有 q1.mp4 上傳, q2.mp4 該回 youtube=None
        (youtube_uploads 是 dict[artifact_name], 跨 artifact 不該漏氣)."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4", "q2.mp4"])
        store.set_youtube_upload(job_id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.DONE, video_id="zzz",
        ))
        items = c.get("/library").json()["items"]
        by_name = {i["artifact_name"]: i for i in items}
        assert by_name["q1.mp4"]["youtube"]["video_id"] == "zzz"
        assert by_name["q2.mp4"]["youtube"] is None
