"""iter 91: _balance_wrap_lines 中文 wrap 後處理測試.

用實際字型測 (避免 mock 字寬), 不過會 skip 沒中文字型的環境.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import ImageFont

from core.render.pptx_style import (
    _balance_wrap_lines,
    _wrap_text,
)


def _load_cjk_font(size: int = 64) -> ImageFont.FreeTypeFont:
    """找一個能塞中文的字型. 沒有就 skip 整檔."""
    candidates = [
        os.environ.get("CLAUDE_FONT_PATH"),
        os.environ.get("CLAUDE_FALLBACK_FONT_PATH"),
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        if not path:
            continue
        p = Path(path)
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except OSError:
                continue
    pytest.skip("沒有可用的 CJK 字型, 跳過 wrap 視覺測試")


class TestBalanceWrapLines:
    def test_empty_lines_passthrough(self):
        font = _load_cjk_font()
        assert _balance_wrap_lines([], font, 800) == []

    def test_single_line_passthrough(self):
        font = _load_cjk_font()
        assert _balance_wrap_lines(["abc"], font, 800) == ["abc"]

    def test_orphan_char_borrowed_from_previous_line(self):
        """孤字「異」該被借字救回 — Skill 短影片實測 case."""
        font = _load_cjk_font(72)
        # 模擬已經被貪婪 wrap 切過的行: 「Skill 的本質與差」+ 「異」
        before = ["Skill 的本質與差", "異"]
        after = _balance_wrap_lines(before, font, 9999)
        # 最後一行該至少 2 字 (借了一個過來)
        assert len(after[-1]) >= 2, f"孤字未修正: {after}"
        # 總字數不變
        assert "".join(after) == "".join(before)

    def test_leading_punct_pulled_back(self):
        """收尾標點不該行首 — 「」「。」「,」拉回上一行."""
        font = _load_cjk_font(48)
        before = ["講完了", "」"]
        after = _balance_wrap_lines(before, font, 9999)
        # 「」該被拉回上一行
        assert after[0].endswith("」"), f"收尾標點未拉回: {after}"

    def test_trailing_open_punct_pushed_down(self):
        """開頭標點不該行尾 — 「「」「(」推到下一行."""
        font = _load_cjk_font(48)
        before = ["前文「", "工作流程"]
        after = _balance_wrap_lines(before, font, 9999)
        # 「該推到第二行頭
        assert not after[0].endswith("「"), f"開引號未推下: {after}"
        assert after[1].startswith("「"), f"開引號未推下: {after}"

    def test_does_not_reduce_to_zero(self):
        """如果借字 / 移標點會讓某行變空, 該整行 pop, 不留空 row."""
        font = _load_cjk_font(48)
        before = ["abc", "」"]
        after = _balance_wrap_lines(before, font, 9999)
        # 不該有空字串
        assert all(line for line in after), f"留下空 row: {after}"

    def test_punct_within_size_constraint(self):
        """borrowed 後若超寬太多 (>×1.08) 該放棄, 不破壞 layout."""
        font = _load_cjk_font(48)
        # 上一行已經頂寬度, 不該硬塞
        max_w = int(font.getlength("一二三四五六"))
        before = ["一二三四五六", "」"]
        after = _balance_wrap_lines(before, font, max_w)
        # 允許借 (×1.08) 或不借, 但內容不能丟
        assert "".join(after) == "".join(before)


class TestWrapTextIntegration:
    def test_no_orphan_in_real_wrap(self):
        """整段 wrap 一次, 確認孤字邏輯有套用."""
        font = _load_cjk_font(72)
        # 用會自然斷成「8 字 + 1 字」的寬度
        text = "Skill的本質與差異"  # 共 9 顯示字符
        # 算寬度: 8 字寬度可塞, 9 字塞不下
        max_w = int(font.getlength("Skill的本質與差")) + 5
        lines = _wrap_text(text, font, max_w)
        # post-process 應該借字: 「異」不該孤立
        if len(lines) >= 2:
            assert len(lines[-1]) >= 2, f"未修正孤字: {lines}"
