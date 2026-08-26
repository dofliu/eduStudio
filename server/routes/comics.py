"""Comic Production System API — Project 內的 file-first 漫畫工作流。"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from core import config
from core.comics import (
    Character,
    ComicConflictError,
    ComicGateError,
    ComicNotFoundError,
    ComicPage,
    ComicStore,
    Dialogue,
    EpisodeManifest,
    EvidenceSource,
    QARecord,
    Series,
    decode_data_url,
    make_mock_scene,
)
from core.infocards.gemini import generate_image_b64, generate_json

from .projects import get_default_project_store
from core.project import ProjectNotFoundError, ProjectStore


router = APIRouter(prefix="/projects/{pid}/comics", tags=["comics"])
_default_comic_store: ComicStore | None = None


def get_default_comic_store() -> ComicStore:
    global _default_comic_store
    if _default_comic_store is None:
        _default_comic_store = ComicStore()
    return _default_comic_store


def _ensure_project(pid: str, store: ProjectStore) -> None:
    try:
        store.get(pid)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {pid}") from exc


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ComicNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc).strip("'"))
    if isinstance(exc, ComicConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, ComicGateError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))


class CreateSeriesRequest(BaseModel):
    series_id: str
    title: str
    description: str = ""
    visual_bible: str = "cinematic industrial manga, clean line art, restrained cel shading"
    world_lock: str = ""
    characters: list[Character] = Field(default_factory=list)


class CreateEpisodeRequest(BaseModel):
    series_id: str
    story_id: str
    title: str
    version: str = "v0.1"
    week: str = ""
    audience: str = "大學生"
    page_count: int = Field(default=8, ge=1, le=80)
    story_brief: str = ""
    learning_objectives: list[str] = Field(default_factory=list)
    technical_topics: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)


class UpdateEpisodeRequest(BaseModel):
    updates: dict[str, Any]


class ForkVersionRequest(BaseModel):
    from_version: str
    new_version: str


class GenerateRequest(BaseModel):
    mock: bool = False
    model: str | None = None


class GenerateImagesRequest(GenerateRequest):
    page_numbers: list[int] = Field(default_factory=list)
    use_references: bool = True


class UploadAssetRequest(BaseModel):
    filename: str
    data_url: str
    kind: str
    provenance: str = "user_upload"
    asset_id: str | None = None


class SetStateRequest(BaseModel):
    target: str
    reason: str = ""


class PublishRequest(BaseModel):
    published_by: str
    channel: str = "internal_reader"


class ImportPackageRequest(BaseModel):
    package_path: str
    series_id: str


class _ScriptGen(BaseModel):
    title: str
    storySummary: str
    storyBeats: list[str]
    characterVisualBible: str


class _DialogueGen(BaseModel):
    speakerId: str
    text: str
    layoutMode: str = "AUTO"
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)
    w: float | None = Field(default=None, ge=0, le=1)
    h: float | None = Field(default=None, ge=0, le=1)
    tailX: float | None = Field(default=None, ge=0, le=1)
    tailY: float | None = Field(default=None, ge=0, le=1)


class _PageGen(BaseModel):
    pageNo: int
    beat: str
    sceneDescription: str
    camera: str
    learningPoint: str
    evidenceIds: list[str] = Field(default_factory=list)
    dialogues: list[_DialogueGen]
    altText: str


class _StoryboardGen(BaseModel):
    pages: list[_PageGen]


@router.get("/capabilities")
def comic_capabilities(pid: str, project_store: ProjectStore = Depends(get_default_project_store)) -> dict:
    _ensure_project(pid, project_store)
    try:
        import importlib.util

        word_shapes = bool(importlib.util.find_spec("win32com"))
    except (ImportError, ValueError):
        word_shapes = False
    return {
        "gemini_configured": bool(config.get_gemini_api_key()),
        "image_generation": True,
        "file_first": True,
        "pdf_export": True,
        "docx_export": True,
        "word_native_shapes_available": word_shapes,
        "docx_fallback": "editable_table",
        "reader": True,
        "qa_gate": True,
        "note": "外部 AI 缺少 API key 時會誠實失敗；mock asset 不可通過發布 gate。",
    }


@router.post("/series", response_model=Series, status_code=status.HTTP_201_CREATED)
def create_series(
    pid: str,
    req: CreateSeriesRequest,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> Series:
    _ensure_project(pid, project_store)
    try:
        return comic_store.create_series(Series(project_id=pid, **req.model_dump()))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/discover")
def discover_package(
    pid: str,
    req: ImportPackageRequest,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> dict:
    """唯讀掃描既有 episode package；不複製、不修改來源。"""
    _ensure_project(pid, project_store)
    try:
        # series_id 在 discovery 階段只作為後續匯入目標，不要求 package 屬於該系列。
        comic_store.get_series(pid, req.series_id)
        return comic_store.discover_package(req.package_path).model_dump()
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/import", response_model=EpisodeManifest, status_code=status.HTTP_201_CREATED)
def import_package(
    pid: str,
    req: ImportPackageRequest,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    """由既有 package 建立 normalized 副本；原資料夾保持唯讀不動。"""
    _ensure_project(pid, project_store)
    try:
        return comic_store.import_package(pid, req.series_id, req.package_path)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/series", response_model=list[Series])
def list_series(
    pid: str,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> list[Series]:
    _ensure_project(pid, project_store)
    return comic_store.list_series(pid)


@router.get("/series/{series_id}", response_model=Series)
def get_series(
    pid: str,
    series_id: str,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> Series:
    _ensure_project(pid, project_store)
    try:
        return comic_store.get_series(pid, series_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.put("/series/{series_id}", response_model=Series)
def update_series(
    pid: str,
    series_id: str,
    series: Series,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> Series:
    _ensure_project(pid, project_store)
    if series.project_id != pid or series.series_id != series_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path identity 與 body 不一致")
    try:
        return comic_store.save_series(series)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/episodes", response_model=EpisodeManifest, status_code=status.HTTP_201_CREATED)
def create_episode(
    pid: str,
    req: CreateEpisodeRequest,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        return comic_store.create_episode(EpisodeManifest(project_id=pid, **req.model_dump()))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/episodes", response_model=list[EpisodeManifest])
def list_episodes(
    pid: str,
    series_id: str | None = None,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> list[EpisodeManifest]:
    _ensure_project(pid, project_store)
    return comic_store.list_episodes(pid, series_id)


@router.get("/episodes/{story_id}", response_model=EpisodeManifest)
def get_episode(
    pid: str,
    story_id: str,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        return comic_store.get_episode(pid, story_id, version)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/episodes/{story_id}/versions", response_model=list[EpisodeManifest])
def list_episode_versions(
    pid: str,
    story_id: str,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> list[EpisodeManifest]:
    _ensure_project(pid, project_store)
    return comic_store.list_versions(pid, story_id)


@router.patch("/episodes/{story_id}", response_model=EpisodeManifest)
def update_episode(
    pid: str,
    story_id: str,
    req: UpdateEpisodeRequest,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        return comic_store.update_episode(pid, story_id, version, req.updates)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/episodes/{story_id}/fork", response_model=EpisodeManifest, status_code=status.HTTP_201_CREATED)
def fork_episode(
    pid: str,
    story_id: str,
    req: ForkVersionRequest,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        return comic_store.fork_version(pid, story_id, req.from_version, req.new_version)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/episodes/{story_id}/auto-layout", response_model=EpisodeManifest)
def auto_layout_episode(
    pid: str,
    story_id: str,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        return comic_store.auto_layout_episode(pid, story_id, version)
    except Exception as exc:
        raise _http_error(exc) from exc


def _script_prompt(episode: EpisodeManifest, series: Series) -> str:
    evidence = "\n".join(
        f"- {item.source_id}: {item.title}; supports={'; '.join(item.supported_claims)}; limits={'; '.join(item.limits)}"
        for item in episode.evidence
    ) or "- 尚無來源；不得自行補成已證實技術結論。"
    return f"""你是專業教學漫畫編劇。請輸出繁體中文 JSON，為可連載漫畫建立劇本草稿。
