# CHANGELOG

> 一頁掃完各階段做了什麼。對接手助理 / 自己日後查考很有用。
>
> 詳細 PR 級內容看 git log;詳細設計看 `docs/*.md`;當前 active 工作看 `TODO.md` 🌟 段落、
> 產品化主線看 `docs/PRODUCT_READINESS.md`。

---

## 2026-07 審查 offline 殘項收尾 — Sprint 2/3（2026-09-04）

> 劉老師指定「先 A 驗模型、B routine 認領 offline 批」的 B,含後續追加的 T2-4 / T0-3。全套 `2975 passed`。

| 項 | 內容 |
|---|---|
| T2-1 | **SSRF 位址過濾**:新增 `core/net_safety.assert_public_url` — scheme 白名單 http/https、port 只允許 80/443、主機名解析後**每個** IP 都必須是 public(擋 loopback / RFC1918 / link-local 含雲端 metadata `169.254.169.254` / ULA / 保留 / multicast;IPv4-mapped IPv6 先還原)。`core/adapters/url.py` 關掉 requests 自動 redirect 改自己跟、**每一跳送出前重驗**(只擋第一跳等於沒擋)。自架逃生門 `EDUSTUDIO_ALLOW_PRIVATE_URLS=1` 只放行位址那道。⚠️ DNS rebinding 未擋(已寫進 docstring)。 |
| T1-3 | **背景 job 並行上限 + task 強參照**:新增 `server/background.spawn` 取代 5 處裸 `asyncio.create_task`。`asyncio.Semaphore` 限並行(`EDUSTUDIO_MAX_CONCURRENT_JOBS`,預設 2,超過**排隊**不是拒絕);task 存 module 級 set 保強參照(asyncio 只持 weak ref,原本回傳值全丟掉);背景例外進 log。YouTube 上傳與 ideate 掃描 `limit=False` 不佔 render 名額。 |
| T1-4 | **`state.json` 原子寫**:`JobStore._persist` 改「寫 .tmp → fsync → `os.replace`」。原本 `write_text` 寫一半被 kill → 截斷檔 → 下次啟動解析失敗被跳過 → 整個 job 從唯一真實來源消失。 |
| T2-4 | **schema 輸入界限**:`JobOptions` / `JobSource` 共 30 個欄位補 `ge/le` 與 `max_length`(過去 50 個 `Field()` 裡 0 個有界限)。`subtitle_font_size` 直達 ffmpeg `force_style`、`max_files` / `photo_max_select` 直達迴圈次數,負值或極大值都會出事。另補 `/api/generate` 的 `slideCount`(≤100)/ `panels`(≤50)與相簿 `max_select`(≤500)—— 這三個直接決定跑幾次生成 = 燒多少額度。加漂移守衛測試。 |
| T0-3 | **review 覆蓋率揭露**:確定性校驗是高精度低召回,含三角 / 開根號的步驟一律跳過不產 flag —— reviewer 看到「沒有 ⚠」會誤讀成「已驗證」,而材力/動力學最容易按錯的步驟恰好全在沒驗到的那堆。新增 `analyze_coverage` 逐步分類(`function` / `symbolic` / `single_value` / `empty`),落 `review_coverage.json`(**分檔**存,不動 flags 既有裸 list 格式 = 零 migration),端點加回 `coverage`,審查頁頂端顯示「N / M 步無法自動驗證,沒有 ⚠ 不代表算對了」。修法**不是放寬檢查**(那會犧牲精度變狼來了),而是誠實揭露。 |
| T1-5 | **dubber 暫存清理**:中間檔(`audio.wav` / `dubbed_audio.wav` / `tts_*.mp3`)在 try/finally 清掉。**沒有**照審查建議 rmtree 整個 job_dir —— 那會把要回傳給呼叫端的成品一起刪;改成只刪自己產的固定樣式 + keep set 保護 results 路徑。⚠️ 成品仍不會過期,保留期限是產品決策待拍板。 |

---

## 文件同步輪 — 現況盤點 + 漂移勾稽（2026-09-04）

> 純文件輪:對照程式碼實況查核各文件說法,修掉漂移。**零 production code 變更**。
> 環境驗證:`2842 passed, 13 skipped(mcp + 缺 ffmpeg 的用例), 1 deselected(office_live)`
> (Linux 容器 · Python 3.11 · CI 依賴清單 + Noto CJK;與本機宣稱的 2854 passed / 1 skipped
> 同一個 2855 collected 母數,差在此容器沒裝 ffmpeg)。frontend `npm test` 7 綠 + `vite build`
> 產物正確引用 `/app/assets/...`。

| 項 | 內容 |
|---|---|
| MODEL | 勾稽模型現況:`core/config.py` 的 `GEMINI_MODEL` 已是 `gemini-3.7-flash`,故 `scriptor`(考卷旁白)/ `outliner`(大綱)/ `translate`(翻譯)**實際上早已不是 2.5**;`solve.py` 走 `resolve_id(text.fast)`。但這三者仍走 legacy `get_gemini_model()`,**只認設定頁 `text_model`、不認逐角色 `model_roles`** → M-2 剩的是「接上角色登錄表」而非「換掉 2.5」,PRODUCT_READINESS / claude.md 對應段落改寫。 |
| ID 衝突 | `docs/PRODUCT_READINESS.md` 有兩個 **U-5**(2026-08-30 新增的「`/ui` 正式退場」撞到既有的「發布站多語上傳驅動」)。既有那項改編號 **U-7**(全 repo 其他 U-5 引用皆指 `/ui` 退場,維持不動)。 |
| SKILLS | `docs/skills.md` 補 `repo-intro-video`(2026-08-31 新 skill)+ 標題從 autoSolverVideo 正名 eduStudio + 補 `/advance` slash command 與 `docs/promo/` 的關係說明。 |
| DOC-5 | demo 影片項目更新:組裝工具鏈(`docs/promo/` 9 景 + `tools/build_promo_video.py`)已就緒,剩「本機跑一次 + 放檔/連結進 README」。 |
| 快照 | PRODUCT_READINESS 的「2026-06-16 routine 快照(offline 已清空)」已被 7/8 月的審查殘項推翻,改寫成 2026-09-04 現況。 |
| 對帳 | HANDOFF / STATUS.yaml / TODO / ROADMAP 補上 2026-08-31 的 promo + skill 一輪。分支現況:`main` 於本輪進行中推進到 `ac07ab4`(2026-08-31),工程收斂輪與 promo 皆已在 main;文件同步輪本身走 PR #101。 |

