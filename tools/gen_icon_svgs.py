#!/usr/bin/env python3
"""V2 執行包 — 讀 manifest 組 Gemini prompt, 產 25 個扁平 SVG icon。

為什麼是這支腳本: `assets/icon_library/manifest.json` 已定義 25 個 icon
(keyword / position / size), 但磁碟上 0 個 .svg → icon_picker 命中也疊不出來
(渲染端 require_file_exists=True 會過濾缺檔)。V2 = 把這 25 個 SVG 生出來。

SVG 是「文字格式」, 用 Gemini **文字模型** (gemini-2.5-flash) 產 SVG 原始碼即可,
**不吃 image generation 額度** (那是 SONG track 真實生圖才用的 gemini-2.5-flash-image)。

安全設計 (offline-first):
- **預設 dry-run**: 只印 prompt 與目標路徑, 不呼叫任何 API、不寫檔。
- `--execute` 才呼叫 Gemini 產 SVG 並落檔。
- 產出的每個 SVG **都要人工 review** (風格一致 / 無多餘文字 / 無版權圖樣) —
  這步不可省 (硬規則: AI 產出不可未經 review 當最終)。腳本落檔後印 review checklist,
  **不自動 commit**, 由劉老師 review 後手動 commit。

用法:
    python tools/gen_icon_svgs.py                 # dry-run, 印全部 prompt
    python tools/gen_icon_svgs.py --only question # dry-run 單一 icon
    python tools/gen_icon_svgs.py --execute       # 真跑 (需 GEMINI_API_KEY)
    python tools/gen_icon_svgs.py --execute --only wind_turbine
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# 路徑常數 (集中, 不寫死 BASE_DIR 散各處 — 對齊 CLAUDE.md 規則 6)
TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_DIR.parent
ICON_LIB_DIR = REPO_ROOT / "assets" / "icon_library"
MANIFEST_PATH = ICON_LIB_DIR / "manifest.json"

# 用文字模型產 SVG markup, 不是 image 模型 (跟 core/config.py GEMINI_MODEL 同值)
MODEL = "gemini-2.5-flash"

# 統一風格規範 (對齊 docs/dynamic-visual-assets-design.md「Gemini prompt 設計指引」)
STYLE_HEADER = """你是專業 SVG icon 設計師。請產生「單一」扁平風格 (flat) SVG icon, 嚴格遵守:

- 根元素 viewBox="0 0 256 256"
- 線條 stroke 用 #1e3a2e (深綠 forest 主色), stroke-width 介於 2~4
- 填充 fill 用 #ffd96b (粉筆黃) 或留白 (fill="none"), 不使用漸層 / 陰影 / 3D / 濾鏡
- 純線條 + 純色填充, 風格類似 Material Icons 或 Feather Icons
- 不含任何中文/英文「說明文字」或標題 label (數學符號如 σ、ε、G(s)、P、I、D、V、M
  可保留, 因為它們是 icon 語意的一部分, 但不要加描述句)
- icon 要 self-explanatory、置中、四周留適當邊距 (約 24px)

