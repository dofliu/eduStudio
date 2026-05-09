# ROADMAP

方向性規劃:版本演進、功能路線圖。短期可立刻做的小事在 [TODO.md](TODO.md),不重複寫。

---

## 產品定位

**「教學影片自動生成平台」**:三種輸入,一條 pipeline,終點是 YouTube。

| 輸入 | 對應 source_type | 渲染風格 |
|---|---|---|
| 考題 PDF | `exam_pdf` | 黑板逐題解答 |
| 教學簡報 PDF | `slides_pdf` | 投影片原圖 + 逐頁旁白 |
| Blog / 文件 / 程式碼 repo | `document` / `url` / `repo` | Forest pptx 主題 (AI 產簡報內容) |

---

## v0 — POC(已完成)

沙箱 (Anthropic Ubuntu 24) 裡跑 pipeline。

- [x] `pipeline.py` JSON → MP4 (H.264) + SRT
- [x] 黑板風格渲染:深綠底、粉筆色階、累積顯示、最新步驟黃字
- [x] Edge-TTS 雲端中文語音(沙箱 fallback espeak-ng)
- [x] FFmpeg 音訊正規化(loudnorm + apad 結尾停頓)

---

## v1 — 本機完整產品(已完成)

### 1.0 — Web UI + 批次流程
- [x] `solve.py` PDF → exam.json(從 Claude → 換 Gemini Vision)
- [x] `app.py` Flask Web UI 列題 / 逐段編輯 / 觸發渲染
- [x] `batch.py` 整份考卷批次渲染

### 1.1 — 多平台相容
- [x] 沙箱 Linux 路徑硬編碼清乾淨(`pathlib.Path(__file__).parent`)
- [x] 字型路徑走環境變數
- [x] Windows / macOS / Linux 通用

### 1.2 — 教學內容深度
- [x] SYSTEM_PROMPT 大改:每題 20~30 step、`_section` 結構、易錯提醒
- [x] few-shot 範例鎖密度(21-step 二階系統題)
- [x] MAX_TOKENS 拉到 32768

### 1.3 — 視覺品質
- [x] 字型 fallback:`msjh.ttc` 缺的 `≤`/`≥` 走 `seguisym.ttf`
- [x] 題目自動換行,字級動態縮放
- [x] 標題小化、底部預留 220px 字幕區
- [x] 步驟累積超過可視區自動滾動

### 1.4 — 語音品質
- [x] `pronunciation.json` 符號對照表(希臘字母、次方、分式、三角函數、拉氏)
- [x] `normalize_for_tts` 替換時前後補空白(解 `ζωn` 黏字)
- [x] 分式 `1/(s+3)` → `s+3 分之 1` 自動改寫
- [x] SRT 按 `。！？` 切句

### 1.5 — 設定可切換
- [x] `tts_backend.py` TTS 抽象層,edge / f5 / fallback
- [x] `tts_config.json` backend / 聲音 / 速度 / F5 ref
- [x] `pipeline_config.json` 老師頭像 overlay
- [x] Web UI 聲音下拉 + 即時試聽
- [x] F5-TTS 選用(本機聲音複製,首次下載 ~1 GB)

### 1.6 — 多考卷管理
- [x] 影片 per-exam subfolder(`videos/<exam_stem>/qN.mp4`)
- [x] `/library` 跨考卷瀏覽 + 路徑穿越防禦
- [x] `/exams` 列表 + `/upload` PDF + `/switch/<stem>`
- [x] 啟動時自動遷移 repo root 散落的 exam JSON 到 `exams/`
- [x] 中文檔名支援(sanitize 防注入)

---

## v1.7 — 簡報講解影片擴充(2026-05 Phase 1/2/3/5 完成)

把同一條 pipeline 擴展到吃簡報 PDF。詳見 [plan_slidevideo.md](plan_slidevideo.md)(規劃文件,主要事項已完成)。

### 1.7.0 — Phase 1 Renderer 抽象
- [x] `pipeline.py` 抽 `Renderer` 基類,`BlackboardRenderer` 包現有邏輯
- [x] `_RENDERERS` registry + dispatcher,依 `step.bg_type` 派發

