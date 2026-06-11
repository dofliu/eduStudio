# 產品化推出清單 — Product Readiness

> 建立：2026-06-07　·　目標：把 eduStudio 以**產品等級**推出去。
> 推出形態（2026-06-07 劉老師拍板）：**公開開源自架**（放 GitHub 讓任何老師 clone 自架；
> 不做多租戶 SaaS）。UI 方向：**收斂到 `/app` 單一**（`/ui` `/studio` 退場或標 legacy；
> `/studio` 的 client-side 直連 Gemini 要改走後端）。涵蓋範圍：**全面產品化稽核**。
>
> 這份是「離產品等級還差什麼」的稽核 + routine 工作清單。大方向版本路線看
> [ROADMAP.md](../ROADMAP.md)、短期雜項看 [TODO.md](../TODO.md)、內容品質看
> [CONTENT_QUALITY_ROADMAP.md](CONTENT_QUALITY_ROADMAP.md)，**不重複寫**，只在這裡收斂
> 「推出去」這條主線。

## 怎麼用這份文件（給 routine）

- 由上而下做：**Phase 0 → 9**（0~5 是「能推了」的門檻，6~7 收尾，8~9 是長尾/差異化；
  Phase 4 內含 **M 軸 模型抽象**），phase 內按 🔴 → 🟡 → 🟢。
- 每項標了 **offline / GATE**：
  - `offline` = routine 可自主（純 code、不打 Gemini/GCP、低風險、有測試）。
  - `GATE` = 需劉老師拍板架構 / 開 API 額度 / 做安全決策，**routine 不自主碰**，寫
    proposal 後 STOP（沿用既有 offline-first 紀律，硬規則 #1/#3）。
- 狀態：`[ ]` 未做 / `[~]` 進行中 / `[x]` 完成。完成的補上日期 + commit 方便追。
- 守既有紀律：動 server/runner/schemas 跑 `pytest tests/`（硬規則 #7）；一輪一小項、
  盡量 ≤3 檔；改 schema 型別寫 migration（見 docs/CODE_REVIEW.md Round 2）。

## 驗收門檻（「可以推了」的定義）

開源自架版本要能讓一個**陌生老師**：clone → 照 README 一條龍跑起來 → 安全地暴露在他的
內網/伺服器 → 產一支影片並上 YouTube，全程不踩雷、不外洩金鑰、server 重啟不丟工作。
具體 = 下面 Phase 0~5 全綠（Phase 6~7 是加分與長尾）。

---

## Phase 0 — 開源/法務前置（🔴 擋發佈，最先做）

> 沒這些不能公開掛上去。多為一次性、offline。

- [x] 🔴 **P0-1 加 LICENSE**（offline）— ✅ 2026-06-07 完成。落 `LICENSE`（MIT，© 2026 劉瑞弘
  Juihung Liu）+ README 授權 badge + footer 授權說明。`pyproject.toml` 因目前是純 pytest 設定
  （無 `[project]` 打包表，檔頭明言「不打算 build/package」），**不另塞 license 欄**避免造出
  半套打包設定；待日後真要打包再補 `[project] license`。
- [x] 🔴 **P0-2 secret 全歷史稽核**（offline）— ✅ 2026-06-07 完成，**結論：乾淨、無需 history
  rewrite**。掃描全 52 個 commit / 所有分支（`git log -p --all`）查：① 真實 Google API key 值
  `AIza+35` → **0** ② OAuth token `ya29.` / refresh `1//` → 無 ③ PRIVATE KEY block → **0**
  ④ OpenAI/AWS/Slack/GitHub token（`sk-`/`AKIA`/`xox`/`ghp_`）→ 無 ⑤ 曾被 commit 的實際 secret
  檔（settings.json/.env/youtube_token.json/tts_config.json/client_secret*.json）→ **從未** ⑥
  硬編 `api_key="..."` 賦值 → 無。歷史中的 `client_secret` 字串全是**程式碼/文件引用檔名**
  （`find_client_secrets()`、glob、gitignore 樣式），非金鑰本體。
  - 縱深防護：CI 已掛 **GitGuardian Security Checks**（每個 PR gating）+ `.gitignore` 已蓋全部
    敏感檔，持續防未來誤 commit。BFG/history rewrite **不需要**。
- [x] 🟡 **P0-3 `.env.example` / 設定範本完整度檢查**（offline）— ✅ 2026-06-07 完成。對全 code
  `getenv`/`environ` 盤點出 **25 個**環境變數，原範本只列 7 個 → 補齊全部並分區註明預設值/用途。
  結論：**唯一必填仍是 `GEMINI_API_KEY`**，其餘 24 個皆選用（DB 路徑預設 repo 內、品牌走設定頁、
  ollama 預設 localhost、whisper 自動偵測），故全部以註解列出當完整參考（不強迫設定）。改檔名
  標題 autoSolverVideo→eduStudio。
- [x] 🟡 **P0-4 CONTRIBUTING.md + issue/PR 範本**（offline）— ✅ 2026-06-07 完成。新增
  `CONTRIBUTING.md`（本機開發 + 跑測試 + **不可妥協規則**：review gate / offline-first /
  pytest / 字型不寫死 / config 集中 / type guard / 別 commit 機密，含 English summary）、
  `.github/ISSUE_TEMPLATE/`（bug_report / feature_request 含 offline-first 影響範圍勾選 +
  config.yml 把安全漏洞導向 SECURITY.md）、`.github/PULL_REQUEST_TEMPLATE.md`（含「未繞 review
  gate」自我檢查）。對外版把硬規則 #2/#3（劉老師個人工作流）轉成「先開 issue 討論」。
- [x] 🟢 **P0-5 SECURITY.md**（offline）— ✅ 2026-06-07 完成。新增 `SECURITY.md`：①「**部署前必讀**」
  強烈警告——目前後端**尚無內建驗證**（S-1 規劃中），維持 `127.0.0.1` 預設、要遠端存取請放反向代理
  + 存取控制、別裸奔 `0.0.0.0` 公網、保護機密檔 ②支援版本（僅 `main`）③漏洞回報走 **GitHub 私密
  漏洞回報 / 私訊 maintainer**（不開公開 issue）+ 3 工作天回覆承諾 + English summary。issue 範本
  config.yml 已把安全項導向本檔。

---

## Phase 1 — 安全硬底層（🔴 開源自架的致命缺口）

> 現況：後端**零驗證** + `CORS allow_origins=["*"]`。任何人連到 port 8000 就能觸發 job、
> 燒你的 Gemini 額度、刪 job、讀檔。對「localhost 自己用」OK，對「自架暴露在內網/公網」
> 不可接受。開源版必須給自架者一個安全預設。

- [x] 🔴 **S-1 單一共享 token 驗證層**（offline）— ✅ 2026-06-07 完成。實作見 `server/auth.py`：
  **HTTP middleware**（非 per-router Depends，因要一致涵蓋靜態 mount 與媒體 FileResponse）+ `/auth`
  登入端點 + `/auth/logout` + 極簡 server-rendered 登入頁（不動 React build）。沒設
  `EDUSTUDIO_API_TOKEN` → middleware no-op 全開 + 啟動大聲警告（既有 ~2400 測試零影響）；設了 →
  Bearer（CLI）或 cookie（瀏覽器，`HttpOnly`+`SameSite=Strict`+https 時 `Secure`）任一通過，否則
  瀏覽器 HTML 請求回登入框、API/媒體回 401。`/auth` 用 `hmac.compare_digest` 常數時間比對、擋 open
  redirect、表單與 JSON 皆收；`/health` 豁免（監控用、不含密鑰）。補 `tests/test_auth.py` 12 測 +
  `.env.example`/`SECURITY.md` 同步更新。全套 2399 passed（1 QR 字型假象）。設計細節：
  - 共享密鑰 `EDUSTUDIO_API_TOKEN`（環境變數）。**沒設 → server 照跑但啟動大聲警告**
    「未驗證，勿暴露公網」（保留 localhost 自用方便）。
  - **瀏覽器走 session cookie**：`/app` 出登入框 → `POST /auth` 比對 token → 種
    `HttpOnly; SameSite=Strict`（https 時加 `Secure`）cookie。**API + 媒體（mp4/png）一律靠
    cookie**（同源自動帶，解決 `<video>`/`<img>` 無法帶 `Authorization` header 的硬限制 →
    一致保護、媒體照常播放）。
  - **CLI / skill / curl 走 Bearer**：同時接受 `Authorization: Bearer <token>`（自動化用）。
  - CSRF：`SameSite=Strict` + 單一同源 `/app` 對自架單機已足夠，**不另做 CSRF token**。
  - **不做帳號系統**（拍板開源自架、非多租戶，單一共享 token 即可）。
  - 共享密鑰 `EDUSTUDIO_API_TOKEN`（環境變數）。**沒設 → server 照跑但啟動大聲警告**
    「未驗證，勿暴露公網」（保留 localhost 自用方便）。
  - **瀏覽器走 session cookie**：`/app` 出登入框 → `POST /auth` 比對 token → 種
    `HttpOnly; SameSite=Strict`（https 時加 `Secure`）cookie。**API + 媒體（mp4/png）一律靠
    cookie**（同源自動帶，解決 `<video>`/`<img>` 無法帶 `Authorization` header 的硬限制 →
    一致保護、媒體照常播放）。
  - **CLI / skill / curl 走 Bearer**：同時接受 `Authorization: Bearer <token>`（自動化用）。
  - CSRF：`SameSite=Strict` + 單一同源 `/app` 對自架單機已足夠，**不另做 CSRF token**。
  - **不做帳號系統**（拍板開源自架、非多租戶，單一共享 token 即可）。
  → 實作：FastAPI dependency 統一掛在所有 router（read 與 write 都擋，因威脅含「讀你的
  job/影片」）；`/auth` + `/app` 登入 UI；啟動警告；測試（無 token 開放+警告 / 有 token：
  cookie 通過、Bearer 通過、無憑證 401 / 媒體端點受保護 / SameSite 屬性）。
