"""server.runner._generate_ai_diagrams_for_outline (iter 56) +
_generate_mermaid_for_outline (iter 57b) helper 安全鎖.

兩個 async helper 從 iter 56/57b 上線後沒對應直接測試. 核心
core.diagram_image_gen.generate_diagrams_for_outline /
core.mermaid_render.generate_mermaid_for_outline 兩 module 各有
自己的測試, 但 runner 內這層 IO + log dispatch wrapper (figures_dir
= job_dir / "figures" 寫死 + `if ai_figs:` 防呆 + `raw.get("figures")
or []` 補空 + raw["figures"] in-place 追加 + raw_content.json 寫回
ensure_ascii=False / indent=2 + try/except 吞例外只 log) 從沒打 —
任何 refactor 不小心動 figures_dir 子目錄名稱 / 防呆改成 fall-through /
existing + new 改成 new 覆蓋 (caller 早 prepend 的 PDF 圖會被吃掉) /
例外 swallow 改成 raise 擋 ingest 就直接上線, 跟 iter 111-129 同思路
(route / helper safety lock).

兩 helper 結構對稱, log 字串 image vs mermaid 一個分流關鍵字 — 鎖住兩段
對比, 防被合併或被偷改, 維運 grep log 找問題不該混淆「image 走哪一支」.

例外 swallow 是 design intent (AI 生圖是 bonus, 不該因 image_gen 失敗
擋整個 ingest), 該被測試鎖住.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest


# =========================================================================
#         _generate_ai_diagrams_for_outline (iter 56) tests
# =========================================================================


class TestImageHappyPath:
    """generate_diagrams_for_outline 回 fig list → 追加 + log + 寫回."""

    @pytest.mark.asyncio
    async def test_appends_to_empty_figures_list(self, tmp_path, monkeypatch):
        """raw["figures"] = [] (Adapter 預設) → call 後變 [fig1, fig2].

        鎖 existing + new 順序 (existing 先, new 後 — 是 caller adapter 抽到的
        PDF 圖該排前面, AI 生圖排後面這個語意).
        """
        import core.diagram_image_gen as dig_mod
        from server.runner import _generate_ai_diagrams_for_outline

        fake_figs = [
            {"path": "ai/fig1.png", "caption": "AI 圖 1"},
            {"path": "ai/fig2.png", "caption": "AI 圖 2"},
        ]
        received = {}

        def fake_gen(outline, figures_dir):
            received["outline"] = outline
            received["figures_dir"] = Path(figures_dir)
            return fake_figs

        monkeypatch.setattr(dig_mod, "generate_diagrams_for_outline", fake_gen)

        outline = {"sections": [{"id": "s1"}]}
        raw = {"figures": []}

        await _generate_ai_diagrams_for_outline(outline, raw, tmp_path)

        # raw["figures"] 該被 in-place 改成 [fig1, fig2]
        assert raw["figures"] == fake_figs
        # 鎖 figures_dir = job_dir / "figures" (子目錄名稱不被偷改)
        assert received["figures_dir"] == tmp_path / "figures"
        # 鎖 outline 透傳 (不做任何 normalize / wrap)
        assert received["outline"] is outline

    @pytest.mark.asyncio
    async def test_preserves_existing_figures(self, tmp_path, monkeypatch):
        """raw["figures"] = [PDF_FIG] (caller 早抽好) → 不被覆蓋, AI 圖 append 後面.

        鎖 existing + new 不是 new 覆蓋 (refactor 不小心寫成
        raw["figures"] = ai_figs 會吃掉 caller 抽好的 PDF figures —
        scriptor 拿到的就少了 PDF 圖, 是真實會踩的 bug).
        """
        import core.diagram_image_gen as dig_mod
        from server.runner import _generate_ai_diagrams_for_outline

        pdf_fig = {"path": "pdf/page_1_fig_1.png", "caption": "from PDF"}
        ai_fig = {"path": "ai/fig1.png", "caption": "AI 生"}

        monkeypatch.setattr(
            dig_mod, "generate_diagrams_for_outline", lambda o, d: [ai_fig],
        )

        outline = {"sections": []}
        raw = {"figures": [pdf_fig]}

        await _generate_ai_diagrams_for_outline(outline, raw, tmp_path)

        # 順序: PDF 圖 (existing) 先, AI 圖 (new) 後
        assert raw["figures"] == [pdf_fig, ai_fig]

    @pytest.mark.asyncio
    async def test_figures_key_missing_uses_or_fallback(self, tmp_path, monkeypatch):
        """raw 沒有 "figures" key → `raw.get("figures") or []` 走 fallback,
        不該 KeyError. 鎖防呆條件不被改成 raw["figures"] (會 KeyError).
        """
        import core.diagram_image_gen as dig_mod
        from server.runner import _generate_ai_diagrams_for_outline

        new_fig = {"path": "ai/x.png"}
        monkeypatch.setattr(
            dig_mod, "generate_diagrams_for_outline", lambda o, d: [new_fig],
        )

        raw = {"title": "no figures key"}  # 故意缺 "figures"

        await _generate_ai_diagrams_for_outline({}, raw, tmp_path)

        assert raw["figures"] == [new_fig]

    @pytest.mark.asyncio
    async def test_figures_none_uses_or_fallback(self, tmp_path, monkeypatch):
        """raw["figures"] = None (Adapter 寫成 None 而非 []) → `or []` 補空.

        鎖 `raw.get("figures") or []` 對 None / [] 兩種都該走同一條 fallback.
        """
        import core.diagram_image_gen as dig_mod
        from server.runner import _generate_ai_diagrams_for_outline

        new_fig = {"path": "ai/y.png"}
        monkeypatch.setattr(
            dig_mod, "generate_diagrams_for_outline", lambda o, d: [new_fig],
        )

        raw = {"figures": None}

        await _generate_ai_diagrams_for_outline({}, raw, tmp_path)

        assert raw["figures"] == [new_fig]

    @pytest.mark.asyncio
    async def test_writes_raw_content_json_on_success(self, tmp_path, monkeypatch):
        """成功時 raw_content.json 寫回 disk, ensure_ascii=False + indent=2.

        鎖兩個 JSON dump 旗標 (中文不該被 escape, indent 給人讀 + git diff
        友善). scriptor 從 disk 讀 raw_content.json, 不從 in-memory dict 拿,
        所以這個 write 一漏掉 AI 圖整批失蹤.
        """
        import core.diagram_image_gen as dig_mod
        from server.runner import _generate_ai_diagrams_for_outline

        new_fig = {"path": "ai/中文圖.png", "caption": "中文標題"}
        monkeypatch.setattr(
            dig_mod, "generate_diagrams_for_outline", lambda o, d: [new_fig],
        )

        raw = {"title": "中文標題 raw", "figures": []}

        await _generate_ai_diagrams_for_outline({}, raw, tmp_path)

        # 檔該被寫到 job_dir/raw_content.json
        raw_path = tmp_path / "raw_content.json"
        assert raw_path.exists(), "raw_content.json 該被寫回 disk"

        raw_text = raw_path.read_text(encoding="utf-8")
        # ensure_ascii=False — 中文該原樣存, 不該變 \uXXXX
        assert "中文標題" in raw_text
        assert "\\u" not in raw_text or "中文" in raw_text  # 寬鬆: 至少中文沒被 escape
        # indent=2 — 該至少有一行以 2-space 開頭
        assert any(
            line.startswith("  ") for line in raw_text.splitlines()
        ), "raw_content.json 該用 indent=2 寫"

        # JSON 內容該包 figures
        parsed = json.loads(raw_text)
        assert parsed["figures"] == [new_fig]

    @pytest.mark.asyncio
    async def test_info_log_contains_image_count_keyword(
        self, tmp_path, monkeypatch, caplog,
    ):
        """logger.info 該含「AI 生圖完成: N 張」(N 是 ai_figs 長度).

        鎖 image vs mermaid log 方向不同關鍵字 (見 test_mermaid 對比測試) —
        合併兩段 log 訊息會讓維運 grep log 找問題時混淆 image vs mermaid.
        """
        import core.diagram_image_gen as dig_mod
        from server.runner import _generate_ai_diagrams_for_outline

        figs = [{"path": f"ai/{i}.png"} for i in range(3)]
        monkeypatch.setattr(
            dig_mod, "generate_diagrams_for_outline", lambda o, d: figs,
        )

        with caplog.at_level(logging.INFO, logger="server.runner"):
            await _generate_ai_diagrams_for_outline({}, {"figures": []}, tmp_path)

        assert any(
            "AI 生圖完成" in rec.message and "3 張" in rec.message
            for rec in caplog.records
        ), f"log 該含「AI 生圖完成: 3 張」, 實際: {[r.message for r in caplog.records]}"
        # 對比鎖: 不該誤含 mermaid 字串 (兩 helper 訊息該嚴格分流)
        assert not any(
            "mermaid" in rec.message.lower() for rec in caplog.records
        )


class TestImageEmptyResult:
    """generate_diagrams_for_outline 回 [] → 一切 noop (不該寫檔不該 log)."""

    @pytest.mark.asyncio
    async def test_empty_list_skips_write_and_log(self, tmp_path, monkeypatch, caplog):
        """空 list → raw["figures"] 保留 existing + 沒寫 raw_content.json +
        沒 logger.info「AI 生圖完成」(避免空噪音 log).

        鎖 `if ai_figs:` 防呆不被改成 fall-through (`if ai_figs is not None:`
        會讓空 list 也寫 raw_content.json 留無謂 disk IO).
        """
        import core.diagram_image_gen as dig_mod
        from server.runner import _generate_ai_diagrams_for_outline

        monkeypatch.setattr(
            dig_mod, "generate_diagrams_for_outline", lambda o, d: [],
        )

        original_fig = {"path": "pdf/keep_me.png"}
        raw = {"figures": [original_fig]}

        with caplog.at_level(logging.INFO, logger="server.runner"):
            await _generate_ai_diagrams_for_outline({}, raw, tmp_path)

        # raw["figures"] 該保留原狀, 沒被覆蓋成 [] 也沒被追加
        assert raw["figures"] == [original_fig]
        # raw_content.json 不該被寫 (沒新圖該 skip IO)
        assert not (tmp_path / "raw_content.json").exists()
        # 沒「AI 生圖完成」訊息 (空列表該靜默)
        assert not any(
            "AI 生圖完成" in rec.message for rec in caplog.records
        )


class TestImageExceptionSwallowed:
    """generate_diagrams_for_outline raise → 不該炸 + logger.exception + raw 不動."""

    @pytest.mark.asyncio
    async def test_exception_not_propagated(self, tmp_path, monkeypatch, caplog):
        """generate_diagrams_for_outline raise RuntimeError → 函式不 raise +
        logger.exception 含「AI 生圖失敗」+「不擋 ingest」+ raw["figures"]
        不被動.

        鎖 try/except 不被改成 raise (AI 生圖是 bonus, 失敗不該擋整 job).
        """
        import core.diagram_image_gen as dig_mod
        from server.runner import _generate_ai_diagrams_for_outline

        def fake_raise(outline, figures_dir):
            raise RuntimeError("Gemini API key invalid")

        monkeypatch.setattr(
            dig_mod, "generate_diagrams_for_outline", fake_raise,
        )

        original_fig = {"path": "pdf/keep_me.png"}
        raw = {"figures": [original_fig]}

        with caplog.at_level(logging.ERROR, logger="server.runner"):
            # 不該 raise — 該被吞掉
            await _generate_ai_diagrams_for_outline({}, raw, tmp_path)

        # raw["figures"] 該保留原狀
        assert raw["figures"] == [original_fig]
        # raw_content.json 不該寫 (失敗該 skip IO)
        assert not (tmp_path / "raw_content.json").exists()
        # logger.exception 該記錄, 訊息含關鍵字
        assert any(
            "AI 生圖失敗" in rec.message and "不擋 ingest" in rec.message
            for rec in caplog.records
        )
        # 例外 traceback 該被 exception() 帶出來
        assert any(rec.exc_info is not None for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_value_error_also_swallowed(self, tmp_path, monkeypatch):
        """非 RuntimeError (ValueError) 也該被吞 — 鎖 except Exception 範圍夠寬,
        不被偷改成 except RuntimeError 只擋特定型別.
        """
        import core.diagram_image_gen as dig_mod
        from server.runner import _generate_ai_diagrams_for_outline

        def fake_raise(outline, figures_dir):
            raise ValueError("outline schema invalid")

        monkeypatch.setattr(
            dig_mod, "generate_diagrams_for_outline", fake_raise,
        )

        raw = {"figures": []}

        # 不該 raise
        await _generate_ai_diagrams_for_outline({}, raw, tmp_path)

        # raw["figures"] 仍 []
        assert raw["figures"] == []


# =========================================================================
#         _generate_mermaid_for_outline (iter 57b) tests
# =========================================================================


class TestMermaidHappyPath:
    """generate_mermaid_for_outline 回 fig list → 追加 + log + 寫回."""

    @pytest.mark.asyncio
    async def test_appends_and_writes_back(self, tmp_path, monkeypatch):
        """正常路徑: raw["figures"] = [] → [fig1] + raw_content.json 寫回."""
        import core.mermaid_render as mr_mod
        from server.runner import _generate_mermaid_for_outline

        new_fig = {"path": "mermaid/s1.png", "caption": "flow"}
        received = {}

        def fake_gen(outline, figures_dir):
            received["figures_dir"] = Path(figures_dir)
            return [new_fig]

        monkeypatch.setattr(mr_mod, "generate_mermaid_for_outline", fake_gen)

        raw = {"figures": []}

        await _generate_mermaid_for_outline({}, raw, tmp_path)

        assert raw["figures"] == [new_fig]
        # figures_dir 跟 image gen 同 — job_dir / "figures" (不該分開到
        # mermaid/ 子目錄, 兩 helper 共用 figure 介面是 design intent)
        assert received["figures_dir"] == tmp_path / "figures"
        assert (tmp_path / "raw_content.json").exists()

    @pytest.mark.asyncio
    async def test_info_log_contains_mermaid_keyword(
        self, tmp_path, monkeypatch, caplog,
    ):
        """logger.info 該含「AI mermaid 生圖完成: N 張」.

        鎖 mermaid 字串 (vs image gen 的「AI 生圖完成」) — 兩 helper 該嚴格
        分流, 維運 grep log 找問題不混淆走哪一支.
        """
        import core.mermaid_render as mr_mod
        from server.runner import _generate_mermaid_for_outline

        figs = [{"path": "mermaid/x.png"}, {"path": "mermaid/y.png"}]
        monkeypatch.setattr(
            mr_mod, "generate_mermaid_for_outline", lambda o, d: figs,
        )

        with caplog.at_level(logging.INFO, logger="server.runner"):
            await _generate_mermaid_for_outline({}, {"figures": []}, tmp_path)

        # 該含 mermaid 字串
        assert any(
            "AI mermaid 生圖完成" in rec.message and "2 張" in rec.message
            for rec in caplog.records
        ), f"log 該含「AI mermaid 生圖完成: 2 張」, 實際: {[r.message for r in caplog.records]}"


class TestMermaidEmptyAndException:
    """空回傳 + 例外路徑 — 跟 image gen 對稱, 鎖兩 helper 一致行為."""

    @pytest.mark.asyncio
    async def test_empty_list_skips_write(self, tmp_path, monkeypatch):
        """mermaid 回 [] → 不寫 raw_content.json + raw["figures"] 保留 existing."""
        import core.mermaid_render as mr_mod
        from server.runner import _generate_mermaid_for_outline

        monkeypatch.setattr(
            mr_mod, "generate_mermaid_for_outline", lambda o, d: [],
        )

        original = {"path": "pdf/existing.png"}
        raw = {"figures": [original]}

        await _generate_mermaid_for_outline({}, raw, tmp_path)

        assert raw["figures"] == [original]
        assert not (tmp_path / "raw_content.json").exists()

    @pytest.mark.asyncio
    async def test_exception_swallowed_with_mermaid_keyword(
        self, tmp_path, monkeypatch, caplog,
    ):
        """mermaid_render raise → 不該 raise + logger.exception 含「AI mermaid
        生圖失敗」+「不擋 ingest」.

        鎖 mermaid 例外訊息 vs image 例外訊息 該各帶 mermaid / 不帶 mermaid
        關鍵字 — 維運看 log 該分得出來哪一支失敗.
        """
        import core.mermaid_render as mr_mod
        from server.runner import _generate_mermaid_for_outline

        def fake_raise(outline, figures_dir):
            raise RuntimeError("mermaid.ink HTTP 500")

        monkeypatch.setattr(
            mr_mod, "generate_mermaid_for_outline", fake_raise,
        )

        raw = {"figures": []}

        with caplog.at_level(logging.ERROR, logger="server.runner"):
            await _generate_mermaid_for_outline({}, raw, tmp_path)

        # 不 raise + raw 不動
        assert raw["figures"] == []
        # 訊息含 mermaid 字串
        assert any(
            "AI mermaid 生圖失敗" in rec.message
            and "不擋 ingest" in rec.message
            for rec in caplog.records
        )


class TestSymmetricBehavior:
    """image + mermaid 串連跑 — 兩 helper 該都能追加, 不互相覆蓋."""

    @pytest.mark.asyncio
    async def test_image_then_mermaid_both_append(self, tmp_path, monkeypatch):
        """先跑 image 加 1 張, 再跑 mermaid 加 1 張 → raw["figures"] = [img, mer].

        鎖兩 helper 都用 `existing + new` 而非覆蓋 — 一前一後跑兩支 helper
        是 ingest_long_form 真實流程 (`ai_generate_diagrams` 跟
        `ai_generate_mermaid` 兩 option 用戶都可開), 任一被改成覆蓋
        就丟掉前一支的成果.
        """
        import core.diagram_image_gen as dig_mod
        import core.mermaid_render as mr_mod
        from server.runner import (
            _generate_ai_diagrams_for_outline,
            _generate_mermaid_for_outline,
        )

        img_fig = {"path": "ai/img.png", "kind": "image"}
        mer_fig = {"path": "mermaid/flow.png", "kind": "mermaid"}

        monkeypatch.setattr(
            dig_mod, "generate_diagrams_for_outline", lambda o, d: [img_fig],
        )
        monkeypatch.setattr(
            mr_mod, "generate_mermaid_for_outline", lambda o, d: [mer_fig],
        )

        raw = {"figures": []}

        await _generate_ai_diagrams_for_outline({}, raw, tmp_path)
        await _generate_mermaid_for_outline({}, raw, tmp_path)

        # 順序: 先跑的 image 先, 後跑的 mermaid 後 (caller 控制順序)
        assert raw["figures"] == [img_fig, mer_fig]
        # raw_content.json 該被寫過 (兩 helper 都寫, 最後版本含兩張)
        parsed = json.loads((tmp_path / "raw_content.json").read_text(encoding="utf-8"))
        assert parsed["figures"] == [img_fig, mer_fig]
