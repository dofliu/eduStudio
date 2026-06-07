"""S-3 path-traversal — 測共用 safe_join 與套用它的端點。

safe_join 是三道防護(字元檢查 + resolve + containment)的單一真相, 這裡把各種逃脫
手法(.. / 絕對路徑 / 分隔符 / 前導點 / symlink / Windows \\)鎖死。
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("fastapi", reason="需要 fastapi 安裝")

from fastapi import HTTPException  # noqa: E402

from server.path_safety import safe_join  # noqa: E402


# ---------- 正常情況 ----------

def test_simple_name_ok(tmp_path):
    target = safe_join(tmp_path, "file.png")
    assert target == (tmp_path.resolve() / "file.png")


def test_nested_parts_ok(tmp_path):
    target = safe_join(tmp_path, "sub", "file.png")
    assert target == (tmp_path.resolve() / "sub" / "file.png")


def test_existence_not_required(tmp_path):
    # safe_join 不檢查存在性 — 回傳路徑即可, 不 raise
    target = safe_join(tmp_path, "does_not_exist.bin")
    assert not target.exists()


# ---------- 各種逃脫手法都要被擋 (400) ----------

@pytest.mark.parametrize("bad", [
    "..",
    "../etc/passwd",
    "../../secret",
    "foo/../../bar",
    "sub/../../..",
])
def test_dotdot_rejected(tmp_path, bad):
    with pytest.raises(HTTPException) as e:
        safe_join(tmp_path, bad)
    assert e.value.status_code == 400


@pytest.mark.parametrize("bad", [
    "a/b",            # 正斜線分隔符
    "a\\b",           # 反斜線 (Windows)
    "/etc/passwd",    # 絕對路徑
    "",               # 空字串
    ".hidden",        # 前導點
    ".",              # 當前目錄
])
def test_separators_and_specials_rejected(tmp_path, bad):
    with pytest.raises(HTTPException) as e:
        safe_join(tmp_path, bad)
    assert e.value.status_code == 400


def test_one_bad_part_among_good_rejected(tmp_path):
    with pytest.raises(HTTPException) as e:
        safe_join(tmp_path, "ok", "../escape")
    assert e.value.status_code == 400


def test_symlink_escape_rejected(tmp_path):
    """base 內放一個指向 base 外的 symlink, resolve 後 containment 必須擋下。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("top secret")

    base = tmp_path / "base"
    base.mkdir()
    link = base / "link"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("此平台不支援 symlink")

    # "link" 本身字元檢查過得了, 但 resolve 後逃出 base → 必須被 containment 擋
    with pytest.raises(HTTPException) as e:
        safe_join(base, "link", "secret.txt")
    assert e.value.status_code == 400


# ---------- 整合: 套用 safe_join 的端點 ----------

@pytest.fixture()
def client():
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient
    from server.main import create_app
    with TestClient(create_app()) as c:
        yield c


def test_slide_image_rejects_traversal(client):
    # 用 URL 編碼的 ..%2f 嘗試逃脫; 端點應回 400 (safe_join) 而非 200/500
    resp = client.get("/slide_images/..%2f..%2fetc/passwd")
    assert resp.status_code in (400, 404)


def test_slide_image_rejects_backslash_part(client):
    resp = client.get("/slide_images/ok/..%5c..%5csecret")
    assert resp.status_code in (400, 404)
