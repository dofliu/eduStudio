# TODO

短期可立刻做、小而具體的事項。大方向看 [ROADMAP.md](ROADMAP.md)。

規則:
- 完成的打勾,定期把勾完的搬去 ROADMAP 或刪掉
- 新增項目加日期當引用(方便追)
- 優先度標示:🌟 下階段重點 / 🔴 高 / 🟡 中 / 🟢 低

---

## 🌟 下階段規劃(2026-05-11 排定,按投報率)

> 這是當前 active 工作清單,user 問「下一個做什麼」直接從這裡挑。
> 階段 1 → 階段 2 → 階段 3 漸進,每階段內部可重排。

### 階段 1 — 短期 1~2 週

**C. Claude Code skill 包裝 `pdf-to-video`** (1~2 天) ✨ 進行中
- [x] `pdf-to-video` skill SKILL.md scaffold (2026-05-12, commit pending)
  - 包裝既有 `scripts/submit_job.py` CLI, 強制 review point 寫進 skill 流程 (Step 4)
  - 涵蓋 exam / slides / document 三種 source
  - 明文化「不繞 require_review=True」「不偽裝 AI 值」等硬規則
- [ ] **下一步**: 實測 skill 真的可以從對話一路跑到 artifacts (本機驗收)
- [ ] **下一步**: skill 自動 poll 流程實作 (目前是文字指引, 改 Bash 包成 helper)
- [ ] `video-to-youtube` skill: 已 review 的 JSON → publish
  - 動 OAuth → 需先跟用戶討論安全模型, STOP 條件
- [ ] skill 整合 README + 範例 PDF (放 docs/skills.md)
- 價值: 研究室擴張 (Kiwi / Christian / 任何 repo 一鍵跑)
- trade-off: 單機 skill 只能本地跑, 跨機器要走別的 hosting

**A. Docker + docker-compose** (2~3 天) ✨ 進行中
- [x] **Dockerfile v1 draft** (2026-05-12 commit pending) — 未實測, 待 user 跑 build
  - Multi-stage: web-builder (Node 20) → final (Python 3.12-slim + FFmpeg + Noto CJK)
  - .dockerignore 排除 runtime / 個人資源 / .git / __pycache__
  - 字型走 Noto CJK (Linux 安裝的, 不是 Windows msjh.ttc 專屬)
  - ENV: GEMINI_API_KEY runtime / CLAUDE_FONT_PATH 對齊 noto / TTS_PROVIDER=edge
  - Healthcheck 走 /health
- [ ] **下一步**: docker-compose.yml (volumes + ports + env_file + restart policy)
- [ ] **下一步**: user 本機 docker build 實測, 修可能踩到的 deps / 字型問題
- [ ] F5 GPU passthrough 文件 (nvidia-docker / --gpus all, 需 user 有 GPU 環境才能測)
- [ ] production reverse proxy (nginx) — 等真要上雲時做
- [ ] 解 P0 #1 部分 (server 在容器內, restart policy 救基本場景)
- 價值: 部署可行性 + 學生協作

### 階段 2 — 中期 2~3 週

**B. v2.1 `ideate.py` 自動內容企劃** (4~5 天)
- [ ] `watched_folders/` 設計 + 路徑配置
- [ ] Gemini 掃 PDF → 產 `proposals.json` (主題 / 片單建議)
- [ ] React UI ProposalsList 頁 + 核准 / 否決 / 編輯
- [ ] 核准 → 自動 create job
- 價值: 產品差異化, 從「批次工具」升級成「自動內容企劃平台」
- 風險: Gemini token 成本 / proposals 品質可能要二次篩

**E. 工程圖 AI 輔助** (3~5 天, 可跟 B 平行)
- [ ] Gemini 產 matplotlib / TikZ code → 本地畫圖
- [ ] step `image` 欄位動態切圖
- [ ] 圖類: 自由體圖、彎矩圖、方塊圖、電路圖
- [ ] 失敗 fallback: 純文字描述
- 價值: 材料力學 / 自動控制影片價值跳一階
- 風險: 產 code 品質起伏大, 要 review 機制

