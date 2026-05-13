"""core/photo_overlay.py — iter 35 從 pipeline.py 拆出的 overlay_teacher_photo。

純 Pillow 操作 + config dict driven, 不必跑 ffmpeg / Gemini 也能完整測。
"""
from __future__ import annotations

import pytest

# Pillow 是 server-side + pipeline 必裝, 沒裝就 skip 不擋 CI
pytest.importorskip("PIL", reason="需要 Pillow")

from PIL import Image


@pytest.fixture
def blank_canvas():
    """1920×1080 純白底, 模擬 BlackboardRenderer / SlideRenderer 產出的 frame."""
    return Image.new("RGB", (1920, 1080), (255, 255, 255))


@pytest.fixture
def real_photo(tmp_path):
    """產一張小頭像 PNG 給 overlay 用 (不依賴外部資源)."""
    p = tmp_path / "teacher.png"
    Image.new("RGB", (100, 100), (0, 200, 0)).save(p)
    return p


class TestOverlayBehavior:
    """overlay_teacher_photo 行為測試 — config 驅動."""

    def test_no_config_returns_silently(self, blank_canvas):
        from core.photo_overlay import overlay_teacher_photo

        # 空 config: teacher_photo / dynamic_avatar 都沒設, 應 noop
        overlay_teacher_photo(blank_canvas, config={})
        # 不該炸, 也不該改動 img (純白底)
        assert blank_canvas.getpixel((1800, 1000)) == (255, 255, 255)

    def test_disabled_teacher_photo_noop(self, blank_canvas):
        from core.photo_overlay import overlay_teacher_photo

        cfg = {"teacher_photo": {"enabled": False, "path": "x.png"}}
        overlay_teacher_photo(blank_canvas, config=cfg)
        assert blank_canvas.getpixel((1800, 1000)) == (255, 255, 255)

    def test_dynamic_avatar_disables_static(self, blank_canvas, real_photo):
        from core.photo_overlay import overlay_teacher_photo

        # dynamic_avatar.enabled=True 應該擋住靜態 overlay (兩模式互斥)
        cfg = {
            "dynamic_avatar": {"enabled": True},
            "teacher_photo": {
                "enabled": True,
                "path": str(real_photo),
                "size": 100,
                "margin": 20,
                "shape": "rect",
                "border_width": 0,
            },
        }
        overlay_teacher_photo(blank_canvas, config=cfg)
        # 沒貼圖 → 純白底
        assert blank_canvas.getpixel((1800, 1000)) == (255, 255, 255)

    def test_missing_file_noop(self, blank_canvas):
        from core.photo_overlay import overlay_teacher_photo

        cfg = {"teacher_photo": {"enabled": True, "path": "/does/not/exist.png"}}
        overlay_teacher_photo(blank_canvas, config=cfg)
        assert blank_canvas.getpixel((1800, 1000)) == (255, 255, 255)

    def test_happy_path_pastes_photo(self, blank_canvas, real_photo):
        """正常路徑: 圖實際被貼到右下角."""
        from core.photo_overlay import overlay_teacher_photo

        cfg = {
            "teacher_photo": {
                "enabled": True,
                "path": str(real_photo),
                "size": 100,
                "margin": 20,
                "shape": "rect",   # 方形免 anti-alias 模糊邊界
                "border_width": 0,
            },
        }
        overlay_teacher_photo(blank_canvas, config=cfg)
        # 1920 - 100 - 20 = 1800 (px), 1080 - 100 - 20 = 960 (py)
        # 中央點 (1850, 1010) 應該是綠色 (0, 200, 0)
        center_pixel = blank_canvas.getpixel((1850, 1010))
        assert center_pixel != (255, 255, 255), "圖沒貼上"
        # 應該偏綠
        assert center_pixel[1] > center_pixel[0]
        assert center_pixel[1] > center_pixel[2]

    def test_circle_shape_corners_transparent(self, blank_canvas, real_photo):
        """圓形 shape — 圓外的角落該維持白底."""
        from core.photo_overlay import overlay_teacher_photo

        cfg = {
            "teacher_photo": {
                "enabled": True,
                "path": str(real_photo),
                "size": 100,
                "margin": 20,
                "shape": "circle",
                "border_width": 0,
            },
        }
        overlay_teacher_photo(blank_canvas, config=cfg)
        # 圓外角落 (1800, 960) 應該還是白
        assert blank_canvas.getpixel((1800, 960)) == (255, 255, 255)
        # 圓內中央應該是綠色
        assert blank_canvas.getpixel((1850, 1010)) != (255, 255, 255)

    def test_border_color_custom(self, blank_canvas, real_photo):
        """border_color 參數可由 caller 指定 (decouple from CHALK_WHITE 預設)."""
        from core.photo_overlay import overlay_teacher_photo

        cfg = {
            "teacher_photo": {
                "enabled": True,
                "path": str(real_photo),
                "size": 100,
                "margin": 20,
                "shape": "rect",
                "border_width": 5,
            },
        }
        # 明顯不一樣的紅色邊框
        overlay_teacher_photo(
            blank_canvas, config=cfg, border_color=(255, 0, 0),
        )
        # 邊框附近 (px=1800-bw, py=960-bw) 應該有紅
        # 取右上邊框中段 (1850, 957) 該是紅色
        edge_pixel = blank_canvas.getpixel((1850, 957))
        # 不該是白, 應該偏紅
        assert edge_pixel[0] > edge_pixel[1] and edge_pixel[0] > edge_pixel[2]

    def test_pipeline_thin_wrapper_works(self, blank_canvas, real_photo, monkeypatch):
        """確認 pipeline._overlay_teacher_photo wrapper 仍工作 (backward compat)."""
        pipeline = pytest.importorskip("pipeline")

        # 把 _get_pipeline_config monkeypatch 回真實 cfg
        cfg = {
            "teacher_photo": {
                "enabled": True,
                "path": str(real_photo),
                "size": 100,
                "margin": 20,
                "shape": "rect",
                "border_width": 0,
            },
        }
        monkeypatch.setattr(pipeline, "_get_pipeline_config", lambda: cfg)

        pipeline._overlay_teacher_photo(blank_canvas)
        # 圖實際貼上
        center_pixel = blank_canvas.getpixel((1850, 1010))
        assert center_pixel != (255, 255, 255)
