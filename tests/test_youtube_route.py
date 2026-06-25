"""server.routes.youtube HTTP route 測試 (iter 116).

server/routes/youtube.py 三個 HTTP endpoint (GET /youtube_meta /
POST /publish / GET /youtube_status) 從 PR-3f 上線後沒對應 route-level
測試 — test_youtube_helper.py 只覆蓋 core.youtube auto_youtube_meta /
_seconds_to_hhmmss 純函式. 任何 refactor 不小心動 _require_artifact
path 防護 / state machine 409 / metadata 覆蓋邏輯 → 直接上線, 跟 iter
111-115 同思路 (安全鎖).

Mock 策略:
- _do_publish: 整個 monkeypatch 成 noop async, 避免真打 OAuth + YouTube API
- core.publish_artifact / OAuthBootstrapRequired: _do_publish 已 noop,
  不用個別 mock
- core.auto_youtube_meta: 信任 test_youtube_helper.py 既有覆蓋, 不重 mock,
  直接餵真 deck.json 走完整路徑
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import server.routes.youtube as youtube_mod
from server.jobs import JobStore, get_default_store
from server.main import create_app
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
def client(tmp_path, monkeypatch):
    """乾淨 TestClient + 隔離 JobStore + _do_publish noop.

    monkeypatch _do_publish: publish endpoint 走 asyncio.create_task(_do_publish(...)),
    若不 mock 會真 import core.publish_artifact 撈 OAuth credentials → 炸.
    替成 noop async 後 route handler 在 create_task 之前已 set UPLOADING,
    可驗 state 寫入而不依賴外部 service.
    """
    async def _noop_publish(*args, **kwargs):
        pass

    monkeypatch.setattr(youtube_mod, "_do_publish", _noop_publish)

    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


def _make_done_job(store: JobStore, artifact_names: list[str],
                   source_type: SourceType = SourceType.EXAM_PDF) -> str:
    """建一個 state=done 的 job + 真 artifact 檔 (路徑必須存在 _require_artifact 才不 404)."""
    rec = store.create(CreateJobRequest(
        source_type=source_type,
        source=JobSource(path="/tmp/fake.pdf"),
        options=JobOptions(require_review=False),
    ))
    artifacts_dir = store.artifacts_dir(rec.id)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for name in artifact_names:
        target = artifacts_dir / name
        target.write_bytes(b"fake mp4")
        artifacts.append(Artifact(
            name=name, path=str(target), size_bytes=8, kind="mp4",
        ))
    store.update(rec.id, state=JobState.DONE, artifacts=artifacts)
    return rec.id


def _write_deck(store: JobStore, job_id: str, deck: dict) -> None:
    deck_path = store.deck_path(job_id)
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")


# ---------- GET /youtube_meta ----------

class TestYoutubeMetaEndpoint:
    """GET /jobs/{id}/artifacts/{name}/youtube_meta — 預填 metadata 產生."""

    def test_returns_meta_for_valid_artifact(self, client):
        """artifact + deck.json 都在 → auto_youtube_meta 走過, 回完整 dict."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        _write_deck(store, job_id, {
            "exam_title": "材料力學期中考",
            "problems": [{
                "id": "q1",
                "number": "第 1 題",
                "problem": "計算 F=ma 在 m=2 a=3 時的 F.",
                "steps": [
                    {"_section": "觀念切入", "narration": "牛頓第二定律。"},
                    {"_section": "代入計算", "narration": "F=2x3=6 N。"},
                ],
            }],
        })
        resp = c.get(f"/jobs/{job_id}/artifacts/q1.mp4/youtube_meta")
        assert resp.status_code == 200
        body = resp.json()
        # auto_youtube_meta 該帶 5 個 key
        assert set(body.keys()) >= {"title", "description", "tags", "privacy", "category"}
        assert "材料力學期中考" in body["title"]
        assert "第 1 題" in body["title"]
        assert body["privacy"] == "unlisted"
        assert body["category"] == "27"

    def test_returns_done_metadata_directly(self, client):
        """已 DONE state → 直接回 existing model_dump, 不重 call auto_youtube_meta.

        為什麼這條重要: 已上傳的影片不該被 deck 編輯改動覆蓋 (user 在 YT 上可能改過標題).
        """
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        # 故意不寫 deck.json, 驗證走 DONE 短路時不該炸
        done_upload = YoutubeUpload(
            state=YoutubeUploadState.DONE,
            title="已上傳的客製標題",
            description="user 在前端編過的",
            tags=["custom"],
            privacy="public",
            video_id="abc123",
            url="https://youtu.be/abc123",
        )
        store.set_youtube_upload(job_id, "q1.mp4", done_upload)
        resp = c.get(f"/jobs/{job_id}/artifacts/q1.mp4/youtube_meta")
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "已上傳的客製標題"
        assert body["video_id"] == "abc123"
        assert body["state"] == "done"  # model_dump 帶 state field

    def test_no_deck_json_falls_back_to_filename(self, client):
        """artifact 存在但 deck.json 不存在 → 退化成「檔名當標題」的最小預填 (不 404)。

        html_animation 這類非 deck 來源沒有 deck.json, 不該被擋住上傳; 退化預填讓
        使用者在前端自行編輯其餘欄位。"""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        # 不寫 deck.json
        resp = c.get(f"/jobs/{job_id}/artifacts/q1.mp4/youtube_meta")
        assert resp.status_code == 200
        meta = resp.json()
        assert meta["title"] == "q1"
        assert meta["privacy"] == "unlisted"

    def test_existing_pending_overwrites_auto_meta(self, client):
        """pending state 帶 user 編過的 title/tags → 覆蓋 auto_youtube_meta 結果.

        為什麼: user 上次跑 publish 失敗或還沒按, 在前端編過的 metadata 該保留,
        不該被 auto-gen 蓋掉.
        """
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        _write_deck(store, job_id, {
            "exam_title": "自動產生標題",
            "problems": [{"id": "q1", "number": "第 1 題",
                          "problem": "test", "steps": []}],
        })
        # 模擬 user 編過的 pending record
        pending = YoutubeUpload(
            state=YoutubeUploadState.PENDING,
            title="user 編過的標題",
            tags=["user", "custom"],
            privacy="public",
        )
        store.set_youtube_upload(job_id, "q1.mp4", pending)

        body = c.get(f"/jobs/{job_id}/artifacts/q1.mp4/youtube_meta").json()
        # title / tags / privacy 該保留 user 編過的
        assert body["title"] == "user 編過的標題"
        assert body["tags"] == ["user", "custom"]
        assert body["privacy"] == "public"

    def test_failed_state_also_regenerates_with_overwrite(self, client):
        """FAILED state 跟 PENDING 一樣走 overwrite 路徑 (line 84 沒限定 PENDING).

        為什麼: 上傳失敗該讓 user 重編後再傳, 不該卡 DONE 短路也不該丟掉 user 編輯.
        """
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        _write_deck(store, job_id, {
            "exam_title": "原標題",
            "problems": [{"id": "q1", "number": "第 1 題",
                          "problem": "test", "steps": []}],
        })
        failed = YoutubeUpload(
            state=YoutubeUploadState.FAILED,
            title="user 修過的標題",
            error="網路斷線",
        )
        store.set_youtube_upload(job_id, "q1.mp4", failed)
        body = c.get(f"/jobs/{job_id}/artifacts/q1.mp4/youtube_meta").json()
        # 不該回 DONE 短路 (因為 state=FAILED), 該走 auto_youtube_meta + user 覆蓋
        assert body["title"] == "user 修過的標題"


