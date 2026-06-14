"""F9-2i：在地化翻譯 route 接課程 glossary 固定譯名測試。

驗收（對應 docs/JOB_COURSE_ASSOCIATION_RFC.md §4.3）：
- `POST /localization/translate` 帶 `project_id` → 載入該課 glossary 的固定譯名
  （`to_translation_rules`）併進 glossary 規則送翻譯。
- 呼叫端顯式 `glossary` 與課程規則合併（顯式在前、課程在後）。
- canonical 區域碼（en-US）↔ glossary 短碼（en）對得上（候選碼退基底）。
- fail-soft（RFC §5）：沒 project_id / 課不存在 / 無 glossary / 該語言無譯名 →
  沿用現行行為（不傳課程規則、絕不讓翻譯失敗）。

Mock 策略：monkeypatch translator.translate 攔截實際送進去的 glossary 字串、不打真
Gemini；ProjectStore 注入 tmp_path 隔離（全 offline-first）。
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import core.translation.service as svc
import server.routes.projects as projects_mod
from core.glossary import Glossary, GlossaryEntry
from server.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient + 隔離 ProjectStore + 攔截 translate 的 glossary 字串。"""
    seen = {}

    def fake_translate(text, source_code, target_code, glossary="", style=""):
        seen["glossary"] = glossary
        seen["target"] = target_code
        return "譯文"

    monkeypatch.setattr(svc.translator, "translate", fake_translate)

    app = create_app()
    project_store = projects_mod.ProjectStore(root=tmp_path / "projects")
    app.dependency_overrides[projects_mod.get_default_project_store] = lambda: project_store
    with TestClient(app) as c:
        yield c, project_store, seen


def _make_course_with_glossary(store, pid="course_statics", *, course="靜力學"):
    """建一門課 + 一份含固定譯名的 glossary（en/ja）。"""
    store.create(pid, title=course)
    glossary = Glossary(
        course=course,
        entries=[
            GlossaryEntry(
                term="自然頻率",
                aliases=["ω_n", "wn"],
                translations={"en": "natural frequency", "ja": "固有振動数"},
            ),
            GlossaryEntry(term="阻尼比", translations={"en": "damping ratio"}),
        ],
    )
    store.save_glossary(pid, glossary)
    return pid


class TestCourseGlossaryWiring:
    def test_project_id_injects_translation_rules(self, client):
        """帶 project_id → glossary 固定譯名（含別名並排）併進送翻譯的 glossary。"""
        c, store, seen = client
        pid = _make_course_with_glossary(store)
        r = c.post("/localization/translate", json={
            "text": "自然頻率與阻尼比", "target_lang": "en-US", "project_id": pid,
        })
        assert r.status_code == 200
        g = seen["glossary"]
        # en-US 退基底 en → 對上 glossary 的 "en" 譯名
        assert "natural frequency" in g
        assert "damping ratio" in g
        # 來源面列出 term + 別名（longest-first，/ 並排）
        assert "ω_n" in g and "自然頻率" in g

    def test_caller_glossary_merged_first(self, client):
        """呼叫端顯式 glossary 與課程規則合併，顯式在前。"""
        c, store, seen = client
        pid = _make_course_with_glossary(store)
        r = c.post("/localization/translate", json={
            "text": "x", "target_lang": "en-US", "project_id": pid,
            "glossary": "手動規則 → manual",
        })
        assert r.status_code == 200
        g = seen["glossary"]
        assert "手動規則 → manual" in g
        assert "natural frequency" in g
        # 顯式規則排在課程規則之前
        assert g.index("手動規則") < g.index("natural frequency")

    def test_exact_region_code_matches(self, client):
        """glossary key 用完整區域碼（zh-CN）時直接命中、不誤退基底。"""
        c, store, seen = client
        store.create("c2", title="材力")
        store.save_glossary("c2", Glossary(
            course="材力",
            entries=[GlossaryEntry(term="應力", translations={"zh-CN": "应力"})],
        ))
        r = c.post("/localization/translate", json={
            "text": "應力", "target_lang": "zh-CN", "project_id": "c2",
        })
        assert r.status_code == 200
        assert "应力" in seen["glossary"]

    def test_no_translation_for_lang_no_rules(self, client):
        """該課 glossary 沒有目標語言譯名 → 不附課程規則（沿用空 glossary）。"""
        c, store, seen = client
        pid = _make_course_with_glossary(store)  # 只有 en/ja
        r = c.post("/localization/translate", json={
            "text": "x", "target_lang": "ko-KR", "project_id": pid,
        })
        assert r.status_code == 200
        assert seen["glossary"] == ""


class TestFailSoft:
    def test_no_project_id_passes_caller_glossary_only(self, client):
        """沒 project_id → 只送呼叫端 glossary（現行行為，零影響）。"""
        c, _store, seen = client
        r = c.post("/localization/translate", json={
            "text": "x", "target_lang": "en-US", "glossary": "只有這條 → only",
        })
        assert r.status_code == 200
        assert seen["glossary"] == "只有這條 → only"

    def test_unknown_project_id_fail_soft(self, client):
        """project_id 指向不存在的課 → fail-soft 不報錯、不附課程規則。"""
        c, _store, seen = client
        r = c.post("/localization/translate", json={
            "text": "x", "target_lang": "en-US", "project_id": "nope",
        })
        assert r.status_code == 200
        assert seen["glossary"] == ""

    def test_course_without_glossary_fail_soft(self, client):
        """課存在但還沒建 glossary → fail-soft 回空課程規則。"""
        c, store, seen = client
        store.create("bare", title="尚無術語表")
        r = c.post("/localization/translate", json={
            "text": "x", "target_lang": "en-US", "project_id": "bare",
        })
        assert r.status_code == 200
        assert seen["glossary"] == ""

    def test_blank_project_id_treated_as_none(self, client):
        """空白 project_id 視同未提供。"""
        c, _store, seen = client
        r = c.post("/localization/translate", json={
            "text": "x", "target_lang": "en-US", "project_id": "   ",
        })
        assert r.status_code == 200
        assert seen["glossary"] == ""
