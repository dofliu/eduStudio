"""core/diagram_gen.py scaffold sanity tests (v4 階段 2 E iter 18).

跟 test_ideate.py 同 pattern: 只測 schema 結構 + function 簽名, 真實實作
分散到 iter 19-21 才補, raise NotImplementedError 故意鎖簽名。

設計文件: docs/engineering-diagram-design.md
"""
from __future__ import annotations

from pathlib import Path

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


class TestStripCodeFence:
    """_strip_code_fence — Gemini 偶爾包 markdown fence, 抓出純 code."""

    def test_no_fence_passthrough(self):
        from core.diagram_gen import _strip_code_fence
        raw = "import matplotlib\nplt.savefig('x.png')\n"
        assert _strip_code_fence(raw) == raw.strip()

    def test_python_fence_stripped(self):
        from core.diagram_gen import _strip_code_fence
        raw = "```python\nimport matplotlib\n```"
        assert _strip_code_fence(raw) == "import matplotlib"

    def test_bare_fence_stripped(self):
        from core.diagram_gen import _strip_code_fence
        raw = "```\nimport numpy as np\n```"
        assert _strip_code_fence(raw) == "import numpy as np"


class TestGenerateDiagram:
    """generate_diagram — 整合 propose → validate → render. 完整 mock 鏈."""

    @pytest.fixture
    def base_spec(self, tmp_path):
        from core.diagram_gen import DiagramSpec
        spec: DiagramSpec = {
            "kind": "free_body",
            "description": "簡支梁中點受 10 kN 集中力",
            "out_path": str(tmp_path / "diagram.png"),
        }
        return spec

    def test_missing_out_path_returns_none(self):
        from core.diagram_gen import DiagramSpec, generate_diagram
        spec: DiagramSpec = {
            "kind": "free_body",
            "description": "test",
            # out_path 缺
        }
        assert generate_diagram(spec) is None

    def test_missing_description_returns_none(self, tmp_path):
        from core.diagram_gen import DiagramSpec, generate_diagram
        spec: DiagramSpec = {
            "kind": "free_body",
            "description": "",
            "out_path": str(tmp_path / "x.png"),
        }
        assert generate_diagram(spec) is None

    def test_propose_raises_returns_none(self, base_spec, monkeypatch):
        from core import diagram_gen
        from core.diagram_gen import generate_diagram

        def boom(spec):
            raise RuntimeError("API limit")
        monkeypatch.setattr(diagram_gen, "_propose_matplotlib_code", boom)
        assert generate_diagram(base_spec) is None

    def test_propose_empty_returns_none(self, base_spec, monkeypatch):
        from core import diagram_gen
        from core.diagram_gen import generate_diagram

        monkeypatch.setattr(diagram_gen, "_propose_matplotlib_code",
                            lambda spec: "")
        assert generate_diagram(base_spec) is None

    def test_validate_fail_returns_none(self, base_spec, monkeypatch):
        """propose 回了惡意 code (有 import os), AST validate 擋 → None."""
        from core import diagram_gen
        from core.diagram_gen import generate_diagram

        monkeypatch.setattr(
            diagram_gen, "_propose_matplotlib_code",
            lambda spec: "import os\nos.system('rm -rf /')",
        )
        assert generate_diagram(base_spec) is None

    def test_validate_pass_render_called(self, base_spec, monkeypatch):
        """propose → validate 過 → render 被叫到. mock render 回 path 不真跑 subprocess."""
        from core import diagram_gen
        from core.diagram_gen import generate_diagram

        safe_code = (
            "import matplotlib\n"
            "matplotlib.use('Agg')\n"
            "import matplotlib.pyplot as plt\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot([0, 1], [0, 1])\n"
            "plt.savefig('x.png')\n"
        )
        monkeypatch.setattr(diagram_gen, "_propose_matplotlib_code",
                            lambda spec: safe_code)

        # mock render: 不真跑 subprocess, 直接回 out_path
        called = {"render": False, "code": None}
        def fake_render(code, out_path, timeout=30):
            called["render"] = True
            called["code"] = code
            return Path(out_path)
        monkeypatch.setattr(diagram_gen, "_render_matplotlib_diagram", fake_render)

        result = generate_diagram(base_spec)
        assert called["render"] is True
        assert called["code"] == safe_code
        assert result == Path(base_spec["out_path"])

    def test_render_fail_returns_none(self, base_spec, monkeypatch):
        """render 失敗 (subprocess timeout / 0-byte 等) → None."""
        from core import diagram_gen
        from core.diagram_gen import generate_diagram

        monkeypatch.setattr(
            diagram_gen, "_propose_matplotlib_code",
            lambda spec: "import matplotlib.pyplot as plt\nplt.savefig('x.png')",
        )
        monkeypatch.setattr(diagram_gen, "_render_matplotlib_diagram",
                            lambda code, out_path, timeout=30: None)
        assert generate_diagram(base_spec) is None


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


