"""M-1 角色登錄表 — 邏輯角色 → 具體 model id 的單一真實來源。

痛點（劉老師 2026-06-07）：模型 id **散落** 在 `slide_ingest.py` / `core/infocards/models.py`
/ `core/config.py` / scriptor / outliner …，名稱/版號不一致、preview id 會 404。本檔把
「哪個角色用哪個模型」收斂成一處，未來換代（4.0/5.0…）只改這張表或設定頁，呼叫端零改動。

設計（M 軸 Option A，介面 B-ready）：
- **邏輯角色**（caller 只認角色，不認具體 id）：
  - ``text.fast``  一般文字生成主力（大綱/旁白/翻譯/解題）
  - ``text.pro``   深度推理（複雜內容/長文）
  - ``vision``     讀圖/OCR（試題影像、投影片頁面理解）
  - ``image.fast`` 快速生圖主力
  - ``image.pro``  最高畫質生圖
  - ``tts``        語音合成
- ``resolve(role)`` 回 ``(provider, model_id)``：**provider 維度預留給 B 階段**
  （Phase 9 F9-3 本機可插拔，例如 ollama/f5）。A 階段 LLM/視覺/生圖角色 provider 恆
  ``gemini``；``tts`` 反映本 repo 既有的 TTS 後端（預設 ``edge``，見 ``tts_backend.py``），
  不硬塞未驗證的 gemini TTS id（避免重蹈 preview id 404）。

解析優先序（``resolve``）：
1. 設定頁 ``model_roles`` 逐角色覆寫（dict，M-3 設定頁 UI 會寫入；現在先讀，向前相容）。
2. 設定頁既有單值欄位 ``text_model`` / ``image_model``（向後相容：保留現行
   ``get_gemini_model()`` 行為，讓 M-2 換接呼叫端時 runtime 行為不變）。
3. 內建預設表 ``DEFAULTS``。

``model_roles`` 逐角色覆寫支援兩種寫法（F9-3c，本機可插拔 provider 預留）：
- **扁平字串** ``{role: "model-id"}``：只覆寫 model id，provider 沿用該角色預設
  （向後相容 M-3 既有寫法）。
- **巢狀物件** ``{role: {"provider": "ollama", "model": "translategemma"}}``：同時指定
  provider（本機 / 雲端）與 model id。讓老師把特定文字角色指到**本機 Ollama**（F9-3
  本機可插拔，M 軸 Option B）。

本檔**只建表 + 解析**（M-1）；把散落的硬編 id 換成 ``resolve()`` 是 M-2、設定頁逐角色
管理是 M-3、provider adapter 介面是 M-4、本機 provider 接線是 F9-3。
"""
from __future__ import annotations

# ── provider 名稱（B 階段會擴張：ollama / claude / f5 …）──
PROVIDER_GEMINI = "gemini"
PROVIDER_EDGE = "edge"
# 本機可插拔 LLM（F9-3 / M 軸 Option B）。DEFAULTS 維持雲端不變——由設定頁
# model_roles（F9-3c）或 env 把特定角色指到本機，此常數先就緒供 OllamaProvider 登記。
PROVIDER_OLLAMA = "ollama"

# 設定頁 model_roles 可指派的 provider（type guard：擋打錯字默默污染登錄表）。
# 只含 LLM/視覺/生圖角色可走的 provider；tts 走獨立 tts_backend 子系統，不在此。
# B 階段擴張本機 provider（如 claude / 其他本機後端）時在此加入即可。
ASSIGNABLE_PROVIDERS: frozenset[str] = frozenset({PROVIDER_GEMINI, PROVIDER_OLLAMA})

# ── 邏輯角色集合（測試鎖死，不可隨意增刪）──
TEXT_FAST = "text.fast"
TEXT_PRO = "text.pro"
VISION = "vision"
IMAGE_FAST = "image.fast"
IMAGE_PRO = "image.pro"
TTS = "tts"

ROLES: frozenset[str] = frozenset(
    {TEXT_FAST, TEXT_PRO, VISION, IMAGE_FAST, IMAGE_PRO, TTS}
)

