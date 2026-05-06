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

# Windows 終端強制 UTF-8 (沿用 solve.py 慣例)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import fitz  # pymupdf

# 共用 solve.py 的 LaTeX 後處理 (簡報旁白若混入 LaTeX 也要清掉)
from solve import strip_latex, clean_json_escapes

BASE_DIR = Path(__file__).parent
SLIDES_ROOT = BASE_DIR / "slides"
EXAMS_ROOT = BASE_DIR / "exams"

MODEL = "gemini-2.5-flash"
SLIDE_DPI = 200          # 1920px 寬左右 (16:9 投影片)
THUMB_WIDTH = 640        # 章節切分用縮圖, 省 token
NARRATION_MAX_TOKENS = 2048


# 章節切分 prompt
CHAPTER_PROMPT = """你看到的是一份簡報的全部投影片縮圖, 順序由 page 1 開始。
請分析整體結構, 把投影片切成「邏輯章節」, 用於後續錄製講解影片時的分段。

切分原則:
1. **以章節標題頁為界線** — 通常有大字標題、留白多、不含密集內文
2. **議題轉換點也算章節邊界** — 即使沒有標題頁, 主題明顯切換就切
3. **每章 3~15 頁** — 太短就合併, 太長就再切
4. **總頁數 ≤ 8 頁時不要切**, 直接回單一章節
5. **章節標題用簡報中的實際標題**, 找不到就用該章主題的 4~12 字摘要

==== 輸出格式 (嚴格) ====
直接輸出 JSON array, 不要 Markdown 標記, 不要說明文字:

[
  {"title": "章節標題", "start_page": 1, "end_page": 5},
  {"title": "...", "start_page": 6, "end_page": 14}
]

start_page / end_page 為 1-indexed inclusive。第一章 start_page 必為 1, 最後一章 end_page 必為總頁數, 章節間頁碼連續不重疊。
"""

