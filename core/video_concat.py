"""影片串接 — intro mp4 接到主影片前面 (iter 41).

只負責: 把 intro 跟主影片串成一支 final.mp4. 不關心 SRT 偏移 (那是 runner /
caller 自己做的事), 不關心 audio_track 替換 (Idea 2 另案).

設計重點:
- intro 跟主影片的 video stream 規格已對齊 (1920×1080/30fps/H.264 yuv420p, 由
  pipeline.py 統一輸出). 但 audio stream 不一致 (intro 通常 44100/stereo,
  主影片 96000/mono), 所以 ffmpeg concat 不能直接 -c copy.
- 策略: 把 intro 的 audio 預先轉檔成跟主影片相同規格, 存
  ASSETS_DIR/intro_normalized.mp4 當快取. 之後每次 concat 用 concat demuxer
  + -c copy, 不再重壓. 第一次跑 ~3 秒, 後面每次秒接.
- normalize cache 用 (intro_path + intro_mtime + target_audio_spec) 當 key,
  intro 換檔或 spec 變了會自動重 normalize. (mtime 變化覆蓋舊快取)

不放這裡:
- SRT 時間偏移: 純文字處理, caller 算
- 主影片 audio spec 探測: 用 ffprobe, 放 runner 那層比較好 (它知道哪支
  主影片是參考)
"""
from __future__ import annotations

import json
import shutil
from core.ffmpeg import run_media_cmd
from pathlib import Path
from typing import NamedTuple


class AudioSpec(NamedTuple):
    """音訊規格三件組 — concat 要對齊的就這三項."""
    sample_rate: int     # e.g. 96000
    channels: int        # 1 (mono) / 2 (stereo)
    codec: str           # e.g. "aac"


def probe_audio_spec(video_path: Path) -> AudioSpec:
    """用 ffprobe 取影片的 audio stream 規格.

    沒 audio stream 會 raise ValueError (我們渲染出來的影片一定帶 TTS audio,
    沒 audio 算 pipeline bug, 不該安靜吞).
    """
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-select_streams", "a",
        str(video_path),
    ]
    proc = run_media_cmd(cmd, step="ffprobe audio spec", timeout=120)
    streams = json.loads(proc.stdout).get("streams", [])
    if not streams:
        raise ValueError(f"{video_path} 沒有 audio stream")
    s = streams[0]
    return AudioSpec(
        sample_rate=int(s["sample_rate"]),
        channels=int(s["channels"]),
        codec=s["codec_name"],
    )


def normalize_intro_audio(
    intro_path: Path, target: AudioSpec, cache_dir: Path,
) -> Path:
    """把 intro 的 audio 轉成 target spec, 影片不重壓 (codec copy).

    快取 key 包含 intro mtime — 換 intro 檔會自動 invalidate.
    回傳 normalized intro 路徑 (cache 命中時跟舊路徑相同).
    """
    if not intro_path.exists():
        raise FileNotFoundError(f"intro 不存在: {intro_path}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    # 快取檔名包含 intro mtime + target spec, 任一變化就重 normalize
    mtime = int(intro_path.stat().st_mtime)
    key = f"{intro_path.stem}_{mtime}_{target.sample_rate}_{target.channels}_{target.codec}"
    cached = cache_dir / f"intro_normalized__{key}.mp4"
    if cached.exists():
        return cached

    # 清掉舊快取 (同 intro stem 但不同 key, 例如 intro 換內容了)
    for old in cache_dir.glob(f"intro_normalized__{intro_path.stem}_*.mp4"):
        try:
            old.unlink()
        except OSError:
            pass

    # 影片 stream copy, 只重壓 audio. -ac/-ar 控 channel/sample rate.
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(intro_path),
        "-c:v", "copy",
        "-c:a", target.codec,
        "-ar", str(target.sample_rate),
        "-ac", str(target.channels),
        # -shortest 不加: intro 通常 audio/video 長度差幾 ms, 留原樣
        str(cached),
    ]
    run_media_cmd(cmd, step="ffmpeg intro audio normalize")
    return cached