主題：{episode.title}
需求：{episode.story_brief}
受眾：{episode.audience}
頁數：{episode.page_count}
學習目標：{episode.learning_objectives}
技術主題：{episode.technical_topics}
角色：{episode.characters}
系列世界觀：{series.world_lock}
來源與限制：
{evidence}

storyBeats 優先使用 Hook、Trigger、First guess、Evidence gate、Branch、Controlled action、Verification、Debrief。
若頁數不是 8，請依頁數合併或展開，但不得跳過 evidence gate 與 debrief。
這是 teaching story，不是 operating instruction；未被來源支持的結論必須保留「待確認／依程序升級處理」。
"""


@router.post("/episodes/{story_id}/generate/script", response_model=EpisodeManifest)
def generate_script(
    pid: str,
    story_id: str,
    req: GenerateRequest,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        episode = comic_store.get_episode(pid, story_id, version)
        series = comic_store.get_series(pid, episode.series_id)
        if req.mock:
            beats = ["Hook", "Trigger", "First guess", "Evidence gate", "Branch", "Controlled action", "Verification", "Debrief"]
            data = {
                "title": episode.title,
                "storySummary": f"MOCK：{episode.story_brief or episode.title}",
                "storyBeats": [beats[i % len(beats)] for i in range(episode.page_count)],
                "characterVisualBible": "MOCK character bible；不得作正式 continuity evidence。",
            }
        else:
            data = generate_json(
                _script_prompt(episode, series),
                model=req.model,
                response_schema=_ScriptGen,
                station="comic-script",
            )
        parsed = _ScriptGen.model_validate(data)
        return comic_store.update_episode(
            pid,
            story_id,
            version,
            {
                "title": parsed.title or episode.title,
                "story_summary": parsed.storySummary,
                "story_beats": parsed.storyBeats,
                "character_visual_bible": parsed.characterVisualBible,
                "state": "BRIEF",
            },
        )
    except Exception as exc:
        raise _http_error(exc) from exc


def _storyboard_prompt(episode: EpisodeManifest) -> str:
    evidence_ids = [item.source_id for item in episode.evidence]
    return f"""你是教學漫畫分鏡師。請依劇本產出恰好 {episode.page_count} 頁的繁體中文 JSON storyboard。
