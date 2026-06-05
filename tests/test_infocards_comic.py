"""core/infocards gemini helper + comic_service 測試（Phase C-2）。mock Gemini，不打真 API。"""
from __future__ import annotations

import base64

import core.infocards.comic_service as comic
import core.infocards.gemini as gem
from core.infocards.schemas import ComicData


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, resp):
        self._resp = resp

    def generate_content(self, **kw):
        return self._resp


class _FakeClient:
    def __init__(self, resp):
        self.models = _FakeModels(resp)


# ── gemini helper ──
class TestGeminiHelper:
    def test_strip_fence(self):
        assert gem._strip_fence('```json\n{"a":1}\n```') == '{"a":1}'
        assert gem._strip_fence('  {"b":2}  ') == '{"b":2}'

    def test_generate_json_parses(self, monkeypatch):
        monkeypatch.setattr(gem, "_client", lambda api_key=None: _FakeClient(_FakeResp('{"x": 1}')))
        assert gem.generate_json("p") == {"x": 1}

    def test_generate_json_bad_returns_empty(self, monkeypatch):
        monkeypatch.setattr(gem, "_client", lambda api_key=None: _FakeClient(_FakeResp("not json")))
        assert gem.generate_json("p") == {}

    def test_generate_image_b64(self, monkeypatch):
        monkeypatch.setattr(gem, "_client", lambda api_key=None: _FakeClient(_FakeResp(None)))
        import core.diagram_image_gen as dig
        monkeypatch.setattr(dig, "_extract_image_bytes", lambda resp: b"PNGBYTES")
        out = gem.generate_image_b64("draw a cat")
        assert out.startswith("data:image/png;base64,")
        assert base64.b64decode(out.split(",", 1)[1]) == b"PNGBYTES"

    def test_generate_image_b64_no_image_returns_blank(self, monkeypatch):
        monkeypatch.setattr(gem, "_client", lambda api_key=None: _FakeClient(_FakeResp(None)))
        import core.diagram_image_gen as dig
        monkeypatch.setattr(dig, "_extract_image_bytes", lambda resp: None)
        assert gem.generate_image_b64("x") == ""


# ── comic service ──
_FAKE_COMIC = {
    "title": "力的合成",
    "storySummary": "兩個力如何相加",
    "characterVisualBible": "小明，藍衣短髮",
    "panels": [
        {"id": "panel_1", "panelNumber": 1, "description": "教室", "dialogue": "今天學向量",
         "cameraDetail": "遠景", "imagePrompt": "a classroom"},
        {"id": "panel_2", "panelNumber": 2, "description": "黑板", "dialogue": "F=F1+F2",
         "cameraDetail": "特寫", "imagePrompt": "a blackboard with vectors"},
    ],
}


class TestComicService:
    def test_generate_script_sets_style_and_prompt(self, monkeypatch):
        monkeypatch.setattr(comic, "generate_json", lambda prompt, model=None, response_schema=None: dict(_FAKE_COMIC))
        data = comic.generate_comic_script("向量加法", "comic", panels=2)
        assert isinstance(data, ComicData)
        assert data.style == "comic"
        assert data.title == "力的合成"
        assert len(data.panels) == 2
        assert data.promptUsed and "向量加法" in data.promptUsed  # 後端補 promptUsed

    def test_custom_style_in_prompt(self, monkeypatch):
        seen = {}

        def fake_json(prompt, model=None, response_schema=None):
            seen["prompt"] = prompt
            return dict(_FAKE_COMIC)

        monkeypatch.setattr(comic, "generate_json", fake_json)
        comic.generate_comic_script("t", "custom", custom="水彩風 watercolor", panels=3)
        assert "ART STYLE: 水彩風 watercolor" in seen["prompt"]
        assert "3 格漫畫" in seen["prompt"]

    def test_generate_images_fills_urls(self, monkeypatch):
        monkeypatch.setattr(comic, "generate_image_b64",
                            lambda prompt, model=None: f"data:image/png;base64,IMG({prompt})")
        data = ComicData.model_validate({**_FAKE_COMIC, "style": "comic"})
        out = comic.generate_comic_images(data)
        assert out.panels[0].imageUrl == "data:image/png;base64,IMG(a classroom)"
        assert out.panels[1].imageUrl.startswith("data:image/png;base64,")
