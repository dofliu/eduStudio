"""server.routes.jobs 邊角 HTTP route 測試 (iter 117).

server/routes/jobs.py 內四個 endpoint 從 PR-3a~PR-4a 上線後沒對應
route-level 測試:
  - GET    /jobs/{id}/draft               (取 deck.json)
  - PUT    /jobs/{id}/draft               (覆寫 deck.json + 狀態 guard)
  - GET    /jobs/{id}/log                 (jsonl tail)
  - POST   /jobs/{id}/sections/{sec}/render  (單章重 render)
  - GET    /jobs/{id}/artifacts/{name}    (artifact 下載 + path 防護)

接 iter 111-116 安全鎖補測思路 — 任何 refactor 不小心動 state machine
guard / path traversal 防護 / deck.json 內 section 查找邏輯 → 直接上線.

Mock 策略:
- schedule_section_render: monkeypatch 成 noop 避免真跑 ffmpeg / Gemini
- 其他 route 純 disk I/O + state 檢查, 不需 mock
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import server.routes.jobs as jobs_mod
from server.jobs import JobStore, get_default_store
from server.main import create_app
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """乾淨 TestClient + 隔離 JobStore + schedule_* noop."""
    monkeypatch.setattr(jobs_mod, "schedule_section_render",
                        lambda store, jid, sec: None)
    monkeypatch.setattr(jobs_mod, "schedule_render", lambda store, jid: None)
    monkeypatch.setattr(jobs_mod, "schedule_job", lambda store, jid: None)

    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


def _new_job(store: JobStore, state: JobState = JobState.AWAITING_REVIEW) -> str:
    rec = store.create(CreateJobRequest(
        source_type=SourceType.DOCUMENT,
        source=JobSource(path="/tmp/x.pdf"),
        options=JobOptions(),
    ))
    store.update(rec.id, state=state)
    return rec.id


def _write_deck(store: JobStore, job_id: str, deck: dict) -> None:
    deck_path = store.deck_path(job_id)
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    deck_path.write_text(json.dumps(deck, ensure_ascii=False), encoding="utf-8")


# ---------- GET /jobs/{id}/draft ----------

class TestGetDraftEndpoint:
    """GET /jobs/{id}/draft — 純讀 deck.json, 不檢 job state."""

    def test_returns_deck_when_exists(self, client):
        c, store = client
        jid = _new_job(store)
        deck = {"deck_title": "材力", "sections": [{"id": "s1", "title": "A"}]}
        _write_deck(store, jid, deck)
        r = c.get(f"/jobs/{jid}/draft")
        assert r.status_code == 200
        assert r.json() == deck

    def test_no_deck_file_returns_404(self, client):
        """job 存在但 deck.json 沒生 (ingest 還沒完 / 失敗) → 404."""
        c, store = client
        jid = _new_job(store, state=JobState.INGESTING)
        r = c.get(f"/jobs/{jid}/draft")
        assert r.status_code == 404

    def test_nonexistent_job_also_404(self, client):
        """nonexistent job 走同條 (deck_path 不會炸, 直接看檔在不在)."""
        c, _ = client
        r = c.get("/jobs/nope/draft")
        assert r.status_code == 404


# ---------- PUT /jobs/{id}/draft ----------

class TestUpdateDraftEndpoint:
    """PUT /jobs/{id}/draft — state guard (僅 awaiting_review/failed/done 可改).

    白名單之外的狀態 (pending/ingesting/rendering) 必須 409, 避免 race
    condition (例: rendering 中改 deck 跟在跑的渲染衝突).
    """

    def test_nonexistent_job_returns_404(self, client):
        c, _ = client
        r = c.put("/jobs/nope/draft", json={"deck": {"a": 1}})
        assert r.status_code == 404

    def test_awaiting_review_allowed(self, client):
        c, store = client
        jid = _new_job(store, state=JobState.AWAITING_REVIEW)
        deck = {"sections": [{"id": "s1"}]}
        r = c.put(f"/jobs/{jid}/draft", json={"deck": deck})
        assert r.status_code == 200
        # 落盤驗證
        saved = json.loads(store.deck_path(jid).read_text(encoding="utf-8"))
        assert saved == deck

    def test_failed_allowed_pr3j(self, client):
        """PR-3j: failed 狀態可改 deck 再 approve retry (避免從頭跑 ingest)."""
        c, store = client
        jid = _new_job(store, state=JobState.FAILED)
        deck = {"sections": [{"id": "s2"}]}
        r = c.put(f"/jobs/{jid}/draft", json={"deck": deck})
        assert r.status_code == 200
        saved = json.loads(store.deck_path(jid).read_text(encoding="utf-8"))
        assert saved == deck

    def test_done_allowed_pr4a(self, client):
        """PR-4a: done 狀態可改 deck (給 section render 用)."""
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        r = c.put(f"/jobs/{jid}/draft", json={"deck": {"x": 1}})
        assert r.status_code == 200

    def test_pending_rejected(self, client):
        c, store = client
        jid = _new_job(store, state=JobState.PENDING)
        r = c.put(f"/jobs/{jid}/draft", json={"deck": {}})
        assert r.status_code == 409
        # 不該落盤
        assert not store.deck_path(jid).exists()

    def test_ingesting_rejected(self, client):
        c, store = client
        jid = _new_job(store, state=JobState.INGESTING)
        r = c.put(f"/jobs/{jid}/draft", json={"deck": {}})
        assert r.status_code == 409

    def test_rendering_rejected(self, client):
        """race-condition 防護 — rendering 中改 deck 跟在跑的渲染會撞."""
        c, store = client
        jid = _new_job(store, state=JobState.RENDERING)
        r = c.put(f"/jobs/{jid}/draft", json={"deck": {}})
        assert r.status_code == 409

    def test_missing_deck_field_returns_422(self, client):
        """pydantic UpdateDeckRequest deck 是必填."""
        c, store = client
        jid = _new_job(store, state=JobState.AWAITING_REVIEW)
        r = c.put(f"/jobs/{jid}/draft", json={})
        assert r.status_code == 422

    def test_unicode_chinese_roundtrip(self, client):
        """deck.json 寫入用 ensure_ascii=False, 中文不該變 \\uXXXX 也不該丟資訊."""
        c, store = client
        jid = _new_job(store, state=JobState.AWAITING_REVIEW)
        deck = {"deck_title": "材料力學 — 第一章", "sections": [
            {"id": "intro", "title": "概念導讀"},
        ]}
        r = c.put(f"/jobs/{jid}/draft", json={"deck": deck})
        assert r.status_code == 200
        raw = store.deck_path(jid).read_text(encoding="utf-8")
        # 原字保留, 不被 ASCII escape
        assert "材料力學" in raw
        assert "\\u6750" not in raw


# ---------- GET /jobs/{id}/log ----------

class TestJobLogEndpoint:
    """GET /jobs/{id}/log — 讀 jsonl tail. tail 範圍 1~2000 邊界檢查."""

    def test_nonexistent_job_returns_404(self, client):
        c, _ = client
        r = c.get("/jobs/nope/log")
        assert r.status_code == 404

    def test_no_log_file_returns_empty_entries(self, client):
        """log.jsonl 不存在不該 404 (read_job_log 該回空 list)."""
        c, store = client
        jid = _new_job(store)
        r = c.get(f"/jobs/{jid}/log")
        assert r.status_code == 200
        assert r.json() == {"entries": []}

    def test_reads_jsonl_entries(self, client):
        """寫真 jsonl, 該 parse 成 dict list."""
        c, store = client
        jid = _new_job(store)
        log_path = store.job_dir(jid) / "log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            '{"level":"INFO","msg":"hi"}\n{"level":"WARN","msg":"slow"}\n',
            encoding="utf-8",
        )
        r = c.get(f"/jobs/{jid}/log")
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert len(entries) == 2
        assert entries[0]["msg"] == "hi"
        assert entries[1]["level"] == "WARN"

    def test_malformed_line_falls_back_to_raw(self, client):
        """壞行不該炸, read_job_log 該回 {level: RAW, msg: line}."""
        c, store = client
        jid = _new_job(store)
        log_path = store.job_dir(jid) / "log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            '{"level":"INFO","msg":"ok"}\nnot json at all\n',
            encoding="utf-8",
        )
        r = c.get(f"/jobs/{jid}/log")
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert len(entries) == 2
        assert entries[1]["level"] == "RAW"
        assert "not json" in entries[1]["msg"]

    def test_tail_param_limits_entries(self, client):
        """tail=2 該只回末 2 筆."""
        c, store = client
        jid = _new_job(store)
        log_path = store.job_dir(jid) / "log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            "\n".join(f'{{"i":{i}}}' for i in range(10)) + "\n",
            encoding="utf-8",
        )
        r = c.get(f"/jobs/{jid}/log?tail=2")
        assert r.status_code == 200
        entries = r.json()["entries"]
        assert [e["i"] for e in entries] == [8, 9]

    def test_tail_zero_rejected(self, client):
        c, store = client
        jid = _new_job(store)
        r = c.get(f"/jobs/{jid}/log?tail=0")
        assert r.status_code == 400

    def test_tail_too_large_rejected(self, client):
        c, store = client
        jid = _new_job(store)
        r = c.get(f"/jobs/{jid}/log?tail=2001")
        assert r.status_code == 400


# ---------- POST /jobs/{id}/sections/{section_id}/render ----------

class TestSectionRenderEndpoint:
    """POST /jobs/{id}/sections/{section_id}/render — PR-4a 單章重 render.

    state 必須 done/failed (其他狀態 race / 前置未完). deck.json + section_id
    都該存在 — _deck_has_section_id 雙 schema 查找 (problems v1 + sections 新)."""

    def test_nonexistent_job_returns_404(self, client):
        c, _ = client
        r = c.post("/jobs/nope/sections/s1/render")
        assert r.status_code == 404

    def test_awaiting_review_rejected(self, client):
        """awaiting_review 還沒 render 過, 不能 section render."""
        c, store = client
        jid = _new_job(store, state=JobState.AWAITING_REVIEW)
        r = c.post(f"/jobs/{jid}/sections/s1/render")
        assert r.status_code == 409

    def test_rendering_rejected(self, client):
        c, store = client
        jid = _new_job(store, state=JobState.RENDERING)
        r = c.post(f"/jobs/{jid}/sections/s1/render")
        assert r.status_code == 409

    def test_done_without_deck_returns_404(self, client):
        """done 卻沒 deck.json (人工刪掉?) → 404, 不該 500."""
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        r = c.post(f"/jobs/{jid}/sections/s1/render")
        assert r.status_code == 404

    def test_done_unknown_section_returns_404(self, client):
        """deck.json 在但找不到該 section_id → 404."""
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        _write_deck(store, jid, {"sections": [{"id": "intro"}, {"id": "hooke"}]})
        r = c.post(f"/jobs/{jid}/sections/ghost/render")
        assert r.status_code == 404

    def test_done_deck_schema_section_id_match(self, client, monkeypatch):
        """deck schema (sections[].id) 命中該 schedule_section_render."""
        c, store = client
        called: dict = {}
        monkeypatch.setattr(
            jobs_mod, "schedule_section_render",
            lambda store, jid, sec: called.setdefault("args", (jid, sec)),
        )
        jid = _new_job(store, state=JobState.DONE)
        _write_deck(store, jid, {"sections": [{"id": "intro", "title": "x"}]})
        r = c.post(f"/jobs/{jid}/sections/intro/render")
        assert r.status_code == 200
        assert called["args"] == (jid, "intro")

    def test_failed_v1_problems_schema_section_match(self, client, monkeypatch):
        """v1 exam schema (problems[].id) 也該命中 _deck_has_section_id."""
        c, store = client
        called: dict = {}
        monkeypatch.setattr(
            jobs_mod, "schedule_section_render",
            lambda store, jid, sec: called.setdefault("args", (jid, sec)),
        )
        jid = _new_job(store, state=JobState.FAILED)
        _write_deck(store, jid, {"problems": [{"id": "q1", "problem": "..."}]})
        r = c.post(f"/jobs/{jid}/sections/q1/render")
        assert r.status_code == 200
        assert called["args"] == (jid, "q1")


# ---------- GET /jobs/{id}/artifacts/{name} ----------

class TestArtifactDownload:
    """GET /jobs/{id}/artifacts/{name} — path traversal 防護 + file 存在檢查."""

    def test_nonexistent_job_returns_404(self, client):
        c, _ = client
        r = c.get("/jobs/nope/artifacts/q1.mp4")
        assert r.status_code == 404

    def test_path_traversal_dotdot_blocked(self, client):
        """`..` 在檔名該 400 (route 內字串檢查, 不靠 OS)."""
        c, store = client
        jid = _new_job(store)
        # `..mp4` 也含 `..` 子串 — 該被擋. (邊界寬鬆比放行安全)
        r = c.get(f"/jobs/{jid}/artifacts/..mp4")
        assert r.status_code == 400

    def test_backslash_in_name_blocked(self, client):
        """Windows-style `\\` 也該擋 (route 同時防 / 跟 \\)."""
        c, store = client
        jid = _new_job(store)
        # URL 內帶字面 backslash 走 %5C
        r = c.get(f"/jobs/{jid}/artifacts/sub%5Cfile.mp4")
        assert r.status_code == 400

    def test_missing_file_returns_404(self, client):
        """檔名合法 + artifacts/ 目錄存在但檔不在 → 404."""
        c, store = client
        jid = _new_job(store)
        store.artifacts_dir(jid).mkdir(parents=True, exist_ok=True)
        r = c.get(f"/jobs/{jid}/artifacts/missing.mp4")
        assert r.status_code == 404

    def test_directory_target_returns_404(self, client):
        """target 解到目錄 (而非檔案) → 404, 不該回 listing 也不該 500."""
        c, store = client
        jid = _new_job(store)
        artifacts = store.artifacts_dir(jid)
        artifacts.mkdir(parents=True, exist_ok=True)
        (artifacts / "subdir").mkdir()
        r = c.get(f"/jobs/{jid}/artifacts/subdir")
        assert r.status_code == 404

    def test_valid_artifact_serves_bytes(self, client):
        """合法檔該 byte-perfect 還原."""
        c, store = client
        jid = _new_job(store)
        artifacts = store.artifacts_dir(jid)
        artifacts.mkdir(parents=True, exist_ok=True)
        payload = b"\x00\x01fake mp4 bytes\xff"
        (artifacts / "q1.mp4").write_bytes(payload)
        r = c.get(f"/jobs/{jid}/artifacts/q1.mp4")
        assert r.status_code == 200
        assert r.content == payload


# ---------- GET /jobs/{id}/versions + /versions/{v}/artifacts/{name} ----------

def _archive_version(store, job_id, **files):
    """把 files 寫進 artifacts/ 後呼叫 archive_artifacts → 產一個歷史版本."""
    d = store.artifacts_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (d / name.replace("__", ".")).write_bytes(data)
    return store.archive_artifacts(job_id)


class TestListArtifactVersions:
    """GET /jobs/{id}/versions — 列歷次歸檔舊版 (F9-4 slice ②)."""

    def test_nonexistent_job_returns_404(self, client):
        c, _ = client
        r = c.get("/jobs/nope/versions")
        assert r.status_code == 404

    def test_no_versions_returns_empty_list(self, client):
        """沒重 render 過 → 空 list, 非 404 (新 job 正常)."""
        c, store = client
        jid = _new_job(store)
        r = c.get(f"/jobs/{jid}/versions")
        assert r.status_code == 200
        assert r.json() == {"versions": []}

    def test_lists_versions_newest_first(self, client):
        """多版本由新到舊排, 每個附 metadata."""
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        _archive_version(store, jid, final__mp4=b"v1")
        _archive_version(store, jid, final__mp4=b"v2")
        r = c.get(f"/jobs/{jid}/versions")
        assert r.status_code == 200
        versions = r.json()["versions"]
        assert [v["version"] for v in versions] == [2, 1]
        v2 = versions[0]
        assert v2["path"] == "artifact_history/v2"
        assert v2["created_at"] and v2["archived_at"]
        a = v2["artifacts"][0]
        assert a["name"] == "final.mp4"
        assert a["kind"] == "mp4"
        assert a["url"] == f"/jobs/{jid}/versions/2/artifacts/final.mp4"

    def test_note_carried_through(self, client):
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        d = store.artifacts_dir(jid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "final.mp4").write_bytes(b"v1")
        store.archive_artifacts(jid, note="重 render 前歸檔")
        r = c.get(f"/jobs/{jid}/versions")
        assert r.json()["versions"][0]["note"] == "重 render 前歸檔"


class TestDownloadVersionedArtifact:
    """GET /jobs/{id}/versions/{v}/artifacts/{name} — 下載指定版本 (F9-4)."""

    def test_nonexistent_job_returns_404(self, client):
        c, _ = client
        r = c.get("/jobs/nope/versions/1/artifacts/final.mp4")
        assert r.status_code == 404

    def test_serves_archived_bytes(self, client):
        """歷史版本檔該 byte-perfect 還原 (回滾 / 比對基礎)."""
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        _archive_version(store, jid, final__mp4=b"good-old-version")
        r = c.get(f"/jobs/{jid}/versions/1/artifacts/final.mp4")
        assert r.status_code == 200
        assert r.content == b"good-old-version"

    def test_each_version_isolated(self, client):
        """v1 / v2 各自回自己的內容, 不互相蓋."""
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        _archive_version(store, jid, final__mp4=b"version-one")
        _archive_version(store, jid, final__mp4=b"version-two")
        r1 = c.get(f"/jobs/{jid}/versions/1/artifacts/final.mp4")
        r2 = c.get(f"/jobs/{jid}/versions/2/artifacts/final.mp4")
        assert r1.content == b"version-one"
        assert r2.content == b"version-two"

    def test_unknown_version_returns_404(self, client):
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        _archive_version(store, jid, final__mp4=b"v1")
        r = c.get(f"/jobs/{jid}/versions/9/artifacts/final.mp4")
        assert r.status_code == 404

    def test_zero_version_returns_404(self, client):
        """version <=0 直接 404, 不去摸磁碟."""
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        r = c.get(f"/jobs/{jid}/versions/0/artifacts/final.mp4")
        assert r.status_code == 404

    def test_missing_file_in_version_returns_404(self, client):
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        _archive_version(store, jid, final__mp4=b"v1")
        r = c.get(f"/jobs/{jid}/versions/1/artifacts/missing.srt")
        assert r.status_code == 404

    def test_path_traversal_blocked(self, client):
        """`..` 在 name 該 400 (safe_join 字串檢查)."""
        c, store = client
        jid = _new_job(store, state=JobState.DONE)
        _archive_version(store, jid, final__mp4=b"v1")
        r = c.get(f"/jobs/{jid}/versions/1/artifacts/..mp4")
        assert r.status_code == 400
