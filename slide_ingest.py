#!/usr/bin/env python3
"""
slide_ingest.py — 簡報 PDF → exam.json (扁平 slide 模式)

流程:
1. PDF 每頁渲染成 PNG (PyMuPDF, 1920px 寬), 存到 slides/<stem>/p001.png
2. Pass 1: Gemini 看全部頁面縮圖, 切章節
3. Pass 2: 逐頁 Gemini 看高解析圖 + 章節 context, 產 narration 草稿
4. 組成 exam.json 格式 (一個 chapter = 一個 problem, slides = steps)

需要環境變數: GEMINI_API_KEY
使用:
    python3 slide_ingest.py <input.pdf> [output.json]
    python3 slide_ingest.py <input.pdf> --mock     # 離線, 用佔位 narration
    python3 slide_ingest.py <input.pdf> --single   # 強制單一章節 (跳過切分)

輸出:
    slides/<stem>/p001.png ... pNNN.png    (高解析渲染)
    exams/<stem>.json                       (供 batch.py / app.py 使用)
"""
import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

import fitz  # pymupdf

# LaTeX 後處理改從 core 拿 (PR-1 重構): 之前 from solve import 會連帶觸發 solve.py 副作用
from core.text_utils import strip_latex, clean_json_escapes

BASE_DIR = Path(__file__).parent
SLIDES_ROOT = BASE_DIR / "slides"
EXAMS_ROOT = BASE_DIR / "exams"

MODEL = "gemini-2.5-flash"
SLIDE_DPI = 200          # 1920px 寬左右 (16:9 投影片)
THUMB_WIDTH = 640        # 章節切分用縮圖, 省 token
NARRATION_MAX_TOKENS = 4096  # 詳盡模式上限 240 字 ≈ 700 tokens, 留 retry 餘裕


# 章節切分 prompt
# 設計目標: 一章 ≈ 12~15 分鐘影片 → 大約 10~12 頁 × 每頁 75s narration
CHAPTER_PROMPT = """你看到的是一份簡報的全部投影片縮圖, 順序由 page 1 開始。
請分析整體結構, 把投影片切成「邏輯章節」, 用於後續錄製 12~15 分鐘的講解影片。

切分原則:
1. **以章節標題頁為界線** — 通常有大字標題、留白多、不含密集內文
2. **議題轉換點才切** — 主題明顯切換才切, 同主題不要硬切
3. **每章 8~15 頁為佳** — 目標每章對應一支 12~15 分鐘影片
   - 不要切太碎 (< 8 頁), 學生看一堆短片很煩
   - 超過 15 頁才再切
4. **總頁數 ≤ 12 頁時不要切**, 直接回單一章節
5. **章節標題用簡報中的實際標題**, 找不到就用該章主題的 4~12 字摘要

==== 輸出格式 (嚴格) ====
直接輸出 JSON array, 不要 Markdown 標記, 不要說明文字:

[
  {"title": "章節標題", "start_page": 1, "end_page": 10},
  {"title": "...", "start_page": 11, "end_page": 22}
]

start_page / end_page 為 1-indexed inclusive。第一章 start_page 必為 1, 最後一章 end_page 必為總頁數, 章節間頁碼連續不重疊。
"""

# 單頁 narration prompt — 詳盡模式 (預設)
# 目標 200~250 字 ≈ 60~80 秒語音, 配合 12 頁/章 → 每支影片約 12~15 分鐘
NARRATION_PROMPT_DETAILED = """你正在替一份簡報的單張投影片撰寫教師講解旁白, 用於講解影片。

==== 章節背景 ====
本投影片屬於「{chapter_title}」章節 (本章共 {chapter_pages} 頁, 此為第 {page_in_chapter} 頁)。

==== 上一張投影片的旁白 (供銜接, 不要重複) ====
{prev_narration}

==== 本張投影片內容 ====
請看圖。

==== 撰寫要求 ====
**首要規則: 句子必須完整, 結尾使用句點「。」, 絕對不要在半句話停下。**

1. 目標長度 200~250 字 (對應 60~80 秒語音), 比目標多 30 字或少 30 字皆可,
   寧可寫到 280 字並完整收尾, 也不要 200 字卻句子半截
2. 「劉老師」第一人稱口吻, 自然口語, 像在課堂面對學生
3. 內容深度: 不只朗讀投影片, 加入下列任一兩項:
   - 概念是什麼 + 為什麼重要
   - 一個具體例子 (生活場景或工程應用)
   - 原理或前後概念的關聯
   - 典型易錯點
4. 開頭銜接多樣化, 不要每張都「好, 我們來看」
5. 不要 LaTeX、不要 Markdown、不要符號標記; 程式碼用「等於」「冒號」念
6. 純中文 + 必要英文術語 / 數值

==== 輸出格式 ====
直接輸出純文字, 不要前言、引號、分段。
"""

