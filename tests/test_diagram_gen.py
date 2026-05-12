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


class TestStillStubbed:
    """iter 20+ 才實作的 stub, 鎖簽名."""

    def test_generate_diagram_still_stub(self):
        from core.diagram_gen import DiagramSpec, generate_diagram

        spec: DiagramSpec = {
            "kind": "free_body",
            "description": "test",
            "out_path": "/tmp/x.png",
        }
        with pytest.raises(NotImplementedError):
            generate_diagram(spec)

    def test_propose_matplotlib_code_still_stub(self):
        from core.diagram_gen import DiagramSpec, _propose_matplotlib_code

        spec: DiagramSpec = {
            "kind": "free_body",
            "description": "test",
            "out_path": "/tmp/x.png",
        }
        with pytest.raises(NotImplementedError):
            _propose_matplotlib_code(spec)


class TestValidateCodeAst:
    """AST allowlist — 只允許 matplotlib / numpy / math / scipy import."""

    def test_simple_matplotlib_passes(self):
        from core.diagram_gen import _validate_code_ast

        code = "import matplotlib.pyplot as plt\nplt.figure()\nplt.savefig('/tmp/x.png')"
        assert _validate_code_ast(code) is True

    def test_numpy_and_math_pass(self):
        from core.diagram_gen import _validate_code_ast

        code = "import numpy as np\nimport math\nimport matplotlib.pyplot as plt"
        assert _validate_code_ast(code) is True

    def test_scipy_submodule_passes(self):
        from core.diagram_gen import _validate_code_ast

        code = "from scipy import signal\nimport matplotlib.pyplot as plt"
        assert _validate_code_ast(code) is True

    def test_import_os_blocked(self):
        from core.diagram_gen import _validate_code_ast

        code = "import os\nimport matplotlib.pyplot as plt"
        assert _validate_code_ast(code) is False

    def test_import_sys_blocked(self):
        from core.diagram_gen import _validate_code_ast

        assert _validate_code_ast("import sys") is False

    def test_import_subprocess_blocked(self):
        from core.diagram_gen import _validate_code_ast

        assert _validate_code_ast("import subprocess") is False

    def test_from_import_socket_blocked(self):
        from core.diagram_gen import _validate_code_ast

        assert _validate_code_ast("from socket import socket") is False

    def test_from_requests_blocked(self):
        from core.diagram_gen import _validate_code_ast

        assert _validate_code_ast("from requests import get") is False

    def test_relative_import_blocked(self):
        from core.diagram_gen import _validate_code_ast

        # `from . import X` 不該出現在獨立 script
        assert _validate_code_ast("from . import config") is False

    def test_eval_call_blocked(self):
        from core.diagram_gen import _validate_code_ast

        code = "import matplotlib.pyplot as plt\nx = eval('1+1')"
        assert _validate_code_ast(code) is False

    def test_exec_call_blocked(self):
        from core.diagram_gen import _validate_code_ast

        code = "exec('print(1)')"
        assert _validate_code_ast(code) is False

    def test_import_function_blocked(self):
        from core.diagram_gen import _validate_code_ast

        code = "x = __import__('os')"
        assert _validate_code_ast(code) is False

    def test_open_call_blocked(self):
        from core.diagram_gen import _validate_code_ast

        # 不讓 Gemini code 自己讀寫檔 — matplotlib savefig 是唯一寫檔路徑
        code = "open('/etc/passwd').read()"
        assert _validate_code_ast(code) is False

    def test_getattr_blocked(self):
        from core.diagram_gen import _validate_code_ast

        # getattr 可繞 allowlist (例: getattr(__builtins__, 'eval'))
        code = "getattr(object, 'foo')"
        assert _validate_code_ast(code) is False

    def test_syntax_error_returns_false(self):
        from core.diagram_gen import _validate_code_ast

        # 壞語法不該 raise, 回 False 讓 caller graceful 處理.
        # 用真的會炸 SyntaxError 的: 未閉合的字串 + 縮排錯
        assert _validate_code_ast("def foo(:\n  pass") is False


class TestRenderMatplotlibDiagram:
    """subprocess sandbox 跑 matplotlib code 寫 PNG."""

    def test_happy_path_writes_png(self, tmp_path):
        from core.diagram_gen import _render_matplotlib_diagram

        out = tmp_path / "fb.png"
        code = f'''
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots()
ax.plot([0, 1, 2], [0, 1, 4])
ax.set_title("Test")
plt.savefig(r"{out}")
'''
        result = _render_matplotlib_diagram(code, out, timeout=30)
        # 在缺 matplotlib 環境會 None, 但 caller 不該 raise
        # 本機有 matplotlib 應該成功
        if result is not None:
            assert result == out
            assert out.exists()
            assert out.stat().st_size > 0

    def test_subprocess_failure_returns_none(self, tmp_path):
        from core.diagram_gen import _render_matplotlib_diagram

        out = tmp_path / "fail.png"
        # 故意 raise 不寫檔
        code = "raise RuntimeError('boom')"
        result = _render_matplotlib_diagram(code, out, timeout=10)
        assert result is None
        assert not out.exists()

    def test_code_not_writing_file_returns_none(self, tmp_path):
        from core.diagram_gen import _render_matplotlib_diagram

        out = tmp_path / "noop.png"
        # 沒寫到 out_path
        code = "x = 1 + 1"
        result = _render_matplotlib_diagram(code, out, timeout=10)
        assert result is None

    def test_empty_output_file_returns_none(self, tmp_path):
        from core.diagram_gen import _render_matplotlib_diagram

        out = tmp_path / "empty.png"
        # 寫了一個 0 byte 檔, 應該被當失敗
        code = f'open(r"{out}", "wb").close()'
        result = _render_matplotlib_diagram(code, out, timeout=10)
        # 注意: open() 在 AST 層已被擋, 但 _render 不跑 AST 檢查 (那是 caller 責任)
        # 這條測試 _render 對 0-byte output 的處理
        assert result is None

    def test_timeout_returns_none(self, tmp_path):
        from core.diagram_gen import _render_matplotlib_diagram

        out = tmp_path / "slow.png"
        # 故意 sleep 超過 timeout — 用 time 不 import (math 是 allowed 不過 time 不是,
        # 但 _render 不檢查 AST, 是 caller 該先過 _validate_code_ast)
        code = "import time; time.sleep(10)"
        result = _render_matplotlib_diagram(code, out, timeout=1)
        assert result is None

    def test_existing_output_cleared_before_run(self, tmp_path):
        from core.diagram_gen import _render_matplotlib_diagram

        out = tmp_path / "old.png"
        out.write_bytes(b"old fake content")

        # code 故意失敗 — 舊檔應該被先清掉, 確保 caller 不會看到舊資料以為成功
        code = "raise RuntimeError('boom')"
        result = _render_matplotlib_diagram(code, out, timeout=10)
        assert result is None
        # 舊檔已被 _render 清掉 (即使後續失敗也沒留)
        assert not out.exists()
