"""AI 直接生圖 — iter 56, Option B.

差別於 core/diagram_gen.py (用 Gemini 寫 matplotlib code → AST validate →
subprocess render). 這個直接呼 Gemini 2.5 Flash Image API 拿 image bytes
寫檔.

跟 diagram_gen 比較:
- diagram_gen: 文字 LLM → matplotlib code → render. 限 7 種 kind, AST allowlist.
  品質有底 (內建 visuals 公式驅動), 但風格固定.
- diagram_image_gen (本檔): 圖文 LLM 直接生圖. 自由風格, 適合架構 / 流程 /
  概念圖. 但 LLM 圖也會醜, 需要 review (硬規則 #1).

用戶選擇 model: gemini-2.5-flash-image-preview (cheap 路, 不是 imagen 那條)
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Gemini 影像生成 model — Flash family 比 imagen 便宜
IMAGE_MODEL = "gemini-2.5-flash-image-preview"


def _build_diagram_prompt(section: dict, deck_title: str = "") -> str:
    """從 outline section 組生圖 prompt — 強調 educational diagram style,
    最小化文字標籤 (LLM 寫的英文標籤常拼錯, 我們靠 narration 解釋).
    """
    title = (section.get("title") or "").strip()
    intent = (section.get("intent") or "").strip()
    topics = section.get("topics") or []
    topics_str = ", ".join(t for t in topics if t)

    parts = [
        "Generate a clean technical diagram suitable for an educational video frame.",
        f"Topic: {title}",
    ]
    if intent:
        parts.append(f"Concept focus: {intent}")
    if topics_str:
        parts.append(f"Key elements to depict: {topics_str}")
    if deck_title:
        parts.append(f"Overall deck context: {deck_title}")

    parts.extend([
        "",
        "Style requirements:",
        "- Minimalist architecture / flowchart / concept-map style",
        "- Light or off-white background",
        "- Use simple geometric shapes (boxes, circles, arrows)",
        "- Short labels in English only (3 words max per label)",
        "- No dense paragraphs of text inside the diagram",
        "- Professional, clean lines — avoid 3D, gradients, shadows",
        "- Single concept per diagram — don't try to show everything",
        "- Aspect ratio close to 4:3 (panel area in 1920x1080 video)",
    ])
    return "\n".join(parts)


def generate_section_diagram_image(
    section: dict, out_path: Path, *,
    deck_title: str = "",
    api_key: str | None = None,
) -> tuple[bool, str]:
    """單一 section → 一張 AI 生圖, 寫到 out_path.

    回傳 (success, error_msg).
    success=False 時 error_msg 帶 reason, caller 通常 logger.warning skip
    這張圖 (不擋 ingest 流程).

    為什麼 single function 不批次:
    - Gemini image gen API 不支援 batch
    - 個別 call 失敗 (rate limit / safety filter) 不該牽連其他 section
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return (False, "google-genai SDK 未安裝")

    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return (False, "缺 GEMINI_API_KEY")

    prompt = _build_diagram_prompt(section, deck_title=deck_title)

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )
    except Exception as e:
        return (False, f"Gemini API call 失敗: {e}")

    # 走 parts 找 inline_data (image/png bytes)
    image_bytes = _extract_image_bytes(resp)
    if image_bytes is None:
        return (False, "Gemini 回應無 image bytes (可能 safety filter)")

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(image_bytes)
    except OSError as e:
        return (False, f"寫檔失敗: {e}")

    return (True, "")


def _extract_image_bytes(resp: Any) -> bytes | None:
    """從 Gemini generate_content 回應拉 image bytes.

    google-genai SDK 結構: response.candidates[0].content.parts[].inline_data.data
    inline_data.data 是 base64 str 或 raw bytes (視 SDK 版本), 試兩種.
    """
    import base64

    try:
        candidates = getattr(resp, "candidates", None) or []
        for cand in candidates:
            content = getattr(cand, "content", None)
            if content is None:
                continue
            parts = getattr(content, "parts", None) or []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                if inline is None:
                    continue
                data = getattr(inline, "data", None)
                if data is None:
                    continue
                # SDK 偶爾回 base64 str, 偶爾回 raw bytes
                if isinstance(data, bytes):
                    return data
                if isinstance(data, str):
                    try:
                        return base64.b64decode(data)
                    except Exception:
                        continue
        return None
    except Exception as e:
        logger.exception("解析 Gemini image response 失敗: %s", e)
        return None


def generate_diagrams_for_outline(
    outline: dict, figures_dir: Path, *,
    api_key: str | None = None,
    max_per_outline: int = 8,
) -> list[dict]:
    """整份 outline 各 section 跑一張 AI 生圖, 回傳 figure metadata list.

    每張圖檔名 ai_{section_id}.png, 存到 figures_dir.
    結構跟 PDF extract_pdf_figures 回的 figure dict 一致 — caller (runner)
    把這個 list 跟 PDF figures 合併進 raw_content.figures.

    參數:
        max_per_outline: 限上限 (預設 8). 多 section 的 lecture 模式不該每章都
                        燒 API 額度, 取前 N 章. caller 也可在更高層限.

    回傳 figure dict (跟 extract_pdf_figures 一致 schema):
        {
          "id": "ai_intro",
          "page_no": 0,                  # AI 圖無頁碼, 用 0
          "path": "ai_intro.png",
          "width": 1024, "height": 1024, # 估值, 不準也沒關係 (scriptor 用 caption)
          "caption_hint": "intro: ...",  # section.intent 第一句
        }
    """
    sections = outline.get("sections", [])[:max_per_outline]
    deck_title = outline.get("deck_title", "")
    out: list[dict] = []

    for sec in sections:
        sec_id = sec.get("id") or "unknown"
        # 防 path traversal: sec_id 限 ascii / 數字 / 底線
        safe_id = "".join(c for c in sec_id if c.isalnum() or c == "_")[:40]
        if not safe_id:
            continue
        fname = f"ai_{safe_id}.png"
        fpath = figures_dir / fname

        ok, err = generate_section_diagram_image(
            sec, fpath, deck_title=deck_title, api_key=api_key,
        )
        if not ok:
            logger.warning("AI 生圖跳過 section %s: %s", sec_id, err)
            continue

        out.append({
            "id": f"ai_{safe_id}",
            "page_no": 0,
            "path": fname,
            "width": 1024,
            "height": 1024,
            "caption_hint": (sec.get("title") or "")[:120],
        })

    return out