---

## 官方介紹影片收尾 + repo-intro-video skill（2026-08-31）

| 項 | 內容 |
|---|---|
| PROMO | 介紹影片配樂三輪迭代:安靜版 v2(移除嘶聲層 / 心跳放疏 / 響度降到 -23 LUFS)→ 音樂主導模式 -16 LUFS(合成 bed 維持 -23)→ 音樂**交叉淡接循環** + `--loudness` 響度檔位。順修漫畫景 QA gate 膠囊 `white-space:nowrap`(防直排換行)。 |
| SKILL | 新 skill **`repo-intro-video`**(`.claude/skills/repo-intro-video/`):把**任何** repo 做成介紹影片 — 讀 repo 萃取賣點 → 分鏡表給人過目 → 產 HTML 場景 → playwright 逐格渲染 → ffmpeg xfade + 配樂。迭代 2 加上「長度可指定(30s / 60-75s / 3min)+ 音樂三選(提供檔案 / 合成氛圍 / 無聲)」與雙動畫類拆彈,附 `evals/evals.json`。與 `docs/promo/`(本專案自己那支)腳本各自獨立,skill 要能在沒有本 repo 的機器上跑。 |

---

## 工程收斂輪 — Sprint 1/2 + 模型遷移 + 計費 + U-5 退場（2026-08-30）

> 劉老師拍板的一輪工程收斂（同日於文件整理之後）。全套測試
> `2854 passed, 1 skipped(mcp), 1 deselected(office_live)`。

| 項 | 內容 |
|---|---|
| SPRINT1 | T1-1 dubber filtergraph 連續索引(缺音檔不再崩)、T2-2 base compose 綁 `127.0.0.1`、T2-3 editor `j.error` escape — 各補測試。 |
| T3-2 | **統一 Gemini client** `core/gemini_client.make_client`:金鑰單一來源(設定頁>環境變數,修掉 7 處 `os.environ` 直讀)、一律帶 timeout(`GEMINI_TIMEOUT_MS`);13 檔遷移,零殘留 `genai.Client` 直呼。 |
| T3-3 | **共用媒體 runner** `core/ffmpeg.run_media_cmd`:一律 timeout(`EDUSTUDIO_FFMPEG_TIMEOUT`)+ returncode 檢查 + stderr 進錯誤訊息;pipeline / video_concat / html_video / dubber / summarizer / tts_backend / server runner(song) 全遷(T1-2 一併收)。 |
| C-3 | **文字主力遷 `gemini-3.7-flash`**(劉老師拍板):目錄 `flash` 鍵換新,3.6 降退回選項;solve.py 改走 `resolve_id(text.fast)`(T0-4)。⚠️ 3.7 id 待 `tools/check_models.py` live 確認,404 退 3.6。 |
| BILLING | 計費準確化:文字費率**分 model**(default 退路)、未知圖片 model 記 default 價不再 $0;補 6 個漏帳點(translate 直呼 / diagram / mermaid / ideate×2 / diagram_image 生圖 / song_images 生圖)。費率仍估算,待官方價校正。 |
| U-5 | **legacy `/ui` 正式退場**:web/ 原始碼專案移除(考古走 git 歷史),`/ui` `/studio` 一律 307 轉址 `/app/`;**Dockerfile 改建 `frontend/` → web/eduapp**(順修 image 只有 /ui 沒有 /app 的缺口);CI 刪 legacy typecheck job、frontend-app-build 補跑 npm test;library.publish_url / landing / TRACK_B_URL / skills 指引同步。 |
| COMIC | 漫畫工作站**正式化啟動**:offline 稽核完成(25 測綠 / reader 全 `html.escape` / token 保護 / fail-closed 驗證),checklist 入 [`COMIC_PRODUCTION_SYSTEM.md`](COMIC_PRODUCTION_SYSTEM.md);剩 GATE 真實生成 QA 輪。 |
| OAUTH | Google Photos 帳號 consent ✅ 劉老師完成(`photos_token.json`),P2-2 BLOCKER 解除,相片簡報軸 live 全通。 |
| PROMO | **官方介紹影片**(60s/1080p30):9 個 HTML 動畫場景(`docs/promo/`)用自家 `core/html_video` 虛擬時鐘引擎渲染,`tools/build_promo_video.py` xfade 轉場串接 + 全本地合成配樂音效;`--narrate` 於本機可加 edge-tts 旁白。吃自己的狗糧。 |

---

## 文件整理 + 分支收斂（2026-08-30）

> 全部工作已收斂到 `main` 單一分支（PR #100 前的 feature branch 均已合併刪除）。
> 文件補上 8 月的漫畫工作站與 P0~P3 驗證輪,整合期規劃文件歸檔。

