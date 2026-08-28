"""LaTeX → 純文字 / JSON escape 修補 — 從 solve.py 抽出來的純函式。

之前 slide_ingest.py 是這樣 import 這兩個函式的:
    from solve import strip_latex, clean_json_escapes

這條 import 會連帶觸發 solve.py 模組頂層的 sys.stdout.reconfigure 副作用,
而且把純文字工具與 Gemini API 邏輯耦在同一個檔。把它們搬到 core.text_utils
之後 solve.py 也從這裡 re-export, 維持向後相容 (任何舊 code 仍可 from solve import ...)。

兩個函式行為完全照抄 solve.py, 沒有改動。
"""
from __future__ import annotations

import re


# ---------- LaTeX 符號對照 ----------
# Gemini 2.5 愛用 LaTeX, 但黑板顯示 + TTS 都要純文字, 故統一還原。
_GREEK_MAP = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
}
_SYMBOL_MAP = {
    "times": "×", "div": "÷", "pm": "±", "mp": "∓", "cdot": "·",
    "circ": "°", "degree": "°", "deg": "°", "approx": "≈", "neq": "≠",
    "leq": "≤", "geq": "≥", "infty": "∞", "partial": "∂", "nabla": "∇",
    "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
}
_LATEX_COMMANDS = {
    *(cmd.lower() for cmd in _GREEK_MAP.keys()),
    *(cmd.lower() for cmd in _SYMBOL_MAP.keys()),
    # b
    "beta", "bar", "begin", "end", "bmatrix", "pmatrix", "vmatrix", "cases",
    "boldsymbol", "bf", "bold", "bullet", "big", "bigg", "bmod", "box", "binom",
    "bot", "backslash", "bowtie", "breve",
    # f
    "frac", "cfrac", "dfrac", "tfrac", "flat", "forall", "frown", "fbox",
    # n
    "nu", "nabla", "neq", "ne", "not", "neg", "norm", "notin", "ni", "natural",
    "nrightarrow", "nleftarrow", "newline", "noindent", "nonumber",
    # r
    "rho", "right", "rangle", "rbrace", "rbracket", "rfloor", "rceil", "root", "rm", "re", "real",
    # t
    "theta", "tau", "times", "tan", "tanh", "text", "textbf", "textit", "textrm", "textsf",
    "texttt", "textnormal", "textstyle", "tilde", "to", "top", "triangle", "tag", "tfrac",
    # 常用符號與數學函數
    "sqrt", "vec", "hat", "dot", "ddot",
    "sin", "cos", "cot", "sec", "csc", "log", "ln", "exp", "lim", "sum", "int", "iint", "iiint", "oint",
    "sinh", "cosh", "arcsin", "arccos", "arctan", "min", "max", "inf", "sup", "det", "dim",
    "left", "quad", "qquad", "over", "cdots", "ldots", "vdots", "ddots",
    "cong", "equiv", "sim", "simeq", "propto", "le", "ge", "ll", "gg",
    "subset", "supset", "subseteq", "supseteq", "in", "cap", "cup", "setminus",
    "wedge", "vee", "oplus", "otimes", "odot",
}



