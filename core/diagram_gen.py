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

import ast
import os
import re
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    pass


# ============================================================
# AST allowlist — Gemini code 必須先過 AST 檢查才能 exec
# ============================================================

# 允許的頂層 module — matplotlib / numpy / math / scipy 是工程圖必要
# 任何其他 import 一律拒絕 (擋 os / sys / subprocess / socket / requests etc)
_ALLOWED_IMPORT_ROOTS: frozenset[str] = frozenset({
    "matplotlib",
    "numpy",
    "np",        # 雖然 np 是 alias 不是 module, 加進來防 caller 寫 import np
    "math",
    "scipy",
})

# 禁止的 builtin call (即使 import 過了, 這些 call 仍然危險)
_BLOCKED_BUILTINS: frozenset[str] = frozenset({
    "__import__",
    "eval",
    "exec",
    "compile",
    "open",      # 不讓 Gemini code 自己讀寫檔, 由 matplotlib savefig 接管
    "input",
    "globals",
    "locals",
    "vars",
})


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

    流程 (iter 31 整合完):
        1. _propose_matplotlib_code(spec) → Gemini 產 .py code
        2. _validate_code_ast(code) → AST allowlist 檢查 (擋 import os 等)
        3. _render_matplotlib_diagram(code, out_path) → subprocess exec → PNG

    參數:
        spec: DiagramSpec, kind / description / out_path 必填

    回傳:
        Path: PNG 已寫出的絕對路徑
        None: 任何階段失敗 (圖產不出來不該擋 pipeline, 寧可 step 沒圖)

    錯誤處理 (一律不 raise, 回 None):
        - 必填欄位缺 / out_path 不能 resolve
        - Gemini API 失敗 / 限流 / 空回應
        - AST 檢查不過 (惡意 code / 違反 allowlist)
        - subprocess timeout / 失敗
        - 輸出檔不存在 (matplotlib 沒成功寫檔)
    """
    # 必填欄位檢查 — 容錯到底, 不 raise
    out_path_raw = spec.get("out_path")
    if not out_path_raw:
        return None
    kind = spec.get("kind") or DiagramKind.GENERIC.value
    description = spec.get("description") or ""
    if not description:
        return None

    out_path = Path(out_path_raw)

    # 1. Gemini 提案 code
    try:
        code = _propose_matplotlib_code(spec)
    except Exception:
        return None
    if not code or not code.strip():
        return None

    # 2. AST allowlist 安全檢查
    if not _validate_code_ast(code):
        return None

    # 3. subprocess sandbox 跑出 PNG
    return _render_matplotlib_diagram(code, out_path)


def _propose_matplotlib_code(spec: DiagramSpec) -> str:
    """Gemini call → 回 matplotlib python code (純字串)。

    讀 prompts/diagram_matplotlib.txt 樣板, 套 spec 參數, 餵 Gemini 純文字
    generation. 拿回的 raw text 還要過 AST allowlist 檢查 (generate_diagram
    第 2 步).

    回傳: 完整可 exec 的 python script, 含 `plt.savefig(out_path)` 句
    錯誤: raise (caller 在 generate_diagram 接住回 None)
    """
    # lazy import — google-genai 是核心 dep 但 import 慢
    from google import genai
    from google.genai import types

    from core.config import get_gemini_api_key
    from core.models import TEXT_FAST, resolve_id
    from core.prompts_loader import load_prompt

    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError("缺 GEMINI_API_KEY")

    prompt = load_prompt("diagram_matplotlib").format(
        kind=spec.get("kind") or DiagramKind.GENERIC.value,
        description=spec.get("description", ""),
        width=spec.get("width", DEFAULT_WIDTH),
        height=spec.get("height", DEFAULT_HEIGHT),
        dpi=spec.get("dpi", DEFAULT_DPI),
        out_path=spec["out_path"],   # caller 必填, generate_diagram 已驗
    )

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=resolve_id(TEXT_FAST),
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=0.3,           # 偏保守, 別亂編幾何
            max_output_tokens=2048,    # matplotlib code 不會太長
        ),
    )
    raw = (resp.text or "").strip()
    return _strip_code_fence(raw)


def _strip_code_fence(text: str) -> str:
    """Gemini 偶爾還是包 ```python ... ```, 抓出中間 code 主體。

    跟 prompts/diagram_matplotlib.txt 內「不要 Markdown fence」對照, 但 LLM
    抗指令偶有失靈, 這層 fallback 比 strict reject 友善 (UX)。
    """
    text = text.strip()
    m = re.search(r"```(?:python|py)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def _validate_code_ast(code: str) -> bool:
    """AST 檢查 — 走 allowlist 模式: 只允許 matplotlib / numpy / math / scipy。

    回傳:
        True: code 安全, 可以 subprocess exec
        False: 偵測到惡意 import / call / dunder 繞道 → caller 應拒絕

    檢查內容:
        - Import / ImportFrom: 頂層 module 必須在 _ALLOWED_IMPORT_ROOTS
        - Call: 函式名稱不能是 _BLOCKED_BUILTINS (eval / exec / __import__ etc)
        - **Attribute access (iter 29 加)**: 任何 dunder attribute (例:
          obj.__dict__ / cls.__class__ / mod.__builtins__) 一律 reject. 這
          擋住「藉 dunder 拿到 globals / builtins 繞 allowlist」的攻擊面.
          副作用: matplotlib code 用 dunder 的機率近 0, 安全 trade-off 划算.
        - 不檢查語法正確性 (那是 ast.parse 自己丟 SyntaxError 的事, caller try)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        # 1. import X
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in _ALLOWED_IMPORT_ROOTS:
                    return False

        # 2. from X import Y
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                # `from . import X` 之類, 拒絕 (relative import 不該出現在獨立腳本)
                return False
            root = node.module.split(".")[0]
            if root not in _ALLOWED_IMPORT_ROOTS:
                return False

        # 3. builtin call (eval / exec / open / __import__ 等)
        elif isinstance(node, ast.Call):
            func = node.func
            # `eval(...)` 直接 Name
            if isinstance(func, ast.Name) and func.id in _BLOCKED_BUILTINS:
                return False
            # `getattr(builtins, "eval")(...)` 之類繞過用 Attribute 形式 — 拒絕 getattr 整批
            # (簡單嚴格: 直接擋 getattr / setattr / delattr)
            if isinstance(func, ast.Name) and func.id in ("getattr", "setattr", "delattr"):
                return False

        # 4. dunder attribute access — iter 29 加, 擋 obj.__dict__ / cls.__class__
        #    / mod.__builtins__ 等繞道. matplotlib / numpy / scipy 正常用法都
        #    不會碰 dunder, 整批 reject 是合理 trade-off.
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                return False

    return True


