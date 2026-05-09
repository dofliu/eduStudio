# TODO

短期可立刻做、小而具體的事項。大方向看 [ROADMAP.md](ROADMAP.md)。

規則:
- 完成的打勾,定期把勾完的搬去 ROADMAP 或刪掉
- 新增項目加日期當引用(方便追)
- 優先度標示:🔴 高 / 🟡 中 / 🟢 低

---

## 🔴 高優先(v3.1 平台合一)

### PR-3f: Track B 接 YouTube 上傳

- [ ] **新增 `server/routes/youtube.py`(或併 jobs.py)** (2026-05-09)
  - `POST /jobs/{id}/publish` — 跑 publish.py 的 upload + caption
  - `GET /jobs/{id}/youtube_meta` — 預填標題 / 描述 / 標籤(讀 deck.json + step durations 算時間軸)
  - `PUT /jobs/{id}/youtube_meta` — 上傳前手改 metadata
- [ ] **`web/src/pages/PublishReview.tsx`** — 嵌 video player + 預填 metadata + 隱私 radio + 一鍵上傳
- [ ] **state.json 加 `youtube` 欄位**(video_id / url / privacy / uploaded_at),JobsIndex 顯示 YouTube badge
- [ ] **OAuth token 共用**:reuse `client_secret*.json` + `youtube_token.json`,跟 Track A 同源

### PR-3g: 考卷 v1 schema 接 React UI

- [ ] **`web/src/pages/ExamEditor.tsx`** — 認 `problems / steps` schema,逐題逐 step 編輯
- [ ] **JobEditor 自動分流** — deck schema → SlideEditor;exam schema → ExamEditor
- [ ] **單 step 重渲染**(Track A 已有,搬過來) — `POST /jobs/{id}/problems/{pid}/steps/{idx}/render`
- [ ] **步驟補圖 / 預覽** — Track A 的 `image` 欄位編輯器搬過來

### PR-3h: slides_pdf 升 deck schema

- [ ] **`slide_ingest.py` 輸出新 deck schema** — 每頁 = section.slide,bg_image 欄位
- [ ] **舊 v1 schema migration helper** — 讀舊 → 自動轉新(讓 exams/ 既有 JSON 不死)
- [ ] **`SlideEditor` 加 bg_image 縮圖預覽**(deck schema slide 渲染前看到)
- [ ] **`core.deck.deck_to_exam_schema_slides`** 渲染前壓平,沿用 SlideRenderer

### PR-3i: Track A redirect / 棄用準備

- [ ] **`app.py` 啟動加旗標** — 終端列「⚠ Track A 即將退場,改用 :8000」
- [ ] **`/` redirect** — 轉到 `:8000/ui/`(env var `KEEP_TRACK_A=1` 可關)
- [ ] **README 主推改成 Track B**,Track A 移到「legacy 段落」(README 已改過,複查一次)
- [ ] **新功能不再進 Track A**(原則,實作上靠 review 把關)

---

## 🟡 中優先(v3.2 基礎建設)

### PR-4a: 單 section / 單 slide 重渲染
- [ ] `POST /jobs/{id}/sections/{sid}/render` 端點 (2026-05-09)
- [ ] React UI 加「只渲染本章」按鈕,deck / exam 兩 schema 都支援
- [ ] runner 階段管理可恢復化(目前線性 ingest → render 不能跳)
- [ ] artifacts 增量更新(不全部覆蓋)
- 動機:長 deck 改一張要重跑 30+ 分鐘無法接受

### PR-4b: pytest 基底 + CI
- [ ] `tests/` 結構 (2026-05-09)
- [ ] 純函式優先:`text_utils` / `deck` normalizer / `adapters/repo` SKIP_DIRS+priority / `jobs.py` JobStore CRUD
- [ ] LLM mock fixture(scriptor / outliner 跑 stable golden)
- [ ] GitHub Actions:Python 3.10/3.12 + Win/Ubuntu matrix
- 動機:7264 行 Python 0 個測試,改 prompt / 換 schema 都沒護網

### PR-4c: Structured logging
- [ ] 換 `logging` module + JSON formatter (2026-05-09)
- [ ] 每 job 一個 log file:`jobs/<id>/log.jsonl`
- [ ] React UI 加 logs panel(tail 最近 200 行)
- [ ] failed job 一鍵 retry(目前要刪掉重跑)
- 動機:server 在跑長 job,沒結構化 log 看不出哪卡住

---

## 🟡 中優先(內容 / 品質)

### Gemini / narration
- [ ] **截斷率 22%** (2026-05-07) — 三段 retry + truncate 後仍 22% 頁面 narration 不完整。候選:換 Gemini 2.5 Pro / 加第 4 次 retry
- [ ] **Pronunciation map 缺漏收集** — 跑幾份考卷後列念錯字,補 `pronunciation.json`(候選:`-` → `減`,但 `-1` 是負一不是減一)