| 項 | 內容 |
|---|---|
| DOCS | README（中英）+ USER_MANUAL 補漫畫工作站、本機 Ollama 文字角色、四工作站首頁結構、測試數更新（2800+）;手冊新增 §7 漫畫站 + `/projects/{pid}/comics` API 速查。 |
| CHANGELOG | 補 2026-08-20 ~ 08-28 三段（漫畫 MVP / P1-P2 驗證 / P3 已有）。 |
| TODO | 勾稽 2026-07 審查項:T0-1（clean_json_escapes 白名單）、T0-2（exam/song review gate 不可關）已在 8 月修復,經查證打勾;新增「下一步候選」盤點段。 |
| ARCHIVE | 整合期文件 `ROADMAP_UNIFIED.md` / `INTEGRATION_KICKOFF.md` / `DESIGN_SPEC.md` 移至 `docs/archive/`（歷史紀錄,不再更新）。 |
| HANDOFF / STATUS | 交接筆記與 STATUS.yaml 頂部欄位刷新到 2026-08 現況。 |

---

## P3 技術債收斂（2026-08-28）

| 項 | 內容 |
|---|---|
| LIFESPAN | FastAPI `@app.on_event("startup")` 遷移為 lifespan async context manager，啟動恢復／selfcheck／security warning 行為不變並補契約測試。 |
| ASYNCIO | pytest 明確固定 `asyncio_default_fixture_loop_scope=function`，避免 plugin 預設變動造成 fixture loop 行為漂移。 |
| OFFICE-GATE | GitHub Actions 明確執行 `not office_live`，另以 collect-only 防 gate 被刪；Windows 本機 PowerPoint COM round-trip 維持 release gate。 |
| WHISPER-CACHE | Whisper 動態解析 `HF_HUB_CACHE`／`HF_HOME`／`XDG_CACHE_HOME`，partial snapshot fail-closed，health 新增 `cache_source`。 |

詳細驗收見 [`P3_COMPLETION_PLAN_2026-08-28.md`](P3_COMPLETION_PLAN_2026-08-28.md)。

---

## P0 live E2E 稽核 → P1/P2 驗證完成（2026-08-27 ~ 2026-08-28）

> 全專案稽核 + live 端到端驗證輪:Phase 2/3 runtime 驗證（含 event sink、手機版面修復）後,
> 關閉稽核抓出的 P1/P2 項。backend full regression `2839 passed`。

| 項 | 內容 |
|---|---|
| P1-1 | **Ollama provider production 接線**:文字 role 可指向本機 Ollama（settings `model_roles` 巢狀 provider）,選 Ollama 不呼叫 Gemini;`qwen3:4b` live inference 通過。 |
| P1-3 | PPTX live round-trip（Windows PowerPoint COM fallback,upload → conversion → augment/export 真跑）。 |
| P1-4 | `/api/generate` request validation:非法 `mode`/`style`/`density` 回 422 + regression tests。 |
| P1-5 | GitHub Actions 升級 `checkout/setup-python/setup-node@v6` + Node 24,雲端 CI 6/6 全綠。 |
| P2-1 | Whisper `large-v3` 三流程 live（影片 STT / 會議摘要 / 歌詞抽取,RTX 4080 cuda/float16）。 |
| P2-2 | Google Photos OAuth 邊界可測;**帳號 consent 未完成**（`/google-photos/status` 誠實回 `authorized=false`,列 BLOCKER）。 |
| P2-3 | Token 部署驗證:未授權 401、Bearer/cookie 200、event sink exemption 204。 |
| P2-4 | 影片/簡報/圖卡/漫畫四工作站 click-through + 手機 390×844 smoke、console zero-error。 |
| FIX | live 圖片 MIME 修正 + per-job TTS 選擇（`8da9935`）;comic DOCX CI 依賴修正（`b8be2b5`）。 |

驗收矩陣見 [`P1_P2_COMPLETION_PLAN_2026-08-28.md`](P1_P2_COMPLETION_PLAN_2026-08-28.md);
證據報告在 `reports/eduStudio_P1_P2_Function_Verification_Report_2026-08-28_v1.0.docx`;
Phase 2/3 runtime 報告見 [`PHASE2_TEST_REPORT_2026-08-27.md`](PHASE2_TEST_REPORT_2026-08-27.md) /
[`PHASE3_TEST_REPORT_2026-08-27.md`](PHASE3_TEST_REPORT_2026-08-27.md)。

---

## 漫畫工作站 Internal MVP + 目標導向首頁（2026-08-20 ~ 2026-08-26）

> `/app` 改版為**目標導向首頁**（輸入需求自動歸類到 影片/簡報/圖卡/漫畫 四工作站）,
> 並新增第四個內容工作站「教學漫畫」— 獨立 Comic Core,與既有工作站共用 Project/設定/
> provider/成本。

| 項 | 內容 |
|---|---|
| COMIC | Comic Core（`core/comics.py` + `server/routes/comics.py` + `frontend/edustudio/comic-studio.jsx`）:Series Bible（世界觀/角色 visual lock/voice/glossary）、script/storyboard/camera/對白/alt text、Evidence Pack、逐頁生成、**六道 QA gate**（anatomy/technical/text/safety/page_render/human_approval）、版本化（PASS 才進 `CURRENT`、`CURRENT` immutable、改稿 fork 新版）、HTML/PDF/DOCX/ZIP 匯出、Internal Reader、release 可撤回。File-first + fail-closed。 |
| UI | 目標導向首頁 + 漫畫工作站介面;視覺模式 UI alias 收斂（`0da0130`）、視覺審查問題修復（`5773819`）、漫畫版面與審查防護強化（`57c2cda`）。 |

設計文件見 [`COMIC_PRODUCTION_SYSTEM.md`](COMIC_PRODUCTION_SYSTEM.md)。

---

## 完整使用手冊 + README 文件導覽 (2026-07-14)

> 新增 `docs/USER_MANUAL.md`(完整操作參考,補在 onboarding 0→1 之上);README 中英雙語加
> 「文件」導覽段與 `server.main:app` 啟動雷提示。