def _render_matplotlib_diagram(code: str, out_path: Path, timeout: int = 30) -> Path | None:
    """subprocess exec matplotlib code, 寫 PNG 到 out_path。

    安全措施 (跟 docs/engineering-diagram-design.md 對齊):
        - subprocess.run(["python", "-c", code], timeout=30, env={...受限})
        - MPLBACKEND=Agg: 不開 GUI (CI / Docker / 無 X server 都可跑)
        - 不傳 GEMINI_API_KEY / OAuth 等敏感 env 進子 process

    回傳:
        Path: 寫檔成功 (out_path 存在且非空)
        None: subprocess 失敗 / timeout / 沒寫出檔 / 寫出檔但是空的
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 確保 caller 沒在 out_path 留舊檔混淆「成功 / 失敗」判斷
    if out_path.exists():
        out_path.unlink()

    # 子 process env: 只給能跑 matplotlib 必要的, 不繼承 caller 整套
    # PYTHONPATH 空避免 caller 環境的可疑 module 被 import; PATH 仍要 (找 python)
    child_env = {
        "MPLBACKEND": "Agg",      # headless 後端, 不需 GUI
        "PATH": __import__("os").environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": "",
        "LANG": "C.UTF-8",
    }

    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            timeout=timeout,
            env=child_env,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    except (OSError, ValueError):
        return None

    if result.returncode != 0:
        # 留 stderr 給 caller debug (這層不 log, log 是 caller / pipeline 的責任)
        return None

    if not out_path.exists() or out_path.stat().st_size == 0:
        return None

    return out_path
