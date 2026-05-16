"""封面頁生成 — iter 62.

在 deck 最前面塞一張靜態封面 section (intro 之後, 主內容之前). 包含:
  - 主題 (deck_title)
  - 講者 (speaker, 預設劉瑞弘)
  - 日期 (date_str, 預設今天 YYYY-MM-DD)
  - 單位 (org, 預設 NCUT IAE · DofLab)
  - 開場口白 (narration, 純模板, 不打 LLM)

封面 section 在 runner 透過 prepend 進 deck["sections"] 第 0 位, 後續 render
flow 跟其他 sections 一樣 — 渲染成 mp4 + 自動 concat 到 intro 後 / 主內容前.

Renderer (core/render/pptx_style.py) 看 step.bg_type == "cover" 切換成
專屬 layout (居中大字, 不畫 banner).
"""
from __future__ import annotations

from datetime import datetime


# 封面 narration 模板. 純模板, 不打 LLM, 預測性高.
# 結尾不該有句點 (TTS 容易切壞), 用「。」 + 短停頓.
_COVER_NARRATION_TEMPLATE = (
    "各位好, 我是{speaker}。"
    "今天要為大家介紹的主題是「{deck_title}」。"
    "本內容由{org}帶來, 讓我們開始。"
)


def build_cover_section(
    deck_title: str,
    *,
    speaker: str = "",
    org: str = "",
    date_str: str | None = None,
) -> dict:
    """產出一張封面 section (含單一 cover slide).

    參數:
        deck_title: 主題 (必填)
        speaker: 講者 (空字串時不畫該欄位)
        org: 單位 (空字串時不畫)
        date_str: 日期字串 (None → 今天 YYYY-MM-DD)

    回 section dict, 結構跟 scriptor 出的 section 一致, 但 slide.bg_type
    設成 "cover" 讓 renderer 切專屬 layout. id 用 "_cover" 底線 prefix
    避免跟 scriptor 產的 section id 撞.
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    narration = _COVER_NARRATION_TEMPLATE.format(
        speaker=speaker or "劉老師",
        deck_title=deck_title or "今天的主題",
        org=org or "DofLab",
    )

    return {
        "id": "_cover",
        "title": deck_title or "封面",
        "slides": [{
            "id": "_cover_1",
            "title": deck_title or "今天的主題",
            "bullets": [],          # 封面不畫 bullet, 改用 meta 欄位
            "code_snippet": None,
            "code_lang": None,
            "file_path": None,
            "image_path": None,
            "narration": narration,
            "bg_type": "cover",     # renderer 看這個切 layout
            "section_title": "",    # 不顯示章節 banner
            # iter 62 cover 專屬欄位 (renderer 讀, 其他 layout 忽略)
            "cover_speaker": speaker or "",
            "cover_org": org or "",
            "cover_date": date_str,
        }],
    }


def section_is_cover(section: dict) -> bool:
    """判斷 section 是否為 cover (id 為 '_cover' 或第一 slide bg_type=cover)."""
    if section.get("id") == "_cover":
        return True
    slides = section.get("slides") or []
    if slides and slides[0].get("bg_type") == "cover":
        return True
    return False
