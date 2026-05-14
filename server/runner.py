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
import logging
import os
import shutil
from pathlib import Path

from core.logging_setup import (
    attach_job_log,
    current_job_id,
    detach_job_log,
)

from .jobs import JobStore
from .schemas import JobRecord, JobState, SourceType, StageInfo, utc_now


logger = logging.getLogger(__name__)


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
    """跑 ingest 階段 (PDF / repo / document / url → deck.json), 回傳 deck dict 並寫盤。

    各 source_type 寫到 deck.json 的格式不同:
    - exam_pdf / slides_pdf: v1 exam schema (problems / steps), 直接給 pipeline.py 吃
    - repo / document / url: 新 deck schema (sections / slides), 渲染前壓平
    """
    mock = bool(rec.options.mock)
    deck_path = store.deck_path(rec.id)

    # url 走網路, 其他都先 check path 存在
    if rec.source_type != SourceType.URL:
        src_path = Path(rec.source.path) if rec.source.path else None
        if src_path is None or not src_path.exists():
            raise FileNotFoundError(f"source.path 不存在: {rec.source.path}")
    else:
        src_path = None

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
        # PR-3h: slides_pdf 走 deck schema (sections/slides), 跟 repo / document / url 對齊。
        # React UI 看到 sections 走 SlideEditor (含 bg_image 縮圖預覽),
        # 渲染前會用 deck_to_exam_schema_slides 壓回 v1 給 pipeline.SlideRenderer 吃。
        await asyncio.to_thread(
            ingest_slides, src_path, deck_path,
            mock=mock, single=False, brief=False, as_deck=True,
        )
        return json.loads(deck_path.read_text(encoding="utf-8"))

    if rec.source_type == SourceType.REPO:
        return await _run_ingest_repo(store, rec, deck_path, mock)

    if rec.source_type in (SourceType.DOCUMENT, SourceType.URL):
        return await _run_ingest_long_form(store, rec, deck_path, mock)

    raise ValueError(f"未支援的 source_type: {rec.source_type}")


async def _run_ingest_repo(store: JobStore, rec: JobRecord, deck_path: Path, mock: bool) -> dict:
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


