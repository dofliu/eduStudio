"""核心渲染模組 (PR-2b-ii) — 把 deck slide / step 畫成 1920x1080 PNG。

Renderer 們各自 plug 到 pipeline.py 的 _RENDERERS dict, 由 step.bg_type 決定走哪個:
- "blackboard" -> pipeline.BlackboardRenderer (考卷 / 數學, 黑板粉筆風格)
- "slide"      -> pipeline.SlideRenderer (簡報 PDF, 用原投影片 PNG 當底圖)
- "pptx_slide" -> core.render.pptx_style.PptxStyleRenderer (repo / 文件講解, Forest 主題)

新增 renderer 應放這個 package 下, 並在 pipeline.py 的 _RENDERERS 註冊。
"""
from __future__ import annotations
