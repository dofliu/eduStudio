# 架構文件 — Architecture

> 給「想改 code 的人」的地圖：一張圖看懂 `core` / `server` / `frontend` 怎麼接、job 怎麼
> 從一份 PDF 走到一支影片、四條 track（影片 / 視覺 / 在地化 / Song MV）怎麼共用同一條
> pipeline。**對齊現況**（2026-06-10）；定位看 [claude.md](../claude.md)、推出主線看
> [PRODUCT_READINESS.md](PRODUCT_READINESS.md)、版本路線看 [ROADMAP.md](../ROADMAP.md)。

eduStudio 是**單一可自架的 FastAPI 後端 + 收斂到 `/app` 的 React 前端**。一個老師 clone
下來、設 `GEMINI_API_KEY`、`python -m server.main` 起在 `127.0.0.1:8000`，就能把考卷 /
講義 / 文件 / 音檔變成有旁白的教學影片、簡報 / 圖卡 / 海報、多語在地化內容 —— 而且**每個
AI 產出都過得了一道人工審查關卡**（review gate，硬規則 #1，不可繞）。

---

## 1. 三層俯瞰（core / server / frontend）

```
┌─────────────────────────────────────────────────────────────────────┐
│  瀏覽器 (React 19 + Vite, base 寫死 /app/)   ·   CLI / skill / curl    │
│         frontend/edustudio/  ──build──►  web/eduapp/ (/app/*)          │
└───────────────┬───────────────────────────────────┬───────────────────┘
                │ HTTP (cookie 或 Bearer token)       │
                ▼                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│  server/  — FastAPI app (server/main.py: create_app)                  │
│   middleware: auth(S-1) · CORS(S-2) · rate-limit(S-6)                 │
│   routes/:  jobs · uploads · slides · voices · youtube · infocards    │
│             localization · projects · settings · themes · editor …    │
│   jobs.py  : JobStore（state.json 持久化 + 啟動 resume R-1）           │
│   runner.py: ingest → (review gate) → render 編排 + render 入口 assert │
└───────────────┬───────────────────────────────────────────────────────┘
                │ 呼叫純函式 / 角色登錄表 resolve()
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  core/  — 不依賴 FastAPI 的內容引擎（可單獨 import / 測試）            │
│   來源解析: solve.py · slide_ingest.py · adapters/{repo,document,url} │
│   內容生成: outliner.py · scriptor.py · infocards/ · song_*           │
│   渲染:     deck.py · render_video · video/ · render/ · formula_render │
│   模型抽象: models.py(角色登錄表) · providers.py · usage.py(計帳)      │
│   設定/路徑: config.py(集中常數) · settings.py · selfcheck.py          │
└───────────────┬───────────────────────────────────────────────────────┘
                │ 外部相依
                ▼
   Gemini API (google.genai)   ·   ffmpeg/ffprobe   ·   TTS 後端
   (edge-tts / Google Cloud TTS / F5-TTS)   ·   Noto CJK 字型
```

**分層紀律**：`core/` 是純內容引擎，**不 import FastAPI**，可獨立跑測試與 CLI（`app.py`、
`pipeline.py`、`batch.py`、`solve.py` 等）。`server/` 只負責 HTTP、job 編排、持久化與安全，
重活全委派給 `core/`。前端只透過 HTTP 跟後端講話，**不直連 Gemini**（原 `/studio` 的
client-side 直連已隨 U-1 退場堵住）。

---

## 2. Job 狀態機（一份來源 → 一支影片）

所有「產一支影片」的工作都是一個 **job**，由 `server/runner.py` 編排、`server/jobs.py::JobStore`
持久化。狀態定義在 [`server/schemas.py::JobState`](../server/schemas.py)：

```
   pending ──ingest──► ingesting ──┬──────────────────────────────┐
                                   │  require_review=False         │
                                   │  (直接續)                      ▼
                                   │                          rendering ──► done
                                   │  require_review=True          ▲
                                   └─► awaiting_review ──approve───┘
                                            (人工審查關卡)
                          (任何階段 raise) ───────────────► failed
```

- **pending → ingesting**：`_run_ingest` 依 `source_type` 分流呼叫 `core/` 的來源解析，
  產出 `deck.json`（內容中介格式）。
- **ingesting → awaiting_review**：`require_review=True`（考卷 `exam_pdf`、`song` 預設為 True）
  時停在這，等人工逐題/逐段審查。進此狀態會把 `reviewed` 重置為 `False`（R-2，防 re-ingest
  挾帶舊的 approve）。
