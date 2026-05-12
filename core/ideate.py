"""自動內容企劃 (v4 階段 2 B) — 設計見 docs/ideate-design.md

scaffold 階段 (iter 10): 只有 schema + 主要 function 簽名, 還沒實作。
- iter 11: scan_changed_files + tests
- iter 12: propose_from_file (Gemini Vision) + tests with mock
- iter 13: dedupe_against_jobs + tests
- iter 14: server route + React UI

設計重點:
- 不繞 require_review=True (P0 #4 學術誠信底線)
- ideate 只是省「找檔 + 想標題」的人力, review 步驟還是要走完
- watched_folders / IdeateConfig 走 yaml (新增 config.yaml, 跟 tts_config 分開)
- proposals.json 存 jobs/ 目錄, 跟 job state.json 並列
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from server.jobs import JobStore
    from server.schemas import SourceType


# ============================================================
# Schema
# ============================================================


class ProposalStatus(str, Enum):
    """proposal 生命週期狀態。"""

    PENDING = "pending"          # 剛產生, 待 user 決策
    APPROVED = "approved"        # user 核准, 已建立 job
    IGNORED = "ignored"          # user 拒絕
    EXPIRED = "expired"          # 過 30 天沒處理


class Proposal(TypedDict):
    """單一影片企劃 — 一份 PDF 可能產出多個 (每個對應不同主題 / 章節)。

    詳細語意見 docs/ideate-design.md "Schema" 段落。
    """

    id: str                              # prop_<uuid8>
    generated_at: str                    # ISO 8601 aware UTC
    source_file: str                     # 絕對路徑
    source_type: str                     # 對齊 SourceType.value (exam_pdf / slides_pdf / document)
    suggested_title: str                 # Gemini 建議的影片標題
    suggested_chapters: list[str]        # (slides_pdf 用) 章節大綱
    reason: str                          # 50~100 字, 為什麼值得做
    estimated_duration_min: int          # 預估時長
    status: str                          # ProposalStatus.value
    job_id: str | None                   # APPROVED 後填, 反查 job


class FileCandidate(TypedDict):
    """掃描階段的候選檔, 還沒送 Gemini 分析。"""

    path: str                            # 絕對路徑
    source_type: str                     # 來自 WatchedFolder.source_type
    mtime: float                         # last modified, time.time() 格式
    size_bytes: int


class WatchedFolder(TypedDict):
    """單一監看資料夾設定。"""

    path: str                            # 絕對或相對 (relative 解析自 PROJECT_ROOT)
    source_type: str                     # exam_pdf / slides_pdf / document
    scan_window_days: int                # 掃 N 天內修改的檔


class IdeateConfig(TypedDict):
    """整份 config.yaml 的 ideate 段落 — 後續 iter 加 PyYAML 讀檔。"""

    watched_folders: list[WatchedFolder]
    llm_model: str                       # 預設 "gemini-2.5-flash"
    max_proposals_per_file: int          # 預設 3
    enabled: bool                        # off 時 ideate 完全不跑


# ============================================================
# Main functions — scaffold, 全部 raise NotImplementedError
# 真實實作分散到 iter 11-13
# ============================================================


def scan_changed_files(config: IdeateConfig) -> list[FileCandidate]:
    """掃 watched_folders, 列出最近 N 天內修改的 PDF / md / pptx。

    iter 11 實作。

    參數:
        config: IdeateConfig, 含 watched_folders 設定

    回傳:
        list[FileCandidate], 已排除 hidden / 暫存檔 (.tmp / ~$*)

    不會做的事:
        - 不分析檔案內容 (那是 propose_from_file 的責任)
        - 不去重既有 job (那是 dedupe_against_jobs 的責任)
    """
    raise NotImplementedError("iter 11 補實作")


def propose_from_file(
    candidate: FileCandidate, config: IdeateConfig
) -> list[Proposal]:
    """Gemini Vision 看 PDF 首頁/目錄, 提出影片企劃。

    iter 12 實作。

    參數:
        candidate: 待分析的檔案
        config: IdeateConfig, 取 llm_model + max_proposals_per_file

    回傳:
        list[Proposal], 最多 max_proposals_per_file 個 (PENDING 狀態)

    錯誤處理:
        - Gemini API 限流 / parse 失敗 → 回 [] (不擋批次)
        - 檔案讀取失敗 → 回 [] + log warning
    """
    raise NotImplementedError("iter 12 補實作 (Gemini Vision call + JSON parse)")


def dedupe_against_jobs(
    proposals: list[Proposal], store: "JobStore"
) -> list[Proposal]:
    """過濾已有 job / 已上傳 YouTube / 前次已處理的 proposal。

    iter 13 實作。

    比對規則:
        - source.path 相同且 state=DONE → 已做過, skip
        - YoutubeUpload.video_id 存在 → 已上傳, skip
        - 前次 proposals.json 已 APPROVED/IGNORED → skip

    參數:
        proposals: 待去重的 proposal 清單
        store: 既有 JobStore (用既有 list/get/搜尋 API)

    回傳:
        list[Proposal] — 過濾後剩下的, 仍是 PENDING
    """
    raise NotImplementedError("iter 13 補實作")


def load_proposals(path: Path) -> list[Proposal]:
    """從 jobs/proposals.json 讀回前次企劃。檔不存在回 []。

    iter 11 一起實作 (因為 dedupe 要用)。
    """
    raise NotImplementedError("iter 11 補實作 (含 jsonl atomic write)")


def save_proposals(path: Path, proposals: list[Proposal]) -> None:
    """atomic write (寫 tmp + rename) 到 jobs/proposals.json。

    iter 11 一起實作。
    """
    raise NotImplementedError("iter 11 補實作")


# ============================================================
# 整合流程 (iter 14 接 server route 後再呼叫)
# ============================================================


def run_ideate(config: IdeateConfig, store: "JobStore", out_path: Path) -> int:
    """執行一次完整流程: scan → propose → dedupe → save。

    給 CLI / server route / 排程器呼叫。

    回傳:
        int — 寫進 out_path 的 proposal 數量
    """
    raise NotImplementedError(
        "iter 14+ 串完整流程 (這時 scan/propose/dedupe 都該實作完)"
    )
