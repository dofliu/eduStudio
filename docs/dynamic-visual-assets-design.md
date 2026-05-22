# dynamic-visual-assets — 動態視覺素材設計 memo

> Status: **RFC approved** (2026-05-22 用戶提議 + 同日劉老師決議 — E1/E2 都走候選 A, 跟其他 backlog 排序動)
> 對應 [CONTENT_QUALITY_ROADMAP.md](CONTENT_QUALITY_ROADMAP.md) E 軸 (E1 + E2).
> 跟 [engineering-diagram-design.md](engineering-diagram-design.md) 屬性不同:
> 那份是「材力 / 自動控制手畫圖 AI 生成」(靜態工程圖), 這份是
> 「漸進顯示動畫 + 內容感知 icon」(視覺流動感).

---

## 動機

目前影片渲染流程: PDF → JSON → 一頁靜態 PNG → ffmpeg concat. 觀眾的視覺
經驗是「每秒/每段 narration 跳一張死的圖」, 缺乏:

1. **時間軸上的視覺流動感** — 流程圖 / 架構圖該配合 narration「正在
   解釋第 X 步」逐步揭露, 不該一次秀完
2. **語意對應的視覺暗示** — 講到「疑問」配個問號 / 講到「風力機」
   配個轉動的風機 / 講到「監控」配儀表板, 強化記憶點

兩個議題互相獨立, 可分階段實作.

---

## 議題 E1: SVG 流程圖 / 架構圖漸進顯示動畫

### 候選 A: 多 PNG frame 序列 + ffmpeg concat ✨ MVP 建議

**流程**:
```
Gemini(描述) → SVG (含 step 標記) → 每個 step 渲一張 PNG (含/不含後續節點)
            → 多張 PNG 配 narration 時間軸 → ffmpeg concat → mp4 區段
```

優點:
- 完全沿用既有 pipeline (slide.image 欄位已支援單張 PNG)
- 可控性高, 每個 step 顯示時長精確對齊 narration
- 不引入新 deps (Pillow / cairosvg 已有)
- 失敗模式單純 (一張 PNG 渲不出來就 fallback 整圖)

缺點:
- 不是真正的 stroke 動畫 (是「揭露」非「畫出」)
- 步驟多時 PNG 暴增 (10 step × 1080p ≈ 5MB 暫存)

**估時**: 1-2 天 MVP (含 schema 改動 + 3 個範例)

### 候選 B: SVG stroke-dasharray CSS 動畫 → 錄屏轉 mp4

**流程**:
```
Gemini(描述) → SVG (含 animateMotion / dasharray) → headless Chrome
            → puppeteer 錄屏 → mp4 → ffmpeg 嵌入主時間軸
```

優點:
- 真 stroke-reveal 動畫 (線條從 0% 畫到 100%)
- SVG 動畫表達力最強

缺點:
- 引入 puppeteer + headless Chrome (Docker image ~200MB)
- 跨平台 (Win/WSL/Linux) headless Chrome 啟動踩過坑
- timeline 控制麻煩 (CSS animation duration ≠ narration 長度)

**估時**: 3-4 天 (含安裝 / Docker 配 / timing 對齊)

### 候選 C: 既有 slide 切片漸顯 (純 Pillow, 不用 SVG)

**流程**:
```
人工/AI 切流程圖成 N 個透明圖層 (PIL Image alpha composite)
            → 每 step 疊加一層 → 跟 A 一樣多 PNG → ffmpeg concat
```

優點:
- 完全不靠 Gemini SVG, 控制最高
- 既有 `core/render/` Pillow 流程直接接

缺點:
- 切圖要人工 (跟「AI 自動產」目標相反)
- 適合手工精美素材, 不適合自動 pipeline

**估時**: 1 天 (純框架, 內容靠人工)

### 建議

**先做 A** (MVP). B 等 Docker 已有 headless Chrome 再評估. C 留給人工精
工素材路徑 (例如 cover / outro 模板).

**schema 改動 (候選 A)**:
- `slide.image` 從 `str` 擴成 `str | list[str]` (frame 序列, 按 narration
  時間軸均分)
