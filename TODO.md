# TODO

短期可立刻做、小而具體的事項。大方向看 [ROADMAP.md](ROADMAP.md), 內容品質
看 [docs/CONTENT_QUALITY_ROADMAP.md](docs/CONTENT_QUALITY_ROADMAP.md).

> 🚀 **推出去主線（產品等級稽核清單）**：見 [docs/PRODUCT_READINESS.md](docs/PRODUCT_READINESS.md)
> （安全/可靠性/UI 收斂/計費/部署/文件/測試/功能收尾，分 Phase 0~8 排好優先序）。
> 目標 = 公開開源自架。routine 優先從那邊 Phase 0→ 往下挑。

規則:
- 完成的打勾, 定期把勾完的搬去 ROADMAP 或刪掉
- 新增項目加日期當引用 (方便追)
- 優先度標示: 🌟 下階段重點 / 🔴 高 / 🟡 中 / 🟢 低
- 完整 iter 歷史看 git log + [docs/CHANGELOG.md](docs/CHANGELOG.md) + STATUS.yaml

> Routine agent 看這個檔挑下一個任務. 看 [docs/ROUTINE_ADVANCE_PROMPT.md](docs/ROUTINE_ADVANCE_PROMPT.md) 流程.

---

## 🌟 下一步候選 (2026-09-04 文件同步輪盤點)

> 2026-08-31:官方介紹影片收尾(配樂三輪 + `--loudness`)+ 新 skill `repo-intro-video`。
> 2026-09-04:純文件同步輪(零 code 變更),對照程式碼查核各文件說法。
> 環境驗證 `2842 passed / 13 skipped / 1 deselected(office_live)`(此容器沒 ffmpeg,
> 故 skip 較多;母數 2855 與本機宣稱的 2854 passed + 1 skipped 一致)、
> frontend `npm test` 7 綠 + `vite build` 產物正確指向 `/app/assets/...`。

**分支現況**:`main` 已推進到 `ac07ab4`(2026-08-31),工程收斂輪 / `/ui` 退場 /
Dockerfile 改建 / promo / `repo-intro-video` skill 都已在 main 上。
2026-09-04 文件同步輪走 PR #101(純文件 1 個 commit)。

### 🔴 先做(阻擋別人 / 一壞全壞)

- [ ] 🔴 **`gemini-3.7-flash` live 確認** — 本機 `python tools/check_models.py`。整條文字線
  (旁白/大綱/翻譯/解題/視覺)現在都吃這個 id,404 就一起壞;退路是設定頁 text 模型退
  `gemini-3.6-flash`(目錄鍵 `flash_36`)。**目前唯一未驗證的全域單點**。
- [ ] 🔴 **漫畫正式化 GATE**:真實生成 QA 一輪(開額度)+ 匯出實機檢查 + 手冊案例,
  checklist 見 [docs/COMIC_PRODUCTION_SYSTEM.md](docs/COMIC_PRODUCTION_SYSTEM.md)。

### 🟡 routine 可自主(offline,不需額度/實機)

> 全部來自 2026-07 全庫審查,細節見下方 🔍 段。

- [ ] 🟡 **T1-3/4/5**:背景 job 並行上限(Semaphore)、`state.json` 原子寫(`os.replace`)、
  dubber 暫存清理。
- [x] 🟡 **T2-1 SSRF 位址過濾** — ✅ 2026-09-04 完成(詳見下方 🔍 段)。
- [x] 🟢 **T2-4 schema 輸入界限** / **T0-3 review_assist 覆蓋率提示** — ✅ 2026-09-04 完成
  (詳見下方 🔍 段)。
- [ ] 🟡 **M-2 尾巴(需拍板)**:`scriptor`/`outliner`/`translate` 走 legacy
  `get_gemini_model()`,**吃不到逐角色 `model_roles`**(視覺站與 `solve` 吃得到)。
  模型值已對齊 3.7、無 2.5 殘留 → 剩的是解析路徑不一致,見 PRODUCT_READINESS「待拍板」#7。

### 🟢 收尾 / 人工

- [ ] 🟢 **介紹影片落地(DOC-5)**:製作鏈已就緒(`docs/promo/` 9 景 +
  `tools/build_promo_video.py`),剩本機跑一次 + 決定放法(YouTube 連結／repo 內檔案)。
- [ ] 🟢 **README / 手冊補 4 張截圖**(`docs/screenshots/`,需實機瀏覽器)。
- [ ] 🟢 **計費尾巴**:多模態「圖片輸入」token 未計;費率待官方價校正
  (`core/infocards/models.py` MODEL_PRICING)。

### 本輪修掉的文件漂移(2026-09-04)

- [x] `docs/PRODUCT_READINESS.md` 兩個 **U-5** 撞號 → 既有「發布站多語上傳驅動」改 **U-7**
  (repo 其他 U-5 引用一律指 `/ui` 退場)。
- [x] M-2 剩餘項描述過期(寫「仍預設 2.5」,實為已遷 3.7、差在不吃 `model_roles`)。
- [x] PRODUCT_READINESS「2026-06-16 routine 無事可做」快照 → 被 7 月審查殘項推翻,已改寫。
- [x] `docs/skills.md` 標題仍叫 autoSolverVideo、缺 `repo-intro-video` → 補齊。
- [x] `claude.md` 模型換接段落與實況對齊。
- [x] ROADMAP 補 v4.7、技術債清單勾稽;HANDOFF / STATUS / CHANGELOG 補 08-31 與本輪。

---

## 🌟 上一輪候選 (2026-08-30 文件盤點)

> 2026-08-20 ~ 08-28 完成:漫畫工作站 MVP、目標導向首頁、P0 live E2E 稽核、P1/P2 驗證
> (Ollama 接線 / PPTX round-trip / request validation / CI Node 24 / Whisper 三流程 /
> token 部署 / 四站 click-through)、P3 技術債(lifespan / asyncio / office gate / Whisper cache)。
> 見 [docs/P1_P2_COMPLETION_PLAN_2026-08-28.md](docs/P1_P2_COMPLETION_PLAN_2026-08-28.md) /
> [docs/P3_COMPLETION_PLAN_2026-08-28.md](docs/P3_COMPLETION_PLAN_2026-08-28.md)。以下為候選,優先序待劉老師拍板:

- [x] 🔴 **Google Photos OAuth consent** — ✅ 2026-08-30 劉老師完成授權(token 存
  `photos_token.json`),相片簡報軸 live 全通。
- [x] 🔴 **Sprint 1 收尾三小修** — ✅ 2026-08-30:T1-1 dubber filtergraph 連續索引、
  T2-2 compose 綁 127.0.0.1、T2-3 editor `j.error` escape,各補測試。
- [x] 🟡 **Sprint 2 穩定性根源** — ✅ 2026-08-30:`core/gemini_client.py` 統一 client
  (13 檔遷移,金鑰單一來源+一律 timeout)、`core/ffmpeg.py` 共用 runner(render 主路徑
  全遷,一律 timeout+returncode)、T0-4 解題走 `resolve_id`。
- [x] 🟡 **C-3:文字主力遷 gemini-3.7-flash** — ✅ 2026-08-30 劉老師拍板;旁白/解題/vision
  隨目錄 `flash` 鍵生效。⚠️ 剩:本機跑 `python tools/check_models.py` live 確認 3.7 id,
  404 就把設定頁 text 模型退 `gemini-3.6-flash`。
- [x] 🟡 **計費準確化** — ✅ 2026-08-30:補 6 個漏帳點(translate 直呼/diagram/mermaid/
  ideate×2 文字 + diagram_image/song_images 生圖);文字費率分 model(default 退路),
  未知圖片 model 不再記 $0。⚠️ 各檔費率仍為估算,官方價公布後在
  `core/infocards/models.py` MODEL_PRICING 校正。
- [~] 🟢 **漫畫工作站正式化** — 進行中:2026-08-30 offline 稽核完成(25 測綠/reader 全
  escape/token 保護/fail-closed 驗證),checklist 見
  [docs/COMIC_PRODUCTION_SYSTEM.md](docs/COMIC_PRODUCTION_SYSTEM.md);剩 🔴 GATE 真實
  生成 QA 一輪(開額度)+ 匯出實機檢查 + 手冊案例。