# 單頁 narration prompt — 簡短模式 (--brief 啟用)
# 50~120 字 ≈ 15~35 秒, 適合純概念過水或快速複習用
NARRATION_PROMPT_BRIEF = """你正在替一份簡報的單張投影片撰寫教師講解旁白, 用於快速複習風格的影片。

==== 章節背景 ====
本投影片屬於「{chapter_title}」章節 (本章共 {chapter_pages} 頁, 此為第 {page_in_chapter} 頁)。

==== 上一張投影片的旁白 (僅供銜接參考, 不要重複) ====
{prev_narration}

==== 本張投影片內容 ====
請看圖。

==== 撰寫要求 ====
1. 50~120 字之間 (中文字數)
2. 以「劉老師」第一人稱口吻, 自然口語
3. 解釋圖中的重點概念、公式、流程圖, 不要只朗讀標題
4. 末尾用句點「。」結束
5. **不要使用 LaTeX / Markdown 標記**
6. 純中文 + 必要的英文術語 / 數值

==== 輸出格式 ====
直接輸出旁白內容, 不要前言、不要引號、不要分段, 一段純文字。
"""


def _ensure_dirs():
    SLIDES_ROOT.mkdir(parents=True, exist_ok=True)
    EXAMS_ROOT.mkdir(parents=True, exist_ok=True)