| 項 | 內容 |
|---|---|
| MANUAL | `docs/USER_MANUAL.md` — 目錄 / 安裝與啟動(含 `server.main:app` vs `main:app` 常見雷)/ 設定(env 完整表 + 模型三階)/ 核心概念(工作空間 · Job 狀態機 mermaid · 審查關卡 · 成本)/ 三大工作站逐一 / 發布 YouTube / CLI / 疑難排解 / REST API 速查 / FAQ + 英文速查。 |
| README | 中英雙語各加「文件 / Documentation」導覽段(手冊 / onboarding / deployment / contributing / roadmap / code review)+ 快速開始補 `server.main:app` 啟動路徑警告。 |
| ROADMAP / TODO | 反映手冊已完成;截圖補齊列為待辦。 |

---

## 程式碼健檢 + 圖片模型入門階對齊 (2026-07-09 ~ 2026-07-10)

> 全庫程式碼審查(5 條並行子系統 + 逐一驗證)產出分 Tier 改善規劃;圖片模型入門階對齊官方
> 三階並統一兩個登錄表。後續認領清單見 `TODO.md` 🔍 段、方向見 `ROADMAP.md` 🔍 段。

| 項 | PR | 內容 |
|---|---|---|
| REVIEW | `#97` | `docs/CODE_REVIEW_2026-07.md` — 全庫審查 + 分 Sprint 改善規劃(Tier 0 產品正確性 / T1 穩定性 / T2 安全 / T3 架構)。結論:體質高於一般自架專案、無遠端未授權嚴重漏洞、上一份 CODE_REVIEW 的 4 個 P0 已全修。 |
| IMG-LITE | `#98` | 圖片入門階 `gemini-2.5-flash-image` → `gemini-3.1-flash-lite-image`(**Nano Banana 2 Lite**),對齊官方三階 Lite/2/Pro;`core.models` 的 image 角色改引用 `core/infocards/models.py` 目錄(單一來源,不再各寫一份)+ 漂移守衛測試;保留 `gemini-2.5-flash-image` 定價(diagram/song 仍直接用)。⚠️ 新 id 待 live 實測確認。 |

---

## Google 相簿相片簡報 + 圖片模型階層 (2026-07-07)

> 新來源「連結 Google 相簿 → AI 選圖+配文 → 相片簡報（影片 + PPTX）」，接在既有 job
> pipeline 上（最大化複用 render / PPTX 匯出 / SlideEditor / YouTube 上傳）。全 offline-first。

| 項 | PR | 內容 |
|---|---|---|
| IMG-TIER | `#94` | 圖片模型選單整理成 便宜 / 中等 / 貴 三品質階層（`gemini-2.5/3.1-flash-image`、`gemini-3-pro-image`），修掉 2.5 被誤標「將停用」（那是 Imagen-4 淘汰，本專案未用）。 |
| PHOTO-1 | `#95` | **Smart Photo-to-Deck 完整功能**：`core/photo_deck.py`（vision 品質過濾/逐張 caption/取標題，防幻覺、縮圖分批）+ `core/google_photos.py`（Photos Picker 薄層，2025 後 Library API 已不可用）+ `tools/photos_auth.py`（一次性 CLI 授權）；`SourceType.GOOGLE_PHOTOS` 走 ingest→render；`/google-photos/*` 路由 + `/app` PhotoSourcePanel。影片＝job mp4、PPTX＝`/jobs/{id}/pptx`。 |

新增系統相依：**LibreOffice**（PPTX 來源已有）；Google Photos 需一次性 OAuth（`photospicker.mediaitems.readonly`）。

---

## 多媒體來源擴充 — 簡報缺圖補圖 / HTML 動畫 / PPTX 原生 (2026-06-25 ~ 2026-06-26)

> 接兩條新來源進既有 render + `/library` + YouTube 上傳：①「缺圖簡報自動補圖 → 新簡報 /
> 影片」②「HTML 動畫 → 影片」。全程 offline-first（mock 走佔位、不打真 Gemini），每個 PR 附測試。

| 項 | PR | 內容 |
|---|---|---|
| HTML-1 | `#87` | HTML 動畫網頁（`.html` / URL）→ 虛擬時鐘無頭逐格擷取 → fps 精準 MP4（`core/html_video.py`），接既有上傳機制 |
| HTML-2 | `#88` *(審查中)* | `/app` HTML 動畫上傳介面（檔案 / URL + 時長 / fps / 解析度） |
| SLIDE-1 | `#89` | 缺圖簡報補圖：PyMuPDF 偵測純文字頁 → Gemini 生配圖 → 合成新頁 → render；含含圖 PPTX 匯出 + `/app` 勾選 UI（`core/slide_image_gen.py`、`core/slide_pptx.py`） |
| SLIDE-2 | `#90` | 補圖改 **auto 智慧置入**：偵測原頁最大空白區就地置入、原頁維持原大小（取代 side-by-side，設為預設） |
| PPTX-1 | `#91` | 上傳 PPTX 原檔就地補圖：在原檔插圖、**原文字保持可編輯**（`core/pptx_augment.py`、`POST /upload/pptx`） |
| PPTX-2 | `#92` *(審查中)* | 補圖簡報一鍵轉講解影片（pptx→pdf→既有 slides_pdf 流程，`POST /jobs/{id}/to-video`） |

新增系統相依：**LibreOffice**（`libreoffice-impress`）— 僅 PPTX 來源功能（上傳補圖 / 轉影片）需要，用於 `.pptx → pdf` 逐頁分析。

---

## v1.0.0 — 產品化推出（開源自架首發候選）(2026-06-07 ~ 2026-06-10)

