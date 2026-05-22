"""Deck schema 與 v1 exam schema 之間的轉換 helper。

PR-2b-i 引入新的 deck schema (sections / slides) 給 repo / document / url 內容用。
為了讓既有 pipeline.py (黑板渲染) 能直接吃, 提供 `deck_to_exam_schema()` 把新 schema
壓平成 v1 exam schema。

未來 PR-2b-ii 的 pptx pipeline 會直接吃新 deck schema, 不再經這層轉換。

新 deck schema:
{
  "deck_title": "...",
  "source_type": "repo" | "slides" | "document" | ...,
  "source_meta": { "path": "...", "primary_language": "python", ... },
  "sections": [
    {
      "id": "intro",
      "title": "專案目的與架構概觀",
      "slides": [
        {
          "id": "intro_1",
          "title": "為什麼有這個專案",
          "bullets": ["..."],
          "code_snippet": null | "...",
          "code_lang": null | "python",
          "file_path": null | "core/foo.py",
          "narration": "...",
          "notes": null   // 額外說明 (debug / TTS hint),不顯示在投影片
        }
      ]
    }
  ]
}
"""
from __future__ import annotations

from typing import Any


def deck_to_exam_schema(deck: dict) -> dict:
    """把 deck.json 壓成 v1 exam.json schema 給 pipeline.py 吃 (黑板模式)。

    對應規則:
    - deck.deck_title       -> exam.exam_title
    - section               -> problem (id 沿用、number 用 "第 N 章 標題")
    - slide                 -> step (display = title + bullets + code_snippet, narration 直接給)
    - 章節間沒有原本「題目」欄位的對應, 用 section.title 當 problem 文字
    """
    problems = []
    for i, section in enumerate(deck.get("sections", [])):
        steps = []
        for slide in section.get("slides", []):
            display = _slide_to_display(slide)
            steps.append({
                "_section": _shorten_section_label(section.get("title", "")),
                "display": display,
                "narration": slide.get("narration", "").strip(),
            })
        if not steps:
            continue
        problems.append({
            "id": section.get("id", f"sec{i+1}"),
            "number": f"第 {i+1} 章 {section.get('title', '').strip()}",
            "score": 0,
            "problem": section.get("title", "").strip(),
            "steps": steps,
        })

    return {
        "exam_title": deck.get("deck_title", "未命名"),
        "source_type": "deck",   # 跟 slides_pdf 的 "slides" 區分
        "source_meta": deck.get("source_meta", {}),
        "problems": problems,
    }


def deck_to_exam_schema_slides(deck: dict) -> dict:
    """slides_pdf 用: 把 deck (sections/slides) 壓成 v1 exam (problems/steps),
    保留 bg_image / bg_type / layout 給 SlideRenderer 直接吃。

    跟 deck_to_exam_schema 的差別:
    - step.bg_type 預設 "slide" (不是黑板)
    - step 額外帶 bg_image / layout 透傳, pipeline 走 SlideRenderer
    - display 直接用 slide.title (無 bullets / code block 邏輯)

    PR-3h 引入: server runner SLIDES_PDF 走這條;
    其他 source_type 仍用 deck_to_exam_schema (黑板) 或 deck_to_exam_schema_pptx (Forest)。
    """
    problems = []
    for i, section in enumerate(deck.get("sections", [])):
        section_title = section.get("title", "").strip()
        steps = []
        for slide in section.get("slides", []):
            slide_title = (slide.get("title") or "").strip()
            steps.append({
                # _section: 黑板模式才用得到, slide 模式不顯示但留著無妨
                "_section": _shorten_section_label(section_title),
                "display": slide_title or "投影片",
                "narration": (slide.get("narration") or "").strip(),
                "bg_type": slide.get("bg_type") or "slide",
                "bg_image": slide.get("bg_image"),
                "layout": slide.get("layout") or "full",
                # Phase 4 split-left 用 (full layout 不讀, 一律透傳保留 schema 一致):
                # title 跟 display 重複 (split-left 用 title 才能還原 layout="full" 改回 split-left 時的原文),
                # bullets 是 split-left 右半文字
                "title": slide_title,
                "bullets": list(slide.get("bullets") or []),
                # iter 100 (E2-4): icon_overlay 透傳, slides_pdf 路徑也吃 (review UI 共用)
                "icon_overlay": slide.get("icon_overlay"),
                # iter 101 (E1-1): image_frames 透傳, slides_pdf 也吃 (review UI 共用)
                "image_frames": slide.get("image_frames"),
            })
        if not steps:
            continue
        problems.append({
            "id": section.get("id", f"ch{i+1}"),
            "number": f"第 {i+1} 章 {section_title}",
            "score": 0,
            "problem": section_title,
            "steps": steps,
        })

    return {
        "exam_title": deck.get("deck_title", "未命名"),
        "source_type": "slides",  # 給 pipeline / Library 看
        "source_meta": deck.get("source_meta", {}),
        "problems": problems,
    }