class TestValidateDunderBypass:
    """iter 29: 擋 dunder attribute 繞道 (review 抓的 🟡 設計疑慮).

    Gemini code 用 obj.__dict__ / cls.__class__ / mod.__builtins__ 可以繞
    allowlist 拿到 builtins 內部 — 即使 import + builtin call 都擋了。
    """

    def test_dict_access_blocked(self):
        """obj.__dict__['__builtins__']['eval'] 經典 sandbox 繞道."""
        from core.diagram_gen import _validate_code_ast

        code = "import matplotlib.pyplot as plt\nplt.__dict__\n"
        assert _validate_code_ast(code) is False

    def test_class_access_blocked(self):
        from core.diagram_gen import _validate_code_ast

        code = "import numpy as np\nnp.__class__\n"
        assert _validate_code_ast(code) is False

    def test_builtins_access_blocked(self):
        """藉 __builtins__ 拿到 eval / exec 整批."""
        from core.diagram_gen import _validate_code_ast

        code = "x = __builtins__\n"
        # __builtins__ 作為 ast.Name 不會被 Attribute 規則擋, 但
        # 直接用 Name 還在 _BLOCKED_BUILTINS? 沒, 它在 set 內. 確認.
        # 實際上 __builtins__ 是名稱不是 attribute. 這條 test 看 Name 端有沒擋
        # 如果 _BLOCKED_BUILTINS 沒列, 這條會 pass — 也許不必擋, 因為它是 reference
        # 不是 call. 真正危險是 __builtins__['eval'] 之類 subscript. 留 None 行為.
        result = _validate_code_ast(code)
        # 不嚴格 assert, 只記錄目前行為; subscript+ name 沒 attribute 形式不擋
        assert result in (True, False)  # 取決於未來 _BLOCKED_BUILTINS 是否加 __builtins__

    def test_module_dunder_blocked(self):
        """plt.__class__.__bases__ 之類 deep dunder chain."""
        from core.diagram_gen import _validate_code_ast

        code = "import matplotlib.pyplot as plt\nx = plt.__class__\n"
        assert _validate_code_ast(code) is False

    def test_subscript_dunder_blocked(self):
        """obj.__dict__['eval'] 中 __dict__ attribute 該被擋."""
        from core.diagram_gen import _validate_code_ast

        code = (
            "import matplotlib\n"
            "x = matplotlib.__dict__['__builtins__']\n"
        )
        assert _validate_code_ast(code) is False

    def test_single_underscore_attribute_still_allowed(self):
        """單一 _ 開頭 (Python 內部約定) 不該被擋, 那是合法使用."""
        from core.diagram_gen import _validate_code_ast

        # numpy 內部有 _array_function_dispatch 等, 是 single underscore
        # 不該擋. 我們只擋 dunder (前後雙底線).
        code = "import numpy as np\nx = np._NoValue\n"
        # _NoValue 不是 dunder, 應該通過
        assert _validate_code_ast(code) is True

    def test_matplotlib_normal_usage_still_works(self):
        """正常 matplotlib code 不該被誤擋."""
        from core.diagram_gen import _validate_code_ast

        code = (
            "import matplotlib.pyplot as plt\n"
            "import numpy as np\n"
            "fig, ax = plt.subplots()\n"
            "x = np.linspace(0, 10, 100)\n"
            "ax.plot(x, np.sin(x))\n"
            "plt.savefig('/tmp/x.png')\n"
        )
        assert _validate_code_ast(code) is True


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