> 從「個人本機能跑」做到驗收門檻：讓一個**陌生老師** clone → 照 README 一條龍跑起來 →
> 安全地暴露在內網/伺服器 → 產一支影片並上 YouTube，全程不踩雷、不外洩金鑰、server 重啟
> 不丟工作。對應 [`docs/PRODUCT_READINESS.md`](PRODUCT_READINESS.md) Phase 0–7，共 **36 個 PR**
> （#15–#50）。整段嚴守 **offline-first** 紀律（純 code、不打真 Gemini/GCP、低風險、有測試），
> 燒額度 / 安全模型 / 大架構決策一律先寫 proposal 待拍板。
>
> **發布狀態**：本段為 **release-notes，git tag `v1.0.0` 與 GitHub Release 的實際發佈時機由劉老師
> 拍板**——首發前還有兩項本機 GATE 待跑：`docker compose up --build` 跨平台實測（D-1）與 F5 GPU
> passthrough 實測（D-4）。版本號 `v1.0.0`（開源首發）已於 readiness 清單定案。

### 🔴 Phase 0 — 開源/法務前置

| 項 | PR | 內容 |
|---|---|---|
| P0-1 | `#16` | 加 **MIT LICENSE**（© 2026 劉瑞弘）+ README 授權 badge / footer |
| P0-2 | `#17` | secret 全歷史稽核（全 52 commit / 所有分支）→ **結論乾淨、無需 history rewrite**；縱深防護靠 GitGuardian CI + `.gitignore` |
| P0-3 | `#18` | `.env.example` 補齊全部 **25 個**環境變數（原僅 7 個）+ 分區註明預設值/用途，唯一必填仍 `GEMINI_API_KEY` |
| P0-4 | `#19` | `CONTRIBUTING.md` + `.github/ISSUE_TEMPLATE/` + `PULL_REQUEST_TEMPLATE.md`（含「未繞 review gate」自我檢查） |
| P0-5 | `#20` | `SECURITY.md`（部署前必讀警告 + 漏洞私密回報流程 + 3 工作天回覆承諾） |

### 🔴 Phase 1 — 安全硬底層（開源自架致命缺口）

| 項 | PR | 內容 |
|---|---|---|
| S-1 | `#23` | **單一共享 token 驗證層**（`server/auth.py` middleware）— 瀏覽器 cookie / CLI Bearer 雙路；沒設 `EDUSTUDIO_API_TOKEN` → 全開 + 啟動大聲警告（保留 localhost 自用） |
| S-2 | `#21` | **CORS 收緊** — `allow_origins=["*"]` → 讀 `EDUSTUDIO_ALLOWED_ORIGINS` 白名單（`core.config.get_allowed_origins()`） |
| S-3 | `#22` | **path-traversal 全面審** — 抽共用 `server/path_safety.py::safe_join`（字元檢查 + resolve-containment），補 3 個 jobs 端點缺口、重構 slides |
| S-4 | `#24` | **上傳硬化** — 副檔名/MIME 白名單 + 檔名 NFC 正規化 |
| S-5 | `#25` | **secret 落地**（GATE→拍板不加密）— 明文 + gitignore，`SECURITY.md` 講清處置（別放共享磁碟、`chmod 600`） |
| S-6 | `#26` | **per-IP rate limit**（自寫 token bucket `server/ratelimit.py`，純標準庫）掛燒額度端點，超限 429 |

### 🔴 Phase 2 — 可靠性（server 重啟不丟工作）

| 項 | PR | 內容 |
|---|---|---|
| R-1 | `#27` | **啟動 resume 止血** — `JobStore.resume_interrupted()` 把重啟中斷的卡住 job 標 FAILED + 提示重試（`AWAITING_REVIEW` 等人工合法暫停不動） |
| R-2 | `#28` | **review gate 不可繞**（硬規則 #1）— render 入口 assert `reviewed`，`require_review=True` 未審→拒渲染標 FAILED；`/approve` 標記、re-ingest 重置 |
| R-3 | `#29` | **sync I/O 收口** — runner merge 路徑 + localization 11 個 async handler 的 blocking 呼叫全包 `asyncio.to_thread`，不阻 event loop |

### 🟠 Phase 3 — UI 收斂到 `/app` 單一

| 項 | PR | 內容 |
|---|---|---|
| U-2 | `#31`·`#32` | **逐區 refine** — 後端 `infographic_service.refine_infographic_section()` + `POST /api/refine-section`（全 mock 不打真 API）；`/app` 前端區塊點選 + 逐區微調面板（可只改文字省額度） |
| U-3 | `#33` | **`/ui` `/studio` 標 legacy + 退場 banner** — index 注入頂部退場提示導向 `/app`，`/studio` 額外警示「直連 Gemini、繞過計費/審查」；landing 卡標 legacy badge |
| U-4 | `#35` | **成本面板真實化** — 移除所有 mock 假數字（`$18.74`/「試用 38/50」SaaS 殘留），頂欄 pill + 抽屜共用真實 `/api/usage`，無呼叫時空狀態 |
| U-6 | `#30` | **前端建置文件化** — `base:'/app/'` 寫死進 `vite.config.ts`（消 footgun）+ `build:app` 別名 + CONTRIBUTING 建置須知 |

### 🟡 Phase 4 — 計費準確 + 模型抽象（M 軸）

