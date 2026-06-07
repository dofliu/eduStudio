"""集中所有 path / env var key / model name 常數。

之前散在 pipeline.py / solve.py / slide_ingest.py / publish.py 各自定義 BASE_DIR、
讀 GEMINI_API_KEY、Gemini MODEL 字串硬編。集中到這裡的好處:
- 未來 FastAPI 層只需要 import core.config 就能組路徑,不必再 import 整個 pipeline
- 換模型 / 換目錄結構時只動一個地方
- 環境變數命名集中,文件好寫

注意: 這個 module 只能放純常數與輕量 helper, 不可有 side effect (印 log、reconfigure
stdout 等),因為 FastAPI 啟動時會被 eager import。
"""
from __future__ import annotations

import os
from pathlib import Path


# ---------- 專案根目錄 ----------
# core/ 的上一層就是專案 root。所有 BASE_DIR 都統一從這裡推。
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 工作 / 輸出 / 資源目錄
WORK_DIR = PROJECT_ROOT / "work"
OUTPUT_DIR = PROJECT_ROOT / "output"
EXAMS_DIR = PROJECT_ROOT / "exams"
SLIDES_DIR = PROJECT_ROOT / "slides"
VOICES_DIR = PROJECT_ROOT / "voices"
PHOTOS_DIR = PROJECT_ROOT / "photos"
VIDEOS_DIR = PROJECT_ROOT / "videos"

# 設定檔 (各模組現在直接讀這幾個檔)
PIPELINE_CONFIG_PATH = PROJECT_ROOT / "pipeline_config.json"
TTS_CONFIG_PATH = PROJECT_ROOT / "tts_config.json"
PRONUNCIATION_PATH = PROJECT_ROOT / "pronunciation.json"

# v4 階段 2 B: 自動內容企劃 (core/ideate.py) 用
# proposals.json 跟 job state.json 並列, 放 jobs/ 目錄但不是某個 job 的
JOBS_DIR = PROJECT_ROOT / "jobs"
PROPOSALS_PATH = JOBS_DIR / "proposals.json"
IDEATE_CONFIG_PATH = PROJECT_ROOT / "ideate_config.yaml"

# eduStudio 合併 (PR-M1, 2026-06-05): Project 薄層的容器目錄。
# 每個 Project 一個資料夾 projects/{pid}/，與 jobs/ 並列 (core/project.py 用)。
PROJECTS_DIR = PROJECT_ROOT / "projects"

# eduStudio 合併 (B-2): translateGemma 學習工具 (單字卡 SM-2) 的 SQLite db。
# 預設落 PROJECT_ROOT/learning.db；env LEARNING_DB_PATH 可覆寫 (測試用 tmp)。
LEARNING_DB_PATH = PROJECT_ROOT / "learning.db"


def get_learning_db_path() -> str:
    """學習工具 db 路徑。env LEARNING_DB_PATH 可覆寫。"""
    return os.environ.get("LEARNING_DB_PATH", str(LEARNING_DB_PATH))


# eduStudio 合併 (B-2): translateGemma 翻譯歷史 SQLite db。env HISTORY_DB_PATH 可覆寫。
HISTORY_DB_PATH = PROJECT_ROOT / "translate_history.db"


def get_history_db_path() -> str:
    """翻譯歷史 db 路徑。env HISTORY_DB_PATH 可覆寫。"""
    return os.environ.get("HISTORY_DB_PATH", str(HISTORY_DB_PATH))


# eduStudio 合併 (C-4): infoCard 分享連結 SQLite db（取代原 in-memory Map）。
SHARE_DB_PATH = PROJECT_ROOT / "infocard_shares.db"


def get_share_db_path() -> str:
    """infoCard 分享 db 路徑。env SHARE_DB_PATH 可覆寫。"""
    return os.environ.get("SHARE_DB_PATH", str(SHARE_DB_PATH))


# eduStudio: 視覺成品素材庫 SQLite db（每次成功生成自動保存，免手動加入 Project）。
VISUAL_LIBRARY_DB_PATH = PROJECT_ROOT / "infocard_visual_library.db"


def get_visual_library_db_path() -> str:
    """視覺素材庫 db 路徑。env VISUAL_LIBRARY_DB_PATH 可覆寫（測試用 tmp）。"""
    return os.environ.get("VISUAL_LIBRARY_DB_PATH", str(VISUAL_LIBRARY_DB_PATH))


# eduStudio 統一介面：Gemini 用量計帳 SQLite db（成本面板真實統計）。
USAGE_DB_PATH = PROJECT_ROOT / "usage.db"


def get_usage_db_path() -> str:
    """用量計帳 db 路徑。env USAGE_DB_PATH 可覆寫（測試用 tmp）。"""
    return os.environ.get("USAGE_DB_PATH", str(USAGE_DB_PATH))


