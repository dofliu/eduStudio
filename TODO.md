# TODO

短期可立刻做、小而具體的事項。大方向看 [ROADMAP.md](ROADMAP.md)。

規則:
- 完成的打勾,定期把勾完的搬去 ROADMAP 或刪掉
- 新增項目加日期當引用(方便追)
- 優先度標示:🔴 高 / 🟡 中 / 🟢 低

---

## 🔴 高優先(Code review follow-ups, v3.3 動工時順手)

獨立 review 報告: [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md) (2026-05-09)

### P0 真該補
- [x] **`core/logging_setup.py` `_job_handlers` 加 lock** (2026-05-10)
  - `threading.Lock()` 包 attach/detach, 順手把 `datetime.utcnow()` 也換掉
- [x] **`utc_now()` 帶 timezone** (2026-05-10)
  - 改 `datetime.now(timezone.utc)`, Pydantic 序列化吐 `Z` 字尾, 跨瀏覽器都認
- [x] **`/upload` 加 size limit** (2026-05-10)
  - `MAX_UPLOAD_SIZE = 200 MB` + content-length 預檢 + read 後二次防呆
- [x] **`solve.py` 改 raise 取代 sys.exit** (2026-05-10)
  - solve.py / scriptor.py / outliner.py / slide_ingest.py 全改 `raise RuntimeError`
  - runner.py 兩處 `except (Exception, SystemExit)` 收回 `except Exception`
  - core/youtube.py 那條 SystemExit catch 是 publish.py CLI 的 OAuth bootstrap, 留著

### P1 應補
- [x] **`PptxStyleRenderer.render` step_idx 越界防護** (2026-05-10)
  - 缺 steps / step_idx 越界 → `raise ValueError` 帶清楚訊息
- [x] **F5 seg WAV cleanup 移 finally** (2026-05-10)
  - `tmp_files` list 收所有暫存 (seg / manifest / merged), finally 統一 unlink
- [x] **PublishReview 雙擊防呆** (2026-05-10)
  - `submittingRef` 同步擋雙擊 closure stale, button 加 isUploading 條件 disabled

---

## 🟡 中優先(實戰打磨)

### Phase 4 split-left layout (留 v3.3)
- [x] **`SlideRenderer` 加 layout="split-left"** (2026-05-10, Option A 靜態版)
  - 左半 940 寬投影片縮放, 右半 920 寬 title + bullets, 字幕黑帶 180px
  - SlideEditor 加 layout 下拉, split-left 模式顯示 bullets 編輯器
  - deck_to_exam_schema_slides 透傳 title + bullets, full layout 不讀但保 schema 一致
  - 5 dispatch test + 2 deck passthrough test (140 → 147 tests)
  - **未做**: Option B 累積式 (一張題目圖 + 多個 step 疊在右側), 真有解題影片需要再考慮

### 內容品質
- [ ] **Gemini narration 截斷率 22%** (2026-05-07)
  - 三段 retry + truncate 後仍 22% 頁面 narration 不完整
  - 候選: 換 Gemini 2.5 Pro / 加第 4 次 retry
- [ ] **Pronunciation map 缺漏收集**
  - 跑幾份考卷後列念錯字補 `pronunciation.json`

### F5 後續(中-中切錯已修, 中-英 / 中國腔還沒)
- [ ] **F5 中國腔仍明顯**
  - 短期試拉高 cfg_strength
  - 中期試 GPT-SoVITS / 其他台灣腔友善 model
  - 長期: 自己 fine-tune 一份台灣腔 checkpoint
- [ ] **錄音腳本工具** `tools/record_ref_script.py`
  - 產 F5 ref 用的朗讀腳本(10~12 秒、抑揚頓挫)