- 或新加 `slide.image_frames: list[dict]` 含 `path` + `display_ratio`
  (0.0~1.0 累進佔比)
- 渲染端 `core/render/slide_renderer.py` 偵測 list 就走 frame 序列模式

**測試需求**: +5~10 tests (frame 序列 dispatch / 時長配置 / fallback)

---

## 議題 E2: 內容感知 icon / motif overlay

### 素材庫設計

```
assets/icon_library/
├── manifest.json            # 對照表 (keyword → icon path + 信心)
├── generic/
│   ├── question.svg         # 問號
│   ├── exclamation.svg      # 驚嘆
│   ├── lightbulb.svg        # 想法
│   ├── gear.svg             # 流程 / 設定
│   ├── warning.svg          # 警示
│   ├── checkmark.svg        # 完成
│   └── thinking.svg         # 思考
├── domain_wind/
│   ├── wind_turbine_static.svg
│   ├── wind_turbine_rotating.gif    # 12 frame loop
│   ├── scada_dashboard.svg
│   ├── iec61400_chart.svg
│   └── nacelle_diagram.svg
├── domain_control/
│   ├── block_diagram.svg
│   ├── pid_loop.svg
│   └── transfer_function.svg
└── domain_mechanics/
    ├── free_body.svg
    ├── stress_strain.svg
    └── mohr_circle.svg
```

**manifest.json 範例**:
```json
{
  "question": {
    "keywords": ["疑問", "為什麼", "怎麼會", "提問", "?", "？"],
    "icon": "generic/question.svg",
    "position": "top-right",
    "size": 0.12
  },
  "wind_turbine": {
    "keywords": ["風力機", "風機", "風電", "葉片", "塔架"],
    "icon": "domain_wind/wind_turbine_rotating.gif",
    "position": "bottom-right",
    "size": 0.18
  }
}
```

### 候選 A: 關鍵字 grep mapping ✨ MVP 建議

**流程**:
```
narration → 對每條 manifest 跑 keyword grep → 命中 → overlay icon
         → human review 階段可調 (UI 顯示「自動建議 icon: 風機」 + 開關)
```

優點:
- 純文字 grep, 0 LLM call, 0 cost
- 結果可解釋 (「為什麼疊風機 icon? 因為 narration 含 '葉片'」)
- 容易擴充 (加新 entry 進 manifest)
- 對齊「require_review=True」硬規則 — 自動建議, 人工確認

缺點:
- 同義詞 / 上下文無法處理 (例如「風機」也可能指 PC 風扇)
- 維護成本: 每個新 domain 要手寫 keywords

**估時**: 框架 1 天 + 10 個 icon 1 天

### 候選 B: Gemini classify

**流程**:
```
narration → Gemini prompt ("這段話最相關的 icon 標籤是?") → 標籤
         → manifest 查 path → overlay
```

優點:
- 上下文敏感 (能分辨「風機 = 風力發電機」vs「風扇」)
- 不需手寫 keywords

缺點:
- 每張 slide 多一次 Gemini call (成本 + 延遲)
- 不可解釋 ("Gemini 為什麼挑這個?" 答不出)
- 跟硬規則衝突 (AI 建議該人工 review, 但 review UI 沒地方放 icon 選項)

**估時**: 1-2 天 (prompt 設計 + 整合 scriptor.py)

### 候選 C: Sentence embedding similarity

**流程**:
```
manifest 預先算每個 entry description 的 embedding
narration → embedding → cosine similarity → top-1 entry → overlay
```

優點:
- 比 A 更語意 (近義詞抓得到)
- 比 B 便宜 (本機 sentence-transformers, 0 API cost)

缺點:
- 引入新 dep (`sentence-transformers` ~500MB 模型)
- 跨語言模型對中文不一定準

**估時**: 2-3 天 (含模型評估)

### 建議

**先做 A** (MVP). 用 30~50 個 keyword entries 涵蓋常見 case, 不命中
就 fallback 不疊 icon. B / C 等 A 收集 1-2 個月實機反饋 (用戶常 reject
哪些自動建議), 看是不是語意問題再升級.

