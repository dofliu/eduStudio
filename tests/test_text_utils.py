"""core.text_utils 測試 — strip_latex / clean_json_escapes 純函式。"""
from __future__ import annotations

from core.text_utils import clean_json_escapes, strip_latex


# ---------- strip_latex ----------

class TestStripLatex:
    def test_empty_returns_empty(self):
        assert strip_latex("") == ""
        assert strip_latex(None) is None  # type: ignore[arg-type]

    def test_plain_text_unchanged(self):
        assert strip_latex("這是一段純文字, 沒有 LaTeX。") == "這是一段純文字, 沒有 LaTeX。"

    def test_frac_converted(self):
        assert strip_latex(r"\frac{a}{b}") == "(a)/(b)"
        assert strip_latex(r"\frac{1}{s+3}") == "(1)/(s+3)"

    def test_sqrt_converted(self):
        assert strip_latex(r"\sqrt{2}") == "根號(2)"

    def test_text_wrapper_removed(self):
        assert strip_latex(r"\text{hello}") == "hello"

    def test_vec_hat_bar_removed(self):
        assert strip_latex(r"\vec{a}") == "a"
        assert strip_latex(r"\hat{x}") == "x"
        assert strip_latex(r"\bar{y}") == "y"

    def test_greek_letters(self):
        assert "α" in strip_latex(r"\alpha")
        assert "β" in strip_latex(r"\beta")
        assert "ζ" in strip_latex(r"\zeta")
        assert "ω" in strip_latex(r"\omega")
        # 大寫
        assert "Σ" in strip_latex(r"\Sigma") or "Σ" in strip_latex(r"\Sigma")

    def test_symbols(self):
        assert "×" in strip_latex(r"a \times b")
        assert "≤" in strip_latex(r"x \leq y")
        assert "≥" in strip_latex(r"x \geq y")
        assert "∞" in strip_latex(r"\infty")

    def test_math_functions(self):
        # \sin → sin (反斜線去掉)
        assert strip_latex(r"\sin(x)") == "sin(x)"
        assert strip_latex(r"\cos(\theta)") == "cos(θ)"

    def test_subscript_brace_with_identifiers(self):
        # preserve_identifiers=True 時 _{xx} → _xx 保留底線
        assert strip_latex(r"x_{ij}", preserve_identifiers=True) == "x_ij"

    def test_subscript_brace_default_collapses(self):
        # 預設 (考卷 / 物理) 變數下標會折疊: x_{ij} → x_ij → xij
        # 這對 F_A → FA 是對的, 對程式碼 text_utils 是錯的, 故 preserve_identifiers 開關存在
        assert strip_latex(r"x_{ij}") == "xij"

    def test_superscript_brace(self):
        assert strip_latex(r"x^{2}") == "x^2"

    def test_variable_subscript_collapse(self):
        # F_A → FA (預設 preserve_identifiers=False)
        assert strip_latex("F_A") == "FA"
        assert strip_latex("ω_n") == "ωn"

    def test_preserve_identifiers_keeps_underscore(self):
        # 給 repo / 文件用, 不要把 text_utils 變成 textutils
        assert strip_latex("text_utils", preserve_identifiers=True) == "text_utils"
        assert strip_latex("solve_pdf", preserve_identifiers=True) == "solve_pdf"

    def test_dollar_wrap_removed(self):
        assert strip_latex(r"$x = 1$") == "x = 1"
        assert strip_latex(r"$$y = 2$$") == "y = 2"

    def test_paren_wrap_removed(self):
        assert strip_latex(r"\(z = 3\)") == "z = 3"
        assert strip_latex(r"\[w = 4\]") == "w = 4"


# ---------- clean_json_escapes ----------

class TestCleanJsonEscapes:
    def test_legal_escapes_unchanged(self):
        # \" \n \t \\ 都是合法 JSON 轉義, 不該被加倍
        legal = r'"hello\n\tworld\\\""'
        assert clean_json_escapes(legal) == legal

    def test_illegal_alpha_escape_doubled(self):
        # LLM 偶爾在 JSON 字串裡夾 \alpha (LaTeX), 該被加倍變 \\alpha 才能 json.loads
        result = clean_json_escapes(r'"\alpha"')
        assert result == r'"\\alpha"'

    def test_illegal_unicode_short_doubled(self):
        # \uABC (只 3 位 hex) 不合法, 該加倍
        result = clean_json_escapes(r'"\uABC"')
        assert result == r'"\\uABC"'

    def test_legal_unicode_unchanged(self):
        # 中 (4 位 hex) 合法, 不動
        legal = r'"中"'
        assert clean_json_escapes(legal) == legal

    def test_double_backslash_stays_double(self):
        # \\ 已合法, 第二個 \ 不該再被加倍
        assert clean_json_escapes(r'"\\\\path"') == r'"\\\\path"'

    def test_realistic_llm_output(self):
        """模擬 Gemini 在 JSON 裡夾混 LaTeX 的常見 bug。

        已修補: 將 LaTeX command 類型（如 \\beta / \\theta / \\times / \\frac）
        也補為 \\beta / \\times / \\frac 讓 json.loads 不會吃掉控制字元.
        """
        bad = r'"\alpha + \beta = \gamma; \theta \times r"'
        good = clean_json_escapes(bad)
        assert r"\\alpha" in good
        assert r"\\gamma" in good
        assert r"\\beta" in good
        assert r"\\theta" in good
        assert r"\\times" in good
        assert clean_json_escapes(r'"\frac{1}{2}"') == r'"\\frac{1}{2}"'
