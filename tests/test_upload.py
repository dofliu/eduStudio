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

# 整支 module 都需要 fastapi.testclient + python-multipart, 任一缺就跳過。
# python-multipart 不裝會在 FastAPI Form/File 路由 collection 階段就炸,
# 必須先 importorskip 才能避免擋住整個 pytest 收集 (commit 8548906 踩過)。
pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="需要 python-multipart 才能測 FastAPI Form/File 路由")

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


# ---------------------------------------------------------------------------
# Helper unit tests — _sanitize_filename / _unique_target_path
#
# 這兩個是 uploads.py 內的純函式, HTTP 層測試 (上面) 不直接驗其行為.
# 路徑安全 helper (path injection / Windows 保留字 / 控制字元) = 攻擊面,
# 沒測試 = 未來 refactor 一不小心放行就直接上線. 補純函式測 = 安全鎖.
# 純 Python, 不需 TestClient, 不需 multipart, 跑超快.
# ---------------------------------------------------------------------------

import unicodedata
from pathlib import Path

from server.routes.uploads import (
    _sanitize_filename,
    _unique_target_path,
    _validate_upload,
)
from server.schemas import SourceType


class TestSanitizeFilenameHappyPath:
    """常見合法檔名不該被改 — 中文 / 多 dot ext / 底線橫線都保留。"""

    def test_normal_pdf_unchanged(self):
        assert _sanitize_filename("report.pdf") == "report.pdf"

    def test_chinese_filename_preserved(self):
        """中文字元不在 _FNAME_BAD 範圍 (BMP 高位區), 該原樣保留。"""
        assert _sanitize_filename("報告.pdf") == "報告.pdf"

    def test_multi_dot_extension_preserved(self):
        """archive.tar.gz: rpartition 只取最末 dot, 前段保留。"""
        assert _sanitize_filename("archive.tar.gz") == "archive.tar.gz"

    def test_underscore_and_dash_preserved(self):
        assert _sanitize_filename("my_report-v2.pdf") == "my_report-v2.pdf"


class TestSanitizeFilenamePathInjection:
    """path separator / dotdot 攻擊面 — 不該讓 caller 跳出 PDFS_DIR。"""

    def test_forward_slash_path_traversal_stripped(self):
        """../../etc/passwd.pdf: 斜線跟 dotdot 都該消, 結果落在 PDFS_DIR 不跳出。"""
        out = _sanitize_filename("../../etc/passwd.pdf")
        assert "/" not in out
        assert ".." not in out
        # 實際行為: ../ + .. 都被吃掉, 剩 "etcpasswd.pdf"
        assert out == "etcpasswd.pdf"

    def test_backslash_path_traversal_stripped(self):
        """Windows-style ..\\..\\etc\\passwd.pdf 同理該擋下。"""
        out = _sanitize_filename("..\\..\\etc\\passwd.pdf")
        assert "\\" not in out
        assert ".." not in out
        assert out == "etcpasswd.pdf"

    def test_colon_stripped(self):
        """C:foo.pdf 含 Windows 磁碟機代號分隔符 ':' — 該消, 不該被當成 drive。"""
        out = _sanitize_filename("C:foo.pdf")
        assert ":" not in out
        assert out == "Cfoo.pdf"

    def test_control_chars_stripped(self):
        """\\x00~\\x1f 控制字元 (含 null byte) 全該消 — 防 C 字串截斷攻擊。"""
        assert _sanitize_filename("foo\x00bar.pdf") == "foobar.pdf"
        assert _sanitize_filename("foo\x01\x02bar.pdf") == "foobar.pdf"
        assert _sanitize_filename("tab\there.pdf") == "tabhere.pdf"

    def test_consecutive_dots_collapsed(self):
        """連續多個 dot 全消, 防 .. 路徑跳出 (即使 sep 已濾)。"""
        assert _sanitize_filename("foo..bar.pdf") == "foobar.pdf"
        assert _sanitize_filename("foo....bar") == "foobar"

    def test_leading_trailing_dots_stripped(self):
        """頭尾的 dot 全消 — Windows 系統不接受開頭 dot 的檔名 (隱藏)。"""
        assert _sanitize_filename("...foo.pdf...") == "foo.pdf"


