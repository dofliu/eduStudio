"""core/prompts_loader.py — prompt 載入 + 版本追蹤 sanity tests.

設計目的: 鎖 prompt 抽到 prompts/*.txt 之後的 contract:
1. 既有兩個 prompt 載得起來
2. 不存在的 name 給清楚 error
3. .format() 仍然能填參數 (向後相容)
4. version hash 穩定 (改 prompt 文件 hash 跟著變)
"""
from __future__ import annotations

import pytest


def test_load_scriptor_repo_section():
    from core.prompts_loader import load_prompt

    prompt = load_prompt("scriptor_repo_section")
    assert "==== 整體脈絡 ====" in prompt
    assert "code_snippet" in prompt
    # 確認 placeholder 還在 (load 不應該做 format)
    assert "{deck_title}" in prompt
    assert "{section_idx}" in prompt


def test_load_scriptor_longform_section():
    from core.prompts_loader import load_prompt

    prompt = load_prompt("scriptor_longform_section")
    assert "==== 整體脈絡 ====" in prompt
    assert "code_snippet / code_lang / file_path 全部設 null" in prompt
    assert "{document_content}" in prompt


def test_load_outliner_repo():
    from core.prompts_loader import load_prompt

    prompt = load_prompt("outliner_repo")
    assert "==== Repo 內容 ====" in prompt
    assert "{root_name}" in prompt
    assert "{tree}" in prompt
    assert "{key_files_section}" in prompt


def test_load_outliner_longform():
    from core.prompts_loader import load_prompt

    prompt = load_prompt("outliner_longform")
    assert "==== 文件資訊 ====" in prompt
    assert "{content}" in prompt
    assert "{source_extra}" in prompt


def test_load_missing_raises_with_clear_message():
    from core.prompts_loader import PromptNotFoundError, load_prompt

    with pytest.raises(PromptNotFoundError) as excinfo:
        load_prompt("definitely_does_not_exist_prompt")
    # error message 應該帶 name + 路徑提示
    assert "definitely_does_not_exist_prompt" in str(excinfo.value)


def test_format_compat_with_scriptor_keys():
    """既有 caller 用 SECTION_PROMPT.format(deck_title=..., ...) 不該炸.

    iter 43 加 length_mode placeholder 後, 完整 kwargs 集合.
    """
    from core.prompts_loader import load_prompt

    prompt = load_prompt("scriptor_repo_section")
    filled = prompt.format(
        deck_title="測試 deck",
        summary="講解主軸",
        section_idx=1,
        total_sections=5,
        section_title="第一章",
        section_intent="意圖",
        section_topics="topics",
        section_files_section="files",
        section_id="ch1",
        # iter 43: length_mode 注入欄位
        length_directive="請設計快速講解",
        slides_per_section_range="5~10",
        narration_chars_range="100~200",
        narration_seconds_range="30~60",
    )
    assert "測試 deck" in filled
    assert "{deck_title}" not in filled  # 已替換


def test_prompt_version_returns_short_hash():
    from core.prompts_loader import prompt_version

    v = prompt_version("scriptor_repo_section")
    # 8 字元 sha256 prefix
    assert len(v) == 8
    assert all(c in "0123456789abcdef" for c in v)


def test_prompt_version_stable_across_calls():
    """同一份 prompt 多次呼叫應回同樣 hash (lru_cache 也保險)."""
    from core.prompts_loader import prompt_version

    v1 = prompt_version("scriptor_repo_section")
    v2 = prompt_version("scriptor_repo_section")
    assert v1 == v2


def test_prompt_version_differs_between_prompts():
    from core.prompts_loader import prompt_version

    v1 = prompt_version("scriptor_repo_section")
    v2 = prompt_version("scriptor_longform_section")
    assert v1 != v2  # 不同內容應該不同 hash


def test_scriptor_backward_compat_constants_loaded():
    """既有 SECTION_PROMPT / LONGFORM_SECTION_PROMPT 仍可用 (alias)。"""
    pytest.importorskip("google.genai", reason="scriptor module 依賴 google-genai")
    from core import scriptor

    assert len(scriptor.SECTION_PROMPT) > 100
    assert len(scriptor.LONGFORM_SECTION_PROMPT) > 100
    assert "{deck_title}" in scriptor.SECTION_PROMPT