def strip_latex(text: str, *, preserve_identifiers: bool = False) -> str:
    """把 LLM 夾帶的 LaTeX 標記還原成黑板/TTS 可讀的純文字。

    preserve_identifiers=False (預設,給考卷 / 物理數學內容):
        套用「變數下標」規則 F_A → FA, ω_n → ωn, F_R_x → FRx
        因為材料力學 / 動力學的變數寫法 F_A 在黑板要顯示 FA, TTS 也要唸成「F A」。

    preserve_identifiers=True (給 repo / 文件 / 程式碼上下文):
        跳過「變數下標」規則, 保留 text_utils / solve_pdf / cfg_strength 等 Python
        識別字的底線, 否則 narration 會把 core/text_utils.py 念成 textutils.py。
        其他 LaTeX 殼 (\\frac, \\sqrt, $...$ 等) 仍會清掉。
    """
    if not text:
        return text
    # \frac{a}{b} → (a)/(b)
    text = re.sub(r'\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}', r'(\1)/(\2)', text)
    # \sqrt{a} → 根號(a)
    text = re.sub(r'\\sqrt\s*\{([^{}]*)\}', r'根號(\1)', text)
    # \text{xxx} → xxx
    text = re.sub(r'\\text\s*\{([^{}]*)\}', r'\1', text)
    # \vec{a} / \hat{a} / \bar{a} → a
    text = re.sub(r'\\(?:vec|hat|bar|tilde|dot|ddot)\s*\{([^{}]*)\}', r'\1', text)
    # 希臘字母 (大寫用首字母大寫判斷)
    def greek_sub(m):
        name = m.group(1)
        if name.lower() in _GREEK_MAP:
            ch = _GREEK_MAP[name.lower()]
            return ch.upper() if name[0].isupper() else ch
        return m.group(0)
    text = re.sub(r'\\([A-Za-z]+)', lambda m: _SYMBOL_MAP.get(m.group(1), m.group(0)), text)
    text = re.sub(r'\\([A-Za-z]+)', greek_sub, text)
    # 數學函數 \sin \cos \tan \log \ln 等 → 拿掉反斜線
    text = re.sub(r'\\(sin|cos|tan|cot|sec|csc|log|ln|exp|lim|sum|int|sinh|cosh|tanh|arcsin|arccos|arctan|min|max)\b', r'\1', text)
    # 上下標 _{xxx} → _xxx, ^{xxx} → ^xxx (保留一層括號的情況)
    text = re.sub(r'_\{([^{}]*)\}', r'_\1', text)
    text = re.sub(r'\^\{([^{}]*)\}', r'^\1', text)
    # 變數下標 F_A → FA — 對程式碼識別字 (text_utils, solve_pdf) 是錯的, 故 opt-out
    if not preserve_identifiers:
        text = re.sub(r'([A-Za-zα-ωΑ-Ω])_(?=[A-Za-z0-9])', r'\1', text)
    # $...$ / $$...$$ / \(...\) / \[...\] 外殼去掉
    text = re.sub(r'\$\$([^$]*)\$\$', r'\1', text)
    text = re.sub(r'\$([^$\n]*)\$', r'\1', text)
    text = re.sub(r'\\\((.*?)\\\)', r'\1', text)
    text = re.sub(r'\\\[(.*?)\\\]', r'\1', text)
    # 剩餘散落的 \xxx (未知命令) — 保留字母去掉反斜線
    text = re.sub(r'\\([a-zA-Z]+)', r'\1', text)
    # 殘留的 { } 若內容單純就去掉
    text = re.sub(r'\{([^{}]*)\}', r'\1', text)
    return text


def clean_json_escapes(text: str) -> str:
    """修正 LLM 產生的非法 JSON 轉義 (如 \\alpha, \\frac, \\(, \\theta 等 LaTeX)。

    JSON 合法反斜線轉義僅: \\" \\\\ \\/ \\b \\f \\n \\r \\t \\uXXXX
    規則: 只把「非已配對」的單一反斜線加倍 (用 negative lookbehind 避開 \\\\ 後接字元的情況),
    且 \\u 後需 4 位 hex 才算合法, 否則也加倍。
    """
    # 第一步: \u 後若不是 4 位 hex, 把 \ 加倍
    text = re.sub(r'(?<!\\)\\u(?![0-9a-fA-F]{4})', r'\\\\u', text)

    # 第二步: 只保留 JSON 真實合法 escape，其餘全補一個反斜線。
    # 但對 b/f/n/r/t 前綴，要避免把 \beta / \times / \frac 當成合法控制字元吞掉：
    # 僅保留「單一 escape 字元」(例如 \n), 若接著延展成 LaTeX 命令則補逃逸。
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "\\":
            out.append(text[i])
            i += 1
            continue

        if i + 1 >= n:
            out.append("\\\\")
            i += 1
            continue

        ch = text[i + 1]
        if ch in {'"', "/", "\\"}:
            out.append(f"\\{ch}")
            i += 2
            continue
        if ch == "u":
            # 這裡只會是合法情況；非法已在第一步補掉
            out.append(f"\\{text[i+1:i+6] if i+6 <= n else text[i+1:]}")
            i += min(6, n - i)
            continue
        if ch in {"b", "f", "n", "r", "t"}:
            # 先看是否是 "\command" 的開頭，例如 \beta、\times、\frac、\rho、\nabla
            j = i + 1
            k = j + 1
            while k < n and text[k].isalpha():
                k += 1
            token = text[j:k]
            # 對於 b/f/r，若後面接字母（len > 1），LLM 幾乎必為 LaTeX/單字轉義，絕非退格/換頁/CR
            # 對於 t/n，若符合已知 LaTeX 指令（如 \theta, \times, \nu, \nabla, \to 等）則補逃逸；否則保留合法 \n, \t
            is_latex = False
            if len(token) > 1:
                if ch in {"b", "f", "r"}:
                    is_latex = True
                elif token.lower() in _LATEX_COMMANDS:
                    is_latex = True

            if is_latex:
                out.append(f"\\\\{token}")
                i = k
                continue
            out.append(f"\\{ch}")
            i += 2
            continue


        # 其餘都不是 JSON 合法 escape：補一個反斜線交給 JSON 可解析為純字面字元
        out.append(f"\\\\{ch}")
        i += 2

    return "".join(out)
