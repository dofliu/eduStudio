"""課程術語/讀音表 glossary（F9-2 第一刀：schema + 套用層）。

為什麼存在
==========
全域 `pronunciation.json` 是「數學/工程符號 → TTS 發音」的單一全站對照表，對所有課
一視同仁。但**不同課**對同一術語有不同固定譯名/讀音/縮寫展開需求——材力的 `σ` 念「應力」
脈絡、自控的 `ω_n` 念「自然頻率」，而且翻譯時術語要前後一致（同一個「阻尼比」不能一下
"damping ratio" 一下 "damping coefficient"）。F9-2 把這層拆成**per-course glossary**：
每門課一份，產旁白/翻譯時套該課術語表 → 術語一致。

這支只做 **schema + 套用層**（offline-first 紀律）:
- schema：`GlossaryEntry`（term + reading + 各語言固定譯名 + 縮寫展開 + 別名）、`Glossary`。
- 套用層：把 glossary 轉成各下游要的 map —— TTS 讀音 map（接 `tts_backend.normalize_text`
  的 `extra_pronunciation`）、翻譯固定譯名 map、縮寫展開 map。
- 載入/存檔：人可讀 JSON，per-course 一份（建議落 `{project_dir}/glossary.json`）。

**不在這刀**（後續 slice / GATE）:
- 接進 ProjectStore / runner pipeline 的逐課自動掛載（後續 offline slice）。
- 「自動建議術語」（要打 Gemini 掃教材抽術語）= GATE，寫 proposal 後再做。

canonical 語言碼沿用 `config.CANONICAL_LANG`（'zh-TW'）；翻譯譯名 key 用目標語言碼。
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


# ---------- schema ----------
class GlossaryEntry(BaseModel):
    """一條課程術語。

    欄位語意（皆選填，除 term）:
    - `term`     術語本體（canonical 寫法），例 "自然頻率" / "ω_n" / "PID"。**必填非空**。
    - `reading`  TTS 讀音覆寫：進 TTS 前把 term/別名換成這串去念（例 "PID" → "P I D 控制器"）。
                 不填 → 該術語不進讀音表（沿用全域 pronunciation.json / 原文照念）。
    - `translations` 各語言固定譯名 `{lang: 譯名}`，例 `{"en": "natural frequency"}`。翻譯層
                 查表強制一致，避免同義詞漂移。
    - `expansion` 縮寫展開全稱（顯示/翻譯用），例 "PID" → "比例-積分-微分"。與 reading 分開：
                 reading 是「怎麼念」、expansion 是「全稱是什麼」，兩者可各自設。
    - `aliases`  同義/變體寫法，全部對應到同一條（例 "wn"/"ωn"/"ω_n" 都是自然頻率）。
    - `note`     人讀備註（不參與任何 map），純維護用。
    """

    term: str
    reading: str | None = None
    translations: dict[str, str] = Field(default_factory=dict)
    expansion: str | None = None
    aliases: list[str] = Field(default_factory=list)
    note: str | None = None

    @field_validator("term")
    @classmethod
    def _term_non_empty(cls, v: str) -> str:
        # term 是所有 map 的 key 來源，空字串會污染替換（把整段切爛），寫入當下就擋。
        if not v or not v.strip():
            raise ValueError("glossary entry term 不可為空")
        return v.strip()

    def surface_forms(self) -> list[str]:
        """這條術語的所有表面寫法（term + 別名），去重去空、長到短排序。

        為什麼長到短：下游做 longest-match 替換時要先換長的（"ω_n" 先於 "ω"），避免
        短 key 提前吃掉長 key 的一部分。各 map helper 共用此序。
        """
        seen: dict[str, None] = {}
        for s in [self.term, *self.aliases]:
            s = (s or "").strip()
            if s:
                seen.setdefault(s, None)
        return sorted(seen.keys(), key=lambda s: -len(s))


class Glossary(BaseModel):
    """一門課的術語表。`course` 是人讀課名/代號（材力、自控…），`entries` 為術語清單。"""

    course: str
    entries: list[GlossaryEntry] = Field(default_factory=list)

    @field_validator("course")
    @classmethod
    def _course_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("glossary course 不可為空")
        return v.strip()


# ---------- 套用層：glossary → 下游各 map ----------
# 為什麼回 dict 而非直接改文字：把「資料」與「替換動作」分離。TTS 走
# tts_backend.normalize_text(extra_pronunciation=...) 的既有 longest-match 機制；翻譯層
# 可自行查表。各 helper 純函式、無副作用 → 好測、好組合。


def to_pronunciation_map(glossary: Glossary) -> dict[str, str]:
    """course glossary → TTS 讀音 map（surface form → reading）。

    只收**有設 reading** 的術語；每個表面寫法都映到同一 reading。直接餵
    `tts_backend.normalize_text(text, extra_pronunciation=這個 map)` 即套用。

    同一表面寫法在多條 entry 重複出現時，**後者覆蓋前者**（維護者把更專一的放後面即可）。
    """
    out: dict[str, str] = {}
    for entry in glossary.entries:
        if entry.reading is None:
            continue
        for form in entry.surface_forms():
            out[form] = entry.reading
    return out


def translation_map(glossary: Glossary, lang: str) -> dict[str, str]:
    """course glossary → 指定語言的固定譯名 map（surface form → 譯名）。

    給翻譯層查表強制術語一致。只收**該語言有設譯名**的術語；查無此 lang 的 entry 跳過。
    """
    out: dict[str, str] = {}
    for entry in glossary.entries:
        target = entry.translations.get(lang)
        if not target:
            continue
        for form in entry.surface_forms():
            out[form] = target
    return out


def expansion_map(glossary: Glossary) -> dict[str, str]:
    """course glossary → 縮寫展開 map（surface form → 全稱）。只收有設 expansion 的術語。"""
    out: dict[str, str] = {}
    for entry in glossary.entries:
        if entry.expansion is None:
            continue
        for form in entry.surface_forms():
            out[form] = entry.expansion
    return out


# ---------- 載入 / 存檔（per-course JSON，人可讀）----------
_GLOSSARY_FILE = "glossary.json"


def glossary_path_for(project_dir: Path | str) -> Path:
    """一門課的 glossary 檔慣例位置：`{project_dir}/glossary.json`。

    為什麼跟 project.json 放一起：F9-2 主軸是「接進 Project 一課一工作空間」。先定好
    路徑慣例，後續 slice 把 ProjectStore / runner 串上來時就照這個位置讀。
    """
    return Path(project_dir) / _GLOSSARY_FILE


def load_glossary(path: Path | str) -> Glossary | None:
    """從 JSON 載入一門課的 glossary；檔案不存在回 None（沿 pronunciation 載入的寬容語意）。

    檔案在但內容壞（非法 JSON / schema 不符）→ 不靜默吞，讓 pydantic/json 拋出，
    維護者一眼看到哪裡壞（對齊 ProjectStore._load 的嚴格 reload）。
    """
    p = Path(path)
    if not p.is_file():
        return None
    return Glossary.model_validate(json.loads(p.read_text(encoding="utf-8")))


def save_glossary(glossary: Glossary, path: Path | str) -> None:
    """把 glossary 寫成 JSON。ensure_ascii=False 讓中文字面落盤、indent 讓人可手改。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(glossary.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
