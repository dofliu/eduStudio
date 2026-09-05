"""角色設定稿三視圖 → 去背 cutout PNG (CLI)。

用法:
    python tools/character_cutout.py photos/阿光.png photos/小儒.png --out assets/comic_characters
    python tools/character_cutout.py photos/*.png --out assets/comic_characters --tolerance 34

每張輸入會產生 <名字>_front.png / _side.png / _three_quarter.png (RGBA, 緊貼邊界)。
之後可上傳成 Series Bible 的 character_anchor, 或當旁白形象 (character_id=narrator)。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.comic_assets import cutout_character_sheet  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="角色設定稿三視圖 → 去背 cutout")
    ap.add_argument("sheets", nargs="+", help="設定稿 PNG/JPG (單色背景, 三視圖排一列)")
    ap.add_argument("--out", default="assets/comic_characters", help="輸出資料夾")
    ap.add_argument("--tolerance", type=int, default=30, help="背景色差門檻 (0-255, 預設 30)")
    args = ap.parse_args()
    for sheet in args.sheets:
        outs = cutout_character_sheet(sheet, args.out, tolerance=args.tolerance)
        print(f"{sheet} → " + ", ".join(p.name for p in outs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