- **awaiting_review → rendering**：只有 `POST /jobs/{id}/approve`（標 `reviewed=True`）能放行。
- **render 入口 assert（硬規則 #1，不可繞）**：`runner._run_render_phase` 進 render 前再驗一次
  `require_review=True and reviewed=False → 拒絕渲染、標 failed`。**任何**想跳過審查直接 render
  的路徑（approve、section render、其他呼叫此入口者）都在此被擋死。改 runner 千萬別弱化這個 assert。
- **任何階段 → failed**：例外即標 failed 並寫進 `state.json`。
- **重啟止血（R-1）**：server 啟動時 `JobStore.resume_interrupted()` 把卡在
  `pending/ingesting/rendering`（重啟前在跑、task 已沒）的 job 標 `failed`，請使用者重試；
  `awaiting_review`（合法暫停）與 `done/failed`（終態）不動。

**持久化**：每個 job 一個目錄 `jobs/<job_id>/`，內含 `state.json`（`JobRecord`，可直接
`cat`/編輯 debug）、`deck.json`、`artifacts/`（mp4 / srt / png …）。沒有 DB、沒有外部 worker
（持久化 worker 是遠期 GATE，見 [V4_WORKER_RFC.md](V4_WORKER_RFC.md) / R-5）。

---

## 3. 四條 track 怎麼共用同一條 pipeline

關鍵設計：**所有 track 都先把來源轉成共同中介格式 `deck.json`，再走共用渲染**。差異收斂在
「來源 adapter」（ingest 前段）與「schema 轉換 + renderer」（render 分流），中段共用。

| Track | SourceType | Ingest（來源 → deck.json） | Render 分流 |
|---|---|---|---|
| 🎬 影片（考卷） | `exam_pdf` | `solve.py` 三段 Gemini（辨識 / 解題 / SVG） | `deck_to_exam_schema` → 黑板風格 |
| 🎬 影片（簡報） | `slides_pdf` | `slide_ingest.py` 章節切分 + 逐頁旁白 | `deck_to_exam_schema_slides` → 原投影片當底圖 |
| 🎬 影片（長文/repo/url） | `document` / `repo` / `url` | `adapters/` → `outliner.py` 兩階段大綱 → `scriptor.py` | `deck_to_exam_schema_pptx` → Forest pptx 主題 |
| 🎵 Song MV | `song` | `_run_ingest_song`：歌詞時間軸對齊 + AI 生圖 prompt | `song_render`（獨立分流，繞過 v0/TTS） |

- **分流點在 `runner._run_render_inner`**：先 `is_song_schema(deck)` type guard 早判（song 走
  獨立 `_run_render_song`），其餘看 `"sections" in deck` 與 `source_type` 選 `deck_to_exam_schema_*`，
  最後統一交給 `core.render_video`（黑板/簡報/pptx 三種 layout 共用同一 TTS + ffmpeg 組裝）。
- **🎨 視覺 track（圖卡 / 海報 / 簡報 PPTX）** 與 **🌐 在地化 track（翻譯 / 重新配音 / 會議摘要）**
  **不是 job-based**：它們是**同步請求**，前端直接打 `routes/infocards.py`、`routes/localization.py`
  即時拿結果（圖卡逐區 refine、海報生圖、翻譯、dub…）。它們共用 `core/infocards/`、
  `core/translation/` 等引擎與**同一套計帳 / 模型抽象**，只是不經過 job 狀態機。

```
   來源 (PDF / 簡報 / 文件 / repo / url / 音檔)
        │  source_type 分流
        ▼
   ┌──────────── ingest adapter ────────────┐
   │ solve / slide_ingest / adapters / song  │  ← track 差異在這
   └──────────────────┬──────────────────────┘
                      ▼
                  deck.json   ← 共同中介格式（review 審的就是它）
                      │  schema 轉換（看 source_type）
                      ▼
   ┌──────────── render_video / song_render ─┐
   │ TTS · 版面 · formula · ffmpeg 組裝       │  ← 共用
   └──────────────────┬──────────────────────┘
                      ▼
              artifacts/*.mp4 + *.srt
```

---

## 4. 橫切關注點（改 code 前要知道的）