- [ ] 🟢 **README / 手冊補 4 張截圖**(`docs/screenshots/`,需實機瀏覽器)。
- [x] 🟢 **legacy `/studio` `/ui` 退場**(U-5)— ✅ 2026-08-30:web/ 原始碼移除、兩路徑
  307 轉址 `/app/`、Dockerfile 改建 frontend/(順修 image 缺 /app 的問題)、CI 收斂。

---

## 🔍 程式碼審查後續改善 (2026-07,見 [docs/CODE_REVIEW_2026-07.md](docs/CODE_REVIEW_2026-07.md))

> 2026-07 全庫程式碼審查(5 條並行子系統 + 逐一驗證)。完整發現含 file:line、失敗情境、
> 修法與分 Sprint 執行順序在 [docs/CODE_REVIEW_2026-07.md](docs/CODE_REVIEW_2026-07.md)。
> 此處只列 routine 認領用的勾選清單,依 Tier 由上而下、Sprint 順序做。
> **守 offline-first**:改抽象 / 加測試可自主;動 render / schema 跑 `pytest`;需 live 打
> Gemini 驗證的(如新 model id)寫 proposal 後 STOP。

### ✅ 已完成
- [x] 🟡 **圖片入門階對齊 Nano Banana 2 Lite** + 統一兩個登錄表(infocards ↔ core.models 單一
  來源 + 漂移守衛測試)(2026-07, PR #98)。⚠️ `gemini-3.1-flash-lite-image` 待 live 實測確認。
- [x] 🟡 **完整使用手冊 `docs/USER_MANUAL.md`**(所有工作站 / 設定對照 / REST API 速查 /
  Job 狀態機 / 疑難排解 / FAQ + 英文速查)+ README 中英雙語加「文件」導覽段 + `server.main:app`
  啟動雷提示(2026-07)。
- [ ] 🟢 補 `docs/screenshots/` 四張截圖(README / 手冊預留位,需實機瀏覽器)。

### Sprint 1 — 產品核心止血(最優先,直擊「絕不發布錯誤數字」)
- [x] 🔴 **T0-1 `clean_json_escapes` 公式修復**(`core/text_utils.py`)— ✅ 已修(2026-08,
  經 2026-08-30 查證:只保留 JSON 真實合法 escape、b/f/n/r/t 延展成 LaTeX 命令時補逃逸)。
- [x] 🔴 **T0-2 exam review gate 不可被關**(`server/jobs.py`)— ✅ 已修(2026-08,經 2026-08-30
  查證:`_resolve_default_review` 對 `EXAM_PDF`/`SONG` 一律 True、忽略 caller 傳入值)。
- [x] 🔴 **T1-1 dubber filtergraph 索引修復** — ✅ 2026-08-30 修復:保留段連續計數器 `j`,
  缺音檔 skip 不再留洞;補回歸測試。
- [x] 🟡 **T2-2 / T2-3 兩個一行修** — ✅ 2026-08-30:base compose 綁 `127.0.0.1`、
  editor `j.error` 加 `_html_escape`(補 XSS 測試)。

### Sprint 2 — 穩定性根源(統一抽象順帶解 timeout / model)
- [x] 🔴 **T1-2 外部呼叫補 timeout** — ✅ 2026-08-30:Gemini 走統一 client 一律帶
  `GEMINI_TIMEOUT_MS`;ffmpeg/ffprobe/轉檔走共用 runner 一律帶 `EDUSTUDIO_FFMPEG_TIMEOUT`
  (render 主路徑全遷;Track A `app.py`/CLI tools 除外,見 T3-4)。
- [x] 🟡 **T3-2 統一 Gemini client** — ✅ 2026-08-30:`core/gemini_client.make_client`
  單一入口(金鑰設定頁>環境變數,修掉 7 處 os.environ 直讀),13 檔遷移,零殘留直呼。
- [x] 🟡 **T3-3 `core/ffmpeg.py` 共用 runner** — ✅ 2026-08-30:`run_media_cmd`(timeout+
  returncode+stderr 進錯誤訊息),pipeline/video_concat/html_video/dubber/summarizer/
  tts_backend/server runner(song) 全遷。
- [x] 🟡 **T0-4 解題走 `resolve_id` + 設定頁金鑰** — ✅ 2026-08-30(`solver_model()` 呼叫時
  解析 text.fast;金鑰走統一 client)。
- [x] 🟡 **T1-3/4/5** — ✅ 2026-09-04:
  - **T1-3** 新增 `server/background.spawn`:module 級 `asyncio.Semaphore` 限並行
    (`EDUSTUDIO_MAX_CONCURRENT_JOBS`,預設 2,超過**排隊**不是拒絕)+ task 存進
    module 級 `set` 保強參照(原本 `create_task` 回傳值全丟掉,asyncio 只持 weak ref)
    + 完成移除 + 背景例外進 log。5 處裸 `create_task` 全遷;YouTube 上傳與 ideate
    掃描走 `limit=False`(純等待,不佔 render 名額)。
  - **T1-4** `JobStore._persist` 改「寫 .tmp → fsync → `os.replace`」原子換檔,
    寫一半被 kill 不再讓 job 從唯一真實來源消失。
  - **T1-5** dubber 中間檔(`audio.wav` / `dubbed_audio.wav` / `tts_*.mp3`)在
    `process_video` / `process_video_batch` 的 try/finally 清掉,成品(mp4/srt)
    以 keep set 保護;清理失敗只記 log 不影響結果。

### Sprint 3 — 安全縱深 + 輸入界限
- [x] 🟡 **T2-1 SSRF 位址過濾** — ✅ 2026-09-04:新增 `core/net_safety.assert_public_url`
  (scheme 白名單 / port 只允許 80·443 / 解析後拒 loopback·RFC1918·link-local·ULA·
  multicast·unspecified,IPv4-mapped IPv6 先還原);`core/adapters/url.py` 關掉自動
  redirect 改自己跟、**每一跳重驗**;逃生門 `EDUSTUDIO_ALLOW_PRIVATE_URLS=1`
  只放行位址那道。+49 測(全 mock DNS/requests)。已知邊界:DNS rebinding 未擋。
- [x] 🟢 **T2-4 schema 輸入界限** — ✅ 2026-09-04:`server/schemas.py` 的 `JobOptions`
  與 `JobSource` 共 30 個欄位補上界限(數值 `ge/le`、字串 `max_length`);另補
  `/api/generate` 的 `slideCount`/`panels` 與相簿 `max_select`(這三個直接決定
  「跑幾次生成」= 燒多少額度)。加漂移守衛測試:之後新增沒界限的 str/int 欄位就會紅。
- [x] 🟢 **T0-3 review_assist 覆蓋率提示** — ✅ 2026-09-04:新增
  `core.review_assist.analyze_coverage` → 逐步分類「有沒有被自動驗到」,沒驗到的給原因
  (`function` 三角/開根號 · `symbolic` 純符號 · `single_value` · `empty`);
  `write_review_flags` 一併落 `review_coverage.json`(**分檔**存,不動 flags 既有的裸 list
  格式 = 零 migration),`GET /jobs/{id}/review-flags` 加回 `coverage`,審查頁最上方顯示
  「N / M 步無法自動驗證,沒有 ⚠ 不代表算對了」。摘要文字刻意不出現「已驗證」。
- [~] 🟢 **T3-7 成本記帳分 model** — 2026-08-30 大半完成:文字費率分 model(default 退路)、
  未知 model 不再記 $0、6 個漏帳點補齊。剩:多模態「圖片輸入」token 未計入、費率待官方價校正。

### Sprint 4+ — 架構償債(長期,最高槓桿但工程最大)
- [ ] 🔴 **T3-1 反轉 core 依賴**:把邏輯搬進 `core/`、根腳本變薄 CLI(現 `core/` 是頂層腳本的空殼再匯出層)。
- [ ] 🟡 **T3-4 刪 `app.py`(Track A)+ 收斂三個並存 UI**(Track A / legacy `web/` / 官方 `frontend/`)。
- [ ] 🟡 **T3-5 拆 god 檔**:`pptx_style.py`(2536)/ `runner.py`(1468)/ `app.jsx`(3508)/ `solve_with_gemini`(203 行)。
- [ ] 🟡 **T3-6 測試結構鏡射原始碼樹 + 補零測模組**(`batch` / `publish` / `slide_ingest` / `app.py`)。
- [ ] 🟢 **T3-7 logging 收斂**(根腳本 `print`→`logging_setup`)+ CI 改 `pip install -r requirements.txt`。
- [ ] 🟢 (可選)`diagram_image_gen` / `song_images` 寫死的 `gemini-2.5-flash-image` 遷到 lite 目錄(定價已保留,現況計帳正確)。

---

## ✅ 多媒體來源擴充 — 已完成 (2026-06 ~ 2026-07,已歸檔至 ROADMAP v4.5)

> 詳見 [ROADMAP.md](ROADMAP.md) v4.5 與 [docs/CHANGELOG.md](docs/CHANGELOG.md)。

- [x] HTML 動畫（`.html` / URL）→ fps 精準 MP4（PR #87 / #88）
- [x] 缺圖簡報補圖：偵測純文字頁 → 生配圖 → **auto 智慧置入**（PR #89 / #90）
- [x] PPTX 原檔就地補圖（**原文字可編輯**）+ 含圖匯出 + 一鍵轉影片（PR #91 / #92）
- [x] 圖片模型三階層：便宜 / 中等 / 貴（PR #94）
- [x] **Google 相簿 → 相片簡報**：Picker + vision 選圖/配文 → 影片 + PPTX（PR #95）
- [ ] 🟢 相片「資訊圖卡」樣式輸出（照片 + caption 卡片）
- [ ] 🟢 Docker image 補 LibreOffice + CJK 字型（PPTX/render 正式機可用）

---

## 🌟 eduStudio 統一介面 `/app` — UI 接線補完 (2026-06-06)

> 完整盤點見 **[docs/EDUSTUDIO_UI_WIRING.md](docs/EDUSTUDIO_UI_WIRING.md)**。
> `/app` 是薄殼:每站主生成動作已接後端,但多數選項/次要動作是 placeholder。
> 後端大多現成(⚙️),多數是純前端接線。前端源碼 `infoCard/edustudio/app.jsx`。

- [x] 🔴 **視覺站選項真化**:風格/張數/格數/自訂 prompt/密度/字型/長寬比 — 真 select 餵 `/api/generate`(2026-06-06, infoCard `f273a5c`)
- [x] 🔴 **學習工具箱接線**:單字卡/寫作糾錯/會話 — 內嵌表單接 `/localization/learning/*`(2026-06-06, infoCard `c20c2ba`)
- [x] 🟡 **影片站 TaskCard 次要動作**:即時預覽→/editor、取消→DELETE、重試→重POST、發布→切站(2026-06-06, infoCard `30e9c08`)
- [x] 🟡 **影片站篩選 tab**(全部/待審/生成中)— 真篩選(2026-06-06, 同上)
- [x] 🟡 **translateGemma 配音 / 會議摘要 進影片站**:影片站「影音工具」面板接 `/localization/dub` + `/meeting/summarize`(2026-06-06, infoCard `e732136`)
- [x] 🟡 **Project 站寫入**:建 Project / 匯入來源 / 多 Project 切換 — 全可寫(2026-06-06, infoCard `7f31024`)
- [x] 🟢 **視覺站結果「加入 Project / 分享」**:`POST /projects/{id}/artifacts`,`/api/share`(2026-06-06, infoCard `d3805ee`)
- [ ] 🟢 **發布站發布語言版本**驅動多語上傳(現只是視覺)
- [x] 🟢 **source 刪除** — `DELETE /projects/{pid}/sources/{sid}` + Project 站來源列垃圾桶鈕(2026-06-06, autoSolver `0ff72e9` / infoCard `ed25ab2`)
- [x] 🟡 **成本面板真實用量統計** — `core/usage.py` 計帳子系統 + `/api/usage`,instrument 視覺/在地化 Gemini chokepoint(2026-06-06, autoSolver `6b3dfa6`/`f8907cb` + infoCard `51bf91d`)
- [x] 🟡 **review gate 逐段編輯存回** — 接既有 `PUT /jobs/{id}/draft`,前端 _path 寫回(2026-06-06, infoCard `1ff47c0`)
- [x] 🟡 **發布站多語上傳(方案 A 多語字幕軌)** — `core/caption_translate.py`(翻譯 SRT 保留時間碼)+ `core.upload_captions` + `POST /jobs/{id}/artifacts/{name}/captions`(翻譯既有 SRT → 上傳多語 caption track)+ 發布站「多語字幕」鈕。需 YouTube OAuth(未授權回 412)(2026-06-06, autoSolver `f966013` + infoCard `9a3ebde`)。方案 B(per-language 影片變體)未做,需要時另開。

**🏁 eduStudio UI 接線全部完成（2026-06-06）：** 視覺站選項/學習工具/影片站動作+影音工具/Project 寫入+source 刪除/視覺結果動作/review 存回/成本統計/多語字幕,全套 2358 tests 綠。剩 PR-M23~M25 + UI 接線。詳見 docs/EDUSTUDIO_UI_WIRING.md。

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

## 🏁 Routine closeout backlog — ✅ 完成 (iter 134-138, 2026-05-28)

> closeout 4 項 (runner.py 4 個 orchestrator 補測試) 全完成, 1580→1659 tests。
> 之後用戶 2026-05-28 給 Phase 2 新方向 (N 軸 → V 軸)。歷史細節見 git log +
> STATUS.yaml key_metrics。(原 `docs/ROUTINE_CLOSEOUT.md` 已於 2026-05-29 文件整理移除。)

---

## 🌟 Active backlog (routine 可自主推進)

> **2026-05-28 用戶指定新焦點**: 先做「內容品質 — narration 截斷治本」(N 軸),
> 做完接「動態視覺」(V 軸 = 既有 G/E 軸). **硬約束: offline-first** — routine
> 不自主呼叫 Gemini / GCP TTS 燒額度. 需打 Gemini 驗證的 (prompt 調整) 一律寫成
> proposal docs, STOP 等用戶 review 後手動跑. 細則見
> [docs/ROUTINE_ADVANCE_PROMPT.md](docs/ROUTINE_ADVANCE_PROMPT.md) Phase 2 段.

### 🎯 N 軸 — narration 截斷治本 (offline-first, 先做這個)

> **背景**: `core/narration_validator.py` (iter 79) 只「偵測+標記」過長 narration
> (治標), 刻意不自動截斷/retry. 「22%」是 2026-05-07 舊估計. 真實截斷發生在
> 字幕帶視覺層 — `build_srt` (core/srt.py) 已按標點切句但**單一 cue 無字數上限**,
> 過長句在 `_draw_subtitle_strip` (pptx_style.py) 會視覺溢出/被切. 治本走確定性
> 後處理 (離線可測), Gemini prompt 強化只寫 proposal 等用戶開額度.

按順序做 (一輪一項, 全部 offline / 不打 Gemini):

- [x] **N1 真實 baseline 測量** (Phase 2 iter 1, 2026-05-28): `tools/measure_narration_truncation.py`
  掃 `jobs/*/deck.json` (+ OUTPUT_DIR), 算 slide over-budget + per-cue 過長句統計
  + 多 threshold 分布, 輸出 [docs/narration-truncation-report.md](docs/narration-truncation-report.md).
  **真實數字: 19 deck / 2423 cue, over-cue ratio (>40 字) = 44.9%** (舊估「~22%」偏低一半),
  over-slide ratio 88%. +43 tests (1659→1702). 純離線, 復用 narration_validator + srt._SENTENCE_SPLIT.
- [x] **N2 可重現 eval fixture** (Phase 2 iter 2, 2026-05-28): 從既有 jobs 抽 4 個
  代表性 deck (lecture/quick/ultra_quick × storyteller/comedy, 含 _cover/_outro)
  做 length-preserving 匿名化 fixture 進 `tests/fixtures/narration/decks.json`
  (CJK→文 / ASCII→x / 數字→0, cue 切分與字數逐字不變 → 截斷率在 CI 無 Gemini
  逐字重現). 工具加 `make_record` 共用 helper + `load_fixture_records` +
  `--fixtures` CLI 模式. +17 tests (1702→1719). locked baseline: 4 deck / 39
  slide / 196 cue / over-cue 61 (budget 40) / over-slide 31.
- [x] **N3 確定性後處理 (治本核心)** (Phase 2 iter 3, 2026-05-29): `core/srt.py`
  加 `SUBTITLE_CUE_CHAR_BUDGET=40` + `_split_long_cue` (次級標點 ，、；：,;: greedy
  裝箱到 ≤ budget, 不硬斷詞) + `narration_to_cues` (切分單一真實來源), `build_srt`
  加 `max_cue_chars` kwarg. 量修前 vs 修後 (N2 fixture): over-cue **61 (31.1%) → 0
  (0.0%)**, max cue **105 → 40 字**, cue 196 → 265 (細). +14 tests (1719→1733).
  - [x] **N3-verify** (Phase 2 iter 4, 2026-05-29): `tools/measure_narration_truncation.py`
    的 `split_cues` 接上 `core.srt.narration_to_cues` (build_srt 同一條切分), 工具/CI
    直接量修後. DEFAULT_CUE_CHAR_BUDGET 改綁 SUBTITLE_CUE_CHAR_BUDGET; split_cues 加
    `max_cue_chars` kwarg (<=0 關閉切分 = 修前對照). N2 locked baseline 更新成修後:
    cue 196→265, over-cue **61 (31.1%) → 0 (0.0%)**, max-cue 105→40 (over-slide 31 /
    slide 39 不變). 報告從 N2 fixture 重生 (匿名化, CI 可重現): over-cue 0.0% (0/265).
    +3 tests (1733→1736). 改 3 檔 (tool + test + report).
- [x] **N4 Gemini prompt 強化提案 (GATE — 不自動跑)** (Phase 2 iter 5, 2026-05-29):
  寫 [docs/narration-prompt-tuning-proposal.md](docs/narration-prompt-tuning-proposal.md)
  — prompt diff 草稿 (兩個 scriptor prompt 加「句子層 ≤40 字 + 長句每 ~20 字逗號」cue
  層約束, 補 N3 切不動的「無次級標點長句」缺口 + 強化 over-slide 79.5% 的 slide 層) +
  A/B 驗證流程 (跑 Gemini 產 A/B deck → `--cue-budget 0` 量源頭 over-cue + over-slide).
  **STOP 等用戶 review + 手動開額度驗證**. 0 production code 改動 (純 doc). offline-first.
  - [x] **§5 配套 counter** (Phase 2 iter 6, 2026-05-29): `tools/measure_narration_truncation.py`
    加 `is_uncuttable_long_cue` + `uncuttable_long_count` (長度 > `SUBTITLE_CUE_CHAR_BUDGET`
    且 `_CLAUSE_SPLIT` 切不出 >1 段 = N3 切不動的殘留, 復用 core.srt 不漂移). 全域摘要 +
    分組表 + 報告各加一列. 配 `--cue-budget 0` 量 Gemini 源頭, 修後等於 over-cue 殘留.
    fixture locked 0 (4 deck 長句剛好都有逗號 = 缺口 A「運氣」實證). +12 tests (1736→1748).
    純離線, 改 3 檔 (tool + test + report). **N 軸全收尾, 下一輪接 V 軸 V1 (offline)**.

### 🎵 SONG 軸 — 歌曲 → AI 生圖 MV 影片 (第 4 條 track, 2026-06-03 用戶拍板正式做)

> **決議 (2026-06-03 互動 session)**: 新增第 4 個 `source_type = "song"` — 歌曲音檔
> (AI 產) + 純文字歌詞 (無 LRC) → forced alignment 對齊時間軸 → 逐段 AI 生圖 → MV
> 影片 → YouTube。forced alignment 走**方案 2 (Demucs 分人聲 + WhisperX word-level +
> 手動 review 微調層)**, 畫面走 **AI 生圖逐段配**。完整設計見
> [docs/SONG_MV_TRACK_RFC.md](docs/SONG_MV_TRACK_RFC.md)。
>
> **GATE**: ① 新 dep demucs + whisperx + torch(CUDA) — 方案 2 已授權, M0 先確認 4080
> 環境再實裝 ② Gemini image 額度 (跟 V2 同開關)。offline-first 不變: 對齊/生圖碰
> 額度的部分寫 proposal + STOP, 不自主燒額度。

- [~] **M0 POC (spike)**: 裝 demucs + whisperx 確認 4080 CUDA 跑得動 + 手動歌詞/時間軸
  1 首歌走通到 mp4 (純色/單圖背景, 先不接生圖, 驗渲染 + 歌曲音軌 + 歌詞字幕)
  - dep 清單已備: `requirements-song.txt` (demucs + whisperx, 獨立檔不進主 requirements
    避免 CI 裝 torch; 含 CUDA wheel 安裝順序註解 + 2026-06-04 M0 spike 實測結果)。
  - [x] **環境 spike** (2026-06-04): CUDA torch (cu124) / demucs / whisper 轉錄全通;
    whisperx **自動對齊**卡依賴地獄 (whisperx 3.8.6 stack vs torch 2.6 互斥) → **降 M1**
    (M0 用手動時間軸不受影響)。實測記進 requirements-song.txt。
  - [x] **M0a 渲染骨架 code** (2026-06-04, offline, RFC §8 授權): `core/song_render.py` —
    `is_song_schema` type guard (track_type==song, 硬規則 #9) + `song_segments_to_srt`
    (對齊時間軸 → SRT, **繞過** narration_to_cues 字數切分, 無效 segment 靜默跳過 +
    重編號) + `build_song_mv_cmd` (ffmpeg 純色背景 + 燒歌詞 + 歌曲音軌, 歌詞置中大字,
    不真跑). +18 tests (1990→2008). 改 2 檔 (core/song_render.py + tests/test_song_render.py).
  - [~] **M0b 本機驗收**: helper `tools/song_mv.py` 完成 (2026-06-04, offline) — 讀
    song.json → is_song_schema 驗證 → song_segments_to_srt 寫 .srt → build_song_mv_cmd
    跑 ffmpeg → mp4; `--dry-run` 不跑 (沒 ffmpeg/測試用); audio_path 相對 song.json 解析;
    Windows 冒號用 cwd+basename 避; ffmpeg 缺/失敗各自 return code. +12 tests (2008→2020).
    改 2 檔 (tools/song_mv.py + tests/test_song_mv.py). **待劉老師真跑**: 寫一首歌
    song.json (手填 segments 時間軸, whisper phrase 時間戳當起點) + 備 audio →
    `python tools/song_mv.py song.json` → 肉眼驗 mp4 渲染+音軌+字幕對齊。
- [ ] **M1 對齊子系統**: Demucs + WhisperX 自動對齊出 song.json 時間軸 + review UI 微調層
- [~] **M2 生圖子系統**: 逐段 Gemini 生圖 + 風格一致性 (統一 style suffix/seed) + ken burns
  - [x] **生圖層 (2026-06-04)**: `core/song_images.py` `build_image_prompt` (歌詞語意 +
    統一 visual_style + 風格 suffix, 0 API; 既有 image_prompt 優先 idempotent) +
    `generate_segment_image` (複用 diagram_image_gen 的 gemini-2.5-flash-image 呼叫, GATE);
    執行包 `tools/gen_song_images.py` 同 gen_icon_svgs 安全模式 (預設 dry-run 印 prompt
    不燒額度, `--execute` 才生圖 + 寫回 song.json image_path + **reviewed=false 停 review**,
    不自動標 reviewed=true / 不自動 commit). +13 tests (2039→2052). 改 3 檔.
  - [ ] **真生圖 (GATE)**: 劉老師開 Gemini image 額度 + song.json 填 visual_style →
    `python tools/gen_song_images.py song.json --execute` → 逐張 review → reviewed=true.
  - [x] **ken burns 渲染串接 (2026-06-04)**: `build_song_mv_kenburns_cmd` (core/song_render.py)
    — 每 segment 一張圖 zoompan 緩慢推鏡 (居中 zoom in) 撐該段時長 → concat → 燒歌詞 +
    歌曲音軌。`tools/song_mv.py` 偵測「每 segment 都有 image_path」→ 走 ken burns, 否則退
    M0 純色; 真跑前檢查圖檔存在 (缺 → 提示先跑 gen_song_images)。+8 tests (2052→2060)。
    **假設 segments 連續無 gap** (concat 是相對串接); 前奏/間奏 gap 對齊精修待後續。
    劉老師生圖 OK 後可直接 `python tools/song_mv.py song.json` 出完整有畫面 MV。
- [~] **M3 整合**: 接進 server flow (建 job → ingest → review → render → YouTube) + web UI。
  跨 server/runner/schemas/jobs/youtube/web 多檔, 拆多 PR。
  - [x] **M3a source_type 註冊 + review policy (2026-06-04)**: schemas.py `SONG = "song"`
    enum + jobs.py `_resolve_default_review` song → True (對齊+生圖 prompt+生圖全 AI 估值,
    同硬規則 #1 強制 review)。+1 test (2060→2061)。
  - [x] **M3b ingest_song (2026-06-04, 劉老師拍板選 B 自包含)**: runner `_run_ingest`
    dispatch 加 SONG 分支 → `_run_ingest_song` 讀 song.json, 複製 audio (→ song<ext>) +
    逐段圖 (→ images/<原名>) 進 jobs/<id>/, deck.json 內路徑改寫成相對 → job 自包含可搬。
    純檔案搬運 0 Gemini; 缺檔 graceful 略過不炸; 非 song schema → ValueError。+8 tests
    (2061→2069, 含「砍來源後 job dir 仍完整」證自包含)。
  - [x] **M3c render_song** (2026-06-04, routine 自主, 純 offline 本機 ffmpeg):
    `_run_render_inner` `deck = json.loads(...)` 後加 `is_song_schema` early-return →
    新 `_run_render_song` (繞 v0/render_video TTS pipeline): song_segments_to_srt 寫
    job_dir/song.srt → 每 valid segment 都備圖且檔案存在走 build_song_mv_kenburns_cmd,
    任一缺圖退 build_song_mv_cmd 純色 (不混搭) → `subprocess.run(cmd, cwd=job_dir)` →
    artifacts/song.mp4。空/全無效 segment + 缺 audio_path → ValueError; returncode!=0 →
    RuntimeError; ffmpeg 不存在 → FileNotFoundError 清楚訊息。section_id 忽略 (整首單一
    影片)。state 由 _run_render_phase 收尾。+15 tests (2069→2084, monkeypatch subprocess
    不真跑 ffmpeg)。改 3 檔 (server/runner.py + tests/test_runner_render_song.py + TODO/STATUS)。
  - [ ] ~~**M3c render_song**~~ (原 spec, 已實作如上):
    **接入點**: `server/runner.py` `_run_render_inner` (line ~535, `deck = json.loads(...)`
    之後、`if "sections" in deck` 判斷之前) 加 early-return 分流:
    `from core.song_render import is_song_schema; if is_song_schema(deck): return await
    _run_render_song(store, rec, deck, section_id=section_id)` — **不碰既有 exam/deck 分支**。
    **新 `_run_render_song(store, rec, deck, *, section_id=None)`** (繞過 v0/render_video
    TTS pipeline):
    · `job_dir = store.deck_path(rec.id).parent`; `artifacts_dir = store.artifacts_dir(rec.id)`;
      artifacts_dir.mkdir。
    · `srt = song_segments_to_srt(deck["segments"])`; 空 → raise ValueError。srt 寫
      `job_dir / "song.srt"` (cwd 設 job_dir, subtitles filter 用 basename 避 Windows 冒號)。
    · audio = `deck["audio_path"]` (ingest 已改寫成相對 job_dir, 如 "song.mp3")。
    · 每 valid segment (用 `_valid_segment`) 都有 `image_path` (相對 job_dir) → ken burns:
      `image_durs = [(s["image_path"], s["end"]-s["start"]) ...]` →
      `build_song_mv_kenburns_cmd(image_durs, audio, "song.srt", out_stem, ...)`; 否則
      `build_song_mv_cmd(audio, "song.srt", out_stem, ...)` 純色。
    · `out_stem = str(artifacts_dir / "song")` (build 補 .mp4 → artifacts/song.mp4)。
    · `subprocess.run(cmd, cwd=str(job_dir))`; returncode !=0 → raise; FileNotFoundError
      (無 ffmpeg) → raise 清楚訊息。
    · section_id 忽略 (song 整首單一影片, 不支援單章 render)。state DONE 由 _run_render_phase
      收尾 (此函式只產 artifacts, 比照 _run_render_inner 不自己 set state)。
    **測試** tests/test_runner_render_song.py: monkeypatch `subprocess.run` (routine 環境
    未必有 ffmpeg, 不真跑) 驗 — ken burns 模式 (全段有圖→cmd 含 zoompan) / 純色模式
    (缺圖) / srt 真寫出 / cwd=job_dir / 空 segment raise / ffmpeg 失敗 raise /
    _run_render_inner 路由 song 到 _run_render_song。≤3 檔 (runner.py + 測試 + TODO/STATUS)。
  - [x] **M3d youtube meta song 分支** (2026-06-04, routine 自主, offline): core/youtube.py
    auto_youtube_meta 最前面加 is_song_schema 分流 (在 deck/exam 之前, song 無 sections/
    problems 會誤走 problems 路徑) → 新 _song_youtube_meta: title=song_title, description=
    歌詞章節 (每段首句 + 對齊好的絕對 start 時間, 繞字數估算)。章節用 _song_chapter_durs
    把絕對 start 轉成段間距餵既有 _build_chapter_lines (累積回到絕對時間戳不漂移), 首段非 0
    補「🎵 前奏」章節 (YouTube 首章須 0:00)。category 用 10 (Music) 非教學 27; tags 加 song
    條目。+15 tests (2084→2099)。改 2 檔 (core/youtube.py + tests/test_youtube_helper.py)。
  - **M3e web UI** (拆 3 小 iter, 守 ≤3 檔):
    - [x] **M3e-1 types 基礎** (2026-06-04, routine 自主, offline, 動 web/ 跑 tsc):
      types.ts SourceType 加 'song' + SongDeck/SongSegment interface (對應 song.json:
      track_type/song_title/audio_path/visual_style/segments[id,start,end,lines,image_path,
      image_prompt,reviewed]) + isSongDraft type guard (比照 core.song_render.is_song_schema,
      track_type==='song' && segments list, 與 isExamDraft/isDeckDraft 不互撞) + Draft union
      加 SongDeck。SourceBadge.tsx SOURCE_META 加 'song' 條目 (唯一 exhaustive Record<SourceType>,
      不加 tsc 紅)。tsc 綠 + 2099 pytest 不變。改 2 檔 (types.ts + SourceBadge.tsx + TODO/STATUS)。
    - [x] **M3e-2 CreateJobForm** (2026-06-05, routine 自主, offline, 動 web/ tsc 綠): source_type
      下拉加 `song` 選項 + song 走 **path-only → song.json** 輸入流 (PATH_ONLY 加 'song';
      build song.json 需離線對齊 GATE, 不是 web 表單做的, 故指向已產好的 song.json,
      ingest_song 以其所在目錄解析 sibling audio/圖)。path 區 song 專屬提示 + 強制 review
      說明 banner。`isSong` 收斂面板: 隱藏長寬比/解析度 + 講者頭像 + 整排渲染 checkbox
      (字幕/intro/outro/mock 對 MV 分流全 no-op, review 後端強制硬規則 #1) → 比照 exam
      收斂。tsc --noEmit 綠 + 2110 pytest 不變 (0 Python)。改 1 檔 (CreateJobForm.tsx)。
    - **M3e-3 JobEditor song review** (圖預覽需後端 endpoint, 故再拆兩半守 ≤3 檔):
      - [x] **M3e-3a song 圖預覽 endpoint** (2026-06-05, routine 自主, offline): song 逐段圖
        存 jobs/<id>/images/<name> (M3b 複製), 既無 endpoint 可預覽 → reviewer 看不到 AI
        生圖無法依硬規則 #1 標 reviewed。server/routes/jobs.py 加 GET /jobs/{id}/images/{name}
        (鏡像 download_figure: 同 path-traversal 防呆 ../ \ / → 400, target 限 images/ 下,
        缺檔/目錄 → 404)。+6 tests。改 2 檔 (jobs.py + tests/test_song_images_route.py)。
      - [x] **M3e-3b JobEditor SongReviewPane** (2026-06-05, routine 自主, offline, 動 web/ tsc):
        JobEditor isSongDraft 分流新 SongReviewPane — 逐段卡片顯示 [start–end] (mm:ss) + dur +
        歌詞行 + image_path 圖預覽 (api.songImageUrl 剝 images/ 前綴傳 basename 接 M3e-3a
        endpoint, 子目錄路徑回 null 對齊後端防呆) + reviewed checkbox (updateSegment mutator
        immutable 換 segment, setDirty → 上方 💾 Save 走既有 saveDraft, awaiting_review 後端
        強制不繞)。header emoji 🎵 + song title/subtitle (reviewed N/total) + 隱藏 outline 鈕。
        無生圖段顯「渲染退純色」, end≤start 標 ⚠ 渲染跳過 (對齊 _valid_segment)。tsc --noEmit
        綠 + 2229 pytest 不變 (0 Python)。改 2 檔 (api.ts + JobEditor.tsx)。**M3e 全完成 → SONG
        M3 (M3a~M3e) 收尾。**
- 對齊策略 (WhisperX ASR→文字對齊 vs align() 強制對齊已知歌詞) 在 M0 spike 拍板

### ✨ 新功能 backlog (2026-06-03 用戶挑選進場)

> 互動 session 用戶從建議清單挑這 4 個進 backlog。多數可接既有結構, 不需 Gemini 額度
> 的先做 (offline-first)。

- [x] **LaTeX 公式渲染 (backend)** (🔴 高, 教學剛需) — **完成 (2026-06-04, iter 18~21)**:
  劉老師授權 GATE 解鎖 (拍板後端 A matplotlib mathtext + 同意 matplotlib 進核心依賴)。
  端到端通: deck.json `slide.formula` → normalize/flatten 透傳 → `render_latex_to_png`
  (mathtext → 透明 PNG) → `compose_formula` (複用 compose_icons 定位/paste) → 三大
  renderer 4 seam 疊放。GATE 緣由 + 後端選型見
  [docs/latex-formula-rendering-proposal.md](docs/latex-formula-rendering-proposal.md)。
  - iter 18: core/formula_render.py render_latex_to_png + matplotlib 進 requirements + CI (+12)
  - iter 19: core/deck.py slide.formula 透傳 (normalize + 兩 flatten 轉換) (+6)
  - iter 20: compose_formula helper (render → tempPNG → compose_icons 複用) (+9)
  - iter 21: pipeline.py (Blackboard/Slide 2 layout) + pptx_style.py (4 路 layout) 接 (+6)
  - **剩 (非本輪)**: ① review UI 讓使用者逐 slide 編 formula (前端 web/, 另開) ②
    auto-formula (Gemini 從 narration 偵測公式自動建議) = GATE 需額度, 不可繞 require_review。
- [x] **YouTube 自動章節** (🔴 高, 近零成本高 CP) (2026-06-04): deck section 結構 → YT
  description 時間軸章節格式 (`0:00 章節名`)。實作在 `core/youtube.py` (Track B 真正組
  description 的地方, 非 publish.py CLI)。`auto_youtube_meta` 原只認 exam schema
  (problems/steps), deck schema (repo/document/url 的 sections/slides) 走 problems 必空 →
  description 全空無章節。加 `_is_deck_schema` type guard (硬規則 #9) + `_deck_youtube_meta`:
  artifact stem 對到 section.id → 單章影片章節=slides; 對不到 (final.mp4 整份) → 章節=各
  section (該章 slides 旁白估算秒數總和)。抽 `_estimate_narration_seconds` +
  `_build_chapter_lines` 共用 (exam 路徑改用後不變)。+15 tests (1814→1829)。改 2 檔。
- [~] **雙語字幕** (🟡 中): 既有 SRT → 翻英/日雙語軌。翻譯需 Gemini/翻譯 API → GATE
  寫 proposal 等用戶開額度; SRT 雙語合併格式 + 渲染是 offline 可先做。
  **proposal 已寫 (2026-06-04, routine)**: [docs/bilingual-subtitle-proposal.md](docs/bilingual-subtitle-proposal.md)
  — 列 3 個架構決策 (格式 A 交錯/B 雙軌/C ASS, 建議 B; 字幕帶 180px 溢出約束; cue 對齊)
  + offline 可先做段 (拍板 B 後 routine 可自主做 build_bilingual_srt_tracks helper + schema
  透傳, 純離線不碰額度)。
  **劉老師 2026-06-04 拍板**: 格式 **B 雙獨立軌** / 翻譯後端 **本機 Ollama translategemma**
  (本機推論不燒雲端額度 → 翻譯不再是 GATE) / 第二語言軌**跳過 review** (中文主軌 require_review
  不動)。
  - [x] **SRT 雙軌組裝層** (2026-06-04): `core/srt.py` `build_bilingual_srt_tracks` —
    同組 durations 出 `{primary, secondary}` 兩條獨立 SRT 軌 (格式 B), step 邊界時間天然
    對齊 (build_srt per-step 切, 沒 narration 的 step 仍累加 t → 不需逐 cue 對齊); 無
    secondary 欄位的舊 deck → secondary 空字串向後相容。+6 tests (2020→2026)。
  - [x] **翻譯層 (本機 Ollama translategemma)** (2026-06-04): `core/translate.py` —
    `translate_text` / `translate_steps` 打本機 Ollama `/api/generate` (標準庫 urllib,
    **不加 pip dep**) 產 `narration_secondary`; 空 narration 跳過 + 已有 out_field 跳過
    (idempotent, 不覆蓋人工修過的) + 不就地改傳入 dict; Ollama 沒開/逾時 → TranslateError
    含修復指引。+13 tests (2026→2039, monkeypatch 不真打 HTTP)。
    **✅ 劉老師本機實測通過 (2026-06-04)**:「你好，這是材料力學的應力分析。」→
    "Hello, this is a stress analysis in mechanics of materials." — 無多餘文字、術語正確、
    格式乾淨, 預設 `_build_prompt` 不需調。VRAM 排 render 前批次跑完卸載避與 TTS/demucs 搶 4080。
  - [ ] **schema 透傳 + 渲染燒第二軌 / YouTube 多軌上傳**: narration_secondary 進 schema
    flatten; 渲染燒一軌 + publish.py captions.insert 上第二軌 (碰 YouTube OAuth = GATE)。
- [ ] **學生提問 → RAG → 解答影片** (🟢 探索, 戰略價值高工程重): 串 RAG 研究
  (Kiwi/Christian) + EdTech 論文 + 課程網站整合。先寫 RFC 拆子系統, 不急著動 code。

### 🖼️ CARD 軸 — 資訊圖卡 → 講解影片 (新 source_type, 🟡 中, 2026-06-03 用戶提)

> **需求 (劉老師 2026-06-03)**: 常有「把某主題/章節 → 1~5 張資訊圖卡」的需求。希望
> 拿那幾張圖 **+ 它們原本的生圖提示詞** 當影片內容 → AI 轉口述旁白 → 出圖卡講解影片
> (配 SRT, 走既有 TTS/YouTube 通道)。
>
> **關鍵發現 (省一半工)**: infoCard poster service 已現成 —
> `core/infocards/poster_service.py` `generate_poster()` 回 `{imageUrl, prompt}`,
> 「圖卡 + 原始生圖 prompt」本來就一起出。原料齊備。
>
> **架構定位**: 比 SONG 軸**簡單** — 圖卡是靜態圖、每張配一段旁白 → **走既有 deck/slides
> 的 TTS+SRT+render pipeline**, 不需要 SONG 的 forced alignment (無歌詞時間軸問題)。
> 本質上是「slides_pdf 流, 但每張 slide = 一張全幅資訊圖卡」。新東西只有「prompt→narration」
> 那一步 + 全幅圖渲染 mode。
>
> **建議流程**:
> 1. 主題/章節 → infoCard poster_service 產 1~5 張卡 (已有 imageUrl + prompt)
> 2. (卡圖 + 該卡生圖 prompt + 主題) → Gemini/Claude 產逐卡旁白 → **強制 review (硬規則 #1,
>    AI 產 narration)**, 停 awaiting_review
> 3. flatten 成 deck-like schema: 每「slide」= 1 張卡全幅背景 + narration (複用 `core/deck.py`)
> 4. 既有 pipeline: TTS → SRT → render → mp4 → YouTube (幾乎全複用)
>
> **複用 vs 新建**:
> - 複用: poster_service / TTS / srt.narration_to_cues / publish.py / review gate / Library
> - 新建: ① source_type 註冊 (名稱待定: `infocard` / `card_video`?) ② prompt→narration 生成層
>   (GATE: 碰 Gemini/Claude 額度, offline-first 寫 proposal 等開額度) ③ 全幅圖渲染 mode
>   (SlideRenderer 已有 full/split-left, 全幅背景圖可能要小調) ④ type guard `is_card_schema`
>   (硬規則 #9) ⑤ web UI: 觸發 + 逐卡 narration review
>
> **開放問題 (待拍板, 不自行假設)**:
> 1. source_type 命名 + 是否獨立 track 還是掛在 infoCard studio 流程下
> 2. 圖卡來源: 一律 infoCard 現生? 還是允許上傳已有圖卡 + 手填 prompt?
> 3. 一張卡一段旁白 (≤5 段短片), 還是允許一張卡多段 (像 slides 逐 bullet)?
> 4. 轉場/動態: 純切換 / ken burns 推鏡 (SONG 軸 `build_song_mv_kenburns_cmd` 可借)?
>
> **下一步**: 等劉老師對上述 4 點拍板 → 寫 `docs/CARD_VIDEO_RFC.md` 拆 PR (比照 SONG M0~M3)。
> offline-first: 渲染/schema/type guard 可先做, prompt→narration 碰額度寫 proposal STOP。

- [ ] **CARD-0 設計拍板**: 上述 4 個開放問題, 劉老師選定後寫 RFC。

### 📚 EBOOK 軸 — 電子書輸出 EduForge (🔴 大功能, v5.0, 2026-06-05 用戶提)

> **需求**: 在不動 video pipeline 前提下, 加**第二條輸出管道** — 同一份教材 → 多版本
> EPUB 電子書 + 練習/測驗題 + 教學簡報 .pptx。Job 狀態機加 `output_type` 概念。
> 完整規格 (模組/API/UI/實作順序/開放問題) 見 **[docs/EBOOK_OUTPUT_RFC.md](docs/EBOOK_OUTPUT_RFC.md)**
> (原 issue `D:\Dropbox\ISSUE_ebook_output.md` 已落地進 repo)。
>
> **新模組**: `core/versioner.py` (Claude 多版本改寫) / `epub_builder.py` (ebooklib 打包) /
> `quiz_gen.py` (出題) / `pptx_export.py` (接 pptx-jliu-style) + `server/routes/ebook.py`。
> **硬規則**: 計算題/AI 內容仍走 `require_review=True` (#1); 動 server/runner/schemas 跑 pytest (#7);
> type guard dispatch output_type (#9)。
>
> **估**: 3~4 週 (Phase A 核心 2w / B 題庫 1w / C 簡報+UI 1w)。**待拍板問題見 RFC §9**
> (版本選擇 UI / 封面圖 / EPUB 2 vs 3 / 公式渲染 — repo 已有 formula_render 可複用 /
> 中文內嵌字型 / 改寫出題用 Claude vs Gemini)。新 dep: `ebooklib`, `anthropic`。

- [ ] **EBOOK-0 設計拍板 + 排程**: RFC §9 六個開放問題拍板 + 決定何時插隊 (這是 v5.0
  大功能, 與 SONG/CARD 軸排序)。

### 🎬 V 軸 — 動態視覺 (N 軸全完成後啟動)

> 接既有 G/E 軸 RFC (見下方階段 2「G. 動態視覺素材」+ CONTENT_QUALITY_ROADMAP
> E 軸). offline 可做的先做; 需 Gemini SVG 產生 (E2-2) / 新 dep cairosvg (E1-3)
> 的一律 STOP 寫 proposal 等用戶.

- [x] **V1 (offline)**: E1-5 / E2 既有 slice 補測試 + icon_picker / image_frames
  parser 強化 (不需 Gemini / 新 dep 的部分) — V1a~V1d 全完成 (Phase 2 iter 7~12)
  - [x] **V1a icon_overlay 尺寸/比例路徑補測試** (Phase 2 iter 7, 2026-05-29):
    既有 icon_overlay 測試 icon 全是 256×256 正方形, aspect-ratio 縮放
    (`target_h = icon_h * target_w/icon_w`) 與 size_ratio 上界 clamp (0.50) 從沒被
    驗過. +6 tests — 上界 clamp / 預設 0.10 / 非數值 size_ratio 靜默 skip + 不擋同
    list 其他 icon / 寬 icon (2:1) 高按比例縮 / 高 icon (1:2) 寬鎖 size_ratio. 純
    PIL pixel 驗, 0 production code 改動. 1748→1754. 改 1 檔 (tests/test_icon_overlay.py).
  - [x] **V1b icon_picker manifest 優先序 + image_frames require_file_exists 透傳補測試** (Phase 2 iter 8, 2026-05-29):
    icon_picker docstring 明定『結果順序 = manifest 出現順序』且 max_icons 截斷依此序,
    但既有測試用 set 沒鎖順序 / 截斷依 manifest 序; manifest 缺 icons key fallback 沒測.
    image_frames select_frame / terminal_frame 的 require_file_exists 透傳給 valid_frames
    從沒驗過. +7 tests (icon_picker 3 + image_frames 4). 純測試 0 production 改動.
    1754→1761. 改 2 檔.
  - [x] **V1c SlideRenderer icon 疊圖整合補測試** (Phase 2 iter 9, 2026-05-29):
    SlideRenderer (pipeline, iter 102) 是最早接 E2-5 compose_icons 的 renderer,
    但 iter 103 整合測試只補了 Blackboard + Pptx, SlideRenderer 自己兩 layout
    (full / split-left) 從沒被直接整合測. +5 tests (TestSlideRendererIntegration) —
    full/split-left 各疊 icon 渲染 / 無 overlay NoOp / bottom-right icon 用
    canvas_h=900 定位 (y=700 在 icon 內證非 1080) / split-left 字幕帶不被 icon 污染.
    純整合測試 0 production 改動. 1761→1766. 改 1 檔 (tests/test_icon_overlay.py).
  - [x] **V1d icon-suggestions / image-frames endpoint 序列化 + 過濾契約補測試** (Phase 2 iter 12, 2026-05-29):
    icon-suggestions endpoint 親手組的 payload dict (jobs.py:179-193) 的 `position` /
    `size_ratio` 兩欄沒被既有 happy path 鎖過 (只測 key/matched_keyword/domain/file_exists/icon),
    重構漏掉前端疊圖位置/大小就錯但測試不紅; max_icons ge=1 le=20 只測界外 (0/21→422)
    沒測界內 (1/20→200). image-frames endpoint 既有 query-param 測試是『全存在』或『全缺檔』
    兩極端, 沒測混合 (缺檔被 valid_frames 踢但存在的保留, terminal 取存在裡最大) /
    亂序輸入 terminal 仍取 display_ratio 最大 (非陣列末筆). +5 tests (icon 3 + frames 2).
    純 endpoint 序列化/過濾契約, 0 production 改動. 1766→1771. 改 2 檔
    (tests/test_icon_suggestions_endpoint.py + tests/test_image_frames_endpoint.py).
    **V1 (offline) 收尾.** 下一輪 = V2 (E2-2 Gemini SVG) / V3 (E1-3 cairosvg) GATE 需用戶開額度/新 dep STOP.
- [x] **V2 (E2-2)** — **完成 (2026-06-04, 劉老師產 SVG + routine 驗收入庫)**: 25 個扁平
  SVG icon (風能/控制/材力各 5 + generic 10) 全進 `assets/icon_library/{wind,control,mechanics,generic}/`,
  manifest 25 entry 對齊。驗收完整性鎖 `tests/test_icon_library_complete.py` (每 icon 檔存在 +
  合法 SVG + viewBox 256 風格 + 欄位合法 + 雙向無孤兒檔 + pick_icons 補檔後真命中, +128 tests
  1862→1990); 順帶更新 test_icon_picker 2 個「SVG 還沒產」前提失效的測試。proposal:
  [docs/dynamic-visual-v2-v3-proposal.md](docs/dynamic-visual-v2-v3-proposal.md).
  - [x] **V2 執行包 (offline)** (2026-06-04): `tools/gen_icon_svgs.py` — 讀 manifest 25
    icon → 內建 VISUAL_DESC 視覺描述 + 統一風格規範 (viewBox 256 / #1e3a2e / #ffd96b /
    無文字 label) 組 per-icon prompt。**SVG 用文字模型 gemini-2.5-flash 產 (不吃 image
    額度)**。預設 dry-run (印 prompt 不打 API), `--execute` 才呼叫 Gemini + 落檔, 產完印
    人工 review checklist + 不自動 commit (硬規則)。+20 tests (完整性鎖 VISUAL_DESC==manifest
    / prompt 含風格+語意 / extract_svg / dry-run)。劉老師開額度後跑 `--execute` → review → 補
    25 SVG → routine 自動接 V2 驗收測試 (tests/test_icon_library_complete.py, proposal §驗收)。
- [ ] **V3 (GATE)**: E1-3 flow_diagram SVG + cairosvg 渲 frame — 新 pip dep + 行為
  refactor. 見上方同一份 proposal. 建議先做完 V2 再評估 (或退候選 C 純 Pillow 不加 dep).

### 🎙️ S 軸 — 語音 voices UI 修補 (offline, 劉老師 2026-05-29 授權 routine 自主)

> **背景**: 2026-05-29 互動 session 查 TTS 現況時發現 voices route 有真 bug —
> `server/routes/voices.py` 的 `_read_current_voice` / `_write_current_voice` 只認
> edge / f5 兩種 backend, 完全沒有 google 分支。後果: 若 `tts_config.json` 的
> `backend` 是 google, UI 會顯示**錯的** current voice (掉成 edge 第一個「小陳」),
> 且使用者在 UI 選任何聲音都會把 google 設定覆蓋掉 → 「Google 在 UI 上管不到、
> 還會騙人」。系統文件 (CLAUDE.md / GOOGLE_TTS_SETUP) 宣稱「預設 google」但 UI 接不住。
>
> **授權**: 劉老師明確授權 routine 自主修這組 (解除硬規則 #3「修 bug 先討論」gate)。
> 全 offline、純 code、低風險、有測試。一輪一項, 按順序做。
>
> **預先定好的設計約束 (routine 照做, 不用自己決策)**:
> - google voice id 格式 = `google:<voiceName>`, 例 `google:cmn-TW-Wavenet-A`
>   (跟 `f5:teacher` 的 prefix 風格一致)。
> - google voice 清單取 docs/GOOGLE_TTS_SETUP.md: cmn-TW-Wavenet-A (女, 預設) /
>   -B (男) / -C (男, 深沉)。
> - 不動 `tts_config.json` 內容本身 (gitignored, smoke test 會改); 只改 route 邏輯 + 測試。

- [x] **S1 voices route 認得 google backend (修顯示斷層)** (2026-05-30): `_read_current_voice`
  加 google 分支 (backend==google → 回 `google:` + cfg["google"]["voice"], 缺 voice 退
  預設 cmn-TW-Wavenet-A); `_write_current_voice` 加 google 分支 (id 以 `google:` 開頭 →
  backend=google + cfg.setdefault("google",{})["voice"] = prefix 後字串, 不動 f5/edge 區塊)。
  google: 走 prefix 命名空間驗證 (不要求在 VOICE_IDS, 因 GCP 合法 voice 名很多, 預設清單
  S2 才補)。+5 tests (TestGoogleBackend: read / read 缺 voice 退預設 / write 切 backend /
  write 保留 edge+f5 區塊 / round-trip)。1777→1782。改 2 檔 (voices.py + test_voices.py)。
- [x] **S2 VOICES 清單加 Google 選項** (2026-05-30): VOICES list 加 3 個 google entry
  (cmn-TW-Wavenet-A 女預設 / B 男中性 / C 男深沉), label 標「(Google 雲端 TTS, 需 GCP
  額度)」, VOICE_IDS 自動含。順帶收緊 `_write_current_voice`: S1 曾為 google: prefix 開
  命名空間放行 (清單未補時的過渡), S2 補進預設清單後改回一律走 VOICE_IDS 白名單 → 未知
  google id 也 400 (符合驗收)。read 仍如實顯示 cfg 裡清單外的 GCP voice (只是 UI 下拉限
  3 個預設)。+8 tests (list 3: 3 google / 進 VOICE_IDS / label 標額度; endpoint 5: GET
  含 3 google / POST 各 google 成功套用 / 未知 google 400)。1782→1790。改 3 檔
  (voices.py + test_voices.py + test_voices_route.py 的 six→nine)。
- [x] **S3 sample 試聽對無預錄 sample 的 voice 優雅降級** (2026-05-30): VoiceInfo schema
  加 `has_sample: bool`, list_voices 以 `(VOICE_SAMPLE_DIR / v["sample"]).exists()` 回填。
  google voice 無 voices/samples/*.mp3 → has_sample==False, 前端據此 disable 試聽鈕優雅
  降級 (sample endpoint 仍維持 404 行為不動)。+4 tests (TestHasSample: 空 dir 全 False /
  google 永遠 False (即使 edge+f5 鋪了) / edge+f5 鋪檔則 True / 逐 voice 獨立判斷) +
  shape test 加 has_sample 欄。1790→1794。改 2 檔 (voices.py + test_voices_route.py)。
  (前端 web/ disable 試聽鈕另開小項, 後端契約先就緒。)

> **S 軸 (S1→S3) 全完成 → 回 wind-down**。其餘大目標 (GitHub issue #12 P0 穩固化 / #13 V2-V3 /
> #14 發佈擴展) 多需架構決策 / Gemini 額度 / 用戶操作, routine 不自主碰, 等劉老師
> 互動 session 推或拆出新 offline 子任務。B1/B2 動態尺寸 (docs/B1_B2_DYNAMIC_DIMENSIONS_RFC.md)
> 卡在「等用戶選 Option A/B/C」架構決策, 選定後才好拆。

---

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
  - [x] **E2-2**: 25 個扁平 SVG icon 已入庫 (2026-06-04, 劉老師產 + routine 驗收, 見上方 V2 段)
  - [x] **E2-3**: `core/icon_picker.py` keyword grep 模組 (iter 99)
  - [x] **E2-4**: schema 加 `slide.icon_overlay` (iter 100)
  - [x] **E2-5**: slide_renderer alpha_composite 疊 icon (iter 102 SlideRenderer 兩 layout; iter 103 擴 BlackboardRenderer + PptxStyleRenderer 4 路 layout — 三大 renderer 全覆蓋)
  - [x] **E2-7**: +8~12 tests (iter 102 +19 含 NoOp/SVG/Position/Size; iter 103 +8 含 BlackboardRendererIntegration / PptxStyleRendererIntegration)
  - [~] **E2-6**: review UI 自動建議 icon 勾選列 (iter 106 backend slice `suggest_for_deck`; iter 107 API endpoint `GET /jobs/{id}/icon-suggestions` 包 suggest_for_deck — 含 require_file_exists / max_icons query params 跟 IconMatch JSON 序列化. 前端 UI 待後續 iter)
  - [x] **E1-1**: schema 加 `slide.image_frames` (iter 101)
  - [~] **E1-2**: slide_renderer 偵測 frame list 走多 PNG 順序 (iter 104: parser + SlideRenderer 兩 layout 接 terminal frame fallback; 真 frame 序列拆 step + build_clip refactor 待 E1-3)
  - [ ] **E1-3**: Gemini flow_diagram SVG prompt + cairosvg 渲 frame (含 build_clip refactor 拆 step → 多 PNG 配 narration 時長均分)
  - [~] **E1-4**: review UI frame preview (iter 108 backend slice `summarize_for_deck`; iter 109 API endpoint `GET /jobs/{id}/image-frames` 包 summarize_for_deck — 含 require_file_exists query param 跟 terminal_path JSON 序列化. 前端 UI 待後續 iter)
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
- [→] **Gemini narration 截斷率** (2026-05-07) — 已升級為 🎯 N 軸 (見上方 Active
  backlog), routine 治本中. 此舊條目保留追溯.
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
