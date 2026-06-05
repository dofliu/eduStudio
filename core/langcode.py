"""語言碼分隔符轉換 helper（canonical = ``zh-TW``，BCP-47 連字號）。

唯一使用場景:呼叫 **translateGemma 邊界**。translateGemma 內部用底線式
``zh_TW``,但本系統 canonical 一律用 BCP-47 連字號 ``zh-TW``(DESIGN_SPEC §3.1 /
core/translate.py 模組 docstring)。為避免底線式 ``zh_TW`` 在 core/RAG/Shell 裡到處
擴散,集中在這一層只在進出 translateGemma 時做純字串的分隔符轉換。

刻意保持 trivial:**只換分隔符,不做語言驗證/白名單**。理由是這層的職責只有
「連字號 <-> 底線」的邊界適配;語言是否合法該由真正的翻譯後端決定,在這裡做白名單
反而會把驗證邏輯散落到字串工具裡,且難以同步 translateGemma 支援的語言集合。
"""
from __future__ import annotations


def to_underscore(code: str | None) -> str | None:
    """``'zh-TW'`` -> ``'zh_TW'``(連字號轉底線)。

    僅在**呼叫 translateGemma 邊界**用(把 canonical 連字號碼轉成 translateGemma
    吃的底線式)。多段如 ``'zh-Hant-TW'`` 只換分隔符 -> ``'zh_Hant_TW'``。

    idempotent:已是底線式的輸入原樣回。None/空字串安全回傳原值(None 回 None、
    '' 回 ''),不丟例外 —— 讓呼叫端可無腦套用而不必先判空。
    """
    if not code:
        # None -> None、'' -> '';保留原值語意(呼叫端可區分 None 與空字串)
        return code
    return code.replace("-", "_")


def to_hyphen(code: str | None) -> str | None:
    """``'zh_TW'`` -> ``'zh-TW'``(底線轉連字號)。

    僅在 translateGemma 邊界用(把 translateGemma 回傳的底線式碼轉回 canonical
    連字號式,讓 core/RAG/Shell 後續一律見 ``zh-TW``)。多段如 ``'zh_Hant_TW'``
    只換分隔符 -> ``'zh-Hant-TW'``。

    idempotent:已是連字號式的輸入原樣回。None/空字串安全回傳原值,不丟例外。
    """
    if not code:
        return code
    return code.replace("_", "-")
