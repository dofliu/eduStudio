"""POST /upload 上傳路由的錯誤路徑測試 (CR Round 1 P0 #3 covered 但無 test)。

涵蓋:
- MAX_UPLOAD_SIZE post-read 防呆 (commit 7db9aab 加的)
- 空檔案 → 400
- 不支援的 source_type (repo / url) → 400
- options_json 不合法 → 400

不測 happy path (那會觸發 schedule_job 真的跑 background task, 需要 mock 整條,
範圍超出單檔 unit test。需要時再加 integration test)。

降低 MAX_UPLOAD_SIZE 到 1024 bytes 跑測試, 不必生真的 200MB body 拖慢 CI。
"""
from __future__ import annotations

import pytest

# 整支 module 都需要 fastapi.testclient + server.main, 任一缺就跳過 (CI 都有裝)
pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")

from fastapi.testclient import TestClient

import server.routes.uploads as uploads_mod
from server.jobs import JobStore, get_default_store
from server.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """乾淨 TestClient — MAX_UPLOAD_SIZE 降到 10KB, JobStore 用 tmp_path。

    為什麼 10KB 不更小: multipart encoding 含 boundary header + form field 的固定
    開銷 (~300 bytes), 上限太低 (e.g. 1KB) 邊界測試會被 overhead 蓋過。
    10KB 留充足 margin, 同時遠小於真實 200MB 上限, CI 跑也夠快。
    """
    monkeypatch.setattr(uploads_mod, "MAX_UPLOAD_SIZE", 10 * 1024)
    # PDFS_DIR 也指到 tmp, 避免測試寫真實 pdfs/
    monkeypatch.setattr(uploads_mod, "PDFS_DIR", tmp_path / "pdfs")

    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    # 覆寫 get_default_store, 不污染真實 jobs/
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c


class TestSizeLimit:
    """commit 7db9aab P0 #3: 200 MB 上傳上限, content-length 預檢 + read 後二次防呆。"""

    def test_oversized_file_returns_413(self, client):
        """超過 MAX_UPLOAD_SIZE 應返 413 Request Entity Too Large。

        測試送 20KB (> 上限 10KB), 應該被 size 防呆擋下。
        """
        big_blob = b"x" * (20 * 1024)
        resp = client.post(
            "/upload",
            files={"file": ("big.pdf", big_blob, "application/pdf")},
            data={"source_type": "document"},
        )
        assert resp.status_code == 413
        assert "過大" in resp.text  # 中文錯誤訊息

    def test_under_limit_not_rejected_by_size(self, client):
        """明確小於 MAX_UPLOAD_SIZE 不被 size 擋。

        會走到 schedule_job 階段, 那會試圖跑真的 task 觸發很多依賴,
        所以這條 expect 任何 *非 413* status 即可 (201 / 4xx 都行,
        只要不是因 size 被擋掉)。
        """
        # 1KB body + multipart headers 安全在 10KB 上限內
        small_blob = b"x" * 1024
        resp = client.post(
            "/upload",
            files={"file": ("ok.pdf", small_blob, "application/pdf")},
            data={"source_type": "document"},
        )
        # 重點: 不會因 size 被擋。後續 schedule_job 成功/失敗都跟本測試無關。
        assert resp.status_code != 413


class TestValidation:
    """source_type 白名單 + options_json 解析 + 空檔案防呆。"""

    def test_unsupported_source_type_repo_returns_400(self, client):
        """repo source_type 沒有檔案概念, 應拒絕上傳。"""
        resp = client.post(
            "/upload",
            files={"file": ("foo.pdf", b"small", "application/pdf")},
            data={"source_type": "repo"},
        )
        assert resp.status_code == 400
        assert "不支援檔案上傳" in resp.text

    def test_unsupported_source_type_url_returns_400(self, client):
        """url source_type 也不能上傳檔案。"""
        resp = client.post(
            "/upload",
            files={"file": ("foo.pdf", b"small", "application/pdf")},
            data={"source_type": "url"},
        )
        assert resp.status_code == 400

    def test_empty_file_returns_400(self, client):
        """0 bytes 不應該接受 (避免 schedule 跑出鬼)。"""
        resp = client.post(
            "/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
            data={"source_type": "document"},
        )
        assert resp.status_code == 400
        assert "空" in resp.text

    def test_invalid_options_json_returns_400(self, client):
        """options_json 不是合法 JSON → 400。"""
        resp = client.post(
            "/upload",
            files={"file": ("foo.pdf", b"content", "application/pdf")},
            data={"source_type": "document", "options_json": "{not valid json"},
        )
        assert resp.status_code == 400
        assert "options_json" in resp.text or "解析" in resp.text

    def test_options_json_not_object_returns_400(self, client):
        """options_json 是合法 JSON 但不是物件 (例 array / number) → 400。"""
        resp = client.post(
            "/upload",
            files={"file": ("foo.pdf", b"content", "application/pdf")},
            data={"source_type": "document", "options_json": "[1, 2, 3]"},
        )
        assert resp.status_code == 400