### UI / UX
- [ ] **LogPanel auto-scroll 在 user 上滑時打斷** (CR P2 #10)
  - detect scrolledToBottom, 只在底端時 auto-scroll
- [ ] **上傳審查頁 SRT 重生成預覽**(若 user 手動編了 narration 後)
- [ ] **`tts_config.json` 容易誤 commit** (CR P2 #9)
  - 候選: 加 .gitignore + tts_config.example.json 模板
  - 或 pre-commit hook 偵測並警告

### Track A 殘留(可選, 等 Track B 實戰一週後再評估)
- [ ] **Track A 完全退場** (Track B 已涵蓋全部工作流)
  - 砍 app.py 跟 v1 相關 routes (`/edit`, `/library` 等)
  - 保留 `solve.py` / `slide_ingest.py` CLI(被 server runner 內部呼叫)
  - 保留 `publish.py` CLI(OAuth bootstrap 用)

---

## 🟢 低優先(看時間)

### v4 平台收斂
- [ ] **Docker file + deploy 文件** — 給雲端 / 學生協作用
- [ ] **持久化 job worker** — server 重啟可 resume(SQLite + worker)
- [ ] **包成 Claude Code skill** — `pdf-to-video` / `video-to-youtube`
- [ ] **v2.1 ideate.py** — watched_folders 自動企劃

### 工程圖 AI 輔助
- [ ] **Gemini → matplotlib / TikZ → 本地執行畫圖**(自由體圖、彎矩圖、方塊圖)
- [ ] 步驟 `image` 欄位動態切圖

### 技術債
- [ ] **`pipeline.py` 拆檔**(800+ 行,候選: render / tts / srt / photo overlay)
- [ ] **`requirements.txt` 區分必要 / 選用** — fastapi 等 Track B 才用
- [ ] **`core/scriptor.py` prompt 抽到 `prompts/`** — 555 行裡 prompt 占大半
- [ ] **更多測試覆蓋** (CR 指出的並行 / 邊界):
  - `test_runner_concurrent_section_render`
  - `test_upload_oversized_pdf`
  - `test_burn_subtitles_windows_path`

### 文件
- [ ] **操作手冊給研究室助理** — Kiwi / Christian 接手用
- [ ] **demo 影片** — YouTube 頻道開專區介紹這個系統

---

## 已知問題(不修)

- **F5-TTS 幻覺**:ref 12 秒 cutoff + ref_text 對齊是主因, YouTube 抽音軌的 ref 品質不穩
- **Gemini 偶爾寫錯單位**:硬規則是人工 review,不是系統 bug
- **edge-tts 停用 `zh-TW-YunJheNeural`**:台灣男聲無選項,只能用大陸男聲
- **Windows 終端 cp950 吃不下 emoji**:已用 `core.runtime.setup_utf8_stdout` 解決
- **`tts_config.json` 在 server 啟動 / smoke test 後會被改**:工作流上注意,別 commit

---

## 已完成(最近 1~2 週,完整列表搬到 ROADMAP)

### v3.2 + 加分 (2026-05-09)
- [x] PR-5c 燒字幕進 MP4 選項
- [x] PR-5b F5 中文預切句(治本 mid-word 切錯)
- [x] PR-5a Navy pptx 主題
- [x] PR-4c structured logging + log panel
- [x] PR-4b pytest 基底 + GitHub Actions CI (140 tests)
- [x] PR-4a 單章 / 單題重 render
- [x] docs/CODE_REVIEW.md 獨立審查 (4 P0 + 4 P1 follow-ups)

### v3.1 平台合一 (2026-05-08~09)
- [x] PR-3m Library 跨 job 影片總覽
- [x] PR-3l 聲音 picker + 試聽
- [x] PR-3k Track B PDF 上傳 (multipart)
- [x] PR-3j FAILED 可編輯 + retry render
- [x] hotfix Windows .js MIME (修 React UI 白畫面)
- [x] PR-3i Track A redirect (預設 / → :8000/ui/)
- [x] PR-3h slides_pdf 升 deck schema + 縮圖預覽
- [x] PR-3g 考卷 v1 schema 接 React UI
- [x] PR-3f Track B YouTube 上傳通道
- [x] docs branch 重整文件對齊三輸入定位

### v3.0 平台基礎 (2026-05-07)
- [x] PR-1 ~ PR-3e (core / FastAPI / repo+document+url 來源 / pptx 主題 / vanilla + React UI)
