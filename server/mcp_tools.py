"""MCP tools — translateGemma 14 tools 收編（eduStudio 合併 B-2 收尾）。

獨立 FastMCP 進程（`python -m server.mcp_tools` 或 mcp.run()），讓外部 agent / Claude
透過 MCP 協定呼叫合併後的翻譯/學習/配音能力。**非 FastAPI app 一部分**（單一 REST server
仍是 server.main）；此檔是平行的 MCP 介面，共用同一份 core 模組。

移植調整:
- import 改自 core（core.translation.service / core.video.dubber / core.storage.history /
  core.learning.manager / core.langcode），用 lazy getter 避免 import 期 side-effect。
- 對外語言碼 canonical 連字號（zh-TW）；呼叫服務前用 core.langcode.to_underscore 轉底線
  （與 REST localization router 同邊界規則）。預設 target 'zh-TW'。
- 後端走 Gemini（core 模組已退 Ollama）。

注意:本檔**不可**加 `from __future__ import annotations` —— FastMCP 的 @mcp.tool() 會內省
參數型別註解（issubclass 檢查），PEP 563 把註解變字串會讓它 TypeError。
"""
import os
from typing import List

from mcp.server.fastmcp import FastMCP

from core.langcode import LANGUAGES, to_underscore
from core.learning.manager import get_learning_manager
from core.storage.history import get_history_manager
from core.translation.service import translator
from core.video.dubber import get_video_dubber

mcp = FastMCP("eduStudio-Localization")


def _u(code: str | None) -> str:
    """canonical 連字號 → 服務內部底線式（唯一邊界轉換）。"""
    return to_underscore(code) or "auto"


def _drain(gen) -> str:
    """收 generator 的最終完整結果（服務 stream 方法在此情境取最後一個）。"""
    out = ""
    for chunk in gen:
        out = chunk
    return out


@mcp.tool()
def list_languages() -> list[dict]:
    """List supported languages (canonical BCP-47 hyphen codes)."""
    rows = [{"code": code, "name_zh": zh, "name_en": en} for code, (zh, en) in LANGUAGES.items()]
    rows.sort(key=lambda x: x["name_zh"])
    return rows


@mcp.tool()
def translate_text(text: str, source_lang: str = "auto", target_lang: str = "zh-TW") -> str:
    """Translate text (cloud Gemini backend)."""
    result = translator.translate(text, _u(source_lang), _u(target_lang))
    get_history_manager().add_history(
        type="text", source_lang=source_lang, target_lang=target_lang,
        original_content=text, translated_content=result, details={"via": "mcp"},
    )
    return result


@mcp.tool()
def translate_batch_text(texts: List[str], source_lang: str = "auto", target_lang: str = "zh-TW") -> List[str]:
    """Translate a batch of text items."""
    su, tu = _u(source_lang), _u(target_lang)
    outputs = [translator.translate(t, su, tu) for t in texts]
    get_history_manager().add_history(
        type="text_batch", source_lang=source_lang, target_lang=target_lang,
        original_content=f"[mcp-batch:{len(texts)}]", translated_content="\n".join(outputs[:3]),
        details={"via": "mcp", "count": len(texts)},
    )
    return outputs


@mcp.tool()
def translate_image(image_path: str, source_lang: str = "auto", target_lang: str = "zh-TW") -> str:
    """Translate text from an image file using OCR."""
    if not os.path.exists(image_path):
        return f"Error: File {image_path} not found."
    full_result = _drain(translator.translate_image(image_path, _u(target_lang), _u(source_lang)))
    get_history_manager().add_history(
        type="image", source_lang=source_lang, target_lang=target_lang,
        original_content=image_path, translated_content=full_result, details={"via": "mcp"},
    )
    return full_result


@mcp.tool()
def translate_pdf(pdf_path: str, source_lang: str = "en-US", target_lang: str = "zh-TW") -> str:
    """Translate text extracted from PDF pages."""
    if not os.path.exists(pdf_path):
        return f"Error: File {pdf_path} not found."
    final_result = _drain(translator.translate_pdf(pdf_path, _u(target_lang), _u(source_lang)))
    get_history_manager().add_history(
        type="pdf", source_lang=source_lang, target_lang=target_lang,
        original_content=pdf_path, translated_content=final_result, details={"via": "mcp"},
    )
    return final_result


@mcp.tool()
def dub_video(video_source: str, source_lang: str = "auto", target_lang: str = "zh-TW", burn_subtitles: bool = True) -> str:
    """Dub a video and return output path."""
    results = get_video_dubber().process_video(
        video_source, _u(source_lang), _u(target_lang), burn_subtitles=burn_subtitles)
    dubbed_path = results.get("dubbed_video", "")
    get_history_manager().add_history(
        type="video", source_lang=source_lang, target_lang=target_lang,
        original_content=video_source, translated_content=dubbed_path,
        details={"via": "mcp", "original_srt": results.get("original_srt"),
                 "translated_srt": results.get("translated_srt")},
    )
    return dubbed_path or "Error: Failed to generate dubbed video."


@mcp.tool()
def translate_with_learning(text: str, source_lang: str = "auto", target_lang: str = "zh-TW") -> str:
    """Translate text with learning annotations (vocabulary, grammar, examples)."""
    return _drain(translator.translate_learning(text, _u(source_lang), _u(target_lang)))


@mcp.tool()
def correct_writing(text: str, writing_lang: str = "en-US", native_lang: str = "zh-TW") -> str:
    """Correct and score a piece of writing with detailed feedback."""
    return _drain(translator.writing_correction(text, _u(writing_lang), _u(native_lang)))


@mcp.tool()
def conversation_practice(scenario: str, user_message: str,
                          practice_lang: str = "en-US", native_lang: str = "zh-TW",
                          history: str = "") -> str:
    """AI conversation partner for language practice in a given scenario."""
    return _drain(translator.conversation_practice(
        scenario, user_message, _u(practice_lang), _u(native_lang), history))


@mcp.tool()
def generate_flashcards(text: str, source_lang: str = "auto",
                        target_lang: str = "zh-TW", count: int = 5) -> str:
    """Generate vocabulary flashcards from input text."""
    return _drain(translator.generate_flashcards(text, _u(source_lang), _u(target_lang), count))


@mcp.tool()
def add_vocabulary(word: str, meaning: str, source_lang: str = "en-US",
                   target_lang: str = "zh-TW", part_of_speech: str = "",
                   example_sentence: str = "") -> dict:
    """Add a vocabulary word to the learning bank."""
    row_id = get_learning_manager().add_vocabulary(
        word=word, meaning=meaning, source_lang=_u(source_lang), target_lang=_u(target_lang),
        part_of_speech=part_of_speech, example_sentence=example_sentence)
    return {"id": row_id, "word": word}


@mcp.tool()
def get_due_vocabulary(source_lang: str = "", target_lang: str = "", limit: int = 20) -> list:
    """Get vocabulary cards due for spaced repetition review."""
    return get_learning_manager().get_due_cards(
        source_lang=_u(source_lang) if source_lang else None,
        target_lang=_u(target_lang) if target_lang else None, limit=limit)


@mcp.tool()
def review_vocabulary(card_id: int, quality: int) -> dict:
    """Submit a spaced repetition review (quality 0-5) for a vocabulary card."""
    return get_learning_manager().review_card(card_id, quality)


@mcp.tool()
def get_learning_stats() -> dict:
    """Get learning progress statistics."""
    return get_learning_manager().get_stats()


if __name__ == "__main__":
    mcp.run()
