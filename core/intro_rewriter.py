"""影片開場白多樣化 — 取代每支影片都「各位同學好」的單調感 (iter 42).

問題: scriptor / solve.py 寫進 deck.json 的 narration 開頭幾乎都是
「各位同學好」, 同一份考卷 10 道題輸出 10 部影片開頭一模一樣很 robotic.

設計:
- 純函式 rewrite_deck_intros(deck, source_type) → 回新 deck dict, 不動原檔
- 對象 (audience) 由 source_type 決定:
    exam_pdf / slides_pdf → student   ("各位同學好" / "來看這題" / ...)
    document / repo / url → general   ("各位好" / "大家好" / "今天來聊" / ...)
- 只動「每支影片的第一句旁白」(問題的第一個 step / 章節的第一張 slide),
  不動每個 step 的旁白 — 避免同一支影片講到一半又冒「大家好」.
- seed 用 problem_id / section_id 的 stable hash, 同題每次跑結果穩定, 跨題會變.
  不靠 random.choice 因為 PYTHONHASHSEED 亂跳 → 重 render 同一題會有不同開頭.

實作策略 (replace-only, 不 prepend):
- 抓現有開頭問候語的 regex (各位同學好 / 大家好 / 同學們好 ...) 替換成新變體
- 沒抓到問候語就 noop — 避免重複堆疊開場白
"""
from __future__ import annotations

import hashlib
import re
from typing import Literal


# ---------- 變體庫 ----------

# 學生對象 (上課用), exam_pdf / slides_pdf
STUDENT_VARIANTS: list[str] = [
    "各位同學好",
    "來看這題",
    "這題的關鍵在於",
    "先看題目問什麼",
    "這題容易踩雷",
    "這道題我們一起拆解",
    "同學們注意",
    "這題重點在",
]

# 泛眾對象 (yt 觀眾用), document / repo / url
GENERAL_VARIANTS: list[str] = [
    "各位好",
    "大家好",
    "今天來看",
    "這篇文章我們聊聊",
    "今天分享",
    "來看這個有趣的內容",
    "這次的主題是",
    "今天聊聊",
]

# audience → 對應變體庫
VARIANTS_BY_AUDIENCE: dict[str, list[str]] = {
    "student": STUDENT_VARIANTS,
    "general": GENERAL_VARIANTS,
}

# source_type → audience 對應 (CLAUDE.md 用戶確認的分類)
AUDIENCE_BY_SOURCE_TYPE: dict[str, str] = {
    "exam_pdf": "student",
    "slides_pdf": "student",
    "document": "general",
    "repo": "general",
    "url": "general",
}


# ---------- regex ----------

# 抓現有開頭問候語 — 涵蓋 scriptor / solve.py 跟 LLM 最常見的輸出
# 注意: 中文標點 ,，。.!！?？ 都要吃, 包含半形全形
_GREETING_PATTERN = re.compile(
    r"^\s*("
    r"各位同學好"
    r"|同學們好"
    r"|各位同學"
    r"|同學們"
    r"|大家好"
    r"|各位好"
    r"|大家"
    r"|各位"
    r")"
    r"[,，。.!！?？\s]*"
)


# ---------- 純函式 helpers ----------


def _stable_seed(key: str) -> int:
    """字串 → 32-bit int (md5 前 8 hex). 跨 process / Python 啟動穩定.

    用 hash() 不行: PYTHONHASHSEED 預設隨機, 同樣 key 不同 process 結果不同
    → 重 render 同一題開頭會跳, 違反「同題穩定」要求.
    """
    return int(hashlib.md5(key.encode("utf-8")).hexdigest()[:8], 16)


def _pick_variant(audience: str, key: str) -> str | None:
    """從 audience 變體庫挑一個, 用 key 當 seed. 沒對應 audience 回 None."""
    pool = VARIANTS_BY_AUDIENCE.get(audience)
    if not pool:
        return None
    return pool[_stable_seed(key) % len(pool)]


def rewrite_narration_intro(
    narration: str, audience: Literal["student", "general"], seed_key: str,
) -> str:
    """把單句旁白開頭的問候語換成 audience 對應變體.

    沒抓到問候語就原樣回傳 (noop) — 避免在沒問候語的句首硬塞變體造成
    「來看這題, 函式 f(x) 的定義是…」這種怪句.

    seed_key: stable hash 用 key, 通常是 problem_id / section_id / slide_id.
    """
    if not narration or not narration.strip():
        return narration

    variant = _pick_variant(audience, seed_key)
    if variant is None:
        return narration

    match = _GREETING_PATTERN.match(narration)
    if not match:
        return narration   # 沒問候語, 別動

    # 取代問候語: 保留後段內容, 中間補一個全形逗號
    rest = narration[match.end():]
    # rest 可能直接以中文開頭, 也可能以空白開頭, 統一 strip 再接
    rest = rest.lstrip()
    if not rest:
        return f"{variant},"
    return f"{variant},{rest}"


# ---------- Deck-level rewriting ----------


def _rewrite_problems_deck(deck: dict, audience: str) -> dict:
    """v1 exam schema (problems / steps): 每 problem 第一個 step 改開頭."""
    problems = deck.get("problems", [])
    for prob in problems:
        steps = prob.get("steps") or []
        if not steps:
            continue
        first = steps[0]
        narration = first.get("narration") or ""
        seed_key = str(prob.get("id") or first.get("display") or "p")
        new_narration = rewrite_narration_intro(narration, audience, seed_key)
        if new_narration != narration:
            first["narration"] = new_narration
    return deck


def _rewrite_sections_deck(deck: dict, audience: str) -> dict:
    """新 deck schema (sections / slides): 每 section 第一張 slide 改開頭."""
    sections = deck.get("sections", [])
    for sec in sections:
        slides = sec.get("slides") or []
        if not slides:
            continue
        first = slides[0]
        narration = first.get("narration") or ""
        seed_key = str(sec.get("id") or first.get("id") or "s")
        new_narration = rewrite_narration_intro(narration, audience, seed_key)
        if new_narration != narration:
            first["narration"] = new_narration
    return deck


def rewrite_deck_intros(deck: dict, source_type: str) -> dict:
    """主入口: 依 source_type 自動分流, 改 deck 內每支影片的開頭旁白.

    參數:
        deck: 兩種 schema 都接 — v1 (problems/steps) 或新 (sections/slides)
        source_type: "exam_pdf" / "slides_pdf" / "document" / "repo" / "url".
                     不認識的 source_type → 走 student 預設 (保守選擇)

    回傳: 原地修改後的同一個 deck dict (方便 chained call).
          沒符合條件就原樣回 (沒問候語抓到 / deck 空 / source_type 未對應).

    為什麼原地修改: deck 通常剛從 json.loads 出來, copy 沒必要; 純函式
    contract 在「同樣 input 同樣 output」, 不在「不改 input」.
    """
    if not deck:
        return deck
    audience = AUDIENCE_BY_SOURCE_TYPE.get(source_type, "student")

    # schema 偵測: 看頂層欄位
    if "problems" in deck and isinstance(deck["problems"], list):
        return _rewrite_problems_deck(deck, audience)
    if "sections" in deck and isinstance(deck["sections"], list):
        return _rewrite_sections_deck(deck, audience)

    # 兩個都不認識, 不動
    return deck