### 階段 3 — 遠期(等真要上雲再做)

**D. 持久化 job worker** (7~10 天, 要先列選型 RFC)
- [ ] 技術選型 RFC: RQ / Celery / SQLite + 自寫 trade-off
- [ ] schema migration 設計 (跟 P0 #3 一起做)
- [ ] worker process 拆出 server, IPC 機制
- [ ] server 重啟 resume 機制
- 價值: 雲端化前置, 沒這個其他都白搭
- trade-off: 架構複雜度跳一階

**F. 課程網站整合 / Moodle plugin** (10+ 天)
- 學生掃 QR code → 跳該題目影片
- 學期跑下來實際使用數據, 寫成 EdTech 論文
- 工程量大, IAE 課程網站工作流要先 alignment

---

## 🔴 P0 結構性弱點(2026-05-11 規劃時辨識,影響可靠性 / 擴張性)

> 對個人使用 OK, 對「交給 Kiwi / Christian / 雲端」不可接受。
> 這四條是上述規劃的根因,動 D 之前要先想清楚 #1 + #3 怎麼解。

- [ ] **#1 無 job 持久化** — `asyncio.create_task` 即起即忘, server 重啟 / Ctrl+C / Windows update 丟所有 job
  - 候選: SQLite + 自寫 thin worker / RQ / Celery
  - blocker: 雲端部署 / 長時間 batch 跑
  - 對應規劃: 階段 1 A (Docker restart 部分救) → 階段 3 D (根治)
- [ ] **#2 單一 process FastAPI 的 sync I/O 仍是炸雷** — F5 download 已踩 (commit 318f5e8), 下次加新 backend / model loader 高機率復發
  - 候選: `core/async_safe.py` 裝飾器強制 `to_thread`, 加 lint 規則或 runtime guard
  - 目前 mitigation: `tts_backend.py` docstring 警告 (commit 75bf434), 沒 enforcement
  - 對應規劃: 沒人扛, 看下次加什麼順手解
- [ ] **#3 schema migration 無框架** — Round 2 P0 #4 已踩 (naive↔aware datetime), 下次改型別還會踩
  - 候選: Pydantic v2 migration validator pattern + 版本化 schema
  - 加 regression test 模擬「混存舊新格式」
  - 對應規劃: 階段 3 D 一起做 (worker 重啟要 reload state)
- [ ] **#4 無 review gate 強制機制** — `require_review=True` 靠 server flag 擋, 測試/誤操作可繞
  - 學術誠信底線, Kiwi / Christian 接手後是真風險
  - 候選: schema 層強制 `awaiting_review` → `done` 轉換需 explicit approve event
  - 對應規劃: 階段 1 C (skill 包裝順手鎖死) ; 階段 3 D schema 重整時根治

---

## 🟡 中優先(實戰打磨, 不急但會回頭做)

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
- [x] **LogPanel auto-scroll 在 user 上滑時打斷** (CR P2 #10, 2026-05-12 完成)
  - pinnedToBottomRef + onScroll handler, 距底 < 5px 才視為 pinned 才 auto-scroll
  - 開啟 panel 時 reset pin = true (上次閱讀位置不跨開關週期)
- [ ] **上傳審查頁 SRT 重生成預覽**(若 user 手動編了 narration 後)
- [x] **`tts_config.json` 容易誤 commit** (CR P2 #9, 2026-05-12 完成)
  - 加 .gitignore + tts_config.example.json 範本 + README quick-start copy 步驟
  - git rm --cached 既有檔, 新 clone 走 example → 真檔 copy 模式

### Track A 殘留(可選, 等 Track B 實戰一週後再評估)
- [ ] **Track A 完全退場** (Track B 已涵蓋全部工作流)
  - 砍 app.py 跟 v1 相關 routes (`/edit`, `/library` 等)
  - 保留 `solve.py` / `slide_ingest.py` CLI(被 server runner 內部呼叫)
  - 保留 `publish.py` CLI(OAuth bootstrap 用)

---

## 🟢 低優先(看時間)

### 技術債
- [ ] **`pipeline.py` 拆檔**(800+ 行,候選: render / tts / srt / photo overlay)
- [ ] **`requirements.txt` 區分必要 / 選用** — fastapi 等 Track B 才用
- [ ] **`core/scriptor.py` prompt 抽到 `prompts/`** — 555 行裡 prompt 占大半
- [ ] **更多測試覆蓋** (CR 指出的並行 / 邊界):
  - `test_runner_concurrent_section_render`
  - [x] **`test_upload_oversized_pdf`** (2026-05-12 完成, 7 tests)
    - 涵蓋 size limit / 不支援 source_type / 空檔 / options_json 驗證
    - 第一個 FastAPI TestClient 整合測試, 為未來加更多 route 測試鋪路
  - `test_burn_subtitles_windows_path`

### 文件
- [ ] **操作手冊給研究室助理** — Kiwi / Christian 接手用
- [ ] **demo 影片** — YouTube 頻道開專區介紹這個系統

### Round 2 殘留(實戰罕見不修)
- [ ] `_render_split_left` bullets 截斷時機: 越界檢查在已畫完之後 (CR Round 2 #1)

---

## 已知問題(不修)

- **F5-TTS 幻覺**:ref 12 秒 cutoff + ref_text 對齊是主因, YouTube 抽音軌的 ref 品質不穩
- **Gemini 偶爾寫錯單位**:硬規則是人工 review,不是系統 bug
- **edge-tts 停用 `zh-TW-YunJheNeural`**:台灣男聲無選項,只能用大陸男聲
- **Windows 終端 cp950 吃不下 emoji**:已用 `core.runtime.setup_utf8_stdout` 解決
- **`tts_config.json` 在 server 啟動 / smoke test 後會被改**:工作流上注意,別 commit

---

## ✅ 最近完成(由新到舊)

### 2026-05-11
- [x] **`core/visuals.py` 集中 layout 常數** (commit 8abfb2e) — v4 暖身, 解 Round 2 lessons-learned #3 根因
  - `SUBTITLE_BAND_HEIGHT` / `CONTENT_BOTTOM` / `SUBTITLE_STRIP_COLOR` 集中
  - pipeline.py / pptx_style.py magic number 7 處統一
  - `tests/test_visuals.py` 7 tests 鎖值 + cross-module 一致性 (148 → 155 tests)
- [x] **Round 2 殘留 5 件全清** (commit ad7f4e1 + 75bf434)
  - `test_jobs_store.py` 三處 `datetime.utcnow()` → aware UTC
  - `tts_backend.py` module-level docstring「sync method 不能在 async 路徑直接呼叫」
  - `SlideEditor` split-left bullets 上限 UI hint (建議 ≤ 5 條)
  - README / ROADMAP 補 `07c4a45` visual regression 註記

### 2026-05-10
- [x] **Round 2 三條實戰補洞** (commit f3fca88 + 318f5e8 + 07c4a45)
- [x] **Phase 4 split-left layout** (Option A 靜態版, commit 7b1eba2)
- [x] **Round 1 P0+P1 follow-ups** (4 P0 + 3 P1, commit 7db9aab + e093720)

### 2026-05-09
- [x] **PR-5a/5b/5c v3.3 加分**: Navy 主題 / F5 中文預切句 / 燒字幕進 MP4
- [x] **PR-4a/4b/4c v3.2 基礎建設**: 單章重 render / pytest CI / structured logging
- [x] **docs/CODE_REVIEW.md** 獨立審查 (Round 1: 4 P0 + 4 P1)

### 2026-05-08
- [x] **PR-3f ~ PR-3m v3.1 平台合一**: YouTube 上傳 / 考卷編輯 / 簡報縮圖 / Library / 聲音切換 / PDF 上傳 / FAILED retry

完整歷史見 [ROADMAP.md](ROADMAP.md)。
