"""Prompt 載入器 — 把 prompt template 從 .py 字串抽到 prompts/*.txt 後集中讀檔。

設計目的:
- IDE 編輯 prompt 純文字, diff review 直觀, 不被 .py escape 干擾
- 未來 A/B 測試 / 版本切換可以靠 sha256 hash 自動追蹤 prompt 變化
- lru_cache 避免每次 LLM call 都讀檔

讀檔走 PROJECT_ROOT/prompts/<name>.txt。回傳的是原始字串, caller 自己跑
`.format(**kwargs)` 填參數 — 為了讓 LRU cache 命中, 不在這層做 format。

版本追蹤:
    prompt_version("scriptor_repo_section") -> 8-char sha256 prefix
    寫進 LLM call log, 之後追溯「這個失敗是用哪版 prompt」就有 anchor。

雜湊長度 8 因為 8^16 = 4 billion 個 unique prompt 才會 collision, 對單一專案
夠了; 完整 hash 太長, 不利日常 debug print。
"""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from core.config import PROJECT_ROOT


PROMPTS_DIR = PROJECT_ROOT / "prompts"


class PromptNotFoundError(FileNotFoundError):
    """指定 prompt name 找不到對應 .txt 檔。"""

    pass


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    """讀 prompts/<name>.txt, lru_cache 加速重複 call。

    參數:
        name: prompt 檔名 (不含 .txt), 例 "scriptor_repo_section"

    回傳:
        原始 prompt 字串 (含未填的 {} placeholder, caller 跑 .format 填)

    錯誤:
        PromptNotFoundError: 檔不存在 (清楚的 error message 給 dev 找錯)
    """
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise PromptNotFoundError(
            f"prompt '{name}' 找不到對應檔: {path}. "
            f"檢查拼字或 prompts/ 目錄是否完整。"
        )
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=64)
def prompt_version(name: str) -> str:
    """回傳 prompt 的 sha256 短 hash (前 8 字元), 寫進 LLM call log 給追溯。

    用法:
        log.info("scriptor call", prompt_version=prompt_version("scriptor_repo_section"))

    哪天 prompt 改了 hash 跟著變, log 自動標出「這條 trace 用 v8a3f1c2d 版」。
    """
    content = load_prompt(name)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
