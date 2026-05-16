# B1 + B2 共用 refactor: 動態影片尺寸 (2026-05-16 草案)

> **狀態**: 草案 / 等決策
> **依賴**: 沒有
> **預估**: 2-3 天

---

## 問題

`core/config.py` 把 `VIDEO_WIDTH = 1920` / `VIDEO_HEIGHT = 1080` 寫成模組
常數. 整個 `core/render/pptx_style.py` (~2200 行) + `pipeline.py` 都把這
兩個值當編譯時常數用 — function 預設值 / class attribute / layout 算數.

B1 (縱向 9:16, 1080×1920) 和 B2 (解析度 1080p / 1440p / 4K) 兩個 feature
都依賴「runtime 切換影片尺寸」, 共用同一個 refactor.

## 架構選項

### Option A: data dict 帶尺寸

renderer 從 `data["video_width"] / data["video_height"]` 讀, fallback 全域
常數. 每個 draw helper 接受 `width / height` kwargs.

**Pros**: per-render 可切, 並發 job 不衝突
**Cons**: 幾十個 helper 都要加 kwarg, 大改動

### Option B: 渲染前 monkey-patch module constants

```python
def render(data):
    if data.get("aspect_ratio") == "9:16":
        old_w, old_h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
        config.VIDEO_WIDTH, config.VIDEO_HEIGHT = 1080, 1920
        try:
            ...
        finally:
            config.VIDEO_WIDTH, config.VIDEO_HEIGHT = old_w, old_h
```

**Pros**: 不動 helper 簽名, 立即可跑
**Cons**: 非 thread-safe, 並發 render 會搶 — 對單 process 跑可接受 (現在就是 sequential)

### Option C: per-render renderer instance

`PptxStyleRenderer(width=1080, height=1920)` 建構時帶尺寸, instance 屬性
存. 所有 draw helper 改成 method.

**Pros**: 乾淨, OO 設計
**Cons**: 從 module function 改 class method 大手術

## 推薦: **Option B (monkey-patch)** 短期 + 後續再走 A 或 C

理由:
- 1-2 天能 ship, 用戶可以實際試 9:16 / 4K
- 跟現有「sequential 單 process job」設計相容 (v4 worker 沒上就不會並發)
- v4 worker 啟動時 (未來) 自然要走 A 或 C 重新設計

風險: 若 future 並發 render (worker pool) 撞.
緩解: monkey-patch 包在 lock 內, 或 worker 改用 subprocess 隔離.

## 實作 outline (Option B)

### iter 78 (B1+B2 一起做):
1. `core/config.py`: 加 `set_video_dimensions(aspect, resolution)` 改 module attrs
2. `pipeline.py`: 把自己的 WIDTH/HEIGHT 改成 import from config
3. JobOptions: `aspect_ratio: Literal["16:9", "9:16"]` + `resolution: Literal["1080p", "1440p", "4K"]`
4. runner: render 前 `set_video_dimensions(...)` 一次, render 後 restore
5. UI: CreateJobForm 加 2 個 dropdown
6. 視覺驗 — portrait 該有的 layout 怪 (cover 字超出 / signature off-screen 等) 後續微調

### iter 79+ (portrait layout 微調):
- cover/outro 字級 / 位置依 aspect ratio 切
- signature decor 位置依 width 動態
- bullets layout 在 portrait 下行距加大 (高度更夠)
- subtitle band 高度依 video height 動態 (16:9 vs 9:16)

## 決策請求

請選:
1. 走 Option B (monkey-patch), 下輪 /advance 開始拆 iter 78
2. 走 Option A (data dict, 乾淨但慢) — 估 3-5 天
3. 走 Option C (renderer instance, 大手術) — 估 1 週
4. 暫不做 B1/B2 — 先做 C (內容品質) / D (其他)
