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
- [ ] 🟡 **P0-3 `.env.example` / 設定範本完整度檢查**（offline）— 確認陌生人照範本能配齊
  所有必要環境變數（GEMINI_API_KEY、字型路徑、TRACK_B_URL…），缺的補進範本 + 註解。
- [ ] 🟡 **P0-4 CONTRIBUTING.md + issue/PR 範本**（offline）— 開源協作基本盤；放
  `.github/ISSUE_TEMPLATE/`、`CONTRIBUTING.md`（含「怎麼跑測試 / 硬規則摘要 / offline-first
  紀律」）。
- [ ] 🟢 **P0-5 SECURITY.md**（offline）— 漏洞回報窗口 + 「請勿把 server 直接裸奔公網」警語。

---

## Phase 1 — 安全硬底層（🔴 開源自架的致命缺口）

> 現況：後端**零驗證** + `CORS allow_origins=["*"]`。任何人連到 port 8000 就能觸發 job、
> 燒你的 Gemini 額度、刪 job、讀檔。對「localhost 自己用」OK，對「自架暴露在內網/公網」
> 不可接受。開源版必須給自架者一個安全預設。

- [ ] 🔴 **S-1 單一共享 token 驗證層**（offline，**設計已拍板 2026-06-07**）— 設計定案：
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
- [ ] 🔴 **S-2 CORS 收緊**（offline）— `allow_origins=["*"]` 改成讀環境變數
  `EDUSTUDIO_ALLOWED_ORIGINS`（預設 `http://127.0.0.1:8000`）。同源 `/app` 不受影響。
  server/main.py:85 一處 + 測試。
