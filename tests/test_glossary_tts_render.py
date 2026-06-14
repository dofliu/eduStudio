"""F9-2h — render 旁白套該課 glossary 讀音表（job ↔ 課 → TTS）。

對應 [JOB_COURSE_ASSOCIATION_RFC.md](../docs/JOB_COURSE_ASSOCIATION_RFC.md) §4.2：
F9-2g 已把 `JobRecord.project_id` 落地，本刀讓 render 旁白前以
`ProjectStore.get_glossary(project_id).to_pronunciation_map()` 取讀音表，render 期間
掛上 `tts_backend.course_pronunciation_override`，`normalize_text` 在呼叫端未顯式給
`extra_pronunciation` 時自動沿用 → 旁白照該課術語讀音念。

三層覆蓋：
1. `tts_backend.course_pronunciation_override` + `normalize_text` 的 render-scoped 套用
   （顯式 arg 優先、context 還原、巢狀安全）。
2. `server.runner._resolve_course_pronunciation`（fail-soft：無 project_id / 課不存在 /
   無 glossary / 空讀音表 → None）。
3. `server.runner._run_render` 把 override 在 inner render 期間掛上、出去還原（wiring）。

全程不打真 API、不真跑 TTS/ffmpeg（monkeypatch inner / tmp 隔離 ProjectStore）。
"""
from __future__ import annotations

import asyncio

import pytest

import core.project as project_mod
import server.runner as runner_mod
import tts_backend
from core.glossary import Glossary, GlossaryEntry
from server.schemas import (
    JobOptions,
    JobRecord,
    JobSource,
    JobState,
    SourceType,
    utc_now,
)


# ---------------------------------------------------------------- fixtures / helpers


@pytest.fixture(autouse=True)
def _reset_course_override():
    """每測前後都把 module-level 課程讀音覆寫清乾淨，避免測試互相污染。"""
    tts_backend._COURSE_PRONUNCIATION = None
    yield
    tts_backend._COURSE_PRONUNCIATION = None


def _make_rec(project_id: str | None = None) -> JobRecord:
    return JobRecord(
        id="job_test",
        source_type=SourceType.DOCUMENT,
        source=JobSource(path="/fake.md"),
        options=JobOptions(),
        state=JobState.RENDERING,
        created_at=utc_now(),
        updated_at=utc_now(),
        project_id=project_id,
    )


def _glossary_with_reading() -> Glossary:
    return Glossary(
        course="材力",
        entries=[
            GlossaryEntry(term="PID", reading="P I D 控制器", aliases=["pid"]),
            GlossaryEntry(term="ω_n", reading="omega n"),
            # 沒 reading 的條目不該進讀音表
            GlossaryEntry(term="自然頻率", translations={"en": "natural frequency"}),
        ],
    )


# ---------------------------------------------------------------- normalize_text 套用


class TestNormalizeTextCourseOverride:
    """normalize_text 在 render-scoped 覆寫下的行為。"""

    def test_no_override_pure_global(self):
        """沒掛覆寫 → 純全域行為（PID 不會被改）。"""
        assert "PID" in tts_backend.normalize_text("看 PID 控制")

    def test_override_applies_when_arg_absent(self):
        """掛了覆寫、呼叫端未給 extra → 自動套課程讀音。"""
        with tts_backend.course_pronunciation_override({"PID": "P I D"}):
            out = tts_backend.normalize_text("看 PID 控制")
        assert "P I D" in out
        assert "PID" not in out

    def test_explicit_arg_wins_over_override(self):
        """顯式給 extra → 蓋掉 render-scoped 覆寫（caller 永遠優先）。"""
        with tts_backend.course_pronunciation_override({"PID": "P I D"}):
            out = tts_backend.normalize_text(
                "看 PID 控制", extra_pronunciation={"PID": "屁挨低"}
            )
        assert "屁挨低" in out
        assert "P I D" not in out

    def test_explicit_empty_dict_disables_course(self):
        """顯式給 {} = 「不要課程讀音」（is not None → 不退回覆寫）。"""
        with tts_backend.course_pronunciation_override({"PID": "P I D"}):
            out = tts_backend.normalize_text("看 PID 控制", extra_pronunciation={})
        assert "PID" in out  # 課程讀音被顯式 {} 擋掉，沿用全域

    def test_context_restores_after_exit(self):
        """出 with 後 module-level state 還原成 None。"""
        assert tts_backend._COURSE_PRONUNCIATION is None
        with tts_backend.course_pronunciation_override({"PID": "P I D"}):
            assert tts_backend._COURSE_PRONUNCIATION == {"PID": "P I D"}
        assert tts_backend._COURSE_PRONUNCIATION is None

    def test_context_restores_on_exception(self):
        """with 內拋例外也要還原（finally 語意）。"""
        with pytest.raises(RuntimeError):
            with tts_backend.course_pronunciation_override({"PID": "P I D"}):
                raise RuntimeError("boom")
        assert tts_backend._COURSE_PRONUNCIATION is None

    def test_nested_override_restores_outer(self):
        """巢狀覆寫：內層出去後還原成外層、最後還原成 None。"""
        with tts_backend.course_pronunciation_override({"A": "a"}):
            with tts_backend.course_pronunciation_override({"B": "b"}):
                assert tts_backend._COURSE_PRONUNCIATION == {"B": "b"}
            assert tts_backend._COURSE_PRONUNCIATION == {"A": "a"}
        assert tts_backend._COURSE_PRONUNCIATION is None

    def test_none_or_empty_mapping_is_noop(self):
        """None / 空 dict 掛上 = no-op（fail-soft，沿用全域）。"""
        with tts_backend.course_pronunciation_override(None):
            assert tts_backend._COURSE_PRONUNCIATION is None
        with tts_backend.course_pronunciation_override({}):
            assert tts_backend._COURSE_PRONUNCIATION is None


