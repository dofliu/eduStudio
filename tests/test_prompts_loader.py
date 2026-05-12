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
    """既有 caller 用 SECTION_PROMPT.format(deck_title=..., ...) 不該炸."""
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
