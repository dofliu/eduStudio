"""Document adapter — PDF / Markdown / TXT 文件 → 統一 raw_content。

跟 repo adapter 不同的地方:
- 沒有檔樹概念, 整份文件就是一段 long-form text
- 沒有 key_files 列表, scriptor 直接看整份內容
- PDF 走 fitz 抽純文字 (跟 slide_ingest 不同, slide_ingest 是 page→image,
  我們這裡是 page→text), 因為 document 通常是 running text 不是投影片頁

raw_content schema:
{
  "source_kind": "document",
  "title": "filename without ext (or LLM-detected)",
  "format": "pdf" | "md" | "txt",
  "content": "...",
  "primary_language": "zh-tw",   # 預設, 後續可加偵測
  "stats": {"chars": int, "pages": int | null, "truncated": bool},
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
