# TODO

短期可立刻做、小而具體的事項。大方向看 [ROADMAP.md](ROADMAP.md), 內容品質
看 [docs/CONTENT_QUALITY_ROADMAP.md](docs/CONTENT_QUALITY_ROADMAP.md).

規則:
- 完成的打勾, 定期把勾完的搬去 ROADMAP 或刪掉
- 新增項目加日期當引用 (方便追)
- 優先度標示: 🌟 下階段重點 / 🔴 高 / 🟡 中 / 🟢 低
- 完整 iter 歷史看 git log + [docs/CHANGELOG.md](docs/CHANGELOG.md) + STATUS.yaml

> Routine agent 看這個檔挑下一個任務. 看 [docs/ROUTINE_ADVANCE_PROMPT.md](docs/ROUTINE_ADVANCE_PROMPT.md) 流程.

---

## 🌟 等用戶介入 (routine 不該動)

> routine 不該自己決策的事 — 等劉老師實機反饋 / 給樣本 / 給 API key.

- [ ] **詞句 / 發音對照**: 等用戶列實測念錯的詞, 加進 `pronunciation.json`
- [ ] **narration_style preset 選定**: 用戶試 5 個 (academic / storyteller /
  wuxia / dialogue / comedy) 選喜歡, 預設可改
- [ ] **persona/jliu v2 樣本**: 等用戶聽完 v1 給「該怎麼講」樣本, 調 prompt
- [ ] **voice clone (ElevenLabs Instant)**: 等用戶決定是否啟用 — 要錄 1 分鐘
  乾淨人聲 + 月費 $5 起
- [ ] **GCP Voice Studio / Custom Voice**: 等 allowlist 個人帳號開放
- [ ] **C2 F5 pronunciation 樣本**: 已被 GCP TTS 主軌取代, 看用戶是否還要維護 F5

---

## 🌟 Active backlog (routine 可自主推進)

### 階段 1 — 短期 (1~2 週內)

**C. Claude Code skill 包裝 `pdf-to-video`** ✨ 進行中
- [ ] skill 自動 poll 流程實作 (現在是文字指引, 改 Bash 包成 helper)
- [ ] `video-to-youtube` skill: 已 review 的 JSON → publish
  - 動 OAuth → 需先跟用戶討論安全模型, STOP 條件
- [x] skill README 整合 (放 docs/skills.md, iter 96) — 範例 PDF 留下次

**A. Docker + docker-compose** ✨ 進行中
- [ ] user 本機 `docker compose up --build` 實測, 修可能踩到的問題
- [ ] F5 GPU passthrough 實測 (nvidia-docker, 需 user 有 GPU 環境)
- [ ] production reverse proxy (nginx + TLS) — 等真要上雲時做
- [ ] YouTube OAuth client_secret 安全 mount 模式 — STOP 條件

### 階段 2 — 中期 (2~3 週)

**E. 工程圖 AI 輔助** ✨ 進行中
- [ ] **iter 21**: 整合 pipeline.py step image 欄位 (取代或補圖)
- 設計細節見 [docs/engineering-diagram-design.md](docs/engineering-diagram-design.md)

**G. 動態視覺素材** ✨ RFC approved, routine 可推 (2026-05-22 用戶決議)
- 決議: E1 走候選 A (PNG frame 序列), E2 走候選 A (keyword grep),
  icon library 風能/自動控制/材力各 5 + generic 10 = 25 個扁平 SVG,
  SVG 全 Gemini 產
- 建議推進順序 (見 design memo 末段):
  - [x] **E2-1**: `assets/icon_library/` 目錄 + manifest.json 框架 (iter 98)
  - [ ] **E2-2**: Gemini 一次性產 25 個扁平 SVG icon, commit 進 repo
  - [x] **E2-3**: `core/icon_picker.py` keyword grep 模組 (iter 99)
  - [x] **E2-4**: schema 加 `slide.icon_overlay` (iter 100)
  - [x] **E2-5**: slide_renderer alpha_composite 疊 icon (iter 102 SlideRenderer 兩 layout; iter 103 擴 BlackboardRenderer + PptxStyleRenderer 4 路 layout — 三大 renderer 全覆蓋)
  - [x] **E2-7**: +8~12 tests (iter 102 +19 含 NoOp/SVG/Position/Size; iter 103 +8 含 BlackboardRendererIntegration / PptxStyleRendererIntegration)
  - [~] **E2-6**: review UI 自動建議 icon 勾選列 (iter 106 backend slice `suggest_for_deck`; iter 107 API endpoint `GET /jobs/{id}/icon-suggestions` 包 suggest_for_deck — 含 require_file_exists / max_icons query params 跟 IconMatch JSON 序列化. 前端 UI 待後續 iter)
  - [x] **E1-1**: schema 加 `slide.image_frames` (iter 101)
  - [~] **E1-2**: slide_renderer 偵測 frame list 走多 PNG 順序 (iter 104: parser + SlideRenderer 兩 layout 接 terminal frame fallback; 真 frame 序列拆 step + build_clip refactor 待 E1-3)
  - [ ] **E1-3**: Gemini flow_diagram SVG prompt + cairosvg 渲 frame (含 build_clip refactor 拆 step → 多 PNG 配 narration 時長均分)
  - [ ] **E1-4**: review UI frame preview
  - [ ] **E1-5**: +5~10 tests