def test_outliner_backward_compat_constants_loaded():
    """既有 OUTLINE_PROMPT_REPO / OUTLINE_PROMPT_LONGFORM 仍可用 (alias)。"""
    pytest.importorskip("google.genai", reason="outliner module 依賴 google-genai")
    from core import outliner

    assert len(outliner.OUTLINE_PROMPT_REPO) > 100
    assert len(outliner.OUTLINE_PROMPT_LONGFORM) > 100
    assert "{root_name}" in outliner.OUTLINE_PROMPT_REPO
    assert "{content}" in outliner.OUTLINE_PROMPT_LONGFORM


class TestCacheInvalidation:
    """iter 30: dev-mode cache invalidation (review 抓的 🟡 設計疑慮).

    Production lru_cache 是必要的 (hot path); dev 改 prompt 不必重啟。
    """

    def test_clear_prompt_cache_callable(self):
        """clear_prompt_cache 不該 raise, 就算 cache 是空的."""
        from core.prompts_loader import clear_prompt_cache

        clear_prompt_cache()  # 第一次調用空 cache, 不該炸
        clear_prompt_cache()  # 兩次也不該炸

    def test_cache_returns_same_content_normally(self):
        """無 env var 時, lru_cache 應該 cache 內容 (同 name 兩次回同樣 object)."""
        from core.prompts_loader import load_prompt

        a = load_prompt("scriptor_repo_section")
        b = load_prompt("scriptor_repo_section")
        # str immutable 但 lru_cache 內部會回同樣 reference 給快速比較
        assert a == b
        assert a is b   # cached: 同個 object

    def test_clear_cache_invalidates(self, monkeypatch, tmp_path):
        """clear_prompt_cache 後再 load 應該重新讀檔 (檔變了會看到新內容)."""
        from core import prompts_loader
        from core.prompts_loader import clear_prompt_cache, load_prompt

        # 自己造一份假 prompt 在 tmp_path, monkeypatch PROMPTS_DIR
        fake_prompt = tmp_path / "test_invalidation.txt"
        fake_prompt.write_text("VERSION_1\n", encoding="utf-8")
        monkeypatch.setattr(prompts_loader, "PROMPTS_DIR", tmp_path)

        # 確保開始沒 cache (前面 test 可能 cache 過別的 name)
        clear_prompt_cache()

        first = load_prompt("test_invalidation")
        assert "VERSION_1" in first

        # 改檔但不清 cache: 應該回舊版 (cache 命中)
        fake_prompt.write_text("VERSION_2\n", encoding="utf-8")
        cached = load_prompt("test_invalidation")
        assert "VERSION_1" in cached    # 仍是舊版 = cache 工作

        # 清 cache 後: 應該回新版
        clear_prompt_cache()
        fresh = load_prompt("test_invalidation")
        assert "VERSION_2" in fresh
        assert "VERSION_1" not in fresh

    def test_no_cache_env_var_bypasses(self, monkeypatch, tmp_path):
        """PROMPTS_NO_CACHE=1 時, 每次 load 都重讀檔."""
        from core import prompts_loader
        from core.prompts_loader import clear_prompt_cache, load_prompt

        fake = tmp_path / "test_nocache.txt"
        fake.write_text("ALPHA\n", encoding="utf-8")
        monkeypatch.setattr(prompts_loader, "PROMPTS_DIR", tmp_path)
        monkeypatch.setenv("PROMPTS_NO_CACHE", "1")
        clear_prompt_cache()  # 清前面殘留

        assert "ALPHA" in load_prompt("test_nocache")

        # 改檔, 不清 cache, 直接 load — PROMPTS_NO_CACHE=1 應該重讀
        fake.write_text("BETA\n", encoding="utf-8")
        assert "BETA" in load_prompt("test_nocache")
        assert "ALPHA" not in load_prompt("test_nocache")

    def test_prompt_version_also_invalidates(self, monkeypatch, tmp_path):
        """prompt_version 也走 cache, clear_prompt_cache 應該一起 invalidate."""
        from core import prompts_loader
        from core.prompts_loader import (
            clear_prompt_cache, prompt_version,
        )

        fake = tmp_path / "test_version.txt"
        fake.write_text("v1 content\n", encoding="utf-8")
        monkeypatch.setattr(prompts_loader, "PROMPTS_DIR", tmp_path)
        clear_prompt_cache()

        hash_v1 = prompt_version("test_version")

        fake.write_text("v2 content totally different\n", encoding="utf-8")
        # 沒清 cache, hash 應該不變
        assert prompt_version("test_version") == hash_v1

        clear_prompt_cache()
        hash_v2 = prompt_version("test_version")
        assert hash_v2 != hash_v1
