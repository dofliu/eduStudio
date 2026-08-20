"""core/infocards 資料層測試（Phase C-1）：models / cost / schemas。純資料，不打外部。"""
from __future__ import annotations

import pytest

from core.infocards import models
from core.infocards.cost import estimate_cost
from core.infocards.schemas import (
    AICost,
    ComicData,
    InfographicData,
    PresentationData,
    PresentationOutline,
    Slide,
)


# ── models ──
class TestModels:
    def test_model_ids(self):
        # 2026-08-18 更新；id 均由帳號 models.list 實測可用。
        assert models.TEXT_MODELS["flash"]["id"] == "gemini-3.6-flash"
        assert models.TEXT_MODELS["lite"]["id"] == "gemini-3.5-flash-lite"
        assert models.IMAGE_MODELS["pro"]["id"] == "gemini-3-pro-image"
        assert models.DEFAULT_TEXT_MODEL == "gemini-3.6-flash"
        assert models.DEFAULT_IMAGE_MODEL == "gemini-3.1-flash-image"

    def test_entry_tier_aligned_to_lite_image(self):
        # 2026-07：入門階由 2.5-flash-image 對齊為 Nano Banana 2 Lite。
        assert models.IMAGE_MODELS["lite"]["id"] == "gemini-3.1-flash-lite-image"
        # legacy key 已改名為 lite（frontend 只吃 .values()，key 不外露）。
        assert "legacy" not in models.IMAGE_MODELS

    def test_pricing_keyed_by_image_id(self):
        assert models.MODEL_PRICING["image"]["gemini-3.1-flash-lite-image"] == 0.002
        assert models.MODEL_PRICING["image"]["gemini-3.1-flash-image"] == 0.003
        assert models.MODEL_PRICING["image"]["gemini-3-pro-image"] == 0.04
        # 舊工作紀錄仍可能引用 → 定價保留，避免歷史計帳記 $0。
        assert models.MODEL_PRICING["image"]["gemini-2.5-flash-image"] == 0.003

    def test_options_helpers(self):
        assert len(models.text_model_options()) == 6
        assert len(models.image_model_options()) == 3
        assert len(models.specialized_model_options()) == 4
        assert {m["id"] for m in models.specialized_model_options()} == {
            "gemini-3.5-live-translate-preview",
            "gemini-3.1-flash-live-preview",
            "gemini-3.1-flash-tts-preview",
            "gemini-omni-flash-preview",
        }


# ── cost ──
class TestCost:
    def test_image_only_cost(self):
        c = estimate_cost(0, 0, 10, "gemini-3-pro-image")
        assert c["totalCost"] == 0.4  # 10 * 0.04
        assert c["currency"] == "USD"
        assert c["breakdown"]["imageCount"] == 10
        assert c["breakdown"]["imageModel"] == "gemini-3-pro-image"

    def test_text_cost(self):
        c = estimate_cost(1000, 1000, 0, "gemini-2.5-flash-image")
        assert c["breakdown"]["textInput"] == round(0.00001875, 5)
        assert c["breakdown"]["textOutput"] == round(0.000075, 5)
        assert c["breakdown"]["imageGeneration"] == 0.0

    def test_unknown_model_falls_back_to_flash(self):
        c = estimate_cost(0, 0, 1, "totally-unknown-model")
        assert c["totalCost"] == 0.003  # fallback flash 定價

    def test_breakdown_camelcase_keys(self):
        c = estimate_cost(100, 100, 1, "gemini-2.5-flash-image")
        assert set(c["breakdown"]) == {
            "textInput", "textOutput", "imageGeneration", "imageCount", "imageModel"
        }
        # cost dict 可被 AICost schema 驗證（契約一致）
        AICost.model_validate(c)


# ── schemas ──
class TestSchemas:
    def test_presentation_minimal_camelcase(self):
        p = PresentationData(
            mainTitle="靜力學", subtitle="第四章", themeColor="#123456", style="academic",
            slides=[Slide(id="s1", layout="title_cover", title="封面", speakerNotes="講稿")],
        )
        dumped = p.model_dump()
        assert dumped["mainTitle"] == "靜力學"
        assert dumped["slides"][0]["speakerNotes"] == "講稿"

    def test_infographic_minimal(self):
        ig = InfographicData(
            mainTitle="T", subtitle="S", layout="grid", themeColor="#fff", style="vibrant",
        )
        assert ig.layout == "grid" and ig.sections == []

    def test_comic_minimal(self):
        c = ComicData(title="漫畫", storySummary="故事", characterVisualBible="角色", style="comic")
        assert c.panels == []

    def test_outline(self):
        o = PresentationOutline(
            id="A", label="方案 A", approach="敘事型", suggestedTheme="forest",
            suggestedTypography="modern", mainTitle="T", subtitle="S",
        )
        assert o.estimatedImageCount == 0

    def test_invalid_enum_rejected(self):
        with pytest.raises(Exception):
            Slide(id="s", layout="bogus_layout", title="x", speakerNotes="")

    def test_slide_legacy_fields_optional(self):
        # 新資料用 sections；legacy content/bulletPoints 可省略
        s = Slide(id="s", layout="bullet_list", title="t", speakerNotes="n")
        assert s.sections is None and s.content is None
