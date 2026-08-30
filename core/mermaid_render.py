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

from core.infocards.models import DEFAULT_TEXT_MODEL

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
            headers={"User-Agent": "eduStudio/mermaid-render"},
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


# ---------- iter 57b: AI 生 mermaid syntax (沒既有 mermaid 時用) ----------

# Gemini text model 由集中式 model catalog 管理。
MERMAID_GEN_MODEL = DEFAULT_TEXT_MODEL

# 系統 prompt for mermaid 生成 — 強調 syntax 純淨度跟 簡潔
_MERMAID_GEN_PROMPT_TEMPLATE = """你是一位資深技術插畫師, 擅長把概念轉成 Mermaid 流程圖.

請針對以下章節主題, 產出一份 mermaid syntax 圖. 內容要忠於章節描述, 不要編造.

==== 章節資訊 ====
章節: {title}
意圖: {intent}
關鍵詞: {topics}
所屬內容: {deck_title}

==== Mermaid 設計原則 ====
1. 用 `graph TD` (上→下) 或 `graph LR` (左→右) 流程圖. 不用 sequenceDiagram / classDiagram 等複雜圖
2. **節點數 4~8 個** (不要太空也不要太密)
3. **節點 label 純英文, 限 3 詞內**. 中文字會渲染不出來
4. 用簡單形狀 — 矩形 [Label], 菱形 {{Label}} (decision), 圓角 (Label)
5. arrows 用 `-->` 或 `-->|condition|` 標條件
6. 不要 emoji, 不要 LaTeX, 不要花俏 style
7. **直接輸出 mermaid syntax, 不要 ```mermaid 包裹, 不要任何解釋文字**

==== 範例 (參考結構) ====
graph TD
  A[Input Data] --> B[Preprocess]
  B --> C{{Has Pattern?}}
  C -->|Yes| D[Extract Feature]
  C -->|No| E[Skip]
  D --> F[Output]
  E --> F

現在請針對上方章節輸出一份類似結構的 mermaid syntax:"""


def generate_mermaid_syntax_for_section(
    section: dict, deck_title: str = "", *,
    api_key: str | None = None,
) -> str | None:
    """單一 section → 一份 mermaid syntax 字串.

    回 None 表示失敗 (沒 API key / Gemini call 拋例外 / 輸出空字串).
    Caller (generate_mermaid_for_outline) 拿 syntax 後丟 mermaid.ink 渲染.

    為什麼跟 image gen 分開:
    - text gen 便宜很多 (Flash text 比 Flash image 一個 OoM)
    - mermaid 結構穩定可預測 (LLM 不會「畫」歪)
    - 但風格只有一種 (普通流程圖), 沒 image gen 的視覺多樣性
    """
    from core import config
    # 金鑰: 傳入 > 設定頁 > 環境變數(修掉 os.environ 直讀繞過設定頁)
    api_key = api_key or config.get_gemini_api_key()
    if not api_key:
        return None

    try:
        from google.genai import types
    except ImportError:
        return None

    title = (section.get("title") or "").strip()
    intent = (section.get("intent") or "").strip()
    topics = section.get("topics") or []
    if not title:
        return None

    prompt = _MERMAID_GEN_PROMPT_TEMPLATE.format(
        title=title,
        intent=intent or "(no specific intent)",
        topics=", ".join(t for t in topics if t) or "(no topics)",
        deck_title=deck_title or "(unknown)",
    )

    try:
        from core.gemini_client import make_client
        client = make_client(api_key)  # 統一工廠(T3-2): 一律帶 timeout
        resp = client.models.generate_content(
            model=MERMAID_GEN_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(
                temperature=0.3,         # 保守, 別亂發明
                max_output_tokens=1024,  # mermaid syntax 不會太長
            ),
        )
    except Exception as e:
        logger.warning("Gemini text gen mermaid 失敗: %s", e)
        return None

    raw = (resp.text or "").strip()
    # 記帳(2026-08-30 補漏): mermaid 架構圖文字生成跟著影片 pipeline 走 video 站
    from core import usage
    usage.record_text_now("video", MERMAID_GEN_MODEL, prompt, raw, label="mermaid")
    # 防 LLM 還是包了 ```mermaid``` fence, 抓出 syntax 主體
    if raw.startswith("```"):
        m = re.search(r"```(?:mermaid)?\s*\n(.*?)\n```", raw, re.DOTALL)
        if m:
            raw = m.group(1).strip()
        else:
            raw = raw.strip("`").strip()

    return raw if raw else None


def generate_mermaid_for_outline(
    outline: dict, figures_dir: Path, *,
    api_key: str | None = None,
    max_per_outline: int = 8,
) -> list[dict]:
    """整 outline 各 section 跑一份 mermaid syntax + 渲染成 PNG.

    Pipeline: Gemini text → mermaid syntax → mermaid.ink → PNG → figure dict.
    跟 generate_diagrams_for_outline (image gen) schema 一致, scriptor 自動配圖.

    參數:
        outline: outliner 輸出 (含 sections)
        figures_dir: 圖存放目錄
        max_per_outline: 上限 (預設 8, 防 lecture 多章燒到爆)

    回 figure dict list, id = "mermaid_<section_id>".
    Section 失敗 (生 syntax 失敗 / 渲染失敗) skip, 不擋其他 sections.
    """
    sections = outline.get("sections", [])[:max_per_outline]
    deck_title = outline.get("deck_title", "")
    figures_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []

    for sec in sections:
        sec_id = sec.get("id") or "unknown"
        safe_id = "".join(c for c in sec_id if c.isalnum() or c == "_")[:40]
        if not safe_id:
            continue

        syntax = generate_mermaid_syntax_for_section(
            sec, deck_title=deck_title, api_key=api_key,
        )
        if not syntax:
            logger.warning("Mermaid syntax 生成跳過: %s", sec_id)
            continue

        fname = f"mermaid_{safe_id}.png"
        fpath = figures_dir / fname
        ok = render_mermaid_to_png(syntax, fpath)
        if not ok:
            logger.warning("Mermaid render 失敗: %s", sec_id)
            continue

        out.append({
            "id": f"mermaid_{safe_id}",
            "page_no": 0,
            "path": fname,
            "width": 0,
            "height": 0,
            "caption_hint": (sec.get("title") or "")[:120],
        })

    return out


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
