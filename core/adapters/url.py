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
from urllib.parse import urljoin

from core.net_safety import UnsafeUrlError, assert_public_url


DEFAULT_MAX_CHARS = 80_000
DEFAULT_TIMEOUT = 15  # 秒
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AutoSolverVideo/0.3 "
    "(+https://github.com/dofliu/examReviewVideo)"
)

# 直接拿掉的標籤 (含內文)
_NOISY_TAGS = ("script", "style", "noscript", "nav", "header", "footer",
               "aside", "form", "iframe", "svg")


def _fetch_with_guarded_redirects(
    url: str,
    *,
    timeout: float,
    user_agent: str,
    max_redirects: int,
):
    """抓 URL,**每一跳都重跑一次 SSRF 檢查**後才發請求 (T2-1)。

    requests 的自動 redirect 只有第一跳會經過我們的檢查 —— 攻擊者拿一個
    public 網址 302 到 `169.254.169.254` 就繞過了。故關掉 `allow_redirects`
    自己跟,每跳先 `assert_public_url` 再送出。
    """
    import requests

    current = url
    for _ in range(max_redirects + 1):
        assert_public_url(current)
        resp = requests.get(
            current,
            timeout=timeout,
            headers={"User-Agent": user_agent},
            allow_redirects=False,
        )
        if resp.is_redirect or resp.is_permanent_redirect:
            location = resp.headers.get("Location")
            if not location:
                raise ValueError(f"{resp.status_code} 轉址但沒有 Location: {current}")
            # 相對路徑轉址要接回目前的 URL 才驗得到真正的目標主機
            current = urljoin(current, location)
            continue
        resp.raise_for_status()
        return resp, current

    raise UnsafeUrlError(f"轉址超過 {max_redirects} 次, 放棄: {url}")


def scan_url(
    url: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = DEFAULT_USER_AGENT,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
) -> dict:
    """抓 URL 主文回傳 raw_content。

    碰到付費牆 / robots.txt / 大站反爬會直接 raise — 由 caller 決定怎麼處理。
    PR-3b 不做自動 fallback。

    T2-1:網址(含每一跳轉址)都要過 `core.net_safety.assert_public_url`,
    指向內網 / metadata 位址會 raise `UnsafeUrlError`(`ValueError` 子類)。
    """
    from bs4 import BeautifulSoup

    resp, final_url = _fetch_with_guarded_redirects(
        url,
        timeout=timeout,
        user_agent=user_agent,
        max_redirects=max_redirects,
    )
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
            # 轉址後的實際來源 (沒轉址時 == url), 讓 review 的人看得到真正抓了誰
            "final_url": final_url,
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
