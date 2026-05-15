"""Document adapter — PDF / Markdown / TXT 文件 → 統一 raw_content。

跟 repo adapter 不同的地方:
- 沒有檔樹概念, 整份文件就是一段 long-form text
- 沒有 key_files 列表, scriptor 直接看整份內容
- PDF 走 fitz 抽純文字 (跟 slide_ingest 不同, slide_ingest 是 page→image,
  我們這裡是 page→text), 因為 document 通常是 running text 不是投影片頁

iter 51: 加 PDF figure 抽取 (extract_pdf_figures). 純文字 scan_document 不變,
figure 抽取單獨函式, runner 自己決定要不要 call.

raw_content schema:
{
  "source_kind": "document",
  "title": "filename without ext (or LLM-detected)",
  "format": "pdf" | "md" | "txt",
  "content": "...",
  "primary_language": "zh-tw",   # 預設, 後續可加偵測
  "stats": {"chars": int, "pages": int | null, "truncated": bool},
  "figures": [...]   # iter 51: PDF 圖列表, runner 補進來; md/txt 無
}
"""
from __future__ import annotations

from pathlib import Path


# 單檔最大字元數 (LLM token budget 緩衝). Gemini 2.5 Flash 1M context 容得下,
# 但 outliner / scriptor 把它整段塞進 prompt 還會跟 prompt 本體競爭, 所以保守。
DEFAULT_MAX_CHARS = 80_000


SUPPORTED_SUFFIXES = {".pdf", ".md", ".markdown", ".txt"}


def scan_document(
    doc_path: Path,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict:
    """掃單一文件檔, 抽純文字回傳 raw_content。

    支援 .pdf / .md / .markdown / .txt — 其他副檔名 raise ValueError。
    超過 max_chars 會 truncate 並在 stats.truncated 標記。
    """
    doc_path = doc_path.resolve()
    if not doc_path.is_file():
        raise FileNotFoundError(f"document 不存在或不是檔案: {doc_path}")

    suffix = doc_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"不支援的副檔名: {suffix} (只接受 {sorted(SUPPORTED_SUFFIXES)})"
        )

    if suffix == ".pdf":
        text, pages = _extract_pdf(doc_path)
        fmt = "pdf"
    else:
        text = _extract_text(doc_path)
        pages = None
        fmt = "md" if suffix in (".md", ".markdown") else "txt"

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return {
        "source_kind": "document",
        "title": doc_path.stem,
        "format": fmt,
        "content": text,
        "primary_language": "zh-tw",  # PR-3b 先寫死, 之後可加 langdetect
        "stats": {
            "chars": len(text),
            "pages": pages,
            "truncated": truncated,
        },
    }


def _extract_pdf(path: Path) -> tuple[str, int]:
    """PyMuPDF 抽 PDF 純文字 (page break 用 \\n\\n)。"""
    import fitz

    doc = fitz.open(path)
    parts = []
    try:
        for i, page in enumerate(doc):
            page_text = page.get_text() or ""
            if page_text.strip():
                parts.append(page_text.strip())
        return ("\n\n".join(parts), len(doc))
    finally:
        doc.close()


# ---------- iter 51: PDF figure 抽取 ----------

# 太小的當 icon / decorative element 跳過 (eg. 公司 logo, 列表 bullet 圖)
DEFAULT_MIN_FIGURE_SIZE = 100

# 圖太多 (eg. 80 頁論文每頁 5 張圖) 會炸 deck, 限上限給 LLM 看
DEFAULT_MAX_FIGURES = 30


