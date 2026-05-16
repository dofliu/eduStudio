"""iter 62b: 封面 meta per-job override — 測 runner._prepend_cover_to_deck.

跳過 build_cover_section 已有的測試 (test_cover_gen.py), 這邊只測 runner
helper 的 override / fallback 邏輯:
  - 非空 override → 用 override
  - 空字串 / None → fallback 到 env defaults / 今天
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from server.runner import _prepend_cover_to_deck


def _make_deck():
    return {
        "deck_title": "iter 62b 測試主題",
        "sections": [
            {"id": "intro", "slides": [{"id": "intro_1"}]},
        ],
    }


class TestPrependCoverOverride:
    """非空 override 直接生效, 不打 env."""

    def test_speaker_override_used(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="FALLBACK_SP"), \
             patch("core.config.get_cover_org", return_value="FALLBACK_ORG"):
            _prepend_cover_to_deck(deck, speaker_override="Alice Pro")
        slide = deck["sections"][0]["slides"][0]
        assert slide["cover_speaker"] == "Alice Pro"
        # org 沒給 → fallback
        assert slide["cover_org"] == "FALLBACK_ORG"

    def test_org_override_used(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="FALLBACK_SP"), \
             patch("core.config.get_cover_org", return_value="FALLBACK_ORG"):
            _prepend_cover_to_deck(deck, org_override="MIT CSAIL")
        slide = deck["sections"][0]["slides"][0]
        assert slide["cover_org"] == "MIT CSAIL"
        assert slide["cover_speaker"] == "FALLBACK_SP"

    def test_date_override_used(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"):
            _prepend_cover_to_deck(deck, date_override="2030 春季")
        slide = deck["sections"][0]["slides"][0]
        assert slide["cover_date"] == "2030 春季"

    def test_all_three_overrides(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="FB_SP"), \
             patch("core.config.get_cover_org", return_value="FB_ORG"):
            _prepend_cover_to_deck(
                deck,
                speaker_override="王教授",
                org_override="台大電機",
                date_override="2026-12-25",
            )
        slide = deck["sections"][0]["slides"][0]
        assert slide["cover_speaker"] == "王教授"
        assert slide["cover_org"] == "台大電機"
        assert slide["cover_date"] == "2026-12-25"


class TestPrependCoverFallback:
    """None / 空字串 → fallback."""

    def test_none_falls_back_to_env(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="FB_SPEAKER"), \
             patch("core.config.get_cover_org", return_value="FB_ORG"):
            _prepend_cover_to_deck(deck)  # 三個 override 都 None
        slide = deck["sections"][0]["slides"][0]
        assert slide["cover_speaker"] == "FB_SPEAKER"
        assert slide["cover_org"] == "FB_ORG"

    def test_empty_string_falls_back(self):
        """空字串視同未設 (使用者可能切開 prepend_cover 但欄位沒填)."""
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="FB_SPEAKER"), \
             patch("core.config.get_cover_org", return_value="FB_ORG"):
            _prepend_cover_to_deck(
                deck,
                speaker_override="",
                org_override="   ",      # whitespace 也算空
                date_override=None,
            )
        slide = deck["sections"][0]["slides"][0]
        assert slide["cover_speaker"] == "FB_SPEAKER"
        assert slide["cover_org"] == "FB_ORG"
        # date None / 空 → 今天 YYYY-MM-DD
        assert slide["cover_date"] == datetime.now().strftime("%Y-%m-%d")

    def test_date_empty_uses_today(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"):
            _prepend_cover_to_deck(deck, date_override="   ")
        slide = deck["sections"][0]["slides"][0]
        assert slide["cover_date"] == datetime.now().strftime("%Y-%m-%d")


class TestPrependCoverNarrationOverride:
    """iter 65: 自訂開場口白 — 非空 → 用 override, 空 → fallback 模板."""

    def test_narration_override_used(self):
        deck = _make_deck()
        custom = "歡迎各位來到本次的特別講座, 今天我們深入聊聊封面口白覆寫."
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"):
            _prepend_cover_to_deck(deck, narration_override=custom)
        slide = deck["sections"][0]["slides"][0]
        assert slide["narration"] == custom

    def test_narration_override_strips_outer_whitespace(self):
        """前後空白 strip 掉, 內容保留."""
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"):
            _prepend_cover_to_deck(deck, narration_override="  hello world  ")
        slide = deck["sections"][0]["slides"][0]
        assert slide["narration"] == "hello world"

    def test_empty_narration_falls_back_to_template(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="講者A"), \
             patch("core.config.get_cover_org", return_value="單位B"):
            _prepend_cover_to_deck(deck, narration_override="")
        slide = deck["sections"][0]["slides"][0]
        # 模板 narration 內含 deck_title / speaker / org
        assert "講者A" in slide["narration"]
        assert "單位B" in slide["narration"]
        assert deck["deck_title"] in slide["narration"]

    def test_whitespace_narration_falls_back(self):
        """全空白 (含中文全形) 視同未設."""
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="講者A"), \
             patch("core.config.get_cover_org", return_value="單位B"):
            _prepend_cover_to_deck(deck, narration_override="   \n  \t ")
        slide = deck["sections"][0]["slides"][0]
        # 該套模板, 不會是全空白
        assert slide["narration"].strip() != ""
        assert "講者A" in slide["narration"]

    def test_narration_override_independent_of_meta(self):
        """narration override 跟 speaker/org override 互不影響."""
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="env_speaker"), \
             patch("core.config.get_cover_org", return_value="env_org"):
            _prepend_cover_to_deck(
                deck,
                speaker_override="ui_speaker",
                narration_override="自訂 narration 字串",
            )
        slide = deck["sections"][0]["slides"][0]
        # meta 仍走 override (ui_speaker)
        assert slide["cover_speaker"] == "ui_speaker"
        # narration 走 override, 跟 ui_speaker 無關
        assert slide["narration"] == "自訂 narration 字串"


class TestPrependCoverNoop:
    """sections 不是 list / 結構壞掉 → noop, 不擋 ingest."""

    def test_missing_sections_noop(self):
        deck = {"deck_title": "x"}
        # 不該丟 exception
        _prepend_cover_to_deck(deck, speaker_override="X")
        assert "sections" not in deck or deck.get("sections") is None

    def test_sections_not_list_noop(self):
        deck = {"deck_title": "x", "sections": "broken"}
        _prepend_cover_to_deck(deck, speaker_override="X")
        # 沒被改 (字串還是字串)
        assert deck["sections"] == "broken"

    def test_inserts_at_position_zero(self):
        """封面該插在 sections[0], 原本的 intro 推到 [1]."""
        deck = _make_deck()
        original_intro_id = deck["sections"][0]["id"]
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"):
            _prepend_cover_to_deck(deck)
        assert deck["sections"][0]["id"] == "_cover"
        assert deck["sections"][1]["id"] == original_intro_id
