"""LaTeX 公式渲染 — matplotlib mathtext → 透明 PNG (新功能 backlog, 2026-06-04).

設計文件: docs/latex-formula-rendering-proposal.md (後端 A: mathtext 子集,
非完整 LaTeX — 材力公式 σ=F/A / 彎矩 / 慣性矩 / 撓度 多半是分數 / 上下標 /
希臘字母 / 根號, mathtext 涵蓋得了, 不需 TeX Live)。

接 slide 既有圖片疊放路徑 (slide.formula → PNG → renderer alpha_composite,
跟 core/icon_overlay.py 同 pattern):
- **失敗回 False 不炸 pipeline** — 壞 LaTeX / matplotlib 不可用都 graceful,
  該 slide 退無公式正常產出 (跟 icon_overlay 單筆失敗靜默 skip 同契約)。
- 透明背景 (transparent=True) — 疊在深色 slide 上不帶白底方塊。
- 用 Figure + FigureCanvasAgg 直接畫, **不碰 pyplot 全域狀態** — pipeline 走
  asyncio.to_thread 渲染, pyplot 的全域 figure registry 非 thread-safe。
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 預設值 — slide 疊放層 (renderer) 之後可覆寫
DEFAULT_DPI = 200          # 200dpi: 1080p slide 疊放夠清晰又不過大
DEFAULT_COLOR = "white"    # 深色 slide 底配白字公式
DEFAULT_FONTSIZE = 28


def render_latex_to_png(
    latex: str,
    out_path: str | Path,
    *,
    dpi: int = DEFAULT_DPI,
    color: str = DEFAULT_COLOR,
    fontsize: int = DEFAULT_FONTSIZE,
) -> bool:
    """把一段 LaTeX 數學式渲成透明 PNG。

    Args:
        latex: 數學式本體, 例 `\\sigma = \\frac{F}{A}` (不必自帶 $ 包圍,
            已帶 $...$ 也接受不重複包)。
        out_path: 輸出 PNG 路徑 (parent 目錄自動建)。
        dpi / color / fontsize: 渲染參數。

    Returns:
        True 渲染成功且檔案非空; False 任何失敗 (空字串 / 壞 LaTeX /
        matplotlib 不可用) — **不 raise**, 由 caller 決定退場 (該 slide
        退無公式)。
    """
    expr_src = (latex or "").strip()
    if not expr_src:
        return False

    # matplotlib 是 GATE-升核心的依賴 (2026-06-04 劉老師授權進 requirements + CI);
    # import 仍包 try — 萬一部署環境沒裝, graceful skip 不炸整批渲染。
    try:
        import matplotlib

        matplotlib.use("Agg")  # headless 後端, CI / Docker / 無 X server 都可跑
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
    except Exception as e:  # pragma: no cover - 部署環境缺 matplotlib 才走到
        logger.warning("matplotlib 不可用, 跳過公式渲染: %s", e)
        return False

    # 未自帶 $ 才補 — mathtext 以 $...$ 界定數學模式
    expr = expr_src if expr_src.startswith("$") and expr_src.endswith("$") else f"${expr_src}$"

    try:
        # 起一個極小 figure, 只放一段 text; bbox_inches="tight" 會把畫布裁到
        # 文字實際大小, 故 figsize 初值不重要。
        fig = Figure(figsize=(0.01, 0.01))
        FigureCanvasAgg(fig)
        fig.text(0, 0, expr, color=color, fontsize=fontsize)

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # mathtext parse error (例 `\frac{` 不完整) 在 savefig 繪製時才 raise,
        # 被下方 except 接住 → 回 False。
        fig.savefig(
            str(out_path),
            dpi=dpi,
            transparent=True,
            bbox_inches="tight",
            pad_inches=0.05,
        )
    except Exception as e:
        logger.warning("LaTeX 公式渲染失敗 (latex=%r): %s", expr_src, e)
        return False

    return out_path.exists() and out_path.stat().st_size > 0


# formula overlay 預設 — 公式比 icon 醒目, size_ratio 比 icon (0.10) 大
DEFAULT_FORMULA_POSITION = "center"
DEFAULT_FORMULA_SIZE_RATIO = 0.35


def compose_formula(
    img,
    formula,
    *,
    canvas_w: int = 1920,
    canvas_h: int = 1080,
    margin: int = 40,
) -> None:
    """把 slide.formula 渲成透明 PNG 再疊到 img 上 (in-place 修改)。

    formula 是 schema slide.formula 欄位 (deck.py 透傳):
        dict {latex: str, position?: str, size_ratio?: float, color?: str} | None。
        非 dict / 無 latex → noop (跟 core.icon_overlay.compose_icons 同容錯契約)。

    複用 compose_icons 做定位 / 縮放 / alpha paste — formula 只是「先把 LaTeX
    render 成 PNG 的一個 icon」, 故先 render_latex_to_png 到暫存檔, 再組成
    icon_overlay 形狀的 entry 交給 compose_icons。canvas_h 該由 caller 傳「字幕帶
    之上」可視高, 公式才不會壓到字幕區 (跟 icon 同規矩)。

    任何失敗 (壞 LaTeX / render 不出 / size 計算炸) 靜默 skip, 不擋影片渲染整批。
    """
    if not isinstance(formula, dict):
        return
    latex = (formula.get("latex") or "").strip()
    if not latex:
        return

    import tempfile

    from core.icon_overlay import compose_icons

    color = formula.get("color") or DEFAULT_COLOR
    try:
        # 暫存 PNG 只在 compose_icons 讀取期間存在, 疊完即清 (公式 PNG 不落 job 盤)
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "formula.png"
            if not render_latex_to_png(latex, png, color=color):
                return
            entry = {
                "path": str(png),
                "position": formula.get("position") or DEFAULT_FORMULA_POSITION,
                "size_ratio": float(
                    formula.get("size_ratio", DEFAULT_FORMULA_SIZE_RATIO)
                ),
            }
            compose_icons(
                img, [entry],
                canvas_w=canvas_w, canvas_h=canvas_h, margin=margin,
            )
    except Exception as e:
        logger.warning("formula 疊放失敗 (latex=%r): %s", latex, e)
        return