async def _run_ingest_long_form(store: JobStore, rec: JobRecord, deck_path: Path, mock: bool) -> dict:
    """document / url 路徑: adapter → outline_long_form → script_long_form → deck.json。

    跟 _run_ingest_repo 結構一致, 差別在 adapter 不同 + outliner / scriptor 走
    long-form prompt template。
    """
    from core.adapters.document import scan_document
    from core.adapters.url import scan_url
    from core.outliner import mock_outline, outline_long_form
    from core.scriptor import mock_deck_from_outline, script_long_form

    if rec.source_type == SourceType.DOCUMENT:
        raw = await asyncio.to_thread(scan_document, Path(rec.source.path))
    else:  # URL
        if not rec.source.url:
            raise ValueError("source_type=url 時必須提供 source.url")
        raw = await asyncio.to_thread(scan_url, rec.source.url)

    job_dir = deck_path.parent
    (job_dir / "raw_content.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if mock:
        outline = mock_outline(raw)
        deck = mock_deck_from_outline(outline, raw)
    else:
        outline = await asyncio.to_thread(outline_long_form, raw)
        deck = await asyncio.to_thread(script_long_form, outline, raw)

    (job_dir / "outline.json").write_text(
        json.dumps(outline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    deck_path.write_text(
        json.dumps(deck, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return deck


async def _run_render(
    store: JobStore, rec: JobRecord, *, section_id: str | None = None,
) -> None:
    """跑 render 階段: deck.json → MP4 + SRT 進 jobs/<id>/artifacts/。

    schema 分流:
    - sections 為頂層 (新 deck schema) + source_type=repo: 走 pptx_slide 渲染 (Forest)
    - sections 為頂層 + 其他 source_type: 走黑板渲染 (deck_to_exam_schema)
    - problems 為頂層 (v1 exam schema): 直接餵 pipeline (考卷 / 簡報走這條)

    PR-4a: section_id 非 None 時只 render 該 section, 其他章保持既有 mp4 不動。
    讓使用者改一章 narration 後不必重跑全部 (50 頁簡報省 30 分鐘)。
    """
    from core import problem_to_v0_json, render_video
    from core.config import OUTPUT_DIR
    from core.deck import (
        deck_to_exam_schema,
        deck_to_exam_schema_pptx,
        deck_to_exam_schema_slides,
    )

    deck_path = store.deck_path(rec.id)
    if not deck_path.exists():
        raise FileNotFoundError(f"deck.json 不存在,ingest 階段未完成?{deck_path}")

    deck = json.loads(deck_path.read_text(encoding="utf-8"))

    # 判斷 schema: 新 deck schema 有 sections, v1 exam schema 有 problems
    if "sections" in deck and "problems" not in deck:
        # 走哪條 renderer 看 source_type:
        if rec.source_type == SourceType.SLIDES_PDF:
            # PR-3h: 簡報走 SlideRenderer (原始投影片當底圖), 不是黑板也不是 pptx
            deck = deck_to_exam_schema_slides(deck)
        elif rec.source_type in (SourceType.REPO, SourceType.DOCUMENT, SourceType.URL):
            # 長篇內容講解走 Forest pptx 主題, 比黑板適合
            deck = deck_to_exam_schema_pptx(deck)
        else:
            deck = deck_to_exam_schema(deck)

    # PR-4a: 過濾指定 section, 兩種 schema 經 deck_to_exam_schema_* 後 problems[].id
    # 都對應原 section/problem 的 id (見 core.deck), 直接 filter 即可
    problems = deck["problems"]
    if section_id is not None:
        matching = [p for p in problems if p.get("id") == section_id]
        if not matching:
            raise ValueError(f"section_id={section_id} 在 deck 中找不到")
        problems = matching

    artifacts_dir = store.artifacts_dir(rec.id)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # TTS 覆寫: options.tts_provider → 設環境變數,pipeline 內部讀取
    if rec.options.tts_provider:
        os.environ["TTS_PROVIDER"] = rec.options.tts_provider

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # PR-5a: 從 JobOptions.theme 帶 theme 進 v0 dict, PptxStyleRenderer.render
    # 會讀 data["theme"] 切色票。其他 renderer (黑板 / SlideRenderer) 不看。
    theme = rec.options.theme or "forest"
    # PR-5c: 燒字幕旗標, pipeline.main 看 data["hardsub"] 決定要不要跑 burn_subtitles
    hardsub = bool(rec.options.hardsub)
    # iter 41: intro 前置. 主迴圈外算一次 normalized intro, 避免每題重 probe.
    prepend_intro = bool(rec.options.prepend_intro)
    normalized_intro: Path | None = None
    intro_duration: float = 0.0
    if prepend_intro:
        normalized_intro, intro_duration = await asyncio.to_thread(
            _prepare_intro_for_problems, problems, artifacts_dir,
        )

    # 逐題渲染 → MP4 / SRT 從 OUTPUT_DIR 搬到 artifacts/
    for prob in problems:
        pid = prob["id"]
        v0 = problem_to_v0_json(deck["exam_title"], prob)
        v0["theme"] = theme
        v0["hardsub"] = hardsub
        v0_path = artifacts_dir / f"{pid}.json"
        v0_path.write_text(
            json.dumps(v0, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        unique_name = f"job_{rec.id}__{pid}"
        await render_video(str(v0_path), unique_name, start_step=None)

        # iter 41: 串 intro + 偏移 SRT (prepend_intro=True 時)
        if prepend_intro and normalized_intro is not None:
            await asyncio.to_thread(
                _apply_intro_postprocess,
                unique_name, normalized_intro, intro_duration,
            )

        for ext in ("mp4", "srt"):
            src = OUTPUT_DIR / f"{unique_name}.{ext}"
            dst = artifacts_dir / f"{pid}.{ext}"
            if src.exists():
                src.replace(dst)


def _prepare_intro_for_problems(
    problems: list[dict], artifacts_dir: Path,
) -> tuple[Path | None, float]:
    """iter 41: 算 normalized intro + 抓 intro 秒數.

    回傳 (normalized_intro_path, intro_duration). 失敗時回 (None, 0) 並
    logger.warning, 讓 render 流程繼續跑 (intro 串接失敗不該整個 job 死).

    放 module level 不放 _run_render 內: 兩條共用 (整份 render + section
    re-render), 抽出來測試也直接 (純 IO 函式, mock ffmpeg 即可).
    """
    from core import video_concat
    from core.config import ASSETS_DIR, get_intro_video_path

    try:
        intro_path = Path(get_intro_video_path())
        if not intro_path.exists():
            logger.warning(
                "prepend_intro=True 但 intro 檔不存在 (%s), 跳過 intro 串接",
                intro_path,
            )
            return None, 0.0

        # 探測主影片 audio spec 當 normalize target.
        # 找剛 render 完的第一支主影片 — 它的 audio 規格代表整批.
        # 但這時候還沒 render, 拿不到. 退一步: 用 pipeline 預設 spec
        # (TTS 出來通常是 96000 Hz mono AAC). 第一題 render 完之後也可以
        # 重 probe, 但對齊整批用第一支即可.
        # 簡化: 直接 hard-code TTS pipeline 的目標 spec.
        target = video_concat.AudioSpec(
            sample_rate=96000, channels=1, codec="aac",
        )
        normalized = video_concat.normalize_intro_audio(
            intro_path, target, ASSETS_DIR,
        )
        duration = video_concat.get_video_duration(normalized)
        logger.info(
            "intro 已 normalize: %s (%.2fs), 將串接到 %d 支主影片前",
            normalized.name, duration, len(problems),
        )
        return normalized, duration
    except Exception as e:
        logger.exception("intro 準備失敗, 跳過 intro 串接: %s", e)
        return None, 0.0


def _apply_intro_postprocess(
    unique_name: str, normalized_intro: Path, intro_duration: float,
) -> None:
    """iter 41: 把 intro 接到主影片前 + 偏移 SRT.

    輸入 OUTPUT_DIR / {unique_name}.{mp4,srt} (剛 render 完的位置),
    處理完原地覆蓋. caller (_run_render) 接著 move 到 artifacts/.

    失敗時 logger.warning 但不 raise — intro 串接是 nice-to-have, 主影片
    成品已存在, 不該整支 job 因為這個炸掉.
    """
    from core import video_concat
    from core.config import OUTPUT_DIR

    main_mp4 = OUTPUT_DIR / f"{unique_name}.mp4"
    main_srt = OUTPUT_DIR / f"{unique_name}.srt"
    if not main_mp4.exists():
        logger.warning("intro 串接跳過: 主影片不存在 %s", main_mp4)
        return

    try:
        # 把 intro + main concat 成 _with_intro.mp4, 再覆蓋原檔
        merged = OUTPUT_DIR / f"{unique_name}.with_intro.mp4"
        video_concat.concat_videos([normalized_intro, main_mp4], merged)
        merged.replace(main_mp4)
        logger.info("intro 串接完成: %s", main_mp4.name)
    except Exception as e:
        logger.exception("intro 串接失敗, 保留無 intro 版本: %s", e)
        return

    # SRT 時間戳往後推 intro 秒數, 字幕跟畫面才對得上
    if main_srt.exists() and intro_duration > 0:
        try:
            srt_text = main_srt.read_text(encoding="utf-8")
            shifted = video_concat.offset_srt(srt_text, intro_duration)
            main_srt.write_text(shifted, encoding="utf-8")
        except Exception as e:
            logger.exception("SRT 偏移失敗 (主影片已串好 intro): %s", e)


# ---------- Top-level runner ----------

async def run_job(store: JobStore, job_id: str) -> None:
    """完整跑一個 job:ingest → (await review or auto) → render → done。

    這個 coroutine 由 routes 層 schedule 成 asyncio.create_task() 背景執行,
    不要 await 它否則 HTTP request 會卡死。

    PR-4c: 一進 task 就 attach per-job log file (jobs/<id>/log.jsonl) 並 set
    contextvar, 結束時 detach + reset, 讓 logger.info / .warning 等自動帶 job_id。
    """
    rec = store.get(job_id)
    if rec is None:
        return

    log_path = store.job_dir(job_id) / "log.jsonl"
    attach_job_log(job_id, log_path)
    token = current_job_id.set(job_id)
    logger.info(
        "job 開始 (source_type=%s, mock=%s, require_review=%s)",
        rec.source_type.value, rec.options.mock, rec.options.require_review,
    )

    try:
        # ---- 1. Ingest ----
        store.update(job_id, state=JobState.INGESTING)
        _start_stage(store, job_id, "ingest")
        logger.info("ingest 開始", extra={"stage": "ingest"})
        try:
            await _run_ingest(store, rec)
        except Exception as e:
            # solve.py / scriptor.py / outliner.py / slide_ingest.py 的 sys.exit
            # 已改 raise RuntimeError, 不再需要 catch SystemExit
            logger.exception("ingest 失敗", extra={"stage": "ingest"})
            _end_stage_fail(store, job_id, str(e))
            store.update(job_id, state=JobState.FAILED, error=f"ingest 失敗: {e}")
            return
        _end_stage_ok(store, job_id)
        logger.info("ingest 完成 → deck.json", extra={"stage": "ingest"})
        store.update(
            job_id,
            deck_path=str(store.deck_path(job_id).relative_to(store.root.parent)).replace("\\", "/"),
        )

        # ---- 2. Pause for review? ----
        rec = store.get(job_id)  # refresh
        if rec.options.require_review:
            store.update(job_id, state=JobState.AWAITING_REVIEW)
            logger.info("等候 review (require_review=True)")
            return  # 等 /approve

        # 否則直接續跑
        await _run_render_phase(store, job_id)

    except Exception as e:
        # catch-all: 任何沒被內層 handle 的例外都標 failed
        logger.exception("unexpected 錯誤")
        store.update(job_id, state=JobState.FAILED, error=f"unexpected: {e}")
    finally:
        current_job_id.reset(token)
        detach_job_log(job_id)


async def _run_render_phase(
    store: JobStore, job_id: str, *, section_id: str | None = None,
) -> None:
    """從 awaiting_review 或直接 ingest 完接著跑 render。供 /approve 也呼叫。

    PR-3j: 從 FAILED retry 進來時, 把舊 error 清掉 (不然成功後 record.error 還
    留著上次的 stale error, UI 會誤以為又失敗)。
    PR-4a: section_id 非 None 時只渲染指定 section, stage name 帶上 section_id
    讓 UI 跟 debug 看得出哪一章在跑。
    PR-4c: schedule_section_render 從另一條 entry 進來, 自己 attach log
    (run_job 那層的 attach 不會跑到)。
    """
    # PR-4c: 若 caller 還沒 attach log (e.g. schedule_section_render), 自己 attach
    log_path = store.job_dir(job_id) / "log.jsonl"
    own_log = current_job_id.get() != job_id
    token = None
    if own_log:
        attach_job_log(job_id, log_path)
        token = current_job_id.set(job_id)

    try:
        store.update(job_id, state=JobState.RENDERING, error=None)
        stage_name = f"render-section-{section_id}" if section_id else "render"
        _start_stage(store, job_id, stage_name)
        if section_id:
            logger.info("render 開始 (section_id=%s)", section_id, extra={"stage": stage_name})
        else:
            logger.info("render 開始 (整份)", extra={"stage": stage_name})
        try:
            rec = store.get(job_id)
            await _run_render(store, rec, section_id=section_id)
        except Exception as e:
            logger.exception("render 失敗", extra={"stage": stage_name})
            _end_stage_fail(store, job_id, str(e))
            store.update(job_id, state=JobState.FAILED, error=f"render 失敗: {e}")
            return
        _end_stage_ok(store, job_id)
        logger.info("render 完成", extra={"stage": stage_name})

        # render 完成後掃 artifacts 寫進 record (section render 也要 refresh, 讓
        # 新 mp4 大小 / 修改時間反映到 JobRecord)
        store.refresh_artifacts(job_id)
        store.update(
            job_id,
            state=JobState.DONE,
            error=None,    # 確保清掉之前 retry 的 stale error
            output_dir=str(store.artifacts_dir(job_id).relative_to(store.root.parent)).replace("\\", "/"),
        )
    finally:
        if own_log and token is not None:
            current_job_id.reset(token)
            detach_job_log(job_id)


def schedule_job(store: JobStore, job_id: str) -> asyncio.Task:
    """在當前 event loop 上 schedule 一個 job runner task。

    Routes 層 call 這個 fn 後立刻回 HTTP response, runner 在背景跑完整 pipeline。
    """
    return asyncio.create_task(run_job(store, job_id))


def schedule_render(store: JobStore, job_id: str) -> asyncio.Task:
    """/approve 端點用: 從 awaiting_review 接著跑 render。"""
    return asyncio.create_task(_run_render_phase(store, job_id))


def schedule_section_render(
    store: JobStore, job_id: str, section_id: str,
) -> asyncio.Task:
    """PR-4a: section / problem 級別重 render。

    呼叫端 (POST /jobs/{id}/sections/{sid}/render) 已驗證 state ∈ {DONE, FAILED}
    且 section_id 在 deck 內存在, 所以這裡不再檢查。
    """
    return asyncio.create_task(_run_render_phase(store, job_id, section_id=section_id))
