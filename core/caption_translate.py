"""SRT 字幕翻譯（發布站多語字幕軌）。

解析既有 .srt → 逐 cue 翻譯文字（保留 index 與時間碼）→ 重組 .srt。翻譯函式注入
（預設走 core.translation TranslateGemmaService.translate），方便測試 mock。純文字處理，
不碰 YouTube；上傳由 core.youtube.upload_captions 負責。
"""
from __future__ import annotations

import re
from typing import Callable

# 時間碼行：00:00:01,000 --> 00:00:03,500
_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}")


def parse_srt(text: str) -> list[dict]:
    """SRT 文字 → [{index, time, lines:[...]}]。容忍多餘空行、缺序號。"""
    cues: list[dict] = []
    blocks = re.split(r"\r?\n\r?\n+", (text or "").strip())
    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue
        idx, time, i = None, None, 0
        # 第一行可能是序號（純數字）
        if lines[0].strip().isdigit():
            idx = lines[0].strip()
            i = 1
        if i < len(lines) and _TIME_RE.match(lines[i].strip()):
            time = lines[i].strip()
            i += 1
        text_lines = [ln for ln in lines[i:] if ln.strip() != ""]
        if time is None or not text_lines:
            continue
        cues.append({"index": idx, "time": time, "lines": text_lines})
    return cues


def build_srt(cues: list[dict]) -> str:
    """[{index?, time, lines}] → SRT 文字（序號未給則重新編號）。"""
    out = []
    for n, cue in enumerate(cues, start=1):
        out.append(str(cue.get("index") or n))
        out.append(cue["time"])
        out.extend(cue["lines"])
        out.append("")  # 區塊間空行
    return "\n".join(out).strip() + "\n"


def translate_srt(
    srt_text: str,
    source_lang: str,
    target_lang: str,
    translate_fn: Callable[[str, str, str], str],
) -> str:
    """翻譯整份 SRT 的 cue 文字（保留時間碼）。

    translate_fn(text, source, target) → 翻譯文字。逐 cue 呼叫（短影片 cue 不多，
    逐句最可靠不會跑位）；多行 cue 合併成一句翻再放回單行。翻譯失敗的 cue 保留原文。
    """
    cues = parse_srt(srt_text)
    for cue in cues:
        original = " ".join(cue["lines"]).strip()
        if not original:
            continue
        try:
            translated = translate_fn(original, source_lang, target_lang)
            cue["lines"] = [(translated or original).strip()]
        except Exception:
            pass  # 保留原文，不讓單 cue 失敗毀掉整份字幕
    return build_srt(cues)
