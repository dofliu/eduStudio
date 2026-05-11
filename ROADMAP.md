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

## v3.1 — 平台合一(2026-05 完成)

**目標達成:Track A 工作流上正式退場,所有功能搬到 Track B。**

### PR-3f — Track B 接 YouTube 上傳 ✅ (commit b22bb36)
- [x] `server/routes/youtube.py`:`POST /jobs/{id}/artifacts/{name}/publish` + `youtube_meta` 預填(章節時間軸自動算)+ `youtube_status` 輪詢
- [x] `core/youtube.py`:`publish_artifact` + `auto_youtube_meta` + `OAuthBootstrapRequired`
- [x] `web/src/pages/PublishReview.tsx`:嵌 video player + 預填 form + 進度條
- [x] state.json 加 `youtube_uploads: dict[artifact_name, YoutubeUpload]`
- [x] JobsIndex JobCard 顯示 📺 N/M badge

### PR-3g — 考卷 v1 schema 接 React UI ✅ (commit e2dcf68)
- [x] `web/src/components/ExamProblemsPanel.tsx` + `StepEditor.tsx`
- [x] JobEditor 依 schema 自動分流(deck schema → SlideEditor / exam schema → ExamProblemsPanel)
- [x] 字數提示 / `_section` 分類下拉 / bg_image step 顯示縮圖檔名 hint

### PR-3h — slides_pdf 升 deck schema ✅ (commit b1d669c)
- [x] `slide_ingest.py` 加 `as_deck=True` 旗標
- [x] `build_deck_sections()` 共用 chapter / narration 三階段, 只差最後組裝
- [x] `core.deck.deck_to_exam_schema_slides` 渲染前壓平保留 bg_image
- [x] `server/routes/slides.py`:`/slide_images/{stem}/{filename}` 縮圖路由
- [x] `web/src/components/SlideEditor.tsx` isSlideMode 顯示 PNG 預覽

### PR-3i — Track A redirect / 棄用 ✅ (commit 4716e7e)
- [x] `app.py` 根路徑 `/` 預設 302 redirect 到 `TRACK_B_URL`
- [x] `KEEP_TRACK_A=1` 保留原行為, `TRACK_B_URL` 自訂目的地
- [x] 全頁黃底 banner 提示棄用
- [x] 啟動 70 字寬橫幅雙模式區分

### Hotfix — Windows .js MIME (commit ada67b1)
- [x] `mimetypes.add_type` 在 `server/main.py` 強制 `.js → application/javascript`
- [x] 修 React UI 在 Windows 白畫面(strict MIME check 拒載 ES module)

### PR-3j — FAILED 可編輯 + retry render ✅ (commit 1bb24da)
- [x] `PUT /draft` + `POST /approve` 接受 FAILED state
- [x] `_run_render_phase` 清掉 stale error
- [x] React 紅色 banner + 「🔄 重試 render」按鈕

### PR-3k — Track B PDF 上傳 ✅ (commit 9287884, 跟 PR-3l 同 commit)
- [x] `server/routes/uploads.py`:`POST /upload` (multipart)
- [x] 接受 exam_pdf / slides_pdf / document, 拒 repo / url
- [x] `_sanitize_filename` + 同名加時間戳
- [x] CreateJobForm 加上傳 / path / url 三模式 radio

### PR-3l — 聲音 picker + 試聽 ✅
- [x] `server/routes/voices.py`:GET / POST / sample 三端點
- [x] VOICES list 6 個(5 edge + 1 F5),f5: 開頭切 backend
- [x] `VoicePicker.tsx` header 全域顯示
- [x] App.tsx header 整合

### PR-3m — Library 跨 job 影片總覽 ✅ (commit a49d8fe)
- [x] `server/routes/library.py`:`GET /library` 平鋪所有 mp4
- [x] `web/src/pages/Library.tsx`:grid 卡片 + filter (source_type / YT 狀態)
- [x] `/ui/library` 路由 + header nav 連結

---

## v3.2 — 基礎建設(2026-05 完成)

### PR-4a — 單 section / 單題重 render ✅ (commit 1007dc3)
- [x] `POST /jobs/{id}/sections/{section_id}/render`
- [x] `_run_render(section_id=...)` filter problems
- [x] DONE / FAILED 才能觸發, 新 stage 名 `render-section-{id}`
- [x] JobEditor / ExamProblemsPanel header 加「🎬 重 render 本章」

### PR-4b — pytest 基底 + CI ✅ (commit 3b17ade)
- [x] `pyproject.toml` [tool.pytest.ini_options]
- [x] `requirements-dev.txt` (pytest + httpx)
- [x] `.github/workflows/test.yml` 4 組 matrix (3.10/3.12 × Linux/Win)
- [x] 108 tests 初版 (text_utils 22, deck 25, youtube_helper 17, jobs_store 32, voices 13)