# ---------- _require_artifact 驗證 (透過 youtube_meta + publish 黑盒測) ----------

class TestRequireArtifactValidation:
    """_require_artifact helper 透過 GET /youtube_meta 黑盒測 path 防護 + 副檔限制.

    youtube_status 不走這條, 該另測 (見 TestYoutubeStatusEndpoint).
    """

    def test_nonexistent_job_returns_404(self, client):
        c, _ = client
        resp = c.get("/jobs/nonexistent_id/artifacts/q1.mp4/youtube_meta")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    def test_path_traversal_dotdot_rejected(self, client):
        """name 含 .. → 400, 防止逃出 artifacts_dir."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        resp = c.get(f"/jobs/{job_id}/artifacts/..q1.mp4/youtube_meta")
        # _require_artifact 內 `if ".." in name` 命中 → 400
        assert resp.status_code == 400
        assert "非法" in resp.json()["detail"]

    def test_artifact_file_missing_returns_404(self, client):
        """name 合法但檔不存在 → 404 (不是上面 path 防護命中, 是 target.exists() check)."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        resp = c.get(f"/jobs/{job_id}/artifacts/q99.mp4/youtube_meta")
        assert resp.status_code == 404
        assert "q99.mp4" in resp.json()["detail"]

    def test_wrong_extension_rejected(self, client):
        """非 .mp4 副檔名 → 400, 防 user 傳 .txt / .srt 等."""
        c, store = client
        job_id = _make_done_job(store, ["q1.srt"])
        # q1.srt 真存在 (上面建檔), 但 _require_artifact 看 suffix 該 400
        resp = c.get(f"/jobs/{job_id}/artifacts/q1.srt/youtube_meta")
        assert resp.status_code == 400
        assert ".mp4" in resp.json()["detail"]