def render_pdf_pages(pdf_path: Path, out_dir: Path) -> list[Path]:
    """每頁 → 高解析 PNG, 存到 out_dir/p001.png ... 回傳路徑 list (1-indexed 順序)。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    paths = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=SLIDE_DPI)
        out_p = out_dir / f"p{i+1:03d}.png"
        pix.save(out_p)
        paths.append(out_p)
    doc.close()
    return paths


def render_thumbs(pdf_path: Path) -> list[bytes]:
    """每頁 → 低解析 PNG bytes (in-memory), 給章節切分階段省 token。"""
    doc = fitz.open(pdf_path)
    thumbs = []
    for page in doc:
        # 縮放到大約 THUMB_WIDTH 寬 (PyMuPDF 用 zoom matrix)
        pw = page.rect.width
        zoom = THUMB_WIDTH / pw if pw > 0 else 1.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        thumbs.append(pix.tobytes("png"))
    doc.close()
    return thumbs


def detect_chapters_with_gemini(thumbs: list[bytes], total_pages: int) -> list[dict]:
    """Gemini 看縮圖切章節, 回傳 [{title, start_page, end_page}]。"""
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 GEMINI_API_KEY 環境變數")
    client = genai.Client(api_key=api_key)

    parts = [types.Part.from_bytes(data=t, mime_type="image/png") for t in thumbs]
    resp = client.models.generate_content(
        model=MODEL,
        contents=parts + [CHAPTER_PROMPT],
        config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=4096),
    )
    raw = (resp.text or "").strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = clean_json_escapes(raw.strip())
    try:
        chapters = json.loads(raw)
    except Exception as e:
        print(f"⚠ 章節切分 JSON 解析失敗: {e}")
        Path("gemini_error_chapters.txt").write_text(raw, encoding="utf-8")
        print("  → 退回單一章節模式")
        return [{"title": "全部內容", "start_page": 1, "end_page": total_pages}]

    return _normalize_chapters(chapters, total_pages)


def _normalize_chapters(chapters: list[dict], total_pages: int) -> list[dict]:
    """確保章節覆蓋全頁、不重疊、邊界合理。Gemini 偶爾會漏頁或越界。"""
    if not chapters:
        return [{"title": "全部內容", "start_page": 1, "end_page": total_pages}]
    cleaned = []
    for c in chapters:
        try:
            s, e = int(c["start_page"]), int(c["end_page"])
            t = str(c.get("title", "")).strip() or f"第 {len(cleaned)+1} 章"
            if s < 1 or e > total_pages or s > e:
                continue
            cleaned.append({"title": strip_latex(t), "start_page": s, "end_page": e})
        except (KeyError, ValueError, TypeError):
            continue
    if not cleaned:
        return [{"title": "全部內容", "start_page": 1, "end_page": total_pages}]
    # 修正邊界: 第一章從 1 開始, 最後一章到末頁
    cleaned.sort(key=lambda c: c["start_page"])
    cleaned[0]["start_page"] = 1
    cleaned[-1]["end_page"] = total_pages
    # 修補章節間隙 (Gemini 偶爾少切一頁)
    for i in range(len(cleaned) - 1):
        if cleaned[i+1]["start_page"] != cleaned[i]["end_page"] + 1:
            cleaned[i]["end_page"] = cleaned[i+1]["start_page"] - 1
    return cleaned


_SENTENCE_END = ("。", "！", "？", ".", "!", "?")
NARRATION_TARGET_CHARS = 250
NARRATION_HARD_MAX = 320  # 超過就 post-process truncate (Gemini 偶爾寫超長)


def _clean_narration(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"^[「『\"']", "", text)
    text = re.sub(r"[」』\"']$", "", text)
    return strip_latex(text)


def _truncate_at_sentence(text: str, target: int = NARRATION_TARGET_CHARS,
                          hard_max: int = NARRATION_HARD_MAX) -> str:
    """超過 hard_max 就在 target 附近找最近的句尾標點切, 確保收尾完整。
    Gemini 對中文字數不易精準控制, 這裡兜底防止單頁 narration 拖長整支影片。"""
    if len(text) <= hard_max:
        return text
    window = text[:hard_max]
    last_end = max(
        window.rfind("。"), window.rfind("！"), window.rfind("？"),
        window.rfind("."), window.rfind("!"), window.rfind("?"),
    )
    if last_end >= target - 50:
        return text[: last_end + 1]
    # 沒找到合理句點: 用逗號退而求其次, 補上句點
    cut = text[:target]
    last_comma = max(cut.rfind("，"), cut.rfind(","))
    if last_comma > target - 80:
        return cut[: last_comma] + "。"
    return cut + "。"


def narrate_page_with_gemini(client, page_png: bytes, chapter_title: str,
                              chapter_pages: int, page_in_chapter: int,
                              prev_narration: str, *, brief: bool = False) -> str:
    """單頁 → narration 草稿。Gemini 偶爾會在中文句中提早 STOP 導致句子腰斬,
    結尾若不是句號類符號就 retry 一次, temperature 提高 + prompt 加強完整性要求。"""
    from google.genai import types

    template = NARRATION_PROMPT_BRIEF if brief else NARRATION_PROMPT_DETAILED
    base_prompt = template.format(
        chapter_title=chapter_title,
        chapter_pages=chapter_pages,
        page_in_chapter=page_in_chapter,
        prev_narration=prev_narration or "(這是本章第一張投影片, 沒有前一張)",
    )
    parts = [types.Part.from_bytes(data=page_png, mime_type="image/png")]

    # 三段式 retry:
    #   1. 純 prompt (temp=0.4)
    #   2. 強調必須完整 (temp=0.7)
    #   3. 把 partial 當 context, 要 Gemini「續寫」剩下的句子 (temp=0.5)
    last_text = ""
    for attempt in range(1, 4):
        if attempt == 1:
            prompt = base_prompt
            temp = 0.4
        elif attempt == 2:
            prompt = base_prompt + (
                "\n\n⚠ 請務必輸出**完整**句子, 並以「。」「！」或「？」結尾, "
                "句子不能中途停。寧可再多寫幾個字到完整收尾, 也不要半句話結束。"
            )
            temp = 0.7
        else:
            # 第 3 次: 給 Gemini 上次的 partial, 直接要求補完
            prompt = base_prompt + (
                f"\n\n⚠ 上次你寫到「{last_text}」就斷了, "
                f"請從這裡接續寫完, 直接給完整版的旁白(不是只給後半段, 是整段重寫並以句點結尾)。"
            )
            temp = 0.5

        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=parts + [prompt],
                config=types.GenerateContentConfig(
                    temperature=temp,
                    max_output_tokens=NARRATION_MAX_TOKENS,
                ),
            )
            text = _clean_narration(resp.text)
            if text and text.endswith(_SENTENCE_END):
                if attempt > 1:
                    print(f"   ↺ retry 成功 (attempt={attempt}, temp={temp})")
                return text
            if text and len(text) > len(last_text):  # 用較長的當 partial
                last_text = text
            if attempt == 1 and text:
                print(f"   ⚠ narration 結尾未完整(「{text[-8:]}」), 進入 retry")
        except Exception as e:
            print(f"   ⚠ 第 {attempt} 次 narration 生成失敗: {e}")

    # 三次都不完整: 回傳最長的一版, 標記人工補完
    return (last_text + " [需人工補完整句]") if last_text else "(此頁旁白生成失敗)"


def build_problems(stem: str, chapters: list[dict], page_paths: list[Path],
                   narrations: list[str]) -> list[dict]:
    """章節 + 每頁 narration → v1 exam.json 的 problems 結構 (Track A 用)。
    每段 narration 進來前先 _truncate_at_sentence 兜底,避免單頁拖長影片。"""
    problems = []
    for ci, ch in enumerate(chapters):
        s, e = ch["start_page"], ch["end_page"]
        steps = []
        for p in range(s, e + 1):
            png_rel = page_paths[p - 1].relative_to(BASE_DIR).as_posix()
            narration = _truncate_at_sentence(narrations[p - 1])
            steps.append({
                "display": f"投影片 {p}",
                "narration": narration,
                "bg_type": "slide",
                "bg_image": png_rel,
                "layout": "full",
            })
        problems.append({
            "id": f"ch{ci+1}",
            "number": f"第 {ci+1} 章 {ch['title']}",
            "score": 0,
            "problem": ch["title"],
            "steps": steps,
        })
    return problems


def build_deck_sections(stem: str, chapters: list[dict], page_paths: list[Path],
                        narrations: list[str]) -> list[dict]:
    """章節 + 每頁 narration → 新 deck schema 的 sections 結構 (Track B / PR-3h 用)。

    對應規則:
    - chapter → section (id="ch{N}", title=chapter.title)
    - 每頁 → slide (id="ch{N}_p{P}", title="投影片 N", bg_image, narration)
    - bullets / code_snippet 留空 (簡報講解不需要這些, 渲染走 SlideRenderer)
    - layout 預設 "full"; 未來 Phase 4 split-left 出來時可由 React UI 改

    React UI 看到這 schema 會走 deck 路徑 (sections/slides), SlideEditor 多帶
    bg_image 顯示縮圖。
    """
    sections = []
    for ci, ch in enumerate(chapters):
        s, e = ch["start_page"], ch["end_page"]
        sec_id = f"ch{ci+1}"
        slides = []
        for p in range(s, e + 1):
            png_rel = page_paths[p - 1].relative_to(BASE_DIR).as_posix()
            narration = _truncate_at_sentence(narrations[p - 1])
            slides.append({
                "id": f"{sec_id}_p{p:03d}",
                "title": f"投影片 {p}",
                "bullets": [],
                "code_snippet": None,
                "code_lang": None,
                "file_path": None,
                "narration": narration,
                "notes": None,
                # 簡報專屬欄位 (deck schema 擴充, render 階段被 deck_to_exam_schema_slides 讀)
                "bg_image": png_rel,
                "bg_type": "slide",
                "layout": "full",
            })
        sections.append({
            "id": sec_id,
            "title": ch["title"],
            "slides": slides,
        })
    return sections


def ingest(pdf_path: Path, out_json: Path, *,
           mock: bool, single: bool, brief: bool, as_deck: bool = False):
    """簡報 PDF → JSON (預設 v1 exam schema, as_deck=True 改 deck schema)。

    PR-3h 加 as_deck 旗標:
    - False (預設, Track A CLI): 出 v1 exam (problems/steps), bg_image 在 step 上
    - True (Track B server runner): 出 deck (sections/slides), bg_image 在 slide 上
    兩條共用 PDF→PNG / 章節切分 / Gemini narration 三個慢階段, 只差最後組裝。
    """
    _ensure_dirs()
    stem = pdf_path.stem
    slide_dir = SLIDES_ROOT / stem

    print(f"[ingest] 渲染 PDF → PNG (DPI={SLIDE_DPI}) ...")
    page_paths = render_pdf_pages(pdf_path, slide_dir)
    total = len(page_paths)
    print(f"[ingest] {total} 頁已存到 {slide_dir.relative_to(BASE_DIR)}")

    # 章節切分: ≤ 12 頁直接單章 (對應一支 12~15 分鐘影片), 因為再切就太碎
    if mock or single or total <= 12:
        if total <= 12 and not single:
            print(f"[ingest] 頁數 ≤ 12, 跳過章節切分 (單章模式)")
        chapters = [{"title": "全部內容", "start_page": 1, "end_page": total}]
    else:
        print(f"[ingest] Pass 1: 章節切分 ...")
        thumbs = render_thumbs(pdf_path)
        chapters = detect_chapters_with_gemini(thumbs, total)
        print(f"[ingest] 切成 {len(chapters)} 章:")
        for c in chapters:
            print(f"   ch: p.{c['start_page']:>3}~{c['end_page']:>3}  {c['title']}")

    style_label = "簡短" if brief else "詳盡"
    print(f"\n[ingest] Pass 2: 逐頁產 narration (mock={mock}, 風格={style_label}) ...")
    narrations: list[str] = [""] * total

    if mock:
        for i in range(total):
            narrations[i] = f"(投影片 {i+1} 佔位旁白, 請至 Web UI 編輯)"
    else:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("缺少 GEMINI_API_KEY 環境變數")
        client = genai.Client(api_key=api_key)

        for ch in chapters:
            s, e = ch["start_page"], ch["end_page"]
            chapter_pages = e - s + 1
            prev = ""
            for offset, p in enumerate(range(s, e + 1), start=1):
                print(f"   -> p{p:03d}/{total} ({ch['title']}, 章內 {offset}/{chapter_pages})")
                png_bytes = page_paths[p - 1].read_bytes()
                text = narrate_page_with_gemini(
                    client, png_bytes, ch["title"], chapter_pages, offset, prev,
                    brief=brief,
                )
                narrations[p - 1] = text
                prev = text

    # 組裝 — 依 as_deck 旗標決定 schema
    if as_deck:
        sections = build_deck_sections(stem, chapters, page_paths, narrations)
        deck_data = {
            "deck_title": f"{stem} 講解",
            "source_type": "slides",
            "source_meta": {"pdf_path": str(pdf_path), "total_pages": total},
            "sections": sections,
        }
        output_data = deck_data
        unit_count = sum(len(s["slides"]) for s in sections)
        print_label = f"{len(sections)} 章 / {unit_count} 張投影片 (deck schema)"
    else:
        problems = build_problems(stem, chapters, page_paths, narrations)
        exam_data = {
            "exam_title": f"{stem} 講解",
            "source_type": "slides",
            "problems": problems,
        }
        output_data = exam_data
        print_label = f"{len(problems)} 章 / {total} 張投影片 (v1 exam schema)"

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # resolve() 確保比 BASE_DIR 時兩邊都是 absolute, 否則 relative path 會 ValueError
    out_resolved = out_json.resolve()
    try:
        display_path = out_resolved.relative_to(BASE_DIR)
    except ValueError:
        # 輸出在 repo 外的情境就直接顯示 absolute (例如使用者用 D:\... 指其他位置)
        display_path = out_resolved
    print(f"\n✅ 完成: {display_path}")
    print(f"   {print_label}")


def main():
    from core.runtime import setup_utf8_stdout
    setup_utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="簡報 PDF 路徑")
    ap.add_argument("output", nargs="?", help="輸出 JSON 路徑 (預設 exams/<stem>.json)")
    ap.add_argument("--mock", action="store_true", help="不呼叫 Gemini, 用佔位 narration")
    ap.add_argument("--single", action="store_true", help="強制單一章節, 跳過切分階段")
    ap.add_argument("--brief", action="store_true",
                    help="簡短風格 (50~120 字/頁), 預設是詳盡風格 (200~300 字/頁, 適合 ~15 分鐘影片)")
    ap.add_argument("--force", action="store_true", help="覆蓋既有 JSON (預設不覆蓋, 防呆)")
    ap.add_argument("--deck-schema", action="store_true",
                    help="輸出新 deck schema (sections/slides), 預設 v1 exam (problems/steps)。"
                         "Track B server / React UI 用; Track A Flask 仍走 v1 schema。")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        sys.exit(f"❌ 找不到 PDF: {pdf_path}")

    out_json = Path(args.output) if args.output else (EXAMS_ROOT / f"{pdf_path.stem}.json")
    if out_json.exists() and not args.force:
        sys.exit(
            f"❌ 已存在: {out_json}\n"
            f"   為避免覆蓋(可能是 solve.py 產的考卷 JSON), 預設不覆蓋。\n"
            f"   要覆蓋請加 --force, 或用第二參數指定其他輸出路徑。"
        )
    ingest(pdf_path, out_json, mock=args.mock, single=args.single, brief=args.brief,
           as_deck=args.deck_schema)


if __name__ == "__main__":
    main()
