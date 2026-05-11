"""影片畫面 layout 常數 — 跨 renderer 共用的 magic number 集中地。

跟 `core/config.py` 的分工:
- `config.py`:路徑、env var、model 名稱、影片總尺寸 (`VIDEO_WIDTH/HEIGHT/FPS`)
- `visuals.py`:renderer 共用的版面切分、配色 (`SUBTITLE_BAND_HEIGHT` 等)

為什麼分開:`config.py` 是 FastAPI eager import 的,不該扛任何渲染相關設計
假設;`visuals.py` 只放純數字 / tuple,給 `pipeline.py` 與 `core.render.*`
等渲染 module 用。

Round 2 lessons-learned #3 (commit 07c4a45) 的洞:letterbox-fit 必須扣 overlay
區才算可視區。先前 `SUBTITLE_BAND=180` 在 `pipeline.py` (兩處) / `pptx_style.py`
散一份,`_render_full` 漏改就把 slide 底部 16.7% 切掉。集中之後改一處全動。
"""
from __future__ import annotations

from core.config import VIDEO_HEIGHT, VIDEO_WIDTH

__all__ = [
    "SUBTITLE_BAND_HEIGHT",
    "CONTENT_BOTTOM",
    "SUBTITLE_STRIP_COLOR",
    "VIDEO_HEIGHT",
    "VIDEO_WIDTH",
]


# 底部字幕黑帶高度 — 三個 renderer (BlackboardRenderer / SlideRenderer /
# PptxStyleRenderer) 全部依賴這個值;外掛 SRT 顯示區與燒字幕 force_style
# 都跟此數對齊。改它前先確認字級夠塞。
SUBTITLE_BAND_HEIGHT = 180

# 可視內容區底部 y 座標 (= 字幕帶上緣)。
# letterbox-fit / step grid / pptx CONTENT_BOTTOM 都用這個,不要直接寫 900。
CONTENT_BOTTOM = VIDEO_HEIGHT - SUBTITLE_BAND_HEIGHT  # 900

# 字幕黑帶填色 (純黑) — 跟 banner / palette 配色無關,單純就是字幕區背景。
SUBTITLE_STRIP_COLOR: tuple[int, int, int] = (0, 0, 0)
