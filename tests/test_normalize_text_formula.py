"""iter 93: normalize_text 公式 / 變數 normalize 測試.

用戶實測 GCP Wavenet 念 `uP(t) = Kp × e(t)` 變成 "up t Kp eh t"
(吃掉括號 + 兩字母黏字念英文 + backtick 念「上句點」). 後處理修.
"""
from __future__ import annotations

from tts_backend import normalize_text


class TestStripMarkdown:
    def test_backtick_stripped(self):
        """`func` → func (backtick TTS 念「上句點」)."""
        out = normalize_text("呼叫 `func` 然後返回")
        assert "`" not in out

    def test_asterisk_stripped(self):
        """*emphasis* → emphasis (避免念「星號」)."""
        out = normalize_text("這 *很* 重要")
        assert "*" not in out

    def test_backtick_with_formula(self):
        """用戶實測 case: `uP(t)` = `Kp` × `e(t)`."""
        out = normalize_text("`uP(t)` 等於 `Kp` 乘以 `e(t)`")
        assert "`" not in out
        # 不爆, 內容仍可辨識
        assert "u" in out and "P" in out


class TestFunctionNotation:
    def test_single_letter_function(self):
        """e(t) → e of t."""
        assert "e of t" in normalize_text("e(t)")
        assert "f of x" in normalize_text("f(x)")

    def test_function_in_sentence(self):
        out = normalize_text("誤差 e(t) 隨時間變化")
        assert "e of t" in out

    def test_function_does_not_break_chinese_parens(self):
        """中文括號內中文不該被誤套."""
        out = normalize_text("這(很重要)")
        # 中文括號內超過一字 → 不該 match
        assert "of" not in out or "of" in "這(很重要)"


class TestTwoLetterVariableSplit:
    def test_kp_split(self):
        """Kp → K p (避免念英文 "kuh-puh")."""
        assert "K p" in normalize_text("增益 Kp 設定")

    def test_up_split_lowercase_then_upper(self):
        """uP → u P (用戶實測「up」念英文)."""
        assert "u P" in normalize_text("控制訊號 uP 輸出")

    def test_common_english_words_not_split(self):
        """blacklist: It / If / Of / On 等不該被拆."""
        for word in ["It", "If", "Of", "On", "Is", "We", "He"]:
            out = normalize_text(f"{word} something")
            assert word in out, f"{word} 該保留, 不被拆字: {out}"

    def test_three_letter_word_not_split(self):
        """3 字以上英文詞不該被拆 (Open / The / PhD)."""
        for word in ["Open", "The", "PhD", "USA"]:
            out = normalize_text(f"hello {word} world")
            assert word in out, f"{word} 該保留: {out}"

    def test_all_uppercase_not_split(self):
        """全大寫 (OK / PI / PM) 不該被拆."""
        for word in ["OK", "PI", "PM", "AM"]:
            out = normalize_text(f"value {word}")
            assert word in out

    def test_all_lowercase_not_split(self):
        """全小寫 (me / my / to) 不該被拆."""
        for word in ["me", "my", "to", "the"]:
            out = normalize_text(f"hello {word}")
            assert word in out


class TestCombined:
    def test_real_user_case(self):
        """用戶實測的 narration 整段."""
        narration = (
            "大家可以看到投影片上的核心公式, 比例項的輸出 `uP(t)` "
            "等於 `Kp` 乘以誤差 `e(t)`. 這裡的 `Kp` 就是比例增益."
        )
        out = normalize_text(narration)
        # backtick 全部沒了
        assert "`" not in out
        # uP 拆成 u P
        assert "u P" in out
        # Kp 拆成 K p
        assert "K p" in out
        # e(t) → e of t
        assert "e of t" in out

    def test_chained_split_then_function(self):
        """uP(t) 該先拆成 u P(t), 再轉成 u P of t (兩步串聯)."""
        out = normalize_text("uP(t)")
        # 完整應該變 "u P of t"
        assert "u P" in out
        assert "of t" in out, f"P(t) 該被轉成 P of t, 實際: {out!r}"

    def test_chained_in_full_formula(self):
        """uP(t) = Kp × e(t) 完整 chain."""
        out = normalize_text("uP(t) = Kp × e(t)")
        # uP(t) → "u P of t"
        assert "u P of t" in out, f"{out!r}"
        # e(t) → "e of t"
        assert "e of t" in out, f"{out!r}"

    def test_preserves_chinese_content(self):
        """改造完中文內容該完整保留."""
        out = normalize_text("這裡的 `Kp` 就是比例增益")
        assert "這裡的" in out
        assert "比例增益" in out

    def test_empty_and_whitespace(self):
        assert normalize_text("") == ""
        assert normalize_text("   ") == ""

    def test_existing_fraction_still_works(self):
        """既有「分數展開」邏輯不該被新規則破壞."""
        out = normalize_text("(a)/(b)")
        assert "分之" in out
