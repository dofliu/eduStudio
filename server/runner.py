"""Job runner — 把 source_type dispatch 到 core 的對應函式,在 background 執行。

設計重點:
- core.solve_pdf / core.ingest_slides 是同步函式,放 asyncio.to_thread 跑,
  不阻塞 FastAPI event loop
- core.render_video 是 async (pipeline.main),直接 await
- 每個階段失敗都會把 stage 標 failed + job 標 failed,error 寫到 state.json
- require_review=True 時 ingest 完停在 awaiting_review,/approve 才繼續

跑出來的檔案放置:
    jobs/<id>/
      ├── state.json        # JobRecord
      ├── deck.json         # ingest 產物 (exam.json schema)
      └── artifacts/
          ├── q1.mp4
          ├── q1.srt
          └── ...
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

from .jobs import JobStore
from .schemas import JobRecord, JobState, SourceType, StageInfo, utc_now


# ---------- Stage helpers ----------

def _start_stage(store: JobStore, job_id: str, name: str) -> None:
    store.add_stage(job_id, StageInfo(
        name=name, state="running", started_at=utc_now(),
    ))


def _end_stage_ok(store: JobStore, job_id: str) -> None:
    store.update_last_stage(job_id, state="done", ended_at=utc_now())


def _end_stage_fail(store: JobStore, job_id: str, err: str) -> None:
    store.update_last_stage(job_id, state="failed", ended_at=utc_now(), error=err)


# ---------- Source-type dispatch ----------

async def _run_ingest(store: JobStore, rec: JobRecord) -> dict:
    """跑 ingest 階段 (PDF / repo → deck.json),回傳 deck dict 並寫 deck.json。

    各 source_type 寫到 deck.json 的格式不同:
    - exam_pdf / slides_pdf: v1 exam schema (problems / steps), 直接給 pipeline.py 吃
    - repo: 新 deck schema (sections / slides), 渲染前透過 deck_to_exam_schema 壓平
    """
    src_path = Path(rec.source.path)
    if not src_path.exists():
        raise FileNotFoundError(f"source 不存在: {src_path}")

    mock = bool(rec.options.mock)
    deck_path = JobStore.deck_path(rec.id)

    if rec.source_type == SourceType.EXAM_PDF:
        if mock:
            from solve import mock_output
            deck = mock_output()
        else:
            from core import solve_pdf
            deck = await asyncio.to_thread(solve_pdf, src_path)
        deck_path.write_text(
            json.dumps(deck, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return deck

    if rec.source_type == SourceType.SLIDES_PDF:
        from core import ingest_slides
        # ingest_slides 直接寫到 out_json, 我們導向 deck.json
        await asyncio.to_thread(
            ingest_slides, src_path, deck_path,
            mock=mock, single=False, brief=False,
        )
        return json.loads(deck_path.read_text(encoding="utf-8"))

    if rec.source_type == SourceType.REPO:
        return await _run_ingest_repo(rec, deck_path, mock)

    raise ValueError(f"未支援的 source_type: {rec.source_type}")


async def _run_ingest_repo(rec: JobRecord, deck_path: Path, mock: bool) -> dict:
    """repo 路徑: adapter → outliner → scriptor → deck.json (新 schema)。"""
    from core.adapters.repo import scan_repo
    from core.outliner import mock_outline, outline_repo
    from core.scriptor import mock_deck_from_outline, script_repo

    src_path = Path(rec.source.path)
    if not src_path.is_dir():
        raise NotADirectoryError(f"source.path 必須是資料夾 (source_type=repo): {src_path}")

    max_files = rec.options.max_files or 50

    # adapter 是純磁碟讀取, scriptor / outliner 是 Gemini 同步呼叫, 都丟 thread
    raw = await asyncio.to_thread(scan_repo, src_path, max_files=max_files)

    # 把中間產物也寫到 jobs/<id>/ 方便 debug (raw_content.json + outline.json)
    job_dir = deck_path.parent
    (job_dir / "raw_content.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if mock:
        outline = mock_outline(raw)
        deck = mock_deck_from_outline(outline, raw)
    else:
        outline = await asyncio.to_thread(outline_repo, raw)
        deck = await asyncio.to_thread(script_repo, outline, raw)

    (job_dir / "outline.json").write_text(
        json.dumps(outline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    deck_path.write_text(
        json.dumps(deck, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return deck


async def _run_render(store: JobStore, rec: JobRecord) -> None:
    """跑 render 階段: deck.json → MP4 + SRT 進 jobs/<id>/artifacts/。

    schema 分流:
    - sections 為頂層 (新 deck schema) + source_type=repo: 走 pptx_slide 渲染 (Forest)
    - sections 為頂層 + 其他 source_type: 走黑板渲染 (deck_to_exam_schema)
    - problems 為頂層 (v1 exam schema): 直接餵 pipeline (考卷 / 簡報走這條)
    """
    from core import problem_to_v0_json, render_video
    from core.config import OUTPUT_DIR
    from core.deck import deck_to_exam_schema, deck_to_exam_schema_pptx

    deck_path = JobStore.deck_path(rec.id)
    if not deck_path.exists():
        raise FileNotFoundError(f"deck.json 不存在,ingest 階段未完成?{deck_path}")

    deck = json.loads(deck_path.read_text(encoding="utf-8"))

    # 判斷 schema: 新 deck schema 有 sections, v1 exam schema 有 problems
    if "sections" in deck and "problems" not in deck:
        # repo source 走 pptx Forest 主題, 其他新 schema (slides 沒走這條, 但保留擴展)
        # 走黑板. 未來其他 source_type (document / url) 自己決定哪條。
        if rec.source_type == SourceType.REPO:
            deck = deck_to_exam_schema_pptx(deck)
        else:
            deck = deck_to_exam_schema(deck)

    artifacts_dir = JobStore.artifacts_dir(rec.id)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # TTS 覆寫: options.tts_provider → 設環境變數,pipeline 內部讀取
    if rec.options.tts_provider:
        os.environ["TTS_PROVIDER"] = rec.options.tts_provider

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 逐題渲染 → MP4 / SRT 從 OUTPUT_DIR 搬到 artifacts/
    for prob in deck["problems"]:
        pid = prob["id"]
        v0 = problem_to_v0_json(deck["exam_title"], prob)
        v0_path = artifacts_dir / f"{pid}.json"
        v0_path.write_text(
            json.dumps(v0, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        unique_name = f"job_{rec.id}__{pid}"
        await render_video(str(v0_path), unique_name, start_step=None)

        for ext in ("mp4", "srt"):
            src = OUTPUT_DIR / f"{unique_name}.{ext}"
            dst = artifacts_dir / f"{pid}.{ext}"
            if src.exists():
                src.replace(dst)


# ---------- Top-level runner ----------

async def run_job(store: JobStore, job_id: str) -> None:
    """完整跑一個 job:ingest → (await review or auto) → render → done。

    這個 coroutine 由 routes 層 schedule 成 asyncio.create_task() 背景執行,
    不要 await 它否則 HTTP request 會卡死。
    """
    rec = store.get(job_id)
    if rec is None:
        return

    try:
        # ---- 1. Ingest ----
        store.update(job_id, state=JobState.INGESTING)
        _start_stage(store, job_id, "ingest")
        try:
            await _run_ingest(store, rec)
        except (Exception, SystemExit) as e:
            # 為什麼 catch SystemExit: solve.py 缺 GEMINI_API_KEY 時會 sys.exit(),
            # 不接住整個 task 會悄悄掛掉 job 卻維持 ingesting 狀態
            _end_stage_fail(store, job_id, str(e))
            store.update(job_id, state=JobState.FAILED, error=f"ingest 失敗: {e}")
            return
        _end_stage_ok(store, job_id)
        store.update(
            job_id,
            deck_path=str(JobStore.deck_path(job_id).relative_to(store.root.parent)).replace("\\", "/"),
        )

        # ---- 2. Pause for review? ----
        rec = store.get(job_id)  # refresh
        if rec.options.require_review:
            store.update(job_id, state=JobState.AWAITING_REVIEW)
            return  # 等 /approve

        # 否則直接續跑
        await _run_render_phase(store, job_id)

    except Exception as e:
        # catch-all: 任何沒被內層 handle 的例外都標 failed
        store.update(job_id, state=JobState.FAILED, error=f"unexpected: {e}")


async def _run_render_phase(store: JobStore, job_id: str) -> None:
    """從 awaiting_review 或直接 ingest 完接著跑 render。供 /approve 也呼叫。"""
    store.update(job_id, state=JobState.RENDERING)
    _start_stage(store, job_id, "render")
    try:
        rec = store.get(job_id)
        await _run_render(store, rec)
    except (Exception, SystemExit) as e:
        _end_stage_fail(store, job_id, str(e))
        store.update(job_id, state=JobState.FAILED, error=f"render 失敗: {e}")
        return
    _end_stage_ok(store, job_id)

    # render 完成後掃 artifacts 寫進 record
    store.refresh_artifacts(job_id)
    store.update(
        job_id,
        state=JobState.DONE,
        output_dir=str(JobStore.artifacts_dir(job_id).relative_to(store.root.parent)).replace("\\", "/"),
    )


def schedule_job(store: JobStore, job_id: str) -> asyncio.Task:
    """在當前 event loop 上 schedule 一個 job runner task。

    Routes 層 call 這個 fn 後立刻回 HTTP response, runner 在背景跑完整 pipeline。
    """
    return asyncio.create_task(run_job(store, job_id))


def schedule_render(store: JobStore, job_id: str) -> asyncio.Task:
    """/approve 端點用: 從 awaiting_review 接著跑 render。"""
    return asyncio.create_task(_run_render_phase(store, job_id))
