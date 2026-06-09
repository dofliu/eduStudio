"""啟動自檢 (D-5) — 印清楚的綠/紅讓自架者一眼知道缺什麼。

server 啟動時跑一輪環境自檢：ffmpeg/ffprobe、字型、GEMINI key。`/health`
端點已回同類診斷（給 monitoring / Docker healthcheck 拉），但那是「要主動打
端點才看得到」；自架者第一次 `docker compose up` / `python -m server.main`
最常踩的雷（沒裝 ffmpeg、容器缺 Noto 字型、忘了設 key）應該在 **啟動 log**
就一眼可見，不必先會打 /health。

設計：
- `collect_checks()` 純函式蒐集結果（不印、不碰 stdout）＝好測。
- `format_report()` 把結果排成綠/紅文字。
- `print_startup_selfcheck()` 啟動時呼叫：印報告、回傳結果。
- **不阻擋啟動**：缺東西只警告（server 仍可瀏覽/設定），讓缺項一目了然即可。
  critical 缺項（ffmpeg/字型）會多印一行醒目總結指引去補。
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

from core.config import (
    get_fallback_font_path,
    get_font_path,
    get_gemini_api_key,
    get_mono_font_path,
)


@dataclass(frozen=True)
class Check:
    """單項自檢結果。

    - `ok`：是否通過。
    - `critical`：True＝缺了核心功能（影片產製）不能跑 → 紅 ❌；
      False＝選用，缺了只黃字 ⚠ 警告（server 仍可跑）。
    """

    name: str
    ok: bool
    detail: str
    critical: bool


def collect_checks() -> list[Check]:
    """蒐集啟動自檢結果（純函式，不印、不碰 stdout）。"""
    checks: list[Check] = []

    # ffmpeg / ffprobe — render / concat / 探測秒數都靠它（皆以 bare command
    # 經 subprocess 呼叫，吃 PATH），缺了不能產影片 → critical。
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        checks.append(
            Check(
                name=tool,
                ok=path is not None,
                detail=path or "PATH 中找不到（影片 render 會失敗，請安裝 ffmpeg）",
                critical=True,
            )
        )

    # 字型 — 缺了渲染會缺字（豆腐方塊）甚至失敗 → critical。容器常缺 Noto CJK，
    # 設 CLAUDE_*_FONT_PATH 指向任一可用 .ttf 即可。
    for label, getter in (
        ("font_main", get_font_path),
        ("font_fallback", get_fallback_font_path),
        ("font_mono", get_mono_font_path),
    ):
        p = getter()
        exists = os.path.exists(p)
        checks.append(
            Check(
                name=label,
                ok=exists,
                detail=p if exists else f"{p}（不存在，設對應 CLAUDE_*_FONT_PATH 指向可用 .ttf）",
                critical=True,
            )
        )

    # GEMINI_API_KEY — 缺了能瀏覽/改設定但不能呼叫 Gemini 產內容，故只黃字警告。
    key = get_gemini_api_key()
    checks.append(
        Check(
            name="gemini_api_key",
            ok=bool(key),
            detail="已設定" if key else "未設定（可瀏覽/設定，但無法呼叫 Gemini 產生內容）",
            critical=False,
        )
    )

    return checks


def format_report(checks: list[Check]) -> str:
    """把自檢結果排成綠/紅多行文字（給 startup log）。"""
    lines = ["[server] 啟動自檢 (D-5):"]
    for c in checks:
        mark = "✅" if c.ok else ("❌" if c.critical else "⚠ ")
        lines.append(f"  {mark} {c.name}: {c.detail}")
    missing_critical = [c.name for c in checks if not c.ok and c.critical]
    if missing_critical:
        lines.append(
            f"  ⛔ 缺少核心相依：{', '.join(missing_critical)} — "
            "影片產製會失敗，請先補齊（見 README / docs/DEPLOYMENT.md）。"
        )
    return "\n".join(lines)


def print_startup_selfcheck() -> list[Check]:
    """server 啟動時呼叫：印自檢報告，回傳結果（呼叫端/測試可用）。"""
    checks = collect_checks()
    print(format_report(checks))
    return checks
