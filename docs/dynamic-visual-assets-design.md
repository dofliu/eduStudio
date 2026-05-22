# dynamic-visual-assets — 動態視覺素材設計 memo

> Status: **RFC draft** (2026-05-22 用戶提議, 等劉老師決議走哪條候選)
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

### Phase 1: MVP (約 3-5 天, 跟劉老師 confirm 後再動)

- [ ] **E1-1**: schema + slide_renderer frame list 支援
- [ ] **E1-2**: scriptor / outliner 產生 SVG (或先用人工模板) + cairosvg 渲 frame
- [ ] **E2-1**: `assets/icon_library/` 結構 + manifest.json 框架
- [ ] **E2-2**: 10 個 generic icon (question / wind_turbine / dashboard /
  warning / lightbulb / gear / checkmark / arrow / chart / network)
- [ ] **E2-3**: keyword grep mapping + slide_renderer icon overlay

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

## 等劉老師決議

1. **E1 走哪條候選?** A (PNG frame 序列, MVP) / B (puppeteer) / C (人工切片) / 還沒決定
2. **E2 走哪條候選?** A (keyword grep, MVP) / B (Gemini classify) / C (embedding) / 還沒決定
3. **Phase 1 何時動?** 等 v4 worker / 跟其他 backlog 排序 / 直接優先
4. **icon library 內容?** 劉老師專業 (風能 / 自動控制 / 材力) 各要幾個?
   有特定樣式偏好嗎 (扁平 / 線條 / 等距視角)?
5. **SVG 來源?** 全靠 Gemini 產 / 部分手工模板 / 用既有 mermaid 模板庫?

收到回饋後 routine 可開始接 Phase 1.
