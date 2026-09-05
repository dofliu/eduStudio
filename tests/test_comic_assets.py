"""core.comic_assets — 角色設定稿去背 + 切視角 (純 Pillow)。"""
from __future__ import annotations

from PIL import Image, ImageDraw

from core.comic_assets import cutout_character_sheet, remove_flat_background, split_views

BG = (133, 142, 159)


def _sheet(w: int = 600, h: int = 300) -> Image.Image:
    """三個「人」(不同顏色的長方形 + 頭圓) 排一列, 中間那個衣服跟背景同色, 腳下有淡陰影。"""
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    for i, body in enumerate(((220, 120, 60), BG, (60, 90, 160))):
        cx = 100 + i * 200
        d.ellipse([cx - 40, h - 30, cx + 40, h - 14], fill=(105, 112, 126))      # 地板陰影 (同色相較暗)
        d.rectangle([cx - 30, 90, cx + 30, h - 26], fill=body, outline=(30, 30, 40), width=4)  # 身體 (含輪廓線)
        d.ellipse([cx - 22, 40, cx + 22, 84], fill=(240, 200, 170))              # 頭
    return im


def test_remove_flat_background_keeps_same_colour_clothes_and_drops_shadow():
    rgba = remove_flat_background(_sheet())
    a = rgba.split()[-1]
    assert a.getpixel((5, 5)) == 0 and a.getpixel((595, 295)) == 0          # 背景透明
    assert a.getpixel((300, 180)) == 255                                    # 中間人的同色衣服保留 (被輪廓線包住)
    assert a.getpixel((100, 180)) == 255 and a.getpixel((500, 60)) == 255   # 身體 / 頭
    assert a.getpixel((100, 285)) < 40                                      # 腳下陰影去掉


def test_split_views_returns_three_tight_crops():
    views = split_views(remove_flat_background(_sheet()))
    assert len(views) == 3
    for v in views:
        assert 60 <= v.width <= 110 and v.height >= 220
        assert v.split()[-1].getpixel((v.width // 2, v.height // 2)) == 255


def test_cutout_character_sheet_writes_labelled_files(tmp_path):
    src = tmp_path / "阿光.png"
    _sheet().save(src)
    outs = cutout_character_sheet(src, tmp_path / "out")
    assert [p.name for p in outs] == ["阿光_front.png", "阿光_side.png", "阿光_three_quarter.png"]
    assert all(Image.open(p).mode == "RGBA" for p in outs)