class TestSanitizeFilenameWindowsReserved:
    """CON / PRN / AUX / NUL / COM1-9 / LPT1-9 不可用作檔名 — 該加底線。"""

    def test_con_pdf_prefixed_with_underscore(self):
        assert _sanitize_filename("CON.pdf") == "_CON.pdf"

    def test_reserved_name_case_insensitive(self):
        """大小寫不敏感比對, 但原 case 保留 (只加前置底線)。"""
        assert _sanitize_filename("con.pdf") == "_con.pdf"
        assert _sanitize_filename("Aux.txt") == "_Aux.txt"

    def test_com1_to_com9_reserved(self):
        """COM1-COM9 是 reserved, COM10+ 不在保留字 set 內。"""
        assert _sanitize_filename("COM1.txt") == "_COM1.txt"
        assert _sanitize_filename("LPT9.txt") == "_LPT9.txt"
        # COM10 是 documented behavior: 不在 reserved set, 該原樣保留
        assert _sanitize_filename("COM10.txt") == "COM10.txt"

    def test_reserved_name_without_extension_passthrough(self):
        """無副檔名時 rpartition 找不到 dot, base="" 不命中 reserved 比對 —
        documented behavior (helper 沒處理這 corner, 但 OS 寫檔還會擋, 不算 bug)."""
        # 純鎖 documented behavior, 未來若改該邏輯該主動更新此 test
        assert _sanitize_filename("CON") == "CON"


class TestSanitizeFilenameFallback:
    """空字串 / 只剩空白或 dot → fallback 'upload', 不能回 ''。"""

    def test_empty_string_returns_upload(self):
        assert _sanitize_filename("") == "upload"

    def test_only_whitespace_returns_upload(self):
        assert _sanitize_filename("   ") == "upload"

    def test_only_dots_returns_upload(self):
        """連續 dots 被吃掉後剩 '' → fallback。"""
        assert _sanitize_filename("....") == "upload"
        assert _sanitize_filename("   ...  ") == "upload"


class TestUniqueTargetPath:
    """同名加時間戳, 不覆蓋既有檔。"""

    def test_returns_input_path_when_file_absent(self, tmp_path):
        """target 不存在 → 直接回傳, 不加時間戳。"""
        out = _unique_target_path(tmp_path, "foo.pdf")
        assert out == tmp_path / "foo.pdf"

    def test_adds_timestamp_suffix_to_base_when_file_exists(self, tmp_path):
        """target 已存在 → base 加時間戳, ext 保留位置。"""
        (tmp_path / "foo.pdf").write_text("existing")
        out = _unique_target_path(tmp_path, "foo.pdf")
        assert out != tmp_path / "foo.pdf"
        assert out.name.startswith("foo_") and out.name.endswith(".pdf")
        # 時間戳格式 YYYYMMDD_HHMMSS (15 字元 + 底線), 確保 collision 不太可能
        # foo_YYYYMMDD_HHMMSS.pdf = 4 + 15 + 4 = 23
        assert len(out.name) == len("foo_20260524_000000.pdf")

    def test_file_without_extension_appends_timestamp_to_full_name(self, tmp_path):
        """無 ext (rpartition 找不到 dot) → 走 fallback 分支, 整名加 _timestamp。"""
        (tmp_path / "noext").write_text("x")
        out = _unique_target_path(tmp_path, "noext")
        assert out.name.startswith("noext_")
        # 沒 ext 結尾不該有 dot
        assert "." not in out.name

    def test_multi_dot_extension_only_last_dot_split(self, tmp_path):
        """archive.tar.gz 已存在 → 時間戳插在最末 dot 前 (rpartition 切點)。"""
        (tmp_path / "archive.tar.gz").write_text("x")
        out = _unique_target_path(tmp_path, "archive.tar.gz")
        # documented behavior: rpartition('.') 取最末 dot
        # → base="archive.tar", ext="gz" → "archive.tar_TS.gz"
        assert out.name.startswith("archive.tar_")
        assert out.name.endswith(".gz")