**schema 改動 (候選 A)**:
- `slide.icon_overlay: list[dict] | None` 含 `path` + `position` +
  `size_ratio` + `start_ms` + `duration_ms`
- review UI 顯示 + 可勾掉
- runner 渲染時調 `core/photo_overlay.py` 既有 PIL.alpha_composite 路徑
  (避免動 ffmpeg overlay 鏈, 跟 talking_head 共用)

**測試需求**: +8~12 tests (keyword 命中 / position 計算 / 多 icon 不衝突 /
GIF 動圖 frame 取樣)

---

## 跟既有系統的整合點

| 點 | E1 影響 | E2 影響 |
|---|---|---|
| `core/schemas.py` Slide model | `image` 擴成 list 或新加 `image_frames` | 新加 `icon_overlay: list` |
| `core/scriptor.py` | 無 (圖內容跟 narration 分開) | 加 keyword mapping 階段, narration 過完後 grep |
| `server/runner.py` | 渲染前展開 frame list | 渲染前對每張 slide 收集 icon overlay 指令 |
| `core/render/slide_renderer.py` | 改 image dispatch 偵測 list | 加 icon overlay PIL composite (alpha) |
| `core/photo_overlay.py` | 不動 | 共用 ImageOps.contain + composite, 不疊 head 時也可疊 icon |
| Review UI (web/) | proposal review 加 frame preview | 加「自動建議 icon: X」勾選列 |
| Tests | +5~10 (frame dispatch) | +8~12 (keyword + position) |

---

## 階段拆解

### Phase 1: MVP (約 3-5 天, 跟其他 backlog 排序, routine 可自主推)

**E1 frame 序列 (候選 A)**:
- [ ] **E1-1**: schema 改動 — `slide.image_frames: list[dict] | None`
  含 `path` + `display_ratio` (累進佔比 0.0~1.0) + 兼容舊 `image: str`
- [ ] **E1-2**: `core/render/slide_renderer.py` 偵測 frame list, 走多
  PNG 順序渲染, 配 narration 時長均分
- [ ] **E1-3**: Gemini SVG flow_diagram prompt 設計 (見下方「prompt 設計
  指引」) + cairosvg 渲每個 step 為 PNG
- [ ] **E1-4**: review UI 加 frame preview (proposal 階段可見 frame 數量)
- [ ] **E1-5**: +5~10 tests (test_image_frames_dispatch / test_frame_timing /
  test_legacy_single_image_fallback)

**E2 icon library + keyword grep (候選 A)**:
- [ ] **E2-1**: `assets/icon_library/` 目錄結構 + `manifest.json` 框架
- [ ] **E2-2**: 用 Gemini 一次性產 25 個扁平 SVG icon (10 generic + 15
  domain), commit 進 repo (見下方「icon 清單」)
- [ ] **E2-3**: `core/icon_picker.py` 新模組 — narration keyword grep →
  manifest 對照 → 回傳 overlay 指令
- [ ] **E2-4**: schema 加 `slide.icon_overlay: list[dict] | None` (path +
  position + size_ratio + start_ms + duration_ms)
- [ ] **E2-5**: `core/render/slide_renderer.py` PIL alpha_composite 疊 icon
  (共用 photo_overlay.py 模式, 不動 ffmpeg overlay 鏈)
- [ ] **E2-6**: review UI 顯示「自動建議 icon」列 + 勾選 / 改位置
- [ ] **E2-7**: +8~12 tests (test_icon_keyword_match / test_icon_position /
  test_multiple_icons_no_collision / test_icon_overlay_render)

### Icon 清單 (劉老師 2026-05-22 決議)

**樣式統一**: 扁平 (flat) SVG, 線條 + 純色填充, 不用 3D / 漸層 / 陰影.
viewBox 256×256, stroke-width 2~4, 主色 forest #1e3a2e + 黃 #ffd96b.

