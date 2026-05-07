#!/usr/bin/env python3
"""scripts/submit_job.py — 用一行 CLI 觸發 server 的 POST /jobs。

設計用途: Claude Cowork 的 schedule 技能 / Windows 工作排程器 / cron 排程
直接呼叫這支 wrapper, 不用手寫 JSON payload + curl。

範例:
    # 排程跑 repo 講解 (預設 require_review=false)
    python scripts/submit_job.py repo D:/path/to/your/repo

    # 講義 PDF
    python scripts/submit_job.py document D:/lecture.pdf

    # 部落格文章
    python scripts/submit_job.py url https://example.com/blog/some-article

    # 考卷 (預設 require_review=true, 加 --no-review 可跳過)
    python scripts/submit_job.py exam D:/exam.pdf

    # 自訂 server (預設 http://localhost:8000)
    python scripts/submit_job.py repo D:/repo --server http://192.168.1.5:8000

回傳 JSON 印到 stdout, 排程 log 直接抓得到 job_id。
exit code: 0 成功, 非 0 失敗 (連線錯 / 4xx / 5xx)。
"""
from __future__ import annotations

import argparse
import json
import sys


# user-facing source_type alias -> 真正 SourceType.value
TYPE_ALIAS = {
    "exam": "exam_pdf",
    "exam_pdf": "exam_pdf",
    "slides": "slides_pdf",
    "slides_pdf": "slides_pdf",
    "repo": "repo",
    "document": "document",
    "doc": "document",
    "md": "document",
    "txt": "document",
    "pdf": "document",  # 視為 document; 要當考卷用 "exam"
    "url": "url",
}


def main() -> int:
    # Windows 終端 cp950 不支援中文 emoji, argparse 印 --help 前先把 stdout 切 UTF-8
    # (sys.path 還沒含 core 也許, 所以這裡直接 inline 不 import core.runtime)
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(
        description="排程觸發 autoSolverVideo job (POST /jobs)。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("source_type",
                    choices=sorted(set(TYPE_ALIAS)),
                    help="來源類型 (exam / slides / repo / document / url)")
    ap.add_argument("source",
                    help="path (檔 / 資料夾) 或 URL")
    ap.add_argument("--server", default="http://localhost:8000",
                    help="server 位址 (預設 http://localhost:8000)")
    ap.add_argument("--review", dest="review", action="store_true", default=None,
                    help="完成 ingest 後停在 awaiting_review (預設 exam=True, 其他=False)")
    ap.add_argument("--no-review", dest="review", action="store_false",
                    help="exam 也跳過 review, 一路跑完")
    ap.add_argument("--mock", action="store_true",
                    help="走 mock 路徑 (不打 Gemini, smoke test 用)")
    ap.add_argument("--max-files", type=int, default=None,
                    help="repo source 限掃幾個檔 (預設 50)")
    ap.add_argument("--tts", default=None, choices=["edge", "f5"],
                    help="覆寫 TTS 後端")
    ap.add_argument("--timeout", type=float, default=15.0,
                    help="server 連線 timeout (秒, 預設 15)")
    args = ap.parse_args()

    canonical = TYPE_ALIAS[args.source_type]

    # 組 payload — url 用 source.url, 其他用 source.path
    if canonical == "url":
        source_field = {"url": args.source}
    else:
        source_field = {"path": args.source}

    options: dict = {"mock": args.mock}
    if args.review is not None:
        options["require_review"] = args.review
    if args.max_files is not None:
        options["max_files"] = args.max_files
    if args.tts is not None:
        options["tts_provider"] = args.tts

    payload = {
        "source_type": canonical,
        "source": source_field,
        "options": options,
    }

    # requests 是 PR-2a 加進 requirements.txt (透過 fastapi 一起裝),
    # 在這裡 lazy import 是為了 --help 不必載入網路 lib。
    import requests

    url = f"{args.server.rstrip('/')}/jobs"
    try:
        resp = requests.post(url, json=payload, timeout=args.timeout)
    except requests.exceptions.RequestException as e:
        print(f"❌ 連線失敗 ({url}): {e}", file=sys.stderr)
        print("   server 是否已啟動? `python -m server.main`", file=sys.stderr)
        return 2

    if resp.status_code >= 400:
        print(f"❌ HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 3

    data = resp.json()
    # 排程 log 友善: 結構化 stdout
    print(json.dumps({
        "ok": True,
        "job_id": data["job_id"],
        "state": data["state"],
        "status_url": f"{args.server.rstrip('/')}{data['status_url']}",
        "submitted": {
            "source_type": canonical,
            "source": source_field,
            "options": options,
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
