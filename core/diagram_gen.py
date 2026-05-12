"""工程圖 AI 輔助 (v4 階段 2 E) — Gemini 產 matplotlib code → 本機 exec → PNG。

scaffold 階段 (iter 18): schema + function 簽名, 還沒實作。
- iter 19: _render_matplotlib_diagram + subprocess sandbox + AST 檢查 + tests
- iter 20: _propose_matplotlib_code (Gemini call) + tests
- iter 21: 整合 pipeline.py step image 欄位

設計重點:
- Gemini code exec 走 subprocess + timeout + env={}, AST allowlist 檢查
- 失敗一律回 None 不擋 pipeline (圖跑不出來不該整支影片廢)
- 詳細設計見 docs/engineering-diagram-design.md
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    pass


# ============================================================
# Schema
# ============================================================


class DiagramKind(str, Enum):
    """工程圖類別 — 對應 prompt template 跟 matplotlib 範例。"""

    FREE_BODY = "free_body"             # 自由體圖 (梁 / 桁架受力)
    BENDING_MOMENT = "bending_moment"   # 彎矩圖 M-x
    SHEAR = "shear"                     # 剪力圖 V-x
    STRESS_STRAIN = "stress_strain"     # 應力-應變曲線
    BLOCK_DIAGRAM = "block_diagram"     # 控制系統方塊圖
    CIRCUIT = "circuit"                 # 電路圖 (簡單)
    GENERIC = "generic"                 # 其他 — 純文字描述


class DiagramSpec(TypedDict, total=False):
    """單張工程圖規格 — caller 填好餵 generate_diagram()。

    total=False 因為 width/height/dpi 都有預設值, caller 不必填全。
    """

    kind: str                # DiagramKind.value
    description: str         # 中文 / 英文描述, 給 Gemini 看
    out_path: str            # 輸出 PNG 絕對路徑
    width: int               # 預設 800
    height: int              # 預設 600
    dpi: int                 # 預設 100


# 預設 spec 值
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 600
DEFAULT_DPI = 100


# ============================================================
# Main function — scaffold, raise NotImplementedError
# ============================================================


def generate_diagram(spec: DiagramSpec) -> Path | None:
    """產一張工程圖, 回 PNG 路徑。

    流程 (iter 19/20 後):
        1. _propose_matplotlib_code(spec) → Gemini 產 .py code
        2. _validate_code_ast(code) → AST allowlist 檢查 (擋 import os 等)
        3. _render_matplotlib_diagram(code, out_path) → subprocess exec → PNG

    參數:
        spec: DiagramSpec, kind / description / out_path 必填

    回傳:
        Path: PNG 已寫出的絕對路徑
        None: 任何階段失敗 (圖產不出來不該擋 pipeline, 寧可 step 沒圖)

    錯誤處理 (一律不 raise, 回 None):
        - Gemini API 失敗 / 限流
        - AST 檢查不過 (惡意 code)
        - subprocess timeout / 失敗
        - 輸出檔不存在 (matplotlib 沒成功寫檔)
    """
    raise NotImplementedError("iter 19+ 補實作")


def _propose_matplotlib_code(spec: DiagramSpec) -> str:
    """Gemini call → 回 matplotlib python code (純字串)。

    iter 20 實作。

    回傳: 完整可 exec 的 python script, 含 `plt.savefig(out_path)` 句。
    錯誤: raise (caller 在 generate_diagram 接住回 None)。
    """
    raise NotImplementedError("iter 20 補實作 (Gemini + prompts/diagram_matplotlib.txt)")


def _validate_code_ast(code: str) -> bool:
    """AST 檢查 — 只允許 matplotlib / numpy / math import, 擋 os / sys / subprocess。

    iter 19 實作。

    回傳:
        True: 安全
        False: 偵測到惡意 import / call → caller 應拒絕 exec

    白名單 (允許):
        - matplotlib.* / numpy / math / scipy
        - 內建 type / list / dict / range / etc
    黑名單 (拒絕):
        - import os / sys / subprocess / socket / urllib / requests
        - __import__ / eval / exec / compile
        - open() (除非寫 out_path)
    """
    raise NotImplementedError("iter 19 補實作 (ast.walk + node 類型檢查)")


def _render_matplotlib_diagram(code: str, out_path: Path, timeout: int = 30) -> Path | None:
    """subprocess exec matplotlib code, 寫 PNG 到 out_path。

    iter 19 實作。

    安全措施:
        - subprocess.run(["python", "-c", code], timeout=30, env={})
        - 不開網路 (env 清空)
        - 失敗 / timeout / 找不到輸出檔 → None

    回傳:
        Path: 寫檔成功
        None: 失敗
    """
    raise NotImplementedError("iter 19 補實作")
