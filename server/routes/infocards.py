"""routes/infocards.py — infoCard 後端端點（eduStudio 合併 Phase C-4）。

對齊 infoCard server.ts 的 /api 契約，前端 build 成靜態檔後改打本 server。後端統一呼叫
Gemini（不再瀏覽器直呼）。本批上 comic + poster 兩模式 + health + share（SQLite）；
presentation 移植進行中，暫回 501。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.infocards import comic_service, poster_service
from core.infocards.models import DEFAULT_IMAGE_MODEL, DEFAULT_TEXT_MODEL
from core.infocards.share_store import get_share_store

router = APIRouter(prefix="/api", tags=["infocards"])

_SUPPORTED_MODES = ("presentation", "poster", "comic")


class GenerateRequest(BaseModel):
    """/api/generate 請求（對齊 infoCard server.ts，常用欄位）。"""

    mode: str
    text: str = ""
    style: str = "professional"
    customStylePrompt: str = ""
    slideCount: int = 10
    panels: int = 4
    typography: str | None = None
    density: str = "balanced"
    aspectRatio: str = "vertical"
    refinement: str = ""
    imageModel: str = DEFAULT_IMAGE_MODEL
    textModel: str = DEFAULT_TEXT_MODEL


class ShareRequest(BaseModel):
    type: str
    title: str = ""
    data: dict | list | None = None


@router.get("/health")
def health() -> dict:
    """infoCard 風格健康檢查（模式清單 + 服務資訊）。"""
    return {
        "status": "ok",
        "service": "infocards",
        "modes": list(_SUPPORTED_MODES),
        "implemented": ["comic", "poster"],   # presentation 移植進行中
    }


@router.post("/generate")
def generate(req: GenerateRequest) -> dict:
    """生成簡報/海報/漫畫。後端呼叫 Gemini（comic/poster 已實作）。"""
    mode = req.mode.lower()
    if mode == "comic":
        data = comic_service.generate_comic_script(
            req.text, req.style, custom=req.customStylePrompt,
            panels=req.panels, model=req.textModel)
        data = comic_service.generate_comic_images(data, model=req.imageModel,
                                                   custom=req.customStylePrompt)
        return {"success": True, "type": "comic", "data": data.model_dump()}

    if mode == "poster":
        result = poster_service.generate_poster(
            req.text, req.style, custom_style_prompt=req.customStylePrompt,
            aspect_ratio=req.aspectRatio, refinement=req.refinement,
            density=req.density, image_model=req.imageModel)
        return {"success": True, "type": "poster",
                "imageUrl": result["imageUrl"], "prompt": result["prompt"]}

    if mode == "presentation":
        # presentationService.ts 拉約 10 helper，移植進行中（MERGE_PLAN §5.6）。
        raise HTTPException(status_code=501, detail="presentation 模式移植進行中")

    raise HTTPException(status_code=400, detail=f"未知 mode：{req.mode}（支援 {_SUPPORTED_MODES}）")


@router.post("/share", status_code=201)
def create_share(req: ShareRequest) -> dict:
    """建立分享連結（7 天，SQLite 持久化）。回 id 與相對 URL。"""
    share_id = get_share_store().create(req.type, req.title, req.data)
    return {"id": share_id, "url": f"/api/share/{share_id}"}


@router.get("/share/{share_id}")
def get_share(share_id: str) -> dict:
    """取分享內容；不存在或過期回 404。"""
    item = get_share_store().get(share_id)
    if item is None:
        raise HTTPException(status_code=404, detail="分享不存在或已過期")
    return item
