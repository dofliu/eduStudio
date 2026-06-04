"""SONG track (第 4 條 track) M0 渲染骨架 — 對齊時間軸 + 歌詞 → SRT → MV mp4.

對應 docs/SONG_MV_TRACK_RFC.md M0 POC: 手動歌詞 + 手填時間軸, 走通到 mp4
(純色背景 + 歌詞字幕 + 歌曲音軌), 先不接生圖 (那是 M2)。RFC §8 明列「M0 渲染
骨架是純 offline, routine 可在 dep 裝好後自主推 + 補測試」。

跟 deck/exam 的關鍵差異 (RFC §3 對接表):
- 音訊軌: 歌曲音檔直接當配樂, **不跑 TTS**。
- 字幕軌: 歌詞行的時間戳由對齊 (M1) 或手填 (M0) 定死, **繞過** core.srt
  的 narration_to_cues 字數切分 (歌詞分行是創作決定, 不該被 40 字 budget 重切)。

此模組純函式 + 不真跑 ffmpeg (build_song_mv_cmd 只組指令, 可離線 unit test);
真正執行交給呼叫端 (跟 pipeline.burn_subtitles 同模式)。
"""
from __future__ import annotations

from pathlib import Path

from core.srt import _fmt_srt_time


def is_song_schema(data: dict) -> bool:
    """type guard (硬規則 #9): song.json 是 track_type=='song' + segments list.

    不靠 `'segments' in data` 字串硬判 (deck 也可能有別的 list 欄位), 而是比照
    core.youtube._is_deck_schema 用 track_type 標記 + 結構型別判。
    """
    return (
        isinstance(data, dict)
        and data.get("track_type") == "song"
        and isinstance(data.get("segments"), list)
    )


def _valid_segment(seg: object) -> bool:
    """segment 至少要有數值 start/end (end>start) + 非空 lines, 否則 M0 跳過.

    對齊/手填可能留下半填的 segment (start 有 end 沒), 渲染端寧可跳過不炸
    (graceful, 同 icon_picker / image_frames 既有缺檔靜默 skip 契約)。
    """
    if not isinstance(seg, dict):
        return False
    start, end = seg.get("start"), seg.get("end")
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return False
    if end <= start:
        return False
    lines = seg.get("lines")
    return isinstance(lines, list) and any(
        isinstance(ln, str) and ln.strip() for ln in lines
    )


def song_segments_to_srt(segments: list[dict]) -> str:
    """歌詞 segments (含對齊好的 start/end) → SRT 字串.

    每個 segment = 一個 SRT cue, 時間戳直接用 segment 的 start/end (繞過字數
    切分), 多行 lines 用換行併進同一 cue (字幕顯示多行歌詞)。

    無效 segment (缺 start/end / end<=start / lines 空) 靜默跳過, cue 編號只對
    有效的遞增 (避免 SRT 出現跳號或空 cue)。空 / 全無效 → 回 ""。

    歌詞行內各行的前後空白 strip 掉, 但保留行間換行。
    """
    out_lines: list[str] = []
    cue = 1
    for seg in segments:
        if not _valid_segment(seg):
            continue
        text = "\n".join(
            ln.strip() for ln in seg["lines"] if isinstance(ln, str) and ln.strip()
        )
        out_lines.append(str(cue))
        out_lines.append(
            f"{_fmt_srt_time(float(seg['start']))} --> {_fmt_srt_time(float(seg['end']))}"
        )
        out_lines.append(text)
        out_lines.append("")  # cue 間空行 separator
        cue += 1
    return "\n".join(out_lines)


def build_song_mv_cmd(
    audio_name: str,
    srt_name: str,
    out_name: str,
    *,
    width: int = 1920,
    height: int = 1080,
    bg_color: str = "black",
    font_size: int = 36,
    font_name: str = "Microsoft JhengHei",
) -> list[str]:
    """組 ffmpeg 指令: 純色背景 + 燒歌詞字幕 + 歌曲音軌 → mp4 (M0 骨架, 不接生圖).

    參數用「檔名」非絕對路徑 — 呼叫端該把 cwd 設成檔案所在目錄 (同
    pipeline._build_hardsub_cmd 慣例), 避開 Windows 路徑冒號要 escape 的麻煩
    (`D\\:/foo/bar.srt`)。

    - 背景: lavfi color source (無限長), 靠 -shortest 截到音軌長度。
    - 字幕: subtitles filter 燒在背景上, 歌詞置中大字 (font_size 36 比旁白
      字幕 22 大, MV 風格)。
    - 音軌: 歌曲音檔直接當配樂 (不跑 TTS), 重編成 aac。
    - M2 接生圖後, 背景 color source 會換成 ken burns 圖序列 (RFC §4.2)。
    """
    return [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={bg_color}:s={width}x{height}",
        "-i", audio_name,
        "-vf", (
            f"subtitles={srt_name}:"
            f"force_style='FontName={font_name},FontSize={font_size},"
            f"Alignment=2,BorderStyle=1,Outline=2'"
        ),
        "-map", "0:v", "-map", "1:a",
        "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        f"{out_name}.mp4",
    ]
