"""core/diagram_gen.py scaffold sanity tests (v4 階段 2 E iter 18).

跟 test_ideate.py 同 pattern: 只測 schema 結構 + function 簽名, 真實實作
分散到 iter 19-21 才補, raise NotImplementedError 故意鎖簽名。

設計文件: docs/engineering-diagram-design.md
"""
from __future__ import annotations

import pytest


def test_module_imports():
    """core.diagram_gen 載得起來就過。"""
    import core.diagram_gen  # noqa: F401


class TestDiagramKindEnum:
    def test_kind_values_stable(self):
        """鎖 enum 值 — 寫進設計文件 / 未來 spec.kind 都依賴。"""
        from core.diagram_gen import DiagramKind

        assert DiagramKind.FREE_BODY.value == "free_body"
        assert DiagramKind.BENDING_MOMENT.value == "bending_moment"
        assert DiagramKind.SHEAR.value == "shear"
        assert DiagramKind.STRESS_STRAIN.value == "stress_strain"
        assert DiagramKind.BLOCK_DIAGRAM.value == "block_diagram"
        assert DiagramKind.CIRCUIT.value == "circuit"
        assert DiagramKind.GENERIC.value == "generic"

    def test_kind_set_is_complete(self):
        from core.diagram_gen import DiagramKind

        all_values = {k.value for k in DiagramKind}
        assert all_values == {
            "free_body", "bending_moment", "shear", "stress_strain",
            "block_diagram", "circuit", "generic",
        }


class TestDefaults:
    def test_default_dimensions(self):
        from core.diagram_gen import DEFAULT_DPI, DEFAULT_HEIGHT, DEFAULT_WIDTH

        # 16:9 不必, 工程圖正方近矩形 800x600 (4:3) 較自然
        assert DEFAULT_WIDTH == 800
        assert DEFAULT_HEIGHT == 600
        assert DEFAULT_DPI == 100


class TestScaffoldStubsRaise:
    """function 簽名穩定 — 改前先改測試 (review gate)."""

    def test_generate_diagram_signature(self):
        from core.diagram_gen import DiagramSpec, generate_diagram

        spec: DiagramSpec = {
            "kind": "free_body",
            "description": "簡支梁中點受 10 kN 集中力",
            "out_path": "/tmp/fb.png",
        }
        with pytest.raises(NotImplementedError):
            generate_diagram(spec)

    def test_propose_matplotlib_code_signature(self):
        from core.diagram_gen import DiagramSpec, _propose_matplotlib_code

        spec: DiagramSpec = {
            "kind": "free_body",
            "description": "test",
            "out_path": "/tmp/x.png",
        }
        with pytest.raises(NotImplementedError):
            _propose_matplotlib_code(spec)

    def test_validate_code_ast_signature(self):
        from core.diagram_gen import _validate_code_ast

        with pytest.raises(NotImplementedError):
            _validate_code_ast("import matplotlib.pyplot as plt\n")

    def test_render_matplotlib_diagram_signature(self, tmp_path):
        from core.diagram_gen import _render_matplotlib_diagram

        with pytest.raises(NotImplementedError):
            _render_matplotlib_diagram(
                code="import matplotlib.pyplot as plt; plt.savefig('x.png')",
                out_path=tmp_path / "x.png",
            )
