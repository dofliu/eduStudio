"""tools/gen_icon_svgs.py 測試 — 純 offline, 不呼叫 Gemini。

鎖三類契約:
1. VISUAL_DESC 完整性 (涵蓋 manifest 全部 25 icon, 不多不少) — 防將來改 manifest
   加 icon 卻漏寫視覺描述, build_prompt 會 KeyError。
2. build_prompt 必含統一風格規範 + 該 icon 語意 + 目標路徑。
3. extract_svg 從 Gemini 回應 (含 code fence / 雜訊) 抽出 SVG 區塊。
"""
import json
import sys
from pathlib import Path

import pytest

# tools/ 不是 package, 且 site-packages 有同名 `tools` 套件會 shadow `import tools.X`.
# 比照 test_measure_narration_truncation.py: 掛 tools 目錄上 path 當 top-level module.
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.append(str(_TOOLS_DIR))

import gen_icon_svgs as g  # noqa: E402


def _manifest_names():
    data = json.loads(g.MANIFEST_PATH.read_text(encoding="utf-8"))
    return set(data["icons"].keys())


class TestLoadIcons:
    def test_loads_25_icons(self):
        icons = g.load_icons()
        assert len(icons) == 25

    def test_preserves_manifest_order(self):
        # 第一個該是 manifest 第一筆 question (icon_picker 依 manifest 序當優先序)
        assert g.load_icons()[0][0] == "question"


class TestVisualDescCompleteness:
    def test_covers_every_manifest_icon(self):
        # 完整性鎖: 每個 manifest icon 都要有視覺描述 (否則 build_prompt KeyError)
        assert _manifest_names() <= set(g.VISUAL_DESC)

    def test_no_orphan_desc(self):
        # 反向: VISUAL_DESC 不該有 manifest 沒有的 key (drift 偵測)
        assert set(g.VISUAL_DESC) <= _manifest_names()

    def test_every_build_prompt_works(self):
        # 端到端: 25 個 icon 都組得出 prompt 不炸
        for name, entry in g.load_icons():
            assert g.build_prompt(name, entry)


class TestBuildPrompt:
    def test_contains_style_spec(self):
        name, entry = g.load_icons()[0]
        p = g.build_prompt(name, entry)
        assert "256 256" in p          # viewBox
        assert "#1e3a2e" in p          # forest stroke
        assert "#ffd96b" in p          # 粉筆黃 fill

    def test_contains_no_text_label_rule(self):
        name, entry = g.load_icons()[0]
        assert "說明文字" in g.build_prompt(name, entry)

    def test_contains_icon_semantics(self):
        # 用 wind_turbine 驗語意描述有進 prompt
        entry = dict(g.load_icons())["wind_turbine"]
        p = g.build_prompt("wind_turbine", entry)
        assert "三葉片" in p
        assert "wind/wind_turbine.svg" in p   # 目標路徑

    def test_keywords_injected(self):
        entry = dict(g.load_icons())["question"]
        p = g.build_prompt("question", entry)
        assert "為什麼" in p   # manifest question 的 keyword


class TestExtractSvg:
    def test_pulls_svg_from_fence(self):
        text = '好的:\n```svg\n<svg viewBox="0 0 256 256"><circle/></svg>\n```'
        svg = g.extract_svg(text)
        assert svg is not None
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")

    def test_pulls_bare_svg(self):
        text = '<svg viewBox="0 0 256 256"><path/></svg>'
        assert g.extract_svg(text) == text

    def test_returns_none_when_absent(self):
        assert g.extract_svg("抱歉我無法產生") is None

    def test_returns_none_on_empty(self):
        assert g.extract_svg("") is None

    def test_first_svg_only(self):
        text = "<svg>A</svg> 中間 <svg>B</svg>"
        # 抓第一個 (非貪婪)
        assert g.extract_svg(text) == "<svg>A</svg>"


class TestIsValidSvg:
    def test_valid_needs_svg_and_viewbox(self):
        assert g._is_valid_svg('<svg viewBox="0 0 256 256"></svg>')

    def test_missing_viewbox_invalid(self):
        assert not g._is_valid_svg("<svg></svg>")

    def test_not_svg_invalid(self):
        assert not g._is_valid_svg("<div viewBox></div>")


class TestMainDryRun:
    def test_dry_run_default_no_write(self, capsys):
        rc = g.main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "dry-run" in out
        assert "25 個" in out

    def test_only_filters_single(self, capsys):
        rc = g.main(["--only", "question"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "會產 1 個" in out

    def test_only_unknown_returns_2(self):
        assert g.main(["--only", "no_such_icon"]) == 2