- 設計細節 + Gemini prompt 草稿見 [docs/dynamic-visual-assets-design.md](docs/dynamic-visual-assets-design.md)
- 對應 `CONTENT_QUALITY_ROADMAP.md` E 軸 (E1 + E2)
- 不可繞 require_review=True 硬規則 — 自動建議走 proposals 人工確認

### 階段 3 — 遠期 (等真要上雲再做)

**D. 持久化 job worker** (7~10 天, 要先列選型 RFC)
- [ ] 技術選型 RFC: RQ / Celery / SQLite + 自寫 trade-off
- [ ] schema migration 設計 (跟 P0 #3 一起做)
- [ ] worker process 拆出 server, IPC 機制
- [ ] server 重啟 resume 機制
- 對應 RFC: [docs/V4_WORKER_RFC.md](docs/V4_WORKER_RFC.md)

**F. 課程網站整合 / Moodle plugin** (10+ 天)
- 學生掃 QR code → 跳該題目影片
- 學期跑下來實際使用數據, 寫 EdTech 論文

---

## 🔴 P0 結構性弱點

> 對個人使用 OK, 對「交給 Kiwi / Christian / 雲端」不可接受。
> 動 D 之前要先想清楚 #1 + #3 怎麼解.

- [ ] **#1 無 job 持久化** — `asyncio.create_task` 即起即忘, server 重啟丟所有 job
- [ ] **#2 單一 process FastAPI sync I/O 仍是炸雷** — F5 已踩, 沒 enforcement
- [ ] **#3 schema migration 無框架** — Round 2 P0 #4 已踩 (naive↔aware datetime)
- [ ] **#4 無 review gate 強制機制** — `require_review=True` 靠 server flag 擋, 可繞

---

## 🟡 中優先

### 內容品質
- [ ] **Gemini narration 截斷率 22%** (2026-05-07)
  - 三段 retry + truncate 後仍 22% 頁面 narration 不完整
- [ ] **Pronunciation map 缺漏收集** — 跑樣本影片自動收念錯詞

### F5 後續
- [ ] **F5 中國腔仍明顯** (已被 GCP TTS 取代主軌, 但若想留 voice clone 軌)
- [ ] **錄音腳本工具** `tools/record_ref_script.py`

### UI / UX
- [ ] **上傳審查頁 SRT 重生成預覽** (若 user 手動編了 narration 後)

### Track A 殘留 (可選)
- [ ] **Track A 完全退場** (Track B 已涵蓋全部工作流)

---

## 🟢 低優先

### 技術債
- [ ] **`pipeline.py` 拆檔** (800+ 行, 候選: render / tts / srt / photo overlay)
- [ ] **更多測試覆蓋**:
  - [ ] `test_runner_concurrent_section_render` (需 asyncio TestClient + 真 runner mock)

### 文件
- [ ] **demo 影片** — YouTube 頻道開專區介紹這個系統

### Round 2 殘留 (實戰罕見不修)
- [ ] `_render_split_left` bullets 截斷時機: 越界檢查在已畫完之後

---

## 已知問題 (不修)

- **F5-TTS 幻覺**: ref 12 秒 cutoff + ref_text 對齊是主因
- **Gemini 偶爾寫錯單位**: 硬規則是人工 review, 不是系統 bug
- **edge-tts 停用 `zh-TW-YunJheNeural`**: 台灣男聲無選項
- **Windows 終端 cp950 吃不下 emoji**: 已用 `core.runtime.setup_utf8_stdout` 解決

---

## 重要踩坑紀錄 (給 routine 看)

- **`tts_config.json` 在 server 啟動 / smoke test 後會被改**: 不要 commit
- **CI 4 組 matrix 必須全綠才算過**: ubuntu/win × py 3.10/3.12 + frontend-typecheck
- **`from X import Y` 跨 module sync 問題**: import 時 capture 不 follow 後續變化,
  改 module-level 常數要 patch 所有 import 過的地方 (iter 83/85 踩過)
- **dispatch 雙層**: 既有 `overlay_teacher_photo` (PIL) + `build_clip` (ffmpeg overlay)
  兩條都會畫頭像, 加 override 要兩處都接 (iter 92→94)
- **prompt placeholder 加新欄位**: 既有測試呼叫 `.format(...)` 全部要補新 kwarg
  (iter 92 踩過 test_length_mode / test_prompts_loader)
- **要改 schema 型別**: 看 docs/CODE_REVIEW.md Round 2 lessons-learned, 寫 migration
- **letterbox-fit 跟字幕帶**: visible_h = HEIGHT - SUBTITLE_BAND_HEIGHT, 不是整個 HEIGHT