# ---------------------------------------------------------------------------
# S-4 上傳硬化 — 副檔名/MIME 白名單 + NFC 正規化
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from fastapi import HTTPException  # noqa: E402


class TestUploadHardeningHTTP:
    """HTTP 層: 非文件副檔名 / 壞 MIME 應在進 schedule 前被 400 擋。"""

    def test_exam_pdf_rejects_non_pdf_extension(self, client):
        resp = client.post(
            "/upload",
            files={"file": ("sneaky.png", b"x" * 64, "application/pdf")},
            data={"source_type": "exam_pdf"},
        )
        assert resp.status_code == 400
        assert "副檔名" in resp.text

    def test_document_rejects_executable_extension(self, client):
        resp = client.post(
            "/upload",
            files={"file": ("malware.exe", b"x" * 64, "application/octet-stream")},
            data={"source_type": "document"},
        )
        assert resp.status_code == 400
        assert "副檔名" in resp.text

    def test_rejects_bad_mime_even_with_ok_extension(self, client):
        resp = client.post(
            "/upload",
            files={"file": ("real.pdf", b"x" * 64, "image/png")},
            data={"source_type": "exam_pdf"},
        )
        assert resp.status_code == 400
        assert "MIME" in resp.text

    def test_document_accepts_markdown(self, client):
        # .md 通過白名單 → 不因驗證被 400 擋 (後續 schedule 與本測試無關)
        resp = client.post(
            "/upload",
            files={"file": ("notes.md", b"# hi\n", "text/markdown")},
            data={"source_type": "document"},
        )
        assert resp.status_code != 400


class TestValidateUploadUnit:
    """_validate_upload 純函式: 副檔名強 gate, MIME 寬鬆。"""

    def test_pdf_source_accepts_pdf(self):
        _validate_upload("a.pdf", SourceType.EXAM_PDF, "application/pdf")  # 不 raise

    def test_pdf_source_rejects_txt(self):
        with pytest.raises(HTTPException) as e:
            _validate_upload("a.txt", SourceType.SLIDES_PDF, "text/plain")
        assert e.value.status_code == 400

    def test_document_accepts_txt_md_pdf(self):
        for fn, ct in [("a.txt", "text/plain"), ("a.md", "text/markdown"), ("a.pdf", "application/pdf")]:
            _validate_upload(fn, SourceType.DOCUMENT, ct)  # 不 raise

    def test_empty_or_missing_content_type_ok(self):
        # 瀏覽器常給空 / octet-stream, 不該因此被擋
        _validate_upload("a.pdf", SourceType.EXAM_PDF, "")
        _validate_upload("a.pdf", SourceType.EXAM_PDF, "application/octet-stream")
        _validate_upload("a.pdf", SourceType.EXAM_PDF, None)

    def test_rejects_known_bad_mime(self):
        with pytest.raises(HTTPException) as e:
            _validate_upload("a.pdf", SourceType.EXAM_PDF, "application/zip")
        assert e.value.status_code == 400

    def test_no_extension_rejected(self):
        with pytest.raises(HTTPException) as e:
            _validate_upload("noext", SourceType.DOCUMENT, "text/plain")
        assert e.value.status_code == 400


class TestNFCNormalization:
    """S-4: 檔名做 Unicode NFC 正規化 (組合字 → 等價單碼)。"""

    def test_decomposed_form_normalized_to_nfc(self):
        # "é" 的分解形式 (e + 組合重音 U+0301) 應被正規化成 NFC 單碼形式
        decomposed = "café.pdf"  # café.pdf (NFD)
        out = _sanitize_filename(decomposed)
        assert out == unicodedata.normalize("NFC", "café.pdf")
        assert "́" not in out
