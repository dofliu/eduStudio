"""翻譯 + 多模態服務（從 translateGemma translator.py 收編，eduStudio 合併 Phase B-2）。

移植原則（MERGE_PLAN §5.5）:
- **後端 ollama → 雲端 Gemini**：原 `ollama.chat` 全改走 `_gemini_complete()`（沿用
  core.config 的 GEMINI_API_KEY / GEMINI_MODEL 與既有 genai.Client 模式）。原本的
  streaming 在 API 情境改為「一次回完整結果」（generator 介面保留、yield 一次），真 SSE
  串流留待之後 router 層再做。
- **內部語言碼維持底線式**（zh_TW）：translator 內部邏輯（detect / prompt / ocr_lang_map /
  whisper_lang_map / voice_map）都圍繞底線碼，自洽；故**不改其內部慣例**，語言中繼資料改從
  core.langcode._LANG_SOURCE 取（單一真相）。連字號↔底線轉換由「呼叫此服務的 router 邊界」
  負責（core.langcode.to_underscore），不在此擴散。
- **重依賴 lazy import**：fitz/pytesseract/PIL/faster_whisper/edge_tts 維持函式內 import，
  讓未裝套件時 pytest collect 不崩（測試用 importorskip）。
- logger 改用 stdlib logging（原 `from logger import get_logger` 是 translateGemma 專屬）。
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from typing import Generator

# 語言中繼資料單一真相：langcode._LANG_SOURCE 是底線 key 的 (中文, 英文, BCP-47) 3-tuple,
# 與 translator 內部底線慣例完全相符（原 translateGemma languages.LANGUAGES 同形）。
from core.langcode import _LANG_SOURCE as LANGUAGES

log = logging.getLogger(__name__)


def _get_language_info(code: str) -> tuple[str, str, str]:
    """回 (中文名, 英文名, BCP-47 locale)；查不到回 Unknown（保留 translateGemma 原語意）。"""
    return LANGUAGES.get(code, ("Unknown", "Unknown", code))


def _gemini_complete(prompt: str) -> str:
    """單次 Gemini completion（取代原 ollama.chat）。沿用 core.config 金鑰/模型。

    為什麼溫度 0.2：翻譯/批改/學習這類任務要穩定、低發散。金鑰缺則丟 RuntimeError，
    由各方法的 try/except 轉成使用者可讀的失敗字串（保留 translateGemma 原行為）。
    """
    from core.config import GEMINI_MODEL, get_gemini_api_key

    key = get_gemini_api_key()
    if not key:
        raise RuntimeError("缺少 GEMINI_API_KEY 環境變數")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.2),
    )
    return (resp.text or "").strip()


class TranslateGemmaService:
    """翻譯與多模態輔助服務（後端 = 雲端 Gemini）。"""

    def __init__(self, model_name: str = "gemini"):
        # model_name 保留作相容參數；實際模型由 core.config.GEMINI_MODEL 決定。
        self.model_name = model_name

    # ---------- 語言偵測 ----------
    def detect_source_language(self, text: str) -> str:
        """auto 來源時的 best-effort 語言偵測（回底線式碼）。"""
        if not text or not text.strip():
            return "en_US"

        if re.search(r"[぀-ヿ]", text):
            return "ja_JP"
        if re.search(r"[가-힯]", text):
            return "ko_KR"
        if re.search(r"[؀-ۿ]", text):
            return "ar_SA"
        if re.search(r"[฀-๿]", text):
            return "th_TH"
        if re.search(r"[Ѐ-ӿ]", text):
            return "ru_RU"

        if re.search(r"[一-鿿]", text):
            simplified_markers = set("们这为发后里来时会点过对于国个说台学车气电长开见进实动业现应间体")
            if any(ch in simplified_markers for ch in text):
                return "zh_CN"
            return "zh_TW"

        if re.search(r"[À-ɏḀ-ỿ]", text):
            return "vi_VN"

        return "en_US"

    def _resolve_source_code(self, text: str, source_code: str) -> str:
        if source_code != "auto":
            return source_code if source_code in LANGUAGES else "en_US"
        detected = self.detect_source_language(text)
        return detected if detected in LANGUAGES else "en_US"

    def _format_custom_rules(self, glossary: str = "", style: str = "") -> str:
        rules = []
        if glossary and glossary.strip():
            rules.append(
                "Terminology rules (strict):\n"
                f"{glossary.strip()}\n"
                "Prefer mapped terms when source terms are present."
            )
        if style and style.strip():
            rules.append(
                "Style guide:\n"
                f"{style.strip()}\n"
                "Follow this style while preserving semantic accuracy."
            )
        return "\n\n".join(rules)

    # ---------- 學習模式 ----------
    def _build_learning_prompt(self, text: str, source_code: str, target_code: str) -> str:
        _, src_en, _ = _get_language_info(source_code)
        _, tgt_en, _ = _get_language_info(target_code)

        return f"""You are a language learning assistant helping a {tgt_en} speaker learn {src_en}.