### 聲音品質
- [ ] **F5 mid-word 切點問題** (2026-05-06,治本) — 「處理與應用」被切成「處」+「理與應用」。在 F5TTS class 用標點先切短段逐段 infer 後 concat
- [ ] **F5 中國腔仍明顯** — 短期試拉高 cfg_strength,中期試 GPT-SoVITS 等台灣腔友善 model
- [ ] **錄音腳本工具** `tools/record_ref_script.py` — 產適合當 F5 ref 的朗讀腳本(10~12 秒、有抑揚頓挫)

### UI / UX(過渡期 Track A)
- [ ] **考卷列表上傳 PDF 後預覽** — Gemini 解完直接進編輯頁有點突兀,中間插「辨識結果概覽」頁
- [ ] **上傳審查頁時間軸** — 依 step durations 算累積時間,自動產 YouTube 章節時間軸
- [ ] **上傳審查頁 SRT 重生成預覽**(用戶手動編了 narration 後)

### 渲染細節
- [ ] **`display` 超長 overflow** — 步驟文字現在有換行但字大,2 行 OK,3+ 行可能溢出

---

## 🟢 低優先(v3.3 加分 / v4 平台收斂)

### v3.3 加分功能
- [ ] **Navy pptx 主題** + theme 參數 + React UI 主題下拉(對應個人偏好 Forest 教學/Navy 科技)
- [ ] **Phase 4 split-left layout**(SlideRenderer `layout="split-left"`,投影片左 + 累積式 step 右)
- [ ] **燒字幕選項**(`ffmpeg -vf subtitles=...` 一個 filter)

### v4 平台收斂
- [ ] **持久化 job worker** — 取消即起即忘,server 重啟可 resume(SQLite + worker process / RQ / Celery)
- [ ] **Docker file + deploy 文件** — 給雲端 / 學生協作用
- [ ] **包成 Claude Code skill** (2026-05-06) — `pdf-to-video` / `video-to-youtube`,強制 review 點
- [ ] **v2.1 ideate.py** — 掃 watched_folders → Gemini 分析 → proposals.json → React UI 列企劃

### 工程圖 AI 輔助
- [ ] **Gemini → matplotlib / TikZ code → 本地執行畫圖**(自由體圖、彎矩圖、方塊圖、電路圖)
- [ ] 步驟 `image` 欄位動態切圖(v1.6 schema 已支援)

### 技術債
- [ ] **`pipeline.py` 拆檔**(800+ 行,候選:render / tts / srt / photo overlay)
- [ ] **`requirements.txt` 區分必要 / 選用** — fastapi / uvicorn / pydantic 是 Track B 才用,初次安裝可省
- [ ] **`core/scriptor.py` prompt 抽到 `prompts/`** — 555 行裡 prompt template 占大半
- [ ] **單元測試** — `normalize_for_tts` / `sanitize_exam_name` / `wrap_text_for_font` 純函式該有 pytest(歸到 PR-4b)

### 文件
- [ ] **操作手冊給研究室助理** — Kiwi / Christian 之後接手 reference,含 API key 設定 / 上傳流程 / 錯誤排除
- [ ] **demo 影片** — YouTube 頻道開專區介紹這個系統

---

## 已知問題(未決)

- **F5-TTS 幻覺**:ref 12 秒 cutoff + ref_text 對齊是主因,YouTube 抽音軌的 ref 品質不穩。v3.3 處理。
- **Gemini 偶爾寫錯單位**:硬規則是人工 review,不是系統 bug。
- **edge-tts 停用 `zh-TW-YunJheNeural`**:台灣男聲無選項,只能用大陸男聲。
- **Windows 終端 cp950 吃不下 emoji**:已用 `sys.stdout.reconfigure` 解決(`core.runtime.setup_utf8_stdout`)。
- **Track A / Track B 同份 PDF 跑兩邊會產生兩份結果,沒 dedup**:過渡期不解,v3.1 結束 Track A 退場後消失。

---

## 已完成(偶爾清一清,只保留最近 1~2 週)

搬到 ROADMAP 對應段落。

- [x] 2026-05-07 React 18 + TS + Vite + Tailwind UI(PR-3e)
- [x] 2026-05-07 Vanilla server-side editor(PR-3d)
- [x] 2026-05-07 submit_job.py 排程 CLI(PR-3c)
- [x] 2026-05-07 document / url adapters(PR-3b)
- [x] 2026-05-07 Forest 主題 Pillow renderer(PR-2b-ii)
- [x] 2026-05-07 repo 資料夾 → outline → deck.json(PR-2b-i)
- [x] 2026-05-07 FastAPI server + JobStore(PR-2a)
- [x] 2026-05-07 core/ package(PR-1)
- [x] 2026-05-07 narration 長度收斂(三輪迭代 + 3 段式 retry + truncate 兜底)
- [x] 2026-05-07 F5 暴露 cfg_strength / cross_fade_duration / nfe_step
- [x] 2026-05-07 ζ / ω_n 改念概念名(避中-英切換 + 中國腔)
- [x] 2026-05-07 pronunciation map 套用層下移到 tts_backend
- [x] 2026-05-06 v2.0 publish.py CLI + UI 整合(YouTube 上傳通道)
- [x] 2026-05-06 v1.7 Phase 1+2+3+5(簡報講解影片擴充)