- [ ] 🔴 **S-3 path-traversal 全面審**（offline）— 既有部分端點有 `_sanitize_filename` /
  `../` 防呆（uploads / library / song images），但**沒系統性審過全部吃 path/filename 的
  端點**（jobs artifacts / slides images / projects sources / editor…）。逐一審 + 補一組
  共用 `safe_join` helper + traversal 測試（`../`、絕對路徑、symlink、Windows `\`）。
- [ ] 🟡 **S-4 上傳硬化**（offline）— 既有 `MAX_UPLOAD_SIZE` 200MB + Content-Length 預檢。
  補：副檔名/MIME 白名單（只收 pdf/mp3/wav/png…）、解壓/解析前大小複查、檔名 NFC 正規化。
- [ ] 🟡 **S-5 secret 落地強化**（GATE）— 現況 settings.json / youtube_token.json 明文存盤
  （已 gitignore）。自架單機可接受，但要在文件講清楚「這些檔含金鑰、別放共享磁碟/別進
  備份」。是否要加靜態加密（如 `cryptography` Fernet + 機器金鑰）= 拍板後再做。
- [ ] 🟢 **S-6 速率限制 / 濫用防護**（offline）— 對 `/api/generate` 等燒額度端點加簡單
  per-IP rate limit（slowapi 或自寫 token bucket），防自架者被內網誤觸刷爆額度。

---

## Phase 2 — 可靠性 P0（🔴 server 重啟不能丟工作）

> 對應 ROADMAP「P0 結構性弱點」+ [V4_WORKER_RFC.md](V4_WORKER_RFC.md)。這四條是
> 「個人用 OK、交給別人自架不可接受」的根因。**全面 D（持久化 worker）是大工程**，但可以
> 先做低成本的止血。

- [ ] 🔴 **R-1 啟動時 resume 卡住的 job**（offline，止血）— 現況 `asyncio.create_task`
  即起即忘，server 重啟後 in-flight job 永遠停在 `ingesting/rendering`。JobStore 已持久化
  狀態，缺的是啟動時掃 `pending/ingesting/rendering` 的 job → 標 `failed`（附「server 重啟
  中斷，請重試」）或自動重排。先做「標 failed + 可一鍵重試」這個最小止血（不需要 worker
  架構）。動 runner/jobs，跑 pytest。
- [ ] 🟡 **R-2 review gate enforcement 不可繞**（offline，**設計已拍板 2026-06-07**）— 現況
  `require_review=True` 靠 server flag 擋，理論可繞（硬規則 #1 的根因 #4）。定案：
  **狀態機強制 + render 入口 assert + 測試鎖死，不做密碼學簽章**。
  - 對 `require_review=True` 的來源（考卷/歌曲等含 AI 數值），job 進 `rendering` **必須**先經
    `awaiting_review` → 明確 approve（state 寫 `reviewed_at`/`reviewed=True`）。
  - render 入口（`_run_render_phase`/inner）直接 assert reviewed，否則 raise。
  - 測試「嘗試跳過審查 → 被擋」鎖死。
  威脅模型是「不小心跳過」非「內部惡意竄改」，簽章對自架單人過度設計，故不做。
- [ ] 🟡 **R-3 sync I/O 阻 event loop 收口**（offline）— F5 已用 `asyncio.to_thread` 包，
  但無全面 enforcement。審 runner/routes 裡的同步重 I/O（PDF 解析、ffmpeg、檔案搬運）有沒有
  漏網的同步呼叫卡 event loop，補 `to_thread`。低風險、逐處補。
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
- [ ] 🟡 **U-2 `/app` 補齊 `/studio` 缺的視覺功能 — 含逐區 refine**（offline，**拍板要做
  2026-06-07**）— 盤點顯示 `/app` 視覺站缺「海報/圖卡逐區 refine、區域選擇」（後端 refine
  圖卡未移植 = 唯一「大」缺口）。**定案：移植後端逐區 refine + 前端區域選擇 UI**（不是首發
  砍項）。其餘（16 主題/密度/長寬比/自訂 prompt）UI_WIRING 標已接完。拆小：①後端 refine
  圖卡端點移植 ②前端區域選擇/逐區 refine UI ③測試。
- [ ] 🟡 **U-3 `/ui` `/studio` 標 legacy / 退場**（offline）— 在舊 UI 頁頂加 banner「此介面
  將退場，請用 /app」+ README/介面表標 legacy。完全移除 build 產物等 `/app` 功能對等確認後
  再做（避免反悔）。
- [ ] 🟡 **U-4 成本面板真實化收尾**（offline，接 Phase 4）— 現況部分 mock。等 Phase 4 計費
  補完後，把成本面板數字接真 `/api/usage`，移除「示意」假數字。
- [ ] 🟢 **U-5 發布站多語上傳驅動**（GATE）— 現況多語版本選擇只是視覺。要驅動真多語上傳碰
  YouTube OAuth + 多語 metadata（方案 A 多語字幕軌後端已有），補前端驅動。
- [ ] 🟢 **U-6 前端建置流程文件化**（offline）— `--base=/app/` 必帶這個雷寫進 README/CONTRIBUTING，
  自架者改前端不踩。考慮加 `npm run build:app` script 包死 flag。

---

## Phase 4 — 計費準確 + 模型一致性（🟡 信任與成本）

> 自架者最在意「這會花我多少錢」。現況計費**只算視覺/在地化**，最大宗的影片 render
> pipeline 完全沒計帳（HANDOFF 待加強 #1）。

- [ ] 🔴 **C-1 影片 pipeline Gemini 呼叫接計帳**（offline）— `core/usage.py` 計帳子系統已有，
  把影片 pipeline 的 Gemini chokepoint（outliner / scriptor / slide_ingest / solve）也
  instrument 進去。讓成本面板涵蓋最大宗。逐 chokepoint 接 + 測試。
- [ ] 🟡 **C-2 單價對齊真實**（GATE，需查官方定價）— 現況單價是估算。對齊 Gemini 3 系列 +
  GCP TTS + （未來）image 真實單價。定價會變動 → 抽成設定常數 + 文件註明「以官方為準」。
- [ ] 🟡 **C-3 旁白模型遷 3.x**（GATE，需開額度驗證品質）— `slide_ingest.py:43`
  `MODEL = "gemini-2.5-flash"`（將淘汰）。**M 軸完成後這只是改角色表 `text.fast` 一個值**。
  3.5-flash 實測接受 `thinking_budget=0`，但**旁白品質要先驗**再換。寫成 A/B proposal，劉老師
  開額度跑過再切。（劉老師 2026-06-07：需額度會給權限。）
- [ ] 🟢 **C-4 `gemini-3.1-pro-image` 等開放再換**（GATE）— 劉老師想用但 API 未開放。等開放
  從 `gemini-3-pro-image` 換（`core/infocards/models.py`）。掛追蹤。
- [ ] 🟢 **C-5 模型 id 自我健檢**（offline）— 加一個 `tools/check_models.py` 跑
  `client.models.list()` 比對設定頁用的 id 是否還存在（這 repo 有用過 preview id 404 前科），
  自架者換 key 後可自查。（並進 M 軸：比對角色登錄表全部 id。）

### M 軸 — 模型抽象與可插拔後端（🔴 結構性，劉老師 2026-06-07 指定）

> **痛點（劉老師提）**：模型 id **散落**（`slide_ingest.py:43` 寫死 `gemini-2.5-flash`、
> `core/infocards/models.py`、`settings.py`、`config.py`、scriptor/outliner…）+ 名稱/版號不
> 一致 + preview id 會 404。要讓「模型設定/修改**獨立於專案之外**」，未來 4.0/5.0/6.0 出來
> 系統零（或極小）改動。
> **拍板（2026-06-07）：做 Option A（角色登錄表）+ 介面設計成 B-ready**（provider 抽象之後
> 再加，不重構）。B 的「本機 provider」就是 Phase 9 F9-3 本機可插拔模型。

- [ ] 🔴 **M-1 角色登錄表 `core/models.py`（offline，A 核心）**— 定義**邏輯角色** →
  具體 model id 的單一真實來源（角色：`text.fast` / `text.pro` / `vision` / `image.fast` /
  `image.pro` / `tts`）。`resolve(role)` 讀設定頁(settings.json) → fallback 內建預設表。
  介面預留 provider 維度（`resolve(role) -> (provider, model_id)`，A 階段 provider 恆 gemini）。
  +測試鎖角色集合 + fallback。
- [ ] 🔴 **M-2 全面換掉寫死 id（offline）**— 把 `slide_ingest.py` / `core/infocards/models.py` /
  scriptor / outliner / translate / 其餘 chokepoint 的硬編 model id **全部改呼叫 `resolve()`**。
  一處一處改、跑 pytest（硬規則 #7）。完成後「換模型 = 改一個表/設定頁」。
- [ ] 🟡 **M-3 設定頁模型管理升級（offline）**— 設定頁從「文字/圖片各一個下拉」升級成
  **逐角色可配**（或維持精簡但底層走角色表），未知 id 顯示健檢結果（接 C-5）。
- [ ] 🟢 **M-4 provider adapter 介面（B-ready stub，offline）**— 定義 `Provider` 協定
  （`generate_text` / `generate_image` / `tts`）+ gemini adapter 包現有呼叫。**只抽介面不換行為**，
  讓 Phase 9 F9-3（ollama/claude provider）能 slot-in。是否現在做或等 F9-3 一起做，routine 視
  M-1/M-2 完成後評估。

---

## Phase 5 — 部署就緒（🟡 開源自架的「跑得起來」）

> Docker scaffold 已有（Dockerfile + docker-compose + .env.example），但**未跨平台實測**，
> 也無 production 反代/TLS 指引。對應 ROADMAP 階段 1 A。

- [ ] 🔴 **D-1 `docker compose up --build` 跨平台實測**（GATE，需劉老師本機跑）— Linux/Win/Mac
  各驗一遍，修踩到的問題（字型、volume、healthcheck）。產出「實測 OK」結論 + 修補。
- [ ] 🟡 **D-2 production 設定範本**（offline）— 一個 `docker-compose.prod.yml` 或文件段：
  收緊 CORS、設 API token、不開 `--reload`、log 落盤、restart policy。把 Phase 1 安全項串成
  「上線前 checklist」。
- [ ] 🟡 **D-3 reverse proxy + TLS 指引**（offline，文件）— nginx/caddy 範例 conf（自架者要把
  server 擺 TLS 後面，不裸奔）。不需自己跑，給可複製範本。
- [ ] 🟡 **D-4 F5 GPU passthrough 文件**（GATE，需 GPU 環境實測）— nvidia-docker 跑 F5-TTS
  的設定 + 「沒 GPU 自動退 edge/google TTS」說明。
- [ ] 🟢 **D-5 健康檢查 / 啟動自檢**（offline）— `/health` 已有；加啟動時自檢（字型在不在、
  ffmpeg 在不在、GEMINI key 設了沒）印清楚的綠/紅，讓自架者一眼知道缺什麼。
- [ ] 🟢 **D-6 requirements 分層說明**（offline）— 已分 core/optional/dev/song，README 講清楚
  「最小裝什麼能跑、要 F5/Whisper/song 再加裝什麼」。

---

## Phase 6 — 文件就緒（🟡 陌生人能上手）

> 整合後文件有**定位漂移**：`claude.md` 還停在舊定位「教學影片自動生成平台」、HANDOFF 寫死
> 劉老師 Windows 本機路徑（`D:\...`）。開源前要去個人化 + 對齊 eduStudio 全貌。

- [ ] 🔴 **DOC-1 `claude.md` 更新到 eduStudio 整合後定位**（offline）— 現況開頭仍是
  「教學影片自動生成平台」+ 三 Track 舊圖 + Gemini 2.5。更新成 4 track（含視覺/在地化/song）
  + 整合架構 + 現行模型。這份是給 Claude/協作者的 context，最該先準。
- [ ] 🟡 **DOC-2 去個人化 / 去 Windows 硬路徑**（offline）— HANDOFF / 文件裡的 `D:\Project_...`
  / `C:\Python\...` 改成相對說明或環境變數，讓非劉老師的機器也讀得懂。保留作者署名，移除
  本機絕對路徑。
- [ ] 🟡 **DOC-3 端到端 onboarding 文件**（offline）— `docs/onboarding.md` 已有，補成「陌生
  老師 0 到 1」：裝 → 配 key → 跑第一支影片 → 上 YouTube，含截圖/常見錯誤。
- [ ] 🟢 **DOC-4 架構文件 / ARCHITECTURE.md**（offline）— 一張圖講清 core/server/frontend
  資料流 + job 狀態機 + 四 track 怎麼共用 pipeline，給想改 code 的人。
- [ ] 🟢 **DOC-5 demo 影片 / 截圖**（GATE，需劉老師錄）— README 放一支 60 秒 demo（用自己的
  系統產，吃自己狗糧）。

---

## Phase 7 — 測試與發佈（🟡 品質護網 + 正式版本）

- [ ] 🟡 **T-1 端到端整合測試**（offline）— 現況 ~2400 tests 強在純函式單元，**缺 TestClient +
  真 pipeline 端到端**（建 job → ingest（mock Gemini）→ review → render（mock ffmpeg）→ artifact）。
  補一組 happy-path E2E，鎖住「整條接線不斷」。CI 可能要分 job 處理重依賴（見 test.yml 註解）。
- [ ] 🟡 **T-2 CI actions 升版**（offline）— Node actions 升 v4 消棄用警告（HANDOFF #6）；
  考慮加一個「裝 ffmpeg 跑少量真 render」的 nightly job。
- [ ] 🟢 **T-3 版本 / tag / CHANGELOG / Release**（offline）— 訂 `v1.0.0`（開源首發）語意化版本，
  `docs/CHANGELOG.md` 已有 → 補 release notes，打 git tag + GitHub Release。
- [ ] 🟢 **T-4 README badge / 截圖牆 / 一鍵 demo**（offline）— 開源門面：CI badge（已有）、
  授權 badge、功能截圖、`docker compose up` 一鍵體驗指引。

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
- [ ] 🟡 **F9-2 課程術語/讀音表 glossary**（offline 可起頭）— `pronunciation.json` 升級成
  **per-course glossary**（理工術語固定譯名 + 讀音 + 縮寫展開，材力/自控各一套）。接進 Project
  「一課一工作空間」：產旁白/翻譯時套該課 glossary → 術語一致。schema + 套用層 offline 可做；
  自動建議術語碰額度 → proposal。
- [ ] 🟡 **F9-3 本機可插拔模型後端**（GATE，= M 軸 Option B 的本機 provider）— 支援
  **Ollama 等本機 LLM** 跑文字（大綱/旁白/翻譯），老師可零雲端成本跑（翻譯已用本機
  translategemma 驗過路子）。**依賴 M-4 provider 介面就緒**後加 ollama adapter + 設定頁可選
  provider。與 offline-first 主軸高度契合。先寫 `docs/LOCAL_MODEL_RFC.md`（哪些角色支援本機 /
  品質落差 / 自動退雲端）。
- [ ] 🟢 **F9-4 影片版本管理**（offline）— 重 render 時**保留舊版**（artifacts 加版本/時間戳，
  不覆蓋），可比對/回滾。教學內容會迭代，避免「重 render 蓋掉還能用的好版本」（已踩過視覺
  regression，見 ROADMAP v3.3 Round 2）。state 加 version 紀錄 + UI 列版本 + 下載指定版。

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
