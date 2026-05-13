"""SRT 字幕生成 — 從 pipeline.py 抽出 (iter 37 技術債清理)。

純函式無副作用 + 不依賴 PIL / mutagen / ffmpeg, 可獨立 unit test:
- build_srt(steps, durations, pause_after_each) → SRT 字串
- _fmt_srt_time(seconds) → "HH:MM:SS,mmm"

pipeline.py 對應段 (iter 37 之前):
    srt, cue, t = [], 1, 0.0
    for s, d in zip(data["steps"], durs):
        sent = [p.strip() for p in re.split(r"(?<=[。！？!?])\\s*", s.get("narration", "")) if p.strip()]
        ...

新版同樣邏輯 (按字數比例切 narration 內 sub-sentence), 但容錯多了:
- s.get("narration") 是 None / 空字串都 graceful
- durations 跟 steps 長度不等 → zip 取短的
"""
from __future__ import annotations

import re

# 中英標點都接, 中文句號 / 驚嘆號 / 問號 / 英文 ! / 英文 ?
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?])\s*")


def _fmt_srt_time(seconds: float) -> str:
    """秒數轉 SRT timestamp 格式 HH:MM:SS,mmm.

    範例: 3661.5 → "01:01:01,500"
    """
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_srt(
    steps: list[dict],
    durations: list[float],
    *,
    pause_after_each: float = 0.6,
) -> str:
    """把 steps (含 narration) 跟對應 durations 組成 SRT 字幕字串.

    參數:
        steps: list of {"narration": str, ...} (其他欄位忽略)
        durations: list of float, 對應每個 step 的影片秒數
        pause_after_each: 每個 step 結尾停頓秒數 (預設 0.6)

    回傳:
        SRT 字串 (\\n 分行, 含結尾換行)

    每個 step 的 narration 按中英標點切句, 各 sub-sentence 字數比例分配時間。
    最後一句吃到 step 結束時間 (避免 float 累積誤差讓字幕對不齊音檔)。

    沒 narration 的 step 不產 cue, 但仍累加 t (避免後續 cue 時間錯位)。
    """
    out_lines: list[str] = []
    cue = 1
    t = 0.0

    for step, dur in zip(steps, durations):
        narration = (step.get("narration") or "").strip()
        sentences = [p.strip() for p in _SENTENCE_SPLIT.split(narration) if p.strip()]

        if not sentences:
            t += dur + pause_after_each
            continue

        total_chars = sum(len(s) for s in sentences)
        sub_start = t

        for j, sentence in enumerate(sentences):
            if j == len(sentences) - 1:
                # 最後一句吃到 step 結束時間, 避免 float 誤差
                sub_end = t + dur
            else:
                # 按字數比例分配
                sub_end = sub_start + dur * (len(sentence) / total_chars)

            out_lines.append(str(cue))
            out_lines.append(f"{_fmt_srt_time(sub_start)} --> {_fmt_srt_time(sub_end)}")
            out_lines.append(sentence)
            out_lines.append("")  # 空白行 separator

            cue += 1
            sub_start = sub_end

        t += dur + pause_after_each

    return "\n".join(out_lines)
