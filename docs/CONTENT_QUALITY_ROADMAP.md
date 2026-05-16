# 內容品質 Roadmap (2026-05-16 起)

> 跟 v4 worker (架構) 並行的工作軸 — 讓影片內容更符合教學需求.
> 2026-05-16 劉老師決議: v4 worker 暫緩, 先做這條.
> 預計用 /loop /advance 自動化迭代逐項完成.

---

## A. 主題 / 排版 (進行中, 從 A1 開始)

### A1. 字級 / 行距 per-theme (claude design 04)

**問題**: TITLE=64 / BULLET=38 / line-height 16 套全 15 主題, brutalist 該超大字 / journal 該大字距 / podium 該超少字大字.

**設計**: 新 `THEME_METRICS` dispatch table, per-theme override 全域常數. 不該破壞 iter 71 各 layout 內部的精心調過的字級.

**估時**: 3-4 hr.

### A2. Margin / 對齊 per-theme (claude design 05)

**問題**: SIDE_MARGIN=100 套全 15 主題, podium / elven 該縮窄 / brutalist 該頂邊緣 / editorial 該不對稱.

**設計**: 延伸 A1 的 `THEME_METRICS` 加 margin / align tokens.

**估時**: 2-3 hr.

### A3. 自訂主題色票 UI

**功能**: UI 直接拉色票, 即時預覽, 不必改 code.

**估時**: 1-2 天.

---

## B. 影片格式 (A 完成後啟動)

### B1. 縱向短影片 (9:16) — TikTok / Shorts / Reels

**現狀**: 固定 1920×1080. 加 1080×1920 模式.

**影響範圍**: layout dispatch + slide_renderer + cover/outro 全部. cover 等的 anchor 都要重算.

**估時**: 1 天.

### B2. 解析度可選 (1080p / 1440p / 4K)

**設計**: JobOptions 加 resolution. pipeline.WIDTH/HEIGHT 改 dynamic.

**估時**: 2-3 hr.

### B3. 整段時長可選

**設計**: 加 ultra-quick (3-5 min) 或自由輸入分鐘數.

**估時**: 2-3 hr.

---

## C. 內容品質 / narration (B 後啟動)

### C1. Narration 截斷率 22% 治本

**問題**: Gemini 偶爾 narration 寫太長被字幕截.

**設計**: 改 prompt 強制 60-180 字 + 後處理長度檢查 + retry.

**估時**: 4-6 hr.

### C2. TTS 中文發音治本

**問題**: F5-TTS 中國腔 / 特定詞發音怪.

**設計**: 加 pronunciation.json mapping. 框架已有, 缺 mapping 內容.

**估時**: 跟用戶 review 樣本, 1-2 hr.

### C3. Slide narration AI 品質升級

**設計**: scriptor prompt 加教學風格指令 (「先舉例再講原理」之類).

**估時**: 依用戶想加的風格而定.

---

## D. 其他 (機會性, 看狀況啟動)

### D1. 投影片 outline AI review 介面

**問題**: outliner 大綱有時偏離主軸.

**設計**: review 大綱介面 (現在直接進 scriptor).

**估時**: 1-2 天.

### D2. 字幕風格樣式

**設計**: 字幕字級 / 字色可調 (現在 ffmpeg subtitles filter 寫死).

**估時**: 2-3 hr.

---

## 執行順序

按 A → B → C → D 順序逐項完成. 每項做完更新本檔案進度.

進度:
- [x] A1 字級 / 行距 per-theme (iter 74, commit 5101afa)
- [x] A2 Margin per-theme (iter 75, side_margin 接 title + bullets)
- [x] A3 自訂主題色票 UI (iter 76, 3 色 override: bg / primary / highlight)
- **A 全部完成 (2026-05-16). 接下來啟動 B 影片格式.**
- [ ] B1 縱向短影片
- [ ] B2 解析度可選
- [ ] B3 整段時長可選
- [ ] C1 Narration 截斷率治本
- [ ] C2 TTS 中文發音治本
- [ ] C3 narration AI 品質升級
- [ ] D1 outline AI review 介面
- [ ] D2 字幕風格樣式
