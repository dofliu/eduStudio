"""core/photo_deck.py — 一組照片 → Gemini vision 選圖+配文 → deck (相片簡報)。

定位
----
Smart Photo-to-Deck 的「AI 視覺大腦」+「組 deck」。輸入一組照片檔路徑, 用既有的
core.infocards.gemini.generate_json (多模態, response_schema 約束 JSON) 做:
  - 品質過濾: 標記過度模糊 / 曝光不良 / 高度重複的照片 → 剔除。
  - 逐張配文: 為留下的照片寫一句 caption。
  - 整體標題: 取一個相簿/簡報標題。
然後組成 sections/slides deck (每張照片一個 slide, bg_image=照片路徑, narration=caption),
交給既有輸出: core.slide_pptx.deck_to_pptx (PPTX) / 既有 render (影片) / infocards (圖卡)。

設計重點
--------
- 送 Gemini 前用 Pillow 把照片縮到 ≤1024px (降 token / 成本 / 傳輸), 分批送 (大量照片
  一次送會爆 token / timeout)。
- 防幻覺: prompt 硬限「只描述明確可見元素, 禁止臆測人名/地點/時間」。
- mock=True 走離線佔位 (不打 Gemini): 全留、caption 佔位 → 給測試 / 無金鑰環境。
- AI 產出為估值 → 組出的 deck slide 標 reviewed=False (硬規則 #1, 由 caller 決定是否停審)。
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_DIM = 1024          # 送 AI 前縮圖長邊上限
BATCH_SIZE = 16         # 每次 vision 呼叫最多幾張 (避免 token 上限 / timeout)

# vision 回傳的 JSON 結構 (google-genai response_schema 吃 dict / OpenAPI 子集)
_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "photos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},   # 1-based, 對應輸入順序
                    "keep": {"type": "boolean"},
                    "caption": {"type": "string"},
                    "score": {"type": "number"},     # 0~10 品質/代表性, 供全域挑選
                    "reason": {"type": "string"},    # 剔除原因 (blur/exposure/duplicate) 或亮點
                },
                "required": ["index", "keep", "caption"],
            },
        },
    },
    "required": ["title", "photos"],
}

_PROMPT = """你是相片策展與圖說助手。下面依序提供 {n} 張照片 (index 1..{n})。請完成:
1. 品質過濾: 過度模糊、曝光嚴重不良、或與其他張高度重複的照片, keep=false, 並在 reason
   標明原因 (blur / exposure / duplicate)。其餘 keep=true。
