"""eduStudio 設定頁持久化（個人品牌 / API key / 模型選擇）。

settings.json 存使用者在設定頁設定的值，覆寫環境變數預設。get_gemini_api_key() 會優先讀
這裡（見 core.config）。API key 屬敏感值——對外端點只回「是否已設定」不回明文。

欄位：
- gemini_api_key：Gemini API 金鑰（覆寫 env）
- text_model / image_model：偏好模型 id（向後相容單值欄位；resolve() 的 legacy fallback）
- model_roles：逐角色覆寫（dict，M-3 設定頁逐角色管理；resolve() 最高優先讀此）。每筆值
  可為扁平字串（只覆 model id）或巢狀 {"provider":...,"model":...}（F9-3c 本機可插拔
  provider，如把某文字角色指到本機 ollama）
- brand_speaker / brand_org / brand_url：個人品牌（封面/結尾頁預設講者/單位/連結）
"""
from __future__ import annotations

import json
import threading

from core import config

_LOCK = threading.Lock()
_KNOWN = ("gemini_api_key", "text_model", "image_model", "model_roles",
          "brand_speaker", "brand_org", "brand_url")


def _clean_model_roles(v) -> dict:
    """只保留合法角色 → 有效覆寫；其餘（未知角色/空值/非 dict/未知 provider）丟棄。

    每筆值正規化為 JSON 可存形式（扁平 model-id 字串，或巢狀
    ``{"provider":...,"model":...}`` 帶 provider 覆寫＝F9-3c 本機可插拔）。解析委派
    ``core.models.clean_role_override``（與 ``resolve()`` 共用同一套解析，避免雙份分歧），
    防設定頁/API 塞進打錯字的角色/provider 或空值默默污染登錄表（呼應 resolve() 的 type guard）。
    """
    if not isinstance(v, dict):
        return {}
    from core.models import ROLES, clean_role_override
    out: dict = {}
    for role, spec in v.items():
        if role not in ROLES:
            continue
        cleaned = clean_role_override(role, spec)
        if cleaned is not None:
            out[role] = cleaned
    return out


def _load() -> dict:
    path = config.get_settings_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get_setting(key: str, default=None):
    """讀單一設定值；不存在回 default。"""
    return _load().get(key, default)


def get_all() -> dict:
    """全部設定（含明文 api key，僅供內部用；對外端點要遮罩）。"""
    return _load()


def update(patch: dict) -> dict:
    """合併寫入設定（只接受已知欄位；空字串視為清除該欄）。回更新後全集。"""
    with _LOCK:
        data = _load()
        for k, v in (patch or {}).items():
            if k not in _KNOWN:
                continue
            if k == "model_roles":
                cleaned = _clean_model_roles(v)
                if cleaned:
                    data[k] = cleaned          # 整批覆寫（前端送全集）
                else:
                    data.pop(k, None)          # 空 dict / 全無效 ＝ 清除逐角色覆寫
                continue
            if v is None or v == "":
                data.pop(k, None)
            else:
                data[k] = v
        with open(config.get_settings_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data


def public_view() -> dict:
    """對外安全視圖：api key 只回是否已設定（不回明文）。"""
    data = _load()
    return {
        "has_gemini_api_key": bool(data.get("gemini_api_key")),
        "text_model": data.get("text_model", ""),
        "image_model": data.get("image_model", ""),
        "model_roles": data.get("model_roles", {}),
        "brand_speaker": data.get("brand_speaker", ""),
        "brand_org": data.get("brand_org", ""),
        "brand_url": data.get("brand_url", ""),
    }