| 項 | PR | 內容 |
|---|---|---|
| C-1 | `#34` | **影片/解析 pipeline 接計帳** — `core.usage.record_text_now()` 接四個 chokepoint（outliner/scriptor/slide_ingest/solve），成本面板新增「影片」「解析」站 |
| C-5 | `#39` | **模型 id 自我健檢** `tools/check_models.py` — 蒐集會送 Gemini 的全部 id（角色登錄表 + 設定下拉）比對 `models.list()` 抓 404 風險（可注入 fake，不打真 API） |
| M-1 | `#36` | **角色登錄表 `core/models.py`** — 6 個邏輯角色 →（provider, model_id）單一真實來源，`resolve()` 優先序：逐角色設定 → legacy 單值 → 內建預設；B-ready |
| M-2 | `#37` | **換掉寫死 id（視覺/infocards 世界）** — `infocards/gemini.py`/`poster_service`/`routes/infocards.py` 全改走 `resolve_id()`，行為不變。影片/解析文字 pipeline 換接屬 C-3 GATE，留待開額度 |
| M-3 | `#38` | **設定頁逐角色模型管理** — 新增 `model_roles` 設定欄位 + `role_catalog()`，設定頁逐角色下拉寫入閉環 |
| M-4 | `#40` | **provider adapter 介面**（B-ready stub `core/providers.py`）— `Provider` 協定 + `GeminiProvider` + registry，Phase 9 本機 provider 可零摩擦 slot-in |

### 🟡 Phase 5 — 部署就緒

| 項 | PR | 內容 |
|---|---|---|
| D-2 | `#41` | **production compose override** `docker-compose.prod.yml`（綁 `127.0.0.1`、log rotation、`no-new-privileges`）+ `docs/DEPLOYMENT.md` 上線前安全 checklist |
| D-3 | `#42` | **反向代理 + TLS 範本** `deploy/nginx.conf.example` / `Caddyfile.example`（上傳上限對齊、長請求逾時、`X-Forwarded-*` 透傳、HSTS） |
| D-5 | `#43` | **啟動自檢** `core/selfcheck.py` — 啟動印綠/紅環境檢查（ffmpeg/字型 critical、GEMINI key 警告），不阻擋啟動 |
| D-6 | `#44` | **requirements 分層說明** — README core/optional/song/dev 四層表 + 系統相依（ffmpeg、Noto CJK）；補回漏報的 `faster-whisper`/`python-pptx` |

### 🟡 Phase 6 — 文件就緒（陌生人能上手）

| 項 | PR | 內容 |
|---|---|---|
| DOC-1 | `#45` | `claude.md` 更新到 eduStudio 整合後定位（四條 track + `/app` 收斂 + M 軸 + 安全/部署現況） |
| DOC-2 | `#46` | 去個人化 / 移除 Windows 個人絕對路徑（`D:\...` / `C:\...` → repo 相對 + 三平台範例） |
| DOC-3 | `#47` | 端到端 onboarding 改寫成**陌生老師 0→1** 主線（安裝 → 配 key → 產第一支影片含 review gate → 上 YouTube → 排查表） |
| DOC-4 | `#48` | 新增 `docs/ARCHITECTURE.md` 架構地圖（三層俯瞰 + job 狀態機含 render assert + 四 track 共用 pipeline + 橫切關注點） |

### 🟡 Phase 7 — 測試與 CI

| 項 | PR | 內容 |
|---|---|---|
| T-1 | `#49` | **端到端整合測試** `tests/test_e2e_pipeline.py` — FastAPI TestClient + 真 pipeline 串 happy-path（建 job→ingest→review gate→approve→render→下載），只 mock 外部邊界；第二支證明 review gate 整條不可繞 |
| T-2 | `#50` | **CI 護網補洞** — 確認 Node actions 已最新主版；新增 `frontend-app-build` job 把唯一正式前端 `/app`（先前從未進 CI）納入 `npm run build` 護網 |

**測試成長**：v4 收尾 **467** → 產品化推出後 **2509 passed**（CI 端，含字型；本機容器缺 Noto CJK 有 1~3 個像素斷言假象）。

**驗收門檻達成度**：Phase 0–4 全綠、Phase 5 文件/設定就緒（**D-1 跨平台 / D-4 GPU 實測為劉老師本機 GATE**）、
Phase 6–7 offline 項清空。剩餘 `[ ]` 多為 GATE（需開額度 / 本機實機 / 架構拍板），見 readiness 清單末「待劉老師拍板」。

---

## Session 2 — 影片成品打磨(2026-05-14 ~ 2026-05-15, iter 39 ~ 48)

| iter | commit | 內容 |
|---|---|---|
| 39 | `73b07a1` | **修 test job leak** — 三層根因(routes `_store` 中介, `_persist` self.root, staticmethod → instance method);清 5 個 leak dir;從此 pytest 不再污染真實 jobs/ |
| 40 | `f5b8db4` | **Proposals 卡片主題下拉** — `POST /proposals/{id}/approve` 接 optional body, 核准前可選 pptx 主題, 不必先核准再到 review page 改 |
| 41 | `035cb52` | **個人 intro 串接** — `core/video_concat.py`(concat + audio normalize cache + SRT offset, 22 tests);runner hook 在每支主影片前接 8 秒 intro;UI checkbox 雙處 |
| 42 | `f4b22d9` | **開場白多樣化** — `core/intro_rewriter.py`(30 tests);exam/slides → 同學變體 8 個, document/repo/url → 大家好變體 8 個;stable md5 hash seed |
| 43 | `e527b1f` | **影片長度模式** — `core/length_mode.py`(12 tests);quick(8-15 min)/ lecture(60-180 min)兩 preset;4 份 prompts 加 placeholder;雙 UI 下拉 |
| 44 | `35a0307`<br>`fa32f64` | **DofLab 10 套主題 + intro 路徑重構**;v1 沉穩(editorial/podium/notebook/shinobi/elven)+ v2 衝擊(zine/arcade/risograph/supergraphic/brutalist);total 5 → **15 套主題**;intro mp4 從 `D:/Dropbox/` 移到 repo 內 `docs/intro_journal.mp4` |
| 45 | `537cb93` | **多章合 final.mp4** — 修「選 quick 出了 5 支獨立 mp4」設計 bug;render 完所有章節後 ffmpeg concat 成單支 `final.mp4` + `final.srt`;intro 改接到 `final.mp4` 不再每章重複;各章 mp4 保留供 section re-render |
| 46 | `7d43a9f` | **收緊 quick mode 預算** — sections 4-6→3-4 / slides 5-10→4-5 / chars 100-200→80-120;加 `total_narration_budget_chars` (quick=2500 / lecture=20000);4 份 prompts 加「取下限優先, 上限是極限」+「強制步驟先估總字數」 |
| 47 | `df32583` | **`final.mp4` UI prominence** — JobEditor emerald 區塊「🎬 完整影片」排頂, 各章列下方標「重 render 用」;JobCard preview button 優先 final;Library 多章 job 只列 final.mp4(各章不污染 YT 上傳列表)+ 6 個新 test |
| 48 | `034d6d7` | **deck 時長 estimator** — `estimate_deck_duration(deck, mode)` 純函式;runner 在 ingest 完跑一輪 log 估算結果, over-budget 用 `logger.warning ⚠`;8 個新 test |