- **模型抽象（M 軸）**：模型 id **不寫死在散落各處**。邏輯角色（`text.fast` / `text.pro` /
  `vision` / `image.fast` / `image.pro` / `tts`）→ `(provider, model_id)` 集中在
  [`core/models.py`](../core/models.py)，呼叫端用 `resolve()`。換模型 = 改登錄表/設定頁一個值。
  provider 介面在 [`core/providers.py`](../core/providers.py)（B-ready，本機 Ollama 等將 slot-in）。
  健檢工具 [`tools/check_models.py`](../tools/check_models.py) 比對哪些 id 在這把 key 下已 404。
  > 注意：影片/解析旁白目前仍寫死 `gemini-2.5-flash`，換到 3.x 是 **C-3 GATE**（需開額度 A/B 驗品質），別自行換。
- **計帳（usage）**：所有送 Gemini 的 chokepoint 接 [`core/usage.py`](../core/usage.py) 計帳，
  成本面板 `/api/usage` 走真實統計（影片 / 視覺 / 在地化 / 解析各站）。
- **安全（Phase 1）**：middleware 三件套 —— `server/auth.py`（單一共享 token，cookie+Bearer）、
  CORS 收緊（`core.config.get_allowed_origins()`）、`server/ratelimit.py`（per-IP token bucket）。
  路徑安全走 `server/path_safety.py::safe_join`（字元檢查 + resolve-containment）。
- **路徑與設定**：常數集中 [`core/config.py`](../core/config.py)（`PROJECT_ROOT` 推導所有
  `*_DIR`）；字型路徑走 `CLAUDE_*_FONT_PATH` env **不寫死**；DB 路徑皆可用 env 覆寫（測試用 tmp）。
- **type guard 分流**：schema dispatch（exam vs slides vs song vs deck）用 `"sections" in deck`、
  `is_song_schema()` 等型別判斷早判，未知角色/類型 `raise ValueError`（硬規則 #9）。

---

## 5. 前端建置（`/app` 唯一正式介面）

- 原始碼 [`frontend/edustudio/`](../frontend/edustudio)（React 19 + Vite），`base` 在
  `vite.config.ts` **寫死 `/app/`**（消除 footgun，見 U-6），`npm run build` 產物落 `web/eduapp/`，
  由 `server/main.py` mount 在 `/app/*`（assets + SPA fallback）。
- `/ui`、`/studio` **已退場**（U-1 2026-06 / U-5 2026-08-30）：兩路徑一律 307 轉址 `/app/`；
  原 `/ui` 的 web/ 原始碼專案已移除（考古走 git 歷史），`/studio` 的 client-side 直連
  Gemini 漏洞隨 U-1 關閉。
- 此 repo 無瀏覽器自動化：前端以 `npm test`（node --test）+ `npm run build` 編譯過為準，**視覺由人後驗**。

---

## 6. 想動哪裡，先看哪裡

| 想做的事 | 入口檔 | 一定要跑的測試 |
|---|---|---|
| 加 / 改一種來源 track | `server/schemas.py`（SourceType）+ `server/runner.py::_run_ingest` + `core/adapters/` | `pytest tests/` 全套 |
| 改 render / 版面 / 字幕 | `server/runner.py::_run_render_inner` + `core/deck.py` + `core/render_video` | render 相關子集 + 全套 |
| 改 review gate / job 狀態 | `server/runner.py` + `server/jobs.py` + `server/schemas.py` | `test_review_gate` / `test_resume_interrupted` + 全套 |
| 換模型 / 加 provider | `core/models.py` · `core/providers.py`（**勿動旁白 2.5→3.x，C-3 GATE**） | `test_models_registry` / `test_providers` |
| 改安全 / 驗證 / 限流 | `server/auth.py` · `server/ratelimit.py` · `server/path_safety.py` · `core/config.py` | `test_auth` / `test_ratelimit` / `test_path_safety` |
| 改視覺（圖卡 / 海報） | `server/routes/infocards.py` + `core/infocards/` | `test_infocards_*`（全 mock，**不打真 API**） |
| 改在地化（翻譯 / dub） | `server/routes/localization.py` + `core/translation/` | `test_localization*` |
| 改前端 | `frontend/edustudio/app.jsx` | `npm run build`（視覺人後驗） |

> **硬規則提醒**：動 `server/` `core/` `schemas` `runner` 一定跑 `pytest tests/`；會燒
> Gemini/GCP 額度、改安全模型、動大架構的事是 GATE，寫 proposal 後 STOP，別自己跑真實 API；
> review gate（`require_review=True` 必須人工 approve 才能 render）絕不繞過。
</content>
</invoke>
