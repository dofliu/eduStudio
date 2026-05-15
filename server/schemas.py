"""Pydantic schemas — request / response models 與 job 內部 state schema。

設計原則:
- request / response 採開放欄位 (Extra.allow) 給未來 PR 加欄位不破壞 API
- JobState 是內部寫到 state.json 的格式, 也直接當 GET /jobs/{id} 的 response
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


# ---------- Datetime normalize helper ----------
# 為什麼: 2026-05-10 utc_now() 從 datetime.utcnow() (naive) 換成 datetime.now(timezone.utc)
# (aware) 後, 既存 state.json 裡寫的 naive ISO 字串 parse 進來變 naive datetime,
# 跟新建 job 的 aware 混在一起時 sorted() / 比較會 TypeError. 這裡讀檔/組 model 時
# 把 naive 一律當 UTC 補 tzinfo, 全程記憶體裡都是 aware, sort/比較 安全.

def _ensure_aware_utc(v: datetime) -> datetime:
    if v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


AwareDatetime = Annotated[datetime, AfterValidator(_ensure_aware_utc)]


# ---------- Enums ----------

class SourceType(str, Enum):
    """支援的內容來源類型。

    PR-2a 支援 exam_pdf / slides_pdf (包現有 pipeline)。
    PR-2b-i 加 repo (folder walker -> outliner -> scriptor -> deck.json)。
    PR-3b 加 document (PDF/MD/TXT) / url (HTML 文章)。
    """
    EXAM_PDF = "exam_pdf"        # 考卷 PDF -> solve.py 三段 Gemini
    SLIDES_PDF = "slides_pdf"    # 簡報 PDF -> slide_ingest.py 章節+逐頁 narration
    REPO = "repo"                # 資料夾 / repo -> repo adapter
    DOCUMENT = "document"        # PDF / MD / TXT 單檔 long-form -> document adapter
    URL = "url"                  # 靜態 HTML 文章 -> url adapter


class JobState(str, Enum):
    """Job 的生命週期狀態。狀態機:

        pending ──ingest──► ingesting ──┬─── awaiting_review ──approve──┐
                                        │                                ▼
                                        └────────────────────────► rendering ──► done
                                                                                   │
                                                            (任何階段失敗) ─► failed
    """
    PENDING = "pending"
    INGESTING = "ingesting"           # 跑 solve.py / slide_ingest.py
    AWAITING_REVIEW = "awaiting_review"  # require_review=True 時停在這
    RENDERING = "rendering"           # 跑 batch + pipeline
    DONE = "done"
    FAILED = "failed"


# ---------- Request schemas ----------

class JobOptions(BaseModel):
    """建立 job 時的選項。所有欄位皆 optional, 採類型預設值。"""
    require_review: bool | None = Field(
        default=None,
        description="是否要在 ingest 完成後停下等人工 review。"
                    "exam_pdf 預設 True (硬規則 #1);slides_pdf 與後續 repo 預設 False。",
    )
    tts_provider: str | None = Field(
        default=None,
        description="TTS 後端 (edge | f5)。覆寫 tts_config.json 的設定,等同設 TTS_PROVIDER 環境變數。",
    )
    output_name: str | None = Field(
        default=None,
        description="輸出檔名前綴 (預設用 source 檔案 stem)。",
    )
    mock: bool = Field(
        default=False,
        description="ingest 走離線 mock 路徑 (不打 Gemini),供 smoke test / 開發用。"
                    "exam_pdf 用 solve.mock_output();slides_pdf 用 ingest_slides(mock=True);"
                    "repo 用 outliner.mock_outline + scriptor.mock_deck。",
    )
    max_files: int | None = Field(
        default=None,
        description="repo source 限制掃幾個檔 (預設 50)。其他 source_type 忽略此欄位。",
    )
    theme: str | None = Field(
        default=None,
        description="pptx renderer 主題 (PR-5a): forest (預設, 教學) / navy (科技). "
                    "只影響 repo / document / url 三種 (走 PptxStyleRenderer);"
                    "exam_pdf / slides_pdf 不適用 (黑板 / 投影片底圖固定色)。",
    )
    hardsub: bool = Field(
        default=False,
        description="是否把 SRT 字幕直接燒進 MP4 (PR-5c). 預設 False — YouTube "
                    "上傳吃分離 SRT 比較好, 燒字幕主要給離線播放用。",
    )
    prepend_intro: bool = Field(
        default=False,
        description="是否把個人 intro 影片接到主影片前 (iter 41). "
                    "Intro 路徑取自 core.config.get_intro_video_path() "
                    "(env CLAUDE_INTRO_VIDEO_PATH 可覆寫). SRT 時間戳會自動 "
                    "往後推 intro 長度, 字幕跟畫面對齊.",
    )
    length_mode: str | None = Field(
        default=None,
        description="影片長度模式 (iter 43): quick = 8~15 分鐘 YT 快速講解 (預設, "
                    "保現有行為), lecture = 60~180 分鐘授課影片 (10~15 章 / "
                    "每章 6~12 張投影片 / narration 180~280 字). 只影響 "
                    "repo / document / url 三類; exam_pdf / slides_pdf 由 PDF "
                    "題數或頁數決定影片數, 不適用.",
    )
    ai_generate_diagrams: bool = Field(
        default=False,
        description="iter 56: 對每 section 跑 Gemini 2.5 Flash Image 產一張 AI "
                    "架構圖, 寫進 figures/ai_<section_id>.png 給 scriptor 配圖. "
                    "成本考量預設 False — 用戶 opt-in. 只影響 document / repo / "
                    "url (走 scriptor figure-aware 流程). 失敗的 section 跳過, "
                    "不擋 ingest.",
    )

    model_config = ConfigDict(extra="allow")


class JobSource(BaseModel):
    """來源描述。

    PR-2a/2b-i: path 指本機絕對路徑 (檔或資料夾依 source_type 而定)。
    PR-3b: source_type=url 時改用 url 欄位; 其他類型仍走 path。
    """
    path: str | None = Field(
        default=None,
        description="server 本機可讀的絕對路徑。source_type=exam_pdf / slides_pdf / "
                    "document 為檔案; source_type=repo 為資料夾; source_type=url 不用。",
    )
    url: str | None = Field(
        default=None,
        description="網址, 僅 source_type=url 使用 (必須 http:// 或 https://)。",
    )

    model_config = ConfigDict(extra="allow")


class CreateJobRequest(BaseModel):
    source_type: SourceType
    source: JobSource
    options: JobOptions = Field(default_factory=JobOptions)

    model_config = ConfigDict(extra="allow")


class UpdateDeckRequest(BaseModel):
    """PUT /jobs/{id}/draft 的 body — 整個 deck.json 內容。
    刻意不在這裡硬寫 schema,因為 v1 (考卷) / slides / 未來 repo 的 deck schema 不同。
    """
    deck: dict[str, Any]


# ---------- Response / state schemas ----------

class StageInfo(BaseModel):
    """單一階段的執行紀錄,寫進 state.json 給 caller 與 debug 用。"""
    name: str
    state: str  # pending | running | done | failed
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    error: str | None = None


class Artifact(BaseModel):
    """產出的檔案 metadata。path 是相對於 jobs/<id>/ 的路徑。"""
    name: str
    path: str
    size_bytes: int
    kind: str  # mp4 | srt | json | png | other


# ---------- YouTube upload (PR-3f) ----------

class YoutubeUploadState(str, Enum):
    """YouTube 上傳的獨立狀態機,跟 Job 主狀態機分離 (上傳失敗不該讓 Job 倒退)。"""
    PENDING = "pending"        # 還沒按上傳
    UPLOADING = "uploading"    # 背景 task 正在跑
    DONE = "done"
    FAILED = "failed"


class YoutubeUpload(BaseModel):
    """單一 artifact (通常 = 一支 mp4) 的 YouTube 上傳記錄。
    寫到 JobRecord.youtube_uploads[<artifact_name>] 之下。
    """
    state: YoutubeUploadState = YoutubeUploadState.PENDING
    title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    privacy: str = "unlisted"      # unlisted | public | private
    category: str = "27"            # 27 = Education, 28 = Science & Tech
    video_id: str | None = None
    url: str | None = None
    caption_id: str | None = None   # SRT captions.insert 結果
    progress_percent: int = 0       # 0~100, 上傳中由背景 task 更新
    started_at: AwareDatetime | None = None
    uploaded_at: AwareDatetime | None = None
    error: str | None = None
    caption_error: str | None = None  # 字幕上傳失敗不致命, 影片仍可用

    model_config = ConfigDict(extra="allow")


class JobRecord(BaseModel):
    """寫到 jobs/<id>/state.json 的完整內容,也直接當 GET /jobs/{id} 的 response。"""
    id: str
    source_type: SourceType
    source: JobSource
    options: JobOptions
    state: JobState
    created_at: AwareDatetime
    updated_at: AwareDatetime
    stages: list[StageInfo] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    error: str | None = None
    # 內部欄位: ingest 後的 deck path, render 後的 output dir
    deck_path: str | None = None
    output_dir: str | None = None
    # PR-3f: YouTube 上傳記錄, key 是 artifact name (例 "q1.mp4")
    # 為什麼是 dict 不是 list: 多 artifact 各自獨立, lookup 要 O(1), append 不太需要
    youtube_uploads: dict[str, YoutubeUpload] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class CreateJobResponse(BaseModel):
    job_id: str
    state: JobState
    status_url: str


class JobListResponse(BaseModel):
    jobs: list[JobRecord]


# ---------- Utility ----------

def utc_now() -> datetime:
    """統一 timestamp 來源, 一律帶 UTC tzinfo。

    為什麼要 tz-aware: 寫進 state.json 的 ISO 字串會帶 +00:00, 前端 new Date(s)
    才不會誤當本地時間 (差 8 小時)。從 datetime.utcnow() (naive) 改過來。
    """
    return datetime.now(timezone.utc)
