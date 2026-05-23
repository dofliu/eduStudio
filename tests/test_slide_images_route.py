"""GET /slide_images/{stem}/{filename} — 投影片 PNG 縮圖端點 (PR-3h).

純 fastapi route 測 — security checks (path traversal, hidden file, abs path)
+ happy path + 404. 不打渲染, 直接 monkeypatch SLIDES_DIR 到 tmp_path 寫假
PNG bytes 模擬 slide_ingest.py 已產出的 slides/<stem>/p001.png 結構.

該 endpoint 安全相關 (任何 user 都打得到, path traversal 直通檔系統),
但 iter 110 之前無 regression 測 — 補上.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Patch SLIDES_DIR 到 tmp_path/slides — 跟真檔案系統隔離.

    route module 內 `from core.config import SLIDES_DIR` 把 reference 捕到
    server.routes.slides.SLIDES_DIR, 必須 patch 這個 attribute (不是 core.config).
    """
    slides_root = tmp_path / "slides"
    slides_root.mkdir()
    monkeypatch.setattr("server.routes.slides.SLIDES_DIR", slides_root)
    app = create_app()
    with TestClient(app) as c:
        yield c, slides_root


def _write_png(slides_root, stem: str, filename: str, content: bytes = b"\x89PNG\r\n\x1a\nfake") -> None:
    """寫一個假 PNG 到 slides_root/<stem>/<filename>."""
    stem_dir = slides_root / stem
    stem_dir.mkdir(exist_ok=True)
    (stem_dir / filename).write_bytes(content)


class TestHappyPath:
    def test_serves_png(self, client):
        c, root = client
        content = b"\x89PNG\r\n\x1a\n test png bytes"
        _write_png(root, "deck_abc", "p001.png", content)
        resp = c.get("/slide_images/deck_abc/p001.png")
        assert resp.status_code == 200
        assert resp.content == content
        assert resp.headers["content-type"] == "image/png"

    def test_serves_multiple_pages_same_stem(self, client):
        c, root = client
        _write_png(root, "deck_xy", "p001.png", b"PAGE1")
        _write_png(root, "deck_xy", "p005.png", b"PAGE5")
        assert c.get("/slide_images/deck_xy/p001.png").content == b"PAGE1"
        assert c.get("/slide_images/deck_xy/p005.png").content == b"PAGE5"


class TestNotFound:
    def test_missing_stem_dir_returns_404(self, client):
        c, _ = client
        resp = c.get("/slide_images/never_existed/p001.png")
        assert resp.status_code == 404

    def test_missing_file_in_existing_stem_returns_404(self, client):
        c, root = client
        # stem 存在但沒這個 filename
        _write_png(root, "deck_a", "p001.png")
        resp = c.get("/slide_images/deck_a/p999.png")
        assert resp.status_code == 404

    def test_directory_instead_of_file_returns_404(self, client):
        c, root = client
        # filename 解到一個目錄 — 仍該 404 (不是 200 整個 listing)
        (root / "deck_z" / "subdir").mkdir(parents=True)
        resp = c.get("/slide_images/deck_z/subdir")
        # 405 / 404 都算擋住, 不該 200
        assert resp.status_code in (404, 405)


class TestPathTraversalSecurity:
    """endpoint 直接拼路徑寫檔, path traversal 必須擋."""

    def test_dotdot_in_filename_rejected(self, client):
        c, _ = client
        # 用 raw URL (不 encode) — fastapi 該擋在 _safe_part
        resp = c.get("/slide_images/deck/..%2Fevil.png")
        # 400 (非法) 或 404 (resolve 後 relative_to 失敗) 都算擋住
        assert resp.status_code in (400, 404)

    def test_dotdot_in_stem_rejected(self, client):
        c, _ = client
        resp = c.get("/slide_images/..%2Fetc/passwd")
        assert resp.status_code in (400, 404)

    def test_backslash_in_filename_rejected(self, client):
        c, _ = client
        resp = c.get("/slide_images/deck/..%5Cwindows%5Csys.png")
        assert resp.status_code in (400, 404)

    def test_hidden_file_dotfile_rejected(self, client, monkeypatch):
        """_safe_part 拒絕 startswith('.') 的 stem / filename — 防 .env / .ssh 等
        敏感檔被當 slide 撈出來. 即使檔真的在 tmp_path 寫了."""
        c, root = client
        # 故意寫一個「.secret」前綴的檔案讓 endpoint 試
        (root / ".secret_stem").mkdir(exist_ok=True)
        (root / ".secret_stem" / ".env").write_bytes(b"SECRET=1")
        resp1 = c.get("/slide_images/.secret_stem/p001.png")
        assert resp1.status_code == 400
        resp2 = c.get("/slide_images/deck/.env")
        assert resp2.status_code == 400


class TestEdgeCases:
    def test_empty_filename_404(self, client):
        c, _ = client
        # /slide_images/stem/ — trailing slash, fastapi 路由不該命中
        resp = c.get("/slide_images/deck/")
        # 405 或 404 都算 — 反正不是 200
        assert resp.status_code in (404, 405, 307)

    def test_special_chars_in_filename_404_not_500(self, client):
        c, root = client
        # filename 含特殊字元 (非 path traversal), 無對應檔 → 404, 不該炸 500
        _write_png(root, "deck_q", "p001.png")
        resp = c.get("/slide_images/deck_q/has%20space.png")
        assert resp.status_code in (400, 404)
