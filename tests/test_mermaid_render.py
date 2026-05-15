"""core/mermaid_render.py — iter 57 Option D.

純函式部分直跑 (extract_mermaid_blocks).
render_mermaid_to_png / 對外 HTTP 部分 mock urllib.request.urlopen.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.mermaid_render import (
    extract_and_render_mermaid_from_repo,
    extract_and_render_mermaid_from_text,
    extract_mermaid_blocks,
    render_mermaid_to_png,
)


class TestExtractMermaidBlocks:
    def test_no_blocks_returns_empty(self):
        assert extract_mermaid_blocks("just plain text") == []

    def test_empty_text(self):
        assert extract_mermaid_blocks("") == []

    def test_single_block_no_caption(self):
        text = "```mermaid\ngraph TD\n  A --> B\n```"
        out = extract_mermaid_blocks(text)
        assert len(out) == 1
        syntax, caption = out[0]
        assert "graph TD" in syntax
        assert "A --> B" in syntax
        assert caption == ""    # 前面沒文字

    def test_single_block_with_caption(self):
        text = (
            "## Architecture\n"
            "下圖顯示系統的整體架構流程。\n"
            "```mermaid\n"
            "graph LR\n  X --> Y\n"
            "```\n"
        )
        out = extract_mermaid_blocks(text)
        assert len(out) == 1
        syntax, caption = out[0]
        assert "graph LR" in syntax
        # caption_hint 抓非標題的最後一行
        assert "系統的整體架構" in caption

    def test_multiple_blocks(self):
        text = """
First diagram caption text.
```mermaid
graph TD
  A --> B
```

Between text here.

Second diagram caption.
```mermaid
sequenceDiagram
  Alice ->> Bob: Hi
```
"""
        out = extract_mermaid_blocks(text)
        assert len(out) == 2
        assert "graph TD" in out[0][0]
        assert "sequenceDiagram" in out[1][0]
        # 各自的 caption 該對得上
        assert "First" in out[0][1]
        assert "Second" in out[1][1]

    def test_empty_mermaid_block_skipped(self):
        """```mermaid\\n\\n``` (空 syntax) 不該被抓."""
        text = "```mermaid\n\n```"
        assert extract_mermaid_blocks(text) == []

    def test_case_insensitive_fence(self):
        """`​``Mermaid` 大寫也該匹配."""
        text = "```Mermaid\ngraph TD\n  A --> B\n```"
        out = extract_mermaid_blocks(text)
        assert len(out) == 1

    def test_caption_skip_markdown_heading(self):
        """前一行是 # heading → 跳過, 找再上一行."""
        text = (
            "describes flow visually\n"
            "## Diagram\n"
            "```mermaid\ngraph TD\n  A --> B\n```"
        )
        _, caption = extract_mermaid_blocks(text)[0]
        # 該抓到 "describes flow visually" 而不是 "## Diagram"
        assert "describes" in caption
        assert "##" not in caption


class TestRenderMermaidToPng:
    def test_empty_syntax_returns_false(self, tmp_path):
        out = tmp_path / "out.png"
        assert render_mermaid_to_png("", out) is False
        assert render_mermaid_to_png("   ", out) is False

    def test_successful_render_writes_file(self, tmp_path):
        out = tmp_path / "test.png"
        fake_png = b"\x89PNG\r\n\x1a\n" + b"x" * 500   # > 100 bytes

        mock_response = MagicMock()
        mock_response.read.return_value = fake_png
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_response):
            ok = render_mermaid_to_png("graph TD\n  A --> B", out)
        assert ok is True
        assert out.exists()
        assert out.read_bytes() == fake_png

    def test_tiny_response_treated_as_failure(self, tmp_path):
        """< 100 bytes 視同失敗 (mermaid.ink 錯誤頁通常很小)."""
        out = tmp_path / "small.png"
        mock_response = MagicMock()
        mock_response.read.return_value = b"err"
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_response):
            ok = render_mermaid_to_png("graph TD", out)
        assert ok is False
        assert not out.exists()

    def test_http_error_returns_false(self, tmp_path):
        """urlopen 拋例外 → False, 不該 raise."""
        out = tmp_path / "fail.png"
        with patch("urllib.request.urlopen", side_effect=RuntimeError("net err")):
            ok = render_mermaid_to_png("graph TD", out)
        assert ok is False