Given the following {src_en} text, provide a structured learning breakdown in {tgt_en}.

IMPORTANT: Output MUST follow this exact format with these section headers:

## 翻譯
(Provide an accurate {tgt_en} translation of the text)

## 重點詞彙
(List 3-6 key vocabulary words/phrases from the text. For each word, provide:)
- **word** (part of speech) {tgt_en} meaning — example sentence

## 文法解析
(Explain 1-3 grammar points found in the text, in {tgt_en})

## 相似表達
(Provide 2-3 alternative ways to express the same meaning in {src_en}, with {tgt_en} translations)

Text to analyze:

{text}"""

    def translate_learning(self, text: str, source_code: str, target_code: str) -> Generator[str, None, None]:
        """翻譯 + 學習註解（詞彙/文法/例句）。generator 介面保留，yield 完整結果一次。"""
        if not text.strip():
            yield ""
            return
        resolved_source = self._resolve_source_code(text, source_code)
        prompt = self._build_learning_prompt(text, resolved_source, target_code)
        try:
            yield _gemini_complete(prompt)
        except Exception as exc:
            yield f"學習模式翻譯失敗：{exc}"

    def generate_flashcards(self, text: str, source_code: str, target_code: str, count: int = 5) -> Generator[str, None, None]:
        """從輸入文字產生單字卡。"""
        if not text.strip():
            yield ""
            return
        resolved_source = self._resolve_source_code(text, source_code)
        _, src_en, _ = _get_language_info(resolved_source)
        _, tgt_en, _ = _get_language_info(target_code)

        prompt = f"""You are a language learning flashcard generator.

From the following {src_en} text, extract {count} important vocabulary words or phrases and create flashcards.

Output format (one card per block, use --- as separator):

**1. word/phrase**
- 詞性: (part of speech)
- 釋義: ({tgt_en} meaning)
- 例句: (example sentence in {src_en})
- 例句翻譯: ({tgt_en} translation of example)

---

**2. word/phrase**
...

Text:

{text}"""
        try:
            yield _gemini_complete(prompt)
        except Exception as exc:
            yield f"閃卡生成失敗：{exc}"

    def dictation_check(self, original: str, user_input: str, target_code: str) -> str:
        """比對聽寫輸入與原文，給回饋。"""
        if not original.strip() or not user_input.strip():
            return "請提供原文與您的聽寫內容。"
        _, tgt_en, _ = _get_language_info(target_code)

        prompt = f"""You are a language learning assistant. A student listened to audio and wrote down what they heard.

Compare the original text with the student's attempt and provide feedback in {tgt_en}.

Original text:
{original}

Student's attempt:
{user_input}

Provide feedback in this format:
## 正確率
(Calculate approximate accuracy percentage)

## 錯誤分析
(List specific differences: missing words, misspellings, wrong words)

## 正確答案
{original}

## 學習建議
(Brief tips for improvement based on the errors found)"""
        try:
            return _gemini_complete(prompt)
        except Exception as exc:
            return f"聽寫檢查失敗：{exc}"

    def conversation_practice(self, scenario: str, user_message: str,
                              practice_lang_code: str, native_lang_code: str,
                              history: str = "") -> Generator[str, None, None]:
        """AI 對話練習夥伴。"""
        _, practice_en, _ = _get_language_info(practice_lang_code)
        _, native_en, _ = _get_language_info(native_lang_code)

        history_block = ""
        if history.strip():
            history_block = f"\nConversation so far:\n{history}\n"

        prompt = f"""You are a friendly {practice_en} conversation partner helping a {native_en} speaker practice {practice_en}.

Scenario: {scenario}
{history_block}
The student says: {user_message}

Respond following these rules:
1. Reply IN {practice_en} as a natural conversation partner in the given scenario.
2. Keep your reply concise (1-3 sentences).
3. After your reply, add a section "---" followed by:
   - **翻譯**: {native_en} translation of your reply
   - **糾正**: If the student's message has grammar/vocabulary errors, explain them in {native_en}. If correct, write "表達正確！"
   - **建議**: One tip to improve their {practice_en}, in {native_en}"""
        try:
            yield _gemini_complete(prompt)
        except Exception as exc:
            yield f"對話練習失敗：{exc}"

    def writing_correction(self, text: str, lang_code: str,
                           native_lang_code: str) -> Generator[str, None, None]:
        """寫作批改與評分。"""
        _, lang_en, _ = _get_language_info(lang_code)
        _, native_en, _ = _get_language_info(native_lang_code)

        prompt = f"""You are a professional {lang_en} writing tutor helping a {native_en} speaker.