標題：{episode.title}
摘要：{episode.story_summary}
節拍：{episode.story_beats}
角色：{episode.characters}
可引用 evidence IDs：{evidence_ids}

每頁要有 pageNo、beat、sceneDescription、camera、learningPoint、evidenceIds、dialogues、altText。
dialogues 每頁 1–3 句，每句只表達一件事；speakerId 必須是角色 ID 或 narrator。
每句 dialogue 可附 x、y、w、h、tailX、tailY（皆為 0–1 正規化座標）與 layoutMode=AUTO。
泡泡要依人物、視線與 negative space 分散在不同高度，不可每頁都固定排在最上方；tailX/tailY 指向說話者。
sceneDescription 要保留 34–38% integrated negative space，且不得要求生成任何可讀中文或 speech bubble。
altText 要能讓看不到圖片的讀者理解人物、動作與技術證據。
沒有來源支持時 evidenceIds 留空，對白不得把推論寫成已證實結果。
"""


def _mock_pages(episode: EpisodeManifest) -> list[_PageGen]:
    beats = episode.story_beats or ["Hook", "Trigger", "Evidence gate", "Debrief"]
    speakers = episode.characters or ["narrator"]
    return [
        _PageGen(
            pageNo=index,
            beat=beats[(index - 1) % len(beats)],
            sceneDescription=f"MOCK scene {index}: {episode.story_brief or episode.title}",
            camera="medium shot",
            learningPoint=(episode.learning_objectives or ["待教師確認學習目標"])[0],
            evidenceIds=[episode.evidence[0].source_id] if episode.evidence else [],
            dialogues=[
                _DialogueGen(
                    speakerId=speakers[(index - 1) % len(speakers)],
                    text=f"MOCK 對白 {index}；僅供流程測試。",
                    x=[0.06, 0.56, 0.08, 0.52][(index - 1) % 4],
                    y=[0.08, 0.25, 0.43, 0.58][(index - 1) % 4],
                    w=0.38,
                    h=0.13,
                    tailX=[0.30, 0.70][(index - 1) % 2],
                    tailY=0.78,
                )
            ],
            altText=f"MOCK 第 {index} 頁流程示意，尚未生成正式漫畫場景。",
        )
        for index in range(1, episode.page_count + 1)
    ]


@router.post("/episodes/{story_id}/generate/storyboard", response_model=EpisodeManifest)
def generate_storyboard(
    pid: str,
    story_id: str,
    req: GenerateRequest,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        episode = comic_store.get_episode(pid, story_id, version)
        data = {"pages": [item.model_dump() for item in _mock_pages(episode)]} if req.mock else generate_json(
            _storyboard_prompt(episode),
            model=req.model,
            response_schema=_StoryboardGen,
            station="comic-storyboard",
        )
        parsed = _StoryboardGen.model_validate(data)
        if len(parsed.pages) != episode.page_count:
            raise ComicGateError(f"AI 回傳 {len(parsed.pages)} 頁，預期 {episode.page_count} 頁；未寫入")
        pages = [
            ComicPage(
                page_no=item.pageNo,
                beat=item.beat,
                scene_id=f"scene_{item.pageNo:02d}",
                scene_description=item.sceneDescription,
                camera=item.camera,
                learning_point=item.learningPoint,
                evidence_ids=item.evidenceIds,
                dialogues=[
                    Dialogue(
                        dialogue_id=f"p{item.pageNo:02d}_d{idx:02d}",
                        speaker_id=dialog.speakerId,
                        text=dialog.text,
                        bubble_style="rounded_callout",
                        layout_mode="MANUAL" if str(dialog.layoutMode).upper() == "MANUAL" else "AUTO",
                        x=dialog.x if dialog.x is not None else (0.06 if idx % 2 else 0.56),
                        y=dialog.y if dialog.y is not None else (0.08 + ((item.pageNo + idx) % 3) * 0.19),
                        w=dialog.w if dialog.w is not None else 0.38,
                        h=dialog.h if dialog.h is not None else 0.13,
                        tail_x=dialog.tailX,
                        tail_y=dialog.tailY,
                    )
                    for idx, dialog in enumerate(item.dialogues, start=1)
                ],
                alt_text=item.altText,
            )
            for item in sorted(parsed.pages, key=lambda x: x.pageNo)
        ]
        if [page.page_no for page in pages] != list(range(1, episode.page_count + 1)):
            raise ComicGateError("AI storyboard 頁碼不連續；未寫入")
        return comic_store.update_episode(pid, story_id, version, {"pages": pages, "state": "STORYBOARD"})
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/episodes/{story_id}/compose-prompts", response_model=EpisodeManifest)
def compose_prompts(
    pid: str,
    story_id: str,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        return comic_store.compose_prompts(pid, story_id, version)
    except Exception as exc:
        raise _http_error(exc) from exc


def _reference_files(comic_store: ComicStore, episode: EpisodeManifest) -> list[dict]:
    refs: list[dict] = []
    for asset in episode.assets:
        if asset.kind not in {"character_anchor", "equipment_reference"}:
            continue
        path = comic_store.resolve_asset(episode, asset.asset_id)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        refs.append({"mimeType": mime, "data": base64.b64encode(path.read_bytes()).decode("ascii")})
        if len(refs) >= 4:
            break
    return refs


@router.post("/episodes/{story_id}/generate/images")
def generate_images(
    pid: str,
    story_id: str,
    req: GenerateImagesRequest,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> dict:
    _ensure_project(pid, project_store)
    try:
        episode = comic_store.get_episode(pid, story_id, version)
        wanted = set(req.page_numbers or [page.page_no for page in episode.pages])
        references = _reference_files(comic_store, episode) if req.use_references else []
        generated: list[int] = []
        failed: list[dict] = []
        for page in episode.pages:
            if page.page_no not in wanted:
                continue
            if not page.image_prompt:
                failed.append({"page_no": page.page_no, "error": "尚未 compose prompt"})
                continue
            try:
                data_url = make_mock_scene(page.page_no) if req.mock else generate_image_b64(
                    page.image_prompt,
                    model=req.model,
                    files=references,
                )
                if not data_url:
                    raise RuntimeError("AI 未回傳圖片")
                raw, suffix = decode_data_url(data_url)
                current = comic_store.attach_asset(
                    pid,
                    story_id,
                    version,
                    filename=f"scene_{page.page_no:02d}{suffix}",
                    data=raw,
                    kind="scene",
                    provenance="mock_placeholder" if req.mock else f"gemini:{req.model or 'configured-image-model'}",
                    asset_id=f"scene_{page.page_no:02d}_{uuid_suffix()}",
                    prompt_version=f"r{episode.revision}",
                )
                asset_id = current.assets[-1].asset_id
                episode = comic_store.set_page_asset(pid, story_id, version, page.page_no, asset_id)
                generated.append(page.page_no)
            except Exception as item_exc:  # 單頁失敗保留其他成功頁，供重試。
                failed.append({"page_no": page.page_no, "error": str(item_exc)})
        return {"episode": episode.model_dump(), "generated": generated, "failed": failed}
    except Exception as exc:
        raise _http_error(exc) from exc


def uuid_suffix() -> str:
    import uuid

    return uuid.uuid4().hex[:6]


@router.post("/episodes/{story_id}/assets", response_model=EpisodeManifest)
def upload_asset(
    pid: str,
    story_id: str,
    req: UploadAssetRequest,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        data, suffix = decode_data_url(req.data_url)
        stem = Path(req.filename).stem or "asset"
        return comic_store.attach_asset(
            pid,
            story_id,
            version,
            filename=f"{stem}{suffix}",
            data=data,
            kind=req.kind,
            provenance=req.provenance,
            asset_id=req.asset_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/episodes/{story_id}/{version}/assets/{asset_id}")
def get_asset(
    pid: str,
    story_id: str,
    version: str,
    asset_id: str,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> FileResponse:
    _ensure_project(pid, project_store)
    try:
        episode = comic_store.get_episode(pid, story_id, version)
        return FileResponse(comic_store.resolve_asset(episode, asset_id))
    except Exception as exc:
        raise _http_error(exc) from exc


@router.put("/episodes/{story_id}/evidence/{source_id}", response_model=EpisodeManifest)
def put_evidence(
    pid: str,
    story_id: str,
    source_id: str,
    evidence: EvidenceSource,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    if source_id != evidence.source_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path source_id 與 body 不一致")
    try:
        return comic_store.add_evidence(pid, story_id, version, evidence)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.put("/episodes/{story_id}/qa/{gate}", response_model=EpisodeManifest)
def put_qa(
    pid: str,
    story_id: str,
    gate: str,
    record: QARecord,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    if gate != record.gate:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "path gate 與 body 不一致")
    try:
        return comic_store.add_qa_record(pid, story_id, version, record)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/episodes/{story_id}/validation")
def validation(
    pid: str,
    story_id: str,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> dict:
    _ensure_project(pid, project_store)
    try:
        return comic_store.validate_episode(comic_store.get_episode(pid, story_id, version)).model_dump()
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/episodes/{story_id}/state", response_model=EpisodeManifest)
def set_state(
    pid: str,
    story_id: str,
    req: SetStateRequest,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        return comic_store.transition(pid, story_id, version, req.target, req.reason)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/episodes/{story_id}/exports/{kind}")
def create_export(
    pid: str,
    story_id: str,
    kind: str,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> dict:
    _ensure_project(pid, project_store)
    try:
        if kind == "html":
            episode, path = comic_store.export_html(pid, story_id, version)
            mode = "reader"
        elif kind == "pdf":
            episode, path = comic_store.export_pdf(pid, story_id, version)
            mode = "a4_reading"
        elif kind == "docx":
            episode, path, mode = comic_store.export_docx(pid, story_id, version)
        elif kind == "source":
            episode = comic_store.get_episode(pid, story_id, version)
            path = comic_store.create_source_zip(pid, story_id, version)
            mode = "file_first_source_pack"
        else:
            raise ValueError("kind 僅支援 html/pdf/docx/source")
        return {
            "kind": kind,
            "mode": mode,
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "download_url": f"/projects/{pid}/comics/episodes/{story_id}/{version}/exports/{path.name}",
            "episode": episode.model_dump(),
        }
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/episodes/{story_id}/{version}/exports/{filename}")
def download_export(
    pid: str,
    story_id: str,
    version: str,
    filename: str,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> FileResponse:
    _ensure_project(pid, project_store)
    try:
        comic_store.get_episode(pid, story_id, version)
        root = (comic_store.episode_dir(pid, story_id, version) / "exports").resolve()
        path = (root / Path(filename).name).resolve()
        path.relative_to(root)
        if not path.is_file():
            raise ComicNotFoundError(f"export 不存在: {filename}")
        return FileResponse(path, filename=path.name)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/episodes/{story_id}/publish", response_model=EpisodeManifest)
def publish_episode(
    pid: str,
    story_id: str,
    req: PublishRequest,
    version: str = "v0.1",
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        episode = comic_store.publish(pid, story_id, version, published_by=req.published_by, channel=req.channel)
        # Project library 只存 link，不複製 artifact；版本與真相仍在 ComicStore。
        project_store.add_artifact(
            pid,
            kind="comic",
            produced_by="eduStudio",
            state="published",
            artifact_id=f"comic_{episode.story_id}_{version.replace('.', '_')}",
            links={"file": episode.releases[-1].url, "youtube": None},
        )
        return episode
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/episodes/{story_id}/{version}/releases/{release_id}/withdraw", response_model=EpisodeManifest)
def withdraw_release(
    pid: str,
    story_id: str,
    version: str,
    release_id: str,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> EpisodeManifest:
    _ensure_project(pid, project_store)
    try:
        return comic_store.withdraw_release(pid, story_id, version, release_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/reader/{story_id}", response_class=HTMLResponse)
def reader(
    pid: str,
    story_id: str,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> HTMLResponse:
    _ensure_project(pid, project_store)
    try:
        candidates = [
            item
            for item in comic_store.list_versions(pid, story_id)
            if any(release.withdrawn_at is None for release in item.releases)
        ]
        if not candidates:
            raise ComicNotFoundError("尚無已發布版本")
        episode = max(
            candidates,
            key=lambda item: max(
                release.published_at for release in item.releases if release.withdrawn_at is None
            ),
        )
        prefix = f"/projects/{pid}/comics/episodes/{story_id}/{episode.version}/assets/"
        series = comic_store.get_series(pid, episode.series_id)
        speaker_names = {item.character_id: item.name for item in series.characters}
        return HTMLResponse(
            comic_store.build_reader_html(
                episode,
                asset_prefix=prefix,
                speaker_names=speaker_names,
            )
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/reader/series/{series_id}", response_class=HTMLResponse)
def series_archive(
    pid: str,
    series_id: str,
    project_store: ProjectStore = Depends(get_default_project_store),
    comic_store: ComicStore = Depends(get_default_comic_store),
) -> HTMLResponse:
    _ensure_project(pid, project_store)
    try:
        series = comic_store.get_series(pid, series_id)
        # 草稿新版本不應讓既有 stable release 從 archive 消失；每個 story
        # 取所有版本中最近一次仍有效的 release。
        released: list[EpisodeManifest] = []
        for latest in comic_store.list_episodes(pid, series_id):
            candidates = [
                item
                for item in comic_store.list_versions(pid, latest.story_id)
                if item.series_id == series_id
                and any(release.withdrawn_at is None for release in item.releases)
            ]
            if candidates:
                released.append(
                    max(
                        candidates,
                        key=lambda item: max(
                            release.published_at
                            for release in item.releases
                            if release.withdrawn_at is None
                        ),
                    )
                )
        return HTMLResponse(comic_store.build_series_archive_html(series, released))
    except Exception as exc:
        raise _http_error(exc) from exc