### 1.7.1 — Phase 2 PDF 簡報 ingestion
- [x] `slide_ingest.py` PDF → 1920px 寬 PNG → `slides/<stem>/`
- [x] Gemini 章節切分 + 逐頁 narration 生成
- [x] CLI:`--mock` / `--single` / `--force`

### 1.7.2 — Phase 3 SlideRenderer A1 純講解
- [x] 投影片 letterbox-fit 到 1920×1080
- [x] 底部 180px 黑帶與 BlackboardRenderer 對齊

### 1.7.3 — Phase 5 Web UI 整合
- [x] `/upload` 加類型 radio(考卷 / 簡報)派發
- [x] 編輯頁顯示投影片縮圖
- [x] Library YouTube 欄位 + 上傳審查頁

### 1.7.4 — narration 長度收斂
- [x] 詳盡 prompt 200~250 字,目標每章 ~15 分鐘
- [x] 3 段式 retry + post-process truncate 兜底
- [x] 實測 37 頁簡報 → 4 章 13~19 分鐘均勻分布

### 1.7.5 — Phase 4 split-left layout(待做,降到 v3.x 加分)
- [ ] `SlideRenderer` 加 `layout="split-left"`(投影片左 + 累積式 step 右)
- [ ] 用途:解題型投影片並陳

---

## v2.0 — YouTube 上傳通道(2026-05 完成)

詳見 [plan_youtube_agent.md](plan_youtube_agent.md)。

### publish.py CLI
- [x] OAuth 2.0 flow,token 存 `youtube_token.json`
- [x] `client_secret*.json` 自動 glob
- [x] Resumable upload + 進度顯示
- [x] SRT 同檔名自動偵測,`captions.insert` zh-TW
- [x] `--out-json` 結構化輸出

### Web UI 整合(Track A)
- [x] Library 影片旁 📺 → `/upload_review/<stem>/<pid>`
- [x] 嵌入 video player + 預填 metadata + 隱私 radio
- [x] 上傳結果寫回 exam.json `youtube` 欄位
- [x] Library badge / `/youtube_status` 輪詢

> **遺留問題:** YouTube 上傳通道目前只在 Track A 有。Track B (FastAPI / React) 尚未接,跑完 job 只到 `done`,要手動 publish。**v3.1 第一個 PR 處理。**

---

## v3.0 — 平台化基礎(2026-05 完成)

從「考卷檢討單一工具」升級成「多來源教學影片平台」。後端架構整理 + 三種新 source。

### 3.0a — `core/` 公開 API 包(PR-1, commit 0bbe2a3)
- [x] `core/__init__.py` lazy re-export 介面層
- [x] `core/config.py` 集中所有 path / env / 模型常數 / 字型
- [x] `core/runtime.py` `setup_utf8_stdout()` (Windows cp950 修正)
- [x] `core/text_utils.py` `strip_latex` / `clean_json_escapes`
- [x] 既有 CLI(`python pipeline.py` / `python solve.py` ...)行為完全沒變

### 3.0b — FastAPI server + JobStore(PR-2a, commit 0e26684)
- [x] `server/main.py` FastAPI app factory + uvicorn CLI
- [x] `server/jobs.py` JobStore(memory + JSON 檔案持久化, 重啟保留)
- [x] `server/runner.py` 背景 task dispatch + asyncio
- [x] `server/routes/jobs.py` REST API(/jobs CRUD + /draft + /approve + /artifacts)
- [x] Job 狀態機:`pending → ingesting → awaiting_review → rendering → done`

### 3.0c — repo 來源 + Forest 主題(PR-2b-i / PR-2b-ii)
- [x] `core/adapters/repo.py` 資料夾掃描 + priority + ≤50 檔
- [x] `core/outliner.py` raw_content → outline.json(repo prompt)
- [x] `core/scriptor.py` 逐 section Gemini → deck.json,code_snippet 強制取自真實檔
- [x] `core/render/pptx_style.py` Forest 主題 Pillow 純畫(無 LibreOffice)
- [x] `deck_to_exam_schema_pptx` 壓平讓 pipeline 吃

### 3.0d — document / url 來源(PR-3b, commit 5f41d53)
- [x] `core/adapters/document.py` PDF / MD / TXT 單檔(80K 字 truncate)
- [x] `core/adapters/url.py` BS4 啟發式抽 `<article>` / `<main>`
- [x] `outline_long_form` + `script_long_form` 共用 prompt template

