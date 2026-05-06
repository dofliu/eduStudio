# 任務:擴充為「簡報講解影片」生成器(slide-video 模式)

> **狀態 (2026-05-07)**:Phase 1, 2, 3, 5 已完成並驗證,Phase 4 (split-left) 待做。
> 詳見 ROADMAP.md v1.7 段落。

## 背景

現行系統只吃考卷 PDF → 黑板風格解題影片。要擴充成同一條 pipeline 也能吃簡報 PDF,輸出投影片講解影片。

理由是「簡報裡其實很多就是要解題的內容」,共用 TTS / SRT / 編輯 UI / 批次合成這些已經穩定的元件比較划算,不另開分支。

## 路線決定

走 **A 路線:擴充 `pipeline.py` 而非另建 `slideVideo` 子專案**。

關鍵抽象:把現行 `step` 通用化成 `scene`,scene 帶 `bg_type`(黑板 / 投影片),由不同 `Renderer` 實作畫面。其他流程(TTS、字幕、批次、Web UI)改動最小。

## 已確認的決策

| 點 | 決定 |
|---|---|
| 簡報來源格式 | **先做 PDF**,PPTX 之後走「先匯出 PDF」捷徑 |
| PDF→PNG 工具 | **PyMuPDF**(免裝 poppler,既有技術棧) |
| 顯示模式 | **A1 純講解 + A2 半疊加都做**,scene 層級切換 |
| 純簡報結構 | 允許扁平 `scenes`(無 `problems`),不硬塞「假題目」 |
| JSON 檔分開 | `exam.json` / `slides.json` 分開,未來要合併再加 `mixed` |
| 向後相容 | 舊的 `steps` 鍵繼續吃,內部統一轉 `scenes` |

## Schema 擴充

```json
{
  "source_type": "exam | slides | mixed",
  "exam_title": "...",
  "problems": [
    {
      "id": "...",
      "scenes": [
        {
          "bg_type": "blackboard",
          "display": "...",
          "narration": "..."
        },
        {
          "bg_type": "slide",
          "bg_image": "slides/<stem>/p03.png",
          "layout": "full | split-left",
          "overlay": [{"display": "...", "region": "right"}],
          "narration": "..."
        }
      ]
    }
  ],
  "scenes": []
}
```

- `problems` 跟頂層 `scenes` 二擇一(扁平簡報用後者)
- 舊欄位 `steps` 內部讀取時轉成 `scenes`(`bg_type:"blackboard"`)

## 五階段實作順序

每階段都能獨立驗證,不會「全做完才能測」。

### Phase 1 — Renderer 抽象 + scenes schema(純重構)✅ done (commit 82c1649)

- `pipeline.py` 抽出 `Renderer` 基類(介面:`render(scene, ctx) -> PIL.Image`)
- 現行 `render_frame` 包成 `BlackboardRenderer`
- 讀取層支援 `scenes` / `steps` 雙軌
- `batch.py` 依 `scene.bg_type` 派發
- **回歸測試關卡**:跑一份既有 `exam.json`,輸出 MP4 與 refactor 前比對
- 不動 Web UI、不動 TTS 層

### Phase 2 — PDF 簡報 ingestion ✅ done (commit 8fb665d, 745ba46 改進長度控制)

- 新增 `slide_ingest.py`
- PDF → PNG(PyMuPDF,渲染到 1920px 寬,約 150~200 DPI)→ 存 `slides/<stem>/p01.png` ...
- 每頁丟 Gemini Vision 看圖產 narration 初稿
- 輸出 `exams/<stem>.json`(扁平 `scenes`,`bg_type:"slide"`,`layout:"full"`)
- CLI:`python slide_ingest.py <pdf>`,加 `--mock` 模式產佔位 narration

### Phase 3 — SlideRenderer A1(純講解)✅ done (commit 8fb665d)

- 新增 `SlideRenderer`,`layout:"full"` 路徑
- 讀 `bg_image` → 置中 letterbox 1920×1080(補黑邊)
- 字幕區沿用既有渲染
- 不疊 `display`
- 驗證:跑一份簡單簡報 PDF end-to-end

### Phase 4 — SlideRenderer A2(半疊加)⏳ 待做

- `layout:"split-left"`:投影片縮到左半,右半當黑板區
- 右半渲染累積式 step,沿用 BlackboardRenderer 的累積邏輯
- 同一 scene 的 `overlay[]` 顯示在右側
- 驗證:混合「概念頁 + 解題頁」的 PDF

### Phase 5 — Web UI ✅ done (commit 796955b)

- `app.py` scene-level 編輯
- 背景類型 radio:`blackboard / slide-full / slide-split`
- 投影片縮圖預覽(讀 `bg_image`)
- 扁平 scenes 的列表 / 編輯
- 上傳路由區分:考卷 → `solve.py`,簡報 → `slide_ingest.py`(或加類型選擇)

## 第一個 session 起手式(Phase 1 具體步驟)

1. 讀 `pipeline.py:196 render_frame`,看現行怎麼吃 step
2. 把介面抽出:`Renderer.render(scene, ctx) -> PIL.Image`
3. 現有邏輯包成 `BlackboardRenderer`
4. 加 `_normalize_to_scenes(problem_dict)` helper:吃 `steps` 或 `scenes` 都吐 scene list
5. `batch.py` 依 `scene.bg_type` 派發 renderer
6. 跑 `python batch.py exams/<某份既有的>.json`,確認影片無回歸
7. 不動其他檔,Phase 1 結束

## 注意事項

- **不要動 `tts_backend.py` / `pronunciation.json` / `tts_config.json`**:TTS 層在 v1.5 已穩定
- **scene 名稱統一,narration 仍是核心**:渲染什麼之外,TTS 都吃 narration
- **PDF→PNG 解析度**:PyMuPDF 預設 72 DPI 太低,目標 1920px 寬
- **字型 fallback 不變**:`pipeline.py` 既有的 main / fallback font 在 SlideRenderer 也用得到(A2 模式疊文字時)
- **檔名安全**:`slides/<stem>/...` 走跟 `videos/<stem>/...` 一樣的 sanitize

## 不做的事(明確排除)

- v1.5 候選的 Mathpix / 單步驟重生成 / 燒字幕 / 工程圖 AI / YouTube 發布 — 各自獨立路線
- PPTX 直接讀(LibreOffice headless / python-pptx)— 等 PDF 路徑穩了再說
- 投影片內既有文字 OCR 化變 step 內容 — Phase 4 後再評估

## 相關檔案速查

| 檔案 | Phase | 改動類型 |
|---|---|---|
| `pipeline.py` | 1, 3, 4 | 重構 + 新 Renderer |
| `batch.py` | 1 | 派發邏輯 |
| `solve.py` | 1 | 輸出格式對齊 scenes |
| `slide_ingest.py` | 2 | 新增 |
| `app.py` | 5 | 新編輯介面 |
| `tts_backend.py` 等 TTS 層 | — | 不動 |
