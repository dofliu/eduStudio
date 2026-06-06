"""全域測試夾具。"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_usage_db(tmp_path_factory):
    """隔離 Gemini 用量計帳 db。

    為什麼需要：被 mock 的 Gemini 測試（comic/route 等）仍會跑 generate_json 的真實 body，
    其中的用量計帳 record_text/record_image 會走 get_usage_store() 寫進真實 usage.db，
    污染成本面板。把 USAGE_DB_PATH 指到 tmp 並重置單例，讓測試完全不碰真實 db。
    """
    db = tmp_path_factory.mktemp("usage") / "test_usage.db"
    os.environ["USAGE_DB_PATH"] = str(db)
    import core.usage as usage
    usage._default_store = None
    yield
    usage._default_store = None
    os.environ.pop("USAGE_DB_PATH", None)
