"""routes/localization.py — translateGemma 收編後的在地化端點（eduStudio 合併 Phase B-2/B-3）。

對外一律 **canonical 連字號語言碼（zh-TW）**；此 router 是**唯一邊界**，呼叫翻譯服務前用
core.langcode.to_underscore() 轉成服務內部吃的底線式（zh_TW）。翻譯後端 = 雲端 Gemini
（core.translation.service，已退 Ollama）。

text-based 端點（translate + 學習工具）不需重依賴；檔案端點（image/pdf/dub/meeting）走
multipart 上傳 + 已搬入的模組（OCR/whisper/edge-tts，lazy）。長任務（dub/meeting）為同步
端點，呼叫端需容忍較久處理時間（之後可改 autoSolver job runner 背景化）。
"""
from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

from core.langcode import LANGUAGES, to_underscore
from core.meeting.summarizer import meeting_summarizer
from core.translation.service import translator
from core.video.dubber import get_video_dubber

router = APIRouter(prefix="/localization", tags=["localization"])


def _u(code: str | None) -> str:
    """canonical 連字號 → 服務內部底線式（唯一邊界轉換）。'auto'/None 安全。"""
    return to_underscore(code) or "auto"


def _save_upload(upload: UploadFile, suffix: str = "") -> str:
    """把上傳檔存到暫存路徑，回路徑（呼叫端負責清理）。"""
    suffix = suffix or os.path.splitext(upload.filename or "")[1] or ""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(upload.file.read())
    return path


# ---------- 請求模型 ----------
class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "zh-TW"          # canonical 連字號
    source_lang: str = "auto"
    glossary: str = ""
    style: str = ""


class LearningTranslateRequest(BaseModel):
    text: str
    target_lang: str = "zh-TW"
    source_lang: str = "auto"


class FlashcardRequest(BaseModel):
    text: str
    target_lang: str = "zh-TW"
    source_lang: str = "auto"
    count: int = Field(default=5, ge=1, le=20)


class WritingCorrectionRequest(BaseModel):
    text: str
    lang: str = "en-US"
    native_lang: str = "zh-TW"


class ConversationRequest(BaseModel):
    scenario: str
    user_message: str
    practice_lang: str = "en-US"
    native_lang: str = "zh-TW"
    history: str = ""


class DictationCheckRequest(BaseModel):
    original: str
    user_input: str
    target_lang: str = "zh-TW"


def _first(gen) -> str:
    """收 generator 的單一完整結果（服務的 stream 方法在 API 情境 yield 一次）。"""
    out = ""
    for chunk in gen:
        out = chunk
    return out


# ---------- 端點 ----------
@router.get("/languages")
async def list_languages() -> dict:
    """列支援語言（canonical 連字號碼 + 中英名）。"""
    return {
        "languages": [
            {"code": code, "zh": zh, "en": en}
            for code, (zh, en) in sorted(LANGUAGES.items())
        ]
    }


@router.post("/translate")
async def translate_text(req: TranslateRequest) -> dict:
    """文字翻譯。對外 zh-TW，邊界轉 zh_TW 後送 Gemini 服務。"""
    translated = translator.translate(
        req.text, _u(req.source_lang), _u(req.target_lang),
        glossary=req.glossary, style=req.style,
    )
    return {
        "translated_text": translated,
        "source_lang": req.source_lang,
        "target_lang": req.target_lang,
    }


@router.post("/learning/translate")
async def learning_translate(req: LearningTranslateRequest) -> dict:
    result = _first(translator.translate_learning(
        req.text, _u(req.source_lang), _u(req.target_lang)))
    return {"result": result, "target_lang": req.target_lang}


@router.post("/learning/flashcards")
async def learning_flashcards(req: FlashcardRequest) -> dict:
    result = _first(translator.generate_flashcards(
        req.text, _u(req.source_lang), _u(req.target_lang), count=req.count))
    return {"result": result}


@router.post("/learning/writing-correction")
async def writing_correction(req: WritingCorrectionRequest) -> dict:
    result = _first(translator.writing_correction(
        req.text, _u(req.lang), _u(req.native_lang)))
    return {"result": result}


@router.post("/learning/conversation")
async def conversation(req: ConversationRequest) -> dict:
    result = _first(translator.conversation_practice(
        req.scenario, req.user_message,
        _u(req.practice_lang), _u(req.native_lang), history=req.history))
    return {"result": result}


@router.post("/learning/dictation-check")
async def dictation_check(req: DictationCheckRequest) -> dict:
    result = translator.dictation_check(
        req.original, req.user_input, _u(req.target_lang))
    return {"result": result}


# ---------- 檔案端點（multipart 上傳 + 已搬入模組）----------
@router.post("/translate/image")
async def translate_image(
    file: UploadFile = File(...),
    target_lang: str = Form("zh-TW"),
    source_lang: str = Form("auto"),
) -> dict:
    """圖片 OCR + 翻譯（pytesseract，lazy）。回最終翻譯文字。"""
    path = _save_upload(file)
    try:
        result = _first(translator.translate_image(path, _u(target_lang), _u(source_lang)))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return {"result": result, "target_lang": target_lang}


@router.post("/translate/pdf")
async def translate_pdf(
    file: UploadFile = File(...),
    target_lang: str = Form("zh-TW"),
    source_lang: str = Form("en-US"),
) -> dict:
    """PDF 逐頁翻譯（PyMuPDF，lazy）。回最終彙整文字。"""
    path = _save_upload(file, suffix=".pdf")
    try:
        result = _first(translator.translate_pdf(path, _u(target_lang), _u(source_lang)))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return {"result": result, "target_lang": target_lang}


@router.post("/meeting/summarize")
async def meeting_summarize(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    summary_types: str = Form("full_summary"),
) -> dict:
    """會議影片摘要（ffmpeg+whisper+Gemini）。長任務，同步處理。

    summary_types 以逗號分隔（如 'key_points,decisions'）。
    """
    path = _save_upload(file)
    types = [t.strip() for t in summary_types.split(",") if t.strip()]
    try:
        res = meeting_summarizer.process_video(path, _u(language), types or None)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return {
        "transcript": res.transcript,
        "transcript_with_time": res.transcript_with_time,
        "summary": res.summary,
        "duration": res.duration,
        "language": res.language,
    }


@router.post("/dub")
async def dub_video(
    target_lang: str = Form("zh-TW"),
    source_lang: str = Form("auto"),
    burn_subtitles: bool = Form(False),
    url: str = Form(""),
    file: UploadFile | None = File(None),
) -> dict:
    """影片配音（下載/上傳 → STT → 翻譯 → TTS → 合成）。長任務，同步處理。

    來源二選一：url（YouTube）或上傳 file。回各產出物路徑。
    """
    path = ""
    if not url:
        if file is None:
            return {"error": "需提供 url 或上傳 file"}
        path = _save_upload(file, suffix=".mp4")
    source = url or path
    try:
        results = get_video_dubber().process_video(
            source, _u(source_lang), _u(target_lang), burn_subtitles=burn_subtitles)
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
    return {"results": results, "target_lang": target_lang}
