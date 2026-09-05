"""core/comic_assets.py — 漫畫角色素材處理: 設定稿三視圖 → 去背 cutout。

用途
----
AI 生的角色設定稿 (character sheet) 通常是「同一角色三個視角排一列 + 單色背景 + 腳下淡陰影」。
這個模組把它拆成三張去背 RGBA PNG (front / side / three_quarter), 之後可以:
- 直接疊到場景背景上 (動態漫畫的角色圖層; 不用每頁重新生圖也能維持角色一致)
- 當 Series Bible 的 character_anchor 參考圖 (乾淨無底的角色圖對 Gemini 生圖更穩)
- 當旁白形象 (片頭 / 片尾卡與字幕條頭像, 見 core.comic_video)

只依賴 Pillow (專案既有), 不需要 numpy / scipy。
演算法: 取四角中位色當背景 → 每像素與背景的 Chebyshev 色差 → 門檻成候選 mask →
只保留「從影像邊界連通」的候選區 (flood fill), 衣服上與背景同色的區塊不會被挖掉 →
腳下陰影 (比背景暗、色相相近, 只在底部帶) 一併去掉 → 依 alpha 欄投影切成多個視角。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

VIEW_LABELS = ("front", "side", "three_quarter")


def _background_color(im: Image.Image, margin: int = 20) -> tuple[int, int, int]:
    w, h = im.size
    samples: list[tuple[int, int, int]] = []
    for box in ((0, 0, margin, margin), (w - margin, 0, w, margin), (0, h - margin, margin, h), (w - margin, h - margin, w, h)):
        samples.extend(im.crop(box).getdata())
    return tuple(sorted(c[i] for c in samples)[len(samples) // 2] for i in range(3))  # type: ignore[return-value]


def _chebyshev_distance(im: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """每像素與 color 的最大通道差 (L 影像)。"""
    solid = Image.new("RGB", im.size, color)
    r, g, b = ImageChops.difference(im, solid).split()
    return ImageChops.lighter(ImageChops.lighter(r, g), b)


def _shadow_mask(im: Image.Image, bg: tuple[int, int, int], *, band_from: float, max_darker: int, max_chroma: int) -> Image.Image:
    """底部帶內「比背景暗、且各通道一致地暗」的像素 = 地板陰影。"""
    w, h = im.size
    solid = Image.new("RGB", im.size, bg)
    darker = ImageChops.subtract(solid, im)          # bg - pixel, 負值截 0 → 只留變暗的量
    dr, dg, db = darker.split()
    amount = ImageChops.lighter(ImageChops.lighter(dr, dg), db)
    # 三通道變暗量差異小 → 色相相近 (陰影); 差異大 → 有顏色的東西 (衣服)
    spread = ImageChops.lighter(
        ImageChops.lighter(ImageChops.difference(dr, dg), ImageChops.difference(dg, db)),
        ImageChops.difference(dr, db),
    )
    is_dark = amount.point(lambda v: 255 if 6 < v <= max_darker else 0)
    is_gray = spread.point(lambda v: 255 if v <= max_chroma else 0)
    mask = ImageChops.multiply(is_dark, is_gray)
    band = Image.new("L", im.size, 0)
    ImageDraw.Draw(band).rectangle([0, int(h * band_from), w, h], fill=255)
    return ImageChops.multiply(mask, band)


def remove_flat_background(
    im: Image.Image,
    *,
    tolerance: int = 30,
    shadow_band_from: float = 0.86,
    shadow_max_darker: int = 75,
    shadow_max_chroma: int = 22,
    feather: float = 0.8,
) -> Image.Image:
    """單色背景 (含腳下淡陰影) → RGBA。只移除從邊界連通的背景, 保留人物內部同色區。"""
    rgb = im.convert("RGB")
    w, h = rgb.size
    bg = _background_color(rgb)
    candidate = _chebyshev_distance(rgb, bg).point(lambda v: 255 if v < tolerance else 0)
    candidate = ImageChops.lighter(
        candidate,
        _shadow_mask(rgb, bg, band_from=shadow_band_from, max_darker=shadow_max_darker, max_chroma=shadow_max_chroma),
    )
    # flood fill: 從邊界每隔幾格下種子, 把連通的候選區填成 128
    fill = candidate.copy()
    step = max(4, min(w, h) // 64)
    seeds = [(x, 0) for x in range(0, w, step)] + [(x, h - 1) for x in range(0, w, step)] + \
            [(0, y) for y in range(0, h, step)] + [(w - 1, y) for y in range(0, h, step)]
    for seed in seeds:
        if fill.getpixel(seed) == 255:
            ImageDraw.floodfill(fill, seed, 128)
    alpha = fill.point(lambda v: 0 if v == 128 else 255)
    if feather > 0:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    out = rgb.copy().convert("RGBA")
    out.putalpha(alpha)
    return out


def split_views(rgba: Image.Image, *, min_width_ratio: float = 0.08, pad: int = 6, alpha_threshold: int = 40) -> list[Image.Image]:
    """依 alpha 欄投影的空白間隔, 把一列多個視角切成多張 (各自裁到緊貼邊界)。"""
    w, h = rgba.size
    alpha = rgba.split()[-1].point(lambda v: 255 if v > alpha_threshold else 0)
    # 欄投影: 把 alpha 壓成 1 像素高
    col = alpha.resize((w, 1), Image.BOX)
    cols = [col.getpixel((x, 0)) > 0 for x in range(w)]
    segs: list[tuple[int, int]] = []
    start: int | None = None
    for x, on in enumerate(cols + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start >= w * min_width_ratio:
                segs.append((start, x))
            start = None
    views: list[Image.Image] = []
    for x0, x1 in segs:
        sub = rgba.crop((max(0, x0 - pad), 0, min(w, x1 + pad), h))
        bbox = sub.split()[-1].point(lambda v: 255 if v > alpha_threshold else 0).getbbox()
        if bbox:
            sub = sub.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(sub.width, bbox[2] + pad), min(sub.height, bbox[3] + pad)))
        views.append(sub)
    return views


def cutout_character_sheet(src: str | Path, out_dir: str | Path, name: str | None = None, **kwargs) -> list[Path]:
    """設定稿 → out_dir/<name>_<view>.png (front / side / three_quarter; 視角數不為 3 時用 v0, v1, ...)。"""
    src = Path(src)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = name or src.stem
    rgba = remove_flat_background(Image.open(src), **kwargs)
    views = split_views(rgba)
    labels = list(VIEW_LABELS) if len(views) == 3 else [f"v{i}" for i in range(len(views))]
    paths: list[Path] = []
    for view, label in zip(views, labels):
        p = out_dir / f"{name}_{label}.png"
        view.save(p)
        paths.append(p)
    return paths
