"""T2-4 schema 輸入界限測試。

`server/schemas.py` 過去 50 個 `Field()` 裡 **0 個** `ge/le/max_length` ——
數值可為負或極大值、字串無長度上限,而這些值直達 ffmpeg 參數(`subtitle_font_size`
進 `force_style`)、迴圈次數(`max_files` / `photo_max_select` / `slideCount`)
與 TTS 文字。這裡鎖住界限,避免日後有人加欄位時又忘了。

界限是「遠高於實務用量」的安全網,不是產品限制 —— 正常操作不該碰到。
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.schemas import JobOptions, JobSource


class TestNumericBounds:
    """數值欄位:負值 / 0 / 極大值都要被擋。"""

    @pytest.mark.parametrize(("field", "ok", "too_small", "too_big"), [
        ("max_files", 50, 0, 10_000),
        ("subtitle_font_size", 22, 0, 5_000),
        ("photo_max_select", 30, 0, 100_000),
    ])
    def test_bounds(self, field, ok, too_small, too_big):
        assert getattr(JobOptions(**{field: ok}), field) == ok
        with pytest.raises(ValidationError):
            JobOptions(**{field: too_small})
        with pytest.raises(ValidationError):
            JobOptions(**{field: too_big})

    @pytest.mark.parametrize("field", [
        "max_files", "subtitle_font_size", "photo_max_select",
    ])
    def test_negative_rejected(self, field):
        with pytest.raises(ValidationError):
            JobOptions(**{field: -1})

    @pytest.mark.parametrize("field", [
        "max_files", "subtitle_font_size", "photo_max_select",
    ])
    def test_none_still_allowed(self, field):
        """None = 用預設,是既有行為, 不能被界限擋掉。"""
        assert getattr(JobOptions(**{field: None}), field) is None


class TestStringBounds:
    @pytest.mark.parametrize(("field", "limit"), [
        ("output_name", 200),
        ("cover_speaker", 200),
        ("cover_narration", 5000),
        ("outro_narration", 5000),
        ("outro_url", 2048),
        ("photo_title_hint", 500),
        ("palette_bg", 32),
        ("subtitle_primary_color", 32),
        ("theme", 64),
    ])
    def test_max_length_enforced(self, field, limit):
        JobOptions(**{field: "a" * limit})            # 剛好上限 → 過
        with pytest.raises(ValidationError):
            JobOptions(**{field: "a" * (limit + 1)})  # 多一個字 → 擋

    def test_empty_string_still_allowed(self):
        """空字串在多處代表「用預設」, 不能被界限擋掉。"""
        assert JobOptions(cover_speaker="").cover_speaker == ""


class TestJobSourceBounds:
    @pytest.mark.parametrize(("field", "limit"), [
        ("path", 4096),
        ("url", 2048),
        ("session_id", 200),
    ])
    def test_max_length_enforced(self, field, limit):
        JobSource(**{field: "a" * limit})
        with pytest.raises(ValidationError):
            JobSource(**{field: "a" * (limit + 1)})


class TestNoUnboundedFieldsRemain:
    """漂移守衛:之後有人加欄位忘了給界限就會紅。

    只看會進迴圈 / 外部指令的 str 與 int;bool 與 Literal 本身就是界限。
    """

    @pytest.mark.parametrize("model", [JobOptions, JobSource])
    def test_every_str_or_int_field_is_bounded(self, model):
        unbounded = []
        for name, f in model.model_fields.items():
            ann = str(f.annotation)
            if "bool" in ann or "Literal" in ann:
                continue
            if ("str" in ann or "int" in ann) and not f.metadata:
                unbounded.append(name)
        assert unbounded == [], (
            f"{model.__name__} 有沒設界限的欄位: {unbounded}。"
            "加 ge/le (數值) 或 max_length (字串), 見 T2-4。"
        )


class TestGenerationLoopCounts:
    """`/api/generate` 的 slideCount / panels 直接決定跑幾次生成 = 花多少額度。"""

    def test_slide_count_bounds(self):
        from server.routes.infocards import GenerateRequest

        GenerateRequest(mode="presentation", slideCount=10)
        with pytest.raises(ValidationError):
            GenerateRequest(mode="presentation", slideCount=0)
        with pytest.raises(ValidationError):
            GenerateRequest(mode="presentation", slideCount=100_000)

    def test_panels_bounds(self):
        from server.routes.infocards import GenerateRequest

        GenerateRequest(mode="infographic", panels=4)
        with pytest.raises(ValidationError):
            GenerateRequest(mode="infographic", panels=0)
        with pytest.raises(ValidationError):
            GenerateRequest(mode="infographic", panels=9_999)

    def test_photos_max_select_matches_job_options(self):
        """同一個功能兩個入口(job option / 相簿端點), 界限不能只擋一邊。"""
        from server.routes.google_photos import GenerateRequest as PhotosRequest

        PhotosRequest(session_id="s", max_select=30)
        with pytest.raises(ValidationError):
            PhotosRequest(session_id="s", max_select=0)
        with pytest.raises(ValidationError):
            PhotosRequest(session_id="s", max_select=100_000)


class TestEndpointReturns422:
    """界限違規要在 HTTP 層變成 422, 不是 500 或默默照跑。"""

    def test_create_job_with_negative_max_files(self):
        from fastapi.testclient import TestClient

        from server.main import app

        with TestClient(app) as client:
            r = client.post("/jobs", json={
                "source_type": "repo",
                "source": {"path": "/tmp/x"},
                "options": {"max_files": -5},
            })
            assert r.status_code == 422

    def test_generate_with_absurd_slide_count(self):
        from fastapi.testclient import TestClient

        from server.main import app

        with TestClient(app) as client:
            r = client.post("/api/generate", json={
                "mode": "presentation", "text": "t", "slideCount": 100000,
            })
            assert r.status_code == 422
