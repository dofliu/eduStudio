"""從 mp3/mp4 自動產 song.json（歌曲 MV 第 4 track 的 AI 協助製作）。

劉老師原本要手刻 song.json（歌詞 + 每段時間軸）。本模組用 whisper 轉錄音檔/影片成
帶時間戳的 segments，自動組成 song.json（track_type=song 結構，對齊 core.song_render）。
之後仍走既有 review/生圖/render 流程（每段 reviewed=False 停人工微調，硬規則 #1）。

whisper 走 core.meeting.summarizer（已用 faster_whisper），影片/音檔都能轉（faster_whisper
以 PyAV 解碼）。重依賴 lazy。
"""
from __future__ import annotations

import os


def build_song_json_from_media(
    media_path: str,
    song_title: str = "",
    *,
    language: str = "auto",
) -> dict:
    """mp3/mp4 → whisper 轉錄 → song.json dict。

    每個 whisper segment → 一個 song segment（id/lines/start/end/image_path/reviewed）。
    空白段跳過。song_title 未給用檔名。回 song.json dict（不落盤，呼叫端決定）。
    """
    from core.meeting.summarizer import meeting_summarizer

    segments, _lang = meeting_summarizer.transcribe(media_path, language)
    song_segments: list[dict] = []
    idx = 1
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        sid = f"s{idx}"
        song_segments.append({
            "id": sid,
            "lines": [text],
            "start": round(float(seg.start), 2),
            "end": round(float(seg.end), 2),
            "image_path": f"images/seg_{sid}.png",
            "reviewed": False,   # 對齊硬規則 #1：AI 對齊/轉錄為估值，停人工微調
        })
        idx += 1

    base = os.path.splitext(os.path.basename(media_path))[0]
    return {
        "track_type": "song",
        "song_title": song_title.strip() or base,
        "audio_path": os.path.basename(media_path),
        "segments": song_segments,
    }
