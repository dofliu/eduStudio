"""core/infocards/poster_service 測試（Phase C-2）。prompt 建構 deterministic + mock 生圖。"""
from __future__ import annotations

import core.infocards.poster_service as poster
from core.infocards.poster_service import build_poster_prompt, generate_poster


class TestBuildPrompt:
    def test_named_style_and_ratio(self):
        p = build_poster_prompt("靜力學重點", "academic", aspect_ratio="horizontal")
        assert "VISUAL STYLE: academic" in p
        assert "ASPECT RATIO: 16:9" in p
        assert "Traditional Chinese" in p  # HIGH_QUALITY 文字渲染要求
        assert "靜力學重點" in p

    def test_custom_style(self):
        p = build_poster_prompt("t", "custom", custom_style_prompt="水彩 watercolor")
        assert "CRITICAL VISUAL STYLE" in p and "水彩 watercolor" in p
        assert "ABANDON ALL DEFAULTS" in p

    def test_density_variants(self):
        assert "MINIMAL" in build_poster_prompt("t", "navy", density="minimal")
        assert "DETAILED" in build_poster_prompt("t", "navy", density="detailed")
        # 未知 density fallback balanced
        assert "BALANCED" in build_poster_prompt("t", "navy", density="bogus")

    def test_refinement_optional(self):
        assert "USER REFINEMENT REQUEST: 加大標題" in build_poster_prompt(
            "t", "navy", refinement="加大標題")
        assert "USER REFINEMENT REQUEST" not in build_poster_prompt("t", "navy")

    def test_content_truncated_at_5000(self):
        long = "字" * 6000
        p = build_poster_prompt(long, "navy")
        # 只取前 5000 字
        assert ("字" * 5000) in p and ("字" * 5001) not in p

    def test_ratio_fallback(self):
        # 未知 aspect_ratio fallback vertical(3:4)
        assert "ASPECT RATIO: 3:4" in build_poster_prompt("t", "navy", aspect_ratio="weird")


class TestGeneratePoster:
    def test_returns_image_and_prompt(self, monkeypatch):
        seen = {}

        def fake_img(prompt, model=None, api_key=None):
            seen["model"] = model
            seen["prompt"] = prompt
            return "data:image/png;base64,POSTER"

        monkeypatch.setattr(poster, "generate_image_b64", fake_img)
        out = generate_poster("內容", "forest", aspect_ratio="square")
        assert out["imageUrl"] == "data:image/png;base64,POSTER"
        assert "ASPECT RATIO: 1:1" in out["prompt"]
        # 預設用 pro 圖片模型
        assert seen["model"] == "gemini-3-pro-image-preview"

    def test_blank_image_on_failure(self, monkeypatch):
        monkeypatch.setattr(poster, "generate_image_b64", lambda prompt, model=None, api_key=None: "")
        out = generate_poster("t", "navy")
        assert out["imageUrl"] == "" and out["prompt"]
