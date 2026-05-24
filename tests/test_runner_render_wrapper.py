"""server.runner._run_render — iter 83 (B1+B2 Option B) wrapper 安全鎖.

_run_render 從 iter 83 上線後沒對應直接測試. 核心 video_dimensions_override
(core.config) / talking_head_override (core.photo_overlay) context manager 各自
module 都有覆蓋, 但 runner 內這層 wrapper 的 value-add 從沒打:

  - rec.options.aspect_ratio 預設 fallback "16:9" (None 該退預設)
  - rec.options.resolution 預設 fallback "1080p"
  - rec.options.talking_head 預設 fallback "long_form_only"
  - is_short = aspect == "9:16" OR length_mode == "ultra_quick" OR short_video_layout
    (三條件 OR, 任一觸發 — 不是 AND 也不是只看 aspect; iter 92 設計意圖)
  - video_dimensions_override(aspect, resolution) OUTER context
  - talking_head_override(th_mode, is_short_form=is_short) INNER context (兩 context
    同時 active 期間 _run_render_inner 才執行)
  - 透傳 section_id 進 _run_render_inner (None / 字串都該透傳, runner 內不 normalize)
  - 出 with 後兩 module-level state 都該 restore

任何 refactor 不小心動 fallback 字串 / is_short 條件少一條 / 兩 context 沒
nest / section_id 沒透傳就直接上線, 跟 iter 111-131 同思路 (route / helper
safety lock).

策略 = monkeypatch _run_render_inner 成 async stub, 在 stub 內 snapshot
core.config.VIDEO_WIDTH/HEIGHT + core.photo_overlay._RUNTIME_TALKING_HEAD_MODE/
IS_SHORT_FORM 證明兩 context 都 active. 不真跑渲染 / ffmpeg / TTS.
"""
from __future__ import annotations

import asyncio

import pytest

import core.config as config_mod
import core.photo_overlay as photo_mod
import server.runner as runner_mod
from server.schemas import (
    JobOptions,
    JobRecord,
    JobSource,
    JobState,
    SourceType,
    utc_now,
)


# ---------------------------------------------------------------- fixtures


