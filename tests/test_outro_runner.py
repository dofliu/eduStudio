"""iter 63: _append_outro_to_deck override / fallback / 位置."""
from __future__ import annotations

from unittest.mock import patch

from server.runner import _append_outro_to_deck


def _make_deck():
    return {
        "deck_title": "iter 63 結尾測試",
        "sections": [
            {"id": "intro", "slides": [{"id": "intro_1"}]},
            {"id": "main", "slides": [{"id": "main_1"}]},
        ],
    }


class TestAppendOutroOverride:
    """非空 override 直接生效."""

    def test_speaker_org_share_cover_env(self):
        """speaker / org 跟封面共用 fallback (一份 env 兩邊用)."""
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="ENV_SP"), \
             patch("core.config.get_cover_org", return_value="ENV_ORG"), \
             patch("core.config.get_outro_thanks", return_value="ENV_THX"), \
             patch("core.config.get_outro_url", return_value="env.com"):
            _append_outro_to_deck(deck)
        slide = deck["sections"][-1]["slides"][0]
        assert slide["outro_speaker"] == "ENV_SP"
        assert slide["outro_org"] == "ENV_ORG"

    def test_thanks_override(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"), \
             patch("core.config.get_outro_thanks", return_value="FB_THX"), \
             patch("core.config.get_outro_url", return_value="fb.com"):
            _append_outro_to_deck(deck, thanks_override="再見")
        slide = deck["sections"][-1]["slides"][0]
        assert slide["title"] == "再見"

    def test_url_override(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"), \
             patch("core.config.get_outro_thanks", return_value="FB"), \
             patch("core.config.get_outro_url", return_value="fb.com"):
            _append_outro_to_deck(deck, url_override="github.com/x")
        slide = deck["sections"][-1]["slides"][0]
        assert slide["outro_url"] == "github.com/x"

    def test_narration_override(self):
        deck = _make_deck()
        custom = "結尾自訂口白"
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"), \
             patch("core.config.get_outro_thanks", return_value="FB"), \
             patch("core.config.get_outro_url", return_value="fb.com"):
            _append_outro_to_deck(deck, narration_override=custom)
        slide = deck["sections"][-1]["slides"][0]
        assert slide["narration"] == custom


class TestAppendOutroFallback:
    def test_all_none_uses_env(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="env_sp"), \
             patch("core.config.get_cover_org", return_value="env_org"), \
             patch("core.config.get_outro_thanks", return_value="env_thx"), \
             patch("core.config.get_outro_url", return_value="env.url"):
            _append_outro_to_deck(deck)
        slide = deck["sections"][-1]["slides"][0]
        assert slide["outro_speaker"] == "env_sp"
        assert slide["outro_org"] == "env_org"
        assert slide["title"] == "env_thx"
        assert slide["outro_url"] == "env.url"

    def test_empty_strings_fall_back(self):
        deck = _make_deck()
        with patch("core.config.get_cover_speaker", return_value="env_sp"), \
             patch("core.config.get_cover_org", return_value="env_org"), \
             patch("core.config.get_outro_thanks", return_value="env_thx"), \
             patch("core.config.get_outro_url", return_value="env.url"):
            _append_outro_to_deck(
                deck,
                speaker_override="   ",
                org_override="",
                thanks_override="\t",
                url_override="",
            )
        slide = deck["sections"][-1]["slides"][0]
        assert slide["outro_speaker"] == "env_sp"
        assert slide["title"] == "env_thx"


class TestAppendOutroPosition:
    def test_appends_at_last_position(self):
        """結尾頁該插在 sections[-1], 原本的 sections 順序不變."""
        deck = _make_deck()
        original_first_id = deck["sections"][0]["id"]
        original_main_id = deck["sections"][1]["id"]
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"), \
             patch("core.config.get_outro_thanks", return_value="T"), \
             patch("core.config.get_outro_url", return_value="u"):
            _append_outro_to_deck(deck)
        assert len(deck["sections"]) == 3
        assert deck["sections"][0]["id"] == original_first_id
        assert deck["sections"][1]["id"] == original_main_id
        assert deck["sections"][2]["id"] == "_outro"

    def test_missing_sections_noop(self):
        deck = {"deck_title": "x"}
        _append_outro_to_deck(deck, speaker_override="X")
        assert "sections" not in deck or deck.get("sections") is None

    def test_sections_not_list_noop(self):
        deck = {"sections": "broken"}
        _append_outro_to_deck(deck, speaker_override="X")
        assert deck["sections"] == "broken"
