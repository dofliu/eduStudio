"""Job 持久化層 — JSON 檔案存到 jobs/<id>/。

為什麼用檔案不用 SQLite:
- 每個 job 的 deck.json / artifacts 本來就要寫檔案,state.json 跟它們放一起最直觀
- 無 schema migration 成本,改 JobRecord 欄位直接生效 (Pydantic 處理舊欄位缺漏)
- debug 友善,可以直接 cat / 編輯 state.json
- v0 階段沒有複雜查詢需求

為什麼仍保留 in-memory 索引:
- list_jobs() 不必每次 scan 整個 jobs/ 目錄
- runner 持有 Job 物件 reference,跨階段更新狀態時不必反覆讀檔
"""
from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable

from core.config import PROJECT_ROOT

from .schemas import (
    Artifact,
    CreateJobRequest,
    JobOptions,
    JobRecord,
    JobSource,
    JobState,
    SourceType,
    StageInfo,
    YoutubeUpload,
    utc_now,
)


# ---------- 設定 ----------

JOBS_DIR = PROJECT_ROOT / "jobs"


# ---------- 純 helpers ----------

def _new_job_id() -> str:
    """12 字元 hex,夠分辨且短到能放 URL / 檔名。"""
    return uuid.uuid4().hex[:12]


def _job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def _state_path(job_id: str) -> Path:
    return _job_dir(job_id) / "state.json"


def _resolve_default_review(source_type: SourceType, opt_value: bool | None) -> bool:
    """require_review 沒明說時的預設值。

    exam_pdf → True (CLAUDE.md 硬規則 #1: AI 產出考題答案必須人工 review)
    slides_pdf → False (簡報講解風險低,可直接渲染)
    """
    if opt_value is not None:
        return opt_value
    return source_type == SourceType.EXAM_PDF


# ---------- Store (thread-safe in-memory + write-through) ----------

