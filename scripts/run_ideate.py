#!/usr/bin/env python3
"""scripts/run_ideate.py — 一鍵跑 ideate.py 自動內容企劃 (v4 階段 2 B iter 23)。

讀一個 watched folder 的 PDF, 餵 Gemini Vision 提出影片企劃, 結果寫進
jobs/proposals.json。寫完後開 http://localhost:8000/ui/proposals 可在 UI
逐一核准 / 忽略。

用法:
    # Dry-run: 只掃資料夾看會抓到哪些 PDF (不打 Gemini, 省 API quota)
    python scripts/run_ideate.py exam_pdf D:/path/to/exams --dry-run

    # 真實跑: 打 Gemini Vision 分析
    python scripts/run_ideate.py exam_pdf D:/path/to/exams

    # 多種 source_type:
    python scripts/run_ideate.py slides_pdf D:/lectures
    python scripts/run_ideate.py document   D:/blogs

    # 自訂窗口 (預設 14 天內修改的)
    python scripts/run_ideate.py exam_pdf D:/exams --window-days 60

    # 自訂每份 PDF 最多幾個提案 (預設 3)
    python scripts/run_ideate.py exam_pdf D:/exams --max-proposals 5

需 GEMINI_API_KEY 環境變數 (跟 server / pipeline 用同一把 key)。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


# 讓 scripts/ 內可以 import 上一層的 core / server
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import PROPOSALS_PATH  # noqa: E402
from core.ideate import IdeateConfig, run_ideate  # noqa: E402
from server.jobs import JobStore  # noqa: E402


VALID_SOURCE_TYPES = ("exam_pdf", "slides_pdf", "document")


def main() -> int:
    # Windows cp950 console 對 emoji / 中文 emoji 易炸, 切 UTF-8
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(
        description="一鍵跑 ideate 自動企劃 — 掃 PDF → Gemini Vision → 寫 proposals.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "source_type",
        choices=VALID_SOURCE_TYPES,
        help="想當作哪種輸入: exam_pdf (考題) / slides_pdf (簡報) / document (文件)",
    )
    ap.add_argument(
        "folder",
        help="要掃的資料夾絕對路徑 (例: D:/Teaching/Exams/2026)",
    )
    ap.add_argument(
        "--window-days",
        type=int,
        default=14,
        help="只掃 N 天內修改的檔 (預設 14, dry-run 看不到舊檔請拉大)",
    )
    ap.add_argument(
        "--max-proposals",
        type=int,
        default=3,
        help="每份 PDF 最多產幾個提案 (預設 3)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只掃資料夾不打 Gemini, 看會抓到哪些 PDF (省 API quota)",
    )
    ap.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Gemini 模型 (預設 gemini-2.5-flash)",
    )
    args = ap.parse_args()

    # 確認資料夾存在
    folder_path = Path(args.folder)
    if not folder_path.exists():
        print(f"❌ 資料夾不存在: {args.folder}", file=sys.stderr)
        return 2
    if not folder_path.is_dir():
        print(f"❌ 不是資料夾: {args.folder}", file=sys.stderr)
        return 2

    # 確認 API key (dry-run 不需要)
    if not args.dry_run and not os.environ.get("GEMINI_API_KEY"):
        print(
            "❌ 缺 GEMINI_API_KEY 環境變數。\n"
            "   Windows: set GEMINI_API_KEY=AIza...\n"
            "   Linux:   export GEMINI_API_KEY=AIza...\n"
            "   想跳過 Gemini 先看掃描結果, 加 --dry-run",
            file=sys.stderr,
        )
        return 3

    # 組 config
    config: IdeateConfig = {
        "watched_folders": [
            {
                "path": str(folder_path.resolve()),
                "source_type": args.source_type,
                "scan_window_days": args.window_days,
            }
        ],
        "llm_model": args.model,
        "max_proposals_per_file": args.max_proposals,
        "enabled": True,
    }

    print(f"📋 ideate config:")
    print(f"   folder: {folder_path.resolve()}")
    print(f"   source_type: {args.source_type}")
    print(f"   window: 最近 {args.window_days} 天")
    print(f"   max proposals/file: {args.max_proposals}")
    print(f"   model: {args.model}")
    print(f"   dry-run: {args.dry_run}")
    print(f"   output: {PROPOSALS_PATH}")
    print()

    # 跑!
    store = JobStore()  # 走預設 jobs/ 目錄
    try:
        proposals = run_ideate(
            config=config,
            store=store,
            out_path=PROPOSALS_PATH,
            dry_run=args.dry_run,
            progress=print,
        )
    except Exception as e:
        print(f"❌ 跑 ideate 失敗: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 4

    print()
    if args.dry_run:
        print("✓ Dry-run 完成。確認要的檔都掃到後, 拿掉 --dry-run 跑真正模式。")
    else:
        print(f"✓ 完成。proposals.json 寫到: {PROPOSALS_PATH}")
        if proposals:
            print(f"   {len(proposals)} 個新提案待 review")
            print(f"   開 http://localhost:8000/ui/proposals 逐一核准 / 忽略")
        else:
            print("   (沒新提案 — 可能 dedupe 後全去掉了, 或 Gemini 沒回什麼)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
