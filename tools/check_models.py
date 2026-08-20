#!/usr/bin/env python3
"""check_models.py — 模型 id 自我健檢（C-5）。

把系統登錄的 Gemini model id（角色登錄表 + 設定頁可選清單 + 專用 API 型號 + 設定頁實際覆寫）
全部蒐齊，再呼叫 ``client.models.list()`` 比對這些 id 在你這把 key 底下**是否真的還存在**，
把不存在的 id 標紅。這 repo 有過用 preview id 結果 404 的前科（見 ``core/infocards/models.py``
註解），自架者換 key / Google 改版後可跑這支自查，免得排版到一半才炸。

設計（offline-first 友善）：
- 蒐集 + 比對拆成純函式（``collect_configured_models`` / ``evaluate``），**不打 API、好測**。
- 只有 ``main()`` 真的建 client 呼叫 ``models.list()``；沒設 GEMINI_API_KEY 就只印「會用到哪些 id」
  並提醒（exit 2），不假裝健檢過。
- 只查 **gemini** provider 的角色（``tts`` 等非 Gemini 後端跳過，不是 models.list 能驗的東西）。

使用：
    python tools/check_models.py            # 人類可讀報告，全部存在 → exit 0，有缺 → exit 1
    python tools/check_models.py --json      # 機器可讀（CI / 其他工具串接）

並進 M 軸：蒐集來源已含角色登錄表（``core/models.py``）全部角色，換代後這支即同時驗新表。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 本檔在 tools/ 底下，加 parent 到 sys.path 才能 import 上層模組。
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import config, models  # noqa: E402
from core.infocards import models as infocard_models  # noqa: E402

# models.list() 回的 name 帶 ``models/`` 前綴；蒐集端與 API 端都正規化成裸 id 比對。
_MODELS_PREFIX = "models/"


def _normalize(model_id: str) -> str:
    """裸 model id（去掉 ``models/`` 前綴、去空白），給比對用。"""
    mid = (model_id or "").strip()
    if mid.startswith(_MODELS_PREFIX):
        mid = mid[len(_MODELS_PREFIX):]
    return mid


def collect_configured_models() -> list[dict]:
    """蒐集系統實際會送去 Gemini 的 model id（純函式，不打 API）。

    來源：
    1. **角色登錄表**（``core/models.py``）— 對每個角色 ``resolve()``，這已涵蓋設定頁
       逐角色 ``model_roles`` 覆寫 + legacy ``text_model``/``image_model`` 覆寫 + 內建預設。
       只收 provider == gemini 的角色（``tts`` 等跳過）。
    2. **設定頁可選清單**（``core/infocards/models.py`` 的 ``TEXT_MODELS`` / ``IMAGE_MODELS``）
       — UI 下拉讓使用者挑的全部 id，就算現在沒選中也該存在（免得選了才 404）。
    3. **專用 API 型號**（``SPECIALIZED_MODELS``）— 尚未接線，但設定頁會顯示的 Live / TTS /
       Omni model 也必須確定存在，避免未來接線時使用過期 id。

    回傳：每個**唯一** id 一筆 ``{"id": str, "sources": [str, ...]}``（sources 已去重排序），
    全表依 id 排序，輸出穩定。
    """
    by_id: dict[str, set[str]] = {}

    def _add(model_id: str, source: str) -> None:
        mid = _normalize(model_id)
        if not mid:
            return
        by_id.setdefault(mid, set()).add(source)

    # 1. 角色登錄表（含設定頁覆寫，透過 resolve）。
    for role in models.all_roles():
        provider, mid = models.resolve(role)
        if provider != models.PROVIDER_GEMINI:
            continue  # tts/本機 provider 非 models.list 能驗，跳過。
        _add(mid, f"角色 {role}")

    # 2. 設定頁文字/圖片下拉可選清單。
    for key, spec in infocard_models.TEXT_MODELS.items():
        _add(spec["id"], f"設定頁下拉 文字/{key}")
    for key, spec in infocard_models.IMAGE_MODELS.items():
        _add(spec["id"], f"設定頁下拉 圖片/{key}")
    for key, spec in infocard_models.SPECIALIZED_MODELS.items():
        _add(spec["id"], f"設定頁資訊 專用/{key}")

    return [
        {"id": mid, "sources": sorted(by_id[mid])}
        for mid in sorted(by_id)
    ]


def evaluate(configured: list[dict], available_ids: set[str]) -> list[dict]:
    """比對蒐集到的 id 與 API 可用 id（純函式）。

    Args:
        configured: ``collect_configured_models()`` 的輸出。
        available_ids: ``models.list()`` 回的裸 id 集合（已 ``_normalize``）。

    回傳：每筆加上 ``ok``（bool），順序沿用 ``configured``。
    """
    norm_available = {_normalize(a) for a in available_ids}
    result = []
    for entry in configured:
        result.append({
            "id": entry["id"],
            "sources": entry["sources"],
            "ok": entry["id"] in norm_available,
        })
    return result


def fetch_available_model_ids(client=None) -> set[str]:
    """呼叫 ``client.models.list()`` 取回這把 key 可用的裸 model id 集合。

    ``client`` 可注入（測試用 fake）；省略則用 ``core.config`` 金鑰建真 client。
    無金鑰 → ``RuntimeError``（呼叫端決定如何呈現）。
    """
    if client is None:
        key = config.get_gemini_api_key()
        if not key:
            raise RuntimeError("缺少 GEMINI_API_KEY（設定頁或環境變數）")
        from google import genai
        client = genai.Client(api_key=key)

    ids: set[str] = set()
    for m in client.models.list():
        name = getattr(m, "name", None) or getattr(m, "id", None) or ""
        if name:
            ids.add(_normalize(name))
    return ids


def _print_report(results: list[dict]) -> None:
    """人類可讀報告。"""
    missing = [r for r in results if not r["ok"]]
    print(f"模型 id 健檢：共 {len(results)} 個設定中的 id，{len(missing)} 個在 API 找不到。\n")
    for r in results:
        mark = "✅" if r["ok"] else "❌"
        print(f"  {mark} {r['id']}")
        print(f"       來源：{'、'.join(r['sources'])}")
    if missing:
        print("\n⚠ 下列 id 在你這把 key 的 models.list() 找不到（會 404）："
              "請改設定頁的對應角色/下拉，或更新 core/models.py 預設表：")
        for r in missing:
            print(f"  - {r['id']}（{'、'.join(r['sources'])}）")
    else:
        print("\n全部設定中的 model id 都還在，沒有 404 風險。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="eduStudio 模型 id 自我健檢")
    parser.add_argument("--json", action="store_true", help="輸出 JSON（機器可讀）")
    args = parser.parse_args(argv)

    configured = collect_configured_models()

    try:
        available = fetch_available_model_ids()
    except RuntimeError as exc:
        # 沒金鑰：只印會用到哪些 id，不假裝驗過。
        if args.json:
            print(json.dumps(
                {"error": str(exc), "configured": configured},
                ensure_ascii=False, indent=2,
            ))
        else:
            print(f"無法連線 API 健檢：{exc}\n以下是設定中會用到的 model id（未驗證存在）：\n")
            for entry in configured:
                print(f"  • {entry['id']}（{'、'.join(entry['sources'])}）")
        return 2

    results = evaluate(configured, available)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print_report(results)

    return 1 if any(not r["ok"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
