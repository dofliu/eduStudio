"""routes/localization.py — translateGemma 收編後的在地化端點（eduStudio 合併 Phase B-2/B-3）。

對外一律 **canonical 連字號語言碼（zh-TW）**；此 router 是**唯一邊界**，呼叫翻譯服務前用
core.langcode.to_underscore() 轉成服務內部吃的底線式（zh_TW）。翻譯後端 = 雲端 Gemini
（core.translation.service，已退 Ollama）。

本批先上 text-based 端點（translate + 學習工具），都不需重依賴、可單元測試。
image/pdf/dub/stt/tts 等需檔案上傳 + OCR/whisper/edge-tts 的端點待 video_dubber/meeting
模組搬入後再加（MERGE_PLAN §5.5 B-2 續）。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.langcode import LANGUAGES, to_underscore
from core.translation.service import translator

router = APIRouter(prefix="/localization", tags=["localization"])


def _u(code: str | None) -> str:
    """canonical 連字號 → 服務內部底線式（唯一邊界轉換）。'auto'/None 安全。"""
    return to_underscore(code) or "auto"


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