### 3.0e — 排程 CLI(PR-3c, commit 137edc6)
- [x] `scripts/submit_job.py` `python scripts/submit_job.py {repo|document|url|exam} <source>`
- [x] 結構化 JSON 輸出供排程 log 抓 job_id
- [x] README 加 Windows 工作排程器使用小節

### 3.0f — Vanilla 編輯器(PR-3d, commit 93a5040)
- [x] `server/routes/editor.py` server-side HTML + vanilla JS(無 build / CDN)
- [x] 新 deck schema 編輯,build 不存在時 fallback

### 3.0g — React 18 + Vite + Tailwind UI(PR-3e, commit e51b7ef)
- [x] `web/` React 專案,build 在 `web/dist/`
- [x] JobsIndex(列表 + 5 秒 auto-poll + filter + 新增表單)
- [x] JobEditor(逐 section/slide 編輯, narration 字數提示)
- [x] Forest 色票對齊 PptxStyleRenderer
- [x] FastAPI 自動 mount `/ui/*`,SPA fallback,deep link OK

---

## v3.1 — 平台合一(進行中,主任務)

**目標:把 Track A 的功能搬到 Track B,只留一個入口。**

詳細 PR 順序:

### PR-3f — Track B 接 YouTube 上傳 🔴
- [ ] `server/routes/youtube.py`(或併入 jobs.py):`POST /jobs/{id}/publish` + `GET/PUT /jobs/{id}/youtube_meta`
- [ ] `web/src/pages/PublishReview.tsx`:嵌 video player + 預填 metadata + 隱私 radio + 一鍵上傳
- [ ] reuse `core.upload_video` / `core.upload_caption` / `core.get_youtube_credentials`
- [ ] 上傳結果寫回 `state.json`(新增 `youtube` 欄位)+ JobsIndex 顯示 badge

### PR-3g — 考卷 v1 schema 接 React UI 🔴
- [ ] `web/src/pages/ExamEditor.tsx`:認出 `problems / steps` schema,Track A 那種逐題逐 step 編輯介面
- [ ] JobEditor 依 schema 自動分流(deck schema → SlideEditor / exam schema → ExamEditor)
- [ ] `app.py` 的 `/edit` 路由全功能對應(包含 single step 重生成、步驟補圖)

### PR-3h — slides_pdf 升 deck schema 🔴
- [ ] `slide_ingest.py` 輸出新 deck schema(每頁 section.slide,bg_image 欄位)
- [ ] React `SlideEditor` 加 bg_image 縮圖預覽
- [ ] `core.deck.deck_to_exam_schema_slides` 渲染前壓平,沿用 `SlideRenderer`
- [ ] 既有 v1 schema slides_pdf JSON 加 migration helper(讀舊 → 自動轉新)

### PR-3i — Track A redirect / 棄用 🟡
- [ ] `app.py` 啟動加大字旗標「⚠ Track A 即將退場,請改用 :8000」
- [ ] 新功能不再進 Track A,僅維護現有業務
- [ ] 根路徑(`/`)redirect 到 `:8000`(可由 env var 關閉,過渡期保留)
- [ ] README 主推改成 Track B,Track A 移到「legacy 段落」

---

## v3.2 — 基礎建設(進行中,平行於 v3.1)

### PR-4a — 單 section / 單 slide 重渲染 🟡
- [ ] `POST /jobs/{id}/sections/{sid}/render` 端點(不重跑整個 deck)
- [ ] React UI SlideEditor / ExamEditor 加「只渲染本章」按鈕
- [ ] `runner.py` 階段管理改成可恢復式(目前是線性 ingest → render)
- [ ] artifacts 增量更新而非全部覆蓋

### PR-4b — pytest 基底 + CI 雛型 🟡
- [ ] `tests/` 結構,先補純函式:`text_utils` / `deck` / `adapters/repo` / `jobs.py` JobStore
- [ ] GitHub Actions:Python 3.10/3.12 + Windows/Ubuntu matrix
- [ ] 不打 LLM 的 mock fixture(rerun outline / scriptor 對 stable golden)

### PR-4c — Structured logging 🟡
- [ ] 換 `logging` module + JSON formatter
- [ ] 每 job 一個 log file:`jobs/<id>/log.jsonl`
- [ ] React UI 加 logs panel(tail 最近 200 行)
- [ ] failed job 一鍵 retry(目前要刪掉重跑)