只輸出『一個』SVG, 用 ```svg ... ``` code block 包起來, 前後不要多餘解說文字。"""

# 每個 icon 的視覺描述 (繁中, 對齊 design memo 的「Icon 清單」段)。
# 此 dict 的 key 必須涵蓋 manifest 全部 icon (有測試鎖完整性, 防漏)。
VISUAL_DESC: dict[str, str] = {
    # --- generic (10) ---
    "question": "一個圓潤的問號 (?)",
    "exclamation": "一個驚嘆號 (!), 可置於圓形內",
    "lightbulb": "一顆燈泡, 底部有螺紋接頭, 象徵靈感與想法",
    "gear": "一個齒輪 (約 8 齒), 中央有圓孔",
    "warning": "一個等邊三角形警示標誌, 中央一個驚嘆號",
    "checkmark": "一個粗勾 (✓), 可置於圓形內",
    "thinking": "一個側臉頭部輪廓搭配思考泡泡 (內含三個小圓點), 象徵思考",
    "arrow_flow": "三個小方塊由帶箭頭的線水平依序連接, 象徵流程方向",
    "chart_bar": "長條圖, 三到四根高度不一的直條立於底部基線上",
    "network": "多個節點 (圓點) 由直線連接成網狀拓樸",
    # --- wind (5) ---
    "wind_turbine": "三葉片水平軸風力機側視圖, 直立塔架, 葉片呈 Y 形, 不畫雲與地面",
    "scada_dashboard": "一個監控儀表板, 含一個圓形儀表 (gauge) 與一條簡單折線, 象徵即時監控",
    "iec61400": "一份證書/文件外框, 內含一個小風機輪廓, 象徵風能標準規範",
    "nacelle": "風機機艙剖面側視, 矩形外殼內含齒輪箱 (齒輪) 與發電機 (圓柱)",
    "power_curve": "一條功率曲線 (S 形上升後進入平台), 畫於 x-y 座標軸上, 象徵 P-V 出力曲線",
    # --- control (5) ---
    "block_diagram": "兩三個方塊由帶箭頭的線串接, 水平信號流, 系統方塊圖",
    "pid_loop": "一個閉迴路控制圖, 含求和點 (圓圈內加十字)、一個方塊、回授線繞回, 可標 P I D",
    "transfer_function": "一個方塊內含 G(s), 左側輸入箭頭、右側輸出箭頭",
    "step_response": "一條階躍響應曲線 (從 0 跳升後輕微震盪收斂到穩態), 畫於 x-y 座標軸上",
    "bode_plot": "波德圖, 一條隨頻率下降的幅值曲線, 畫於對數座標軸上",
    # --- mechanics (5) ---
    "free_body": "一個方塊 (物體) 搭配數個朝不同方向的受力箭頭, 自由體圖 (FBD)",
    "stress_strain": "應力-應變曲線 (σ-ε): 線性段後轉為彎曲, 畫於 x-y 座標軸上",
    "mohr_circle": "一個圓繪於 σ-τ 座標上 (莫爾圓), 圓心落在 σ 軸",
    "beam_load": "一根水平梁, 兩端為三角形支撐, 上方數個向下的負載箭頭",
    "shear_moment": "一根梁, 下方配一條剪力 (V) 或彎矩 (M) 折線圖, 象徵 V-x / M-x 圖",
}

_SVG_RE = re.compile(r"<svg\b.*?</svg>", re.IGNORECASE | re.DOTALL)


def load_icons(manifest_path: Path = MANIFEST_PATH) -> list[tuple[str, dict]]:
    """讀 manifest, 回 [(name, entry), ...] (保留 manifest 出現順序)。"""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return list(data["icons"].items())


def build_prompt(name: str, entry: dict) -> str:
    """組單一 icon 的 Gemini prompt (風格規範 + 該 icon 語意 + 目標路徑)。"""
    desc = VISUAL_DESC[name]
    keywords = "、".join(entry.get("keywords", []))
    return (
        f"{STYLE_HEADER}\n\n"
        f"要產生的 icon 代號:「{name}」\n"
        f"語意 (narration 命中以下任一關鍵字時會疊這個 icon): {keywords}\n"
        f"視覺描述: {desc}\n"
        f"目標檔名: {entry['icon']}"
    )


def extract_svg(text: str) -> str | None:
    """從 Gemini 回應抽出第一個 <svg>...</svg> 區塊 (忽略 code fence)。抽不到回 None。"""
    if not text:
        return None
    m = _SVG_RE.search(text)
    return m.group(0).strip() if m else None


def _is_valid_svg(svg: str) -> bool:
    """最低限度驗證: 含 <svg 開頭 + viewBox (對齊驗收測試標準)。"""
    return "<svg" in svg.lower() and "viewbox" in svg.lower()


def _dry_run(icons: list[tuple[str, dict]]) -> int:
    print(f"[dry-run] 會產 {len(icons)} 個 SVG icon (不呼叫 API、不寫檔)。\n")
    for name, entry in icons:
        print(f"  - {name:18s} → assets/icon_library/{entry['icon']}")
    print("\n--- 範例 prompt (第一個 icon) ---\n")
    first_name, first_entry = icons[0]
    print(build_prompt(first_name, first_entry))
    print("\n--- 範例 prompt 結束 ---")
    print("\n要真正產生請加 --execute (需 GEMINI_API_KEY)。產完每個 SVG 都要人工 review。")
    return 0


def _execute(icons: list[tuple[str, dict]], out_dir: Path) -> int:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "❌ 缺 GEMINI_API_KEY 環境變數。\n"
            "   Windows: set GEMINI_API_KEY=AIza...\n"
            "   Linux:   export GEMINI_API_KEY=AIza...",
            file=sys.stderr,
        )
        return 2

    from google import genai  # 延遲 import — dry-run / 測試不需要此套件

    client = genai.Client(api_key=api_key)
    ok, fail = [], []
    for name, entry in icons:
        target = out_dir / entry["icon"]
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            resp = client.models.generate_content(
                model=MODEL, contents=build_prompt(name, entry)
            )
            svg = extract_svg(getattr(resp, "text", "") or "")
            if not svg or not _is_valid_svg(svg):
                fail.append((name, "回應抽不到合法 SVG"))
                print(f"  ✗ {name}: 抽不到合法 SVG", file=sys.stderr)
                continue
            target.write_text(svg, encoding="utf-8")
            ok.append(name)
            print(f"  ✓ {name} → {target.relative_to(REPO_ROOT)}")
        except Exception as e:  # 單一 icon 失敗不擋整批 (跟 icon_overlay 設計一致)
            fail.append((name, str(e)))
            print(f"  ✗ {name}: {e}", file=sys.stderr)

    print(f"\n完成: {len(ok)} 成功 / {len(fail)} 失敗。")
    print("\n⚠️  人工 review checklist (硬規則, 不可省):")
    print("   1. 每個 SVG 風格一致 (扁平 / forest 綠 + 粉筆黃 / 無漸層陰影)")
    print("   2. 無多餘說明文字 label")
    print("   3. 無第三方版權圖樣")
    print("   4. 開檔肉眼確認長相對得上 icon 語意")
    print("   review 通過後再手動 git add / commit (腳本不自動 commit)。")
    if fail:
        print(f"\n失敗清單 (可 --only <name> 單獨重產): {[n for n, _ in fail]}")
    return 0 if not fail else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="產 manifest 定義的 25 個扁平 SVG icon")
    ap.add_argument("--execute", action="store_true", help="真跑 (呼叫 Gemini + 寫檔); 預設 dry-run")
    ap.add_argument("--only", metavar="NAME", help="只處理單一 icon (manifest 內的代號)")
    ap.add_argument("--out-dir", type=Path, default=ICON_LIB_DIR, help="輸出根目錄 (預設 assets/icon_library/)")
    args = ap.parse_args(argv)

    icons = load_icons()
    if args.only:
        icons = [(n, e) for n, e in icons if n == args.only]
        if not icons:
            print(f"❌ manifest 找不到 icon: {args.only}", file=sys.stderr)
            return 2

    if args.execute:
        return _execute(icons, args.out_dir)
    return _dry_run(icons)


if __name__ == "__main__":
    raise SystemExit(main())