# ---------- POST /publish ----------

class TestPublishEndpoint:
    """POST /jobs/{id}/artifacts/{name}/publish — 觸發背景上傳."""

    def test_publish_starts_upload(self, client):
        """第一次 publish → 202 + 寫 UPLOADING state + title 等 metadata 落盤."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        resp = c.post(
            f"/jobs/{job_id}/artifacts/q1.mp4/publish",
            json={
                "title": "test title",
                "description": "desc",
                "tags": ["tag1", "tag2"],
                "privacy": "unlisted",
                "category": "27",
            },
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["state"] == "uploading"
        assert body["title"] == "test title"
        assert body["tags"] == ["tag1", "tag2"]
        assert body["progress_percent"] == 0

        # store 該寫入相同 state
        rec = store.get(job_id)
        assert rec.youtube_uploads["q1.mp4"].state == YoutubeUploadState.UPLOADING
        assert rec.youtube_uploads["q1.mp4"].title == "test title"

    def test_publish_already_uploading_returns_409(self, client):
        """重複 publish 同一個 artifact → 409 (跟 in-flight task 衝突)."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        # 先注入 UPLOADING state
        store.set_youtube_upload(job_id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.UPLOADING,
            progress_percent=42,
        ))
        resp = c.post(
            f"/jobs/{job_id}/artifacts/q1.mp4/publish",
            json={"title": "重複呼叫"},
        )
        assert resp.status_code == 409
        assert "上傳中" in resp.json()["detail"]
        assert "42" in resp.json()["detail"]  # progress 該帶在訊息

    def test_publish_already_done_returns_409(self, client):
        """已 DONE → 409, 不該蓋掉既有上傳 (要重傳該另外開機制).

        為什麼這條重要: 學術影片上傳是高成本不可逆 (對 YouTube quota / 觀看數 / 連結),
        不該被前端誤觸再次傳.
        """
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        store.set_youtube_upload(job_id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.DONE,
            video_id="xyz789",
            url="https://youtu.be/xyz789",
        ))
        resp = c.post(
            f"/jobs/{job_id}/artifacts/q1.mp4/publish",
            json={"title": "想重傳"},
        )
        assert resp.status_code == 409
        assert "已上傳" in resp.json()["detail"]
        assert "xyz789" in resp.json()["detail"]

    def test_publish_failed_can_retry(self, client):
        """FAILED state 該可重 publish (不該 409, 不卡死).

        為什麼: 上次 OAuth 失效 / 網路斷, 重新獲得授權後 user 該能重觸發.
        """
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        store.set_youtube_upload(job_id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.FAILED,
            error="OAuth expired",
        ))
        resp = c.post(
            f"/jobs/{job_id}/artifacts/q1.mp4/publish",
            json={"title": "重試"},
        )
        assert resp.status_code == 202
        # 重新走 set_youtube_upload, 蓋掉舊 FAILED, error 清空
        rec = store.get(job_id)
        upload = rec.youtube_uploads["q1.mp4"]
        assert upload.state == YoutubeUploadState.UPLOADING
        assert upload.error is None

    def test_publish_minimal_request_uses_defaults(self, client):
        """只給必填 title, 其他走 PublishRequest 預設 (description='' / tags=[] / unlisted / 27)."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        resp = c.post(
            f"/jobs/{job_id}/artifacts/q1.mp4/publish",
            json={"title": "minimal"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["title"] == "minimal"
        assert body["description"] == ""
        assert body["tags"] == []
        assert body["privacy"] == "unlisted"
        assert body["category"] == "27"

    def test_publish_missing_title_returns_422(self, client):
        """PublishRequest title 必填, 缺 → pydantic v2 422."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        resp = c.post(
            f"/jobs/{job_id}/artifacts/q1.mp4/publish",
            json={"description": "沒 title"},
        )
        assert resp.status_code == 422

    def test_publish_path_traversal_rejected(self, client):
        """publish 也走 _require_artifact, path injection 該擋 (不單只 youtube_meta)."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        resp = c.post(
            f"/jobs/{job_id}/artifacts/..%2Fq1.mp4/publish",
            json={"title": "x"},
        )
        # FastAPI path converter 不解 %2F → name="..q1.mp4" 含 .. → 400
        # 或被 routing 解成 405/404, 任一非 200/202 都算擋住
        assert resp.status_code != 202


# ---------- GET /youtube_status ----------

class TestYoutubeStatusEndpoint:
    """GET /jobs/{id}/artifacts/{name}/youtube_status — 輪詢狀態."""

    def test_status_no_upload_returns_blank(self, client):
        """從沒呼叫 publish 過的 artifact → 回空白 YoutubeUpload (state=pending).

        為什麼: 前端輪詢時不該因為 user 還沒按上傳就 404, 該回空白讓 UI 顯示 'pending'.
        """
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        resp = c.get(f"/jobs/{job_id}/artifacts/q1.mp4/youtube_status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "pending"
        assert body["title"] == ""
        assert body["progress_percent"] == 0
        assert body["video_id"] is None

    def test_status_returns_existing_upload(self, client):
        """有 upload record → 透傳所有 field."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4"])
        store.set_youtube_upload(job_id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.DONE,
            title="ok",
            video_id="vid_abc",
            url="https://youtu.be/vid_abc",
            progress_percent=100,
            caption_id="cap_001",
        ))
        body = c.get(f"/jobs/{job_id}/artifacts/q1.mp4/youtube_status").json()
        assert body["state"] == "done"
        assert body["video_id"] == "vid_abc"
        assert body["url"] == "https://youtu.be/vid_abc"
        assert body["progress_percent"] == 100
        assert body["caption_id"] == "cap_001"

    def test_status_job_not_found_returns_404(self, client):
        """job 不存在 → 404 (這條跟 _require_artifact 那邊邏輯獨立, 在 route 內直接 store.get).

        為什麼分開測: youtube_status 不走 _require_artifact (line 211-213
        直接 store.get + youtube_uploads.get), 不會檢 artifact 副檔名 / 路徑, 該獨立驗.
        """
        c, _ = client
        resp = c.get("/jobs/nonexistent/artifacts/q1.mp4/youtube_status")
        assert resp.status_code == 404
        assert "不存在" in resp.json()["detail"]

    def test_status_does_not_check_artifact_existence(self, client):
        """youtube_status 不走 _require_artifact, 故 artifact 檔不存在仍回 blank (不 404).

        Documented behavior: 前端在 publish 觸發瞬間就可以開始輪詢, 即使
        artifact 暫時不在 disk (例如被搬走 / 還沒生), 仍回 pending 空白.
        若日後改成 strict check (走 _require_artifact), 此 test 該打掉重寫.
        """
        c, store = client
        job_id = _make_done_job(store, [])  # 空 artifacts list
        # 沒建 q_ghost.mp4 檔, 但仍 200
        resp = c.get(f"/jobs/{job_id}/artifacts/q_ghost.mp4/youtube_status")
        assert resp.status_code == 200
        assert resp.json()["state"] == "pending"

    def test_status_multi_artifact_isolation(self, client):
        """同 job 兩個 artifact: q1 已 DONE, q2 從沒 publish → 各自獨立 state."""
        c, store = client
        job_id = _make_done_job(store, ["q1.mp4", "q2.mp4"])
        store.set_youtube_upload(job_id, "q1.mp4", YoutubeUpload(
            state=YoutubeUploadState.DONE,
            video_id="q1_video",
        ))
        body_q1 = c.get(f"/jobs/{job_id}/artifacts/q1.mp4/youtube_status").json()
        body_q2 = c.get(f"/jobs/{job_id}/artifacts/q2.mp4/youtube_status").json()
        assert body_q1["state"] == "done"
        assert body_q1["video_id"] == "q1_video"
        assert body_q2["state"] == "pending"
        assert body_q2["video_id"] is None