---

## v3.3 — 體驗加分(順位較後)

### Navy pptx 主題
- 對應個人偏好(Forest 教學類 / Navy 科技類)
- `PptxStyleRenderer` 加 theme 參數,React UI 主題下拉
- 範圍小,單 PR 解決

### F5 中文預切句(TODO.md 🔴 治本)
- F5 內部 batch 不顧中文詞邊界,「處理與應用」被切成「處」+「理與應用」
- 在 F5TTS class 用標點先切短段,逐段 infer 後 concat
- 預期能根除大部分中-中切錯;不解中-英切換口音漂移

### Phase 4 split-left layout
- `SlideRenderer` 加 `layout="split-left"`,投影片左 + 右半累積式 step
- 解題型投影片需要

### 燒字幕選項
- `ffmpeg -vf subtitles=...` 一個 filter
- Web UI 加 checkbox「要輸出硬字幕版本」
- 優先度低,YouTube 上 SRT 也行

### 工程圖 AI 輔助
- 自由體圖、彎矩圖、方塊圖、電路圖
- Gemini 產 matplotlib / TikZ code,本地執行畫圖
- 步驟 `image` 欄位動態切圖

---

## v4 — 平台收斂與部署(規劃中)

### 持久化 job worker
- 取消 `asyncio.create_task` 即起即忘,改 SQLite + worker process
- server 重啟能 resume 正在跑的 job
- 候選:RQ / Celery / 自寫 thin worker

### Docker file + deploy 文件
- 給雲端 / 學生協作用
- 拆 web (建 image) + python (建 image) + nginx reverse proxy

### v2.1 — 自動內容企劃(`ideate.py`)
- 掃 watched_folders → Gemini 分析 PDF → `proposals.json`
- React UI 加企劃列表 + 核准
- 詳見 [plan_youtube_agent.md](plan_youtube_agent.md) v2.1

### v2.2 — Claude Code skill 包裝
- `pdf-to-video` skill:PDF → JSON → 暫停 review → render
- `video-to-youtube` skill:已 review 的 JSON → publish
- 強制 review 點(配合硬規則 #1)

---

## v5+ — 長期(看需求再說)

### 多使用者 / 權限
- 開給實驗室其他老師用要有帳號系統
- 多使用者 exam / video 隔離

### 課程網站整合
- 推進 IAE 系課程網站 / Moodle
- 學生端:題目 QR code → 該題影片

### AI 批改助手
- 學生上傳答案掃描 → 跟 exam.json 標準解法比對
- 個人化回饋(哪一步錯、建議重看哪段)

### 國際化
- Gemini prompt 支援英文考卷 → 英文 narration
- 其他語系看需求

### v2 聲音複製品質穩定
- 重跑系統化實驗:ref 長度 / 品質、gen_text 分段、speed、lead_trim
- 候選:XTTS v2、GPT-SoVITS、更新版 F5
- 嘴型對齊(MuseTalk / SadTalker / Wav2Lip / V-Express)

---

## 技術債 / 重構候選

- `pipeline.py` 800+ 行,可拆 `render.py` / `compose.py` / `tts.py`
- `app.py` Flask template 全寫字串,Track A 棄用前不重構
- 同名工具字串 helper 分散(sanitize / wrap / normalize 在不同檔)
- `requirements.txt` 沒區分必要 / 選用,新人裝不確定
- `core/scriptor.py` 555 行,prompt template 占大半,可抽到 `prompts/` 資料夾

---

## 決策紀錄

- **用 Gemini 不用 Claude**:Gemini 2.5 Flash 輸出 token 上限高(64K)、視覺夠、便宜 ~10x
- **黑板主題維持深綠**:已驗證學生接受度高
- **TTS 不燒字幕預設**:YouTube 可分離上傳 SRT,保持選擇性
- **UI 寫在 Flask template 字串(Track A)**:POC 階段方便,Track A 棄用後不再用
- **新功能進 Track B 不進 Track A**(2026-05 起)
- **不 refactor pipeline.py**:現在能跑就好,v3.1 完成後再評估
- **deck schema 渲染前壓平 v1 schema**:過渡方案,未來 pipeline 直接吃 deck 後可棄