- [x] 🔴 **S-2 CORS 收緊**（offline）— ✅ 2026-06-07 完成。`allow_origins=["*"]` → 讀
  `EDUSTUDIO_ALLOWED_ORIGINS`（逗號分隔，預設 `http://127.0.0.1:8000` + `localhost:8000`，
  `*` 可臨時全開）。helper `core.config.get_allowed_origins()`（符合硬規則 #6 集中）、
  `server/main.py` 套用、補 `tests/test_cors_config.py`（6 測：預設/空白/逗號解析/萬用 +
  白名單 origin 拿到 CORS header、非白名單拿不到）、`.env.example` 補該變數。本機全套
  2367 passed（3 個 font-pixel 斷言失敗是容器缺 Noto CJK 的字型替代假象，CI 有裝字型）。
- [x] 🔴 **S-3 path-traversal 全面審**（offline）— ✅ 2026-06-07 完成。系統性審過所有吃
  path/filename 的端點（jobs artifacts/figures/images、slide_images、uploads、voices sample、
  projects、library、editor、infocards、localization、youtube SRT、themes）。**發現缺口**：3 個
  jobs 端點（artifacts/figures/images）只有字元黑名單、**缺 resolve-containment 二次防護**；其餘
  端點已用白名單 / `safe_id` / temp file / slides 的 resolve-containment，安全。**修補**：抽出共用
  `server/path_safety.py::safe_join`（字元檢查 + `.resolve()` + `relative_to` 三道），套到 3 個
  jobs 端點，並把 slides.py 重構成用同一 helper（消除重複、單一真相）。補 `tests/test_path_safety.py`
  18 測（`..`/絕對路徑/分隔符/前導點/**symlink 逃脫**/Windows `\`/多碎片其一壞 + 端點整合）。
  全套 2387 passed（1 個 QR 像素斷言失敗為容器缺 Noto 字型假象，CI 有字型）。
- [x] 🟡 **S-4 上傳硬化**（offline）— ✅ 2026-06-07 完成。在主檔案進口 `POST /upload` 補：
  **副檔名白名單**（per source_type：exam/slides_pdf 只收 `.pdf`，document 收 `.pdf/.md/.markdown/
  .txt`，強 gate）+ **MIME 寬鬆白名單**（擋 image/zip/exe 等明顯非文件，但放行瀏覽器常見的
  octet-stream/空）+ **檔名 NFC 正規化**（`unicodedata.normalize`，防組合字混淆）。大小上限/
  Content-Length 預檢/讀後複查既有已具備。`tests/test_upload.py` 補 11 測（HTTP 層擋副檔名/MIME
  + `_validate_upload` 單元 + NFC）。全套 2410 passed。
  - 註：`localization.py` 的 dub 上傳走 `tempfile`（OS 管理路徑，audit 評為低風險），本輪未動；
    若要一併套白名單可開後續小 PR。
- [x] 🟡 **S-5 secret 落地強化**（GATE→已拍板）— ✅ 2026-06-07 完成。**劉老師拍板：不加密**
  （明文 + gitignore，自架單機可接受，Fernet 靜態加密過度設計、徒增金鑰管理負擔）。改為在
  `SECURITY.md` 把機密檔處置講清楚：明文存放、**別放共享磁碟/雲端同步、別進未加密備份**（要備份
  用磁碟層級加密）、`chmod 600` 收權限、外洩即撤銷重發。無 code 變更。
- [x] 🟢 **S-6 速率限制 / 濫用防護**（offline）— ✅ 2026-06-07 完成。**自寫 token bucket**
  （`server/ratelimit.py`，純標準庫、不引入 slowapi 依賴），per-IP、預設 30/min、env
  `EDUSTUDIO_RATE_LIMIT_PER_MIN` 可調（<=0 關閉）。掛到燒額度端點：`/api/generate`、`/api/refine`、
  建 job（`POST /jobs`）、上傳（`POST /upload`），超限回 429。limiter 掛 `app.state`（per-app，
  測試每次 `create_app` 拿新滿桶，不會跨測試誤觸）。補 `tests/test_ratelimit.py` 9 測（bucket
  容量/補充/per-IP 隔離/關閉/env 解析/dependency 429）。全套 2419 passed。

---

## Phase 2 — 可靠性 P0（🔴 server 重啟不能丟工作）

> 對應 ROADMAP「P0 結構性弱點」+ [V4_WORKER_RFC.md](V4_WORKER_RFC.md)。這四條是
> 「個人用 OK、交給別人自架不可接受」的根因。**全面 D（持久化 worker）是大工程**，但可以
> 先做低成本的止血。

- [x] 🔴 **R-1 啟動時 resume 卡住的 job**（offline，止血）— ✅ 2026-06-07 完成。
  `JobStore.resume_interrupted()`：啟動時掃 `PENDING/INGESTING/RENDERING`（重啟前在跑/排隊、
  task 已沒）→ 標 `FAILED` + 訊息「server 重啟導致中斷，請重試此 job。」（寫盤持久化）。
  `AWAITING_REVIEW`（等人工）合法暫停不動、`DONE/FAILED` 終態不動。在 `main.py` startup hook
  呼叫並印出受影響數。補 `tests/test_resume_interrupted.py` 4 測（in-flight 標 failed / 暫停與
  終態不動 / 持久化跨 reload / idempotent）。最小止血、不需 worker 架構。全套 2423 passed。
- [x] 🟡 **R-2 review gate enforcement 不可繞**（offline）— ✅ 2026-06-07 完成。實作（狀態機強制
  + render 入口 assert + 測試鎖死，**不做簽章**）：
  - JobRecord 加 `reviewed`/`reviewed_at`（`extra="allow"` → 舊 state.json 無痛相容）。
  - `_run_render_phase` **入口 assert**：`require_review=True` 且 `reviewed=False` → 拒絕渲染、標
    FAILED + 硬規則 #1 訊息、不進 render（涵蓋 `/approve`、section render、任何呼叫此入口的路徑）。
  - `/approve`（從 awaiting_review/done）標 `reviewed=True`+`reviewed_at`；`run_job` 進
    `awaiting_review` 時重置 `reviewed=False`（防 re-ingest 挾帶舊 reviewed 直接 render）。
  - `tests/test_review_gate.py` 5 測（未審被擋無 artifact / 已審放行 / 非 require_review 不擋 /
    approve 標記 / 預設 False）；修 `test_runner_render_phase` fixture 標 reviewed=True（反映
    render 只在審後跑）。全套 2428 passed。
  威脅模型是「不小心跳過」非「內部惡意竄改」，簽章對自架單人過度設計，故不做。
- [x] 🟡 **R-3 sync I/O 阻 event loop 收口**（offline）— ✅ 2026-06-07 完成。審過 runner/routes
  的 async handler。**發現漏網**：① `runner._run_render_inner` 的 merge 路徑直接跑
  `get_video_duration`（ffprobe subprocess）沒包 to_thread ② `routes/localization.py` 11 個 async
  handler（translate/learning ×5/image/pdf/meeting/song transcribe/dub）全部 inline 跑 blocking
  的 Gemini/whisper/ffmpeg/OCR。**修補**：全部改 `await asyncio.to_thread(...)`（generator 方法
  靠 lazy 特性在 worker thread 迭代）。runner 其餘重活（ingest/render_video/ffmpeg/concat/intro）
  原本已包 to_thread，確認無漏。行為不變（既有 208 個相關測試 + 全套 2428 passed 驗證），純
  非阻塞改善。R-4/R-5（schema migration / 持久化 worker）為 GATE 遠期，留待與 V4 worker 一起。
- [ ] 🟢 **R-4 schema migration 框架**（GATE）— 對應 P0 #3，Round 2 已踩 naive↔aware
  datetime。要不要正式引入版本化 schema migration 是架構決策，建議**跟全面 worker（V4 D）
  一起做**，不單獨提前。先在本檔掛追蹤。
- [ ] 🟢 **R-5 持久化 job worker（V4 D，遠期）**（GATE）— RQ/Celery/SQLite 選型 RFC →
  worker 拆 process → 重啟 resume。大工程，等真有併發/雲端需求再啟動。見 V4_WORKER_RFC.md。

---

## Phase 3 — UI 收斂到 `/app` 單一（🟠 一致性 + 堵計費/審查漏洞）

> 拍板：收斂到 `/app`，`/ui` `/studio` 退場或標 legacy。**最關鍵的漏洞**：`/studio` 仍
> client-side 直連 Gemini → 繞過後端計費 + 繞過 review gate。盤點見
> [EDUSTUDIO_UI_WIRING.md](EDUSTUDIO_UI_WIRING.md)。多為前端工。

- [ ] 🔴 **U-1 `/studio` 直連 Gemini 改走後端**（offline，前端 + 確認後端端點）— 把 `/studio`
  仍 client-side 呼叫 Gemini 的路徑改打 `/api/generate` 等後端端點（後端大多現成），堵住
  「繞過計費 + 繞過審查」漏洞。或者若 U-3 直接退場 /studio，則本項併入「功能搬進 /app」。
  - ⏸️ **2026-06-08 routine 判定：完整退場為人工 gate，本輪只做非破壞性過渡。** `/studio` 源碼不在
    本 repo（拍板走退場路線），故 (a) 改 client-side 呼叫不可行；(b) server 移除 `/studio` 路由屬
    不可逆，依 U-3「`/app` 功能對等確認後再做（避免反悔）」需 **U-2③ 人工視覺驗收 `/app` 對等**先過。
    過渡止血改由 **U-3 退場 banner** 承接（頂部固定提示 + landing 標警告「`/studio` 直連 Gemini、
    繞過後端計費/審查」），把使用者導向 `/app`。**待劉老師確認 `/app` 對等後**，再開後續 PR 移除
    `/studio` 路由與 build 產物，屆時本項可結。
- [x] 🟡 **U-2 `/app` 補齊 `/studio` 缺的視覺功能 — 含逐區 refine**（offline，**拍板要做
  2026-06-07**）— 盤點顯示 `/app` 視覺站缺「海報/圖卡逐區 refine、區域選擇」（後端 refine
  圖卡未移植 = 唯一「大」缺口）。**定案：移植後端逐區 refine + 前端區域選擇 UI**（不是首發
  砍項）。其餘（16 主題/密度/長寬比/自訂 prompt）UI_WIRING 標已接完。拆小：①後端 refine
  圖卡端點移植 ②前端區域選擇/逐區 refine UI ③測試。
  - ✅ 2026-06-08 **①後端逐區 refine 端點完成**（含測試③的後端部分）。`infographic_service.
    refine_infographic_section()`：依指令重生指定 `section`（區域），merge 保留 AI 省略欄位、id
    鎖死、iconType 越界退預設（比照 `_coerce`）、imagePrompt 變動才重生圖（prompt 清空則去圖、
    `regenerate_image=False` 可只改文字省額度）；找不到 section → `ValueError`。新增 `POST
    /api/refine-section`（404 找不到 section / 400 圖卡資料無效）。`tests/test_infocards_
    infographic.py` 補 11 測（**全程 mock Gemini/生圖，不打真 API**＝offline-first；真實生圖燒額度
    仍走人工觸發）。本機全套 2436 passed（3 個 font-pixel 斷言為容器缺 Noto 字型假象，CI 權威）。
  - ✅ 2026-06-08 **②前端區域選擇/逐區 refine UI 完成**。`frontend/edustudio/app.jsx` 的
    `VisualComposer` 新增 **infographic 模式**（接後端 `mode:"infographic"`）：`RealPreview`
    渲染多區塊版面、區塊可**點選**（區域選擇）→ 開啟逐區微調面板；面板提供區塊下拉 + 修改指令
    + 「一併重生此區配圖」開關（預設關＝只改文字省額度），呼叫 `POST /api/refine-section`、以
    後端回的整張更新圖卡替換結果。版式（aspectRatio）下拉沿用。本機 `npm run build`（vite，
    node22）編譯通過。**視覺驗收待人工**（此環境無瀏覽器，依既定「前端 build 為準、人後視覺驗收」）。
  - ③前端整合視覺驗收 = 人工後驗（非 routine 程式工項）。
- [x] 🟡 **U-3 `/ui` `/studio` 標 legacy / 退場**（offline）— ✅ 2026-06-08 完成 banner 步驟（非
  破壞性，build 產物移除待 `/app` 對等確認後另開 PR）。`server/main.py` serve `/ui` `/studio` 的
  index.html 時於 `<body>` 頂注入固定退場 banner（`_inject_legacy_banner`），導向 `/app`；`/studio`
  額外標「直連 Gemini、繞過後端計費/審查」（U-1 漏洞警示）。asset 檔不注入、index/deep-link 才注入。
  landing 頁把 `/ui` `/studio` 兩張卡標 `legacy` badge + grid 標題改「舊版介面（即將退場）」+
  `/studio` 卡加 ⚠ 警告。補 `tests/test_legacy_banner.py` 5 測（連結 /app / studio 警示 / body 注入
  位置 / 無 body 前置 / 大寫 body）+ TestClient 端到端驗 index 注入、asset 不注入。全套 2443 passed
  （1 QR 字型假象）。
- [x] 🟡 **U-4 成本面板真實化收尾**（offline，接 Phase 4）— ✅ 2026-06-08 完成（C-1 影片/解析
  計帳落地後收尾）。**移除所有 mock 示意數字**：刪掉前端 `COST` 假物件（含 `$18.74` 假累計、
  「試用模式 38/50 次」、假近期呼叫列表、「試用完畢請填 API Key」這類不符開源自架定位的 SaaS
  殘留）。頂欄成本 pill 與成本面板抽屜改**共用同一份 `/api/usage` 真實統計**（App 層 `loadUsage`，
  開抽屜時重抓刷新），數字、各站花費、近期呼叫全走後端真實計帳；尚無任何 Gemini 呼叫時顯示**空
  狀態**（$0.00 + 「目前還沒有任何呼叫紀錄」）而非假數字。後端 `/api/usage` budget 從寫死 `30.0`
  改讀 `core.config.get_monthly_budget()`（env `EDUSTUDIO_MONTHLY_BUDGET` 可覆寫，集中於 config 符
  硬規則 #6），note 更新成「已涵蓋視覺／在地化／影片／解析各站」（C-1 後影片 pipeline 已計帳，舊
  note「另計」已過時）。補 `tests/test_usage.py` budget env override 測 + `.env.example` 文件。前端
  `npm run build`（vite, node22）編譯通過；視覺驗收待人工。本機全套 2447 passed（3 個 QR/journal
  字型像素假象為容器缺字型，CI 權威）。註：單價精準對齊（C-2）仍 GATE，面板成本為依用量估算、面板
  note 已標「以官方定價為準」。
- [ ] 🟢 **U-5 發布站多語上傳驅動**（GATE）— 現況多語版本選擇只是視覺。要驅動真多語上傳碰
  YouTube OAuth + 多語 metadata（方案 A 多語字幕軌後端已有），補前端驅動。
- [x] 🟢 **U-6 前端建置流程文件化**（offline）— ✅ 2026-06-07 完成。直接**把 `base:'/app/'` 寫死
  進 `frontend/vite.config.ts`**（最徹底消除 footgun：連 `vite build` 都對，不必記 CLI flag）+ 加
  `npm run build:app` 語意別名 + CONTRIBUTING 補「前端建置須知」（/app 唯一正式前端、base 已寫死、
  web//studio 為 legacy）。本機 node22 實 build 驗證產物 `index.html` 正確引用 `/app/assets/...`
  且與既有 commit 產物**完全一致**（零 diff）。

---

## Phase 4 — 計費準確 + 模型一致性（🟡 信任與成本）

> 自架者最在意「這會花我多少錢」。現況計費**只算視覺/在地化**，最大宗的影片 render
> pipeline 完全沒計帳（HANDOFF 待加強 #1）。

- [x] 🔴 **C-1 影片 pipeline Gemini 呼叫接計帳**（offline）— ✅ 2026-06-08 完成。新增
  `core.usage.record_text_now(station, model, prompt, response, label)` 便捷層（自動填 UTC ts +
  數字元，datetime 只落這層、UsageStore 核心仍純可重現），接上四個 chokepoint：`outliner.
  _call_outline_gemini`（station=video/outline）、`scriptor._call_with_retry`（video/script:<id>）、
  `slide_ingest` 章節切分 + 逐頁旁白（video/chapters、narration）、`solve` 三 pass（material/
  identify、solve:<num>、svg）。成本面板新增「影片」「解析」兩站（站別 label 早已預留）。補
  `tests/test_usage_pipeline.py` 5 測（字元/成本/ts/站別分組 + outliner 注入 fake genai 驗計帳
  確實接上，**全 mock 不打真 API**＝offline-first）。本機全套 2446 passed（3 個 font-pixel 斷言為
  容器缺 Noto CJK 字型假象，CI 權威）。註：多模態（圖片 input）僅計 prompt 文字字元，沿用既有
  char-based 近似模型。
- [ ] 🟡 **C-2 單價對齊真實**（GATE，需查官方定價）— 現況單價是估算。對齊 Gemini 3 系列 +
  GCP TTS + （未來）image 真實單價。定價會變動 → 抽成設定常數 + 文件註明「以官方為準」。
- [ ] 🟡 **C-3 旁白模型遷 3.x**（GATE，需開額度驗證品質）— `slide_ingest.py:43`
  `MODEL = "gemini-2.5-flash"`（將淘汰）。**M 軸完成後這只是改角色表 `text.fast` 一個值**。
  3.5-flash 實測接受 `thinking_budget=0`，但**旁白品質要先驗**再換。寫成 A/B proposal，劉老師
  開額度跑過再切。（劉老師 2026-06-07：需額度會給權限。）
- [ ] 🟢 **C-4 `gemini-3.1-pro-image` 等開放再換**（GATE）— 劉老師想用但 API 未開放。等開放
  從 `gemini-3-pro-image` 換（`core/infocards/models.py`）。掛追蹤。
- [x] 🟢 **C-5 模型 id 自我健檢**（offline）— ✅ 2026-06-09 完成。新增 `tools/check_models.py`：蒐集
  系統「會送去 Gemini」的全部 model id（**角色登錄表 `core/models.py` 經 `resolve()`** ＝含設定頁
  逐角色 `model_roles` 覆寫 + legacy `text_model`/`image_model` 覆寫 + 內建預設；**＋設定頁文字/圖片
  下拉可選清單** `core/infocards/models.py` 的 `TEXT_MODELS`/`IMAGE_MODELS`），呼叫 `client.models.
  list()` 比對哪些 id 在這把 key 底下已不存在（404 風險，本 repo 有 preview id 404 前科），標紅輸出。
  只查 `gemini` provider 角色（`tts` 等非 Gemini 後端跳過）；蒐集/比對拆純函式（`collect_configured_
  models`/`evaluate`），**API 端可注入 fake**＝全程不打真 API（offline-first）；缺 `GEMINI_API_KEY`
  只印「會用到哪些 id」+ exit 2，全綠 exit 0、有缺 exit 1，`--json` 機器可讀。補 `tests/test_check_
  models.py` 18 測（角色覆蓋/排除 tts/下拉清單/去重排序/設定覆寫經 resolve/前綴正規化/exit code/JSON）。
  本機全套 2484 passed（3 個 QR/journal 字型像素為容器缺 Noto CJK 假象，CI 權威）。並進 M 軸：蒐集
  來源已含角色登錄表全部角色，換代後同支即驗新表。註：M-3 設定頁「未知 id 健檢顯示」可日後串本工具輸出。

### M 軸 — 模型抽象與可插拔後端（🔴 結構性，劉老師 2026-06-07 指定）

> **痛點（劉老師提）**：模型 id **散落**（`slide_ingest.py:43` 寫死 `gemini-2.5-flash`、
> `core/infocards/models.py`、`settings.py`、`config.py`、scriptor/outliner…）+ 名稱/版號不
> 一致 + preview id 會 404。要讓「模型設定/修改**獨立於專案之外**」，未來 4.0/5.0/6.0 出來
> 系統零（或極小）改動。
> **拍板（2026-06-07）：做 Option A（角色登錄表）+ 介面設計成 B-ready**（provider 抽象之後
> 再加，不重構）。B 的「本機 provider」就是 Phase 9 F9-3 本機可插拔模型。

- [x] 🔴 **M-1 角色登錄表 `core/models.py`（offline，A 核心）**— ✅ 2026-06-08 完成。新增
  `core/models.py`：6 個**邏輯角色**（`text.fast`/`text.pro`/`vision`/`image.fast`/`image.pro`/
  `tts`）→ `(provider, model_id)` 單一真實來源。`resolve(role)` 解析優先序＝設定頁逐角色
  `model_roles`（M-3 UI 會寫入，現在先讀＝向前相容）→ legacy 單值欄位 `text_model`/`image_model`
  （向後相容，保留現行 `get_gemini_model()` 行為，讓 M-2 換接 runtime 不變）→ 內建 `DEFAULTS`。
  provider 維度 B-ready（A 階段 LLM/視覺/生圖恆 gemini；tts 反映既有 edge/f5/google 後端，預設
  `edge`，不硬塞未驗證 gemini TTS id 避免 preview 404）；未知角色 `ValueError`（type guard）。
  預設 id 對齊既有 `core/infocards/models.py`（live 實測的 Gemini 3 系列）。補
  `tests/test_models_registry.py` 12 測（鎖角色集合/預設表/type guard/legacy 覆寫/逐角色覆寫/
  空值 fallback，**全 tmp 隔離不打 API**）。全套 2459 passed（3 個字型像素假象為容器缺 Noto CJK，
  CI 權威）。換接散落硬編 id＝M-2、設定頁逐角色管理＝M-3、provider adapter 介面＝M-4。
- [~] 🔴 **M-2 全面換掉寫死 id（offline）**— 把 `slide_ingest.py` / `core/infocards/models.py` /
  scriptor / outliner / translate / 其餘 chokepoint 的硬編 model id **全部改呼叫 `resolve()`**。
  一處一處改、跑 pytest（硬規則 #7）。完成後「換模型 = 改一個表/設定頁」。
  - ✅ 2026-06-08 **視覺/infocards 世界已換接（行為不變）**。`core/infocards/gemini.py`（生 JSON/
    生圖 fallback：`DEFAULT_TEXT_MODEL`/`DEFAULT_IMAGE_MODEL` → `resolve_id(text.fast/image.fast)`）、
    `server/routes/infocards.py::_resolve_models`（`get_setting("text_model") or DEFAULT_*` 鏈 →
    `resolve_id()`，並向前相容 M-3 逐角色設定）、`core/infocards/poster_service.py`（海報 pro 生圖
    `IMAGE_MODELS["pro"]["id"]` → `resolve_id(image.pro)`）全部改走角色登錄表。**完全行為不變**：登錄表
    預設 id 與這些 chokepoint 原本的 3.x 預設一字不差（text.fast=3.5-flash、image.fast=3.1-flash-image、
    image.pro=3-pro-image），只是改成單一真實來源 + 多帶 `model_roles` 覆寫感知。本機全套 2459 passed
    （3 個 QR/CJK 主題像素斷言為容器缺 Noto 字型假象，CI 權威）。
  - ⏸️ **影片/解析文字 pipeline 的硬編 id 換接 = C-3 GATE，本輪不動。** `slide_ingest.py:43`、
    `solve.py:30`、`core/config.py:170 GEMINI_MODEL` 等目前寫死 `gemini-2.5-flash`；而登錄表 `text.fast`
    預設是 `gemini-3.5-flash`。把這些 chokepoint 換成 `resolve("text.fast")` **會把旁白/解題默默從 2.5
    遷到 3.5**，這正是 **C-3（旁白模型遷 3.x，GATE，需開額度 A/B 驗品質）**。故此部分留待 C-3 拍板/
    開額度後一併換（屆時就是「改登錄表一個值 + 換 call site」）。`mermaid_render.py`/`ideate`/`diagram_*`
    等 GATE 半成品（F-5）同理留待各自項目。
- [x] 🟡 **M-3 設定頁模型管理升級（offline）**— ✅ 2026-06-08 完成。設定頁從「文字/圖片各一個下拉」
  升級成 **逐角色可配**：新增設定欄位 `model_roles`（dict，逐角色 model id 覆寫），`resolve()` 早已
  最高優先讀它（M-1 預留），現在設定頁能寫入＝閉環。`core/models.py` 加 `role_catalog()`（單一真實
  來源：role/label/kind/default，**tts 不列**——走獨立 TTS 子系統避免「選了不生效」誤導）；
  `core/settings.py` 加 `model_roles` 至 `_KNOWN` + `_clean_model_roles()`（只留合法角色→非空字串、
  空 dict 清除，呼應 type guard）+ `public_view` 曝光；`/settings` 端點補 `model_roles` patch 欄位
  與 `roles` catalog。前端 `app.jsx` SettingsDrawer 改逐角色下拉（依 kind 挑 text/image 候選、留空＝
  系統預設）。legacy `text_model`/`image_model` 仍留作 `resolve()` 較低優先 fallback（向後相容、不孤兒）。
  補測 `test_settings.py`（roundtrip/清洗未知角色/空清除/非 dict/public_view/路由 catalog+寫入）+
  `test_models_registry.py`（catalog 形狀+排除 tts）。本機 `npm run build`（vite/node22）編譯通過、全套
  2466 passed（3 個 QR/journal 字型像素為容器缺 Noto 假象，CI 權威）。註：未知 id 健檢顯示（接 C-5）
  待 C-5 工具落地後再串。
- [x] 🟢 **M-4 provider adapter 介面（B-ready stub，offline）**— ✅ 2026-06-09 完成。M-1/M-2/M-3
  落地後評估：先把介面座位備好，讓 Phase 9 F9-3 能零摩擦 slot-in。新增 `core/providers.py`：
  `Provider` 協定（`runtime_checkable`，三能力面 `generate_text` / `generate_image` / `tts`）+
  `GeminiProvider`（A 階段唯一 LLM/視覺/生圖 provider：`generate_text` 走 google.genai、
  `generate_image` **委派既有** `generate_image_b64`＝包現有呼叫；`tts` 非其職責 →
  `NotImplementedError`，本 repo 語音走獨立 `tts_backend` 子系統）+ `register_provider` /
  `get_provider`（未知 provider→`ValueError`）/ `provider_for_role`（`resolve()` 拿 provider+model
  id 的 B-ready 座位）。**只抽介面不換行為**：現有散落呼叫端本輪不改線，仍各自運作；genai 呼叫隔離成
  模組層 `_gemini_text_call`＝B 階段抽換點 + 測試注入點。補 `tests/test_providers.py` 18 測（協定符合/
  registry 單例+未知/逐角色 model 解析+設定覆寫/usage 計帳/生圖委派/tts NotImplementedError/
  provider_for_role text+非法角色+tts 未登記，**全 monkeypatch 不打真 API、不需裝 genai**）。本機全套
  2500 passed（1 QR 像素為容器缺 Noto CJK 字型假象，CI 權威）。B 階段（F9-3）只要新增實作此協定的
  class + `register_provider`，呼叫端零改動即生效。

---

## Phase 5 — 部署就緒（🟡 開源自架的「跑得起來」）

> Docker scaffold 已有（Dockerfile + docker-compose + .env.example），但**未跨平台實測**，
> 也無 production 反代/TLS 指引。對應 ROADMAP 階段 1 A。

- [ ] 🔴 **D-1 `docker compose up --build` 跨平台實測**（GATE，需劉老師本機跑）— Linux/Win/Mac
  各驗一遍，修踩到的問題（字型、volume、healthcheck）。產出「實測 OK」結論 + 修補。
- [x] 🟡 **D-2 production 設定範本**（offline）— ✅ 2026-06-09 完成。新增
  `docker-compose.prod.yml`（疊在 base 之上的 production override，用 `-f docker-compose.yml -f
  docker-compose.prod.yml` 帶）：**port 只綁 `127.0.0.1`**（對外走反向代理、不裸暴露）、container
  log 走 **json-file driver + rotation**（`max-size 10m`×`max-file 5`，補 base compose 的 log
  rotation TODO）、`restart: always`、`no-new-privileges:true`、`stop_grace_period`。`--reload`
  本來就沒開（Dockerfile `CMD` 直接 `python -m server.main`，於 override 註明）。新增
  `docs/DEPLOYMENT.md`：一鍵起 prod 容器指令 + base↔prod 對照表 + **「上線前安全 checklist」**把
  Phase 1 串成逐項（S-1 設 token / S-2 收 CORS / 放反向代理+TLS / S-6 維持 rate limit / S-5 機密檔
  權限 / 月預算）+ 運維備忘（持久化、R-1 重啟不丟工作、review gate 不可繞、磁碟、健康檢查）+ 指出
  D-1/D-3/D-4 後續。純設定/文件，無 code 變更（未動 server/core/schemas/runner）。
- [x] 🟡 **D-3 reverse proxy + TLS 指引**（offline，文件）— ✅ 2026-06-09 完成。新增兩份可複製範本：
  [`deploy/nginx.conf.example`](deploy/nginx.conf.example)（http→https 轉址、certbot/Let's Encrypt
  簽發註解）與 [`deploy/Caddyfile.example`](deploy/Caddyfile.example)（自動 TLS、零手動憑證）。兩份都
  預先處理好踩雷點：**上傳上限對齊** `200m`/`200MB`（對齊 `server/routes/uploads.py` 的 `MAX_UPLOAD_SIZE`，
  代理層預設太小會在傳大檔時先回 413）、**長請求逾時** 放寬到 600s（影片 render / 同步 Gemini 呼叫不被切成
  504）、**轉發 `X-Forwarded-For`/`-Proto`**（per-IP rate limit S-6 看真實來源、cookie `Secure` 判定正確）、
  **`Authorization`+cookie 透傳**（S-1 驗證所依）、HSTS。`docs/DEPLOYMENT.md` 補「反向代理 + TLS」一節
  （nginx vs Caddy 選用對照表 + 踩雷點說明 + 「反代非驗證替代品、仍要設 token」提醒）並消除原 D-3「規劃中」
  佔位。純文件/設定，無 code 變更（未動 server/core/schemas/runner）。
- [ ] 🟡 **D-4 F5 GPU passthrough 文件**（GATE，需 GPU 環境實測）— nvidia-docker 跑 F5-TTS
  的設定 + 「沒 GPU 自動退 edge/google TTS」說明。
- [x] 🟢 **D-5 健康檢查 / 啟動自檢**（offline）— ✅ 2026-06-09 完成。新增 `core/selfcheck.py`：
  server 啟動時印一輪**綠/紅環境自檢**（ffmpeg/ffprobe 在不在＝critical、三個字型在不在＝critical、
  GEMINI key 設了沒＝黃字警告非 critical），缺核心相依時多印一行 ⛔ 醒目總結指引去補。`/health`
  雖已回同類診斷，但那要主動打端點才看得到；自架者第一次 `docker compose up` 最常踩的雷（沒裝
  ffmpeg、容器缺 Noto 字型、忘設 key）改在 **啟動 log** 一眼可見。純函式 `collect_checks()`／
  `format_report()`（不碰 stdout＝好測）＋ `print_startup_selfcheck()`，在 `server/main.py` startup
  hook 呼叫。**不阻擋啟動**（缺東西只警告、server 仍可瀏覽/設定）。補 `tests/test_selfcheck.py` 8 測
  （全綠／ffmpeg 缺／字型缺 critical、缺 key／空 key 為警告非 critical、報告綠紅標記與總結、print 回傳，
  **全 monkeypatch 不碰真 ffmpeg/字型/API**）。本機全套 2506 passed（3 個 QR/journal 字型像素為容器
  缺 Noto CJK 假象，CI 權威）。
- [x] 🟢 **D-6 requirements 分層說明**（offline）— ✅ 2026-06-09 完成。README（中英雙語）新增「依賴
  分層 / Dependency layers」一節：core/optional/song/dev 四層表格（裝什麼、加了什麼、不裝會怎樣）+
  系統相依（ffmpeg、Noto CJK 字型，非 pip，原 quick-start 漏寫）+ 字型 env 覆寫 + Dockerfile 已內建。
  順手補回**漏報的兩個 optional dep**：`faster-whisper`（STT，lazy import、自動 GPU→CPU）與
  `python-pptx`（PPTX 匯出，lazy import）——tech stack 有列、code 有用，但先前任一 requirements 檔
  都沒宣告 → 補進 `requirements-optional.txt` 並註明各自驅動的功能與「沒裝只該功能優雅報錯」。純文件
  /設定，無 code 變更（未動 server/core/schemas/runner，故不需跑 pytest）。

---

## Phase 6 — 文件就緒（🟡 陌生人能上手）

> 整合後文件有**定位漂移**：`claude.md` 還停在舊定位「教學影片自動生成平台」、HANDOFF 寫死
> 劉老師 Windows 本機路徑（`D:\...`）。開源前要去個人化 + 對齊 eduStudio 全貌。

- [x] 🔴 **DOC-1 `claude.md` 更新到 eduStudio 整合後定位**（offline）— ✅ 2026-06-09 完成。
  把開頭從「教學影片自動生成平台」+ 三 Track A/B/C 舊圖 + Gemini 2.5 改寫成 **eduStudio 教學內容
  工作站**整合定位：四條 track（🎬影片 / 🎨視覺 / 🌐在地化 / 🎵Song MV）共用單一 FastAPI 後端 +
  收斂到 `/app` 的整合架構圖、現行 **Gemini 3 系列**模型（含旁白仍 2.5 待 C-3 GATE 的註記）、
  **模型抽象 M 軸**（`core/models.py` 角色登錄表 + `core/providers.py` provider 介面 +
  `tools/check_models.py` 健檢）、安全與部署現況（auth/CORS/path-safety/rate-limit/resume/反代）。
  硬規則對齊現行紀律（review gate 不可繞 + offline-first + 字型不寫死 + config 集中 + type guard +
  schema migration + 別 commit 機密 + 動 server/core/runner/schemas 跑 pytest），移除已過時的
  Track A/C 規則。保留作者/溝通風格/熟悉度/Git 同步等仍有效的 maintainer context。純文件,無 code
  變更（未動 server/core/schemas/runner,故不需跑 pytest）。
- [x] 🟡 **DOC-2 去個人化 / 去 Windows 硬路徑**（offline）— ✅ 2026-06-10 完成。掃過全 docs 的
  Windows 個人絕對路徑並去個人化（保留作者署名/maintainer context，只移除「換台機器就讀不懂」的
  硬路徑）：① `HANDOFF.md`「位置與環境」把 `D:\Project_CodingSimulation\...` / `C:\Python\Python312-64`
  / `C:\Users\user\.claude\...` 改成「clone 到任一目錄、以 repo 根為基準」+ venv/`uv` 說明 + 字型走
  `CLAUDE_FONT_PATH`（附三平台預設）+ memory 路徑改 `~/.claude/...` / `%USERPROFILE%`。② `docs/onboarding.md`
  把 `D:/path/to/midterm.pdf`、`D:/Teaching/Materials` 例子改相對 `./path/...` / `./materials`。
  ③ `docs/ideate-design.md` watched_folders 例子 `D:/Teaching/...` → `./materials` / `./exams`。
  ④ `docs/GOOGLE_TTS_SETUP.md` 憑證路徑補 Linux/macOS `export` 範例、Windows 例子改中性 `C:\path\to\...`。
  純文件，無 code 變更（未動 server/core/schemas/runner，不需跑 pytest）。註：歷史紀錄裡的路徑
  （CHANGELOG/TODO 的 `D:/Dropbox/` 為「已搬進 repo」的事實記述）與 skill 對話範例刻意保留；routine
  內部 `ROUTINE_ADVANCE_PROMPT.md` 的本機路徑屬個人工作流非對外文件，不在本輪。
- [x] 🟡 **DOC-3 端到端 onboarding 文件**（offline）— ✅ 2026-06-10 完成。把 `docs/onboarding.md`
  從舊的「研究室 onboarding（autoSolverVideo / Track A-B-C / `/ui` / `web/` / 舊模型）」整份改寫成
  **陌生老師 0→1 主線**：§0 你會得到什麼 → §1 系統需求表（含 ffmpeg/Noto 非 pip、唯一必填
  `GEMINI_API_KEY`）→ §2 安裝（A. Docker 最少踩雷 / B. 本機 Python venv + `npm run build`，base 已
  寫死）→ §3 配 key（env 或設定頁）→ §4 **產第一支影片**（考卷 PDF GUI 流程：選課→上傳→ingest→
  **awaiting_review 逐題人工審查**→approve→render→下載，強調 review gate 核心價值；§4a CLI
  `submit_job.py`）→ §5 **上 YouTube**（5a 一次性 OAuth client_secret 設定 + 5b GUI/`publish.py` 上傳、
  配額註記）→ §6 常見錯誤排查表（對齊現況：空白頁=沒 build、字型方框、首跑 F5 1.3GB、重啟 resume、
  暴露需 token）→ §7 下一步（指向 DEPLOYMENT/CONTRIBUTING/SECURITY）。截圖位置以 `<!-- 截圖：… -->`
  預留待人工補（此環境無瀏覽器，依既定「文字步驟可獨立完成、視覺後驗」）。純文件，無 code 變更（未動
  server/core/schemas/runner，故不需跑 pytest）。
- [x] 🟢 **DOC-4 架構文件 / ARCHITECTURE.md**（offline）— ✅ 2026-06-10 完成。新增
  [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)，給「想改 code 的人」的地圖：① 三層俯瞰
  ASCII 圖（`frontend` build→`web/eduapp` /app · `server` middleware/routes/JobStore/runner ·
  `core` 純內容引擎不依賴 FastAPI · 外部相依 Gemini/ffmpeg/TTS/字型）② job 狀態機
  （pending→ingesting→(review gate)→rendering→done/failed，含 **render 入口 assert 不可繞** 與
  R-1 重啟止血、state.json 持久化）③ 四條 track 怎麼共用同一條 pipeline（來源 adapter 差異 →
  共同中介 `deck.json`（review 審的就是它）→ 共用 render，附對照表 + 分流點 `_run_render_inner`，
  並點出視覺/在地化是同步非 job-based）④ 橫切關注點（M 軸模型抽象/計帳/安全 middleware/config 集中/
  type guard）⑤ 前端建置（`/app` 唯一、`/ui`·`/studio` legacy 退場）⑥「想動哪裡先看哪裡」入口檔 +
  必跑測試對照表，含硬規則提醒（review gate 不可繞 / C-3 旁白模型 GATE 別自換 / 動 server·core 跑
  pytest）。純文件，無 code 變更（未動 server/core/schemas/runner，故不需跑 pytest）。
- [ ] 🟢 **DOC-5 demo 影片 / 截圖**（GATE，需劉老師錄）— README 放一支 60 秒 demo（用自己的
  系統產，吃自己狗糧）。

---

## Phase 7 — 測試與發佈（🟡 品質護網 + 正式版本）

- [x] 🟡 **T-1 端到端整合測試**（offline）— ✅ 2026-06-10 完成。新增 `tests/test_e2e_pipeline.py`：
  用 **FastAPI TestClient + 真 pipeline** 串「整條接線不斷」happy-path——建 job（`POST /jobs`）→
  ingest → review gate 停 `awaiting_review` → 看 draft（`GET /draft`）→ 人工 approve（`POST /approve`）→
  render → DONE → 下載 artifact（`GET /artifacts/{name}`），走真實 `run_job` / `_run_render_phase` /
  JobStore / route 接線，只 mock **兩個外部邊界**：Gemini ingest 用 `EXAM_PDF`+`mock=True`（走
  `solve.mock_output()` 離線資料）、ffmpeg/TTS render monkeypatch `core.render_video` 只寫 fake mp4/srt
  ＝offline-first 不打真 API、不跑 ffmpeg。第二支測試證明 **R-2 review gate（硬規則 #1）在整條 pipeline
  裡仍不可繞**：approve 前 render 被擋 FAILED 且根本沒進 `render_video`、無 artifact，approve 後才放行
  DONE。本機全套 2509 passed（2 個 QR/theme 字型像素為容器缺 Noto CJK 假象，CI 權威）。註：CI 端到端
  重依賴分 job 處理（test.yml）可後續隨 T-2 一併評估。
- [x] 🟡 **T-2 CI actions 升版 / 護網補洞**（offline）— ✅ 2026-06-10 完成。① **Node actions 已是
  最新主版**（`actions/checkout@v4`、`actions/setup-python@v5`、`actions/setup-node@v4`，無
  `upload-artifact@v3` 等 Node16 棄用節點）→ HANDOFF #6 的「消棄用警告」實際已無待辦。② **補上
  真正的護網漏洞**：CI 先前只 `tsc --noEmit` legacy `web/`（`/ui`·`/studio`，已標 legacy 退場），
  **唯一正式對外前端 `frontend/`（`/app`，React 19+Vite，U-6 base 寫死 `/app/`）從未進 CI** ——
  `app.jsx` 壞了不會被擋。新增 `frontend-app-build` job 跑 `npm ci && npm run build`（純 JSX 無
  tsconfig，`tsc --noEmit` 不適用 → vite build 即護網：JSX 解析錯／import 缺失／建置失敗都紅；產物
  到 gitignore 的 `web/eduapp` 不污染 repo）。保留 web typecheck 守 legacy 退場前不退步。本機 node20+
  `npm run build` 通過。純 CI 設定，無 code 變更（未動 server/core/schemas/runner，故不需跑 pytest）。
  - ⏸️ 「裝 ffmpeg 跑少量真 render」nightly job 留作後續：真 render 會跑 ffmpeg/TTS，且文字 pipeline
    要不打 Gemini 才 offline（須 `mock=True` 固定 fixture）；牽涉額度/外部服務取捨，另開項評估，不併本輪。
- [~] 🟢 **T-3 版本 / tag / CHANGELOG / Release**（offline）— 訂 `v1.0.0`（開源首發）語意化版本，
  `docs/CHANGELOG.md` 已有 → 補 release notes，打 git tag + GitHub Release。
  - ✅ 2026-06-10 **release notes 已備好（offline 部分）**。`docs/CHANGELOG.md` 原停在 v4
    （2026-05-15 iter 48），完全沒涵蓋產品化推出的 36 個 PR（#15–#50）。新增 **v1.0.0 —
    產品化推出（開源自架首發候選）** 一段：按 Phase 0–7 分節列出每項（P0/S/R/U/C/M/D/DOC/T 系列）
    對應 PR + 一句內容，含測試成長（467→2509 passed）與驗收門檻達成度。CHANGELOG 標題從「v4 階段
    累積進度」改為通用「CHANGELOG」並指回本清單。純文件，無 code 變更（未動 server/core/schemas/
    runner，故不需跑 pytest）。
  - ⏸️ **實際 git tag `v1.0.0` + GitHub Release 發佈時機 = 劉老師拍板**（routine 不自主做：建立公開
    Release 屬對外、不可逆的首發里程碑決策；且首發前還有兩項本機 GATE 未跑 —— D-1 `docker compose
    up` 跨平台實測、D-4 F5 GPU passthrough 實測）。release notes 既已備好，劉老師確認後一鍵發佈即可
    （`git tag -a v1.0.0 -m "..." && git push origin v1.0.0` → GitHub Release 貼 CHANGELOG v1.0.0 段）。
    待發佈後本項可結。
- [x] 🟢 **T-4 README badge / 截圖牆 / 一鍵 demo**（offline）— ✅ 2026-06-10 完成（offline 門面部分）。
  README 補上**實時 CI/tests 狀態 badge**（`actions/workflows/test.yml/badge.svg`，先前只有靜態
  `status:active` 與已有的 MIT 授權 badge，缺真正反映綠/紅的 CI badge）、新增 **`docker compose up`
  一鍵體驗指引**（中英雙語各補一段「一鍵體驗（Docker）」放在原始碼安裝法之前——內附 image 已帶
  ffmpeg+CJK 字型、`cp .env.example .env` → `docker compose up -d --build` → 開 `/app/`，並提醒沒設
  `EDUSTUDIO_API_TOKEN` 前別開公網 port、指回 DEPLOYMENT.md）、新增**截圖牆 section**（中英雙語 4 格
  表格：`/app` 工作站 / 人工審查關卡 / 視覺工作台 / 成本面板，以 `docs/screenshots/*.png` 預留位 +
  `<!-- screenshot: … -->` 佔位）。順手把 `docker-compose.yml` 註解頭從舊名 `autoSolverVideo` + 指向
  legacy `/ui/` 更新成 eduStudio + 指向 `/app/`，讓一鍵 demo 前後一致。純文件/設定，無 code 變更
  （未動 server/core/schemas/runner，故不需跑 pytest）。
  - ⏸️ **實際截圖圖檔 = 人工後補**（此環境無瀏覽器，依既定「文字步驟可獨立完成、視覺後驗」，比照
    DOC-3 的截圖佔位）：把四張 `docs/screenshots/*.png` 放進去即自動顯示。與 **DOC-5（demo 影片，GATE）**
    一併由劉老師用跑起來的系統截/錄。

---

## Phase 8 — 功能半成品收尾（🟢 非擋發佈，看排序插隊）

> 這些是「有了更完整、缺了不擋開源首發」的長尾。詳細設計各有 RFC/proposal，這裡只掛主線
> 追蹤，**不重複內容**，細節看 TODO.md / 各 RFC。

- [ ] 🟡 **F-1 雙語字幕燒軌 + 多軌上傳**（GATE）— schema 透傳 + 渲染燒第二軌 + publish 多軌。
  翻譯層（本機 Ollama）+ 雙軌組裝已完成，剩渲染/上傳。見 TODO 雙語字幕段。
- [ ] 🟢 **F-2 SONG M1 自動對齊子系統**（GATE）— Demucs + WhisperX 自動對齊（卡 whisperx 依賴
  地獄，M0 已用手動時間軸走通）。M0~M3 渲染/生圖/server flow 已完成。
- [ ] 🟢 **F-3 CARD 軸（資訊圖卡→講解影片）**（GATE）— 等劉老師對 4 個開放問題拍板寫 RFC。
  原料齊備（poster_service 已出 imageUrl+prompt）。見 TODO CARD 軸段。
- [ ] 🟢 **F-4 EBOOK 軸（EduForge 電子書輸出）**（GATE）— v5.0 大功能，RFC §9 六問待拍板 +
  排程。見 EBOOK_OUTPUT_RFC.md。
- [ ] 🟢 **F-5 ideate.py / diagram_gen.py scaffold 收尾**（GATE）— 兩個半成品模組（自動內容
  企劃 / 工程圖 AI），多需 Gemini 額度驗證。見 ROADMAP 階段 2 B/E。

---

## Phase 9 — 產品差異化新功能（🟡 劉老師 2026-06-07 挑選納入）

> 互動 session 從建議清單挑這 4 個進場（貼合「老師內容工作站 + 人工把關 + 自架」主軸）。
> 沿用 offline-first：碰 Gemini/雲端額度的部分寫 proposal STOP。各項先寫小 RFC 再拆 PR。

- [ ] 🟡 **F9-1 review 數值二次校驗**（GATE，強化核心賣點）— AI 產出的數字/公式自動標「可疑
  點」輔助 reviewer：① 二次獨立模型 pass 比對數值 ② 數學步驟符號/單位一致性檢查。**只標記不
  自動改**（不繞硬規則 #1，是輔助人工不是取代）。降低 reviewer 負擔 = 把核心差異化做深。
  先寫 `docs/REVIEW_ASSIST_RFC.md` 拆子任務。碰額度（二次模型）→ proposal。
- [~] 🟡 **F9-2 課程術語/讀音表 glossary**（offline 可起頭）— `pronunciation.json` 升級成
  **per-course glossary**（理工術語固定譯名 + 讀音 + 縮寫展開，材力/自控各一套）。接進 Project
  「一課一工作空間」：產旁白/翻譯時套該課 glossary → 術語一致。schema + 套用層 offline 可做；
  自動建議術語碰額度 → proposal。
  - ✅ 2026-06-11 **第一刀：schema + TTS 套用層完成**。新增 `core/glossary.py`：`GlossaryEntry`
    （term + reading 讀音覆寫 + 各語言固定譯名 `translations` + 縮寫展開 `expansion` + 別名 aliases +
    note；term/course 非空 type guard）、`Glossary`（per-course），純函式套用層 `to_pronunciation_map`
    （→ TTS 讀音）/`translation_map(lang)`（→ 翻譯固定譯名）/`expansion_map`（→ 縮寫全稱），surface form
    展開 + longest-first，加 `load_glossary`/`save_glossary`（per-course `glossary.json`，路徑慣例
    `glossary_path_for(project_dir)`，沿 pronunciation 寬容語意：缺檔回 None、壞檔嚴格拋）。`tts_backend.
    normalize_text` 加**選填** `extra_pronunciation`（per-course 讀音與全域 `pronunciation.json`
    longest-first 合併、同 key 課程優先；預設 None＝既有 caller 零影響）。補 `tests/test_glossary.py`
    22 測（schema 驗證/各 map/roundtrip/缺檔/壞檔/normalize 整合覆蓋全域，**全 tmp 隔離不打 API**＝
    offline-first）。本機全套 2529 passed（3 個 QR/journal 字型像素為容器缺 Noto CJK 假象，CI 權威）。
  - ✅ 2026-06-11 **第二刀：掛進 ProjectStore（一課一 glossary）完成**。`core/project.py` 的
    `ProjectStore` 加 `get_glossary(pid)` / `save_glossary(pid, glossary)`：每課 glossary 落
    `{root}/{pid}/glossary.json`（沿 `core.glossary.glossary_path_for` 路徑慣例），**與 `project.json`
    分檔**（術語可上百條、跟 project 生命週期不同步，分檔避免改一條術語就重寫整個 project.json）。
    讀無檔回 None（寬容語意）、對不存在的 pid 讀/寫丟 `ProjectNotFoundError`（glossary 必依附 project，
    不靜默回 None 掩蓋），全程 RLock 內完成。補 `tests/test_project.py` 4 測（無檔回 None / save→reload
    跨 store 持久化 / 逐課隔離 / 不存在 project 拋錯，**全 tmp 隔離不打 API**＝offline-first）。本機全套
    2533 passed（3 個 QR/journal 字型像素為容器缺 Noto CJK 假象，CI 權威）。
  - ✅ 2026-06-11 **第三刀：glossary 編輯 API（GET/PUT）完成**。`server/routes/projects.py` 補
    `GET /projects/{pid}/glossary`（取該課術語表）/ `PUT /projects/{pid}/glossary`（整張覆寫）
    兩端點，薄轉接到既有 `ProjectStore.get_glossary` / `save_glossary`（第二刀已落地、含 RLock 與
    路徑慣例）。GET 兩種 404 以 detail 區分——「project 不存在」vs「此課尚未建立 glossary」——讓編輯
    UI 能分辨「沒這門課」與「課在但還沒建表」（後者可開空表起頭再 PUT）。body 直吃 `core.glossary.
    Glossary`，term/course 非空 validator 在 HTTP 層生效（空 term → 422）。pid（資料夾鍵）與
    glossary.course（人讀課名）各自獨立、不強制相等。補 `tests/test_projects_route.py` 6 測（未建
    →404 detail 區分 / PUT→GET roundtrip 跨 store 持久化 / 整張覆寫 / 不存在 project 404 / 空 term
    422 / 逐課隔離，**全 tmp 隔離不打 API**＝offline-first）。本機相關子集 66 passed、全套 2539 passed
    （3 個 QR/journal 字型像素為容器缺 Noto CJK 假象，CI 權威）。
  - ✅ 2026-06-11 **第四刀：translation_map → translate() 橋接完成**。`core/glossary.py` 加純函式
    `to_translation_rules(glossary, lang)`：把該課固定譯名整理成逐行「來源寫法（term + 別名，
    longest-first，`/` 並排）→ 目標譯名」文字塊，直接餵 `TranslateGemmaService.translate(...,
    glossary=...)`（會被 `_format_custom_rules` 包成 strict 術語規則塞進 prompt），讓翻譯層強制術語
    一致——對應 TTS 側 `to_pronunciation_map()` → `normalize_text` 的同類橋接（補上 `translation_map`
    回 dict、但 translate 吃 str 的缺口）。只收該 lang 有設譯名的 entry、都沒有回空字串（translate
    對空字串 no-op＝既有 caller 零影響）。補 `tests/test_glossary.py` 6 測（逐行格式/別名並排/限該
    lang/缺譯名回空/空 glossary/橋接進 `_format_custom_rules` + 空字串 no-op，**全 offline 不打 API**）。
    本機全套 2545 passed（3 個 QR/journal 字型像素為容器缺 Noto CJK 假象，CI 權威）。
  - ✅ 2026-06-11 **第五刀：前端 glossary 編輯 UI 完成**。`frontend/edustudio/app.jsx` 新增
    `GlossaryEditor`（掛在課程工作空間 `ProjectStation` 作用中課程下方，per-course 一份）：切換作用中
    課程→`GET /projects/{pid}/glossary` 整張載入（404「此課尚未建立」＝開空表起頭、course 預設課名），
    可逐條編輯 **術語 / 讀音（TTS 覆寫）/ 縮寫全稱 / 別名（逗號或、分隔→陣列）/ 逐語言固定譯名（語言
    下拉×譯名→ translations dict）/ 備註**，新增/刪除術語與譯名列，「儲存術語表」→ `PUT` 整張覆寫並
    以後端回存為準。存檔前濾掉沒填 term 的列（後端 term 非空 validator，空 term→422）；別名/譯名以
    `esGlossToApi` 轉回 API 形。可折疊面板（預設收合）避免干擾工作空間。本機 `npm run build`（vite,
    node22）編譯通過；**視覺驗收待人工**（此環境無瀏覽器，依既定「前端 build 為準、人後視覺驗收」）。
  - ⏸️ **後續 offline slice**：runner 產旁白時帶該課 `to_pronunciation_map()`（需先定 job↔課
    association：jobs 目前不帶 project_id、只有 `ProjectStore.add_job` 單向掛載 → 反查設計是架構抉擇，
    待拍板；同一 association 也是把 `to_translation_rules()` 接進翻譯 route 的前提）。**自動建議術語**
    （掃教材抽術語）碰 Gemini 額度 = GATE，寫 proposal 再做。
- [ ] 🟡 **F9-3 本機可插拔模型後端**（GATE，= M 軸 Option B 的本機 provider）— 支援
  **Ollama 等本機 LLM** 跑文字（大綱/旁白/翻譯），老師可零雲端成本跑（翻譯已用本機
  translategemma 驗過路子）。**依賴 M-4 provider 介面就緒**後加 ollama adapter + 設定頁可選
  provider。與 offline-first 主軸高度契合。先寫 `docs/LOCAL_MODEL_RFC.md`（哪些角色支援本機 /
  品質落差 / 自動退雲端）。
- [~] 🟢 **F9-4 影片版本管理**（offline）— 重 render 時**保留舊版**（artifacts 加版本/時間戳，
  不覆蓋），可比對/回滾。教學內容會迭代，避免「重 render 蓋掉還能用的好版本」（已踩過視覺
  regression，見 ROADMAP v3.3 Round 2）。state 加 version 紀錄 + UI 列版本 + 下載指定版。
  - ✅ 2026-06-11 **第一刀：後端重 render 歸檔機制完成**。`server/schemas.py` 新增
    `ArtifactVersion`（version/created_at/archived_at/path/artifacts/note）+ `JobRecord.
    artifact_versions`（`extra="allow"` → 舊 state.json 無痛相容）。`JobStore.archive_artifacts
    (job_id, note)`：把現有 `artifacts/` **複製（非搬移）**進 `jobs/<id>/artifact_history/v<N>/`
    保留舊版，回傳更新後 record；`artifacts/` 空（沒可保留的舊版）→ no-op 回 None；版本序號遞增、
    各檔 metadata（name/kind/size/相對路徑）寫進快照、寫盤持久化。`server/runner.py::_run_render_phase`
    在重 render 一個 **DONE** job 前自動呼叫歸檔（首次 render 與 FAILED retry 不歸檔＝沒有可保留的
    好版本）；歸檔非破壞性、artifacts/ 照常被後續 render 覆蓋。補 `tests/test_artifact_versions.py`
    14 測（空/缺目錄 no-op、copy 非 move、版本欄位、kind 分類、多版遞增、持久化、未知 job 拋錯 +
    runner 整合：DONE 重 render 歸檔／首次不歸檔／FAILED 不歸檔／DONE 但空不留空版本，**全 tmp
    隔離不打 API**＝offline-first）。本機全套 2557 passed（3 個 QR/journal 字型像素為容器缺 Noto
    CJK 假象，CI 權威）。**後續 offline slice**：② API 列版本 + 下載指定版本端點 ③前端版本列/回滾 UI。

> （備案，未納入：**LMS/Moodle/SCORM 匯出** — 教學剛需但 ROADMAP 已列遠期、最遠，要提前再議。）

---

## 待劉老師拍板（卡住 routine 的決策點）

> 主要決策（授權/驗證/review gate/逐區 refine/模型抽象/新功能）已於 2026-06-07 拍板，
> 寫進各對應項。**剩餘需要你的只有「開額度 / 本機實機跑」這幾項**：

1. **C-2 單價對齊**：以 Gemini/GCP 官方定價為準的數字，需要時給我查。
2. **C-3 旁白模型遷 3.x**：開額度跑 A/B 驗品質後切（M 軸做完只改一個值）。
3. **D-1 docker compose 跨平台實測 / D-4 F5 GPU passthrough**：需你本機（Win/含 GPU）實跑。
4. **S-5 secret 靜態加密**：自架單機明文（已 gitignore）可接受 vs 要不要加 Fernet 加密 — 低優先，要不要做你定。
5. **F-3 CARD 軸 / F-4 EBOOK 軸**：RFC 開放問題待拍板（這兩個非首發必要）。
6. **DOC-5 demo 影片**：需你錄 60 秒 demo 放 README。

> 劉老師 2026-06-07：「需要額度我會給你權限」→ 上述開額度項 routine 寫好 proposal 後可請你開。

---

## 變更紀錄

- 2026-06-07：建檔。基於整合後現況稽核（README/claude.md/HANDOFF/ROADMAP/TODO/UI_WIRING +
  server/core 結構 + CI/安全掃描），對齊「公開開源自架 + /app 單一 + 全面稽核」三項拍板。
- 2026-06-07（同日 review session）：拍板落定 — P0-1 授權 **MIT** / S-1 驗證 **cookie+Bearer
  單一共享 token** / R-2 **狀態機強制+assert+測試（不簽章）** / U-2 **逐區 refine 要做** /
  新增 **M 軸 模型抽象**（A 現在+B 介面預留）/ 新增 **Phase 9** 四個差異化功能
  （review 二次校驗 / 課程 glossary / 本機可插拔模型 / 影片版本管理）。