**iter 46 修法效果實測** (用戶實機跑 Journal_Paper PDF):
| Job | prompt 版本 | sections | 字數 | 估時 | budget 使用率 |
|---|---|---|---|---|---|
| 7d93439a0793 (新) | iter 46 | 3 | 2374 | 11.9 min | **95%** ✓ |
| 9c8e3df46ba5 (舊) | iter 43 | 5 | 8594 | 43.0 min | 344% ⚠ |
| 764039d15546 (舊) | iter 43 | 5 | 6774 | 33.9 min | 271% ⚠ |

字數降到老 prompt 28%, 落在預算內. 渲染後 final.mp4 實際 11.0 分鐘 (vs estimator 預估 11.9, 誤差 8%).

**測試成長(session 2)**: 354 → **467 tests**(+113 tests),全綠;無 test job leak。

**用戶可見變化(React UI)**:
- 建 job / 核准 proposal 三個新選項:
  - pptx 主題下拉:5 既有 + 10 dof-* 分 5 組 optgroup(課程教學 / 期刊 / 漫畫 / DofLab v1 / DofLab v2)
  - 影片長度下拉:快速(8-15 min)/ 詳細授課(60-180 min)
  - 串個人 intro checkbox:勾起來在主影片前接 8 秒個人開場
- 開場白會自動依 source_type 換變體(同學好 / 大家好), 同題穩定跨題會變
- 多章 job 自動合成 `final.mp4`, UI emerald 區塊醒目標「🎬 完整影片」當主交付

**沒做(延後)**:
- **Idea 2 多 voice / 多語言** — 用戶要求放到後面(Edge TTS 替代 F5、英 / 日翻譯軌)

---

## v4 階段四大 feature track(全部 server-side 完成)

### 🟢 階段 1 A — Docker 部署

