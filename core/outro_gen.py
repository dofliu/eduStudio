"""結尾頁生成 — iter 63.

在 deck 最後面塞一張靜態結尾 section (主內容後, intro 對稱於封面之前).
跟 cover_gen 對稱 — 純函式, 模板化 narration, 不打 LLM.

結尾 section 包含:
  - 主標題 (thanks_text, 預設「謝謝聆聽」)
  - 講者 (speaker, 跟封面用同一個預設)
  - 單位 (org, 跟封面用同一個預設)
  - 聯絡 URL (url, 預設 doflab.cc)
  - 結尾口白 (narration, 純模板, 不打 LLM)

結尾 section 在 runner 透過 append 進 deck["sections"][-1+1], 後續 render
flow 跟其他 sections 一樣 — 渲染成 mp4 + 自動 concat 到主內容後 / outro
個人影片 (若有) 前.

Renderer (core/render/pptx_style.py) 看 step.bg_type == "outro" 切換成
專屬 layout (居中大字, 不畫 banner).
"""
from __future__ import annotations


# 結尾 narration 模板. 純模板, 不打 LLM, 預測性高.
# 跟 cover narration 對稱: cover 是「介紹」, outro 是「感謝 + 聯絡」.
_OUTRO_NARRATION_TEMPLATE = (
    "今天的內容到此告一段落, 感謝各位的時間。"
    "我是{speaker}, 來自{org}。"
    "更多內容歡迎到 {url} 查看, 我們下次見。"
)


def build_outro_section(
    *,
    speaker: str = "",
    org: str = "",
    thanks_text: str = "",
    url: str = "",
    narration_override: str | None = None,
    show_qr: bool = False,
    youtube_url: str = "",
) -> dict:
    """產出一張結尾 section (含單一 outro slide).

    參數:
        speaker: 講者 (空字串時不畫該欄位)
        org: 單位 (空字串時不畫)
        thanks_text: 大字主標題 (空 → 「謝謝聆聽」)
        url: 聯絡 URL (空 → 「doflab.cc」, 不檢查格式)
        narration_override: 自訂結尾口白. None / 空字串 → 套模板.
        show_qr: iter 67 — 是否在底部畫兩個 QR code (網頁 + YouTube)
        youtube_url: iter 67 — YouTube 頻道 URL (給 QR code 用,
            空 → 跳過第二個 QR)

    回 section dict, 結構跟 scriptor 出的 section 一致, 但 slide.bg_type
    設成 "outro" 讓 renderer 切專屬 layout. id 用 "_outro" 底線 prefix
    避免跟 scriptor 產的 section id 撞.
    """
    thanks = (thanks_text or "").strip() or "謝謝聆聽"
    url_val = (url or "").strip() or "doflab.cc"
    youtube_val = (youtube_url or "").strip()

    # iter 63: narration_override 非空 → 直接用; 否則 fallback 到模板
    override = (narration_override or "").strip()
    if override:
        narration = override
    else:
        narration = _OUTRO_NARRATION_TEMPLATE.format(
            speaker=speaker or "劉老師",
            org=org or "DofLab",
            url=url_val,
        )

    return {
        "id": "_outro",
        "title": thanks,
        "slides": [{
            "id": "_outro_1",
            "title": thanks,
            "bullets": [],          # 結尾不畫 bullet, 改用 meta 欄位
            "code_snippet": None,
            "code_lang": None,
            "file_path": None,
            "image_path": None,
            "narration": narration,
            "bg_type": "outro",     # renderer 看這個切 layout
            "section_title": "",    # 不顯示章節 banner
            # iter 63 outro 專屬欄位 (renderer 讀, 其他 layout 忽略)
            "outro_speaker": speaker or "",
            "outro_org": org or "",
            "outro_url": url_val,
            # iter 67 QR code 欄位
            "outro_show_qr": bool(show_qr),
            "outro_youtube_url": youtube_val,
        }],
    }


def section_is_outro(section: dict) -> bool:
    """判斷 section 是否為 outro (id 為 '_outro' 或第一 slide bg_type=outro)."""
    if section.get("id") == "_outro":
        return True
    slides = section.get("slides") or []
    if slides and slides[0].get("bg_type") == "outro":
        return True
    return False