### PR-4c — Structured logging ✅ (commit f4f6008)
- [x] `core/logging_setup.py`:setup_logging / attach_job_log / detach_job_log / read_job_log
- [x] contextvar `current_job_id` 自動帶 job_id 進 log
- [x] `runner.py` 開 job 自動 attach, 結束 detach
- [x] `GET /jobs/{id}/log?tail=N`
- [x] `LogPanel.tsx` 摺疊式 + LIVE 狀態 3 秒 auto-poll

---

## v3.3 — 體驗加分(2026-05 部份完成)

### Navy pptx 主題 ✅ (PR-5a, commit ec8befb)
- [x] `THEMES` dict (forest / navy) + `get_palette` 容錯查
- [x] 全部 _draw_* 函式 palette 參數化
- [x] `JobOptions.theme` 欄位
- [x] `runner.py` 寫進 v0 dict
- [x] CreateJobForm 主題下拉(只對 repo / document / url 顯示)
- [x] 13 tests covering THEMES / get_palette / contrast

### F5 中文預切句 ✅ (PR-5b, commit c5d2f81)
- [x] `split_for_f5(text, max_chars=30)` 標點預切
- [x] `F5TTS.synthesize` 逐段 infer + ffmpeg concat
- [x] 13 tests covering 切點規則 + 邊界

### 燒字幕選項 ✅ (PR-5c, commit e764cab)
- [x] `pipeline._build_hardsub_cmd` + `burn_subtitles`
- [x] `JobOptions.hardsub` 欄位
- [x] CreateJobForm checkbox(對所有 source 顯示)
- [x] force_style: Microsoft JhengHei 22pt + BorderStyle=3
- [x] 6 tests for command construction

### Phase 4 split-left layout ✅ (2026-05-10, Option A 靜態版)
- [x] `SlideRenderer` 加 `layout="split-left"` 分支
  - 左半 940 寬投影片縮放, 右半 920 寬 title + bullets, 字幕黑帶 180px
  - 案內常數: DIVIDER_X=955, RIGHT_X=980, TITLE 52px, BULLET 32px
- [x] `core.deck.deck_to_exam_schema_slides` 透傳 title + bullets (full 不讀, 保 schema 一致)
- [x] `SlideEditor` 加 layout `<select>`, split-left 才顯示 bullets 編輯器
- [x] 7 tests (5 dispatch + 2 deck passthrough); 140 → 147 tests
- 未做: Option B 累積式 (section 共用一張題目圖 + 右側疊 step 行) — schema 大改, 等真有解題影片需求再評估

### 工程圖 AI 輔助(待做)
- [ ] 自由體圖、彎矩圖、方塊圖、電路圖
- [ ] Gemini 產 matplotlib / TikZ code,本地執行畫圖
- [ ] 步驟 `image` 欄位動態切圖

### Code Review follow-ups(2026-05-09 review 找出)
- [x] P0: `_job_handlers` 加 `threading.Lock` (2026-05-10)
- [x] P0: `utc_now()` 改 `datetime.now(timezone.utc)` (2026-05-10)
- [x] P0: 上傳加 `MAX_UPLOAD_SIZE` (200MB) + Content-Length 預檢 (2026-05-10)
- [x] P0: `solve.py` / scriptor / outliner / slide_ingest 把 `sys.exit()` 改 raise, runner 移除 `SystemExit` catch (2026-05-10)
- [x] P1: `PptxStyleRenderer.render` 加 step_idx 越界防護 (2026-05-10)
- [x] P1: F5 seg WAV cleanup 移到 finally (2026-05-10)
- [x] P1: PublishReview button 雙擊 race (submittingRef 同步擋, 2026-05-10)

詳細見 [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md)。

### Round 2 hotfix(2026-05-10 實戰才踩)
- [x] `AwareDatetime AfterValidator` — naive/aware datetime 共存防炸 (commit f3fca88)
- [x] F5 `_lazy_init` 包 `asyncio.to_thread` — 1.35GB safetensors download 不阻 event loop (commit 318f5e8)
- [x] `update_draft` 允許 `DONE` state — 接通 DONE section re-render (commit e372b7f)
- [x] `_render_full` letterbox 縮 `HEIGHT - 180` 進可視區 — slide 底部 16.7% 不被字幕帶蓋 (commit 07c4a45)
  - ⚠ **Visual regression**:fix 之前產出的 mp4 (含 `jobs/b40d51a96a07` 的 Chap05 4 支)
    視覺比 fix 後大 17%,底部標籤/footer 被字幕帶覆蓋。要不要重 render 由用戶決定,
    不重 render 也能用,只是底部缺失。

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