Analyze and correct the following {lang_en} text. Provide feedback in {native_en}.

Student's writing:
{text}

Respond in this exact format:

## 修正後的文章
(Rewrite the corrected version in {lang_en})

## 錯誤分析
(List each error found, with:)
- ❌ Original → ✅ Corrected — Explanation in {native_en}

## 寫作評分
- 文法 Grammar: X/10
- 詞彙 Vocabulary: X/10
- 流暢度 Fluency: X/10
- 整體 Overall: X/10

## 改善建議
(2-3 specific tips to improve their {lang_en} writing, in {native_en})"""
        try:
            yield _gemini_complete(prompt)
        except Exception as exc:
            yield f"寫作批改失敗：{exc}"

    # ---------- 純翻譯 ----------
    def _build_prompt(self, text: str, source_code: str, target_code: str, glossary: str = "", style: str = "") -> str:
        _, src_en, src_locale = _get_language_info(source_code)
        _, tgt_en, tgt_locale = _get_language_info(target_code)
        custom_rules = self._format_custom_rules(glossary, style)

        if target_code == "zh_TW":
            prompt = f"""You are a professional {src_en} ({src_locale}) to Traditional Chinese (Taiwan) translator.

IMPORTANT RULES:
1. You MUST output ONLY Traditional Chinese characters as used in Taiwan.
2. DO NOT use any Simplified Chinese characters.
3. Examples of correct Traditional vs incorrect Simplified:
   - 台灣 (correct) vs 台湾 (wrong)
   - 翻譯 (correct) vs 翻译 (wrong)
   - 資料 (correct) vs 数据 (wrong)
   - 設定 (correct) vs 设置 (wrong)
   - 網路 (correct) vs 网络 (wrong)
   - 應用程式 (correct) vs 应用程序 (wrong)
   - 專案 (correct) vs 项目 (wrong)

Please provide ONLY the Traditional Chinese translation without any additional explanations.

{custom_rules}

Translate the following text:

{text}"""
        else:
            prompt = f"""You are a professional {src_en} ({src_locale}) to {tgt_en} ({tgt_locale}) translator.
Your goal is to accurately convey the meaning and nuances of the original {src_en} text while adhering to {tgt_en} grammar, style, and conventions.

Please provide ONLY the {tgt_en} translation without any additional explanations or commentary.

{custom_rules}

Translate the following text:

