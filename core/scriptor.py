"""Scriptor — 把 outline + raw_content 餵 Gemini, 逐 section 產 slides + narration。

設計原則:
- 每個 section 一次 Gemini call (避免 single-shot 大型輸出 token 截斷)
- 每個 slide 的 narration 100~200 字 (對應 30~60 秒語音)
- 每個 section 5~10 張投影片
- code_snippet 從 raw_content.key_files 抓真實內容, 嚴禁 LLM 編造程式碼

scriptor 的輸入是 outline (有 key_files 指標) + raw_content (含實際檔案內容),
所以 LLM 看到的是「這章該講什麼 + 這些檔長什麼樣」, 出來的內容能對應到具體檔案。

deck schema 見 core.deck 模組註解。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .config import get_gemini_api_key, get_gemini_model
from .deck import normalize_deck
from .text_utils import clean_json_escapes, strip_latex


# ---------- Prompt loaders ----------
#
# Prompt 字串 abstracted 到 prompts/*.txt, 經 core.prompts_loader 載入 + cache。
# 為什麼: 555 行 .py 裡 prompt 佔 136 行 (24%), 純文字檔 IDE diff 更直觀 +
# 未來 A/B 測試靠 prompt_version() sha256 hash 追蹤改動。

from core.prompts_loader import load_prompt, prompt_version  # noqa: E402

# 維持向後相容的常數名 — 既有 caller 用 SECTION_PROMPT / LONGFORM_SECTION_PROMPT,
# 不必動 .format() 用法。lazy property 形式: 第一次取用才 load_prompt (lru_cache)。


def _get_section_prompt() -> str:
    return load_prompt("scriptor_repo_section")


def _get_longform_section_prompt() -> str:
    return load_prompt("scriptor_longform_section")


# 向後相容 alias — 既有 caller `SECTION_PROMPT.format(...)` 直接生效
SECTION_PROMPT = _get_section_prompt()
LONGFORM_SECTION_PROMPT = _get_longform_section_prompt()


# iter 92 (L2): 教學風格 preset 載入 — prompts/styles/<name>.txt
# 5 種風格: academic / storyteller (預設) / wuxia / dialogue / comedy
_VALID_STYLES = {"academic", "storyteller", "wuxia", "dialogue", "comedy"}
_STYLE_CACHE: dict[str, str] = {}


def _get_style_directive(style: str | None) -> str:
    """讀 prompts/styles/<style>.txt 內容. 未知 style → fallback storyteller.

    None / 空字串 → storyteller (跟 iter 82 行為一致).
    cache 避免每 section 重讀檔.
    """
    name = (style or "storyteller").strip().lower()
    if name not in _VALID_STYLES:
        name = "storyteller"
    if name in _STYLE_CACHE:
        return _STYLE_CACHE[name]
    style_path = Path(__file__).resolve().parent.parent / "prompts" / "styles" / f"{name}.txt"
    if not style_path.exists():
        # 不該發生 (5 個 file 該 ship 在 repo), 但保險 fallback 空字串
        _STYLE_CACHE[name] = ""
        return ""
    content = style_path.read_text(encoding="utf-8").strip()
    _STYLE_CACHE[name] = content
    return content


# iter 92 (L3 hook): persona 注入 — 暫時空字串 placeholder
# 將來接劉老師個人風格 few-shot (需用戶提供 5-10 段「會這樣講」樣本).
def _get_persona_directive(persona: str | None = None) -> str:
    """L3 persona placeholder. None / "default" → 空字串.

    將來支援讀 prompts/persona/<name>.txt — 收用戶提供的口頭禪 / 範例.
    """
    name = (persona or "").strip().lower()
    if not name or name == "default":
        return ""
    persona_path = Path(__file__).resolve().parent.parent / "prompts" / "persona" / f"{name}.txt"
    if not persona_path.exists():
        return ""
    return persona_path.read_text(encoding="utf-8").strip()


# ---------- Public API ----------

def script(
    outline: dict, raw_content: dict, *,
    length_mode: str | None = None,
    narration_style: str | None = None,
    persona: str | None = None,
) -> dict:
    """Source-agnostic scriptor — 依 source_kind dispatch。

    PR-3b: source_kind in {"repo", "document", "url"}。
    iter 43: 接 length_mode kwarg (lecture / quick), 透傳.
    iter 92 (L2): 接 narration_style — academic / storyteller (預設) /
                  wuxia / dialogue / comedy.
    iter 92 (L3 hook): persona — None / "default" 空字串, 未來接個人化檔.
    """
    kind = raw_content.get("source_kind")
    if kind == "repo":
        return script_repo(
            outline, raw_content,
            length_mode=length_mode, narration_style=narration_style, persona=persona,
        )
    if kind in ("document", "url"):
        return script_long_form(
            outline, raw_content,
            length_mode=length_mode, narration_style=narration_style, persona=persona,
        )
    raise ValueError(f"未支援的 source_kind: {kind!r}")


def script_repo(
    outline: dict, raw_content: dict, *,
    length_mode: str | None = None,
    narration_style: str | None = None,
    persona: str | None = None,
) -> dict:
    """outline + raw_content (repo) → 完整 deck.json。

    每個 section 各自呼叫一次 Gemini, 失敗的 section 會留下佔位 slide
    (避免整份 deck 廢掉, 與 solve.py 的 partial-failure 哲學一致)。
    iter 43: length_mode 控 narration / slides 數量規模.
    """
    if raw_content.get("source_kind") != "repo":
        raise ValueError(f"script_repo 只吃 repo, 收到 {raw_content.get('source_kind')}")

    client, types = _provider_client()
    from .length_mode import preset as _length_preset
    p = _length_preset(length_mode)

    # 把 raw_content 的 key_files index 起來, 給 _format_section_files 用
    file_index = {kf["path"]: kf for kf in raw_content.get("key_files", [])}

    sections_out = []
    total = len(outline.get("sections", []))
    for i, sec_outline in enumerate(outline["sections"]):
        section_id = sec_outline.get("id", f"sec{i+1}")
        print(f"   -> scripting {section_id} ({i+1}/{total}): {sec_outline.get('title')}")

        prompt = SECTION_PROMPT.format(
            deck_title=outline.get("deck_title", ""),
            summary=outline.get("summary", ""),
            section_idx=i + 1,
            total_sections=total,
            section_id=section_id,
            section_title=sec_outline.get("title", ""),
            section_intent=sec_outline.get("intent", ""),
            section_topics=", ".join(sec_outline.get("topics", [])),
            section_files_section=_format_section_files(
                sec_outline.get("key_files", []), file_index,
            ),
            length_directive=p["length_directive"],
            slides_per_section_range=p["slides_per_section_range"],
            narration_chars_range=p["narration_chars_range"],
            narration_seconds_range=p["narration_seconds_range"],
            # iter 92: L2 風格 + L3 persona (預設 storyteller, persona 空)
            style_directive=_get_style_directive(narration_style),
            persona_directive=_get_persona_directive(persona),
        )

        section_dict = _call_with_retry(client, types, prompt, section_id, sec_outline)
        sections_out.append(section_dict)

    # iter 56d: repo 模式如果有 AI 生圖 (option B opt-in), 自動 attach 給對應
    # section 的第一張 slide. repo prompt 沒接 figures 系統 (跟 long_form 不同),
    # 所以這條 post-process 是唯一路徑.
    ai_figure_ids = {
        f["id"] for f in (raw_content.get("figures") or [])
        if isinstance(f, dict) and f.get("id", "").startswith("ai_")
    }
    if ai_figure_ids:
        _attach_ai_diagrams_to_first_slide(sections_out, ai_figure_ids)

    deck = {
        "deck_title": outline.get("deck_title", "未命名"),
        "source_type": "repo",
        "source_meta": {
            "root_name": raw_content.get("root_name"),
            "primary_language": raw_content.get("primary_language"),
            "scanned_files": raw_content.get("stats", {}).get("selected"),
        },
        "sections": sections_out,
    }
    return normalize_deck(deck)


def script_long_form(
    outline: dict, raw_content: dict, *,
    length_mode: str | None = None,
    narration_style: str | None = None,
    persona: str | None = None,
) -> dict:
    """outline + raw_content (document / url) → 完整 deck.json。

    跟 script_repo 結構一致 (逐 section call Gemini + 共用 retry / placeholder),
    差別在 prompt 餵的是 long-form text 而不是 key_files。
    iter 43: length_mode 控 narration 長度跟 slides 數量.
    """
    kind = raw_content.get("source_kind")
    if kind not in ("document", "url"):
        raise ValueError(f"script_long_form 只吃 document / url, 收到 {kind!r}")

    client, types = _provider_client()
    from .length_mode import preset as _length_preset
    p = _length_preset(length_mode)

    document_content = raw_content.get("content", "")
    # iter 52: figures 從 raw_content 拉, format 給 prompt; 沒 figures 給空段落 + 警示
    figures = raw_content.get("figures", []) or []
    figures_section = _format_figures_for_prompt(figures)
    valid_figure_ids = {f["id"] for f in figures}

    sections_out = []
    total = len(outline.get("sections", []))
    for i, sec_outline in enumerate(outline["sections"]):
        section_id = sec_outline.get("id", f"sec{i+1}")
        print(f"   -> scripting {section_id} ({i+1}/{total}): {sec_outline.get('title')}")

        prompt = LONGFORM_SECTION_PROMPT.format(
            deck_title=outline.get("deck_title", ""),
            summary=outline.get("summary", ""),
            section_idx=i + 1,
            total_sections=total,
            section_id=section_id,
            section_title=sec_outline.get("title", ""),
            section_intent=sec_outline.get("intent", ""),
            section_topics=", ".join(sec_outline.get("topics", [])),
            document_content=document_content,
            figures_section=figures_section,
            length_directive=p["length_directive"],
            slides_per_section_range=p["slides_per_section_range"],
            narration_chars_range=p["narration_chars_range"],
            narration_seconds_range=p["narration_seconds_range"],
            # iter 92: L2 風格 + L3 persona (預設 storyteller, persona 空)
            style_directive=_get_style_directive(narration_style),
            persona_directive=_get_persona_directive(persona),
        )

        section_dict = _call_with_retry(client, types, prompt, section_id, sec_outline)
        # iter 52: 驗 slide.image_path — Gemini 亂打的 id 清掉
        _sanitize_slide_image_paths(section_dict, valid_figure_ids)
        sections_out.append(section_dict)

    # iter 56d: AI 圖 (ai_<section_id>) 自動配給對應 section 第一張 slide.
    # scriptor prompt 沒讓 Gemini 認 AI 圖 (page_no=0 不像 PDF 圖那樣可靠),
    # 不靠 LLM 判斷, deterministic 配上去. 已有圖的 section 不動.
    _attach_ai_diagrams_to_first_slide(sections_out, valid_figure_ids)

    # iter 52b: 跨 section image_path 去重 — scriptor 一次只看一個 section,
    # 無法擋同張圖在不同 section 被選兩次. 全部 section 跑完再過一遍.
    _dedupe_image_paths_across_deck(sections_out)

    deck = {
        "deck_title": outline.get("deck_title", "未命名"),
        "source_type": kind,
        "source_meta": {
            "title": raw_content.get("title"),
            "format": raw_content.get("format"),
            "url": raw_content.get("url"),
            "chars": raw_content.get("stats", {}).get("chars"),
        },
        "sections": sections_out,
    }
    return normalize_deck(deck)


# ---------- iter 52: figures helpers ----------


def _format_figures_for_prompt(figures: list[dict]) -> str:
    """把 figures list 排成給 Gemini 看的條列, 用 page_no 排序方便配章節.

    沒 figures 時回提示文字 (讓 Gemini 知道是「沒圖可配」, 不是 prompt bug).
    """
    if not figures:
        return "(本份文件沒抽到 figure, 全部 slide 的 image_path 都填 null)"

    by_page = sorted(figures, key=lambda f: (f.get("page_no", 0), f.get("id", "")))
    lines = []
    for f in by_page:
        cap = (f.get("caption_hint") or "").strip()
        cap_str = f" — {cap}" if cap else ""
        lines.append(
            f"- {f['id']}: page {f.get('page_no', '?')}, "
            f"{f.get('width', 0)}×{f.get('height', 0)}{cap_str}"
        )
    return "\n".join(lines)


def _sanitize_slide_image_paths(section_dict: dict, valid_ids: set[str]) -> None:
    """iter 52: 清掉 Gemini 亂打 / 漏掉的 image_path.

    規則:
    - image_path 不是字串 / 不在 valid_ids → 設 None
    - 沒 image_path key 補上 None (deck schema 一致性)
    - 同一 section 內同一張圖重複使用, 第二次以後設 None
    - 跨 section 重複另由 _dedupe_image_paths_across_deck 處理 (iter 52b)
    """
    slides = section_dict.get("slides") or []
    used_in_section: set[str] = set()
    for slide in slides:
        img = slide.get("image_path")
        if not isinstance(img, str) or img not in valid_ids:
            slide["image_path"] = None
            continue
        if img in used_in_section:
            slide["image_path"] = None
            continue
        used_in_section.add(img)


def _attach_ai_diagrams_to_first_slide(
    sections_out: list[dict], figure_ids: set[str],
) -> None:
    """iter 56d / 57b: section-name 綁定的 figures 自動配給對應 section 第一張 slide.

    為什麼要 post-process: scriptor prompt 寫「看 page X 決定圖屬於哪段」, 但
    AI 圖 / mermaid 圖 page_no=0 沒這資訊, Gemini 不敢挑. 這函式繞過 LLM
    判斷 — 圖名命名上就跟 section 綁定, deterministic 配給該 section 第一張.

    認的 prefix:
    - ai_<section_id>    (iter 56: Gemini Flash Image 生)
    - mermaid_<section_id>  (iter 57b: Gemini text → mermaid → mermaid.ink 渲染)

    若兩種都存在 (兩個 opt-in 都開), 優先用 ai_ (image gen 圖通常更漂亮).
    用戶想反過來可在 UI 手動換圖.

    規則:
    - 此 figure 不在 figure_ids 內 (沒生成) → 跳該 prefix, 試下一個
    - 該 section 已用該圖 → skip (避免重複)
    - 第一張 slide 已有 image_path (其他圖配上去 / 用戶手動) → 不覆寫

    參數:
        sections_out: 已建好的 sections list (deck["sections"])
        figure_ids: 所有有效 figure id 集合 (含 PDF + AI 生圖 + mermaid)
    """
    # iter 57b: 優先順序 — AI 圖 > mermaid 圖
    candidate_prefixes = ("ai_", "mermaid_")
    for sec in sections_out:
        sec_id = sec.get("id")
        if not sec_id:
            continue
        slides = sec.get("slides") or []
        if not slides:
            continue

        # 第一張已有別張圖 → 整個 section 跳 (尊重既有選擇)
        first_slide = slides[0]
        if first_slide.get("image_path"):
            continue

        # section 已用過的圖 (Gemini / 用戶 / 其他 helper 配的)
        used_in_section = {
            sl.get("image_path") for sl in slides if sl.get("image_path")
        }

        # 依優先順序試各 prefix
        for prefix in candidate_prefixes:
            fig_id = f"{prefix}{sec_id}"
            if fig_id not in figure_ids:
                continue
            if fig_id in used_in_section:
                # 該圖已被該 section 其他 slide 用了 → 不重複
                # 但既然 first 是空的, 表示用戶設這張在後面, 那 first 留空合理
                break
            first_slide["image_path"] = fig_id
            break


def _dedupe_image_paths_across_deck(sections_out: list[dict]) -> None:
    """iter 52b: 跨 section 去 image_path 重複 — 同一張圖只能被一個 slide 用一次.

    scriptor 一次 call 只看一 section 的 valid_ids, 無法看到別 section 已用什麼.
    這個 helper 在所有 section build 完後跑, 保留第一次出現, 後面遇到同 id 清掉.

    例: iter 52 用戶實測 deck 出現:
      intro_4.image_path = "fig_p6_1"
      method_results_1.image_path = "fig_p6_1"   ← 同張圖, 應該清掉這個
      method_results_5.image_path = "fig_p18_2"
      implications_future_2.image_path = "fig_p18_2"  ← 同張圖, 應該清掉這個

    執行後 4 個 image_path 變 2 個 (留前者), 配 6 張圖最多 6 slides 帶圖.
    """
    used: set[str] = set()
    for sec in sections_out:
        for slide in sec.get("slides") or []:
            img = slide.get("image_path")
            if not img:
                continue
            if img in used:
                slide["image_path"] = None
            else:
                used.add(img)


# ---------- Internals ----------

def _provider_client():
    """Gemini role 才建立 SDK client；Ollama role 完全不讀 Gemini key。"""
    from core.models import PROVIDER_GEMINI, TEXT_FAST, resolve

    provider_name, _ = resolve(TEXT_FAST)
    if provider_name != PROVIDER_GEMINI:
        return None, None
    from google.genai import types

    from core.gemini_client import make_client

    return make_client(), types

def _call_with_retry(client, types, prompt: str, section_id: str, sec_outline: dict) -> dict:
    """單一 section 的 Gemini call, 兩次 retry, 失敗回佔位 slide。

    第二次 retry 關 thinking_budget=0 把 token 全給 output, 與 outliner 一致。
    """
    raw_text = ""
    last_err = None
    attempts = [
        {"temp": 0.4, "no_thinking": False, "max_tokens": 16384},
        {"temp": 0.6, "no_thinking": True,  "max_tokens": 16384},
    ]
    for attempt_i, params in enumerate(attempts, start=1):
        try:
            from core.models import PROVIDER_GEMINI, TEXT_FAST, resolve

            provider_name, _ = resolve(TEXT_FAST)
            if provider_name == PROVIDER_GEMINI:
                cfg_kwargs = {
                    "temperature": params["temp"],
                    "max_output_tokens": params["max_tokens"],
                }
                if params["no_thinking"]:
                    model_for_check = get_gemini_model()
                    if "2.5" in model_for_check or "thinking" in model_for_check:
                        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
                resp = client.models.generate_content(
                    model=get_gemini_model(),
                    contents=[prompt],
                    config=types.GenerateContentConfig(**cfg_kwargs),
                )
                raw_text = (resp.text or "").strip()
                from core import usage
                usage.record_text_now("video", get_gemini_model(), prompt, raw_text,
                                      label=f"script:{section_id}")
            else:
                from core.providers import generate_text_for_role

                raw_text = generate_text_for_role(
                    TEXT_FAST, prompt, temperature=params["temp"], station="video",
                ).strip()
            cleaned = _strip_fence(raw_text)
            cleaned = clean_json_escapes(cleaned)
            section = json.loads(cleaned)
            _normalize_section(section, section_id, sec_outline)
            if attempt_i > 1:
                print(f"      ↺ section {section_id} retry 成功 "
                      f"(temp={params['temp']}, thinking={'off' if params['no_thinking'] else 'on'})")
            return section
        except Exception as e:
            last_err = e
            print(f"      ⚠ section {section_id} attempt {attempt_i} 失敗 "
                  f"(temp={params['temp']}, thinking={'off' if params['no_thinking'] else 'on'}): {e}")

    # 兩次都失敗: raw 存檔 + 回退佔位
    err_dir = Path("./_scriptor_errors")
    err_dir.mkdir(exist_ok=True)
    (err_dir / f"{section_id}_raw.txt").write_text(
        raw_text or f"(no resp) {last_err}", encoding="utf-8",
    )
    return _placeholder_section(section_id, sec_outline, str(last_err))


def _format_section_files(file_paths: list[str], file_index: dict[str, dict]) -> str:
    """把本章 outline 列出的 key_files 拼成 fenced block 餵 LLM。"""
    blocks = []
    for fp in file_paths:
        kf = file_index.get(fp)
        if kf is None:
            blocks.append(f"### {fp}\n(檔案不在 raw_content, 無內容可提供)")
            continue
        ext = Path(fp).suffix.lstrip(".") or "text"
        truncated_note = " (truncated)" if kf.get("truncated") else ""
        blocks.append(
            f"### {fp}  ({kf['kind']}, {kf['bytes']} bytes{truncated_note})\n"
            f"```{ext}\n{kf['content']}\n```"
        )
    if not blocks:
        return "(本章 outline 未指定 key_files; 請以章節 intent 為主, 不放具體 code_snippet)"
    return "\n\n".join(blocks)


def _strip_fence(text: str) -> str:
    """從 Gemini response 抓 JSON 主體。

    與 outliner._strip_fence 同邏輯 — preamble + fence + 純 JSON 三種型態都 robust。
    放在 scriptor 自己 module 裡 (不從 outliner import) 避免相依方向擾亂。
    """
    text = text.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return text[first:last + 1].strip()
    return text


def _normalize_section(section: dict, section_id: str, sec_outline: dict) -> None:
    """補預設值 + 清掉 LaTeX 殘渣 + 強制 id 對齊 outline。

    slide.id 採 force assign 而非 setdefault, 因為 Gemini 常編自己的 ID
    (例如把 data_schema 章內的 slide 命名 deck_structure_conversion_1),
    讓 ID 跟 outline section_id 失去聯繫。

    所有 strip_latex call 都走 preserve_identifiers=True, 因為 repo 講解
    內容會出現 text_utils / solve_pdf / cfg_strength 等 Python 識別字,
    底線不能被當變數下標吃掉。
    """
    section["id"] = section_id
    section.setdefault("title", sec_outline.get("title", ""))
    section["title"] = strip_latex(section["title"], preserve_identifiers=True)

    slides = section.setdefault("slides", [])
    for j, sl in enumerate(slides):
        # force assign — 不留 LLM 自編 ID 的機會
        sl["id"] = f"{section_id}_{j+1}"
        sl["title"] = strip_latex(sl.get("title", "") or "", preserve_identifiers=True)
        bullets = sl.get("bullets") or []
        sl["bullets"] = [strip_latex(b, preserve_identifiers=True) for b in bullets if b]
        # code_snippet / code_lang / file_path 直接保留, narration 走 strip_latex
        sl.setdefault("code_snippet", None)
        sl.setdefault("code_lang", None)
        sl.setdefault("file_path", None)
        sl["narration"] = strip_latex(
            sl.get("narration", "") or "", preserve_identifiers=True,
        ).strip()
        sl.setdefault("notes", None)


def _placeholder_section(section_id: str, sec_outline: dict, err: str) -> dict:
    """LLM 兩次失敗的補救: 留一張提示 slide 讓人工補。"""
    return {
        "id": section_id,
        "title": sec_outline.get("title", section_id),
        "slides": [{
            "id": f"{section_id}_1",
            "title": "(本章自動生成失敗)",
            "bullets": [
                "Gemini 兩次嘗試皆未產出合法 JSON",
                f"intent: {sec_outline.get('intent', '')}",
                "請在 Web UI 編輯這張投影片",
            ],
            "code_snippet": None,
            "code_lang": None,
            "file_path": None,
            "narration": (
                f"這一章原本要講{sec_outline.get('title', '')}, 不過自動生成失敗了, "
                "請劉老師到編輯介面手動補上內容。"
            ),
            "notes": f"scriptor error: {err[:200]}",
        }],
    }


# ---------- Mock ----------

def mock_deck_from_outline(outline: dict, raw_content: dict) -> dict:
    """離線測試用 — 不打 Gemini, 從 outline 拼結構合法的 deck。

    每個 section 產 1~2 張投影片, narration 用 outline 的 intent + topics 組,
    確保下游 deck_to_exam_schema + pipeline.py 能跑得起來。
    支援 repo / document / url 三種 source_kind。
    """
    kind = raw_content.get("source_kind", "repo")
    file_index = (
        {kf["path"]: kf for kf in raw_content.get("key_files", [])}
        if kind == "repo" else {}
    )

    sections = []
    for i, sec in enumerate(outline.get("sections", [])):
        section_id = sec.get("id", f"sec{i+1}")
        title = sec.get("title", f"第 {i+1} 章")
        intent = sec.get("intent", "")
        topics = sec.get("topics", [])

        slides = [
            {
                "id": f"{section_id}_1",
                "title": title,
                "bullets": (topics[:3] if topics else ["(mock 章節, 無實際內容)"]),
                "code_snippet": None,
                "code_lang": None,
                "file_path": None,
                "narration": (
                    f"同學們, 這一章我們要講的是{title}。{intent}"
                    if intent else
                    f"這是 mock 模式的第 {i+1} 章, 用於 smoke test 不打 Gemini。"
                ),
                "notes": "mock",
            },
        ]

        # 第二張: repo 才會塞 code_snippet, document / url 跳過
        if kind == "repo" and sec.get("key_files"):
            fp = sec["key_files"][0]
            kf = file_index.get(fp)
            if kf and kf.get("content"):
                preview = "\n".join(kf["content"].splitlines()[:6])
                slides.append({
                    "id": f"{section_id}_2",
                    "title": f"關鍵檔案: {Path(fp).name}",
                    "bullets": [f"位置: {fp}", f"類型: {kf['kind']}"],
                    "code_snippet": preview,
                    "code_lang": Path(fp).suffix.lstrip(".") or None,
                    "file_path": fp,
                    "narration": (
                        f"來看一下{fp}這個檔案, 它是這個專案裡比較關鍵的{kf['kind']}檔案, "
                        f"我們可以看到開頭幾行就交代了它的職責。"
                    ),
                    "notes": "mock",
                })

        sections.append({"id": section_id, "title": title, "slides": slides})

    # source_meta 依來源類型不同
    if kind == "repo":
        source_meta = {
            "root_name": raw_content.get("root_name"),
            "primary_language": raw_content.get("primary_language"),
            "scanned_files": raw_content.get("stats", {}).get("selected"),
        }
        title_for_default = raw_content.get("root_name", "project")
    else:
        source_meta = {
            "title": raw_content.get("title"),
            "format": raw_content.get("format"),
            "url": raw_content.get("url"),
            "chars": raw_content.get("stats", {}).get("chars"),
        }
        title_for_default = raw_content.get("title", "untitled")

    deck = {
        "deck_title": outline.get("deck_title", f"{title_for_default} — 講解 (Mock)"),
        "source_type": kind,
        "source_meta": source_meta,
        "sections": sections,
    }
    return normalize_deck(deck)


# ---------- CLI ----------

if __name__ == "__main__":
    import argparse

    from core.runtime import setup_utf8_stdout
    setup_utf8_stdout()

    ap = argparse.ArgumentParser(description="Scriptor 自我測試")
    ap.add_argument("outline", help="outline.json (outliner 產出)")
    ap.add_argument("raw_content", help="raw_content.json (repo adapter 產出)")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    outline_dict = json.loads(Path(args.outline).read_text(encoding="utf-8"))
    raw = json.loads(Path(args.raw_content).read_text(encoding="utf-8"))
    deck = mock_deck_from_outline(outline_dict, raw) if args.mock else script(outline_dict, raw)

    out_path = Path(args.out) if args.out else Path(args.outline).with_name("deck.json")
    out_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    total_slides = sum(len(s["slides"]) for s in deck["sections"])
    print(f"✅ deck 寫到 {out_path} ({len(deck['sections'])} sections / {total_slides} slides)")