def deck_to_exam_schema_pptx(deck: dict, *, short_video_layout: bool = False) -> dict:
    """把 deck.json 壓成 v1 exam schema, 但 step 帶 pptx_slide 渲染所需欄位。

    跟 deck_to_exam_schema 的差別:
    - step.bg_type = "pptx_slide" (讓 pipeline 走 PptxStyleRenderer)
    - step 額外保留 title / bullets / code_snippet / code_lang / file_path
      / section_title 給 renderer 直接讀
    - display 仍然有 (legacy fallback), 但 PptxStyleRenderer 不用

    PR-2b-ii: source_type=repo 走這條轉換, 其他類型仍走 deck_to_exam_schema 黑板版。

    iter 88: short_video_layout=True 時 (ultra_quick mode UI 預設自動勾),
    pptx_slide 改用 bg_type="short_video_slide" 走獨立大字居中 layout —
    給 Shorts/TikTok/Reels 即時震撼用. cover/outro 不受影響.
    """
    problems = []
    for i, section in enumerate(deck.get("sections", [])):
        section_title = section.get("title", "").strip()
        steps = []
        for slide in section.get("slides", []):
            # iter 62 + 63: 封面 / 結尾 slide 走專屬 bg_type, 不被覆寫成 pptx_slide
            slide_bg_type = slide.get("bg_type")
            if slide_bg_type in ("cover", "outro"):
                bg_type = slide_bg_type
            elif short_video_layout:
                # iter 88: 短影片用獨立大字 layout
                bg_type = "short_video_slide"
            else:
                bg_type = "pptx_slide"
            step = {
                "_section": _shorten_section_label(section_title),
                "section_title": section_title,
                "title": (slide.get("title") or "").strip(),
                "bullets": [b for b in (slide.get("bullets") or []) if b],
                "code_snippet": slide.get("code_snippet"),
                "code_lang": slide.get("code_lang"),
                "file_path": slide.get("file_path"),
                "display": _slide_to_display(slide),  # legacy
                "narration": (slide.get("narration") or "").strip(),
                "bg_type": bg_type,
                # iter 53: figure id (or None). 此時還是 deck.json 的 id
                # (例如 "fig_p3_1"), runner 會在 render 前轉成絕對路徑.
                "image_path": slide.get("image_path"),
                # iter 100 (E2-4): icon_overlay list[dict] | None — 動態視覺素材 RFC.
                # E2-5 renderer 走 PIL alpha_composite 疊 icon. 此處純透傳, 不檢驗.
                "icon_overlay": slide.get("icon_overlay"),
                # iter 101 (E1-1): image_frames list[dict] | None — 動態視覺素材 RFC E1.
                # 流程圖 frame 序列, 渲染端 (E1-2) 偵測 list 走多 PNG 順序. 此處純透傳.
                "image_frames": slide.get("image_frames"),
            }
            # iter 62: cover 專屬 meta 欄位 (其他 layout 不會讀)
            if bg_type == "cover":
                step["cover_speaker"] = slide.get("cover_speaker", "")
                step["cover_org"] = slide.get("cover_org", "")
                step["cover_date"] = slide.get("cover_date", "")
            # iter 63: outro 專屬 meta 欄位 (其他 layout 不會讀)
            elif bg_type == "outro":
                step["outro_speaker"] = slide.get("outro_speaker", "")
                step["outro_org"] = slide.get("outro_org", "")
                step["outro_url"] = slide.get("outro_url", "")
                # iter 67 QR code 欄位
                step["outro_show_qr"] = slide.get("outro_show_qr", False)
                step["outro_youtube_url"] = slide.get("outro_youtube_url", "")
            steps.append(step)
        if not steps:
            continue
        problems.append({
            "id": section.get("id", f"sec{i+1}"),
            "number": f"第 {i+1} 章 {section_title}",
            "score": 0,
            "problem": section_title,
            "steps": steps,
        })

    return {
        "exam_title": deck.get("deck_title", "未命名"),
        "source_type": "deck_pptx",
        "source_meta": deck.get("source_meta", {}),
        "problems": problems,
    }


