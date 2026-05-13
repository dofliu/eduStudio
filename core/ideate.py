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

    參數:
        candidate: 待分析的檔案 (PDF only — md/txt 不走 vision)
        config: IdeateConfig, 取 llm_model + max_proposals_per_file

    回傳:
        list[Proposal], 最多 max_proposals_per_file 個 (PENDING 狀態)

    錯誤處理 (一律不 raise, 回 [] 不擋批次):
        - 檔案不存在 / 不是 PDF: 回 []
        - PyMuPDF 開檔失敗 (損毀 / 加密): 回 []
        - Gemini API 限流 / parse 失敗 / 空回應: 回 []
        - JSON parse / schema 不對: 回 []
    """
    path = Path(candidate["path"])
    if not path.exists() or path.suffix.lower() != ".pdf":
        return []

    # 1. 讀前 5 頁 PDF, 渲染成縮圖 PNG bytes
    try:
        thumbs = _render_pdf_thumbs(path, max_pages=5)
    except Exception:
        return []
    if not thumbs:
        return []

    # 2. 呼叫 Gemini Vision (容錯一切失敗)
    try:
        raw_json = _call_gemini_vision(
            thumbs=thumbs,
            filename=path.name,
            source_type=candidate["source_type"],
            max_proposals=config.get("max_proposals_per_file", 3),
            model_name=config.get("llm_model", "gemini-2.5-flash"),
        )
    except Exception:
        return []

    # 3. Parse + build Proposal list
    try:
        return _parse_proposals_response(
            raw_json=raw_json,
            candidate=candidate,
            max_proposals=config.get("max_proposals_per_file", 3),
        )
    except Exception:
        return []


def _render_pdf_thumbs(pdf_path: Path, max_pages: int = 5) -> list[bytes]:
    """PDF 前 max_pages 頁 → 縮圖 PNG bytes (in-memory).

    用 PyMuPDF, 不寫檔. 200 DPI 對 Gemini Vision 足夠 (再高 token 飆升)。
    """
    # lazy import 避免 module-level 強拉 pymupdf
    import fitz  # type: ignore[import-untyped]

    doc = fitz.open(pdf_path)
    try:
        thumbs: list[bytes] = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            # zoom = 1.5 約等於 1500px 寬, Gemini Vision 看得清楚又不爆 token
            mat = fitz.Matrix(1.5, 1.5)
            pix = page.get_pixmap(matrix=mat)
            thumbs.append(pix.tobytes("png"))
        return thumbs
    finally:
        doc.close()


def _call_gemini_vision(
    *,
    thumbs: list[bytes],
    filename: str,
    source_type: str,
    max_proposals: int,
    model_name: str,
) -> str:
    """組 prompt + images, 呼叫 Gemini, 回 raw text。
    這函式失敗會 raise (caller 在 try/except 接住)。
    """
    # lazy import — google-genai 是核心 dep 但 import 慢
    from google import genai
    from google.genai import types

    from core.prompts_loader import load_prompt

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("缺 GEMINI_API_KEY")

    prompt = load_prompt("ideate_propose").format(
        filename=filename,
        source_type=source_type,
        max_proposals_per_file=max_proposals,
    )

    client = genai.Client(api_key=api_key)
    parts = [types.Part.from_bytes(data=b, mime_type="image/png") for b in thumbs]
    resp = client.models.generate_content(
        model=model_name,
        contents=parts + [prompt],
        config=types.GenerateContentConfig(
            temperature=0.3,         # 偏保守, 別亂編
            max_output_tokens=4096,
        ),
    )
    return (resp.text or "").strip()


def _parse_proposals_response(
    *,
    raw_json: str,
    candidate: FileCandidate,
    max_proposals: int,
) -> list[Proposal]:
    """解析 Gemini 回應字串成 Proposal list。失敗會 raise (caller 接住回 [])。"""
    # 處理 Gemini 偶爾包 markdown fence 的 case
    text = raw_json.strip()
    if text.startswith("```"):
        # 抓 ``` ... ``` 中間 (跳過 ```json / ``` 標記)
        import re as _re
        m = _re.search(r"```(?:json)?\s*\n?(.*?)```", text, _re.DOTALL)
        if m:
            text = m.group(1).strip()
    # 若 model 回的不是純 object, 嘗試抓第一個 {...} 區塊
    if not text.startswith("{"):
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return []
        text = text[first:last + 1]

    data = json.loads(text)
    raw_items = data.get("proposals") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        return []

    now_iso = datetime.now(timezone.utc).isoformat()
    out: list[Proposal] = []
    for i, item in enumerate(raw_items[:max_proposals]):
        if not isinstance(item, dict):
            continue
        title = (item.get("suggested_title") or "").strip()
        if not title:
            continue
        chapters = item.get("suggested_chapters") or []
        if not isinstance(chapters, list):
            chapters = []
        out.append({
            # 用 ns 級時間戳避免同秒內多次呼叫撞 id (review iter 22 抓出的 P0 bug)
            "id": f"prop_{time.time_ns()}_{i:02d}",
            "generated_at": now_iso,
            "source_file": candidate["path"],
            "source_type": candidate["source_type"],
            "suggested_title": title,
            "suggested_chapters": [str(c) for c in chapters][:6],
            "reason": (item.get("reason") or "").strip()[:300],
            "estimated_duration_min": int(item.get("estimated_duration_min", 5)),
            "status": ProposalStatus.PENDING.value,
            "job_id": None,
        })
    return out


def dedupe_against_jobs(
    proposals: list[Proposal],
    store: "JobStore",
    previous_proposals: list[Proposal] | None = None,
) -> list[Proposal]:
    """過濾已有 job / 已上傳 YouTube / 前次已處理的 proposal。

    比對規則 (任一中即 skip):
      1. JobStore 內 source.path == proposal.source_file 且 state=DONE → 已做過
      2. 上述 job 任一 youtube_uploads.video_id 非 None → 已上傳到 YouTube
      3. previous_proposals 中 source_file 相同且 status APPROVED/IGNORED → 用戶已決策

    參數:
        proposals: 待去重的新企劃 (通常從 propose_from_file 來)
        store: 既有 JobStore (走 store.list() 拿 JobRecord)
        previous_proposals: 上一輪 ideate 的 proposals.json 內容
            (None → 直接跑 load_proposals(PROPOSALS_PATH) 太隱性 + 易污染測試;
            caller 自己傳, dedupe 不偷讀檔)

    回傳:
        list[Proposal] — 仍是 PENDING, 順序保持輸入順序
    """
    if not proposals:
        return []

    # 1+2. 從 JobStore 蒐集「已做過 / 已上傳」的 source.path 集合
    done_paths: set[str] = set()
    uploaded_paths: set[str] = set()
    for rec in store.list():
        src_path = (rec.source.path or "").strip()
        if not src_path:
            continue
        normalized = _normalize_path(src_path)
        # state=DONE 視為「已做過」
        if rec.state.value == "done":
            done_paths.add(normalized)
        # 任一 YouTube upload 有 video_id 視為「已上傳」
        if rec.youtube_uploads:
            for upload in rec.youtube_uploads.values():
                if getattr(upload, "video_id", None):
                    uploaded_paths.add(normalized)
                    break

    # 3. 上次已 APPROVED / IGNORED 的 source_file
    decided_paths: set[str] = set()
    for prev in previous_proposals or []:
        if prev.get("status") in ("approved", "ignored"):
            decided_paths.add(_normalize_path(prev.get("source_file", "")))

    # 過濾
    out: list[Proposal] = []
    for p in proposals:
        path_norm = _normalize_path(p["source_file"])
        if path_norm in done_paths:
            continue
        if path_norm in uploaded_paths:
            continue
        if path_norm in decided_paths:
            continue
        out.append(p)
    return out


def _normalize_path(p: str) -> str:
    """跨平台 path 正規化 — Windows 大小寫不敏感, 統一 lower + / 分隔."""
    if not p:
        return ""
    return str(Path(p).resolve()).replace("\\", "/").lower() if Path(p).is_absolute() else p.replace("\\", "/").lower()


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
