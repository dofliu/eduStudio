"""語言碼分隔符轉換 helper（canonical = ``zh-TW``，BCP-47 連字號）。

唯一使用場景:呼叫 **translateGemma 邊界**。translateGemma 內部用底線式
``zh_TW``,但本系統 canonical 一律用 BCP-47 連字號 ``zh-TW``(docs/archive/DESIGN_SPEC.md §3.1 /
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


# ============================================================================
# 語言中繼資料（eduStudio 合併 PR-M1 B-1，從 translateGemma languages.py 收編）
#
# 設計:核心 canonical 一律用 BCP-47 連字號(zh-TW)。translateGemma 原始資料以底線式
# 為 key(且 tuple 第三元素已是 BCP-47)。為降低轉錄錯誤,**原樣保留底線版來源 dict**,
# 再以程式導出「連字號 key」的 canonical 視圖供核心使用。底線式只在 translateGemma
# 邊界出現(用 to_underscore())。
# ============================================================================

# (中文名稱, English name, BCP-47 locale) — 從 translateGemma languages.py 原樣搬入。
_LANG_SOURCE = {
    # East Asian
    "zh_TW": ("繁體中文", "Traditional Chinese", "zh-TW"),
    "zh_CN": ("簡體中文", "Simplified Chinese", "zh-CN"),
    "ja_JP": ("日文", "Japanese", "ja-JP"),
    "ko_KR": ("韓文", "Korean", "ko-KR"),
    # European
    "en_US": ("英文", "English", "en-US"),
    "de_DE": ("德文", "German", "de-DE"),
    "fr_FR": ("法文", "French", "fr-FR"),
    "es_ES": ("西班牙文", "Spanish", "es-ES"),
    "it_IT": ("義大利文", "Italian", "it-IT"),
    "pt_BR": ("葡萄牙文（巴西）", "Portuguese", "pt-BR"),
    "pt_PT": ("葡萄牙文（葡萄牙）", "Portuguese", "pt-PT"),
    "nl_NL": ("荷蘭文", "Dutch", "nl-NL"),
    "pl_PL": ("波蘭文", "Polish", "pl-PL"),
    "ru_RU": ("俄文", "Russian", "ru-RU"),
    "uk_UA": ("烏克蘭文", "Ukrainian", "uk-UA"),
    "cs_CZ": ("捷克文", "Czech", "cs-CZ"),
    "sv_SE": ("瑞典文", "Swedish", "sv-SE"),
    "da_DK": ("丹麥文", "Danish", "da-DK"),
    "fi_FI": ("芬蘭文", "Finnish", "fi-FI"),
    "no_NO": ("挪威文", "Norwegian", "no-NO"),
    "el_GR": ("希臘文", "Greek", "el-GR"),
    "hu_HU": ("匈牙利文", "Hungarian", "hu-HU"),
    "ro_RO": ("羅馬尼亞文", "Romanian", "ro-RO"),
    "sk_SK": ("斯洛伐克文", "Slovak", "sk-SK"),
    "sl_SI": ("斯洛維尼亞文", "Slovenian", "sl-SI"),
    "hr_HR": ("克羅埃西亞文", "Croatian", "hr-HR"),
    "sr_RS": ("塞爾維亞文", "Serbian", "sr-RS"),
    "bg_BG": ("保加利亞文", "Bulgarian", "bg-BG"),
    "lt_LT": ("立陶宛文", "Lithuanian", "lt-LT"),
    "lv_LV": ("拉脫維亞文", "Latvian", "lv-LV"),
    "et_EE": ("愛沙尼亞文", "Estonian", "et-EE"),
    "is_IS": ("冰島文", "Icelandic", "is-IS"),
    # South / Southeast Asian
    "vi_VN": ("越南文", "Vietnamese", "vi-VN"),
    "th_TH": ("泰文", "Thai", "th-TH"),
    "id_ID": ("印尼文", "Indonesian", "id-ID"),
    "ms_MY": ("馬來文", "Malay", "ms-MY"),
    "tl_PH": ("菲律賓文", "Filipino", "fil-PH"),
    "hi_IN": ("印地文", "Hindi", "hi-IN"),
    "bn_IN": ("孟加拉文", "Bengali", "bn-IN"),
    "ta_IN": ("坦米爾文", "Tamil", "ta-IN"),
    "te_IN": ("泰盧固文", "Telugu", "te-IN"),
    "mr_IN": ("馬拉地文", "Marathi", "mr-IN"),
    "gu_IN": ("古吉拉特文", "Gujarati", "gu-IN"),
    "kn_IN": ("卡納達文", "Kannada", "kn-IN"),
    "ml_IN": ("馬拉雅拉姆文", "Malayalam", "ml-IN"),
    "pa_IN": ("旁遮普文", "Punjabi", "pa-IN"),
    "ur_PK": ("烏都文", "Urdu", "ur-PK"),
    # Middle East
    "ar_SA": ("阿拉伯文", "Arabic", "ar-SA"),
    "he_IL": ("希伯來文", "Hebrew", "he-IL"),
    "fa_IR": ("波斯文", "Persian", "fa-IR"),
    "tr_TR": ("土耳其文", "Turkish", "tr-TR"),
    # African
    "sw_KE": ("史瓦希里文（肯亞）", "Swahili", "sw-KE"),
    "sw_TZ": ("史瓦希里文（坦尚尼亞）", "Swahili", "sw-TZ"),
    "zu_ZA": ("祖魯文", "Zulu", "zu-ZA"),
}

# edge-tts voice id（從 translateGemma languages.py 原樣搬入，底線 key）。
_EDGE_TTS_SOURCE = {
    "zh_TW": "zh-TW-HsiaoChenNeural",
    "zh_CN": "zh-CN-XiaoxiaoNeural",
    "en_US": "en-US-JennyNeural",
    "ja_JP": "ja-JP-NanamiNeural",
    "ko_KR": "ko-KR-SunHiNeural",
    "de_DE": "de-DE-KatjaNeural",
    "fr_FR": "fr-FR-DeniseNeural",
    "es_ES": "es-ES-ElviraNeural",
    "it_IT": "it-IT-ElsaNeural",
    "pt_BR": "pt-BR-FranciscaNeural",
    "ru_RU": "ru-RU-SvetlanaNeural",
    "vi_VN": "vi-VN-HoaiMyNeural",
    "th_TH": "th-TH-PremwadeeNeural",
    "id_ID": "id-ID-GadisNeural",
    "ar_SA": "ar-SA-ZariyahNeural",
    "tr_TR": "tr-TR-EmelNeural",
    "pl_PL": "pl-PL-ZofiaNeural",
    "nl_NL": "nl-NL-ColetteNeural",
    "hi_IN": "hi-IN-SwaraNeural",
}

_DEFAULT_EDGE_VOICE = "en-US-JennyNeural"

# ---- canonical 視圖（連字號 key），由 source 程式導出，避免手抄 70 筆出錯 ----
# LANGUAGES: {BCP-47 連字號: (中文名, 英文名)}
LANGUAGES: dict[str, tuple[str, str]] = {
    bcp47: (zh_name, en_name)
    for (zh_name, en_name, bcp47) in _LANG_SOURCE.values()
}

# EDGE_TTS_VOICES: {BCP-47 連字號: voice id}。把底線 key 經 _LANG_SOURCE 對到 BCP-47。
EDGE_TTS_VOICES: dict[str, str] = {
    (_LANG_SOURCE[u][2] if u in _LANG_SOURCE else to_hyphen(u)): voice
    for u, voice in _EDGE_TTS_SOURCE.items()
}


def get_edge_tts_voice(lang_code: str | None) -> str:
    """回 edge-tts voice id。輸入容忍底線/連字號(內部正規化成連字號再查)。

    查不到回預設 en-US voice(不丟例外,讓配音流程有保底嗓音)。
    """
    return EDGE_TTS_VOICES.get(to_hyphen(lang_code) or "", _DEFAULT_EDGE_VOICE)


def get_language_info(lang_code: str | None) -> tuple[str, str]:
    """回 (中文名, 英文名)。輸入容忍底線/連字號。查不到回 ('Unknown', 'Unknown')。"""
    return LANGUAGES.get(to_hyphen(lang_code) or "", ("Unknown", "Unknown"))
