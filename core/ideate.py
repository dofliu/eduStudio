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

import json
import os
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from server.jobs import JobStore
    from server.schemas import SourceType


# ============================================================
# 副檔名規則 — 每個 source_type 認哪些檔
# ============================================================

# source_type → 可掃的副檔名 (小寫, 含點). 不在這裡的會被 skip。
_SOURCE_TYPE_EXTENSIONS: dict[str, frozenset[str]] = {
    "exam_pdf": frozenset({".pdf"}),
    "slides_pdf": frozenset({".pdf"}),
    "document": frozenset({".pdf", ".md", ".txt"}),
}

# 跳過的檔案 (暫存 / hidden / 系統)
_SKIP_PREFIXES = ("~$", ".")            # ~$abc.pdf, .DS_Store
_SKIP_SUFFIXES = (".tmp", ".swp", ".bak")


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
    """掃 watched_folders, 列出最近 N 天內修改的 PDF / md / txt。

    參數:
        config: IdeateConfig, 含 watched_folders 設定

    回傳:
        list[FileCandidate], 已排除 hidden / 暫存檔 (.tmp / ~$* / .swp 等)

    不會做的事:
        - 不分析檔案內容 (那是 propose_from_file 的責任)
        - 不去重既有 job (那是 dedupe_against_jobs 的責任)
        - 不 follow symlink 出 watched_folders (避免無限迴圈 / 跑出限定範圍)
    """
    if not config.get("enabled", True):
        return []

    now = time.time()
    out: list[FileCandidate] = []
    for folder in config.get("watched_folders", []):
        folder_path = Path(folder["path"])
        if not folder_path.exists() or not folder_path.is_dir():
            # 設定有誤路徑不存在不該擋整批, 跳過即可
            continue

        source_type = folder["source_type"]
        valid_exts = _SOURCE_TYPE_EXTENSIONS.get(source_type)
        if not valid_exts:
            # 未知 source_type 跳過 (跟 SourceType enum 對齊)
            continue

        cutoff = now - folder["scan_window_days"] * 86400
        for f in folder_path.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in valid_exts:
                continue
            name = f.name
            if name.startswith(_SKIP_PREFIXES):
                continue
            if name.lower().endswith(_SKIP_SUFFIXES):
                continue
            try:
                stat = f.stat()
            except OSError:
                # 權限 / 暫時消失等狀況, 跳過不擋整批
                continue
            if stat.st_mtime < cutoff:
                continue
            out.append({
                "path": str(f.resolve()),
                "source_type": source_type,
                "mtime": stat.st_mtime,
                "size_bytes": stat.st_size,
            })

    # 排序: 最新修改在前 (UI 直覺看新東西)
    out.sort(key=lambda c: c["mtime"], reverse=True)
    return out


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
    """從 jobs/proposals.json 讀回前次企劃。檔不存在 / JSON 壞掉都回 []。

    grace 行為:
      - 檔不存在 (第一次跑) → []
      - JSON parse 失敗 (檔壞) → [] (不 raise, 但 log 給未來監控)
      - 結構不對 → []
    """
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, dict):
        return []
    items = raw.get("proposals")
    if not isinstance(items, list):
        return []
    # 不在這層做 schema 嚴格驗證 — 容錯讀回, 由上層 (UI / dedupe) 再過濾。
    return items  # type: ignore[return-value]


def save_proposals(path: Path, proposals: list[Proposal]) -> None:
    """atomic write 到 jobs/proposals.json (寫 .tmp + os.replace, 跨平台原子).

    結構:
        {
          "generated_at": "<aware UTC ISO>",
          "proposals": [Proposal, ...]
        }

    為什麼要 atomic: server 跑 ideate 寫檔時若 server crash / kill,
    semi-written JSON 會讓下次 load_proposals 直接掛。寫 .tmp + rename
    保證讀的人看到的永遠是「上次完整 commit 的版本」。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "proposals": proposals,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # os.replace 在 POSIX 是 atomic, 在 Windows 也 atomic 從 Vista+ 起
    # (跨檔案系統不行, 但同一目錄沒問題)
    os.replace(tmp, path)


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
