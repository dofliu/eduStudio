"""考卷檢討影片自動生成系統 — Core 模組

PR-1 階段: 這個 package 是「再匯出層」, 主要實作仍在頂層的 pipeline.py /
solve.py / slide_ingest.py / batch.py / publish.py / tts_backend.py 內。
未來 PR-2 (FastAPI) 應該只 import core, 不要直接 import 頂層 CLI 腳本。

公開 API 列表 (穩定, 後續 PR 應維持簽章不變):

渲染:
    render_video(json_path, out_name, start_step=None) -> async, MP4 + SRT

PDF / 簡報 ingestion:
    solve_pdf(pdf_path) -> dict          # 考卷 PDF → exam.json (3-pass Gemini)
    ingest_slides(pdf_path, out_json, *, mock, single, brief)  # 簡報 PDF → exam.json

Batch / 編排:
    problem_to_v0_json(exam_title, prob) -> dict   # v1 → v0 schema 轉換

TTS:
    load_tts_backend(config_path=None) -> TTSBackend
    normalize_text(text) -> str           # 進 TTS 前的文字正規化

YouTube:
    upload_video(youtube, video_path, *, title, description, tags, privacy, category) -> str
    upload_caption(youtube, video_id, srt_path, language="zh-TW", name="繁體中文") -> str
    get_youtube_credentials() -> Credentials
    publish_artifact(video_path, *, title, description, tags, privacy, category, srt_path,
                     on_progress) -> PublishResult     # PR-3f, server 用 (含 progress callback)
    auto_youtube_meta(deck, problem_id, *, source_type) -> dict   # PR-3f, 預填產生器

文字工具:
    strip_latex(text) -> str
    clean_json_escapes(text) -> str

設定 (常數 / paths):
    透過 from core import config 取用
"""
from __future__ import annotations

# config / runtime 是純常數與 helper, 安全 eager import
from . import config
from .runtime import setup_utf8_stdout
from .text_utils import strip_latex, clean_json_escapes

__all__ = [
    # config / runtime
    "config",
    "setup_utf8_stdout",
    # text utils
    "strip_latex",
    "clean_json_escapes",
    # 以下函式採 lazy import (見 __getattr__),避免 import core 就把整條 pipeline
    # 的重型依賴 (PIL / fitz / google-genai / googleapiclient 等) 都拉進來。
    "render_video",
    "solve_pdf",
    "ingest_slides",
    "problem_to_v0_json",
    "load_tts_backend",
    "normalize_text",
    "TTSBackend",
    "upload_video",
    "upload_caption",
    "get_youtube_credentials",
    # PR-3f: server 用 YouTube helper
    "publish_artifact",
    "auto_youtube_meta",
    "OAuthBootstrapRequired",
]


def __getattr__(name: str):
    """Lazy import — 第一次存取才把對應模組拉進來。

    為什麼: 重型依賴 (Pillow / pymupdf / google-genai / google-api-python-client
    / mutagen) 各自 ~100ms~1s 啟動成本; FastAPI 起來時若 eager import 會拖慢
    冷啟動,而且只用部分功能的 caller (例如只想跑 TTS) 不必載入全部。
    """
    if name == "render_video":
        from pipeline import main as _render_video
        return _render_video
    if name == "solve_pdf":
        from solve import solve_with_gemini as _solve_pdf
        return _solve_pdf
    if name == "ingest_slides":
        from slide_ingest import ingest as _ingest_slides
        return _ingest_slides
    if name == "problem_to_v0_json":
        from batch import problem_to_v0_json as _p2v0
        return _p2v0
    if name in ("load_tts_backend", "normalize_text", "TTSBackend"):
        from tts_backend import load_tts_backend, normalize_text, TTSBackend
        return {
            "load_tts_backend": load_tts_backend,
            "normalize_text": normalize_text,
            "TTSBackend": TTSBackend,
        }[name]
    if name in ("upload_video", "upload_caption", "get_youtube_credentials"):
        from publish import upload_video, upload_caption, get_credentials
        return {
            "upload_video": upload_video,
            "upload_caption": upload_caption,
            "get_youtube_credentials": get_credentials,
        }[name]
    if name in ("publish_artifact", "auto_youtube_meta", "OAuthBootstrapRequired"):
        # PR-3f: server 用的 YouTube helper, 不靠 sys.exit, 給 progress callback
        from .youtube import publish_artifact, auto_youtube_meta, OAuthBootstrapRequired
        return {
            "publish_artifact": publish_artifact,
            "auto_youtube_meta": auto_youtube_meta,
            "OAuthBootstrapRequired": OAuthBootstrapRequired,
        }[name]
    raise AttributeError(f"module 'core' has no attribute {name!r}")
