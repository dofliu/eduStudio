"""M-1 角色登錄表 core/models.py — 鎖角色集合、預設表、解析優先序、fallback。

每測試把 ES_SETTINGS_PATH 指 tmp 隔離，不碰真實 settings.json，不打任何 API。
"""
from __future__ import annotations

import json

import pytest

from core import models


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    monkeypatch.setenv("ES_SETTINGS_PATH", str(p))
    return p


def _write_settings(path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ---------- 角色集合鎖死 ----------

def test_role_set_is_exactly_the_six_logical_roles():
    assert models.ROLES == frozenset(
        {"text.fast", "text.pro", "vision", "image.fast", "image.pro", "tts"}
    )


def test_all_roles_sorted():
    assert models.all_roles() == sorted(models.ROLES)


def test_every_role_has_a_default():
    for role in models.ROLES:
        assert role in models.DEFAULTS


def test_role_catalog_shape_and_excludes_tts():
    cat = models.role_catalog()
    keys = [c["role"] for c in cat]
    # tts 走獨立 TTS 子系統，不在逐角色設定頁管理
    assert keys == ["text.fast", "text.pro", "vision", "image.fast", "image.pro"]
    for c in cat:
        assert set(c) == {"role", "label", "kind", "default"}
        assert c["kind"] in ("text", "image")
        assert c["default"] == models.DEFAULTS[c["role"]][1]   # 與登錄表單一真實來源一致
        assert c["label"]


# ---------- 預設表（無設定覆寫）----------

def test_defaults_resolve_when_no_settings(settings_path):
    # settings.json 不存在 → 全走內建預設
    assert models.resolve("text.fast") == ("gemini", "gemini-3.5-flash")
    assert models.resolve("text.pro") == ("gemini", "gemini-3.1-pro-preview")
    assert models.resolve("vision") == ("gemini", "gemini-3.5-flash")
    assert models.resolve("image.fast") == ("gemini", "gemini-3.1-flash-image")
    assert models.resolve("image.pro") == ("gemini", "gemini-3-pro-image")
    assert models.resolve("tts") == ("edge", "edge")


def test_resolve_id_returns_model_id_only(settings_path):
    assert models.resolve_id("text.fast") == "gemini-3.5-flash"
    assert models.resolve_id("image.pro") == "gemini-3-pro-image"


# ---------- type guard ----------

def test_unknown_role_raises():
    with pytest.raises(ValueError):
        models.resolve("text.turbo")
    with pytest.raises(ValueError):
        models.resolve_id("nope")


# ---------- legacy 單值欄位向後相容 ----------

def test_legacy_text_model_overrides_text_roles(settings_path):
    _write_settings(settings_path, {"text_model": "gemini-9.9-flash"})
    # text.fast / text.pro / vision 都採用 legacy text_model
    assert models.resolve("text.fast") == ("gemini", "gemini-9.9-flash")
    assert models.resolve("text.pro") == ("gemini", "gemini-9.9-flash")
    assert models.resolve("vision") == ("gemini", "gemini-9.9-flash")
    # image / tts 不受 text_model 影響
    assert models.resolve("image.fast") == ("gemini", "gemini-3.1-flash-image")
    assert models.resolve("tts") == ("edge", "edge")


def test_legacy_image_model_overrides_image_roles(settings_path):
    _write_settings(settings_path, {"image_model": "gemini-9.9-image"})
    assert models.resolve("image.fast") == ("gemini", "gemini-9.9-image")
    assert models.resolve("image.pro") == ("gemini", "gemini-9.9-image")
    assert models.resolve("text.fast") == ("gemini", "gemini-3.5-flash")


def test_blank_legacy_value_falls_through_to_default(settings_path):
    _write_settings(settings_path, {"text_model": "   "})
    assert models.resolve("text.fast") == ("gemini", "gemini-3.5-flash")


# ---------- per-role override（M-3 設定頁 UI 會寫入；現在先讀，向前相容）----------

def test_per_role_override_takes_precedence_over_legacy(settings_path):
    _write_settings(
        settings_path,
        {
            "text_model": "gemini-legacy",
            "model_roles": {"text.pro": "gemini-role-specific"},
        },
    )
    # text.pro 有逐角色覆寫 → 用它；text.fast 無逐角色 → 退 legacy
    assert models.resolve("text.pro") == ("gemini", "gemini-role-specific")
    assert models.resolve("text.fast") == ("gemini", "gemini-legacy")


def test_per_role_override_ignored_when_not_dict(settings_path):
    _write_settings(settings_path, {"model_roles": "oops-not-a-dict"})
    assert models.resolve("text.fast") == ("gemini", "gemini-3.5-flash")


def test_per_role_blank_value_falls_through(settings_path):
    _write_settings(settings_path, {"model_roles": {"image.pro": ""}})
    assert models.resolve("image.pro") == ("gemini", "gemini-3-pro-image")