class TestExtractAndRenderFromText:
    def test_no_blocks_returns_empty(self, tmp_path):
        assert extract_and_render_mermaid_from_text(
            "no mermaid here", tmp_path,
        ) == []

    def test_renders_each_block(self, tmp_path):
        text = """
intro caption
```mermaid
graph TD
  A --> B
```

second caption
```mermaid
graph LR
  X --> Y
```
"""
        fake_png = b"\x89PNG" + b"x" * 500
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_png
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            figs = extract_and_render_mermaid_from_text(
                text, tmp_path, id_prefix="m",
            )

        assert len(figs) == 2
        assert figs[0]["id"] == "m_1"
        assert figs[1]["id"] == "m_2"
        assert (tmp_path / "m_1.png").exists()
        assert (tmp_path / "m_2.png").exists()
        # caption 該帶入
        assert "intro" in figs[0]["caption_hint"]
        assert "second" in figs[1]["caption_hint"]

    def test_render_failure_skips_block(self, tmp_path):
        """render 失敗的 block 不該進 figures list (不擋其他成功的)."""
        text = """
```mermaid
graph TD
  A --> B
```

```mermaid
graph LR
  X --> Y
```
"""
        # 第一次成功 (大 PNG), 第二次失敗 (太小)
        calls = []

        def fake_urlopen(req, **kw):
            calls.append(req)
            m = MagicMock()
            m.__enter__ = lambda s: s
            m.__exit__ = lambda s, *a: None
            if len(calls) == 1:
                m.read.return_value = b"\x89PNG" + b"x" * 500
            else:
                m.read.return_value = b"fail"
            return m

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            figs = extract_and_render_mermaid_from_text(
                text, tmp_path, id_prefix="m",
            )
        assert len(figs) == 1
        assert figs[0]["id"] == "m_1"

    def test_max_blocks_respected(self, tmp_path):
        text = "\n".join([
            "```mermaid\ngraph TD\n  A --> B\n```",
        ] * 5)
        fake_png = b"\x89PNG" + b"x" * 500
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_png
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            figs = extract_and_render_mermaid_from_text(
                text, tmp_path, max_blocks=3,
            )
        assert len(figs) == 3

    def test_figure_schema_matches_pdf(self, tmp_path):
        """回的 dict 跟 extract_pdf_figures / AI gen 一致, scriptor 能 reuse."""
        text = "```mermaid\ngraph TD\n  A --> B\n```"
        fake_png = b"\x89PNG" + b"x" * 500
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_png
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            figs = extract_and_render_mermaid_from_text(text, tmp_path)
        assert len(figs) == 1
        f = figs[0]
        required = {"id", "page_no", "path", "width", "height", "caption_hint"}
        assert set(f.keys()) >= required


class TestExtractAndRenderFromRepo:
    def test_scans_only_md_files(self, tmp_path):
        """key_files 內非 .md 不該被掃."""
        raw = {
            "key_files": [
                {"path": "core/foo.py", "content": "```mermaid\ngraph TD\n```"},
                {"path": "README.md", "content": "```mermaid\ngraph TD\n  A->B\n```"},
            ],
        }
        fake_png = b"\x89PNG" + b"x" * 500
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_png
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            figs = extract_and_render_mermaid_from_repo(raw, tmp_path)
        # 只該掃 README.md (有 1 個 block)
        assert len(figs) == 1
        # id 該含 file stem
        assert "README" in figs[0]["id"]

    def test_empty_key_files(self, tmp_path):
        assert extract_and_render_mermaid_from_repo({}, tmp_path) == []
        assert extract_and_render_mermaid_from_repo({"key_files": []}, tmp_path) == []

    def test_unsafe_filename_chars_sanitized(self, tmp_path):
        """file stem 含特殊字元時, 落在 figure id 該被替換為 _."""
        raw = {
            "key_files": [
                {"path": "docs/path/has space.md",
                 "content": "```mermaid\ngraph TD\n```"},
            ],
        }
        fake_png = b"\x89PNG" + b"x" * 500
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_png
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            figs = extract_and_render_mermaid_from_repo(raw, tmp_path)
        assert len(figs) == 1
        # id 不該含空白
        assert " " not in figs[0]["id"]