# ---------- 字型 ----------
# Windows: 微軟正黑體 (中文)
# 環境變數 CLAUDE_FONT_PATH / CLAUDE_FALLBACK_FONT_PATH 可覆寫
DEFAULT_FONT_PATH = "C:/Windows/Fonts/msjh.ttc"
DEFAULT_FALLBACK_FONT_PATH = "C:/Windows/Fonts/seguisym.ttf"
# 等寬字型 — pptx Forest 風格的程式碼區塊用 (PR-2b-ii 引入)
DEFAULT_MONO_FONT_PATH = "C:/Windows/Fonts/consola.ttf"


def get_font_path() -> str:
    """主字型路徑。優先吃環境變數 CLAUDE_FONT_PATH,沒設就用 Windows 預設。"""
    return os.environ.get("CLAUDE_FONT_PATH", DEFAULT_FONT_PATH)


def get_fallback_font_path() -> str:
    """fallback 字型路徑(渲染主字型缺字時用,通常是 Segoe UI Symbol)"""
    return os.environ.get("CLAUDE_FALLBACK_FONT_PATH", DEFAULT_FALLBACK_FONT_PATH)


def get_mono_font_path() -> str:
    """等寬字型路徑(程式碼區塊用)。"""
    return os.environ.get("CLAUDE_MONO_FONT_PATH", DEFAULT_MONO_FONT_PATH)


# ---------- 環境變數 ----------
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"
TTS_PROVIDER_ENV = "TTS_PROVIDER"

# CORS 允許來源。預設只給本機自用，部署時用環境變數放行實際前端 origin。
ALLOWED_ORIGINS_ENV = "EDUSTUDIO_ALLOWED_ORIGINS"
DEFAULT_ALLOWED_ORIGINS = ["http://127.0.0.1:8000", "http://localhost:8000"]