class JobStore:
    """單一 process 內共享的 job 記憶體 + 磁碟同步層。

    Thread-safe (RLock): runner 可能在 background thread 改狀態,
    routes 在 asyncio event loop 讀,要避免並發踩到。
    """

    def __init__(self, root: Path = JOBS_DIR):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._cache: dict[str, JobRecord] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        """啟動時掃 jobs/ 把既有 state.json 讀回 cache。

        舊 state 若 schema 不相容 (Pydantic ValidationError) 跳過並印警告,
        不讓單一壞檔擋住整個 server 啟動。
        """
        for sub in sorted(self.root.glob("*/state.json")):
            try:
                rec = JobRecord.model_validate_json(sub.read_text(encoding="utf-8"))
                self._cache[rec.id] = rec
            except Exception as e:
                print(f"[jobstore] 略過無法解析的 state: {sub} ({e})")

    # ---- CRUD ----

    def create(self, req: CreateJobRequest) -> JobRecord:
        """建立 job, 寫初始 state.json, 但不啟動執行 (runner 自行接手)。"""
        with self._lock:
            job_id = _new_job_id()
            # iter 39 fix: 用 self.root 不再 fall through 到 module-level JOBS_DIR
            # (避免 test fixture 設了 root=tmp_path 仍寫到真實 jobs/)
            d = self.root / job_id
            d.mkdir(parents=True, exist_ok=True)
            (d / "artifacts").mkdir(exist_ok=True)

            # require_review 預設值依 source_type
            options = req.options.model_copy(update={
                "require_review": _resolve_default_review(
                    req.source_type, req.options.require_review,
                ),
            })

            now = utc_now()
            rec = JobRecord(
                id=job_id,
                source_type=req.source_type,
                source=req.source,
                options=options,
                state=JobState.PENDING,
                created_at=now,
                updated_at=now,
            )
            self._cache[job_id] = rec
            self._persist(rec)
            return rec

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._cache.get(job_id)

    def list(self) -> list[JobRecord]:
        with self._lock:
            return sorted(
                self._cache.values(),
                key=lambda r: r.created_at,
                reverse=True,
            )

    def update(self, job_id: str, **fields) -> JobRecord:
        """部分更新, 自動 bump updated_at, 寫盤。"""
        with self._lock:
            rec = self._cache.get(job_id)
            if rec is None:
                raise KeyError(job_id)
            updated = rec.model_copy(update={**fields, "updated_at": utc_now()})
            self._cache[job_id] = updated
            self._persist(updated)
            return updated

    def add_stage(self, job_id: str, stage: StageInfo) -> JobRecord:
        """append 一個 stage 紀錄並寫盤。"""
        with self._lock:
            rec = self._cache[job_id]
            new_stages = list(rec.stages) + [stage]
            return self.update(job_id, stages=new_stages)

    def update_last_stage(self, job_id: str, **fields) -> JobRecord:
        """改最後一個 stage 的欄位 (例如 ended_at / state / error)。"""
        with self._lock:
            rec = self._cache[job_id]
            if not rec.stages:
                raise ValueError(f"job {job_id} 沒有 stage 可更新")
            last = rec.stages[-1]
            new_last = last.model_copy(update=fields)
            new_stages = list(rec.stages[:-1]) + [new_last]
            return self.update(job_id, stages=new_stages)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            if job_id not in self._cache:
                return False
            del self._cache[job_id]
            # iter 39 fix: 用 self.root
            d = self.root / job_id
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            return True

    # ---- Artifacts ----

    def scan_artifacts(self, job_id: str) -> list[Artifact]:
        """重新掃 jobs/<id>/artifacts/ 並更新 cache。

        放在 store 裡而不是 runner 內: 若 caller 在 done 後手動加檔,
        scan 後也能反映,跟現實狀態同步。
        """
        # iter 39 fix: 用 self.root
        d = self.root / job_id / "artifacts"
        out: list[Artifact] = []
        if not d.exists():
            return out
        for p in sorted(d.iterdir()):
            if not p.is_file():
                continue
            ext = p.suffix.lower().lstrip(".")
            kind = ext if ext in ("mp4", "srt", "json", "png") else "other"
            out.append(Artifact(
                name=p.name,
                path=str(p.relative_to(JOBS_DIR)).replace("\\", "/"),
                size_bytes=p.stat().st_size,
                kind=kind,
            ))
        return out

    def refresh_artifacts(self, job_id: str) -> JobRecord:
        return self.update(job_id, artifacts=self.scan_artifacts(job_id))

    # ---- YouTube uploads (PR-3f) ----

    def set_youtube_upload(self, job_id: str, artifact_name: str,
                           upload: YoutubeUpload) -> JobRecord:
        """整顆覆寫單一 artifact 的 YT 上傳記錄, 寫盤。"""
        with self._lock:
            rec = self._cache.get(job_id)
            if rec is None:
                raise KeyError(job_id)
            new_map = dict(rec.youtube_uploads)
            new_map[artifact_name] = upload
            return self.update(job_id, youtube_uploads=new_map)

    def patch_youtube_upload(self, job_id: str, artifact_name: str,
                             **fields) -> JobRecord:
        """部分更新 YT 上傳記錄 (不存在會自動建空 record)。背景 task 用得最多。"""
        with self._lock:
            rec = self._cache.get(job_id)
            if rec is None:
                raise KeyError(job_id)
            current = rec.youtube_uploads.get(artifact_name) or YoutubeUpload()
            updated = current.model_copy(update=fields)
            new_map = dict(rec.youtube_uploads)
            new_map[artifact_name] = updated
            return self.update(job_id, youtube_uploads=new_map)

    # ---- Disk I/O ----

    def _persist(self, rec: JobRecord) -> None:
        # iter 39 fix: 用 self.root 不再 fall through 到 module-level _state_path
        path = self.root / rec.id / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            rec.model_dump_json(indent=2),
            encoding="utf-8",
        )

    # ---- Path helpers ----
    # iter 39 fix: 改 instance methods 用 self.root, 不再 fall through 到模組級
    # JOBS_DIR. 之前 runner.py / routes 用 JobStore.deck_path(id) (staticmethod)
    # 會在 test override 走 tmp_path 時仍寫到真實 jobs/, 造成 test 污染真實目錄.

    def job_dir(self, job_id: str) -> Path:
        return self.root / job_id

    def deck_path(self, job_id: str) -> Path:
        return self.root / job_id / "deck.json"

    def artifacts_dir(self, job_id: str) -> Path:
        return self.root / job_id / "artifacts"


# 模組級單例 (FastAPI app 啟動時 import 即可)
_default_store: JobStore | None = None


def get_default_store() -> JobStore:
    global _default_store
    if _default_store is None:
        _default_store = JobStore()
    return _default_store
