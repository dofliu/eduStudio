"""單頁微調 refine_service 測試（Phase C）。

純 prompt 組裝零 API；refine 主流程 mock Gemini。對齊 refineSlidePrompt.ts /
speakerNotesPrompt.ts / presentationService.ts:refinePresentationSlide。
"""
from __future__ import annotations

import core.infocards.refine_service as rf
from core.infocards.schemas import Slide


class TestPromptBuilders:
    def test_persona_block(self):
        assert rf.build_persona_block({"tone": "活潑", "audience": "大學生"}) == "語氣：活潑；目標受眾：大學生"
        assert rf.build_persona_block({}) == ""
        assert rf.build_persona_block(None) == ""

    def test_refine_prompt_without_persona(self):
        p = rf.build_refine_slide_prompt({"title": "封面"}, "改成更專業")
        assert p.startswith('Refine this slide based on: "改成更專業".')
        assert "個人簡報風格設定" not in p
        assert '"title": "封面"' in p

    def test_refine_prompt_with_persona(self):
        p = rf.build_refine_slide_prompt({"title": "t"}, "x", {"tone": "正式"})
        assert "個人簡報風格設定" in p and "語氣：正式" in p

    def test_slide_content_block(self):
        block = rf.build_slide_content_block(
            {"title": "牛頓", "content": "慣性", "bulletPoints": ["F=ma", "作用力"]})
        assert "標題：牛頓" in block and "內容：慣性" in block and "F=ma / 作用力" in block

    def test_speaker_notes_prompt_last_slide(self):
        p = rf.build_speaker_notes_prompt(
            {"title": "結論"}, {"mainTitle": "簡報", "slideIndex": 4, "totalSlides": 5}, {"tone": "親切"})
        assert "總結全場" in p and "語氣：親切" in p and "第 5 頁" in p

    def test_speaker_notes_prompt_mid_slide(self):
        p = rf.build_speaker_notes_prompt(
            {"title": "中段"}, {"mainTitle": "簡報", "slideIndex": 1, "totalSlides": 5}, {})
        assert "自然銜接到下一頁" in p


class TestRefineSlide:
    def test_merges_and_validates(self, monkeypatch):
        # AI 只回 title/content，其餘欄位應由原 slide 補回。
        monkeypatch.setattr(rf, "generate_json",
                            lambda prompt, model=None: {"title": "新標題", "content": "新內容"})
        original = {"id": "s1", "layout": "bullet_list", "title": "舊", "content": "舊內容",
                    "speakerNotes": "備忘", "bulletPoints": ["a", "b", "c"]}
        out = rf.refine_presentation_slide(original, "改標題", slide_index=2, total_slides=5)
        assert isinstance(out, Slide)
        assert out.title == "新標題" and out.content == "新內容"
        assert out.id == "s1"  # 原欄位保留
        assert out.speakerNotes == "備忘"

    def test_reconcile_layout_applied(self, monkeypatch):
        monkeypatch.setattr(rf, "generate_json",
                            lambda prompt, model=None: {"title": "安裝步驟", "content": "步驟 依序 操作",
                                                        "layout": "bullet_list"})
        out = rf.refine_presentation_slide({"id": "s1", "layout": "bullet_list", "title": "x",
                                            "content": "", "speakerNotes": ""},
                                           "改成流程", slide_index=2, total_slides=5)
        assert out.layout == "process_steps"  # 規則強訊號覆蓋

    def test_drops_imageprompt_on_native(self, monkeypatch):
        monkeypatch.setattr(rf, "generate_json",
                            lambda prompt, model=None: {"layout": "bullet_list",
                                                        "imagePrompt": "AI 雞婆的圖", "title": "t"})
        out = rf.refine_presentation_slide({"id": "s1", "layout": "bullet_list", "title": "t",
                                            "content": "", "speakerNotes": ""}, "x",
                                           slide_index=2, total_slides=5)
        assert out.imagePrompt is None

    def test_generates_image_on_allowed_layout(self, monkeypatch):
        monkeypatch.setattr(rf, "generate_json",
                            lambda prompt, model=None: {"layout": "text_and_image",
                                                        "imagePrompt": "a diagram", "title": "圖文"})
        monkeypatch.setattr(rf, "generate_image_b64",
                            lambda prompt, model=None: "data:image/png;base64,IMG")
        out = rf.refine_presentation_slide({"id": "s1", "layout": "bullet_list", "title": "t",
                                            "content": "內容", "speakerNotes": ""}, "加圖",
                                           slide_index=2, total_slides=5)
        assert out.imageUrl == "data:image/png;base64,IMG"


class TestRefineRoute:
    def test_route(self, tmp_path, monkeypatch):
        import pytest
        pytest.importorskip("fastapi.testclient")
        pytest.importorskip("multipart")
        from fastapi.testclient import TestClient

        import core.infocards.refine_service as rfs
        import server.routes.infocards as ic
        from core.infocards.share_store import ShareStore
        from server.main import create_app

        monkeypatch.setattr(ic, "get_share_store", lambda: ShareStore(db_path=str(tmp_path / "s.db")))
        monkeypatch.setattr(rfs, "generate_json", lambda prompt, model=None: {"title": "改好的", "content": "c"})
        app = create_app()
        with TestClient(app) as c:
            r = c.post("/api/refine", json={
                "slide": {"id": "s1", "layout": "bullet_list", "title": "舊", "content": "",
                          "speakerNotes": ""},
                "instruction": "改標題", "slideIndex": 1, "totalSlides": 3,
            })
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True and body["slide"]["title"] == "改好的"
