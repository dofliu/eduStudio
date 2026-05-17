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
    ai_generate_mermaid: bool = Field(
        default=False,
        description="iter 57b: Gemini 2.5 Flash text 生 mermaid syntax → 透過 "
                    "mermaid.ink 渲染成 PNG. 比 ai_generate_diagrams 便宜 (text "
                    "比 image gen 一個 OoM), 但風格只有流程圖一種. 適合 repo / "
                    "document. 寫進 figures/mermaid_<section_id>.png. 失敗 skip, "
                    "不擋 ingest. 兩個 opt-in 都開時, scriptor 自動配圖優先 ai_*, "
                    "用戶可在 UI 手動換.",
    )
    prepend_cover: bool = Field(
        default=False,
        description="iter 62: 在 intro 之後 / 主內容之前插入封面頁 (deck_title + "
                    "講者 + 日期 + 單位), 配開場口白 narration. 講者 / 單位由 "
                    "core.config 預設或 env CLAUDE_COVER_SPEAKER / CLAUDE_COVER_ORG "
                    "覆寫. 只影響 repo / document / url (multi-section concat 路徑); "
                    "exam_pdf 每題獨立 mp4 不適用.",
    )
    cover_speaker: str | None = Field(
        default=None,
        description="iter 62b: per-job 封面講者覆寫. None / 空字串 → 用 "
                    "core.config.get_cover_speaker() (env 或預設). 只 prepend_cover=True "
                    "時有意義.",
    )
    cover_org: str | None = Field(
        default=None,
        description="iter 62b: per-job 封面單位覆寫. 同上 fallback 規則.",
    )
    cover_date: str | None = Field(
        default=None,
        description="iter 62b: per-job 封面日期 (字串, 建議 YYYY-MM-DD). "
                    "None / 空字串 → 用今天日期. 不檢查格式 — 給用戶自由 "
                    "(可以寫「2026 春季」等).",
    )
    cover_narration: str | None = Field(
        default=None,
        description="iter 65: per-job 封面開場口白覆寫. None / 空字串 → 用 "
                    "core.cover_gen._COVER_NARRATION_TEMPLATE 套 speaker / "
                    "title / org. 非空 → 直接拿用戶字串當 narration 餵 TTS, "
                    "不再套模板. 長度建議 60~180 字 (跟 scriptor narration "
                    "規範一致).",
    )
    # iter 63: 結尾頁 (跟 prepend_cover 對稱)
    append_outro: bool = Field(
        default=False,
        description="iter 63: 在主內容後插入結尾頁 (大字「謝謝聆聽」+ 講者 + "
                    "單位 + URL), 配結尾口白. 講者 / 單位用 cover_speaker / "
                    "cover_org 共用 (沒填用 env 預設); URL 用 outro_url 欄. "
                    "只影響 repo / document / url (multi-section concat).",
    )
    outro_thanks: str | None = Field(
        default=None,
        description="iter 63: per-job 結尾大字 (預設「謝謝聆聽」). 空 → 預設.",
    )
    outro_url: str | None = Field(
        default=None,
        description="iter 63: per-job 結尾頁聯絡 URL (預設 doflab.cc). 不檢查 "
                    "格式 — 可放 GitHub / email / 任何字串.",
    )
    outro_narration: str | None = Field(
        default=None,
        description="iter 63: per-job 結尾口白覆寫. None / 空 → 用模板 "
                    "「今天的內容到此告一段落, 感謝各位的時間…」.",
    )
    # iter 66: outro 個人影片 (跟 iter 41 prepend_intro 對稱, 串到 final 最後)
    append_outro_video: bool = Field(
        default=False,
        description="iter 66: 把預設 / env 設定的 outro mp4 (CLAUDE_OUTRO_VIDEO_PATH) "
                    "串接到 final.mp4 最後. 跟 prepend_intro 對稱. 只影響多章 "
                    "merge 路徑 (repo / document / url / slides_pdf 整份 render).",
    )
    # iter 67: outro 結尾頁 QR code
    show_qr_on_outro: bool = Field(
        default=False,
        description="iter 67: outro 結尾頁左下右下各畫一個 QR code. 左下指 "
                    "outro_url (網頁), 右下指 outro_youtube_url (頻道). 只 "
                    "append_outro=True 才有效.",
    )
    outro_youtube_url: str | None = Field(
        default=None,
        description="iter 67: 結尾頁 YouTube 頻道 URL (給 QR code 用). "
                    "None / 空 → fallback 到 CLAUDE_OUTRO_YOUTUBE_URL env / "
                    "預設 https://www.youtube.com/@dofliu.",
    )
    # iter 76 (A3): 自訂主題色票 override — 用 hex string (#RRGGBB / RRGGBB).
    # 3 個最影響視覺的 token. 其他 5 個 (banner / secondary / code_bg /
    # code_border / file_header) 仍跟主題基底 — 簡化用戶選擇.
    palette_bg: str | None = Field(
        default=None,
        description="iter 76: 自訂背景色 hex (例 '#1e3a2e' 或 '1e3a2e'). "
                    "None → 用主題預設.",
    )
    palette_primary: str | None = Field(
        default=None,
        description="iter 76: 自訂主色 (標題 / bullet 文字), hex.",
    )
    palette_highlight: str | None = Field(
        default=None,
        description="iter 76: 自訂強調色 (底線 / marker / banner 字), hex.",
    )
    # iter 80 (D2): 字幕樣式 — 只在 hardsub=True 時有效
    subtitle_font_size: int | None = Field(
        default=None,
        description="iter 80: 燒字幕字級 (預設 22, 對 1920x1080 視訊適中). "
                    "建議 16-32 範圍. None → 用預設.",
    )
    subtitle_primary_color: str | None = Field(
        default=None,
        description="iter 80: 字幕字色 hex (#RRGGBB / RRGGBB). None → 白 #FFFFFF.",
    )
    subtitle_outline_color: str | None = Field(
        default=None,
        description="iter 80: 字幕描邊色 hex. None → 黑 #000000.",
    )
    # iter 83 (B1+B2): 影片長寬比 + 解析度
    aspect_ratio: str | None = Field(
        default=None,
        description="iter 83: 影片長寬比, '16:9' (橫向, 預設) 或 '9:16' "
                    "(縱向, 給 Shorts/TikTok/Reels). None → '16:9'.",
    )
    resolution: str | None = Field(
        default=None,
        description="iter 83: 影片解析度, '1080p' (預設) / '1440p' / '4K'. "
                    "None → '1080p'. 1440p 跟 4K 渲染時間明顯較長 (2-3x).",
    )
    short_video_layout: bool = Field(
        default=False,
        description="iter 88: 短影片 layout — 巨大字居中 + image 滿版下半, "
                    "給 Shorts / TikTok / Reels 即時震撼用. ultra_quick mode "
                    "UI 預設自動勾, 用戶可手動取消. cover/outro 不受影響.",
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
