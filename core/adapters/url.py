"""URL adapter — 抓靜態 HTML 文章 → 統一 raw_content。

PR-3b 範圍限制 (跟之前討論一致):
- 只支援靜態 HTML, 不跑 JS
- 不繞付費牆 / 登入頁
- 不裝 readability-lxml / trafilatura, 用 bs4 簡單啟發式

抽取策略:
1. 拿掉所有 noisy tag (script / style / nav / header / footer / aside)
2. 優先找 <article> / <main> / [role="main"], 沒有就 fallback <body>
3. .get_text(separator='\\n', strip=True) 取純文字, 多餘空白壓平

raw_content schema (跟 document adapter 一致, 只是 source_kind="url"):
{
  "source_kind": "url",
  "title": "...",            # <title> 或 <h1>
  "url": "...",
  "content": "...",
  "primary_language": "zh-tw",
  "stats": {"chars": int, "fetched_at": "ISO", "truncated": bool, "status_code": 200},
}
"""
from __future__ import annotations

import re
from datetime import datetime, timezone


DEFAULT_MAX_CHARS = 80_000
DEFAULT_TIMEOUT = 15  # 秒
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutoSolverVideo/0.3 "
    "(+https://github.com/dofliu/examReviewVideo)"
)

# 直接拿掉的標籤 (含內文)
_NOISY_TAGS = ("script", "style", "noscript", "nav", "header", "footer",
               "aside", "form", "iframe", "svg")


def scan_url(
    url: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict:
    """抓 URL 主文回傳 raw_content。

    碰到付費牆 / robots.txt / 大站反爬會直接 raise — 由 caller 決定怎麼處理。
    PR-3b 不做自動 fallback。
    """
    import requests
    from bs4 import BeautifulSoup

    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"URL 必須以 http:// 或 https:// 開頭, 得到: {url}")

    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": user_agent},
    )
    resp.raise_for_status()
    html = resp.text

    soup = BeautifulSoup(html, "html.parser")

    # 拿掉雜訊
    for tag in soup.find_all(_NOISY_TAGS):
        tag.decompose()

    # 抓主內容區: article > main > role=main > body
    main = (
        soup.find("article")
        or soup.find("main")
        or soup.find(attrs={"role": "main"})
        or soup.body
    )
    if main is None:
        # 完全沒 body? 退到整份 soup
        main = soup

    # 取文字, 段落間用 \n, 把多餘空白壓平 (3+ 換行 -> 2 個)
    text = main.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    # title: <title> 或 <h1>
    title_el = soup.find("title")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else url

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    return {
        "source_kind": "url",
        "title": title,
        "url": url,
        "content": text,
        "primary_language": "zh-tw",
        "stats": {
            "chars": len(text),
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "truncated": truncated,
            "status_code": resp.status_code,
        },
    }


# ---------- CLI ----------

if __name__ == "__main__":
    import argparse
    import json
    import sys

    from core.runtime import setup_utf8_stdout
    setup_utf8_stdout()

    ap = argparse.ArgumentParser(description="URL adapter 自我測試")
    ap.add_argument("url")
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    raw = scan_url(args.url, max_chars=args.max_chars)
    print(f"source_kind: {raw['source_kind']}")
    print(f"title: {raw['title']}")
    print(f"url: {raw['url']}")
    print(f"stats: {raw['stats']}")
    sys.stdout.buffer.write(b"--- first 400 chars ---\n")
    sys.stdout.buffer.write(raw["content"][:400].encode("utf-8") + b"\n")

    if args.out:
        from pathlib import Path
        Path(args.out).write_text(
            json.dumps(raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n寫到 {args.out}")
