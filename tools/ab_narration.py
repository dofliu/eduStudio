#!/usr/bin/env python3
"""tools/ab_narration.py — C-3 旁白模型 A/B 比對工具（離線寫好、你本機開額度跑）。

為什麼：`slide_ingest.py` 的旁白目前寫死 `gemini-2.5-flash`（將淘汰）。遷到 3.x 前
**旁白品質要先驗**（清單 C-3 = GATE，需開額度）。本工具對**同一份簡報的同幾頁**，用
舊模型（2.5-flash）與候選模型（3.x）各生一次旁白，並排輸出，讓你一眼比品質再決定切不切。

它**只跑旁白生成**（不跑章節切分 / TTS / ffmpeg / 完整 render），所以比「跑兩支完整影片」
省很多額度；且**不改動正式 pipeline 預設**（只是對同一頁注入不同 model 呼叫真實
`narrate_page_with_gemini`，prompt/retry 邏輯與正式線一模一樣，不會 prompt 漂移）。

用法（在**你本機**、設好 `GEMINI_API_KEY`）：

    python tools/ab_narration.py slides.pdf \
        --pages 1,3,5 \
        --models gemini-2.5-flash,gemini-3.5-flash \
        --out ab_narration_report.md

輸出一份 Markdown 並排報告 + 印出各模型的字元用量（粗估成本對照）。決策準則與「驗過怎麼切」
見 docs/C3_NARRATION_AB_PROPOSAL.md。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 預設比對組合：現役（將淘汰）vs M 軸登錄表 text.fast 預設。
DEFAULT_MODELS = ("gemini-2.5-flash", "gemini-3.5-flash")


def parse_pages(spec: str, total: int) -> list[int]:
    """'1,3,5' 或 '1-4' → 1-indexed 頁碼 list（去重排序、夾在 1..total）。"""
    pages: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            for p in range(int(a), int(b) + 1):
                pages.add(p)
        else:
            pages.add(int(chunk))
    return sorted(p for p in pages if 1 <= p <= total)


def narrate_one_page(client, narrate_fn, png: bytes, model: str,
                     *, chapter_title: str = "A/B 比對", chapter_pages: int = 1,
                     page_in_chapter: int = 1, prev: str = "", brief: bool = False) -> str:
    """對單頁、單一 model 生一次旁白（薄包裝，便於注入測試）。"""
    return narrate_fn(
        client, png, chapter_title, chapter_pages, page_in_chapter, prev,
        brief=brief, model=model)


def run_ab(client, narrate_fn, pages: dict[int, bytes], models: list[str],
           *, brief: bool = False) -> list[dict]:
    """對每頁 × 每模型各生一次旁白，回 [{page, model: {text, chars}}]。

    純資料流：client / narrate_fn 都注入 → 測試可餵 fake、不打真 API。
    """
    results: list[dict] = []
    for page_no in sorted(pages):
        png = pages[page_no]
        per_model: dict[str, dict] = {}
        for model in models:
            text = narrate_one_page(client, narrate_fn, png, model,
                                    page_in_chapter=page_no, brief=brief)
            per_model[model] = {"text": text, "chars": len(text or "")}
        results.append({"page": page_no, "models": per_model})
    return results


def render_report(results: list[dict], models: list[str], pdf_name: str) -> str:
    """並排 Markdown 報告。"""
    lines = [
        f"# C-3 旁白 A/B 比對報告 — {pdf_name}",
        "",
        f"比對模型：{' vs '.join(f'`{m}`' for m in models)}",
        "",
        "> 同一頁、同一 prompt/retry 邏輯，只換 model。請逐頁讀兩欄旁白比**正確性 /",
        "> 通順度 / 是否完整收尾 / 講解深度**，再決定是否遷移（見 C3 proposal 決策準則）。",
        "",
    ]
    for row in results:
        lines.append(f"## 第 {row['page']} 頁")
        lines.append("")
        for model in models:
            entry = row["models"].get(model, {})
            text = entry.get("text", "(無)")
            chars = entry.get("chars", 0)
            lines.append(f"### `{model}`（{chars} 字）")
            lines.append("")
            lines.append(text or "(空)")
            lines.append("")
    # 用量小結
    lines.append("## 字元用量小結（粗估成本對照）")
    lines.append("")
    for model in models:
        total = sum(r["models"].get(model, {}).get("chars", 0) for r in results)
        lines.append(f"- `{model}`：輸出共 {total} 字")
    lines.append("")
    lines.append("> 精準單價見 C-2（待對齊官方定價）；此處字元數供相對量級參考。")
    lines.append("")
    return "\n".join(lines)


def _build_client(timeout_ms: int = 120_000):
    """真實 genai client（讀本機 GEMINI_API_KEY）。無 key 直接報錯、不靜默。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit(
            "缺少 GEMINI_API_KEY 環境變數 —— C-3 A/B 需在你本機開額度跑。\n"
            "  export GEMINI_API_KEY=...（別貼進任何會 commit 的檔案）")
    from google import genai
    from google.genai import types
    return genai.Client(api_key=api_key,
                        http_options=types.HttpOptions(timeout=timeout_ms))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C-3 旁白模型 A/B 比對")
    ap.add_argument("pdf", type=Path, help="簡報 PDF")
    ap.add_argument("--pages", default="1,2,3", help="頁碼 '1,3,5' 或 '1-4'（1-indexed）")
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS),
                    help=f"逗號分隔模型 id（預設 {','.join(DEFAULT_MODELS)}）")
    ap.add_argument("--brief", action="store_true", help="用簡短旁白模式")
    ap.add_argument("--out", type=Path, default=Path("ab_narration_report.md"))
    args = ap.parse_args(argv)

    if not args.pdf.exists():
        raise SystemExit(f"找不到 PDF：{args.pdf}")

    import slide_ingest

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if len(models) < 2:
        raise SystemExit("--models 至少給兩個才有得比")

    # 渲染整份頁面（沿用 pipeline 的高解析渲染，確保跟正式線一致）
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        page_paths = slide_ingest.render_pdf_pages(args.pdf, Path(td))
        wanted = parse_pages(args.pages, len(page_paths))
        if not wanted:
            raise SystemExit(f"--pages 在 1..{len(page_paths)} 內沒有有效頁碼")
        pages = {p: page_paths[p - 1].read_bytes() for p in wanted}

        client = _build_client()
        print(f"▶ 比對 {len(pages)} 頁 × {len(models)} 模型：{', '.join(models)}")
        results = run_ab(client, slide_ingest.narrate_page_with_gemini,
                         pages, models, brief=args.brief)

    report = render_report(results, models, args.pdf.name)
    args.out.write_text(report, encoding="utf-8")
    print(f"✅ 報告已寫到 {args.out}")
    for model in models:
        total = sum(r["models"].get(model, {}).get("chars", 0) for r in results)
        print(f"   {model}: 輸出共 {total} 字")
    return 0


if __name__ == "__main__":
    sys.exit(main())
