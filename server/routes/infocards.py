"""routes/infocards.py — infoCard 後端端點（eduStudio 合併 Phase C-4）。

對齊 infoCard server.ts 的 /api 契約，前端 build 成靜態檔後改打本 server。後端統一呼叫
Gemini（不再瀏覽器直呼）。本批上 comic + poster 兩模式 + health + share（SQLite）；
presentation 移植進行中，暫回 501。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.infocards import (
    comic_service,
    infographic_service,
    poster_service,
    presentation_service,
)
from core.infocards.models import DEFAULT_IMAGE_MODEL, DEFAULT_TEXT_MODEL
from core.infocards.share_store import get_share_store

router = APIRouter(prefix="/api", tags=["infocards"])

_SUPPORTED_MODES = ("presentation", "poster", "comic", "infographic")


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
    selectedOutline: dict | None = None
    imageModel: str = DEFAULT_IMAGE_MODEL
    textModel: str = DEFAULT_TEXT_MODEL


class ShareRequest(BaseModel):
    type: str
    title: str = ""
    data: dict | list | None = None


class ExportPptxRequest(BaseModel):
    """把生成的簡報 PresentationData 匯出成 .pptx。data 接 /api/generate 回的 data 物件。"""

    data: dict
    filename: str = "presentation"


class RefineSlideRequest(BaseModel):
    """單頁微調：slide 為要改的投影片，instruction 為修改指令。"""

    slide: dict
    instruction: str
    style: str = "professional"
    customStylePrompt: str = ""
    persona: dict | None = None
    slideIndex: int | None = None
    totalSlides: int | None = None
    imageModel: str = DEFAULT_IMAGE_MODEL
    textModel: str = DEFAULT_TEXT_MODEL


@router.get("/usage")
def usage_summary() -> dict:
    """Gemini 用量真實統計（成本面板）。涵蓋視覺站 + 在地化的呼叫；budget 為設定值。"""
    from core.usage import get_usage_store

    s = get_usage_store().summary()
    s["budget"] = 30.0           # 月預算（設定值，無真實來源）
    s["note"] = "已涵蓋視覺站／在地化的 Gemini 呼叫；影片 render pipeline 用量另計"
    return s


@router.get("/health")
def health() -> dict:
    """infoCard 風格健康檢查（模式清單 + 服務資訊）。"""
    return {
        "status": "ok",
        "service": "infocards",
        "modes": list(_SUPPORTED_MODES),
        "implemented": ["comic", "poster", "infographic", "presentation"],
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

    if mode in ("infographic", "card"):
        data = infographic_service.generate_infographic_data(
            req.text, req.style, custom=req.customStylePrompt,
            aspect_ratio=req.aspectRatio, model=req.textModel)
        data = infographic_service.generate_infographic_images(
            data, model=req.imageModel, custom=req.customStylePrompt)
        return {"success": True, "type": "infographic", "data": data.model_dump()}

    if mode == "poster":
        result = poster_service.generate_poster(
            req.text, req.style, custom_style_prompt=req.customStylePrompt,
            aspect_ratio=req.aspectRatio, refinement=req.refinement,
            density=req.density, image_model=req.imageModel)
        return {"success": True, "type": "poster",
                "imageUrl": result["imageUrl"], "prompt": result["prompt"]}

    if mode == "outline":
        # 兩階段 Stage 1：產 3 個大綱方案（低成本，不生圖）。
        outlines = presentation_service.generate_presentation_outlines(
            req.text, req.style, custom=req.customStylePrompt,
            slide_count=req.slideCount, model=req.textModel)
        return {"success": True, "type": "outline",
                "data": {"outlines": [o.model_dump() for o in outlines]}}

    if mode == "presentation":
        data = presentation_service.generate_presentation_data(
            req.text, req.style, custom=req.customStylePrompt,
            slide_count=req.slideCount, density=req.density,
            typography=req.typography or "modern", selected_outline=req.selectedOutline,
            model=req.textModel)
        data = presentation_service.generate_presentation_images(
            data, style=req.style, custom=req.customStylePrompt, image_model=req.imageModel)
        return {"success": True, "type": "presentation", "data": data.model_dump()}

    raise HTTPException(status_code=400, detail=f"未知 mode：{req.mode}（支援 {_SUPPORTED_MODES}）")


@router.post("/refine")
def refine_slide(req: RefineSlideRequest) -> dict:
    """單頁微調：依指令重生該頁並套用與整份生成一致的後處理。回 refined slide。"""
    from core.infocards import refine_service

    slide = refine_service.refine_presentation_slide(
        req.slide, req.instruction, style=req.style, custom=req.customStylePrompt,
        persona=req.persona, slide_index=req.slideIndex, total_slides=req.totalSlides,
        model=req.textModel, image_model=req.imageModel)
    return {"success": True, "slide": slide.model_dump()}


@router.post("/export/pptx")
def export_pptx(req: ExportPptxRequest) -> Response:
    """簡報 PresentationData → .pptx 下載（python-pptx，座標對齊 slideMasters）。"""
    from core.infocards.pptx_export import build_pptx

    from urllib.parse import quote

    try:
        blob = build_pptx(req.data)
    except Exception as e:  # 匯出失敗回 400 帶原因，不讓 500 把細節吞掉
        raise HTTPException(status_code=400, detail=f"PPTX 匯出失敗：{e}") from e
    name = (req.filename or "presentation").replace('"', "").replace("\\", "").strip() or "presentation"
    # Content-Disposition 走 latin-1：中文檔名用 RFC 5987 filename*（UTF-8 百分號編碼），
    # 另給純 ASCII fallback 給不支援 filename* 的舊客戶端。
    ascii_name = name.encode("ascii", "ignore").decode() or "presentation"
    disp = f"attachment; filename=\"{ascii_name}.pptx\"; filename*=UTF-8''{quote(name)}.pptx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": disp},
    )


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