def _shorten_section_label(title: str) -> str:
    """_section 是黑板渲染右下角小標,過長會擠到。8 字內。"""
    title = title.strip()
    return title[:8] if len(title) > 8 else title


def _slide_to_display(slide: dict) -> str:
    """把 slide 各欄位組成黑板可顯示的純文字 display。

    渲染順序: title -> bullets -> code_snippet (含檔名 header)
    黑板字數限制 ~40 字一行,所以 bullets 不要太長,code_snippet 不要超過 ~10 行。
    這個轉換不負責截斷 — scriptor 階段就該控制好內容長度。
    """
    parts: list[str] = []
    title = (slide.get("title") or "").strip()
    if title:
        parts.append(title)

    bullets = slide.get("bullets") or []
    for b in bullets:
        b = (b or "").strip()
        if b:
            parts.append(f"• {b}")

    code = (slide.get("code_snippet") or "").strip()
    if code:
        # 程式碼前面加檔名 header (如果有), 讓學生知道是哪個檔
        file_path = (slide.get("file_path") or "").strip()
        if file_path:
            parts.append(f"# {file_path}")
        parts.append(code)

    return "\n".join(parts) if parts else "(無內容)"


# ---------- Validators / 修補 ----------

def normalize_deck(deck: dict) -> dict:
    """補齊 deck 缺漏欄位,LLM 偶爾會漏 id / bullets / 留 None。

    這個 normalizer 只做 in-place 補, 不檢驗語意正確性。
    """
    deck.setdefault("deck_title", "未命名")
    deck.setdefault("source_type", "unknown")
    deck.setdefault("source_meta", {})
    sections = deck.setdefault("sections", [])

    for i, sec in enumerate(sections):
        sec.setdefault("id", f"sec{i+1}")
        sec.setdefault("title", f"第 {i+1} 章")
        slides = sec.setdefault("slides", [])
        for j, sl in enumerate(slides):
            sl.setdefault("id", f"{sec['id']}_{j+1}")
            sl.setdefault("title", "")
            sl.setdefault("bullets", [])
            sl.setdefault("code_snippet", None)
            sl.setdefault("code_lang", None)
            sl.setdefault("file_path", None)
            sl.setdefault("narration", "")
            sl.setdefault("notes", None)
            sl.setdefault("image_path", None)   # iter 52: figure 配圖 id (or None)
            sl.setdefault("icon_overlay", None)  # iter 100 (E2-4): list[dict] | None
            # 動態視覺素材 RFC Phase 1, 給 icon_picker / review UI / slide_renderer 共用.
            # 每個 dict 預期欄位: path / position / size_ratio /
            # 選擇性的 start_ms / duration_ms (None = 整 slide). 此處不檢驗
            # 內部結構 — E2-5 renderer 接時用 .get() 容錯.
            sl.setdefault("image_frames", None)  # iter 101 (E1-1): list[dict] | None
            # 動態視覺素材 RFC Phase 1 — E1 PNG frame 序列 (流程圖/架構圖漸進顯示).
            # 每個 dict 預期欄位: path (str, PNG 絕對/相對) + display_ratio
            # (float 0.0~1.0 累進佔比). 渲染端 (E1-2) 偵測 list 走多 PNG 順序模式,
            # 配 narration 時長均分. 舊 deck 沒這欄 → 用既有 image_path 單張流程.

    return deck


def assert_deck_minimum(deck: dict) -> None:
    """執行前 sanity check: 至少要有 1 章 1 段且 narration 非空, 否則 render 會空轉。"""
    if not deck.get("sections"):
        raise ValueError("deck 缺 sections")
    for sec in deck["sections"]:
        if not sec.get("slides"):
            raise ValueError(f"section {sec.get('id')} 沒有 slides")
        for sl in sec["slides"]:
            if not (sl.get("narration") or "").strip():
                raise ValueError(f"slide {sl.get('id')} narration 為空, 無法渲染")