def _make_rec(**opts) -> JobRecord:
    """最小 JobRecord — 直接 construct, 不走 store.create (避開 schedule_job side effect).

    _run_render 只讀 rec.options.* + rec.source_type, 其他欄位佔位即可.
    """
    return JobRecord(
        id="job_test",
        source_type=SourceType.DOCUMENT,
        source=JobSource(path="/fake.md"),
        options=JobOptions(**opts),
        state=JobState.RENDERING,
        created_at=utc_now(),
        updated_at=utc_now(),
    )


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stub _run_render_inner — snapshot 兩 context 在 inner 執行時的 runtime state.

    function-local `from core.config import ... video_dimensions_override` / `from
    core.photo_overlay import talking_head_override` 每次 _run_render 進來都重新
    lookup module attribute, monkeypatch runner_mod._run_render_inner 直接生效
    (跟 iter 126/127/128/130 同 pattern).
    """
    state: dict = {"called": 0}

    async def stub_inner(store, rec, *, section_id=None):
        state["called"] += 1
        state["store"] = store
        state["rec"] = rec
        state["section_id"] = section_id
        # snapshot module-level state — 證明兩 context manager 同時 active
        state["video_width"] = config_mod.VIDEO_WIDTH
        state["video_height"] = config_mod.VIDEO_HEIGHT
        state["talking_head_mode"] = photo_mod._RUNTIME_TALKING_HEAD_MODE
        state["is_short_form"] = photo_mod._RUNTIME_IS_SHORT_FORM

    monkeypatch.setattr(runner_mod, "_run_render_inner", stub_inner)
    return state


# ---------------------------------------------------------------- TestDefaultFallbacks


class TestDefaultFallbacks:
    """三個 None options 該套寫死預設 — 不該洩到 context manager 拿 None 炸."""

    @pytest.mark.asyncio
    async def test_aspect_ratio_none_falls_back_to_16_9(self, captured):
        """rec.options.aspect_ratio=None → "16:9" → VIDEO_WIDTH=1920 (16:9 1080p 預設).

        鎖 `aspect = rec.options.aspect_ratio or "16:9"` 不被改成 .get default 或
        誤設 "9:16" 預設 (橫向是預設, 直向是 opt-in).
        """
        rec = _make_rec(aspect_ratio=None, resolution=None)
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["called"] == 1
        assert captured["video_width"] == 1920  # 16:9 1080p
        assert captured["video_height"] == 1080

    @pytest.mark.asyncio
    async def test_resolution_none_falls_back_to_1080p(self, captured):
        """rec.options.resolution=None → "1080p" → height=1080 (在 16:9 下).

        鎖 `resolution = rec.options.resolution or "1080p"` 不被偷改 1440p / 4K
        當預設 (1440p/4K 渲染慢 2-3x, 預設不該打開).
        """
        rec = _make_rec(aspect_ratio="16:9", resolution=None)
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["video_width"] == 1920
        assert captured["video_height"] == 1080

    @pytest.mark.asyncio
    async def test_talking_head_none_falls_back_to_long_form_only(self, captured):
        """rec.options.talking_head=None → "long_form_only" (iter 92 預設策略).

        鎖 `th_mode = rec.options.talking_head or "long_form_only"` 不被偷改成
        "always" / "off" 預設 — long_form_only 是 iter 92 設計意圖 (短片 skip
        長片 show), 改任一邊都是行為大改.
        """
        rec = _make_rec(talking_head=None)
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["talking_head_mode"] == "long_form_only"


# ---------------------------------------------------------------- TestIsShortComputation


class TestIsShortComputation:
    """is_short 三條件 OR — 各條件單獨能觸發 / 三個都 False 不該觸發 / 三個都 True 仍 True."""

    @pytest.mark.asyncio
    async def test_aspect_9_16_alone_triggers_short(self, captured):
        """aspect_ratio="9:16" 單獨 → is_short=True.

        鎖 OR 第一項. 直向影片本質是短片格式 (Shorts/TikTok/Reels), 即使
        length_mode 不是 ultra_quick, 也該套短片策略.
        """
        rec = _make_rec(
            aspect_ratio="9:16", resolution="1080p",
            length_mode=None, short_video_layout=False,
        )
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["is_short_form"] is True

    @pytest.mark.asyncio
    async def test_ultra_quick_alone_triggers_short(self, captured):
        """length_mode="ultra_quick" 單獨 → is_short=True (即使 16:9 橫向).

        鎖 OR 第二項. ultra_quick 是 30 秒短講 (iter 88 加), 不該因 aspect=16:9
        被當成長片仍畫頭像.
        """
        rec = _make_rec(
            aspect_ratio="16:9", resolution="1080p",
            length_mode="ultra_quick", short_video_layout=False,
        )
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["is_short_form"] is True

    @pytest.mark.asyncio
    async def test_short_video_layout_alone_triggers_short(self, captured):
        """short_video_layout=True 單獨 → is_short=True.

        鎖 OR 第三項. 用戶手動勾 short_video_layout (iter 88 大字 layout) 即使
        其他兩條件都關, 仍該被視作短片.
        """
        rec = _make_rec(
            aspect_ratio="16:9", resolution="1080p",
            length_mode="quick", short_video_layout=True,
        )
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["is_short_form"] is True

    @pytest.mark.asyncio
    async def test_all_three_false_is_long_form(self, captured):
        """三條件都關 (預設長片配置) → is_short=False.

        鎖 OR 結果 — 若不小心改成 AND, 這 test 仍會過 (False AND False AND False
        = False), 但搭配前三 test (各 OR 條件單獨能觸發) 就能擋 AND refactor.
        """
        rec = _make_rec(
            aspect_ratio="16:9", resolution="1080p",
            length_mode="quick", short_video_layout=False,
        )
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["is_short_form"] is False

    @pytest.mark.asyncio
    async def test_all_three_true_still_short(self, captured):
        """三條件都中 → is_short=True (不被多重觸發干擾).

        鎖 OR 不被改成 XOR / 互斥邏輯.
        """
        rec = _make_rec(
            aspect_ratio="9:16", resolution="1080p",
            length_mode="ultra_quick", short_video_layout=True,
        )
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["is_short_form"] is True

    @pytest.mark.asyncio
    async def test_length_mode_none_does_not_trigger_short(self, captured):
        """length_mode=None (預設) 該被 `or ""` 防呆, 不該 raise AttributeError /
        誤判 None == "ultra_quick" 為 True.

        鎖 `(rec.options.length_mode or "") == "ultra_quick"` 兩段防呆 (or "" +
        eq) 都不可被偷拿掉.
        """
        rec = _make_rec(
            aspect_ratio="16:9", resolution="1080p",
            length_mode=None, short_video_layout=False,
        )
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["is_short_form"] is False


# ---------------------------------------------------------------- TestExplicitOptionsHonored


class TestExplicitOptionsHonored:
    """非 None options 該被尊重 — 不被 wrapper 覆寫."""

    @pytest.mark.asyncio
    async def test_explicit_9_16_1440p_dimensions(self, captured):
        """aspect_ratio="9:16", resolution="1440p" → (1440, 2560) 直向 1440p.

        鎖 dimensions 真的進 video_dimensions_override — 若 wrapper 把 args
        弄反 (給成 ("1440p", "9:16")), resolve_video_dimensions 找不到組合會
        fallback (1920, 1080) 而非 (1440, 2560).
        """
        rec = _make_rec(aspect_ratio="9:16", resolution="1440p")
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["video_width"] == 1440
        assert captured["video_height"] == 2560

    @pytest.mark.asyncio
    async def test_explicit_talking_head_off_honored(self, captured):
        """talking_head="off" → 透傳, 不被預設覆寫.

        鎖 `or "long_form_only"` 只在 falsy 時退預設, 非空字串該直通.
        """
        rec = _make_rec(talking_head="off")
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["talking_head_mode"] == "off"

    @pytest.mark.asyncio
    async def test_explicit_talking_head_always_honored(self, captured):
        """talking_head="always" → 透傳.

        鎖 wrapper 不做白名單 (refactor 偷把未認的字串 fallback 成預設, "always"
        是合法字串該直通).
        """
        rec = _make_rec(talking_head="always")
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["talking_head_mode"] == "always"


# ---------------------------------------------------------------- TestContextRestoreAfterReturn


class TestContextRestoreAfterReturn:
    """兩 context manager 是 `with` 包進來的, _run_render 返回後該全 restore."""

    @pytest.mark.asyncio
    async def test_video_dimensions_restored_after_return(self, captured):
        """直向 9:16 1080p 渲染後, VIDEO_WIDTH/HEIGHT 該回到原 16:9 1080p 預設.

        鎖 video_dimensions_override.__exit__ 真有被叫 — 若 wrapper 被改成
        手動 setattr 不用 context manager, 異常路徑會洩 state.
        """
        before_w = config_mod.VIDEO_WIDTH
        before_h = config_mod.VIDEO_HEIGHT
        rec = _make_rec(aspect_ratio="9:16", resolution="1080p")
        await runner_mod._run_render(store=None, rec=rec)

        assert config_mod.VIDEO_WIDTH == before_w
        assert config_mod.VIDEO_HEIGHT == before_h

    @pytest.mark.asyncio
    async def test_talking_head_restored_after_return(self, captured):
        """talking_head="off" 渲染後, _RUNTIME_TALKING_HEAD_MODE 該回 None.

        鎖 talking_head_override 的 finally restore — 沒 restore 下個 job 仍
        被 force off.
        """
        before_mode = photo_mod._RUNTIME_TALKING_HEAD_MODE
        before_short = photo_mod._RUNTIME_IS_SHORT_FORM
        rec = _make_rec(talking_head="off", aspect_ratio="9:16")
        await runner_mod._run_render(store=None, rec=rec)

        assert photo_mod._RUNTIME_TALKING_HEAD_MODE == before_mode
        assert photo_mod._RUNTIME_IS_SHORT_FORM == before_short

    @pytest.mark.asyncio
    async def test_both_contexts_active_inside_inner(self, captured):
        """inner 執行的瞬間, video_dimensions 跟 talking_head 兩 module state
        都被 patch — 不是「先進先出」一個一個跑.

        鎖 nesting (兩 with 巢狀, inner await 看到兩 context 同時 active);
        若 refactor 改成「先 video_dimensions enter→exit, 再 talking_head
        enter→exit」, 這 test 該 fail (snapshot 拿到的會是 default 而非
        force overridden).
        """
        rec = _make_rec(
            aspect_ratio="9:16", resolution="1440p",
            talking_head="off",
        )
        await runner_mod._run_render(store=None, rec=rec)

        # 在 inner 內同時看到兩 context 的 override 值
        assert captured["video_width"] == 1440
        assert captured["video_height"] == 2560
        assert captured["talking_head_mode"] == "off"


# ---------------------------------------------------------------- TestSectionIdPassthrough


class TestSectionIdPassthrough:
    """section_id (PR-4a 加, 單 section re-render 用) 該透傳, runner 內不 normalize."""

    @pytest.mark.asyncio
    async def test_section_id_none_default(self, captured):
        """不傳 section_id → stub 收到 None (kwarg 預設透傳).

        鎖 _run_render 不把 None 偷改成空字串 / "all" / 別值.
        """
        rec = _make_rec()
        await runner_mod._run_render(store=None, rec=rec)

        assert captured["section_id"] is None

    @pytest.mark.asyncio
    async def test_section_id_explicit_passed_through(self, captured):
        """section_id="q1" → stub 該收到 "q1" 原值.

        鎖透傳, 不被 lowercase / strip / 加 prefix.
        """
        rec = _make_rec()
        await runner_mod._run_render(store=None, rec=rec, section_id="q1")

        assert captured["section_id"] == "q1"

    @pytest.mark.asyncio
    async def test_store_and_rec_passed_through(self, captured):
        """store + rec 兩 positional 都該原物件透傳 — wrapper 不該複製 / 重建.

        鎖 inner 拿到的是 caller 給的同一物件 (id check), 避免 wrapper 偷
        deepcopy 後 inner 對 rec 的改動 caller 看不到.
        """
        rec = _make_rec()
        store_sentinel = object()  # 拿任意 sentinel — _run_render 不該用它
        await runner_mod._run_render(store=store_sentinel, rec=rec)

        assert captured["store"] is store_sentinel
        assert captured["rec"] is rec