**Generic (10)** — 跨主題通用:
1. `question.svg` — 問號 (?, ？, 為什麼, 怎麼會, 提問, 疑問)
2. `exclamation.svg` — 驚嘆 (!, 注意, 重點, 強調)
3. `lightbulb.svg` — 想法 (靈感, idea, 啟發, 想到)
4. `gear.svg` — 流程 / 設定 (機制, 運作, 流程)
5. `warning.svg` — 警示 (注意, 小心, 風險, 易錯)
6. `checkmark.svg` — 完成 / 正確 (對, 正確, OK, 完成)
7. `thinking.svg` — 思考 (思考, 想一想, 推理)
8. `arrow_flow.svg` — 流向 / 步驟 (步驟, 接下來, 流程)
9. `chart_bar.svg` — 數據 (數據, 統計, 比較)
10. `network.svg` — 連結 / 系統 (系統, 網路, 串接)

**Domain 風能 (5)**:
11. `wind/wind_turbine.svg` — 風機側視 (風機, 風電, 葉片, 塔架)
12. `wind/scada_dashboard.svg` — SCADA 儀表板 (監控, SCADA, 即時)
13. `wind/iec61400.svg` — 風能標準 (IEC, 規範, 標準)
14. `wind/nacelle.svg` — 機艙剖面 (機艙, 齒輪箱, 發電機)
15. `wind/power_curve.svg` — 功率曲線 (功率, P-V, 出力)

**Domain 自動控制 (5)**:
16. `control/block_diagram.svg` — 方塊圖 (方塊圖, block, 系統圖)
17. `control/pid_loop.svg` — PID 迴路 (PID, 回授, feedback, 控制器)
18. `control/transfer_function.svg` — 轉移函數 (G(s), 轉移函數)
19. `control/step_response.svg` — 階躍響應 (step, 階躍, 暫態)
20. `control/bode_plot.svg` — 波德圖 (波德, Bode, 頻率響應)

**Domain 材料力學 (5)**:
21. `mechanics/free_body.svg` — 自由體圖 (FBD, 自由體, 受力)
22. `mechanics/stress_strain.svg` — 應力應變 (σ-ε, 應力, 應變)
23. `mechanics/mohr_circle.svg` — 莫爾圓 (Mohr, 莫爾, 主應力)
24. `mechanics/beam_load.svg` — 梁負載 (梁, 桁架, 負載)
25. `mechanics/shear_moment.svg` — 剪力彎矩 (剪力, 彎矩, V-x, M-x)

### Gemini prompt 設計指引

**SVG 來源**: 劉老師決議 — **全靠 Gemini 產**.

**Icon 一次性產生 (E2-2, 設計時)**:
```
任務: 產 25 個扁平 SVG icon, 風格統一.

每個 icon:
- viewBox: 0 0 256 256
- stroke: #1e3a2e (forest 主色), stroke-width 2~4
- fill: 主體用 #ffd96b (chalk 黃) 或留空, 不用漸層 / 陰影 / 3D
- 純線條 + 純色填充, 像 Material Icons 或 Feather Icons 那種扁平風
- 不含任何文字 / label (icon 本身要 self-explanatory)

[此處列每個 icon 的描述, 例: 11. wind_turbine = 一個三葉片風機側視
圖, 塔架直立, 葉片呈 Y 形, 不畫雲 / 不畫地面]

輸出: 25 個 .svg 檔, 用 ```svg 標籤包好, 一個 code block 一個檔.
```

人工 review 後 commit 進 `assets/icon_library/`.

**Flow diagram per-job 動態產 (E1-3, 每影片)**:
```
任務: 從流程描述產 SVG, 含 step 標記讓 frame 序列可拆.

輸入: 一段 narration 描述某 N 步驟的流程 (例「PID 控制流程: 量測誤差
→ 比例計算 → 積分累加 → 微分預測 → 加總輸出」).