# 單頁 narration prompt
NARRATION_PROMPT_TEMPLATE = """你正在替一份簡報的單張投影片撰寫教師講解旁白, 用於黑板風格的解說影片。

==== 章節背景 ====
本投影片屬於「{chapter_title}」章節 (本章共 {chapter_pages} 頁, 此為第 {page_in_chapter} 頁)。

==== 上一張投影片的旁白 (僅供銜接參考, 不要重複) ====
{prev_narration}

==== 本張投影片內容 ====
請看圖。

==== 撰寫要求 ====
1. 以「劉老師」第一人稱口吻, 自然口語, 像在課堂上對學生說話
2. 50~120 字之間 (中文字數)
3. 開頭可用「接下來我們看…」「這張投影片要說明…」等銜接語, 但不要每張都用同一句
4. 解釋圖中的重點概念、公式、流程圖, 不要只朗讀標題
5. 末尾用句點「。」結束
6. **不要使用 LaTeX 標記** (例如 $x^2$ 一律寫成 x 的平方; 不要寫 \\frac, \\sqrt 等)
7. **不要 Markdown 標記** (** _ # 等)
8. 純中文 + 必要的英文術語/數值, 沒有任何符號標記

==== 輸出格式 ====
直接輸出旁白內容, 不要前言「以下是旁白:」、不要引號、不要分段, 一段純文字。
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
        sys.exit("❌ 缺少 GEMINI_API_KEY 環境變數")
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


def _clean_narration(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"^[「『\"']", "", text)
    text = re.sub(r"[」』\"']$", "", text)
    return strip_latex(text)


def narrate_page_with_gemini(client, page_png: bytes, chapter_title: str,
                              chapter_pages: int, page_in_chapter: int,
                              prev_narration: str) -> str:
    """單頁 → narration 草稿。Gemini 偶爾會在中文句中提早 STOP 導致句子腰斬,
    結尾若不是句號類符號就 retry 一次, temperature 提高 + prompt 加強完整性要求。"""
    from google.genai import types

    base_prompt = NARRATION_PROMPT_TEMPLATE.format(
        chapter_title=chapter_title,
        chapter_pages=chapter_pages,
        page_in_chapter=page_in_chapter,
        prev_narration=prev_narration or "(這是本章第一張投影片, 沒有前一張)",
    )
    parts = [types.Part.from_bytes(data=page_png, mime_type="image/png")]

    last_text = ""
    for attempt, temp in enumerate([0.4, 0.7], start=1):
        prompt = base_prompt if attempt == 1 else (
            base_prompt
            + "\n\n⚠ 上次輸出結尾沒有句點, 看起來被截斷。請務必輸出**完整**句子, "
              "並以「。」「！」或「？」結尾, 不要中途停。"
        )
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
                    print(f"   ↺ retry 成功 (temp={temp})")
                return text
            last_text = text or last_text
            if attempt == 1 and text:
                print(f"   ⚠ narration 結尾未完整(「{text[-8:]}」), 進入 retry")
        except Exception as e:
            print(f"   ⚠ 第 {attempt} 次 narration 生成失敗: {e}")

    # 兩次都不完整: 回傳最後一次內容(總比沒有好), 在後面標個記號
    return (last_text + " [需人工補完整句]") if last_text else "(此頁旁白生成失敗)"


def build_problems(stem: str, chapters: list[dict], page_paths: list[Path],
                   narrations: list[str]) -> list[dict]:
    """章節 + 每頁 narration → exam.json 的 problems 結構。"""
    problems = []
    for ci, ch in enumerate(chapters):
        s, e = ch["start_page"], ch["end_page"]
        steps = []
        for p in range(s, e + 1):
            png_rel = page_paths[p - 1].relative_to(BASE_DIR).as_posix()
            steps.append({
                "display": f"投影片 {p}",
                "narration": narrations[p - 1],
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


def ingest(pdf_path: Path, out_json: Path, *, mock: bool, single: bool):
    _ensure_dirs()
    stem = pdf_path.stem
    slide_dir = SLIDES_ROOT / stem

    print(f"[ingest] 渲染 PDF → PNG (DPI={SLIDE_DPI}) ...")
    page_paths = render_pdf_pages(pdf_path, slide_dir)
    total = len(page_paths)
    print(f"[ingest] {total} 頁已存到 {slide_dir.relative_to(BASE_DIR)}")

    # 章節切分
    if mock or single or total <= 8:
        if total <= 8 and not single:
            print(f"[ingest] 頁數 ≤ 8, 跳過章節切分 (單章模式)")
        chapters = [{"title": "全部內容", "start_page": 1, "end_page": total}]
    else:
        print(f"[ingest] Pass 1: 章節切分 ...")
        thumbs = render_thumbs(pdf_path)
        chapters = detect_chapters_with_gemini(thumbs, total)
        print(f"[ingest] 切成 {len(chapters)} 章:")
        for c in chapters:
            print(f"   ch: p.{c['start_page']:>3}~{c['end_page']:>3}  {c['title']}")

    # narration 生成
    print(f"\n[ingest] Pass 2: 逐頁產 narration (mock={mock}) ...")
    narrations: list[str] = [""] * total

    if mock:
        for i in range(total):
            narrations[i] = f"(投影片 {i+1} 佔位旁白, 請至 Web UI 編輯)"
    else:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            sys.exit("❌ 缺少 GEMINI_API_KEY 環境變數")
        client = genai.Client(api_key=api_key)

        for ch in chapters:
            s, e = ch["start_page"], ch["end_page"]
            chapter_pages = e - s + 1
            prev = ""
            for offset, p in enumerate(range(s, e + 1), start=1):
                print(f"   -> p{p:03d}/{total} ({ch['title']}, 章內 {offset}/{chapter_pages})")
                png_bytes = page_paths[p - 1].read_bytes()
                text = narrate_page_with_gemini(
                    client, png_bytes, ch["title"], chapter_pages, offset, prev
                )
                narrations[p - 1] = text
                prev = text

    # 組裝
    problems = build_problems(stem, chapters, page_paths, narrations)
    exam_data = {
        "exam_title": f"{stem} 講解",
        "source_type": "slides",
        "problems": problems,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(exam_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n✅ 完成: {out_json.relative_to(BASE_DIR)}")
    print(f"   {len(problems)} 章 / {total} 張投影片")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="簡報 PDF 路徑")
    ap.add_argument("output", nargs="?", help="輸出 JSON 路徑 (預設 exams/<stem>.json)")
    ap.add_argument("--mock", action="store_true", help="不呼叫 Gemini, 用佔位 narration")
    ap.add_argument("--single", action="store_true", help="強制單一章節, 跳過切分階段")
    ap.add_argument("--force", action="store_true", help="覆蓋既有 JSON (預設不覆蓋, 防呆)")
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
    ingest(pdf_path, out_json, mock=args.mock, single=args.single)


if __name__ == "__main__":
    main()
