"""/jobs API routes — 把 server/jobs.py + runner.py 接到 FastAPI。

端點清單:
    POST   /jobs                          建立並排程
    GET    /jobs                          列出 (created_at desc)
    GET    /jobs/{id}                     取單一狀態
    DELETE /jobs/{id}                     刪除 (含磁碟資料)
    GET    /jobs/{id}/draft               取 deck.json (review / done 階段)
    PUT    /jobs/{id}/draft               覆寫 deck.json (僅 awaiting_review)
    GET    /jobs/{id}/outline              取 outline.json (iter 81 D1 v1)
    GET    /jobs/{id}/icon-suggestions    批次 icon 建議 (iter 107 E2-6 backend)
    GET    /jobs/{id}/image-frames        批次 image_frames summary (iter 109 E1-4 backend)
    POST   /jobs/{id}/approve             從 awaiting_review 進入 render
    GET    /jobs/{id}/artifacts/{name}    下載產物檔
    GET    /jobs/{id}/versions            列出歷次歸檔舊版 artifacts (F9-4)
    GET    /jobs/{id}/versions/{v}/artifacts/{name}  下載指定版本 artifact (F9-4)
    GET    /jobs/{id}/images/{name}       下載 song 逐段生圖 (SONG M3e-3 預覽)
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse

from core.icon_picker import suggest_for_deck
from core.image_frames import summarize_for_deck

from ..jobs import JobStore, get_default_store
from ..path_safety import safe_join
from ..ratelimit import rate_limit
from ..runner import schedule_job, schedule_render, schedule_section_render
from ..schemas import (
    CreateJobRequest,
    CreateJobResponse,
    JobListResponse,
    JobRecord,
    JobState,
    UpdateDeckRequest,
    utc_now,
)


router = APIRouter(prefix="/jobs", tags=["jobs"])



def _require_job(job_id: str, store: JobStore = Depends(get_default_store)) -> JobRecord:
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    return rec


# ---------- CRUD ----------

@router.post(
    "",
    response_model=CreateJobResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit)],
)
async def create_job(req: CreateJobRequest, store: JobStore = Depends(get_default_store)) -> CreateJobResponse:
    """建立 job 並立即在背景排程。回應裡的 status_url 可拿來 poll 狀態。"""
    from ..schemas import SourceType

    # 依 source_type 做早期驗證 — 拼錯路徑 / 缺欄位的常見錯誤先攔下
    if req.source_type == SourceType.URL:
        url = (req.source.url or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "source_type=url 時必須提供 source.url (http:// 或 https://)",
            )
    else:
        if not req.source.path:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"source_type={req.source_type.value} 時必須提供 source.path",
            )
        if not Path(req.source.path).exists():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"source.path 不存在: {req.source.path}",
            )

    rec = store.create(req)
    schedule_job(store, rec.id)
    return CreateJobResponse(
        job_id=rec.id,
        state=rec.state,
        status_url=f"/jobs/{rec.id}",
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(store: JobStore = Depends(get_default_store)) -> JobListResponse:
    return JobListResponse(jobs=store.list())


@router.get("/{job_id}", response_model=JobRecord)
async def get_job(rec: JobRecord = Depends(_require_job)) -> JobRecord:
    return rec


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, store: JobStore = Depends(get_default_store)) -> None:
    if not store.delete(job_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")


# ---------- Draft (deck.json) ----------

@router.get("/{job_id}/draft")
async def get_draft(job_id: str, store: JobStore = Depends(get_default_store)) -> JSONResponse:
    """取 deck.json — ingest 完之後就有,直到 job 被刪除前都可讀。"""
    deck_path = store.deck_path(job_id)
    if not deck_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "deck.json 尚未產生 (ingest 未完成或已失敗)",
        )
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    return JSONResponse(content=deck)


# ---------- Outline (D1 v1, iter 81) ----------

@router.get("/{job_id}/outline")
async def get_outline(job_id: str, store: JobStore = Depends(get_default_store)) -> JSONResponse:
    """iter 81 (D1 v1): 取 outline.json — scriptor 前的中間產物.

    outliner_repo / outliner_longform 產的章節 + topics + 字數預算規劃,
    後續 scriptor 才依此把每章長成 slide 集. 提供給用戶看 LLM 的拆解
    結果, 判斷要不要重 ingest (調 length_mode / source).

    exam_pdf 直接吐 deck (沒 outline 中間步驟), 該 source 永遠回 404.
    repo / document / url / slides_pdf 在 ingest 完後該有 outline.json.
    """
    outline_path = store.outline_path(job_id)
    if not outline_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "outline.json 尚未產生 (該 source_type 不產 outline 或 ingest 未完)",
        )
    outline = json.loads(outline_path.read_text(encoding="utf-8"))
    return JSONResponse(content=outline)


# ---------- Icon suggestions (iter 107 E2-6 backend) ----------

@router.get("/{job_id}/icon-suggestions")
async def get_icon_suggestions(
    job_id: str,
    require_file_exists: bool = True,
    max_icons: int = Query(default=3, ge=1, le=20),
    store: JobStore = Depends(get_default_store),
) -> JSONResponse:
    """E2-6 backend: 批次跑 icon_picker.suggest_for_deck 回整 deck 建議.

    給 review UI「自動建議 icon 勾選列」一次拿完所有 slide 建議, 不必每
    slide 一個 API call. 純文字 grep, 0 LLM call.

    Query params:
        require_file_exists: True (預設) 過濾 SVG 缺檔 (E2-2 未產的 entry).
            False 給 review UI 提案預覽用 — 顯示「將會」建議的 icon, 之後
            渲染前再過濾.
        max_icons: 同 slide 最多回幾個 icon (預設 3, 1~20).

    回傳: {"suggestions": {slide_id: [{key, icon, matched_keyword, position,
        size_ratio, domain, file_exists}, ...]}}
    沒命中也保留 key=[] (跟「沒掃到」做出區別).
    exam_pdf deck (problems schema) 沒 sections.slides → suggestions 為 {}.
    """
    deck_path = store.deck_path(job_id)
    if not deck_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "deck.json 尚未產生 (ingest 未完成或已失敗)",
        )
    deck = json.loads(deck_path.read_text(encoding="utf-8"))

    suggestions = suggest_for_deck(
        deck,
        max_icons=max_icons,
        require_file_exists=require_file_exists,
    )
    # IconMatch dataclass → JSON-friendly dict (Path → str, 給前端拿 URL 用)
    payload = {
        slide_id: [
            {
                "key": m.key,
                "icon": str(m.icon_path),
                "matched_keyword": m.matched_keyword,
                "position": m.position,
                "size_ratio": m.size_ratio,
                "domain": m.domain,
                "file_exists": m.file_exists,
            }
            for m in matches
        ]
        for slide_id, matches in suggestions.items()
    }
    return JSONResponse(content={"suggestions": payload})


# ---------- Image frames summary (iter 109 E1-4 backend) ----------

@router.get("/{job_id}/image-frames")
async def get_image_frames_summary(
    job_id: str,
    require_file_exists: bool = True,
    store: JobStore = Depends(get_default_store),
) -> JSONResponse:
    """E1-4 backend: 批次跑 image_frames.summarize_for_deck 回整 deck frame summary.

    給 review UI「frame preview 縮圖列」一次拿完所有 slide 的 frame 資訊, 不必
    每 slide 一個 API call. 純 Python / 0 PIL / 0 ffmpeg / 0 LLM. 對應 iter 107
    icon-suggestions endpoint pattern.

    Query params:
        require_file_exists: True (預設) 走渲染端嚴格模式 (檔案不在的 frame
            算 invalid, count 不算進去). False 給 review UI 提案階段預覽 —
            frame 尚未產出來也要列在 summary.

    回傳: {"summary": {slide_id: {"count": int, "terminal_path": str | None,
        "has_frames": bool}}}
    沒 image_frames 也保留 slide_id 對應 count=0 / terminal_path=None /
    has_frames=False (跟「沒掃到」做出區別).
    exam_pdf deck (problems schema) 沒 sections.slides → summary={}.
    """
    deck_path = store.deck_path(job_id)
    if not deck_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "deck.json 尚未產生 (ingest 未完成或已失敗)",
        )
    deck = json.loads(deck_path.read_text(encoding="utf-8"))

    summary = summarize_for_deck(deck, require_file_exists=require_file_exists)
    return JSONResponse(content={"summary": summary})


@router.put("/{job_id}/draft", response_model=JobRecord)
async def update_draft(
    job_id: str, body: UpdateDeckRequest, store: JobStore = Depends(get_default_store),
) -> JobRecord:
    """覆寫 deck.json。

    可編輯的狀態:
    - awaiting_review: ingest 完成等人工 review (主路徑)
    - failed:          render 失敗後可改 deck.json 再重試 (PR-3j 加入,
                       避免使用者要從頭跑 ingest 30 分鐘)
    - done:            已 render 完仍可改 + 用 section render (PR-4a) 重跑該章
                       (例如: 切 layout=split-left 後想看新版 / 補錯字後重做一章).
                       既有 mp4 會跟新 deck 不同步, caller 要自行重 render section.

    其他狀態擋住, 避免 race condition (例: rendering 中改 deck 會跟在跑的渲染衝突)。
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if rec.state not in (JobState.AWAITING_REVIEW, JobState.FAILED, JobState.DONE):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"目前狀態 {rec.state.value}, 僅 awaiting_review / failed / done 可改 deck",
        )
    store.deck_path(job_id).write_text(
        json.dumps(body.deck, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # 更新 timestamp 反映有手改過 (狀態維持不變)
    return store.update(job_id)


# ---------- Approve ----------

@router.post("/{job_id}/approve", response_model=JobRecord)
async def approve_job(job_id: str, store: JobStore = Depends(get_default_store)) -> JobRecord:
    """進入 rendering 階段。可在四種狀態觸發:

    - awaiting_review: 主路徑, 第一次 review 通過開始渲染
    - failed (有 deck.json):  重試 render (PR-3j 加入)
    - failed (無 deck.json):  ingest 階段就死了, 重跑整條 pipeline (從 ingest 開始)
                              這條 2026-05-13 加, 修「重試只走 render 找不到
                              deck.json」的洞 (ideate approve 進來踩到)
    - done: iter 55 加 — 渲染完發現 deck 要大改 (例: 多個 slide 都要改 / 全
            重配 figures), 不想逐章按 section render N 次. 直接覆蓋全部 mp4
            + final.mp4. 既有 mp4 全部被新版蓋掉.

    擋住 rendering / pending / ingesting (避免覆寫進行中或前置階段未完成).
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if rec.state not in (JobState.AWAITING_REVIEW, JobState.FAILED, JobState.DONE):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"approve 僅在 awaiting_review / failed / done 可用 (目前 {rec.state.value})",
        )

    # FAILED 但沒 deck.json → ingest 沒跑完, 該從頭重跑整條 pipeline
    # (走 schedule_job 經 run_job 從 ingest 開始, 而非 schedule_render 直接跳 render)
    if rec.state == JobState.FAILED and not store.deck_path(job_id).exists():
        # 要重跑 ingest 產生新內容 → 不在此標 reviewed (run_job 會再停 awaiting_review)
        schedule_job(store, job_id)
    else:
        # R-2: 人工 approve = 通過審查 (硬規則 #1)。render 入口會 assert reviewed。
        store.update(job_id, reviewed=True, reviewed_at=utc_now())
        schedule_render(store, job_id)
    return store.get(job_id)


# ---------- Job log tail (PR-4c) ----------

@router.get("/{job_id}/log")
async def get_job_log(
    job_id: str, tail: int = 200, store: JobStore = Depends(get_default_store),
) -> JSONResponse:
    """讀 jobs/<id>/log.jsonl 末尾 N 筆 log, 給 React UI 即時看 render 進度。

    回傳: {"entries": [{ts, level, logger, msg, job_id, stage?, ...}, ...]}
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if tail < 1 or tail > 2000:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "tail 必須在 1~2000 之間",
        )
    from core.logging_setup import read_job_log
    log_path = store.job_dir(job_id) / "log.jsonl"
    entries = read_job_log(log_path, tail=tail)
    return JSONResponse(content={"entries": entries})


# ---------- Section render (PR-4a) ----------

def _deck_has_section_id(deck: dict, section_id: str) -> bool:
    """deck 可能是 v1 exam (problems) 或新 deck schema (sections), 兩邊找。"""
    for p in deck.get("problems", []):
        if p.get("id") == section_id:
            return True
    for s in deck.get("sections", []):
        if s.get("id") == section_id:
            return True
    return False


@router.post("/{job_id}/sections/{section_id}/render", response_model=JobRecord)
async def render_section(
    job_id: str, section_id: str, store: JobStore = Depends(get_default_store),
) -> JobRecord:
    """重新渲染單一 section / problem (PR-4a)。

    使用情境: render 完發現某章 narration 想改, 改完按這個重跑該章 mp4,
    其他章保留既有 artifact 不動。50 頁簡報改一章可省 ~30 分鐘。

    狀態檢查:
    - DONE: 正常 re-render 該章 (覆蓋舊 mp4)
    - FAILED: 用於上次 render 在某章炸了, 修完 deck 後想只重跑那一章
    - 其他狀態 (rendering / ingesting / awaiting_review / pending) → 409
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if rec.state not in (JobState.DONE, JobState.FAILED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"section render 僅在 done / failed 可用 (目前 {rec.state.value})",
        )

    deck_path = store.deck_path(job_id)
    if not deck_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "deck.json 不存在, 無法 render",
        )
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    if not _deck_has_section_id(deck, section_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"section_id={section_id} 在 deck 中找不到",
        )

    schedule_section_render(store, job_id, section_id)
    return store.get(job_id)


# ---------- Artifacts ----------

@router.get("/{job_id}/artifacts/{name}")
async def download_artifact(job_id: str, name: str, store: JobStore = Depends(get_default_store)) -> FileResponse:
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    # 防 path traversal: 字元檢查 + resolve + 限定在 artifacts/ 下 (S-3 共用 safe_join)
    target = safe_join(store.artifacts_dir(job_id), name)
    if not target.exists() or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"artifact 不存在: {name}")
    return FileResponse(target, filename=name)


# ---------- Artifact 版本歷史 (F9-4 影片版本管理) ----------

@router.get("/{job_id}/versions")
async def list_artifact_versions(
    job_id: str, store: JobStore = Depends(get_default_store),
) -> JSONResponse:
    """列出該 job 重 render 前歸檔的歷次舊版 artifacts (F9-4 slice ②)。

    archive_artifacts 把每次重 render 前的 artifacts/ 快照進 artifact_history/v<N>/,
    record.artifact_versions 存其 metadata。這裡把它整理成附下載 URL 的列表給 UI
    列版本 / 回滾用。沒歸檔過 → 回空 list (新 job 或從未重 render 都正常)。
    版本由新到舊排 (最近歸檔的好版本在最上面)。
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    versions = []
    for v in sorted(rec.artifact_versions, key=lambda v: v.version, reverse=True):
        artifacts = [{
            "name": a.name,
            "kind": a.kind,
            "size_bytes": a.size_bytes,
            "url": f"/jobs/{job_id}/versions/{v.version}/artifacts/{a.name}",
        } for a in v.artifacts]
        versions.append({
            "version": v.version,
            "created_at": v.created_at.isoformat(),
            "archived_at": v.archived_at.isoformat(),
            "path": v.path,
            "note": v.note,
            "artifacts": artifacts,
        })
    return JSONResponse(content={"versions": versions})


@router.get("/{job_id}/versions/{version}/artifacts/{name}")
async def download_versioned_artifact(
    job_id: str, version: int, name: str,
    store: JobStore = Depends(get_default_store),
) -> FileResponse:
    """下載指定歷史版本的 artifact (F9-4 slice ②)，給比對 / 回滾用。

    歷史檔在 jobs/<id>/artifact_history/v<N>/<name>。version 為 int (FastAPI 驗型),
    <=0 直接 404; name 走 safe_join 三道 path-traversal 防護 (比照 artifacts 端點)。
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if version < 1:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"版本不存在: v{version}")
    version_dir = store.job_dir(job_id) / "artifact_history" / f"v{version}"
    target = safe_join(version_dir, name)
    if not target.exists() or not target.is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"版本 v{version} 無此 artifact: {name}")
    return FileResponse(target, filename=name)


# ---------- Figures (iter 54) ----------

@router.get("/{job_id}/figures")
async def list_figures(job_id: str, store: JobStore = Depends(get_default_store)) -> JSONResponse:
    """列出該 job 抽出來的 PDF figures (iter 51 抽到 jobs/<id>/figures/).

    給 SlideEditor 的「換圖」picker 用 — 列出所有 figures 配 thumbnail URL,
    UI 可呼叫 GET /jobs/{id}/figures/{name} 顯示縮圖.

    來源 raw_content.json 內 figures 欄位 (iter 51 寫進去的 metadata).
    沒 raw_content.json 或沒 figures → 回空 list.
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")

    raw_path = store.job_dir(job_id) / "raw_content.json"
    if not raw_path.exists():
        return JSONResponse(content={"figures": []})

    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse(content={"figures": []})

    figures = raw.get("figures") or []
    # 加 url 欄位讓 UI 直接拿 thumbnail
    out = []
    for f in figures:
        if not isinstance(f, dict) or not f.get("path"):
            continue
        out.append({
            "id": f.get("id"),
            "page_no": f.get("page_no"),
            "path": f.get("path"),
            "width": f.get("width"),
            "height": f.get("height"),
            "caption_hint": f.get("caption_hint", ""),
            "url": f"/jobs/{job_id}/figures/{f['path']}",
        })
    return JSONResponse(content={"figures": out})


@router.get("/{job_id}/figures/{name}")
async def download_figure(
    job_id: str, name: str, store: JobStore = Depends(get_default_store),
) -> FileResponse:
    """下載 / 預覽單張 figure. <img src="..."> 直接吃這條.

    跟 artifact 同 path-traversal 防呆, target 限定 figures/ 下.
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    target = safe_join(store.job_dir(job_id) / "figures", name)
    if not target.exists() or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"figure 不存在: {name}")
    return FileResponse(target, filename=name)


# ---------- Song segment images (SONG M3e) ----------

@router.get("/{job_id}/images/{name}")
async def download_song_image(
    job_id: str, name: str, store: JobStore = Depends(get_default_store),
) -> FileResponse:
    """下載 / 預覽單張 song 逐段生圖. <img src="..."> 直接吃這條.

    ingest_song (M3b) 把逐段圖複製到 jobs/<id>/images/ 並把 segment.image_path
    改寫成相對路徑 "images/<name>". SongReviewPane (M3e-3) 預覽時只傳 basename
    (前端剝掉 "images/" 前綴) — 跟 figures endpoint 同 path-traversal 防呆, target
    限定 images/ 下, 確保 reviewer 看得到 AI 生圖才能依硬規則 #1 標 reviewed.
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    target = safe_join(store.job_dir(job_id) / "images", name)
    if not target.exists() or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"image 不存在: {name}")
    return FileResponse(target, filename=name)