def concat_videos(
    parts: list[Path], output: Path,
) -> None:
    """ffmpeg concat demuxer 把多支影片無重壓串成一支.

    要求所有 parts 的 codec / 解析度 / fps / audio spec 一致 (caller 自己
    用 normalize_intro_audio 對齊). 不一致會 fail, 不會自動 re-encode (那會
    把 5 分鐘渲染變 15 分鐘, 違背 cache 設計初衷).
    """
    if not parts:
        raise ValueError("parts 不能空")
    if len(parts) == 1:
        # 單一檔直接 copy 過去, 不必經 concat
        shutil.copy(parts[0], output)
        return

    # ffmpeg concat demuxer 需要一份檔案列表
    # 用 absolute path + 反斜線轉正斜線 (Windows ffmpeg concat 不認 \, 認 /)
    list_file = output.with_suffix(".concat.txt")
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in parts),
        encoding="utf-8",
    )
    try:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(output),
        ]
        run_media_cmd(cmd, step="ffmpeg concat")
    finally:
        # 清掉 concat list 暫存檔
        try:
            list_file.unlink()
        except OSError:
            pass


def get_video_duration(video_path: Path) -> float:
    """用 ffprobe 取影片秒數. SRT offset 用得到."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    proc = run_media_cmd(cmd, step="ffprobe duration", timeout=120)
    return float(proc.stdout.strip())


def merge_srts(parts: list[tuple[str, float]]) -> str:
    """合併多章 SRT 成單一 SRT, 各章按累積時間偏移 + cue 編號重排.

    parts: [(srt_text, segment_duration_seconds), ...]
           segment_duration 用前一段的影片秒數做累積 offset, 不是 SRT 自身長度
           (SRT 結尾可能比影片短, 偏移要用實際影片時長, 避免下一章 cue 提早跳).

    回傳: 合併後的 SRT (cue 編號 1, 2, 3, ... 連續).

    iter 45: 多章合 final.mp4 用. 純字串處理, 不開 ffmpeg.
    """
    if not parts:
        return ""

    cumulative_offset = 0.0
    output_lines: list[str] = []
    cue_counter = 1

    import re
    cue_block_pattern = re.compile(
        r"^\s*\d+\s*$\s*(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*$\s*(.+?)(?=\n\s*\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    for srt_text, segment_dur in parts:
        if srt_text.strip():
            shifted = offset_srt(srt_text, cumulative_offset)
            # 重編號 cue id: 每章從 1 開始, 合併後要全程連續
            for m in cue_block_pattern.finditer(shifted):
                start, end, body = m.group(1), m.group(2), m.group(3).strip()
                output_lines.append(str(cue_counter))
                output_lines.append(f"{start} --> {end}")
                output_lines.append(body)
                output_lines.append("")
                cue_counter += 1
        cumulative_offset += segment_dur

    return "\n".join(output_lines).rstrip() + "\n" if output_lines else ""


def offset_srt(srt_text: str, offset_seconds: float) -> str:
    """把 SRT 全部 cue 的時間戳往後推 offset 秒.

    intro prepend 後, 主影片字幕得從 offset 開始, 不然 SRT 跟畫面對不上.
    純字串處理, 不依賴 SRT lib (jobs/<id>/artifacts/*.srt 是我們自己產的,
    格式可控).
    """
    if offset_seconds <= 0:
        return srt_text

    import re
    # SRT 時間戳格式: HH:MM:SS,mmm --> HH:MM:SS,mmm
    pattern = re.compile(
        r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*"
        r"(\d{2}):(\d{2}):(\d{2}),(\d{3})"
    )

    def _shift(match: re.Match) -> str:
        s_h, s_m, s_s, s_ms, e_h, e_m, e_s, e_ms = match.groups()
        start = int(s_h) * 3600 + int(s_m) * 60 + int(s_s) + int(s_ms) / 1000
        end = int(e_h) * 3600 + int(e_m) * 60 + int(e_s) + int(e_ms) / 1000
        start += offset_seconds
        end += offset_seconds
        return f"{_fmt(start)} --> {_fmt(end)}"

    return pattern.sub(_shift, srt_text)


def _fmt(seconds: float) -> str:
    """秒 → HH:MM:SS,mmm (SRT 格式)."""
    if seconds < 0:
        seconds = 0
    total_ms = int(round(seconds * 1000))
    h = total_ms // 3_600_000
    rem = total_ms % 3_600_000
    m = rem // 60_000
    rem %= 60_000
    s = rem // 1000
    ms = rem % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
