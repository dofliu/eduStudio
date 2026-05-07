"""Outliner — 把 raw_content 餵 Gemini, 產 outline.json。

設計原則:
- 一次 Gemini call (不像 scriptor 是逐 section), 因為 outline 只是骨架,
  資料量比較小, 一次到位省 token
- 強制輸出純 JSON (跟 solve.py / slide_ingest.py 同套 fence 處理)
- 沒拿到合法 JSON 就 retry 1 次, 用更高 temperature

outline.json schema (給 scriptor 階段吃):
{
  "deck_title": "...",
  "summary": "1-2 句整體介紹, 用於開場白",
  "sections": [
    {
      "id": "intro",
      "title": "專案目的",
      "intent": "讓觀眾理解這個專案要解決什麼問題",
      "topics": ["教學影片自動生成", "AI 輔助 vs 全自動"],
      "key_files": ["README.md"]
    },
    ...
  ]
}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .config import GEMINI_MODEL, get_gemini_api_key
from .text_utils import clean_json_escapes, strip_latex


# ---------- Prompt ----------

OUTLINE_PROMPT_REPO = """你是一位資深的軟體工程師兼技術講師, 擅長把 GitHub 專案拆成易懂的講解大綱。
你會收到一份 repo 的精簡內容 (檔案樹 + 主要檔案內容), 請設計一份 8~15 分鐘講解影片的章節大綱。

==== Repo 內容 ====
專案名稱: {root_name}
主要語言: {primary_language}
語言分佈 (副檔名: bytes): {lang_stats}

檔案樹:
```
{tree}
```

關鍵檔案內容 (依重要性排序):
{key_files_section}

==== 大綱設計原則 ====
1. **章節數 4~6 章**, 每章對應一段 1.5~3 分鐘的講解 (約 5~10 張投影片)
2. **第一章必為「專案目的」或「整體介紹」**, 讓觀眾理解 motivation 與大架構
3. **最後一章必為「如何使用」或「下一步」**, 給觀眾具體 take-away
4. **中間章節依重點分配** — 核心模組逐個介紹、關鍵流程拆解、特殊技術點
5. **章節 title 簡潔 (4~12 字)**, intent 一句話 (不超過 30 字)
6. **topics 列 3~6 個重點關鍵詞**, 不是完整句子
7. **key_files 列出本章會引用的檔案路徑** (來自上面檔案樹), 沒對應就空 list
8. **deck_title 用專案實際名稱 + 副標題** (例: "autoSolverVideo — 考卷檢討影片自動生成")
9. **summary 1~2 句, 開場白用**, 描述「這個專案解決什麼問題」

==== 嚴禁事項 ====
- 不要 LaTeX、Markdown 標題、emoji
- 不要編造 repo 裡不存在的檔案/功能 (key_files 必須真實存在)
- 不要把 README 整段抄成 topics, 要提煉成關鍵詞

==== 輸出格式 (嚴格) ====
直接回 JSON object, 從 {{ 開頭到 }} 結尾, 不要 Markdown fence、不要前後說明文字:

{{
  "deck_title": "...",
  "summary": "...",
  "sections": [
    {{
      "id": "intro",
      "title": "...",
      "intent": "...",
      "topics": ["...", "..."],
      "key_files": ["README.md", "core/__init__.py"]
    }}
  ]
}}
"""


# ---------- Public API ----------

def outline_repo(raw_content: dict, *, max_files_in_prompt: int = 25) -> dict:
    """raw_content (repo adapter 輸出) → outline dict。

    max_files_in_prompt: 餵進 prompt 的檔案數上限, 避免 token 爆。
    通常 README + STATUS + ROADMAP + 主要 source 25 個就夠 outline 用,
    完整 50 個檔留給 scriptor 階段精讀。
    """
    if raw_content.get("source_kind") != "repo":
        raise ValueError(f"outline_repo 只吃 source_kind=repo, 收到 {raw_content.get('source_kind')}")

    api_key = get_gemini_api_key()
    if not api_key:
        sys.exit("❌ 缺少 GEMINI_API_KEY 環境變數")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    prompt = OUTLINE_PROMPT_REPO.format(
        root_name=raw_content.get("root_name", "(unknown)"),
        primary_language=raw_content.get("primary_language") or "unknown",
        lang_stats=json.dumps(raw_content.get("lang_stats", {}), ensure_ascii=False),
        tree=raw_content.get("tree", "(no tree)"),
        key_files_section=_format_key_files(
            raw_content.get("key_files", []),
            max_files=max_files_in_prompt,
        ),
    )

    raw_text = ""
    last_err = None
    for attempt, temp in enumerate([0.3, 0.6], start=1):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=temp,
                    max_output_tokens=8192,
                ),
            )
            raw_text = (resp.text or "").strip()
            cleaned = _strip_fence(raw_text)
            cleaned = clean_json_escapes(cleaned)
            outline = json.loads(cleaned)
            _normalize_outline(outline)
            return outline
        except Exception as e:
            last_err = e
            print(f"   ⚠ outline attempt {attempt} 失敗 (temp={temp}): {e}")

    # 兩次都失敗: 把 raw 存下來方便 debug
    err_dir = Path("./_outline_errors")
    err_dir.mkdir(exist_ok=True)
    (err_dir / "last_raw.txt").write_text(raw_text or f"(no resp) {last_err}", encoding="utf-8")
    raise RuntimeError(f"outline 兩次重試皆失敗,最後錯誤: {last_err}")


# ---------- Helpers ----------

def _format_key_files(key_files: list[dict], max_files: int) -> str:
    """把 key_files 拼成可讀的 markdown-ish block 餵 LLM。

    每個檔頭帶 path / kind / 是否截斷, 內容以 ```{lang} fence 包,
    LLM 看得清楚邊界。
    """
    blocks = []
    for kf in key_files[:max_files]:
        ext = Path(kf["path"]).suffix.lstrip(".")
        truncated_note = " (truncated)" if kf.get("truncated") else ""
        blocks.append(
            f"### {kf['path']}  ({kf['kind']}, {kf['bytes']} bytes{truncated_note})\n"
            f"```{ext}\n{kf['content']}\n```"
        )
    if len(key_files) > max_files:
        blocks.append(f"_(...另有 {len(key_files) - max_files} 個檔案省略)_")
    return "\n\n".join(blocks)


def _strip_fence(text: str) -> str:
    """LLM 偶爾還是會包 ```json ... ``` fence, 拆掉。"""
    text = text.strip()
    if text.startswith("```"):
        # 抓第一個 fence 內容
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        else:
            text = text.lstrip("`").strip()
            if text.startswith("json"):
                text = text[4:].lstrip()
    return text


def _normalize_outline(outline: dict) -> None:
    """補預設值 + 清掉 LaTeX 殘渣 (Gemini 偶爾會混進 \\theta 之類)。"""
    outline.setdefault("deck_title", "未命名")
    outline.setdefault("summary", "")
    outline["deck_title"] = strip_latex(outline["deck_title"])
    outline["summary"] = strip_latex(outline.get("summary", ""))

    sections = outline.setdefault("sections", [])
    for i, sec in enumerate(sections):
        sec.setdefault("id", f"sec{i+1}")
        sec.setdefault("title", f"第 {i+1} 章")
        sec.setdefault("intent", "")
        sec.setdefault("topics", [])
        sec.setdefault("key_files", [])
        sec["title"] = strip_latex(sec["title"])
        sec["intent"] = strip_latex(sec.get("intent", ""))
        sec["topics"] = [strip_latex(t) for t in sec["topics"] if t]


# ---------- Mock ----------

def mock_outline(raw_content: dict) -> dict:
    """離線測試用 — 不打 Gemini, 用 raw_content 拼一個結構合法的 outline。"""
    root = raw_content.get("root_name", "project")
    return {
        "deck_title": f"{root} — Mock 講解大綱",
        "summary": f"{root} 是一個 mock 模式產出的範例大綱,用於離線 smoke test。",
        "sections": [
            {
                "id": "intro",
                "title": "專案目的",
                "intent": "讓觀眾理解這個專案在做什麼",
                "topics": ["問題背景", "解法概觀"],
                "key_files": ["README.md"] if any(
                    kf["path"] == "README.md" for kf in raw_content.get("key_files", [])
                ) else [],
            },
            {
                "id": "arch",
                "title": "整體架構",
                "intent": "拆解三層 (CLI / core / server) 各自負責什麼",
                "topics": ["分層設計", "資料流"],
                "key_files": [kf["path"] for kf in raw_content.get("key_files", [])[:3]],
            },
            {
                "id": "next",
                "title": "如何使用",
                "intent": "給觀眾立刻能上手的指令",
                "topics": ["安裝", "啟動", "進階"],
                "key_files": [],
            },
        ],
    }


# ---------- CLI ----------

if __name__ == "__main__":
    import argparse

    from core.runtime import setup_utf8_stdout
    setup_utf8_stdout()

    ap = argparse.ArgumentParser(description="Outliner 自我測試")
    ap.add_argument("raw_content", help="raw_content.json 路徑 (repo adapter 產出)")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    raw = json.loads(Path(args.raw_content).read_text(encoding="utf-8"))
    outline = mock_outline(raw) if args.mock else outline_repo(raw)
    out_path = Path(args.out) if args.out else Path(args.raw_content).with_name("outline.json")
    out_path.write_text(json.dumps(outline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ outline 寫到 {out_path} ({len(outline['sections'])} sections)")
