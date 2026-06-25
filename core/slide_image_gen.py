"""core/slide_image_gen.py — 缺圖簡報逐頁補圖 (eduStudio Visual track 延伸)。

定位
----
slides_pdf 走 slide_ingest.py 後, 每頁 = 一個 deck slide, slide.bg_image 指向原始
投影片 PNG。但很多簡報是「純文字、缺配圖」的。這個模組:

  1. 偵測 PDF 哪些頁是「純文字、缺圖」(detect_imageless_pages, 用 PyMuPDF 看每頁
     的嵌入點陣圖覆蓋率 + 向量圖數量)。
  2. 依該頁的標題 / 旁白, 用 Gemini 生一張符合內容的配圖 (generate_slide_image,
     複用 core.diagram_image_gen 的 Gemini 2.5 Flash Image)。
  3. 把「原頁 + 配圖」合成一張新頁 (compose_augmented_page, 左原頁右配圖), 寫回
     slide.bg_image — render 階段 (SlideRenderer) 與未來 PPTX 匯出都直接吃這張新頁,
     不需要改 render。

設計重點
--------
- AI 生圖是估值 → 一律標 slide.reviewed=False (硬規則 #1: AI 產出停人工 review)。
  原頁路徑保留在 slide.source_bg_image, 方便 review 時對照 / 一鍵還原。
- mock=True 走 PIL 佔位圖, 不打 Gemini / 不需網路, 給 CI / smoke test。
- 失敗容錯: 單頁生圖失敗只 log warning skip 該頁, 不擋整份 deck。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# slide id 形如 "ch1_p001" — 末段 p{NNN} 為 1-based PDF 頁碼
_PAGE_RE = re.compile(r"_p(\d+)$")


def _slide_page_no(slide: dict) -> int | None:
    """從 slide id (ch1_p007) 解析 1-based PDF 頁碼; 解析不到回 None。"""
    sid = slide.get("id") or ""
    m = _PAGE_RE.search(sid)
    return int(m.group(1)) if m else None


def detect_imageless_pages(
    pdf_path: str | Path,
    *,
    image_coverage_threshold: float = 0.04,
    min_vector_paths: int = 12,
) -> list[int]:
    """回傳「純文字、缺圖」的 1-based 頁碼清單。

    一頁被視為「有圖」若任一成立:
      - 嵌入點陣圖 (raster) 覆蓋率 ≥ image_coverage_threshold (預設 4% 頁面積), 或
      - 向量繪圖路徑數 ≥ min_vector_paths (預設 12, 概估有流程圖 / 架構圖)。
    否則視為缺圖 (純文字 / 只有少量表格框線)。

    用 PyMuPDF (fitz)。讀不到 / 壞檔 raise; 個別頁解析失敗當作「有圖」(保守不補)。
    """
    import fitz

    pdf_path = Path(pdf_path)
    imageless: list[int] = []
    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc, start=1):
            try:
                page_area = abs(page.rect.width * page.rect.height) or 1.0

                # 1) 點陣圖覆蓋率
                raster_area = 0.0
                for img in page.get_images(full=True):
                    xref = img[0]
                    for rect in page.get_image_rects(xref):
                        raster_area += abs(rect.width * rect.height)
                coverage = raster_area / page_area

                # 2) 向量繪圖路徑 (流程圖 / 框圖常見)
                try:
                    n_vectors = len(page.get_drawings())
                except Exception:
                    n_vectors = 0

                has_image = coverage >= image_coverage_threshold or n_vectors >= min_vector_paths
                if not has_image:
                    imageless.append(i)
            except Exception as e:  # noqa: BLE001 — 單頁解析失敗保守當作有圖
                logger.warning("第 %d 頁缺圖偵測失敗, 視為有圖跳過: %s", i, e)
    finally:
        doc.close()
    return imageless


def _slide_to_section(slide: dict, deck_title: str = "") -> dict:
    """把 deck slide 轉成 diagram_image_gen 期望的 section dict (title/intent/topics)。

    簡報頁沒有 outline 的 intent/topics, 改用 title + 旁白前段當概念描述, 讓生圖
    prompt 抓得到這頁要表達什麼。
    """
    title = (slide.get("title") or "").strip()
    narration = (slide.get("narration") or "").strip()
    # 旁白第一句當 intent (生圖 prompt 的 concept focus)
    intent = re.split(r"[。!?\n]", narration, maxsplit=1)[0][:160] if narration else ""
    return {
        "id": slide.get("id") or "slide",
        "title": title or "投影片",
        "intent": intent,
        "topics": [],
    }


def _write_placeholder_image(out_path: Path, *, size: int = 1024, label: str = "AI") -> None:
    """mock / fallback: 寫一張 PIL 佔位 PNG (不打 Gemini)。"""
    from PIL import Image, ImageDraw

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (size, size), (236, 240, 233))
    d = ImageDraw.Draw(img)
    d.rectangle([8, 8, size - 8, size - 8], outline=(120, 140, 120), width=4)
    d.text((size // 2 - 40, size // 2 - 8), f"[{label}]", fill=(90, 110, 90))
    img.save(out_path)


def generate_slide_image(
    slide: dict,
    out_path: Path,
    *,
    deck_title: str = "",
    api_key: str | None = None,
    mock: bool = False,
) -> tuple[bool, str]:
    """為單一 slide 生一張配圖, 寫到 out_path。回傳 (success, error_msg)。

    mock=True → 寫 PIL 佔位圖 (success=True)。否則複用 diagram_image_gen 打 Gemini。
    """
    if mock:
        _write_placeholder_image(out_path, label=slide.get("id") or "AI")
        return (True, "")

    from core.diagram_image_gen import generate_section_diagram_image

    section = _slide_to_section(slide, deck_title=deck_title)
    return generate_section_diagram_image(
        section, out_path, deck_title=deck_title, api_key=api_key,
    )


def compose_augmented_page(
    original_png: str | Path,
    ai_png: str | Path,
    out_path: Path,
    *,
    width: int = 1920,
    height: int = 1080,
    bg_color: tuple[int, int, int] = (255, 255, 255),
) -> Path:
    """把原頁 + AI 配圖合成一張新頁: 左半原頁, 右半配圖 (各自等比 letterbox-fit)。

    產出 width×height 的 PNG → 直接給 SlideRenderer (letterbox-fit 進影格) 或未來
    PPTX 匯出用。原頁讀不到時, 整張用配圖填滿 (仍是有效的新頁)。
    """
    from PIL import Image

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (width, height), bg_color)
    pad = 24
    half_w = width // 2

    def _fit_into(img_path: str | Path, box_x: int, box_w: int) -> None:
        try:
            im = Image.open(img_path).convert("RGB")
        except Exception as e:  # noqa: BLE001
            logger.warning("合成頁讀圖失敗 %s: %s", img_path, e)
            return
        avail_w = box_w - 2 * pad
        avail_h = height - 2 * pad
        scale = min(avail_w / im.width, avail_h / im.height)
        sw, sh = max(1, int(im.width * scale)), max(1, int(im.height * scale))
        im = im.resize((sw, sh), Image.LANCZOS)
        x = box_x + (box_w - sw) // 2
        y = (height - sh) // 2
        canvas.paste(im, (x, y))

    original_exists = Path(original_png).exists()
    if original_exists:
        _fit_into(original_png, 0, half_w)
        _fit_into(ai_png, half_w, width - half_w)
    else:
        # 沒有原頁就讓配圖佔滿整張
        _fit_into(ai_png, 0, width)

    canvas.save(out_path)
    return out_path


def augment_deck_with_images(
    deck: dict,
    *,
    figures_dir: Path,
    pdf_path: str | Path | None = None,
    only_missing: bool = True,
    api_key: str | None = None,
    mock: bool = False,
    max_images: int | None = None,
    asset_base: Path | None = None,
) -> dict:
    """為 deck 中「缺圖」的 slide 逐頁生 AI 配圖並合成新頁。原地修改並回傳 deck。

    Args:
        deck: slides ingest 出的 deck (sections/slides, slide 有 bg_image)。
        figures_dir: 生成圖 / 合成頁的輸出目錄 (通常 jobs/<id>/figures)。
        pdf_path: 原始 PDF; only_missing=True 時用來偵測哪些頁缺圖。None 則退化成
                  對「沒有 bg_image 的 slide」補圖。
        only_missing: True 只補缺圖頁; False 對每頁都生圖。
        mock: True 走 PIL 佔位圖 (不打 Gemini)。
        max_images: 生圖上限 (省 API 額度); None = 不限。
        asset_base: 解析 slide.bg_image 相對路徑的基底 (預設 core.config.PROJECT_ROOT)。

    回傳的 deck 中, 被補圖的 slide 會多 / 改這些欄位:
        bg_image          → 合成後的新頁 (相對 figures_dir 之上層, 見下)
        source_bg_image   → 原頁路徑 (保留, 供 review 對照 / 還原)
        ai_image          → 原始 AI 生圖路徑
        image_generated   → True
        reviewed          → False (AI 估值, 停 review)
    並在 deck["image_augmentation"] 記一筆 summary。
    """
    from core import config

    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)
    base = Path(asset_base) if asset_base else Path(config.PROJECT_ROOT)
    deck_title = deck.get("deck_title", "")

    # 決定要補圖的頁碼集合
    target_pages: set[int] | None = None
    if only_missing and pdf_path is not None:
        target_pages = set(detect_imageless_pages(pdf_path))
        logger.info("偵測到 %d 個缺圖頁: %s", len(target_pages), sorted(target_pages))

    generated = 0
    skipped: list[str] = []
    for section in deck.get("sections", []):
        for slide in section.get("slides", []):
            if max_images is not None and generated >= max_images:
                break

            page_no = _slide_page_no(slide)
            if only_missing:
                if target_pages is not None:
                    if page_no is None or page_no not in target_pages:
                        continue
                else:
                    # 無 pdf: 退化成「沒有 bg_image 才補」
                    if slide.get("bg_image"):
                        continue

            sid = slide.get("id") or f"slide{generated}"
            safe_id = "".join(c for c in sid if c.isalnum() or c == "_")[:48] or f"slide{generated}"
            ai_path = figures_dir / f"ai_{safe_id}.png"

            ok, err = generate_slide_image(
                slide, ai_path, deck_title=deck_title, api_key=api_key, mock=mock,
            )
            if not ok:
                logger.warning("slide %s 生圖跳過: %s", sid, err)
                skipped.append(sid)
                continue

            # 合成新頁 (原頁在左, AI 圖在右)
            orig_rel = slide.get("bg_image")
            orig_abs = (base / orig_rel) if orig_rel else figures_dir / "__none__"
            aug_path = figures_dir / f"aug_{safe_id}.png"
            compose_augmented_page(orig_abs, ai_path, aug_path)

            # 回填 slide 欄位 — bg_image 改指合成頁 (相對 PROJECT_ROOT, 與原 schema 對齊)
            slide["source_bg_image"] = orig_rel
            slide["ai_image"] = ai_path.relative_to(base).as_posix() if _under(ai_path, base) else str(ai_path)
            slide["bg_image"] = aug_path.relative_to(base).as_posix() if _under(aug_path, base) else str(aug_path)
            slide["image_generated"] = True
            slide["reviewed"] = False
            generated += 1

    deck["image_augmentation"] = {
        "generated": generated,
        "skipped": skipped,
        "only_missing": only_missing,
        "mock": mock,
    }
    logger.info("簡報補圖完成: 生 %d 張, 跳過 %d 張", generated, len(skipped))
    return deck


def _under(path: Path, base: Path) -> bool:
    """path 是否在 base 子樹下 (避免 relative_to 丟例外)。"""
    try:
        path.resolve().relative_to(Path(base).resolve())
        return True
    except ValueError:
        return False
