"""core/langcode.py 測試 —— round-trip 穩定、idempotent、多段邊界、None/空安全。

純字串轉換,不打任何外部服務。驗證重點:這層只做分隔符替換,不偷偷做語言驗證,
所以對任意內容都該是可預期的機械轉換。
"""
from __future__ import annotations

import pytest

from core.langcode import to_hyphen, to_underscore


def test_canonical_hyphen_to_underscore():
    # canonical zh-TW -> translateGemma 邊界吃的底線式
    assert to_underscore("zh-TW") == "zh_TW"


def test_underscore_back_to_hyphen():
    # translateGemma 回傳底線式 -> 轉回 canonical 連字號
    assert to_hyphen("zh_TW") == "zh-TW"


def test_to_underscore_idempotent():
    # 已是底線式,再轉一次不應變動(避免重複套用炸掉)
    assert to_underscore("zh_TW") == "zh_TW"
    assert to_underscore(to_underscore("zh-TW")) == "zh_TW"


def test_to_hyphen_idempotent():
    # 已是連字號式,再轉一次不變
    assert to_hyphen("zh-TW") == "zh-TW"
    assert to_hyphen(to_hyphen("zh_TW")) == "zh-TW"


def test_round_trip_stable():
    # canonical -> 底線 -> canonical 應回到原值(雙向穩定)
    assert to_hyphen(to_underscore("zh-TW")) == "zh-TW"
    assert to_underscore(to_hyphen("zh_TW")) == "zh_TW"


def test_multipart_only_swaps_separator():
    # 多段如 zh-Hant-TW:只換分隔符,段內容不動
    assert to_underscore("zh-Hant-TW") == "zh_Hant_TW"
    assert to_hyphen("zh_Hant_TW") == "zh-Hant-TW"
    assert to_hyphen(to_underscore("zh-Hant-TW")) == "zh-Hant-TW"


def test_simple_code_no_separator():
    # 無分隔符的單段碼(en/ja)原樣回,不被誤改
    assert to_underscore("en") == "en"
    assert to_hyphen("ja") == "ja"


@pytest.mark.parametrize("fn", [to_underscore, to_hyphen])
def test_none_safe(fn):
    # None 安全回傳 None(呼叫端可無腦套用)
    assert fn(None) is None


@pytest.mark.parametrize("fn", [to_underscore, to_hyphen])
def test_empty_safe(fn):
    # 空字串原樣回 ''
    assert fn("") == ""


# ---------- 語言中繼資料（B-1，從 translateGemma 收編）----------
from core.langcode import (  # noqa: E402
    EDGE_TTS_VOICES,
    LANGUAGES,
    get_edge_tts_voice,
    get_language_info,
)


class TestLanguageMetadata:
    def test_languages_keyed_by_canonical_hyphen(self):
        # canonical 視圖以 BCP-47 連字號為 key
        assert "zh-TW" in LANGUAGES
        assert LANGUAGES["zh-TW"] == ("繁體中文", "Traditional Chinese")
        assert "en-US" in LANGUAGES

    def test_no_underscore_keys_in_canonical_views(self):
        # 核心 canonical 不得有底線式 key（底線只在 translateGemma 邊界）
        assert all("_" not in k for k in LANGUAGES)
        assert all("_" not in k for k in EDGE_TTS_VOICES)

    def test_edge_tts_voice_keyed_by_hyphen(self):
        assert EDGE_TTS_VOICES["zh-TW"] == "zh-TW-HsiaoChenNeural"

    def test_get_edge_tts_voice_tolerates_both_forms(self):
        # 底線 / 連字號輸入都該對到同一 voice
        assert get_edge_tts_voice("zh-TW") == "zh-TW-HsiaoChenNeural"
        assert get_edge_tts_voice("zh_TW") == "zh-TW-HsiaoChenNeural"

    def test_get_edge_tts_voice_unknown_returns_default(self):
        assert get_edge_tts_voice("xx-YY") == "en-US-JennyNeural"
        assert get_edge_tts_voice(None) == "en-US-JennyNeural"

    def test_get_language_info_tolerates_both_forms(self):
        assert get_language_info("ja-JP") == ("日文", "Japanese")
        assert get_language_info("ja_JP") == ("日文", "Japanese")

    def test_get_language_info_unknown(self):
        assert get_language_info("xx-YY") == ("Unknown", "Unknown")

    def test_source_and_canonical_sizes_match(self):
        # 導出視圖筆數與來源一致（沒漏轉）
        from core.langcode import _EDGE_TTS_SOURCE, _LANG_SOURCE
        assert len(LANGUAGES) == len(_LANG_SOURCE)
        assert len(EDGE_TTS_VOICES) == len(_EDGE_TTS_SOURCE)
