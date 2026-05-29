# V 軸 V2 / V3 提案 — GATE, 等用戶手動驅動 (2026-05-29)

> **寫於 2026-05-29**, hourly routine wind-down. V 軸 V1 (offline 補測試 +
> parser 強化) 全完成後, 剩下的 V2 / V3 都需要 routine 不該自主做的資源
> (Gemini 額度 / 新 pip dep) → 寫成提案 STOP, 等劉老師決定後手動跑。
>
> 設計母文件: [dynamic-visual-assets-design.md](dynamic-visual-assets-design.md)
> (icon 清單 / Gemini prompt 草稿在那份)。本檔只列「卡在哪、要你做什麼、
> 怎麼驗收」。

---

## 現況 (offline 已備妥的部分)

E2 / E1 的「程式骨架」routine 已全部接好, 純差「素材」與「需 API/dep 的那一步」:

| 編號 | 內容 | 狀態 |
|---|---|---|
| E2-1 | `assets/icon_library/manifest.json` (25 icon 定義: keyword/position/size) | ✅ 已 commit |
| E2-3 | `core/icon_picker.py` keyword grep → manifest 對照 | ✅ + 測試 |
| E2-4 | schema `slide.icon_overlay` | ✅ |
| E2-5 | 三大 renderer alpha_composite 疊 icon (full / split-left) | ✅ + 整合測試 |
| E2-6 | `GET /jobs/{id}/icon-suggestions` batch API | ✅ + 測試 (V1d) |
| E1-1 | schema `slide.image_frames` | ✅ |
| E1-2 | renderer 接 terminal frame fallback | ✅ (部分) |
| E1-4 | `GET /jobs/{id}/image-frames` batch API | ✅ + 測試 (V1d) |

**關鍵事實**: `manifest.json` 已定義 25 個 icon, 但 `assets/icon_library/` 內
**0 個 .svg 檔**。icon_picker 會 grep 到 manifest entry, 但 `require_file_exists=True`
(渲染端預設) 會把缺檔的全過濾掉 → 目前疊不出任何 icon。**V2 = 把這 25 個 SVG 生出來。**

---

## V2 (E2-2) — Gemini 產 25 個扁平 SVG icon

### 卡在哪
- SVG 全靠 Gemini 產 (劉老師 2026-05-22 決議)。**routine offline-first 不自主呼叫 Gemini**。
- 25 個 icon 清單 + 統一風格 prompt 草稿已在母文件 `dynamic-visual-assets-design.md`
  「Icon 清單」+「Gemini prompt 設計指引」段 (viewBox 256×256, stroke #1e3a2e,
  fill #ffd96b, 扁平無漸層, 無文字)。

### 要你做什麼
1. 開 Gemini 額度, 跑母文件的「Icon 一次性產生」prompt (一次 25 個, 或分 domain 批次)。
2. **人工 review 每個 SVG** (這步不可省 — 風格一致 / 無多餘文字 / 無版權圖樣)。
3. 把 25 個檔放進 `assets/icon_library/` 對應路徑 (generic 放根, domain 放
   `wind/` `control/` `mechanics/` 子目錄), 檔名**嚴格對齊 manifest 的 `icon` 欄位**。

### 怎麼驗收 (offline, 放好檔後 routine / CI 可自動驗)
- 寫一個 `tests/test_icon_library_complete.py`: 掃 manifest 每個 entry 的 `icon`
  路徑, assert 檔案存在 + 是合法 SVG (開頭 `<svg` + 有 `viewBox`)。
- 跑既有 `icon-suggestions` endpoint (require_file_exists=True), 確認命中的 icon
  `file_exists=True` (V1d 測試已驗 False 路徑, 補檔後 True 路徑自然通)。
- 真實 deck 跑一遍 render, 肉眼確認 icon 疊在對的位置、不擋字幕帶。

> routine 在你補完檔後可自主做「驗收測試 + manifest 完整性鎖」(offline)。
> **產 SVG 本身是 GATE。**

---

## V3 (E1-3) — flow_diagram SVG + cairosvg 渲 frame

### 卡在哪 (兩個 GATE 疊加)
1. **新 pip dep `cairosvg`** — routine 不自主加 dep。cairosvg 在 Windows 需
   GTK / libcairo runtime, 安裝不像純 Python wheel 那麼乾淨, 要你確認本機 +
   CI (ubuntu/win matrix) 都裝得起來。
2. **Gemini 每影片動態產 flow_diagram SVG** — 又是 Gemini call (offline-first 擋)。
3. 附帶 `build_clip` refactor: 目前一 step 一張靜態圖, 要改成「一 step 多 PNG
   frame 按 narration 時長均分」(母文件 E1 候選 A)。這是 production 行為改動,
   依硬規則 #3 要先跟你討論。

### 要你做什麼 (決策, 不急)
- 決定要不要走 cairosvg (vs 候選 C「純 Pillow 切片漸顯」不用新 dep — 母文件有比較)。
- 若走 cairosvg: 確認 Windows + CI 裝得起來, 同意加進 `requirements.txt`。
- 開 Gemini 額度跑 flow_diagram prompt (母文件「Flow diagram per-job 動態產」段)。

### 建議
V3 比 V2 重 (新 dep + 行為 refactor + 每影片 Gemini call)。建議**先做完 V2**
(純補素材, 風險低, 馬上看得到 icon 效果), V3 等 V2 驗收順了再評估要不要走
cairosvg 或退而用候選 C。

---

## STOP gate

- routine **不**自己跑 Gemini 產 SVG、**不**自己 `pip install cairosvg`、**不**改
  `build_clip` 行為。
- 這份提案完成 = V 軸 offline 能做的都做完了。**hourly routine 到此 wind-down**
  (見 STATUS.yaml + `ROUTINE_ADVANCE_PROMPT.md` Phase 3 段), 等劉老師:
  1. 開額度跑 V2 → 補 25 SVG → routine 可恢復做驗收測試。
  2. 或給全新方向。
