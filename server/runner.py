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
    """跑 ingest 階段 (PDF → exam.json),回傳 deck dict 並寫 deck.json。"""
    src_path = Path(rec.source.path)
    if not src_path.exists():
        raise FileNotFoundError(f"source 不存在: {src_path}")

    mock = bool(rec.options.mock)

    # 同步函式丟 thread (避免阻塞 event loop)
    if rec.source_type == SourceType.EXAM_PDF:
        if mock:
            # 不打 Gemini, 用 solve.mock_output() 的離線版本
            from solve import mock_output
            deck = mock_output()
        else:
            from core import solve_pdf
            deck = await asyncio.to_thread(solve_pdf, src_path)
    elif rec.source_type == SourceType.SLIDES_PDF:
        from core import ingest_slides
        # ingest_slides 直接寫到 out_json, 我們導向 deck.json
        deck_path = JobStore.deck_path(rec.id)
        await asyncio.to_thread(
            ingest_slides, src_path, deck_path,
            mock=mock, single=False, brief=False,
        )
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        return deck
    else:
        raise ValueError(f"未支援的 source_type: {rec.source_type}")

    # exam_pdf 路徑: 自己把 deck dict 寫成 deck.json
    deck_path = JobStore.deck_path(rec.id)
    deck_path.write_text(
        json.dumps(deck, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return deck


async def _run_render(store: JobStore, rec: JobRecord) -> None:
    """跑 render 階段: deck.json → MP4 + SRT 進 jobs/<id>/artifacts/。"""
    from core import problem_to_v0_json, render_video
    from core.config import OUTPUT_DIR

    deck_path = JobStore.deck_path(rec.id)
    if not deck_path.exists():
        raise FileNotFoundError(f"deck.json 不存在,ingest 階段未完成?{deck_path}")

    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    artifacts_dir = JobStore.artifacts_dir(rec.id)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # TTS 覆寫: options.tts_provider → 設環境變數,pipeline 內部讀取
    if rec.options.tts_provider:
        os.environ["TTS_PROVIDER"] = rec.options.tts_provider

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 逐題渲染 → MP4 / SRT 從 OUTPUT_DIR 搬到 artifacts/
    for prob in deck["problems"]:
        pid = prob["id"]
        # v0 single-question JSON
        v0 = problem_to_v0_json(deck["exam_title"], prob)
        v0_path = artifacts_dir / f"{pid}.json"
        v0_path.write_text(
            json.dumps(v0, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        unique_name = f"job_{rec.id}__{pid}"
        await render_video(str(v0_path), unique_name, start_step=None)

        # pipeline 寫到 OUTPUT_DIR/<unique_name>.{mp4,srt} 搬到 artifacts/<pid>.{mp4,srt}
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
