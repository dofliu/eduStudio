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

# 次級標點 (逗號 / 頓號 / 分號 / 冒號, 中英都收) — 過長句在這裡再切.
# 用 lookbehind 切在標點「之後」, 保留標點與其後空白給接續判斷 (英文逗號後空白
# 才不會被吃掉變 "Hello,world"). 不含 _SENTENCE_SPLIT 的終止標點 (那層已切過).
_CLAUSE_SPLIT = re.compile(r"(?<=[，、；：,;:])")

# 單一 cue 字數上限 (N3 治本核心). 真實「截斷」發生在字幕帶視覺層:
# ffmpeg subtitles filter (FontName=Microsoft JhengHei, FontSize=22, BorderStyle=3,
# MarginV=40, 見 pipeline._build_hardsub_cmd) 在 1080p 把過長 cue 自動 wrap 成
# 多行, 超出 180px 字幕帶 (core.visuals.SUBTITLE_BAND_HEIGHT) 就視覺溢出 / 被切.
# 40 字 ≈ 字幕帶可容的 2 行 CJK (每行 ~20 字), 跟 N1 測量工具
# (tools/measure_narration_truncation.py DEFAULT_CUE_CHAR_BUDGET) 同值 — 兩邊
# 一起改才不漂移. 之後若用實機渲染量到更精準的可容字數再對齊調整.
SUBTITLE_CUE_CHAR_BUDGET = 40


def _split_long_cue(sentence: str, max_cue_chars: int) -> list[str]:
    """把超過 max_cue_chars 的句子在次級標點 greedy 裝箱成 ≤ 上限的片段.

    只在標點 (逗號 / 分號 / 冒號) 切, **不硬斷詞** — 語意優先. 若一段沒有次級
    標點可切 (例如一長串無逗號的句子), 整段保留不切 (寧可超出也不破壞語意).

    max_cue_chars <= 0 視為關閉切分 (回原句), 方便對照「修前」行為與測試.
    """
    if max_cue_chars <= 0 or len(sentence) <= max_cue_chars:
        return [sentence]

    segments = [seg for seg in _CLAUSE_SPLIT.split(sentence) if seg.strip()]
    if len(segments) <= 1:
        # 沒有次級標點可切 → 不硬斷詞, 整段保留
        return [sentence]

    chunks: list[str] = []
    cur = ""
    for seg in segments:
        candidate = cur + seg
        if cur and len(candidate.strip()) > max_cue_chars:
            chunks.append(cur.strip())
            cur = seg
        else:
            cur = candidate
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def narration_to_cues(
    narration: str | None,
    *,
    max_cue_chars: int = SUBTITLE_CUE_CHAR_BUDGET,
) -> list[str]:
    """把一段 narration 切成 SRT cue 序列 (字幕帶切分的單一真實來源).

    兩階段: 先按終止標點 (`_SENTENCE_SPLIT`) 切句, 再把過長句按次級標點
    (`_split_long_cue`) greedy 裝箱到 ≤ max_cue_chars. build_srt 與 N1 測量
    工具都該走這條, 確保「字幕實際呈現」與「截斷率測量」對齊.
    """
    text = (narration or "").strip()
    sentences = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    cues: list[str] = []
    for sentence in sentences:
        cues.extend(_split_long_cue(sentence, max_cue_chars))
    return cues


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
    max_cue_chars: int = SUBTITLE_CUE_CHAR_BUDGET,
) -> str:
    """把 steps (含 narration) 跟對應 durations 組成 SRT 字幕字串.

    參數:
        steps: list of {"narration": str, ...} (其他欄位忽略)
        durations: list of float, 對應每個 step 的影片秒數
        pause_after_each: 每個 step 結尾停頓秒數 (預設 0.6)
        max_cue_chars: 單一 cue 字數上限 (N3, 預設 SUBTITLE_CUE_CHAR_BUDGET).
            過長句按次級標點再切, 避免字幕帶視覺溢出. <=0 關閉切分.

    回傳:
        SRT 字串 (\\n 分行, 含結尾換行)

    每個 step 的 narration 先按終止標點切句、過長句再按次級標點切, 各 cue 按
    字數比例分配時間。最後一個 cue 吃到 step 結束時間 (避免 float 累積誤差讓
    字幕對不齊音檔)。

    沒 narration 的 step 不產 cue, 但仍累加 t (避免後續 cue 時間錯位)。
    """
    out_lines: list[str] = []
    cue = 1
    t = 0.0

    for step, dur in zip(steps, durations):
        cues = narration_to_cues(step.get("narration"), max_cue_chars=max_cue_chars)

        if not cues:
            t += dur + pause_after_each
            continue

        total_chars = sum(len(c) for c in cues)
        sub_start = t

        for j, cue_text in enumerate(cues):
            if j == len(cues) - 1:
                # 最後一個 cue 吃到 step 結束時間, 避免 float 誤差
                sub_end = t + dur
            else:
                # 按字數比例分配
                sub_end = sub_start + dur * (len(cue_text) / total_chars)

            out_lines.append(str(cue))
            out_lines.append(f"{_fmt_srt_time(sub_start)} --> {_fmt_srt_time(sub_end)}")
            out_lines.append(cue_text)
            out_lines.append("")  # 空白行 separator

            cue += 1
            sub_start = sub_end

        t += dur + pause_after_each

    return "\n".join(out_lines)
