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
