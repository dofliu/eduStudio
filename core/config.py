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


def get_gemini_api_key() -> str | None:
    return os.environ.get(GEMINI_API_KEY_ENV)


# ---------- LLM 模型 ----------
GEMINI_MODEL = "gemini-2.5-flash"


# ---------- 影片參數 ----------
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
PAUSE_AFTER_EACH = 0.6


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


# Intro normalize cache 放 PROJECT_ROOT/assets/, 不是 PROJECT_ROOT 根
# (跟既有 photos/ voices/ 等 asset 目錄並列)
ASSETS_DIR = PROJECT_ROOT / "assets"