# ── 內建預設表：角色 → (provider, model_id)──
# id 對齊既有 single-source（core/infocards/models.py 經 live API 實測可用的 Gemini 3 系列）。
# text.fast/vision 用 3.5-flash（多模態主力）、text.pro 用 3.1-pro-preview、
# image.fast 用 3.1-flash-image、image.pro 用 3-pro-image（3.1-pro-image 未開放，見 infocards/models.py）。
DEFAULTS: dict[str, tuple[str, str]] = {
    TEXT_FAST:  (PROVIDER_GEMINI, "gemini-3.5-flash"),
    TEXT_PRO:   (PROVIDER_GEMINI, "gemini-3.1-pro-preview"),
    VISION:     (PROVIDER_GEMINI, "gemini-3.5-flash"),
    IMAGE_FAST: (PROVIDER_GEMINI, "gemini-3.1-flash-image"),
    IMAGE_PRO:  (PROVIDER_GEMINI, "gemini-3-pro-image"),
    # tts：本 repo 走 provider 子系統（edge/f5/google，預設 edge），非單一 model id。
    # B 階段（F9-3 本機 provider）會把 f5/google 接進來；model_id 暫等同後端名。
    TTS:        (PROVIDER_EDGE, "edge"),
}

# ── 向後相容：設定頁既有單值欄位 → 哪些角色採用 ──
# 現行設定頁只有 text_model / image_model 各一格；M-3 升級成逐角色前，沿用此映射讓
# 「設定頁選的模型」繼續生效（與現行 get_gemini_model() 一致）。
_LEGACY_SETTING_KEY: dict[str, str] = {
    TEXT_FAST: "text_model",
    TEXT_PRO: "text_model",
    VISION: "text_model",
    IMAGE_FAST: "image_model",
    IMAGE_PRO: "image_model",
    # tts 無對應 legacy 欄位（走 TTS_PROVIDER / tts_config.json）。
}


def all_roles() -> list[str]:
    """所有邏輯角色（排序，UI/健檢用）。"""
    return sorted(ROLES)


# ── 設定頁逐角色管理（M-3）用的呈現資料 ──
# tts 走獨立 TTS 子系統（TTS_PROVIDER / tts_config.json），不在設定頁逐角色下拉管理，
# 避免「這裡選了卻不生效」的誤導；故 catalog 只列 resolve() 實際治理的 LLM/視覺/生圖角色。
_ROLE_LABELS: dict[str, str] = {
    TEXT_FAST:  "文字 · 主力（大綱／旁白／翻譯／解題／圖卡文字）",
    TEXT_PRO:   "文字 · 深度推理（複雜內容／長文）",
    VISION:     "視覺理解（讀圖／OCR／投影片頁面）",
    IMAGE_FAST: "生圖 · 主力（快速）",
    IMAGE_PRO:  "生圖 · 最高畫質（海報）",
}
# 逐角色用哪一組候選清單（前端據此挑 text_models / image_models 下拉）。
_ROLE_KIND: dict[str, str] = {
    TEXT_FAST: "text", TEXT_PRO: "text", VISION: "text",
    IMAGE_FAST: "image", IMAGE_PRO: "image",
}
# 設定頁呈現順序（穩定，UI 用）。
_CATALOG_ORDER: tuple[str, ...] = (TEXT_FAST, TEXT_PRO, VISION, IMAGE_FAST, IMAGE_PRO)


def role_catalog() -> list[dict[str, str]]:
    """設定頁逐角色管理用的角色清單（單一真實來源）。

    每筆：``role``（key）/ ``label``（人類說明）/ ``kind``（text|image，挑哪組候選下拉）
    / ``default``（內建預設 model id，下拉「預設」選項顯示用）/ ``provider``（角色預設
    provider，設定頁 provider 下拉的初始值；F9-3e 本機可插拔接線）。tts 不列（見上註）。
    """
    return [
        {
            "role": r,
            "label": _ROLE_LABELS[r],
            "kind": _ROLE_KIND[r],
            "default": DEFAULTS[r][1],
            "provider": DEFAULTS[r][0],
        }
        for r in _CATALOG_ORDER
    ]


# 設定頁 provider 下拉的人讀標籤（單一真實來源；B 階段擴張本機 provider 時在此加入）。
_PROVIDER_LABELS: dict[str, str] = {
    PROVIDER_GEMINI: "Gemini（雲端）",
    PROVIDER_OLLAMA: "Ollama（本機）",
}


def provider_catalog() -> list[dict[str, str]]:
    """設定頁 model_roles 可指派的 provider 清單（單一真實來源，F9-3e）。

    每筆：``id``（存進 ``model_roles[role].provider``，須在 ``ASSIGNABLE_PROVIDERS``）
    / ``label``（人讀，下拉顯示用）。穩定排序（gemini 在前）。tts 後端不在此（走獨立
    tts_backend 子系統，避免「這裡選了卻不生效」的誤導）。
    """
    return [
        {"id": p, "label": _PROVIDER_LABELS.get(p, p)}
        for p in sorted(ASSIGNABLE_PROVIDERS)
    ]


