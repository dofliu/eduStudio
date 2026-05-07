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

from .config import GEMINI_MODEL, get_gemini_api_key
from .deck import normalize_deck
from .text_utils import clean_json_escapes, strip_latex


# ---------- Prompt ----------

SECTION_PROMPT = """你是一位資深的軟體工程講師, 擅長把程式專案拆解成清楚的講解影片。
請針對指定章節, 產出 5~10 張投影片的講解內容 (display + narration)。

==== 整體脈絡 ====
專案: {deck_title}
講解主軸: {summary}
這是第 {section_idx}/{total_sections} 章

==== 本章資訊 ====
標題: {section_title}
意圖: {section_intent}
重點關鍵詞: {section_topics}

==== 本章可引用的檔案 (建議用真實程式碼片段而非編造) ====
{section_files_section}

==== 投影片設計原則 ====
1. **5~10 張投影片** (依本章複雜度), 第一張通常是章節標題 + 概觀
2. **每張投影片 narration 100~200 字** (中文字數), 對應 30~60 秒語音
3. **narration 用「劉老師」第一人稱口吻**, 自然口語, 像在課堂面對學生
4. **bullets 每點 ≤ 25 字**, 一張投影片不超過 4 個 bullet
5. **code_snippet 從上面提供的檔案內容取**, 一次最多 8~12 行, 太長要 elide。
   嚴禁編造檔案沒有的程式碼; 若不放程式碼, code_snippet 設 null。
6. **file_path 標註程式碼來自哪個檔**, 沒程式碼就 null
7. **slide title 簡潔 (4~14 字)**, 別跟 narration 重複

==== 嚴禁事項 (★ 重要) ====
- 不要 LaTeX、不要 Markdown 標題符號、不要 emoji、不要 \\theta 之類反斜線命令
- code_snippet 內容必須是上面 ==== 本章可引用的檔案 ==== 區段裡看得到的真實程式碼,
  不可發明從未出現過的函式、檔名、API
- narration 不要重複 bullets 文字, 要解釋「為什麼」而不是「念出 bullet 標題」
- bullets / narration 不要使用金錢符號 (dollar sign) 包裹的數學模式

==== 輸出格式 (嚴格) ====
直接回 JSON object, 從 {{ 開頭到 }} 結尾, 不要 Markdown fence、不要前後說明文字:

{{
  "id": "{section_id}",
  "title": "{section_title}",
  "slides": [
    {{
      "id": "{section_id}_1",
      "title": "...",
      "bullets": ["...", "..."],
      "code_snippet": null,
      "code_lang": null,
      "file_path": null,
      "narration": "..."
    }}
  ]
}}
"""


# ---------- Public API ----------

def script_repo(outline: dict, raw_content: dict) -> dict:
    """outline + raw_content → 完整 deck.json。

    每個 section 各自呼叫一次 Gemini, 失敗的 section 會留下佔位 slide
    (避免整份 deck 廢掉, 與 solve.py 的 partial-failure 哲學一致)。
    """
    if raw_content.get("source_kind") != "repo":
        raise ValueError(f"script_repo 只吃 repo, 收到 {raw_content.get('source_kind')}")

    api_key = get_gemini_api_key()
    if not api_key:
        sys.exit("❌ 缺少 GEMINI_API_KEY 環境變數")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

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
        )

        section_dict = _call_with_retry(client, types, prompt, section_id, sec_outline)
        sections_out.append(section_dict)

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


# ---------- Internals ----------

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
            cfg_kwargs = {
                "temperature": params["temp"],
                "max_output_tokens": params["max_tokens"],
            }
            if params["no_thinking"]:
                try:
                    cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
                except Exception:
                    pass
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(**cfg_kwargs),
            )
            raw_text = (resp.text or "").strip()
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

    每個 section 產 2~3 張投影片, narration 用 outline 的 intent + topics 組,
    確保下游 deck_to_exam_schema + pipeline.py 能跑得起來。
    """
    root_name = raw_content.get("root_name", "project")
    primary_lang = raw_content.get("primary_language", "")
    file_index = {kf["path"]: kf for kf in raw_content.get("key_files", [])}

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

        # 第二張: 若有 key_files, 抓第一個出來給 code_snippet
        if sec.get("key_files"):
            fp = sec["key_files"][0]
            kf = file_index.get(fp)
            if kf and kf.get("content"):
                # 只取前 6 行避免太長
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

    deck = {
        "deck_title": outline.get("deck_title", f"{root_name} — 講解 (Mock)"),
        "source_type": "repo",
        "source_meta": {
            "root_name": root_name,
            "primary_language": primary_lang,
            "scanned_files": raw_content.get("stats", {}).get("selected"),
        },
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

    outline = json.loads(Path(args.outline).read_text(encoding="utf-8"))
    raw = json.loads(Path(args.raw_content).read_text(encoding="utf-8"))
    deck = mock_deck_from_outline(outline, raw) if args.mock else script_repo(outline, raw)

    out_path = Path(args.out) if args.out else Path(args.outline).with_name("deck.json")
    out_path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    total_slides = sum(len(s["slides"]) for s in deck["sections"])
    print(f"✅ deck 寫到 {out_path} ({len(deck['sections'])} sections / {total_slides} slides)")