{text}"""
        return prompt

    def translate(self, text: str, source_code: str, target_code: str, glossary: str = "", style: str = "") -> str:
        if not text.strip():
            return ""
        resolved_source = self._resolve_source_code(text, source_code)
        prompt = self._build_prompt(text, resolved_source, target_code, glossary, style)
        try:
            return _gemini_complete(prompt)
        except Exception as exc:
            return f"翻譯失敗：{exc}"

    def translate_stream(self, text: str, source_code: str, target_code: str, glossary: str = "", style: str = "") -> Generator[str, None, None]:
        if not text.strip():
            yield ""
            return
        resolved_source = self._resolve_source_code(text, source_code)
        prompt = self._build_prompt(text, resolved_source, target_code, glossary, style)
        try:
            yield _gemini_complete(prompt)
        except Exception as exc:
            yield f"翻譯失敗：{exc}"

    # ---------- PDF 翻譯（PyMuPDF，lazy）----------
    def translate_pdf(self, pdf_path: str, target_code: str, source_code: str = "en_US") -> Generator[str, None, None]:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            yield "未安裝 PyMuPDF，請先執行：pip install PyMuPDF"
            return

        yield "正在讀取 PDF...\n"
        try:
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            if total_pages == 0:
                yield "錯誤：PDF 沒有頁面。"
                return

            yield f"PDF 共 {total_pages} 頁，開始翻譯...\n\n"
            all_results: list[str] = []
            for page_num in range(total_pages):
                page = doc[page_num]
                page_text = page.get_text().strip()
                if not page_text:
                    all_results.append(f"第 {page_num + 1} 頁：無可擷取文字\n")
                    yield self._format_pdf_results(all_results, page_num + 1, total_pages)
                    continue

                all_results.append(f"第 {page_num + 1} 頁：\n")
                yield self._format_pdf_results(all_results, page_num + 1, total_pages, translating=True)

                page_translation = ""
                for result in self.translate_stream(page_text, source_code, target_code):
                    page_translation = result
                    current_results = all_results.copy()
                    current_results[-1] = f"第 {page_num + 1} 頁：\n{result}\n"
                    yield self._format_pdf_results(current_results, page_num + 1, total_pages, translating=True)

                all_results[-1] = f"第 {page_num + 1} 頁：\n{page_translation}\n"
                yield self._format_pdf_results(all_results, page_num + 1, total_pages)

            doc.close()
            yield self._format_pdf_results(all_results, total_pages, total_pages, done=True)
        except FileNotFoundError:
            yield f"找不到 PDF 檔案：{pdf_path}"
        except Exception as exc:
            yield f"PDF 翻譯失敗：{exc}"

    def _format_pdf_results(self, results: list, current_page: int, total_pages: int, translating: bool = False, done: bool = False) -> str:
        if done:
            header = f"翻譯完成（共 {total_pages} 頁）\n{'=' * 40}\n\n"
        elif translating:
            header = f"正在翻譯第 {current_page}/{total_pages} 頁...\n{'=' * 40}\n\n"
        else:
            header = f"已完成第 {current_page}/{total_pages} 頁\n{'=' * 40}\n\n"
        return header + "\n".join(results)

    # ---------- 圖片 OCR 翻譯（pytesseract，lazy）----------
    def translate_image(self, image_path: str, target_code: str, source_code: str = "auto") -> Generator[str, None, None]:
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            yield "未安裝 OCR 套件，請先執行：pip install pytesseract Pillow"
            return

        yield "正在進行 OCR 文字辨識...\n"
        try:
            image = Image.open(image_path)
            ocr_lang_map = {
                "zh_TW": "chi_tra", "zh_CN": "chi_sim", "ja_JP": "jpn",
                "ko_KR": "kor", "en_US": "eng", "de_DE": "deu", "fr_FR": "fra",
                "es_ES": "spa", "it_IT": "ita", "ru_RU": "rus", "vi_VN": "vie",
                "th_TH": "tha", "ar_SA": "ara",
            }
            if source_code == "auto":
                ocr_lang = "chi_tra+chi_sim+eng+jpn+kor"
            else:
                ocr_lang = ocr_lang_map.get(source_code, "eng")

            try:
                extracted_text = pytesseract.image_to_string(image, lang=ocr_lang)
            except Exception:
                extracted_text = pytesseract.image_to_string(image, lang="eng")

            extracted_text = extracted_text.strip()
            if not extracted_text:
                yield "辨識不到文字。\n\n建議：\n- 使用更清晰圖片\n- 提高對比與解析度\n- 嘗試不同來源語言設定"
                return

            yield f"OCR 結果：\n{extracted_text}\n\n正在翻譯...\n"
            resolved_source = self._resolve_source_code(extracted_text, source_code)
            for result in self.translate_stream(extracted_text, resolved_source, target_code):
                yield f"OCR 結果：\n{extracted_text}\n\n翻譯結果：\n{result}"
        except FileNotFoundError:
            yield f"找不到圖片檔案：{image_path}"
        except Exception as exc:
            yield f"圖片翻譯失敗：{exc}"

    # ---------- STT（faster-whisper，lazy）----------
    def speech_to_text(self, audio_path: str, language: str = "auto") -> tuple[str, str]:
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            return "未安裝 faster-whisper，請先執行：pip install faster-whisper", ""
        try:
            model = WhisperModel("base", device="cpu", compute_type="int8")
            whisper_lang_map = {
                "zh_TW": "zh", "zh_CN": "zh", "en_US": "en", "ja_JP": "ja",
                "ko_KR": "ko", "de_DE": "de", "fr_FR": "fr", "es_ES": "es",
                "it_IT": "it", "ru_RU": "ru", "pt_BR": "pt", "vi_VN": "vi",
                "th_TH": "th", "ar_SA": "ar",
            }
            lang_code = None if language == "auto" else whisper_lang_map.get(language)
            segments, info = model.transcribe(audio_path, language=lang_code)
            text = "".join([segment.text for segment in segments]).strip()
            return text, info.language
        except Exception as exc:
            return f"語音辨識失敗：{exc}", ""

    # ---------- TTS（edge-tts，lazy）----------
    async def text_to_speech(self, text: str, language_code: str) -> str:
        try:
            import edge_tts
        except ImportError:
            return ""
        # voice 查找改用 core.langcode（單一真相，容忍底線/連字號）。
        from core.langcode import get_edge_tts_voice
        voice = get_edge_tts_voice(language_code)
        try:
            output_path = os.path.join(tempfile.gettempdir(), f"tts_output_{id(text)}.mp3")
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            return output_path
        except Exception as exc:
            log.warning("TTS failed: %s", exc)
            return ""


# 模組級單例（沿 translateGemma 慣例）。
translator = TranslateGemmaService()
