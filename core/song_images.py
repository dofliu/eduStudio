"""SONG M2 生圖 — 每 segment 依歌詞 + 統一視覺風格組 prompt → Gemini 生圖。

對應 docs/SONG_MV_TRACK_RFC.md §4.2 (畫面生成). 兩層:
- build_image_prompt: 確定性組 prompt (歌詞語意 + 統一 visual_style + 風格 suffix),
  0 API call — routine / 測試可自由跑。
- generate_segment_image: 真呼 gemini-2.5-flash-image 燒 **image 額度** (GATE) —
  複用 core.diagram_image_gen 既有 Gemini image 呼叫 pattern。

offline-first: routine 不自主跑 generate_segment_image (燒額度), 由
tools/gen_song_images.py --execute 手動觸發 (預設 dry-run)。生成的圖是 AI 估值 →
寫回 song.json reviewed=false 停 awaiting_review (硬規則 #1, 不可繞)。

風格一致性 (RFC §4.2): 所有 segment 共用同一 visual_style + style_suffix, 避免逐段
畫風跳 (統一 suffix 取代固定種子/參考圖的最小做法)。
"""
from __future__ import annotations

import os
from pathlib import Path

from core.diagram_image_gen import IMAGE_MODEL, _extract_image_bytes

# 統一風格 suffix — 保逐段畫風一致 + 無文字浮水印 (歌詞字幕由渲染層燒, 圖不該帶字)
DEFAULT_STYLE_SUFFIX = (
    "cinematic, consistent art style across the whole music video, "
    "high detail, no text, no watermark, no captions, 16:9 aspect ratio"
)


def build_image_prompt(
    segment: dict,
    visual_style: str,
    *,
    style_suffix: str = DEFAULT_STYLE_SUFFIX,
) -> str:
    """組單一 segment 的生圖 prompt: 歌詞語意 + 統一視覺風格 + 風格 suffix。

    segment 已有非空 image_prompt → 原樣用 (人工 review 修過 / 前輪填的優先,
    idempotent, 不被覆蓋); 否則用歌詞行 + visual_style 組。
    """
    existing = (segment.get("image_prompt") or "").strip()
    if existing:
        return existing

    lyrics = " / ".join(
        ln.strip()
        for ln in (segment.get("lines") or [])
        if isinstance(ln, str) and ln.strip()
    )
    parts: list[str] = []
    if visual_style.strip():
        parts.append(visual_style.strip())
    if lyrics:
        parts.append(f"Scene inspired by the lyrics: {lyrics}")
    parts.append(style_suffix)
    return ". ".join(parts)


def generate_segment_image(
    prompt: str,
    out_path: Path,
    *,
    api_key: str | None = None,
) -> tuple[bool, str]:
    """單一 prompt → Gemini 生圖寫 out_path。回 (success, error_msg)。

    ⚠️ 燒 image 額度 (GATE)。複用 core.diagram_image_gen 的 genai 呼叫 + image bytes
    抽取。失敗回 (False, reason), caller 通常 logger.warning skip 該圖不擋整批
    (個別 safety filter / rate limit 不牽連其他 segment)。
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return (False, "google-genai SDK 未安裝")

    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return (False, "缺 GEMINI_API_KEY")

    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
    except Exception as e:
        return (False, f"Gemini API call 失敗: {e}")

    image_bytes = _extract_image_bytes(resp)
    if image_bytes is None:
        return (False, "Gemini 回應無 image bytes (可能 safety filter)")

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(image_bytes)
    except OSError as e:
        return (False, f"寫檔失敗: {e}")

    return (True, "")