# ---------------------------------------------------------------- _resolve_course_pronunciation


class TestResolveCoursePronunciation:
    """runner._resolve_course_pronunciation — 從 job.project_id 取該課讀音表 (fail-soft)。"""

    @pytest.fixture
    def store_at(self, tmp_path, monkeypatch):
        """讓 `ProjectStore()`（無參數）落在 tmp_path，回傳已建好的真 store。"""
        OrigStore = project_mod.ProjectStore
        store = OrigStore(root=tmp_path)
        monkeypatch.setattr(
            project_mod, "ProjectStore", lambda *a, **k: OrigStore(root=tmp_path)
        )
        return store

    def test_no_project_id_returns_none(self):
        """無主 job（project_id=None）→ None，零 ProjectStore 觸碰。"""
        assert runner_mod._resolve_course_pronunciation(_make_rec(None)) is None

    def test_project_with_glossary_returns_reading_map(self, store_at):
        """課有 glossary + 有 reading → 回 surface form → reading map。"""
        store_at.create("mech101", "材力")
        store_at.save_glossary("mech101", _glossary_with_reading())
        out = runner_mod._resolve_course_pronunciation(_make_rec("mech101"))
        assert out == {
            "PID": "P I D 控制器",
            "pid": "P I D 控制器",
            "ω_n": "omega n",
        }
        assert "自然頻率" not in out  # 沒 reading 的不進讀音表

    def test_unknown_project_returns_none_fail_soft(self, store_at):
        """課不存在（get_glossary 拋 ProjectNotFoundError）→ fail-soft None，不爆。"""
        out = runner_mod._resolve_course_pronunciation(_make_rec("ghost"))
        assert out is None

    def test_project_without_glossary_returns_none(self, store_at):
        """課在但還沒建 glossary → None（沿用全域）。"""
        store_at.create("mech101", "材力")
        out = runner_mod._resolve_course_pronunciation(_make_rec("mech101"))
        assert out is None

    def test_empty_reading_map_returns_none(self, store_at):
        """glossary 有條目但都沒 reading → 空 map → 收斂成 None（no-op override）。"""
        store_at.create("mech101", "材力")
        store_at.save_glossary(
            "mech101",
            Glossary(course="材力", entries=[GlossaryEntry(term="自然頻率")]),
        )
        out = runner_mod._resolve_course_pronunciation(_make_rec("mech101"))
        assert out is None


# ---------------------------------------------------------------- _run_render wiring


class TestRunRenderWiring:
    """_run_render 把課程讀音覆寫在 inner render 期間掛上、出去還原。"""

    @pytest.mark.asyncio
    async def test_override_active_during_inner_and_restored(self, monkeypatch):
        """resolve 出讀音表 → inner 執行時 module-level 已掛上 → 出去還原 None。"""
        captured: dict = {}

        async def stub_inner(store, rec, *, section_id=None):
            captured["during"] = tts_backend._COURSE_PRONUNCIATION

        monkeypatch.setattr(runner_mod, "_run_render_inner", stub_inner)
        monkeypatch.setattr(
            runner_mod, "_resolve_course_pronunciation", lambda rec: {"PID": "P I D"}
        )

        await runner_mod._run_render(store=None, rec=_make_rec("mech101"))

        assert captured["during"] == {"PID": "P I D"}
        # 出 with 後還原（不洩漏到下個 render）
        assert tts_backend._COURSE_PRONUNCIATION is None

    @pytest.mark.asyncio
    async def test_no_glossary_leaves_global_behavior(self, monkeypatch):
        """resolve 回 None（無主 job / 無 glossary）→ inner 期間覆寫仍 None（沿用全域）。"""
        captured: dict = {}

        async def stub_inner(store, rec, *, section_id=None):
            captured["during"] = tts_backend._COURSE_PRONUNCIATION

        monkeypatch.setattr(runner_mod, "_run_render_inner", stub_inner)
        monkeypatch.setattr(
            runner_mod, "_resolve_course_pronunciation", lambda rec: None
        )

        await runner_mod._run_render(store=None, rec=_make_rec(None))

        assert captured["during"] is None
        assert tts_backend._COURSE_PRONUNCIATION is None
