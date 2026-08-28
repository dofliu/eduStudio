#!/usr/bin/env python3
"""以本機 Microsoft PowerPoint 將 PPTX 轉成 PDF（Windows fallback）。"""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: pptx_to_pdf.py <source.pptx> <output.pdf>", file=sys.stderr)
        return 2

    source = Path(args[0]).resolve()
    output = Path(args[1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    app = presentation = None
    try:
        import win32com.client

        app = win32com.client.DispatchEx("PowerPoint.Application")
        presentation = app.Presentations.Open(str(source), True, False, False)
        presentation.SaveAs(str(output), 32)  # 32 = ppSaveAsPDF
    except Exception as exc:
        print(f"PowerPoint COM error: {exc}", file=sys.stderr)
        return 1
    finally:
        if presentation is not None:
            try:
                presentation.Close()
            except Exception:
                pass
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
    return 0 if output.is_file() and output.stat().st_size > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