def _provider_for(role: str) -> str:
    """角色預設 provider（給只覆寫 model id 的 legacy/per-role override 沿用）。"""
    return DEFAULTS[role][0]


def normalize_override(role: str, spec) -> tuple[str, str] | None:
    """把一筆 ``model_roles`` override 解析成 ``(provider, model_id)``；無效回 None。

    接受兩種寫法（單一真實來源——``resolve()`` 與設定頁清洗共用此解析）：
    - 扁平字串 ``"model-id"``（向後相容）→ ``(角色預設 provider, model-id)``。
    - 巢狀 ``{"provider":..., "model":...}`` → 解析 provider + model。

    回 None（＝無有效覆寫，退 legacy/預設）的情形：
    - 空字串 / 空白 / 非 str 非 dict。
    - 巢狀但 provider 與預設相同且未帶 model（空殼覆寫，無意義）。
    - 巢狀但指到**非預設 provider 卻沒帶 model**（本機 provider 無雲端 model 可退，
      無從解析；漏報優先、不亂猜）。
    未知 provider（不在 ``ASSIGNABLE_PROVIDERS``）一律忽略 → 退角色預設 provider。
    """
    default_provider = _provider_for(role)
    if isinstance(spec, str):
        mid = spec.strip()
        return (default_provider, mid) if mid else None
    if isinstance(spec, dict):
        prov = spec.get("provider")
        prov = prov.strip() if isinstance(prov, str) and prov.strip() else None
        if prov is not None and prov not in ASSIGNABLE_PROVIDERS:
            prov = None                       # 未知 provider 忽略，退預設
        mid = spec.get("model")
        mid = mid.strip() if isinstance(mid, str) and mid.strip() else None
        provider = prov or default_provider
        if mid:
            return (provider, mid)
        # 無 model：只有 provider==預設才能退預設 model（但那等於無覆寫 → None）；
        # 非預設 provider 缺 model 無從解析 → None（退完全預設，不拿錯 id 打本機）。
        return None
    return None


def clean_role_override(role: str, spec):
    """正規化 ``model_roles`` 單筆 → **JSON 可存形式**（扁平 str 或巢狀 dict）或 None。

    供 ``core.settings`` 寫入時清洗用（與 ``resolve()`` 共用同一套解析，避免雙份分歧）。
    收斂表示法：provider 等於角色預設時退回扁平字串（與 legacy 一致、最精簡）；
    指到非預設 provider 才保留巢狀 ``{"provider":..., "model":...}``。
    """
    norm = normalize_override(role, spec)
    if norm is None:
        return None
    provider, model = norm
    if provider == _provider_for(role):
        return model                          # 扁平字串（純 model 覆寫）
    return {"provider": provider, "model": model}


def resolve(role: str) -> tuple[str, str]:
    """解析邏輯角色 → ``(provider, model_id)``。

    優先序：設定頁 ``model_roles[role]`` → 設定頁 legacy 單值欄位 → 內建預設表。
    覆寫只帶 model id 時，provider 沿用該角色預設（A 階段恆 gemini / tts 為 edge）；
    巢狀覆寫帶 provider 時回該 provider（F9-3c 本機可插拔，如 ``ollama``）。

    Args:
        role: 必須是 ``ROLES`` 之一，否則 ``ValueError``（type guard，禁止打錯字默默退預設）。
    """
    if role not in ROLES:
        raise ValueError(
            f"未知模型角色 {role!r}；合法角色：{', '.join(all_roles())}"
        )

    override = _settings_override(role)
    if override:
        return override

    return DEFAULTS[role]


def resolve_id(role: str) -> str:
    """便捷層：只要 model id（A 階段呼叫端多半只需這個）。"""
    return resolve(role)[1]


def _settings_override(role: str) -> tuple[str, str] | None:
    """讀設定頁覆寫（逐角色 model_roles → legacy 單值欄位）→ ``(provider, model_id)``；
    無則 None。失敗靜默回 None。"""
    try:
        from core.settings import get_setting

        per_role = get_setting("model_roles")
        if isinstance(per_role, dict) and role in per_role:
            norm = normalize_override(role, per_role[role])
            if norm is not None:
                return norm

        legacy_key = _LEGACY_SETTING_KEY.get(role)
        if legacy_key:
            v = get_setting(legacy_key)
            if isinstance(v, str) and v.strip():
                return (_provider_for(role), v.strip())
    except Exception:
        pass
    return None
