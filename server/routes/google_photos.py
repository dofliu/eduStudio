"""Google 相簿 (Photos Picker) 路由 — 連相簿 → 選照片 → 產相片簡報/影片。

流程 (對應 core.google_photos):
    GET  /google-photos/status              是否已 OAuth 授權 (未授權回 authorized=false)
    POST /google-photos/session             建 Picker session, 回 picker_uri 給使用者開
    GET  /google-photos/session/{id}         輪詢是否已選好照片 (media_items_set)
    POST /google-photos/generate            用選好的 session 建 job → 跑 vision+deck+render

未授權時 status 回 authorized=false; session/generate 回 412 (提示先在本機
`python -m tools.photos_auth` 授權一次), 對齊 youtube 的 412 慣例。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..jobs import JobStore, get_default_store
from ..ratelimit import rate_limit
from ..runner import schedule_job
from ..schemas import CreateJobRequest, CreateJobResponse, JobOptions, JobSource, SourceType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/google-photos", tags=["google_photos"])


def _bootstrap_412():
    return HTTPException(
        status.HTTP_412_PRECONDITION_FAILED,
        "尚未授權 Google 相簿。請在伺服器本機執行一次: python -m tools.photos_auth",
    )


@router.get("/status")
async def photos_status() -> dict:
    """是否已完成 Google 相簿 OAuth 授權 (未授權不報錯, 回 authorized=false)。"""
    from core.google_photos import OAuthBootstrapRequired, get_photos_credentials
    try:
        get_photos_credentials(allow_interactive=False)
        return {"authorized": True}
    except OAuthBootstrapRequired:
        return {"authorized": False}
    except Exception as e:  # noqa: BLE001
        logger.warning("photos status 檢查失敗: %s", e)
        return {"authorized": False, "error": str(e)}


@router.post("/session")
async def create_pick_session() -> dict:
    """建立 Picker session, 回 picker_uri (給使用者在新分頁開啟挑照片)。"""
    from core.google_photos import OAuthBootstrapRequired, create_session
    try:
        s = create_session()
    except OAuthBootstrapRequired:
        raise _bootstrap_412()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"建立 Picker session 失敗: {e}")
    return {
        "session_id": s.get("id"),
        "picker_uri": s.get("pickerUri"),
        "media_items_set": bool(s.get("mediaItemsSet")),
        "polling_config": s.get("pollingConfig"),
    }


@router.get("/session/{session_id}")
async def poll_pick_session(session_id: str) -> dict:
    """輪詢 session: 使用者是否已選好照片 (media_items_set=true 才能 generate)。"""
    from core.google_photos import OAuthBootstrapRequired, get_session
    try:
        s = get_session(session_id)
    except OAuthBootstrapRequired:
        raise _bootstrap_412()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"讀取 session 失敗: {e}")
    return {"session_id": session_id, "media_items_set": bool(s.get("mediaItemsSet"))}


class GenerateRequest(BaseModel):
    session_id: str
    title_hint: str = ""
    max_select: int | None = Field(default=None, description="最多保留幾張 (None=全留)")
    require_review: bool = Field(default=False, description="產 deck 後停下讓你編輯 caption 再渲染")
    mock: bool = False

    model_config = {"extra": "allow"}


@router.post("/generate", response_model=CreateJobResponse,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit)])
async def generate_from_session(
    req: GenerateRequest, store: JobStore = Depends(get_default_store),
) -> CreateJobResponse:
    """用選好的 Picker session 建一個 google_photos job → 走 vision+deck+render。

    完成後: 影片 = job artifacts 的 mp4; PPTX = GET /jobs/{id}/pptx; 也可在
    /app SlideEditor 編 caption 後重渲染。
    """
    if not req.session_id.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺 session_id")

    rec = store.create(CreateJobRequest(
        source_type=SourceType.GOOGLE_PHOTOS,
        source=JobSource(session_id=req.session_id.strip()),
        options=JobOptions(
            mock=bool(req.mock),
            require_review=req.require_review,
            photo_title_hint=req.title_hint or None,
            photo_max_select=req.max_select,
        ),
    ))
    schedule_job(store, rec.id)
    return CreateJobResponse(job_id=rec.id, state=rec.state, status_url=f"/jobs/{rec.id}")