| iter | commit | 內容 |
|---|---|---|
| 6 | `d4b3b04` | `Dockerfile` v1 — multi-stage(Node 20 build → Python 3.12-slim + FFmpeg + Noto CJK),~700MB |
| 9 | `3fe99e3` | `docker-compose.yml` + `.env.example` — volumes / restart unless-stopped(解 P0 #1 部分)/ F5 GPU passthrough section 註解 |

**等 user 本機實測**(目前 user 機器沒 Docker 環境,擱置)。

### 🟢 階段 1 C — Claude Code skill

| iter | commit | 內容 |
|---|---|---|
| 3 | `0e6cddb` | `.claude/skills/pdf-to-video/SKILL.md` — 完整流程指引(server health → submit_job → review → render) |

**等 user 在另一 Claude session 試觸發**(目前還沒手動驗收 + 沒寫 self-poll helper)。

### 🟢 階段 2 B — ideate.py 自動內容企劃(完整可運作)

| iter | commit | 內容 |
|---|---|---|
| 10 | `f894b74` | scaffold + design RFC(`docs/ideate-design.md`)|
| 11 | `f533995` | `scan_changed_files` + `load/save_proposals`(atomic write) |
| 12 | `e474c40` | `propose_from_file`(Gemini Vision 看 PDF 前 5 頁提案) |
| 13 | `ee01c8a` | `dedupe_against_jobs`(三層去重: JobStore done / YouTube uploaded / 前次 approved/ignored) |
| 14 (前半) | `8285432` | server route `/proposals` — GET list / POST approve / PATCH ignore |
| 14 (後半) | `25c2044` | React UI `ProposalsList.tsx` 卡片頁 |
| 23 | `d55809f` | CLI `scripts/run_ideate.py` + `run_ideate` 整合函式 |
| 24 | `4fe1802` | 修 retry 走錯階段(`state=FAILED + 無 deck.json` 走 schedule_job) |
| 25 | `1ebd398` | **自動判斷 source_type** — Gemini Vision 看前 2 頁分類,解 user 真實踩雷 |
| 25 hotfix | `db1a732` | prompt `{{ }}` 雙花括號 bug 修(detect 沒走 `.format()` 不該 escape) |
| 27 | `4577675` | UX 翻轉:砍 yaml + 自動排程,全 ad-hoc UI modal(user 反饋 UX 太繁瑣) |
| 33 | `43e1ac3` | 進度 streaming server-side: `POST /scan-folder/async` + `GET /scan-status/{id}` + in-memory state |
| 34 | `a574627` | React UI modal 配對 — fire-and-forget + 3 秒 poll + 即時 metrics |

**user 已驗證 ideate 端到端跑通**(2026-05-13 用 `pdfs/test/` 混合內容測過,auto 正確分類 article vs 考題)。

### 🟢 階段 2 E — 工程圖 AI 輔助(完整可運作)

| iter | commit | 內容 |
|---|---|---|
| 18 | `17826a9` | scaffold + design RFC(`docs/engineering-diagram-design.md`)|
| 19 | `dd47798` | `_validate_code_ast` AST allowlist(matplotlib/numpy/math/scipy + 擋 eval/exec/open/getattr)+ `_render_matplotlib_diagram` subprocess sandbox |
| 29 | `403ffc4` | AST 補擋 dunder attribute(`obj.__dict__` / `cls.__class__` 繞道,review 抓的 P0) |
| 31 | `5c4d899` | `_propose_matplotlib_code`(Gemini text gen)+ `generate_diagram` 整合 + `prompts/diagram_matplotlib.txt` 規則 |

**等 user 給 spec 跑一張真實圖看效果**(自由體圖 / 彎矩圖 / 方塊圖等 7 種 kind 都支援)。

---

## P0 結構性弱點(review iter 22 抓的,全修)

| # | bug | 修法 commit |
|---|---|---|
| #1 | proposal id collision(秒級精度同秒撞 id) | `5d9714b` 改 `time.time_ns()` 納秒級 |
| #2 | prompt `{{ }}` 雙花括號(detect 沒走 `.format()`) | `db1a732` 改單花括號 + `_parse_detect_response` 補防呆 |
| #3 | retry 路徑(ingest fail 時走 render 找不到 deck.json) | `4fe1802` `state=FAILED + 無 deck.json` 走 schedule_job |
| #4 | AST allowlist 漏 dunder attribute 繞道 | `403ffc4` 加 dunder reject + 7 regression tests |

---

## 技術債清理

| iter | commit | 內容 |
|---|---|---|
| 1 | `008ae1e` | `tts_config.json` gitignored + `tts_config.example.json`(server 跑會改檔,踩過 2 次誤 commit) |
| 5 | `dfac939` | CI 紅修兩條 — Py 3.10 f-string 反斜線 + 缺 mutagen |
| 8 | `f8ad547` | `requirements.txt` 分層(core/llm/pdf/server/legacy)+ **修 google-genai 漏列** bug |
| 12 | `7b68209` | 死碼 deps 真實移除(anthropic / pdfplumber / reportlab) |
| 13 | `1828ac5` | `scriptor.py` prompt 抽到 `prompts/*.txt`(555 → 434 行,-22%) |
| 14 | `a08c15f` | `outliner.py` prompt 抽到 `prompts/*.txt`(432 → 343 行,-21%) |
| 28 | `894ae78` | `pptx-jliu-style` 5 主題色票移植(+Frieren / Naruto / Journal) |
| 30 | `439e540` | `prompts_loader` cache invalidation(`clear_prompt_cache()` + `PROMPTS_NO_CACHE` env) |
| 35 | `9f65707` | `pipeline.py` 拆出 `core/photo_overlay.py`(decouple from 全局狀態) |
| 37 | `99d48bc` | `pipeline.py` 拆出 `core/srt.py`(純函式 + 16 tests cover 中英切句 / 字數比例 / float 誤差) |

---

## 加分項目

| iter | commit | 內容 |
|---|---|---|
| 2 | `ffd1df6` | `LogPanel` 上滑不被打斷(pin-to-bottom pattern,CR P2 #10) |
| 19 | `699abcc` | `docs/onboarding.md`(給研究室助理 Kiwi / Christian 上手用)|
| 36 | `7235ca7` | `/health` 加強 8 條 setup diagnostics(gemini_key / fonts / proposals.json 等) |

---

## 測試覆蓋

| 起點 | 終點 | 變化 |
|---|---|---|
| 148 tests / 9 modules | **354 tests / 16 modules** | **+206 tests** |

新增 modules(對應 v4 新功能):
- `tests/test_upload.py`(7,iter 4)
- `tests/test_ideate.py`(57,iter 10-25)
- `tests/test_prompts_loader.py`(16,iter 13 + 30)
- `tests/test_ideate_runner.py`(11,iter 27 + 33)
- `tests/test_proposals_route.py`(17,iter 14 + 27 + 33)
- `tests/test_diagram_gen.py`(42,iter 18-31)
- `tests/test_visuals.py`(7,iter 9 暖身)
- `tests/test_photo_overlay.py`(8,iter 35)
- `tests/test_srt.py`(16,iter 37)
- `tests/test_health_endpoint.py`(6,iter 36)

`hardsub` 跟 `pptx_themes` 也擴充(各 +4 / +7 tests cover Windows path 跟 5 主題)。

---

## 還沒做(低優先 / 需 user 互動)

- **F5 中國腔治本** — 需實機跑樣本對比(cfg_strength / 換 model / fine-tune)
- **Gemini narration 截斷率 22%** — 需實跑驗證
- **Pronunciation map 缺漏** — 需實聽錄音收集念錯字
- **`pdf-to-video` skill 實測 + auto-poll helper** — 需 user 在另一 session 試
- **Docker compose up 實測** — 等 user 有 Docker 環境
- **diagram_gen 真實圖 demo** — 需 user 給工程圖 spec 跑一張
- **階段 3 D 持久化 worker** — 大工程,要先 RFC 對齊技術選型(RQ / Celery / SQLite 自寫)
- **pipeline.py 繼續拆檔**(剩 dynamic_avatar / hardsub wrapper 等可獨立)
- **ROADMAP 同步 v4 段落**(可能 stale,等下波)

---

## 開發體驗工具(本次 session 引入)

| 工具 | 用途 |
|---|---|
| `/loop /advance` | 自我配速自動推進(dynamic mode,25 分一輪) |
| `/advance` slash command | 單輪手動觸發 health check → 挑任務 → execute → commit → push → 同步追蹤檔 |
| 主動 stop loop | 任務做完 + 沒 backlog 時 AI 自主停(這個 session 還沒觸發過) |

37 個 iter 跑下來,**所有 commit 都 CI 綠燈**,沒回滾。
