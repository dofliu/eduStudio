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

iter 30: dev-mode invalidation
    改 prompt 通常要重啟 server 才會生效 (lru_cache 命中舊內容). 兩條解法:

    1. 環境變數 `PROMPTS_NO_CACHE=1` → 每次都讀檔 (慢一點, 但即時)
    2. 程式碼 / REPL 呼叫 `clear_prompt_cache()` → 一次性 invalidate

    production 不該設 PROMPTS_NO_CACHE — load_prompt 是 hot path, 每個
    LLM call 都會 hit。dev / 測試環境改 prompt 後 set 一下就好。
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path

from core.config import PROJECT_ROOT


PROMPTS_DIR = PROJECT_ROOT / "prompts"


class PromptNotFoundError(FileNotFoundError):
    """指定 prompt name 找不到對應 .txt 檔。"""

    pass


def _no_cache() -> bool:
    """dev opt-out 開關: PROMPTS_NO_CACHE=1 → 每次重讀檔, lru_cache 失效."""
    return os.environ.get("PROMPTS_NO_CACHE") == "1"


def _read_prompt_file(name: str) -> str:
    """純讀檔, 不 cache. lru_cache 包在 _load_prompt_cached 上."""
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise PromptNotFoundError(
            f"prompt '{name}' 找不到對應檔: {path}. "
            f"檢查拼字或 prompts/ 目錄是否完整。"
        )
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=64)
def _load_prompt_cached(name: str) -> str:
    """cache 封裝, 由 load_prompt 依 _no_cache() 決定走不走."""
    return _read_prompt_file(name)


def load_prompt(name: str) -> str:
    """讀 prompts/<name>.txt, lru_cache 加速重複 call。

    參數:
        name: prompt 檔名 (不含 .txt), 例 "scriptor_repo_section"

    回傳:
        原始 prompt 字串 (含未填的 {} placeholder, caller 跑 .format 填)

    錯誤:
        PromptNotFoundError: 檔不存在 (清楚的 error message 給 dev 找錯)

    cache 行為:
        - 正常 (production): lru_cache 命中, 改 .txt 要重啟 server 才生效
        - 設 PROMPTS_NO_CACHE=1 (dev): 每次讀檔, 改 .txt 即時生效
        - 程式內 clear_prompt_cache(): 一次性 invalidate 後恢復 cache
    """
    if _no_cache():
        return _read_prompt_file(name)
    return _load_prompt_cached(name)


@lru_cache(maxsize=64)
def _prompt_version_cached(name: str) -> str:
    """sha256 hash 也經 cache (因為內部呼叫 load_prompt)."""
    content = load_prompt(name)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]


def prompt_version(name: str) -> str:
    """回傳 prompt 的 sha256 短 hash (前 8 字元), 寫進 LLM call log 給追溯。

    用法:
        log.info("scriptor call", prompt_version=prompt_version("scriptor_repo_section"))

    哪天 prompt 改了 hash 跟著變, log 自動標出「這條 trace 用 v8a3f1c2d 版」。

    cache 行為跟 load_prompt 一致 (PROMPTS_NO_CACHE / clear_prompt_cache 控制)。
    """
    if _no_cache():
        # 重算 hash, 不走 cache
        content = _read_prompt_file(name)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
    return _prompt_version_cached(name)


def clear_prompt_cache() -> None:
    """一次性清空 load_prompt + prompt_version 的 lru_cache。

    dev 改 .txt 後不必重啟 server, 在 REPL / debug endpoint 呼叫一次即可。
    或考慮 PROMPTS_NO_CACHE=1 整輪 server 都不 cache (適合密集 prompt 調校)。
    """
    _load_prompt_cached.cache_clear()
    _prompt_version_cached.cache_clear()
