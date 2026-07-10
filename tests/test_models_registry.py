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
        assert set(c) == {"role", "label", "kind", "default", "provider"}
        assert c["kind"] in ("text", "image")
        assert c["default"] == models.DEFAULTS[c["role"]][1]    # 與登錄表單一真實來源一致
        assert c["provider"] == models.DEFAULTS[c["role"]][0]   # 角色預設 provider（F9-3e 下拉初值）
        assert c["label"]


def test_provider_catalog_shape_and_excludes_tts():
    cat = models.provider_catalog()
    ids = [p["id"] for p in cat]
    # gemini 在前的穩定排序、只列可指派 provider、tts 後端不在此
    assert ids == ["gemini", "ollama"]
    assert set(ids) == set(models.ASSIGNABLE_PROVIDERS)
    assert "edge" not in ids and "tts" not in ids
    for p in cat:
        assert set(p) == {"id", "label"}
        assert p["id"] in models.ASSIGNABLE_PROVIDERS
        assert p["label"]


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


def test_image_roles_derive_from_infocards_catalog(settings_path):
    """漂移守衛：image.fast/image.pro 的預設 id 必須等於 infocards 圖片目錄的
    中等/貴兩階（單一來源，2026-07 統一）。任何一邊改 id 不同步即紅。"""
    from core.infocards.models import IMAGE_MODELS

    assert models.DEFAULTS[models.IMAGE_FAST][1] == IMAGE_MODELS["flash"]["id"]
    assert models.DEFAULTS[models.IMAGE_PRO][1] == IMAGE_MODELS["pro"]["id"]


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


# ---------- F9-3c：巢狀 provider 覆寫（本機可插拔 ollama）----------

def test_nested_override_resolves_provider_and_model(settings_path):
    # 把 text.fast 指到本機 ollama + 本機 model id → resolve 回該 provider
    _write_settings(
        settings_path,
        {"model_roles": {"text.fast": {"provider": "ollama", "model": "translategemma"}}},
    )
    assert models.resolve("text.fast") == ("ollama", "translategemma")
    # 其餘角色不受影響，仍走雲端預設
    assert models.resolve("text.pro") == ("gemini", "gemini-3.1-pro-preview")


def test_nested_override_model_only_keeps_default_provider(settings_path):
    # 巢狀但只帶 model（無 provider）＝等同扁平字串：provider 沿用角色預設
    _write_settings(settings_path, {"model_roles": {"text.pro": {"model": "gemini-x"}}})
    assert models.resolve("text.pro") == ("gemini", "gemini-x")


def test_nested_override_unknown_provider_ignored(settings_path):
    # 未知 provider 忽略 → 退角色預設 provider，但保留有效 model
    _write_settings(
        settings_path,
        {"model_roles": {"text.fast": {"provider": "bogus", "model": "still-used"}}},
    )
    assert models.resolve("text.fast") == ("gemini", "still-used")


def test_nested_override_non_default_provider_without_model_falls_through(settings_path):
    # 指到非預設 provider 卻沒帶 model → 無從解析，退完全預設（不拿錯 id 打本機）
    _write_settings(settings_path, {"model_roles": {"text.fast": {"provider": "ollama"}}})
    assert models.resolve("text.fast") == ("gemini", "gemini-3.5-flash")


def test_nested_override_default_provider_explicit(settings_path):
    # provider 明寫 gemini（＝預設）+ model → 等同扁平字串
    _write_settings(
        settings_path,
        {"model_roles": {"vision": {"provider": "gemini", "model": "gemini-vis-x"}}},
    )
    assert models.resolve("vision") == ("gemini", "gemini-vis-x")


# ---------- F9-3c：normalize_override / clean_role_override 單元 ----------

def test_normalize_override_forms():
    # 扁平字串 → 角色預設 provider
    assert models.normalize_override("text.fast", "m") == ("gemini", "m")
    # 巢狀帶 provider + model
    assert models.normalize_override(
        "text.fast", {"provider": "ollama", "model": "qwen2.5"}
    ) == ("ollama", "qwen2.5")
    # 空字串 / 空白 / 非 str 非 dict → None
    assert models.normalize_override("text.fast", "") is None
    assert models.normalize_override("text.fast", "  ") is None
    assert models.normalize_override("text.fast", 123) is None
    # 非預設 provider 缺 model → None
    assert models.normalize_override("text.fast", {"provider": "ollama"}) is None


def test_clean_role_override_storage_form():
    # provider==預設 → 收斂回扁平字串（最精簡，與 legacy 一致）
    assert models.clean_role_override("text.fast", "m") == "m"
    assert models.clean_role_override(
        "text.fast", {"provider": "gemini", "model": "m"}
    ) == "m"
    # 非預設 provider → 保留巢狀
    assert models.clean_role_override(
        "text.fast", {"provider": "ollama", "model": "qwen2.5"}
    ) == {"provider": "ollama", "model": "qwen2.5"}
    # 無效 → None
    assert models.clean_role_override("text.fast", {"provider": "ollama"}) is None


def test_assignable_providers_set():
    # tts 後端（edge/f5/google）不在 model_roles 可指派範圍
    assert models.ASSIGNABLE_PROVIDERS == frozenset({"gemini", "ollama"})