def extract_pdf_figures(
    pdf_path: Path,
    out_dir: Path,
    *,
    min_width: int = DEFAULT_MIN_FIGURE_SIZE,
    min_height: int = DEFAULT_MIN_FIGURE_SIZE,
    max_figures: int = DEFAULT_MAX_FIGURES,
) -> list[dict]:
    """抽 PDF 內嵌圖到 out_dir/, 回傳 figure metadata list (iter 51).

    PyMuPDF page.get_images() 列每頁影像 xref, doc.extract_image(xref) 取 raw bytes.
    對每張圖嘗試找 caption (該頁緊接圖位置下方的第一段文字, "圖 N: ..." 或
    "Figure N: ..." 開頭). caption_hint 給 scriptor 配圖用, 抓不到不致命.

    參數:
        pdf_path: 來源 PDF
        out_dir: 圖存放目錄 (會自動 mkdir, 通常 = jobs/<id>/figures/)
        min_width / min_height: 過濾掉小於這尺寸的圖 (icon / decoration)
        max_figures: 全 PDF 累積上限 (預設 30, 避免巨大論文炸 deck)

    回傳 figure dict list:
        {
          "id": "fig_p3_1",            # 唯一 id (頁碼 + 該頁第幾張)
          "page_no": 3,                 # 1-based
          "path": "fig_p3_1.png",      # 相對 out_dir 的檔名
          "width": 800,
          "height": 600,
          "caption_hint": "圖 3: 系統架構",  # 該圖下方第一段文字 (best effort)
        }

    沒抽到任何圖回 []. 失敗的單張圖 print warning 但不擋整批.
    """
    import fitz

    out_dir.mkdir(parents=True, exist_ok=True)
    figures: list[dict] = []

    doc = fitz.open(pdf_path)
    try:
        for page_idx, page in enumerate(doc):
            page_no = page_idx + 1
            try:
                img_list = page.get_images(full=True)
            except Exception as e:
                print(f"[figure-extract] page {page_no} get_images 失敗: {e}")
                continue

            seq = 0
            for img_info in img_list:
                if len(figures) >= max_figures:
                    break
                xref = img_info[0]
                try:
                    img_dict = doc.extract_image(xref)
                except Exception as e:
                    print(f"[figure-extract] xref {xref} extract 失敗: {e}")
                    continue

                w = img_dict.get("width", 0)
                h = img_dict.get("height", 0)
                if w < min_width or h < min_height:
                    continue   # 小圖 skip

                ext = img_dict.get("ext", "png")
                seq += 1
                fig_id = f"fig_p{page_no}_{seq}"
                fname = f"{fig_id}.{ext}"
                fpath = out_dir / fname
                try:
                    fpath.write_bytes(img_dict["image"])
                except Exception as e:
                    print(f"[figure-extract] 寫 {fname} 失敗: {e}")
                    continue

                caption = _find_caption_hint(page, xref)

                figures.append({
                    "id": fig_id,
                    "page_no": page_no,
                    "path": fname,
                    "width": w,
                    "height": h,
                    "caption_hint": caption or "",
                })

            if len(figures) >= max_figures:
                break
    finally:
        doc.close()

    return figures


def _find_caption_hint(page, xref: int) -> str | None:
    """heuristic 找該圖的 caption — 圖 bbox 下方第一段以「圖 / Figure / Fig.」開頭的文字.

    PyMuPDF page.get_image_rects(xref) 給圖的 bbox, page.get_text("blocks") 給
    文字 block 列表. 找 block.y0 > image.y1 且最靠近的 block, 文字以
    "圖 N" / "Figure N" / "Fig." 開頭就拿來當 caption.

    抓不到回 None — caller 用空字串 fallback.
    """
    import re

    try:
        rects = page.get_image_rects(xref)
        if not rects:
            return None
        img_rect = rects[0]   # 第一個 instance
        img_bottom = img_rect.y1

        blocks = page.get_text("blocks") or []
        # blocks 格式: (x0, y0, x1, y1, text, block_no, block_type)
        candidates = []
        for b in blocks:
            if len(b) < 5:
                continue
            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
            if y0 < img_bottom:
                continue
            txt = (text or "").strip()
            if not txt:
                continue
            # 必須以圖標記開頭才算 caption (避免抓到下段正文)
            if re.match(r"^(圖|Figure|Fig\.?)\s*\d+", txt, re.IGNORECASE):
                candidates.append((y0 - img_bottom, txt))

        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])    # 最靠近圖底的
        # 只取 caption 第一行 (避免吞下整段內文)
        return candidates[0][1].splitlines()[0][:200]
    except Exception:
        return None


def _extract_text(path: Path) -> str:
    """讀 .md / .txt, 嘗試 utf-8, 退到 utf-8 surrogateescape。"""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


# ---------- CLI ----------

if __name__ == "__main__":
    import argparse
    import json
    import sys

    from core.runtime import setup_utf8_stdout
    setup_utf8_stdout()

    ap = argparse.ArgumentParser(description="Document adapter 自我測試")
    ap.add_argument("path", help="PDF / MD / TXT 路徑")
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    raw = scan_document(Path(args.path), max_chars=args.max_chars)
    print(f"source_kind: {raw['source_kind']}")
    print(f"title: {raw['title']}")
    print(f"format: {raw['format']}")
    print(f"stats: {raw['stats']}")
    sys.stdout.buffer.write(b"--- first 300 chars ---\n")
    sys.stdout.buffer.write(raw["content"][:300].encode("utf-8") + b"\n")

    if args.out:
        Path(args.out).write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n寫到 {args.out}")