def get_allowed_origins() -> list[str]:
    """CORS allow_origins 清單。

    讀環境變數 EDUSTUDIO_ALLOWED_ORIGINS（逗號分隔），未設則回預設本機 origin。
    同源 `/app` 不經過 CORS，不受此清單影響；此清單只管跨 origin 的瀏覽器呼叫。
    設成 `*` 可全開（不建議，僅供臨時除錯）。
    """
    raw = os.environ.get(ALLOWED_ORIGINS_ENV)
    if not raw or not raw.strip():
        return list(DEFAULT_ALLOWED_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


def get_gemini_api_key() -> str | None:
    """Gemini 金鑰：設定頁(settings.json)優先，否則環境變數。"""
    try:
        from core.settings import get_setting
        k = get_setting("gemini_api_key")
        if k:
            return k
    except Exception:
        pass
    return os.environ.get(GEMINI_API_KEY_ENV)


# eduStudio 設定頁（個人品牌 / API / 模型）持久化檔。
SETTINGS_PATH = PROJECT_ROOT / "settings.json"


def get_settings_path() -> str:
    """設定 json 路徑。env ES_SETTINGS_PATH 可覆寫（測試用 tmp）。"""
    return os.environ.get("ES_SETTINGS_PATH", str(SETTINGS_PATH))


# ---------- LLM 模型 ----------
GEMINI_MODEL = "gemini-2.5-flash"


def get_gemini_model() -> str:
    """Gemini 文字模型：設定頁 text_model 優先，否則預設 GEMINI_MODEL。

    讓影片 pipeline（outliner/scriptor/翻譯）與視覺站一樣吃設定頁選的模型。
    """
    try:
        from core.settings import get_setting
        m = get_setting("text_model")
        if m:
            return m
    except Exception:
        pass
    return GEMINI_MODEL


# ---------- 語言 ----------
# eduStudio 合併 (PR-M1): 全系統 canonical 語言碼 (BCP-47 連字號)。
# 底線式 zh_TW 只在 translateGemma 邊界出現 (core/langcode.py 負責轉換)。
CANONICAL_LANG = "zh-TW"


# ---------- 影片參數 ----------
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
PAUSE_AFTER_EACH = 0.6


# iter 83 (B1+B2 Option B): runtime 切影片尺寸 (橫向 / 縱向 + 解析度).
# 用 monkey-patch 模式 — 接 set_video_dimensions(aspect, resolution) 改
# module-level 常數, render 完 restore. 非 thread-safe, 跟現有 sequential
# job runner 設計相容 (v4 worker pool 啟動後要走別的方案).

# 各 aspect × resolution 對應的 (width, height) 表.
# 1080p / 1440p / 4K 在 16:9 跟 9:16 之間切換時直接整數對調.
VIDEO_DIMENSIONS: dict[tuple[str, str], tuple[int, int]] = {
    ("16:9", "1080p"): (1920, 1080),
    ("16:9", "1440p"): (2560, 1440),
    ("16:9", "4K"):    (3840, 2160),
    ("9:16", "1080p"): (1080, 1920),
    ("9:16", "1440p"): (1440, 2560),
    ("9:16", "4K"):    (2160, 3840),
}


def resolve_video_dimensions(
    aspect_ratio: str = "16:9", resolution: str = "1080p",
) -> tuple[int, int]:
    """從 (aspect_ratio, resolution) 取對應 (width, height).
    無效組合 fallback 到 (1920, 1080)."""
    return VIDEO_DIMENSIONS.get((aspect_ratio, resolution), (1920, 1080))


class video_dimensions_override:
    """context manager — render 期間暫時 patch module-level 影片尺寸.

    使用:
        with video_dimensions_override("9:16", "1080p"):
            # core.config.VIDEO_WIDTH == 1080, VIDEO_HEIGHT == 1920
            pipeline.render_video(...)
        # 出 with 後 restore 到原值

    為什麼用 module attr monkey-patch 而非傳參:
    pipeline + pptx_style + visuals 散一堆 module-level 常數捕獲, 改全部
    function signature 加 dimensions 是 2-3 天 refactor. 短期用這方案 ship.
    v4 worker 啟動後要走「per-render 不共享 module state」方案.

    非 thread-safe — 兩個 thread 同時開 context 會搶. 跟 server.runner.py
    現有 sequential job 設計相容.
    """

    def __init__(self, aspect_ratio: str = "16:9", resolution: str = "1080p"):
        self.aspect_ratio = aspect_ratio
        self.resolution = resolution
        self._old_w: int | None = None
        self._old_h: int | None = None

    # 需要 patch 的所有 module — `from X import Y` 會在每個 module 內留
    # 自己的 reference, 必須各個都 patch. 否則 render 仍讀舊值.
    _PATCH_TARGETS = (
        ("core.config", "VIDEO_WIDTH", "VIDEO_HEIGHT"),
        ("core.visuals", "VIDEO_WIDTH", "VIDEO_HEIGHT"),
        ("core.render.pptx_style", "VIDEO_WIDTH", "VIDEO_HEIGHT"),
        ("pipeline", "WIDTH", "HEIGHT"),
    )

    def _set_all(self, w: int, h: int) -> None:
        import sys
        for mod_name, w_attr, h_attr in self._PATCH_TARGETS:
            mod = sys.modules.get(mod_name)
            if mod is None:
                continue
            if hasattr(mod, w_attr):
                setattr(mod, w_attr, w)
            if hasattr(mod, h_attr):
                setattr(mod, h_attr, h)
        # CONTENT_BOTTOM 重算 (跟 height 連動). pipeline.py 也 import 了該值,
        # 給 BlackboardRenderer / SlideRenderer 用 — 不 patch 會在 portrait
        # 下用 stale 900 把 slide 底部切到 1020+ 變空白 (iter 85 CR4 抓的).
        for mod_name in ("core.visuals", "core.render.pptx_style", "pipeline"):
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, "CONTENT_BOTTOM"):
                from core.visuals import SUBTITLE_BAND_HEIGHT
                setattr(mod, "CONTENT_BOTTOM", h - SUBTITLE_BAND_HEIGHT)

    def __enter__(self) -> tuple[int, int]:
        import sys
        # 確保 pipeline / pptx_style 已 import (測試環境可能還沒)
        try:
            import core.visuals  # noqa
            import core.render.pptx_style  # noqa
            import pipeline  # noqa
        except ImportError:
            pass
        this_mod = sys.modules[__name__]
        self._old_w = this_mod.VIDEO_WIDTH
        self._old_h = this_mod.VIDEO_HEIGHT
        w, h = resolve_video_dimensions(self.aspect_ratio, self.resolution)
        self._set_all(w, h)
        return (w, h)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._old_w is not None and self._old_h is not None:
            self._set_all(self._old_w, self._old_h)
        return None


# ---------- Intro 影片串接 (iter 41) ----------
# 用戶個人 ~8 秒的開場投影片影片. 啟用 JobOptions.prepend_intro=True 時,
# 渲染完成的主影片前面會接這支 intro, 統一 YT 上傳的品牌開場.
#
# 規格要求: H.264 1920x1080 30fps yuv420p — 跟主影片渲染輸出對齊.
# Audio 不一致由 video_concat.normalize_intro_audio 自動轉檔處理 (一次性快取).
#
# iter 44: 改用專案內相對路徑 (docs/intro_journal.mp4), 不再寫死 D:/Dropbox.
# 好處: clone 出來不必另外改路徑; 換主機 / Docker 都跟著走.
# 要換 intro 直接覆蓋 docs/intro_journal.mp4 (mtime 變動會讓 normalize cache 自動 invalidate).
DEFAULT_INTRO_VIDEO_PATH = str(PROJECT_ROOT / "docs" / "intro_journal.mp4")