要求:
- viewBox 1920×1080 (對齊影片解析度)
- 每個 step 包 <g class="step-N"> (N=1..K), 渲染端可逐個揭露
- 節點: 圓角矩形 80×40, 純色 forest, 文字白色 18pt
- 箭頭: 黑色 stroke 2, 含箭頭 marker
- 整體 layout 自動水平 / 垂直流, 不用太花俏
- 不含動畫 (CSS animation), 渲染端會切 frame

輸出: 一個 SVG + 一個 step_count 數字.
```

渲染流程: SVG → 依 step_count 切 frame (frame 1 顯示 step 1, frame 2
顯示 step 1+2, ...) → 每 frame cairosvg → PNG → 配 narration 時長均分.

### Phase 2: 完整 (約 1-2 週, Phase 1 收 1-2 月實機反饋後啟動)

- [ ] **E2-8**: 收集實機反饋 — 用戶常 reject 哪些自動建議 icon? 哪些
  常希望換位置?
- [ ] **E2-9**: 補 domain 第二批 (依用戶實際拍片頻率最高的領域)
- [ ] **E1-6**: review UI 手動調 frame 數量 (預設均分, 可改 per-frame 秒數)
- [ ] **E1-7**: SVG fallback PNG (Gemini 產 SVG 失敗時降級到單張 PNG)

### Phase 3: 進階 (條件: Phase 2 結果好, 用戶想再投入)

- [ ] **E1-5**: 候選 B (puppeteer SVG 動畫) 評估
- [ ] **E2-7**: 候選 C (embedding) 評估

### Phase 2: 完整 (約 1-2 週)

- [ ] **E1-3**: Gemini SVG 自動產 + fallback PNG
- [ ] **E1-4**: review UI frame preview + 手動調 frame 數量
- [ ] **E2-4**: 30+ icon (含 domain_wind / domain_control / domain_mechanics)
- [ ] **E2-5**: review UI 自動建議 icon 列 + 勾選
- [ ] **E2-6**: 收集實機反饋常 reject 的 case, 評估升級到 B/C

### Phase 3: 進階 (條件: Phase 2 結果好, 用戶想再投入)

- [ ] **E1-5**: 候選 B (puppeteer SVG 動畫) 評估
- [ ] **E2-7**: 候選 C (embedding) 評估

---

## 硬規則對齊

- ✅ AI 自動建議 (icon / frame slice) **不可繞過 require_review=True** —
  自動建議走 proposals 流程, 人工確認再進渲染
- ✅ 不新增 pip 必要依賴 (Phase 1 用 Pillow + cairosvg 已有; sentence-
  transformers 在 Phase 3 才評估)
- ✅ schema 兼容舊資料 (新欄位 nullable, 舊 slide 預設無 icon / 單張 image)
- ✅ 跟 v4 worker 解耦 (frame list 渲染仍是同步, 不依賴持久化)

---

## 劉老師決議 (2026-05-22)

| # | 問題 | 決議 |
|---|---|---|
| 1 | E1 走哪條候選? | **A** (PNG frame 序列 + ffmpeg concat) |
| 2 | E2 走哪條候選? | **A** (keyword grep + manifest.json) |
| 3 | Phase 1 何時動? | **跟其他 backlog 排序** (routine 在沒插隊事項時自主推) |
| 4 | icon library 內容? | **風能 / 自動控制 / 材力各 5 個**, 共 15 domain + 10 generic = **25 個扁平 SVG** |
| 5 | SVG 來源? | **全靠 Gemini 產** (icon 一次性產 commit; flow diagram per-job 動態產) |

**下一步**: routine 下輪有空可從 Phase 1 task list 挑起點. 建議順序:
1. **E2-1 → E2-2** (icon library 框架 + Gemini 一次性產 25 個 SVG, 最
   單純, 不動 schema)
2. **E2-3 → E2-4 → E2-5 → E2-7** (icon_picker 模組 + schema + renderer
   + tests, 端到端打通)
3. **E2-6** (review UI, 涉及前端較多工)
4. **E1-1 → E1-2** (frame 序列 schema + renderer, 不依賴 Gemini)
5. **E1-3** (Gemini flow diagram, 最複雜 prompt 設計)
6. **E1-4 → E1-5** (review UI + tests)