2. 為每張給 score (0~10, 代表清晰度+代表性)。
3. 為 keep=true 的每張寫一句 ≤30 字的繁體中文 caption。
4. 取一個貼切的整體簡報標題 title。
嚴格限制: caption 只描述照片中「明確可見」的元素, 禁止臆測人名、地點、日期等未顯示的資訊。
{hint}{cap}
以 JSON 回傳 (photos 陣列每張一筆, index 對應上面順序)。"""


def _downscale_to_bytes(path: str | Path, *, max_dim: int = MAX_DIM) -> bytes | None:
    """把照片等比縮到長邊 ≤ max_dim, 回 JPEG bytes。讀失敗回 None (該張跳過)。"""
    from PIL import Image

    try:
        im = Image.open(path)
        im = im.convert("RGB")
        im.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception as e:  # noqa: BLE001
        logger.warning("照片讀取/縮圖失敗 %s: %s", path, e)
        return None


def _analyze_batch(
    batch_bytes: list[bytes], *, deck_title_hint: str, max_select: int | None,
    api_key: str | None,
) -> dict:
    """一批 (≤BATCH_SIZE) 照片 → vision JSON。回 {title, photos:[{index,keep,caption,score,reason}]}。"""
    from core.infocards.gemini import generate_json

    hint = f"主題脈絡: {deck_title_hint}\n" if deck_title_hint else ""
    cap = f"最多保留 {max_select} 張最佳的。\n" if max_select else ""
    prompt = _PROMPT.format(n=len(batch_bytes), hint=hint, cap=cap)
    files = [{"mimeType": "image/jpeg", "data": b} for b in batch_bytes]
    return generate_json(
        prompt, files=files, response_schema=_ANALYSIS_SCHEMA,
        api_key=api_key, temperature=0.3, station="visual",
    )


def analyze_photos(
    paths: list[str | Path],
    *,
    deck_title_hint: str = "",
    max_select: int | None = None,
    batch_size: int = BATCH_SIZE,
    api_key: str | None = None,
    mock: bool = False,
) -> dict:
    """一組照片 → vision 分析。回 {"title": str, "photos": [{path, keep, caption, score, reason}]}。

    photos 依輸入順序 (含被剔除的, keep=False)。mock=True 全留 + 佔位 caption, 不打 Gemini。
    max_select 有值時, 全域只保留 score 最高的 max_select 張 (其餘 keep 改 False)。
    """
    paths = [Path(p) for p in paths]

    if mock:
        title = deck_title_hint or "相片集"
        photos = [{"path": str(p), "keep": True, "caption": f"照片 {i + 1}",
                   "score": 5.0, "reason": ""} for i, p in enumerate(paths)]
        if max_select:
            for ph in photos[max_select:]:
                ph["keep"] = False
        return {"title": title, "photos": photos}

    # 縮圖 (保留與 path 的對應, 讀失敗者標為不可用)
    prepared: list[tuple[Path, bytes | None]] = [(p, _downscale_to_bytes(p)) for p in paths]

    title = deck_title_hint or "相片集"
    result: list[dict] = [{"path": str(p), "keep": False, "caption": "",
                           "score": 0.0, "reason": "unreadable" if b is None else ""}
                          for p, b in prepared]

    # 分批送 (只送讀得到的), 回填到 result (用全域 index 對應)
    usable = [(gi, b) for gi, (_, b) in enumerate(prepared) if b is not None]
    for start in range(0, len(usable), batch_size):
        chunk = usable[start:start + batch_size]
        out = _analyze_batch(
            [b for _, b in chunk], deck_title_hint=deck_title_hint,
            max_select=None, api_key=api_key,  # 全域 max_select 最後統一套
        )
        if out.get("title") and start == 0:
            title = out["title"]
        for item in out.get("photos", []):
            local = item.get("index")
            if not isinstance(local, int) or not (1 <= local <= len(chunk)):
                continue
            gi = chunk[local - 1][0]
            result[gi].update({
                "keep": bool(item.get("keep", True)),
                "caption": (item.get("caption") or "").strip(),
                "score": float(item.get("score") or 0.0),
                "reason": (item.get("reason") or "").strip(),
            })

    # 全域 max_select: 只留 score 最高的 N 張
    if max_select is not None:
        kept = [r for r in result if r["keep"]]
        kept.sort(key=lambda r: r["score"], reverse=True)
        allow = {id(r) for r in kept[:max_select]}
        for r in result:
            if r["keep"] and id(r) not in allow:
                r["keep"] = False

    return {"title": title, "photos": result}


def _safe_id(s: str, i: int) -> str:
    base = "".join(c for c in s if c.isalnum() or c == "_")[:40]
    return base or f"p{i:03d}"


def build_photo_deck(
    analysis: dict,
    *,
    asset_base: str | Path,
    deck_title: str | None = None,
) -> dict:
    """vision 分析結果 → sections/slides deck (只納入 keep=True 的照片)。

    每張照片 → 一個 slide: bg_image=照片路徑 (相對 asset_base), narration=caption。
    產出的 deck 直接可餵 core.slide_pptx.deck_to_pptx / 既有 render / infocards。
    """
    base = Path(asset_base)
    title = deck_title or analysis.get("title") or "相片集"
    slides = []
    for i, ph in enumerate(p for p in analysis.get("photos", []) if p.get("keep")):
        abs_p = Path(ph["path"])
        try:
            rel = abs_p.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            rel = str(abs_p)  # 不在 asset_base 下 → 用絕對路徑 (renderer 也能吃)
        pid = f"p{i + 1:03d}"
        slides.append({
            "id": f"photo_{pid}",
            "title": ph.get("caption") or f"照片 {i + 1}",
            "narration": ph.get("caption") or "",
            "bg_image": rel,
            "bg_type": "slide",
            "layout": "full",
            "reviewed": False,   # AI 估值, 停審由 caller 決定
        })
    return {
        "deck_title": title,
        "source_type": "photos",
        "source_meta": {"total_photos": len(analysis.get("photos", [])),
                        "kept": len(slides)},
        "sections": [{"id": "ch1", "title": title, "slides": slides}],
    }


def photos_to_deck(
    paths: list[str | Path],
    *,
    asset_base: str | Path,
    deck_title_hint: str = "",
    max_select: int | None = None,
    api_key: str | None = None,
    mock: bool = False,
) -> dict:
    """便利函式: 照片路徑 → 分析 → deck (一步到位)。"""
    analysis = analyze_photos(
        paths, deck_title_hint=deck_title_hint, max_select=max_select,
        api_key=api_key, mock=mock,
    )
    return build_photo_deck(analysis, asset_base=asset_base, deck_title=deck_title_hint or None)
