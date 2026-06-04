#!/usr/bin/env python3
"""SONG M2 生圖執行包 — 讀 song.json 每 segment 組 prompt → (--execute) Gemini 生圖。

跟 V2 的 tools/gen_icon_svgs.py 同安全模式:
- **預設 dry-run**: 只印每 segment 的生圖 prompt 與目標路徑, 不呼叫 API、不寫檔、
  不燒 image 額度。
- `--execute` 才呼 gemini-2.5-flash-image 生圖 (GATE, 燒 image 額度), 寫圖到
  song.json 同目錄 images/seg_<id>.png, 並把 image_path 寫回 song.json +
  reviewed=false (停 awaiting_review, 硬規則 #1 — AI 生圖是估值, 必須人工 review)。
- **不自動 commit / 不自動標 reviewed=true** — 生圖後印 review checklist, 由劉老師
  逐張看 (風格一致 / 不對題 / safety) 再手動進渲染。

用法:
    python tools/gen_song_images.py song.json                  # dry-run, 印全部 prompt
    python tools/gen_song_images.py song.json --style "賽博龐克霓虹城市夜景"  # 覆寫 visual_style
    python tools/gen_song_images.py song.json --execute        # 真生圖 (需 GEMINI_API_KEY + 額度)
    python tools/gen_song_images.py song.json --execute --only seg_3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.song_images import build_image_prompt, generate_segment_image  # noqa: E402
from core.song_render import is_song_schema  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SONG M2 生圖執行包 (預設 dry-run)")
    ap.add_argument("song_json", type=Path, help="song.json 路徑 (segments + visual_style)")
    ap.add_argument("--execute", action="store_true", help="真生圖 (呼 Gemini + 寫檔 + 寫回 song.json); 預設 dry-run")
    ap.add_argument("--style", default=None, help="覆寫 song.json 的 visual_style (統一視覺風格一句話)")
    ap.add_argument("--only", metavar="SEG_ID", help="只處理單一 segment id")
    args = ap.parse_args(argv)

    if not args.song_json.exists():
        print(f"❌ 找不到 song.json: {args.song_json}", file=sys.stderr)
        return 2

    song = json.loads(args.song_json.read_text(encoding="utf-8"))
    if not is_song_schema(song):
        print("❌ 不是 song schema (需 track_type=='song' + segments list)", file=sys.stderr)
        return 2

    visual_style = (args.style or song.get("visual_style") or "").strip()
    segments = song["segments"]
    if args.only:
        segments = [s for s in segments if s.get("id") == args.only]
        if not segments:
            print(f"❌ 找不到 segment id: {args.only}", file=sys.stderr)
            return 2

    img_dir = args.song_json.resolve().parent / "images"

    if not args.execute:
        print(f"=== dry-run: {len(segments)} segment 生圖 prompt (visual_style={visual_style!r}) ===\n")
        for seg in segments:
            sid = seg.get("id") or "?"
            print(f"[{sid}] → {img_dir / f'seg_{sid}.png'}")
            print(build_image_prompt(seg, visual_style))
            print()
        print("(dry-run: 沒呼叫 Gemini, 沒寫檔, 沒燒額度。--execute 才真生圖。)")
        return 0

    # --execute: 真生圖 (GATE, 燒 image 額度)
    ok, fail = 0, 0
    for seg in segments:
        sid = seg.get("id") or "?"
        prompt = build_image_prompt(seg, visual_style)
        out_path = img_dir / f"seg_{sid}.png"
        success, err = generate_segment_image(prompt, out_path)
        if success:
            # 寫回 song.json: image_path (相對 song.json) + reviewed=false (停 review)
            seg["image_path"] = f"images/seg_{sid}.png"
            seg["reviewed"] = False
            ok += 1
            print(f"✅ [{sid}] → {out_path}")
        else:
            fail += 1
            print(f"⚠️  [{sid}] 跳過: {err}", file=sys.stderr)

    args.song_json.write_text(json.dumps(song, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n生圖完成: {ok} 成功 / {fail} 失敗。song.json 已更新 image_path + reviewed=false。")
    print("⚠️  下一步 (硬規則): 逐張 review images/seg_*.png — 風格一致 / 不對題 / safety,")
    print("    OK 後在 review UI 改 reviewed=true 才進渲染。**不要自動標 reviewed。**")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