def get_intro_video_path() -> str:
    """Intro mp4 路徑. 環境變數 CLAUDE_INTRO_VIDEO_PATH 可覆寫."""
    return os.environ.get("CLAUDE_INTRO_VIDEO_PATH", DEFAULT_INTRO_VIDEO_PATH)


# ---------- Outro 個人影片 (iter 66, 跟 intro 對稱) ----------
DEFAULT_OUTRO_VIDEO_PATH = str(PROJECT_ROOT / "docs" / "outro_journal.mp4")


def get_outro_video_path() -> str:
    """Outro mp4 路徑 (跟 intro 對稱, 串接到 final 最後).
    環境變數 CLAUDE_OUTRO_VIDEO_PATH 可覆寫."""
    return os.environ.get("CLAUDE_OUTRO_VIDEO_PATH", DEFAULT_OUTRO_VIDEO_PATH)


# Intro normalize cache 放 PROJECT_ROOT/assets/, 不是 PROJECT_ROOT 根
# (跟既有 photos/ voices/ 等 asset 目錄並列)
ASSETS_DIR = PROJECT_ROOT / "assets"


# ---------- 封面頁預設 (iter 62) ----------
# prepend_cover=True 時, 自動在影片開頭插一張封面頁: 主題 + 講者 + 日期 + 單位.
# env 可覆寫單一欄位, 沒覆寫就用這裡的 default.
DEFAULT_COVER_SPEAKER = "劉瑞弘 副教授"
DEFAULT_COVER_ORG = "國立勤益科技大學 · 智慧自動化工程系 · DofLab"


def _brand_setting(key: str) -> str | None:
    """讀設定頁的個人品牌欄位（brand_speaker/brand_org/brand_url）；失敗回 None。"""
    try:
        from core.settings import get_setting
        v = get_setting(key)
        return v or None
    except Exception:
        return None


def get_cover_speaker() -> str:
    """封面講者. 優先序: 設定頁個人品牌 > env CLAUDE_COVER_SPEAKER > 預設."""
    return _brand_setting("brand_speaker") or os.environ.get("CLAUDE_COVER_SPEAKER") or DEFAULT_COVER_SPEAKER


def get_cover_org() -> str:
    """封面單位. 優先序: 設定頁 > env CLAUDE_COVER_ORG > 預設."""
    return _brand_setting("brand_org") or os.environ.get("CLAUDE_COVER_ORG") or DEFAULT_COVER_ORG


# ---------- 結尾頁預設 (iter 63) ----------
# append_outro=True 時, 自動在主內容後插一張結尾頁: 大字「謝謝聆聽」+ 講者 +
# lab url + 單位. 跟封面對稱, narration 模板簡短.
DEFAULT_OUTRO_THANKS = "謝謝聆聽"
DEFAULT_OUTRO_URL = "doflab.cc"


def get_outro_thanks() -> str:
    """結尾頁主標題 (大字). env CLAUDE_OUTRO_THANKS 可覆寫."""
    return os.environ.get("CLAUDE_OUTRO_THANKS", DEFAULT_OUTRO_THANKS)


def get_outro_url() -> str:
    """結尾頁聯絡 URL. 優先序: 設定頁個人品牌 brand_url > env CLAUDE_OUTRO_URL > 預設.

    不檢查 URL 格式 — 給用戶自由 (可放 GitHub / email / lab 網址 / 任何字串)."""
    return _brand_setting("brand_url") or os.environ.get("CLAUDE_OUTRO_URL") or DEFAULT_OUTRO_URL


def get_brand_footer() -> str:
    """個人品牌頁尾「講者 · 單位 · 連結」字串，給簡報母片頁尾 / 圖卡底部共用。
    只取設定頁實際填的欄位（不帶預設值）；都沒填回空字串（呼叫端據此略過頁尾）。"""
    parts = [_brand_setting(k) for k in ("brand_speaker", "brand_org", "brand_url")]
    parts = [str(p).strip() for p in parts if p and str(p).strip()]
    return "  ·  ".join(parts)


# iter 67: 結尾頁 QR code — 第二個 URL 給 YouTube 頻道用
DEFAULT_OUTRO_YOUTUBE_URL = "https://www.youtube.com/@dofliu"


def get_outro_youtube_url() -> str:
    """結尾頁 YouTube 頻道 URL (給 QR code 用). env CLAUDE_OUTRO_YOUTUBE_URL 可覆寫."""
    return os.environ.get("CLAUDE_OUTRO_YOUTUBE_URL", DEFAULT_OUTRO_YOUTUBE_URL)
