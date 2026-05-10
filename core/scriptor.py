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
請針對指定章節, 產出 5~10 張投影片的講解內容。**這是程式碼專案的講解, 沒有真實程式碼片段就是失敗的講解**。

==== 整體脈絡 ====
專案: {deck_title}
講解主軸: {summary}
這是第 {section_idx}/{total_sections} 章

==== 本章資訊 ====
標題: {section_title}
意圖: {section_intent}
重點關鍵詞: {section_topics}

==== 本章必須引用的檔案 (你的 code_snippet 必須來自這裡) ====
{section_files_section}

==== ★★★ 程式碼覆蓋率硬規則 (最重要) ★★★ ====
這是「程式碼講解」影片, **本章 5~10 張投影片中必須至少 3 張**包含 code_snippet。
若整章 0 張 code_snippet, 視為品質不合格的輸出。

唯一豁免: 若上面 ==== 本章必須引用的檔案 ==== 區段顯示「未指定 key_files」,
才允許整章不放 code_snippet (但仍鼓勵舉抽象例子)。

正確的 code_snippet slide 範例 (這是你應該模仿的結構):
{{
  "id": "ingest_3",
  "title": "Repo 掃描: scan_repo()",
  "bullets": [
    "走遍整個 repo, 跳過 binary 與 build artifact",
    "依 priority 選 ≤50 個檔餵 LLM",
    "輸出 raw_content (tree + key_files + lang_stats)"
  ],
  "code_snippet": "def scan_repo(repo_path: Path, *, max_files: int = 50) -> dict:\\n    candidates = []\\n    for p in repo_path.rglob(\\"*\\"):\\n        if any(part in SKIP_DIRS for part in p.parts):\\n            continue\\n        kind = _classify(p)\\n        if kind is None:\\n            continue\\n        candidates.append((_priority(p, kind), p, kind))\\n    candidates.sort(key=lambda x: -x[0])\\n    return _build_result(candidates[:max_files])",
  "code_lang": "python",
  "file_path": "core/adapters/repo.py",
  "narration": "我們先看 scan_repo 這個函式..."
}}

注意: code_snippet 是「實際出現在你拿到的檔案內容裡」的程式碼摘錄, 不是你寫的偽碼。

==== 投影片設計建議結構 ====
- 第 1 張: 章節概觀 (無 code, bullets 介紹本章重點)
- 第 2~N 張: code walkthrough (每張帶一個關鍵函式 / class / 設定區塊的 code_snippet)
- 最後 1 張: 本章重點回顧 (無 code, 收束)

==== 投影片格式規則 ====
1. **5~10 張投影片**
2. **每張 narration 100~200 字** (中文字數), 對應 30~60 秒語音
3. **narration 用「劉老師」第一人稱口吻**, 自然口語, 解釋「為什麼這樣寫」「這段做什麼」
4. **bullets 每點 ≤ 25 字**, 一張投影片不超過 4 個 bullet
5. **code_snippet 一次 6~12 行**, 太長就摘關鍵幾行 + 用 ... 省略號標示
6. **file_path 標註 code 來自哪個檔** (例: "core/outliner.py")
7. **code_lang** 用副檔名小寫 (python / javascript / typescript / yaml ...)
8. **slide title 簡潔 (4~14 字)**, 不要跟 narration 第一句重複

==== 嚴禁事項 (★ 重要) ====
- 不可發明檔案沒有的函式 / class / API; code_snippet 必須是上方檔案內容的真實摘錄
- 不要 LaTeX、Markdown 標題符號、emoji、\\theta 之類反斜線命令
- 不要在 narration 重念 bullets 文字; narration 解釋「為什麼」, bullets 是「重點」
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
    }},
    {{
      "id": "{section_id}_2",
      "title": "...",
      "bullets": ["...", "..."],
      "code_snippet": "def example():\\n    ...",
      "code_lang": "python",
      "file_path": "core/foo.py",
      "narration": "..."
    }}
  ]
}}
"""


# ---------- Long-form (document / url) section prompt ----------

LONGFORM_SECTION_PROMPT = """你是一位資深的講師, 擅長把長篇文件 (講義 / 部落格文章 / 報告) 拆成清楚的講解投影片。
請針對指定章節, 產出 5~10 張投影片的講解內容。

==== 整體脈絡 ====
文件: {deck_title}
講解主軸: {summary}
這是第 {section_idx}/{total_sections} 章

==== 本章資訊 ====
標題: {section_title}
意圖: {section_intent}
重點關鍵詞: {section_topics}

==== 完整文件內容 (請聚焦在本章主題的部分) ====
{document_content}

==== 投影片設計原則 ====
1. **5~10 張投影片**, 第一張通常是章節概觀, 最後一張為小結
2. **每張 narration 100~200 字** (中文字數), 對應 30~60 秒語音
3. **narration 用「劉老師」第一人稱口吻**, 自然口語, 解釋「為什麼這個概念重要」「實際怎麼用」
4. **bullets 每點 ≤ 25 字**, 一張投影片不超過 4 個 bullet
5. **slide title 簡潔 (4~14 字)**, 不要跟 narration 第一句重複
6. **內容必須來自上方文件**, 不可發明文件沒提到的概念 / 數據 / 引言

==== 嚴禁事項 ====
- 不要 LaTeX、Markdown 標題符號、emoji、\\theta 之類反斜線命令
- 不要編造文件沒提到的內容; 寧可少說也不要捏造
- code_snippet / code_lang / file_path 全部設 null (這是文件講解, 不是程式碼導覽)
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

def script(outline: dict, raw_content: dict) -> dict:
    """Source-agnostic scriptor — 依 source_kind dispatch。

    PR-3b: source_kind in {"repo", "document", "url"}。
    """
    kind = raw_content.get("source_kind")
    if kind == "repo":
        return script_repo(outline, raw_content)
    if kind in ("document", "url"):
        return script_long_form(outline, raw_content)
    raise ValueError(f"未支援的 source_kind: {kind!r}")


def script_repo(outline: dict, raw_content: dict) -> dict:
    """outline + raw_content (repo) → 完整 deck.json。

    每個 section 各自呼叫一次 Gemini, 失敗的 section 會留下佔位 slide
    (避免整份 deck 廢掉, 與 solve.py 的 partial-failure 哲學一致)。
    """
    if raw_content.get("source_kind") != "repo":
        raise ValueError(f"script_repo 只吃 repo, 收到 {raw_content.get('source_kind')}")

    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("缺少 GEMINI_API_KEY 環境變數")

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


def script_long_form(outline: dict, raw_content: dict) -> dict:
    """outline + raw_content (document / url) → 完整 deck.json。

    跟 script_repo 結構一致 (逐 section call Gemini + 共用 retry / placeholder),
    差別在 prompt 餵的是 long-form text 而不是 key_files。
    """
    kind = raw_content.get("source_kind")
    if kind not in ("document", "url"):
        raise ValueError(f"script_long_form 只吃 document / url, 收到 {kind!r}")

    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("缺少 GEMINI_API_KEY 環境變數")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    document_content = raw_content.get("content", "")
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
        )

        section_dict = _call_with_retry(client, types, prompt, section_id, sec_outline)
        sections_out.append(section_dict)

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
