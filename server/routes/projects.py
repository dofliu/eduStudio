"""routes/projects.py — Project 薄層端點（eduStudio 合併 PR-M1，MERGE_PLAN §3 Phase A）。

合併後是**單一 server、in-process**：Project 層建 job 不再走 HTTP service_client（strangler
舊作法），而是**直接 await 既有 routes/jobs.py:create_job**——同一份程式碼、同進程呼叫。
這樣 review gate 延續性（exam_pdf 預設停 awaiting_review，硬規則 #1）天然成立，因為走的
就是 jobs.create_job → JobStore.create → _resolve_default_review 那條原路，沒有任何透傳層
改寫 options 的機會。

端點：
- POST /projects                  建 Project
- GET  /projects                  列出
- GET  /projects/{pid}            取單一
- POST /projects/{pid}/jobs       in-process 建 job（reuse jobs.create_job）並掛進 jobs[]
- POST /projects/{pid}/artifacts  收 artifact（infoCard write-back 等）
- GET  /projects/{pid}/notebook   聚合視圖（sources/jobs/artifacts + counts）
- GET  /projects/{pid}/glossary   取該課術語表（F9-2，無則 404 與「project 不存在」區分）
- PUT  /projects/{pid}/glossary   覆寫該課術語表（reuse ProjectStore.save_glossary）

store 注入：仿 jobs.py 的 get_default_store 單例模式，提供 get_default_project_store()，
測試以 app.dependency_overrides 注入 tmp_path 隔離。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core import config
from core.glossary import Glossary
from core.project import (
    Artifact,
    ArtifactKind,
    ArtifactState,
    ProducedBy,
    Project,
    ProjectNotFoundError,
    ProjectStore,
    Source,
    SourceType,
)

from . import jobs as jobs_routes
from ..jobs import JobStore, get_default_store
from ..schemas import CreateJobRequest, CreateJobResponse

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------- store 單例（仿 jobs.py:get_default_store）----------
_default_project_store: ProjectStore | None = None


def get_default_project_store() -> ProjectStore:
    """共享 ProjectStore（lazy 建立，預設 root=config.PROJECTS_DIR）。

    測試以 app.dependency_overrides[get_default_project_store] 注入 tmp_path 隔離，
    不污染真實 projects/。
    """
    global _default_project_store
    if _default_project_store is None:
        _default_project_store = ProjectStore()
    return _default_project_store


# ---------- 請求模型 ----------
class CreateProjectRequest(BaseModel):
    """建 Project 的請求體。project_id 由 ProjectStore.safe_id 再過濾防 traversal。"""

    project_id: str
    title: str
    target_languages: list[str] = Field(default_factory=list)


class AddSourceRequest(BaseModel):
    """掛一筆來源素材到 Project（匯入 PDF/repo/url/影片/圖片/音訊）。"""

    type: SourceType
    path_or_url: str
    lang: str = config.CANONICAL_LANG
    source_id: str | None = None
    indexed: bool = False


class AddArtifactRequest(BaseModel):
    """收一筆 artifact（infoCard/translateGemma/autoSolver 產出回寫）。"""

    kind: ArtifactKind
    produced_by: ProducedBy
    state: ArtifactState = "draft"
    lang: str = config.CANONICAL_LANG
    artifact_id: str | None = None
    citations: list[str] = Field(default_factory=list)
    links: dict[str, str | None] | None = None


class NotebookView(BaseModel):
    """單一 Project 的聚合視圖。jobs 僅為 id 字串清單（真相在 JobStore）。"""

    project_id: str
    title: str
    target_languages: list[str]
    sources: list
    jobs: list[str]
    artifacts: list[Artifact]
    counts: dict[str, int]


# ---------- 端點 ----------
@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    req: CreateProjectRequest,
    store: ProjectStore = Depends(get_default_project_store),
) -> Project:
    """建立 Project。同 pid 已存在回 409（不靜默覆蓋既有資料）。"""
    try:
        return store.create(
            project_id=req.project_id,
            title=req.title,
            target_languages=req.target_languages,
        )
    except FileExistsError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


@router.get("", response_model=list[Project])
async def list_projects(
    store: ProjectStore = Depends(get_default_project_store),
) -> list[Project]:
    """列出所有 Project（依 project_id 排序）。"""
    return store.list()


@router.get("/{pid}", response_model=Project)
async def get_project(
    pid: str, store: ProjectStore = Depends(get_default_project_store)
) -> Project:
    """取單一 Project；不存在回 404。"""
    try:
        return store.get(pid)
    except ProjectNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {pid}") from e


@router.post(
    "/{pid}/jobs",
    response_model=CreateJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_job(
    pid: str,
    req: CreateJobRequest,
    project_store: ProjectStore = Depends(get_default_project_store),
    job_store: JobStore = Depends(get_default_store),
) -> CreateJobResponse:
    """in-process 建 job 並掛進 project.jobs[]。

    **review gate 延續性（硬規則 #1 / MERGE_PLAN R7）**：本端點不解析、不改寫 req.options，
    直接 await 既有 jobs_routes.create_job —— 走的就是 JobStore.create →
    _resolve_default_review 那條原路。exam_pdf 未顯式傳 require_review 時預設 True，停在
    awaiting_review。同一份程式碼、同進程，沒有透傳層繞過 review gate 的機會。
    """
    # project 必須存在才建 job（不對不存在的 pid 建 orphan job）。
    try:
        project_store.get(pid)
    except ProjectNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {pid}") from e

    # reuse 既有建 job 路徑（驗證 + store.create + review gate + schedule_job 全在裡面）。
    resp = await jobs_routes.create_job(req, store=job_store)
    project_store.add_job(pid, resp.job_id)
    return resp


@router.post(
    "/{pid}/artifacts",
    response_model=Artifact,
    status_code=status.HTTP_201_CREATED,
)
async def add_artifact(
    pid: str,
    req: AddArtifactRequest,
    store: ProjectStore = Depends(get_default_project_store),
) -> Artifact:
    """收一筆 artifact 寫進 Project（不存在的 pid 回 404）。"""
    try:
        return store.add_artifact(
            pid,
            kind=req.kind,
            produced_by=req.produced_by,
            state=req.state,
            lang=req.lang,
            artifact_id=req.artifact_id,
            citations=req.citations,
            links=req.links,
        )
    except ProjectNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {pid}") from e


@router.post(
    "/{pid}/sources",
    response_model=Source,
    status_code=status.HTTP_201_CREATED,
)
async def add_source(
    pid: str,
    req: AddSourceRequest,
    store: ProjectStore = Depends(get_default_project_store),
) -> Source:
    """掛一筆來源素材到 Project（不存在的 pid 回 404）。"""
    try:
        return store.add_source(
            pid,
            type=req.type,
            path_or_url=req.path_or_url,
            lang=req.lang,
            source_id=req.source_id,
            indexed=req.indexed,
        )
    except ProjectNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {pid}") from e


@router.delete("/{pid}/sources/{sid}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_source(
    pid: str, sid: str, store: ProjectStore = Depends(get_default_project_store)
) -> None:
    """從 Project 移除一筆來源素材；project 不存在或 source 不存在皆回 404。"""
    try:
        if not store.remove_source(pid, sid):
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"source 不存在: {sid}")
    except ProjectNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {pid}") from e


@router.get("/{pid}/notebook", response_model=NotebookView)
async def get_notebook(
    pid: str, store: ProjectStore = Depends(get_default_project_store)
) -> NotebookView:
    """聚合 Project 的 sources/jobs/artifacts 成單一視圖；不存在回 404。

    為什麼只列 jobs id 不展開遠端 job 細節：jobs 真相在 JobStore，此處只組裝呈現層，
    避免 N 次查詢拖慢頁面（要 job 細節走 GET /jobs/{id}）。
    """
    try:
        project = store.get(pid)
    except ProjectNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {pid}") from e

    return NotebookView(
        project_id=project.project_id,
        title=project.title,
        target_languages=project.target_languages,
        sources=project.sources,
        jobs=project.jobs,
        artifacts=project.artifacts,
        counts={
            "sources": len(project.sources),
            "jobs": len(project.jobs),
            "artifacts": len(project.artifacts),
        },
    )


# ---------- 課程術語表 glossary（F9-2：設定頁/API 編輯）----------
# 為什麼用 GET/PUT 而非 POST：glossary 是「一課一份、整張覆寫」的 idempotent 資源
# （UI 載入整張→改→存回整張），PUT 語意正好。CRUD 落在 ProjectStore.get_glossary /
# save_glossary（已於 F9-2 第二刀落地、含 RLock 與路徑慣例），這層只做 HTTP 薄轉接。
@router.get("/{pid}/glossary", response_model=Glossary)
async def get_glossary(
    pid: str, store: ProjectStore = Depends(get_default_project_store)
) -> Glossary:
    """取該課術語表。

    兩種 404 以 detail 區分，讓編輯 UI 能分辨「沒這門課」與「課在但還沒建術語表」：
    - project 不存在 → 404「project 不存在」（ProjectStore.get_glossary 內部先驗）。
    - glossary 尚未建立（無 glossary.json）→ 404「此課尚未建立 glossary」；UI 收到後
      可開一張空表讓老師起頭，再 PUT 落盤。
    """
    try:
        glossary = store.get_glossary(pid)
    except ProjectNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {pid}") from e
    if glossary is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"此課尚未建立 glossary: {pid}"
        )
    return glossary


@router.put("/{pid}/glossary", response_model=Glossary)
async def put_glossary(
    pid: str,
    glossary: Glossary,
    store: ProjectStore = Depends(get_default_project_store),
) -> Glossary:
    """整張覆寫該課術語表（不存在的 pid 回 404）。

    body 直接吃 `Glossary`（course + entries），pydantic 已在進來時驗過 term/course 非空
    （core.glossary 的 field_validator），故這層只需轉接落盤。glossary.course 與 pid 各自
    獨立——pid 是資料夾鍵、course 是人讀課名，不強制相等（沿 schema 設計）。
    """
    try:
        return store.save_glossary(pid, glossary)
    except ProjectNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {pid}") from e
