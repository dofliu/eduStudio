"""Mermaid 圖渲染 — iter 57, Option D.

從 .md 文字 (repo / document) 抽出 ```mermaid``` block, 透過 mermaid.ink
線上服務 render 成 PNG 存到 figures/.

為什麼選 mermaid.ink:
- 零安裝 — 不必裝 npm + Chrome (mermaid-cli 路線需要這些, Docker 變肥)
- 免費公開服務
- HTTP GET 就能拿圖 (URL-safe base64 編碼 syntax)
- trade-off: 外部依賴, 服務掛了會 fail. 我們的失敗策略是 skip 該圖 + 警告, 不擋 ingest

iter 57b 預留: AI 生 mermaid syntax fallback (sections 沒抽到 mermaid 時)
"""
from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


MERMAID_INK_BASE = "https://mermaid.ink/img"

# ```mermaid 開頭, ``` 結尾, 中間是 mermaid syntax
# DOTALL 讓 . 匹配換行
MERMAID_BLOCK_RE = re.compile(
    r"```mermaid\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)

# 抓 mermaid block 前一行 (常是 caption: "下圖顯示..." / "Figure 1: ...")
# 取 100 字內當 caption_hint
CAPTION_LOOKBACK_CHARS = 300


def extract_mermaid_blocks(text: str) -> list[tuple[str, str]]:
    """從文字抽出所有 mermaid block.

    回傳 list of (syntax, caption_hint).
    caption_hint = mermaid block 前一段文字 (取最後一行非空, 限 100 字).
    抓不到回 ""(沒 caption 仍是有效 figure).
    """
    if not text:
        return []

    results: list[tuple[str, str]] = []
    for match in MERMAID_BLOCK_RE.finditer(text):
        syntax = match.group(1).strip()
        if not syntax:
            continue
        # caption_hint: 看 block 開頭往前 CAPTION_LOOKBACK_CHARS 內最後一行
        start = match.start()
        look_back = text[max(0, start - CAPTION_LOOKBACK_CHARS):start]
        # 從後往前找第一段非空文字
        caption_hint = ""
        for line in reversed(look_back.splitlines()):
            line = line.strip()
            # 跳過 markdown 標題 # / 列表 - + * / code fence
            if not line:
                continue
            if line.startswith(("#", "```", "---", "===")):
                continue
            caption_hint = line[:100]
            break
        results.append((syntax, caption_hint))
    return results


def render_mermaid_to_png(syntax: str, out_path: Path, *, timeout: float = 15.0) -> bool:
    """呼叫 mermaid.ink 把 syntax 轉成 PNG 存到 out_path.

    成功回 True, 失敗回 False (caller 自己 log skip). 不 raise — mermaid 圖
    是 bonus, 服務不通不該擋 ingest.

    URL-safe base64 編碼 syntax 後接到 mermaid.ink/img/{encoded}.
    參考: https://mermaid.ink/ — 服務簡介
    """
    if not syntax.strip():
        return False
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        return False

    try:
        # mermaid.ink 用標準 base64 (不是 urlsafe), 用 URL path 接收
        encoded = base64.urlsafe_b64encode(syntax.encode("utf-8")).decode("ascii")
        # urlsafe_b64encode 把 + → - , / → _, 適合放 URL
        # 但 mermaid.ink 可能用標準 base64 (RFC 4648 §4); 兩個都試
        url = f"{MERMAID_INK_BASE}/{encoded}?type=png"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "autoSolverVideo/mermaid-render"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if not data or len(data) < 100:
            return False
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return True
    except Exception as e:
        logger.warning("mermaid.ink render 失敗 (%s): %s", out_path.name, e)
        return False


def extract_and_render_mermaid_from_text(
    text: str, figures_dir: Path, *,
    id_prefix: str = "mermaid",
    source_label: str = "",
    max_blocks: int = 10,
) -> list[dict]:
    """從一份文字抽 mermaid blocks → 渲染成 PNG → 回 figure metadata list.

    參數:
        text: 含 ```mermaid``` blocks 的文字 (repo .md / document .md txt)
        figures_dir: 圖檔存放目錄 (= jobs/<id>/figures/)
        id_prefix: figure id 前綴, 預設 "mermaid" → 產 mermaid_1, mermaid_2...
                   repo 模式可帶 file stem 區分 ("mermaid_README_1")
        source_label: 給 logger 看的來源名稱 (e.g. "README.md")
        max_blocks: 單次最多渲染幾張 (避免一個 .md 內 50 個 block 全打)

    回傳 figure dict list (跟 extract_pdf_figures / AI gen 同 schema):
        {
          "id": "mermaid_1",
          "page_no": 0,           # mermaid 無頁碼概念, 用 0
          "path": "mermaid_1.png",
          "width": 0, "height": 0, # mermaid.ink 不回尺寸, 用 0 (renderer 不靠這欄位)
          "caption_hint": "下圖顯示流程...",
        }
    """
    blocks = extract_mermaid_blocks(text)
    if not blocks:
        return []

    figures: list[dict] = []
    for idx, (syntax, caption) in enumerate(blocks[:max_blocks], start=1):
        fig_id = f"{id_prefix}_{idx}"
        fname = f"{fig_id}.png"
        fpath = figures_dir / fname

        ok = render_mermaid_to_png(syntax, fpath)
        if not ok:
            logger.warning(
                "mermaid block 跳過: source=%s id=%s (render 失敗)",
                source_label or "?", fig_id,
            )
            continue

        figures.append({
            "id": fig_id,
            "page_no": 0,
            "path": fname,
            "width": 0,
            "height": 0,
            "caption_hint": caption,
        })

    if figures:
        logger.info(
            "Mermaid 抽取: %s 找到 %d 張", source_label or "text", len(figures),
        )
    return figures


def extract_and_render_mermaid_from_repo(
    raw_content: dict, figures_dir: Path, *, max_per_repo: int = 30,
) -> list[dict]:
    """從 repo raw_content 走全部 key_files 內 .md 找 mermaid → 渲染.

    參數:
        raw_content: scan_repo() 輸出 (含 key_files: [{path, content, ...}])
        figures_dir: 圖存放目錄
        max_per_repo: 全 repo mermaid 圖上限

    回 figure dict list. 每張 id = "mermaid_<file_stem>_<idx>" (file stem
    防 path traversal, 限 alnum / _ / -, 截 40 chars).
    """
    key_files = raw_content.get("key_files") or []
    figures: list[dict] = []
    for kf in key_files:
        if len(figures) >= max_per_repo:
            break
        if not isinstance(kf, dict):
            continue
        path_str = kf.get("path", "")
        content = kf.get("content", "")
        if not path_str.lower().endswith((".md", ".markdown")):
            continue
        if not content:
            continue
        # safe stem: alnum / _ / - 限定 40 字, 防 fig 檔名怪
        from pathlib import PurePosixPath
        stem = PurePosixPath(path_str).stem
        safe_stem = "".join(
            c if (c.isalnum() or c in "_-") else "_" for c in stem
        )[:40] or "doc"

        new_figs = extract_and_render_mermaid_from_text(
            content, figures_dir,
            id_prefix=f"mermaid_{safe_stem}",
            source_label=path_str,
            max_blocks=max(0, max_per_repo - len(figures)),
        )
        figures.extend(new_figs)
    return figures
