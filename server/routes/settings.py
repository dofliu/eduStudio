"""eduStudio 設定頁端點（個人品牌 / API key / 模型選擇）。

GET  /settings         安全視圖（api key 只回是否已設定）+ 可選模型清單
POST /settings         合併寫入設定（patch；空字串清除）
api key 不回明文（公開視圖遮罩）。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from core import settings as settings_store
from core.infocards.models import image_model_options, text_model_options
from core.models import role_catalog

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsPatch(BaseModel):
    """設定頁可改欄位（全 optional；空字串＝清除）。"""

    gemini_api_key: str | None = None
    text_model: str | None = None
    image_model: str | None = None
    model_roles: dict[str, str] | None = None    # 逐角色 model id 覆寫（M-3）；{} ＝清除
    brand_speaker: str | None = None
    brand_org: str | None = None
    brand_url: str | None = None


def _payload() -> dict:
    view = settings_store.public_view()
    view["text_models"] = text_model_options()    # [{id,label,description}]
    view["image_models"] = image_model_options()
    view["roles"] = role_catalog()                 # [{role,label,kind,default}] 逐角色管理用
    return view


@router.get("")
def get_settings() -> dict:
    """目前設定（遮罩 api key）+ 可選模型清單。"""
    return _payload()


@router.post("")
def update_settings(patch: SettingsPatch) -> dict:
    """合併寫入設定，回更新後的安全視圖。"""
    settings_store.update(patch.model_dump(exclude_none=True))
    return _payload()
