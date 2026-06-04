#!/usr/bin/env python3
"""SONG M0b helper — song.json (歌詞 + 手填時間軸) → MV mp4。

對應 docs/SONG_MV_TRACK_RFC.md M0: 手動歌詞 + 手填時間軸, 1 首歌走通到 mp4
(純色背景 + 歌詞字幕 + 歌曲音軌, 先不接生圖)。把 core/song_render.py 的三個
純函式串成一條可跑的 CLI, 讓劉老師一行指令把一首歌跑成 MV。

song.json 最小範例 (M0, start/end 手填 — whisper 轉錄的 phrase 時間戳可當起點微調):
    {
      "track_type": "song",
      "song_title": "此刻的溫度",
      "audio_path": "此刻的溫度.mp3",        # 相對 song.json 或絕對路徑
      "segments": [
        {"id": "seg_1", "lines": ["舊書牆架在舊書裡", "停在你沒翻的那頁"], "start": 10.3, "end": 20.1},
        {"id": "seg_2", "lines": ["咖啡熱情慢慢升起"], "start": 20.1, "end": 28.5}
      ]
    }

用法:
    python -m tools.song_mv song.json              # 真跑 → 出 mp4 (需 ffmpeg + audio)
    python -m tools.song_mv song.json --dry-run    # 只印 SRT + ffmpeg 指令, 不寫不跑
    python -m tools.song_mv song.json --bg navy --font-size 48 --out out.mp4
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.song_render import (  # noqa: E402  (sys.path 注入後才 import)
    _valid_segment,
    build_song_mv_cmd,
    build_song_mv_kenburns_cmd,
    is_song_schema,
    song_segments_to_srt,
)


def load_song(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_audio(song: dict, song_path: Path) -> Path:
    """audio_path 相對 song.json 所在目錄解析 (絕對路徑則原樣)。"""
    p = Path(song.get("audio_path") or "")
    if not p.is_absolute():
        p = (song_path.parent / p).resolve()
    return p


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SONG M0b — song.json → MV mp4")
    ap.add_argument("song_json", type=Path, help="song.json 路徑 (segments 時間軸 + audio_path)")
    ap.add_argument("--out", type=Path, default=None, help="輸出 mp4 (預設 song.json 同目錄 / song_title)")
    ap.add_argument("--bg", default="black", help="背景純色 (ffmpeg color, 預設 black)")
    ap.add_argument("--font-size", type=int, default=36, help="歌詞字級 (預設 36)")
    ap.add_argument("--dry-run", action="store_true", help="只印 SRT + ffmpeg 指令, 不寫檔不跑")
    args = ap.parse_args(argv)

    if not args.song_json.exists():
        print(f"❌ 找不到 song.json: {args.song_json}", file=sys.stderr)
        return 2

    song = load_song(args.song_json)
    if not is_song_schema(song):
        print("❌ 不是 song schema (需 track_type=='song' + segments list)", file=sys.stderr)
        return 2

    srt = song_segments_to_srt(song["segments"])
    if not srt.strip():
        print("❌ 沒有有效 segment (每個都缺 start/end 或 lines 空)", file=sys.stderr)
        return 2

    audio = resolve_audio(song, args.song_json)

    # 工作目錄 = song.json 所在。srt 寫這 + ffmpeg cwd 設這 → subtitles filter 用
    # basename 避開 Windows 路徑冒號 escape (同 pipeline._build_hardsub_cmd 慣例)。
    workdir = args.song_json.resolve().parent
    srt_path = workdir / (args.song_json.stem + ".srt")

    if args.out:
        out_stem = str(args.out.resolve().with_suffix(""))  # build 會補 .mp4
    else:
        title = (song.get("song_title") or "").strip() or args.song_json.stem
        out_stem = str(workdir / title)

    # 每個有效 segment 都有 image_path → ken burns (M2 完整畫面); 否則純色 (M0)。
    valid_segs = [s for s in song["segments"] if _valid_segment(s)]
    seg_images = [(s.get("image_path") or "").strip() for s in valid_segs]
    use_kenburns = bool(valid_segs) and all(seg_images)

    if use_kenburns:
        image_durs = [
            (img, float(s["end"]) - float(s["start"]))
            for img, s in zip(seg_images, valid_segs)
        ]
        cmd = build_song_mv_kenburns_cmd(
            image_durs, str(audio), srt_path.name, out_stem, font_size=args.font_size,
        )
        mode = f"ken burns (每段圖推鏡, {len(image_durs)} 圖)"
    else:
        cmd = build_song_mv_cmd(
            str(audio), srt_path.name, out_stem,
            bg_color=args.bg, font_size=args.font_size,
        )
        n_missing = sum(1 for i in seg_images if not i)
        mode = (
            "純色背景 (M0)" if not valid_segs
            else f"純色背景 (M0; {n_missing}/{len(valid_segs)} segment 缺 image_path, 跑 gen_song_images 補圖才走 ken burns)"
        )
    n_cues = srt.count(" --> ")

    if args.dry_run:
        print(f"=== 模式: {mode} ===")
        print("=== SRT ===")
        print(srt)
        print(f"=== ffmpeg cmd (cwd={workdir}) ===")
        print(" ".join(cmd))
        print(f"\n(dry-run: {n_cues} cue; 沒寫 {srt_path.name}, 沒跑 ffmpeg)")
        return 0

    if not audio.exists():
        print(f"❌ 找不到歌曲音檔: {audio} (song.json 的 audio_path)", file=sys.stderr)
        return 2

    if use_kenburns:
        missing_imgs = [img for img in seg_images if not (workdir / img).exists()]
        if missing_imgs:
            print(f"❌ 缺圖檔: {missing_imgs} — 先跑 gen_song_images.py --execute 生圖", file=sys.stderr)
            return 2

    print(f"▶ 模式: {mode}")

    srt_path.write_text(srt, encoding="utf-8")
    print(f"✅ 寫出 {srt_path.name} ({n_cues} cue)")
    print(f"▶ 跑 ffmpeg → {out_stem}.mp4 ...")
    try:
        proc = subprocess.run(cmd, cwd=str(workdir))
    except FileNotFoundError:
        print("❌ 找不到 ffmpeg — 確認已裝且在 PATH", file=sys.stderr)
        return 3
    if proc.returncode != 0:
        print(f"❌ ffmpeg 失敗 (return {proc.returncode})", file=sys.stderr)
        return proc.returncode
    print(f"✅ 完成: {out_stem}.mp4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
