"""routes/infocards.py — infoCard 後端端點（eduStudio 合併 Phase C-4）。

對齊 infoCard server.ts 的 /api 契約，前端 build 成靜態檔後改打本 server。後端統一呼叫
Gemini（不再瀏覽器直呼）。本批上 comic + poster 兩模式 + health + share（SQLite）；
presentation 移植進行中，暫回 501。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ..ratelimit import rate_limit
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
    files: list[dict] = Field(default_factory=list)   # 多模態參考檔 [{mimeType, data(base64)}]
    imageModel: str = ""   # 空＝採設定頁/預設（見 generate 解析）
    textModel: str = ""
    projectId: str = ""    # 可選：歸屬的 Project（一課一工作空間），空＝只存全域素材庫
    # 簡報受眾／語氣引導（對齊 infoCard brandConfig；空字串＝不指定）。
    animation: str = "fade"
    audience: str = ""
    purpose: str = ""
    tone: str = ""
    visualEmphasis: str = ""

    def _steer(self) -> dict:
        return {"audience": self.audience, "purpose": self.purpose,
                "tone": self.tone, "visualEmphasis": self.visualEmphasis}


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


class RefineSectionRequest(BaseModel):
    """資訊圖卡單區微調：section 為要改的區塊，instruction 為修改指令。"""

    section: dict
    instruction: str
    imageModel: str = DEFAULT_IMAGE_MODEL
    textModel: str = DEFAULT_TEXT_MODEL
    regenerateImage: bool = True


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


def _resolve_models(req: "GenerateRequest") -> tuple[str, str]:
    """模型解析優先序：請求顯式 > 設定頁 > 程式預設。"""
    from core.settings import get_setting
    tm = req.textModel or get_setting("text_model") or DEFAULT_TEXT_MODEL
    im = req.imageModel or get_setting("image_model") or DEFAULT_IMAGE_MODEL
    return tm, im


def _lib_title(req: "GenerateRequest", fallback: str) -> str:
    """素材庫標題：取內容第一行（截 40 字），無內容則用 fallback。"""
    raw = (req.text or "").strip()
    first = raw.splitlines()[0][:40] if raw else ""
    return first or fallback


def _auto_save_library(asset_type: str, title: str, data: dict, thumb: str = "") -> str | None:
    """成功生成 → 自動寫進視覺素材庫（#6），回 library id（給 Project 歸屬連結用）。
    失敗只記 log 回 None，絕不讓存庫拖垮生成回應。"""
    try:
        from core.infocards.visual_library import get_visual_library
        return get_visual_library().add(asset_type, title, data, thumb=thumb)
    except Exception:  # noqa: BLE001 — 存庫是加值，壞了不能影響主流程
        import logging
        logging.getLogger("infocards").warning("視覺素材庫自動保存失敗", exc_info=True)
        return None


# 視覺成品型別 → Project ArtifactKind（一課一工作空間歸屬）。
_ARTIFACT_KIND = {"poster": "image", "presentation": "deck", "infographic": "infographic"}


def _attach_to_project(project_id: str, asset_type: str, title: str, library_id: str | None) -> None:
    """有帶 project_id 且存庫成功 → 把成品掛進 Project.artifacts[]，links 連回素材庫 id。
    Project 不存在/出錯只記 log，不讓歸屬失敗拖垮生成。"""
    if not project_id or not library_id:
        return
    try:
        from .projects import get_default_project_store
        get_default_project_store().add_artifact(
            project_id, kind=_ARTIFACT_KIND.get(asset_type, "image"),
            produced_by="infoCard", state="draft",
            links={"library_id": library_id, "title": title},
        )
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger("infocards").warning("成品歸屬 Project 失敗", exc_info=True)


def _first_slide_thumb(deck: dict) -> str:
    """簡報 deck → 首張有圖 slide 的 imageUrl（素材庫縮圖）；無則空字串。"""
    for s in deck.get("slides") or []:
        if s.get("imageUrl"):
            return s["imageUrl"]
    return ""


@router.post("/generate", dependencies=[Depends(rate_limit)])
def generate(req: GenerateRequest) -> dict:
    """生成簡報/海報/漫畫。後端呼叫 Gemini（comic/poster 已實作）。"""
    mode = req.mode.lower()
    text_model, image_model = _resolve_models(req)
    if mode == "comic":
        data = comic_service.generate_comic_script(
            req.text, req.style, custom=req.customStylePrompt,
            panels=req.panels, model=text_model, files=req.files)
        data = comic_service.generate_comic_images(data, model=image_model,
                                                   custom=req.customStylePrompt)
        return {"success": True, "type": "comic", "data": data.model_dump()}

    if mode in ("infographic", "card"):
        data = infographic_service.generate_infographic_data(
            req.text, req.style, custom=req.customStylePrompt,
            aspect_ratio=req.aspectRatio, model=text_model, files=req.files)
        data = infographic_service.generate_infographic_images(
            data, model=req.imageModel, custom=req.customStylePrompt)
        dd = data.model_dump()
        title = dd.get("mainTitle") or _lib_title(req, "資訊圖卡")
        lid = _auto_save_library("infographic", title, dd, thumb=_first_slide_thumb(dd))
        _attach_to_project(req.projectId, "infographic", title, lid)
        return {"success": True, "type": "infographic", "data": dd}

    if mode == "poster":
        result = poster_service.generate_poster(
            req.text, req.style, custom_style_prompt=req.customStylePrompt,
            aspect_ratio=req.aspectRatio, refinement=req.refinement,
            density=req.density, image_model=image_model, files=req.files)
        if result["imageUrl"]:   # 生圖成功才存（空＝失敗，不存）
            title = _lib_title(req, "圖卡 · 海報")
            lid = _auto_save_library("poster", title,
                                     {"imageUrl": result["imageUrl"], "prompt": result["prompt"]},
                                     thumb=result["imageUrl"])
            _attach_to_project(req.projectId, "poster", title, lid)
        return {"success": True, "type": "poster",
                "imageUrl": result["imageUrl"], "prompt": result["prompt"]}

    if mode == "outline":
        # 兩階段 Stage 1：產 3 個大綱方案（低成本，不生圖）。
        outlines = presentation_service.generate_presentation_outlines(
            req.text, req.style, custom=req.customStylePrompt,
            slide_count=req.slideCount, steer=req._steer(), model=text_model, files=req.files)
        return {"success": True, "type": "outline",
                "data": {"outlines": [o.model_dump() for o in outlines]}}

    if mode == "presentation":
        data = presentation_service.generate_presentation_data(
            req.text, req.style, custom=req.customStylePrompt,
            slide_count=req.slideCount, density=req.density,
            typography=req.typography or "modern", animation=req.animation,
            selected_outline=req.selectedOutline, steer=req._steer(),
            model=text_model, files=req.files)
        data = presentation_service.generate_presentation_images(
            data, style=req.style, custom=req.customStylePrompt, image_model=image_model)
        dd = data.model_dump()
        title = dd.get("mainTitle") or _lib_title(req, "教學簡報")
        lid = _auto_save_library("presentation", title, dd, thumb=_first_slide_thumb(dd))
        _attach_to_project(req.projectId, "presentation", title, lid)
        return {"success": True, "type": "presentation", "data": dd}

    raise HTTPException(status_code=400, detail=f"未知 mode：{req.mode}（支援 {_SUPPORTED_MODES}）")


@router.get("/visual-library")
def visual_library_list() -> dict:
    """視覺素材庫清單（新到舊，含縮圖，不含完整 data）。"""
    from core.infocards.visual_library import get_visual_library

    return {"items": get_visual_library().list()}


@router.get("/visual-library/{asset_id}")
def visual_library_get(asset_id: str) -> dict:
    """取單筆完整成品（含 data，供重新檢視/下載/分享）。"""
    from core.infocards.visual_library import get_visual_library

    item = get_visual_library().get(asset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="素材不存在")
    return item


@router.delete("/visual-library/{asset_id}")
def visual_library_delete(asset_id: str) -> dict:
    """刪除一筆素材。"""
    from core.infocards.visual_library import get_visual_library

    return {"deleted": get_visual_library().delete(asset_id)}


@router.post("/refine", dependencies=[Depends(rate_limit)])
def refine_slide(req: RefineSlideRequest) -> dict:
    """單頁微調：依指令重生該頁並套用與整份生成一致的後處理。回 refined slide。"""
    from core.infocards import refine_service

    slide = refine_service.refine_presentation_slide(
        req.slide, req.instruction, style=req.style, custom=req.customStylePrompt,
        persona=req.persona, slide_index=req.slideIndex, total_slides=req.totalSlides,
        model=req.textModel, image_model=req.imageModel)
    return {"success": True, "slide": slide.model_dump()}


@router.post("/refine-section", dependencies=[Depends(rate_limit)])
def refine_section(req: RefineSectionRequest) -> dict:
    """資訊圖卡單區微調：依指令重生該區塊（title/content/iconType/圖），回 refined section。"""
    from core.infocards import refine_service

    section = refine_service.refine_infographic_section(
        req.section, req.instruction,
        model=req.textModel, image_model=req.imageModel,
        regenerate_image=req.regenerateImage)
    return {"success": True, "section": section.model_dump()}


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
