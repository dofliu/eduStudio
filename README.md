<div align="center">

# 🎓 eduStudio

**教學內容工作站 · Teaching Content Studio**

*Turn exams, slides, documents, code repos and audio into narrated teaching videos, slide decks, infographics and localized content — from one self-hostable server, organized per course, with a human review gate over every AI output.*

把考卷、講義、文件、程式碼、音檔，一站式變成**有旁白的教學影片**、**簡報 / 圖卡 / 海報**與**多語在地化內容** — 單一可自架伺服器、以「一門課一工作空間」管理、且每個 AI 產出都有人工審查關卡。

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Gemini](https://img.shields.io/badge/Google-Gemini%203-4285F4?logo=googlegemini&logoColor=white)
[![tests](https://github.com/dofliu/eduStudio/actions/workflows/test.yml/badge.svg)](https://github.com/dofliu/eduStudio/actions/workflows/test.yml)
![Status](https://img.shields.io/badge/status-active-success)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](#-english) · [繁體中文](#-繁體中文)

</div>

---

## 🇬🇧 English

### What is eduStudio?

eduStudio is a single, self-hostable **Python FastAPI** server that helps teachers (especially STEM / engineering) turn raw materials into polished, publishable teaching content — and keeps a **human in the loop** over the AI. It merges three formerly separate tools into one unified web app and one deployable backend.

> Think of it as **"NotebookLM for teachers who publish on YouTube"** — but you own the server, and nothing ships until you approve it.

### Three pillars

| 🎬 Video | 🎨 Visual | 🌐 Localization |
|---|---|---|
| Exam PDF → blackboard-style worked-solution video | Teaching slides (16 themes, audience/tone steering) | Translate / re-dub external videos |
| Slides PDF → page-by-page narrated lecture | Infographic cards & print-grade posters | Meeting / lecture audio → summary |
| Doc / Repo / URL → AI outline → narrated video | Two-stage outline → full deck → PPTX export | Song mp3 → lyric timeline → AI-image MV |
| HTML animation (`.html` / URL) → recorded MP4 | Image-less deck → AI fills illustrations into each page's blank space | Flashcards (SM-2), writing correction |
| Subtitles (SRT) + one-click YouTube upload | PPTX in-place augment (text stays editable) → editable PPTX or one-click video | Per-slide refine + auto chart/diagram |
| Google Photos → AI-curated photo slideshow (narrated video + PPTX) | — | — |

### Highlights

- **🛡️ Human review gate** — AI output (especially exam answers / numbers) stops at an editable review screen before rendering. The product's core principle: *never publish unverified AI numbers.* Exam solutions are review-locked by design.
- **🗂️ One course = one workspace** — pick a course at the top; every video and visual you generate is automatically filed under it (sources · tasks · products), NotebookLM-style.
- **🎙️ Your own voice** — F5-TTS voice cloning lets narration speak in *your* voice, with automatic fallback to edge-tts / Google TTS.
- **🧩 Gemini 3 powered** — `gemini-3.5-flash` / `gemini-3.1-pro-preview` for text; three image tiers **Nano Banana 2 Lite / 2 / Pro** (`gemini-3.1-flash-lite-image` / `gemini-3.1-flash-image` / `gemini-3-pro-image`), fully configurable in-app.
- **📤 Publish-ready** — PPTX export, YouTube auto-chapters, bilingual subtitle tracks, LaTeX formula rendering, personal-brand footer baked into slides & cards.
- **🖼️ Smart slide augmentation** — upload an image-less deck (slides PDF *or* PPTX); eduStudio detects text-only pages and drops a matching AI illustration into each page's blank area, keeping the original layout at full size (and, for PPTX, the original text fully editable). Then export an updated deck or a one-click narrated video.
- **🎞️ HTML animation → video** — turn any self-contained `.html` animation (or a URL) into a frame-accurate MP4 via a virtual-clock headless capture, ready for the same `/library` + YouTube upload path.
- **❖ Google Photos → photo deck** — pick photos from your Google Photos library (via the Photos Picker API); a vision model quality-filters (blurry / duplicate), writes a caption per photo and a deck title, and produces a narrated slideshow video **and** an exportable PPTX — all through the same review gate and job pipeline.
- **🔒 Self-hosted & offline-first** — your API key, your machine, your data. No third-party SaaS in the loop.

### Screenshots

> Screenshots are captured from a running `/app` instance. Drop the images under
> `docs/screenshots/` with the filenames below and they'll render here.

| The unified `/app` workstation | The human review gate |
|---|---|
| <!-- screenshot: docs/screenshots/app-home.png --> _`docs/screenshots/app-home.png`_ | <!-- screenshot: docs/screenshots/review-gate.png --> _`docs/screenshots/review-gate.png`_ |
| Pick a course, then Video / Visual / Localization | Every AI answer stops here, editable, until you approve |

| Visual composer (infographics & posters) | Cost panel (real per-station usage) |
|---|---|
| <!-- screenshot: docs/screenshots/visual.png --> _`docs/screenshots/visual.png`_ | <!-- screenshot: docs/screenshots/usage.png --> _`docs/screenshots/usage.png`_ |

<!-- TODO（人工）：在 docs/screenshots/ 補上上述四張截圖（此環境無瀏覽器，依「文字步驟可獨立完成、視覺後驗」） -->

### Quick start

**One-command try (Docker)** — fastest way to kick the tyres. The bundled image already
has ffmpeg + CJK fonts, so you don't install anything except Docker itself:

```bash
cp .env.example .env          # then put your GEMINI_API_KEY in it
cp tts_config.example.json tts_config.json   # default edge-tts is fine
docker compose up -d --build  # build + start in the background
```

Then open **`http://localhost:8000/app/`**. Stop with `docker compose down` (add `-v` to
also wipe the `jobs` volume). For exposing it beyond localhost (token, CORS, reverse proxy
+ TLS), follow [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — never put it on a public port
without setting `EDUSTUDIO_API_TOKEN` first.

**Or run it from source:**

```bash
# 0. System prerequisites (NOT pip): ffmpeg (+ffprobe) for any render,
#    and Noto CJK fonts for correct Chinese glyphs. See "Dependency layers" below.

# 1. Backend (Python 3.12)
pip install -r requirements.txt          # core deps — enough to run the server
#   add-ons (only if you need them): requirements-optional.txt (PPTX export / STT /
#   F5-TTS), requirements-song.txt (SONG MV track), requirements-dev.txt (tests)
export GEMINI_API_KEY=your_key           # or set it in the in-app Settings page

# 2. Frontend (the unified /app UI)
cd frontend && npm install && npx vite build --base=/app/   # --base=/app/ is required
cd ..

# 3. Run
uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Then open **`http://127.0.0.1:8000/app/`**.

> ⚠️ The ASGI path is **`server.main:app`** — there is no root `main.py`. Running
> `uvicorn main:app` fails with *"Error loading ASGI app. Could not import module 'main'"*.
> Equivalent: `python -m server.main`.

📖 **New here?** The full [**User Manual**](docs/USER_MANUAL.md) covers every station, the
config reference, the REST API and troubleshooting. For the shortest path (exam → video →
YouTube) see [onboarding](docs/onboarding.md).

📚 **Serialized comics:** the internal Comic Production System covers Series Bible,
script/storyboard, evidence-gated AI generation, editable Word bubbles, versioned release
and the Internal Reader. See [Comic Production System](docs/COMIC_PRODUCTION_SYSTEM.md).

### Dependency layers

Dependencies are split so you install only what you actually use. `requirements.txt`
alone is enough to run the server and the main pipelines (video, visual, localization
text) — add a layer only when you want the matching feature.

| Layer | Install | What it adds | Without it |
|---|---|---|---|
| **core** | `pip install -r requirements.txt` | Server + video / visual / localization-text pipelines (Gemini, FastAPI, Pillow, edge-tts, PyMuPDF, matplotlib) | — (always required) |
| **optional** | `pip install -r requirements-optional.txt` | PPTX export (`python-pptx`), speech-to-text (`faster-whisper`, auto GPU→CPU), F5-TTS voice cloning, sample-PDF tool, outro QR | Those specific features fail gracefully; everything else runs |
| **song** | `pip install -r requirements-song.txt` | SONG MV track only — Demucs + WhisperX (heavy, several GB, GPU recommended) | The song/MV track is unavailable; all other tracks fine |
| **dev** | `pip install -r requirements-dev.txt` | Test suite (`pytest`, `httpx`) | Can't run `pytest tests/` |

**System dependencies (installed outside pip):**

- **ffmpeg / ffprobe** — *required* for any video render or audio extraction. `apt install ffmpeg` · `brew install ffmpeg` · `choco install ffmpeg`.
- **Noto CJK fonts** (e.g. `fonts-noto-cjk`) — needed for correct Chinese rendering in slides / blackboard. Paths are overridable via `CLAUDE_FONT_PATH` / `CLAUDE_FALLBACK_FONT_PATH` / `CLAUDE_MONO_FONT_PATH`.
- **LibreOffice** (`libreoffice-impress`) — cross-platform renderer for PPTX-source features. On Windows, installed Microsoft PowerPoint is used as a COM fallback. All other tracks (exam / slides-PDF / doc / HTML / song) don't need either renderer.

### Local release gates and portable model cache

- Cloud CI runs all unit/contract/integration tests and explicitly excludes `office_live`, because hosted runners do not guarantee a desktop Office runtime. Before a Windows release, run `pytest -m office_live tests/test_uploads_pptx.py -q` locally.
- To move the Whisper model cache to another computer, set `HF_HOME` before starting the server (for example `HF_HOME=D:\hf-cache`). `/health` must report `whisper.cached=true`; `cache_source` shows which cache setting was used. An incomplete snapshot is not accepted as cached.

The bundled `Dockerfile` already installs ffmpeg and the CJK fonts for you.

### Interfaces

| Path | What | |
|---|---|---|
| **`/app`** | Unified workstation (Video · Visual · Material/Project · Publish · Status) | primary |
| `/api`, `/localization`, `/projects`, `/jobs` | REST backend (generation, translation, projects, jobs) | |
| `/docs` | Auto-generated OpenAPI docs | |
| `/studio`, `/ui` | Legacy standalone UIs (kept for reference) | legacy |

### Tech stack

`Python 3.12` · `FastAPI` · `React 19 + Vite` · `Google Gemini 3` · `faster-whisper` · `F5-TTS` · `edge-tts` · `PyMuPDF` · `python-pptx` · `matplotlib` (LaTeX) · `ffmpeg`

### Documentation

| Doc | For |
|---|---|
| 📖 [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) | **Full user manual** — every station, config reference, REST API, troubleshooting (English quick-reference inside) |
| 🚀 [`docs/onboarding.md`](docs/onboarding.md) | Getting started 0→1 (exam → video → YouTube) |
| 🔒 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Production deploy (token · CORS · reverse proxy · TLS) |
| 🛠️ [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`claude.md`](claude.md) | Contributing + non-negotiable hard rules |
| 🗺️ [`ROADMAP.md`](ROADMAP.md) · [`TODO.md`](TODO.md) · [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Roadmap · backlog · changelog |
| 🔍 [`docs/CODE_REVIEW_2026-07.md`](docs/CODE_REVIEW_2026-07.md) | Latest code audit + improvement plan |

---

## 🇹🇼 繁體中文

### eduStudio 是什麼？

eduStudio 是一套**單一、可自架的 Python FastAPI** 伺服器，幫老師（尤其理工 / 工程科）把原始素材變成可發布的教學內容，而且**全程人工把關** AI 產出。它把三個原本獨立的工具整合成**一個 Web 介面 + 一個可部署後端**。

> 可以想成 **「給在 YouTube 上課的老師用的 NotebookLM」** — 但伺服器是你自己的，東西沒按下核准就不會出去。

### 三大支柱

| 🎬 影片 | 🎨 視覺 | 🌐 在地化 |
|---|---|---|
| 考卷 PDF → 黑板風格逐題解答影片 | 教學簡報（16 種主題、受眾/語氣引導） | 外部影片翻譯 / 重新配音 |
| 簡報 PDF → 逐頁旁白講解影片 | 資訊圖卡 & 印刷級海報 | 會議 / 演講錄音 → 重點摘要 |
| 文件 / Repo / 網址 → AI 大綱 → 講解影片 | 兩階段大綱 → 完整簡報 → PPTX 匯出 | 歌曲 mp3 → 歌詞時間軸 → AI 生圖 MV |
| HTML 動畫（`.html` / 網址）→ 錄製 MP4 | 缺圖簡報 → AI 把配圖補進每頁空白處 | 單字卡（SM-2）、寫作批改 |
| 字幕（SRT）+ 一鍵上傳 YouTube | PPTX 原檔就地補圖（文字仍可編輯）→ 可編輯 PPTX 或一鍵轉影片 | 單頁微調 + 自動圖表/架構圖 |
| Google 相簿 → AI 選圖+配文 相片簡報（有旁白影片 + PPTX） | — | — |

### 特色

- **🛡️ 人工審查關卡** — AI 產出（尤其解題答案 / 數字）會停在**可編輯的審查頁**，核准後才渲染。核心原則：*絕不發布未經查證的 AI 數值*。考卷解答一律強制審查。
- **🗂️ 一門課＝一工作空間** — 右上選課，之後產的每支影片 / 每張圖卡都自動歸到該課（來源 · 任務 · 成品），NotebookLM 式管理。
- **🎙️ 你自己的聲音** — F5-TTS 聲音複製讓旁白用**你的**聲音念，並自動退回 edge-tts / Google TTS。
- **🧩 Gemini 3 驅動** — 文字用 `gemini-3.5-flash` / `gemini-3.1-pro-preview`；圖片三階層 **Nano Banana 2 Lite / 2 / Pro**（便宜 `gemini-3.1-flash-lite-image`／中等 `gemini-3.1-flash-image`／貴 `gemini-3-pro-image`），App 內可自由設定。
- **📤 隨時可發布** — PPTX 匯出、YouTube 自動章節、雙語字幕軌、LaTeX 公式渲染、個人品牌頁尾自動帶進簡報與圖卡。
- **🖼️ 缺圖簡報智慧補圖** — 上傳缺圖的簡報（PDF 或 PPTX）；eduStudio 偵測純文字頁，把符合內容的 AI 配圖放進該頁的空白區、原頁維持原大小（PPTX 則直接在原檔上插圖、原文字仍完全可編輯）。接著可匯出新簡報或一鍵產生有旁白的講解影片。
- **🎞️ HTML 動畫轉影片** — 用虛擬時鐘的無頭瀏覽器逐格擷取，把任意自含 `.html` 動畫（或網址）轉成 fps 精準的 MP4，直接接上既有的 `/library` + YouTube 上傳。
- **❖ Google 相簿 → 相片簡報** — 從 Google 相簿挑照片（走 Photos Picker API）；視覺模型做品質過濾（模糊/重複）、為每張配一句說明並取簡報標題，產出**有旁白的相片幻燈片影片**＋**可匯出的 PPTX** — 全程走同一套 review gate 與 job pipeline。
- **🔒 自架、離線優先** — 你的 API key、你的機器、你的資料，中間不經第三方 SaaS。

### 截圖

> 截圖取自實際跑起來的 `/app`。把圖檔以下方檔名放進 `docs/screenshots/` 即會顯示於此。

| 統一 `/app` 工作站 | 人工審查關卡 |
|---|---|
| <!-- screenshot: docs/screenshots/app-home.png --> _`docs/screenshots/app-home.png`_ | <!-- screenshot: docs/screenshots/review-gate.png --> _`docs/screenshots/review-gate.png`_ |
| 右上選課，再切影片 / 視覺 / 在地化 | 每個 AI 答案都停在這裡、可編輯，核准前不外流 |

| 視覺工作台（圖卡 & 海報） | 成本面板（各站真實用量） |
|---|---|
| <!-- screenshot: docs/screenshots/visual.png --> _`docs/screenshots/visual.png`_ | <!-- screenshot: docs/screenshots/usage.png --> _`docs/screenshots/usage.png`_ |

<!-- TODO（人工）：在 docs/screenshots/ 補上上述四張截圖（此環境無瀏覽器，依「文字步驟可獨立完成、視覺後驗」） -->

### 快速開始

**一鍵體驗（Docker）** — 試水溫最快的路。內附 image 已裝好 ffmpeg + CJK 字型，除了 Docker
本身你什麼都不用裝：

```bash
cp .env.example .env          # 填入你的 GEMINI_API_KEY
cp tts_config.example.json tts_config.json   # 預設 edge-tts 即可
docker compose up -d --build  # 建置 + 背景啟動
```

接著打開 **`http://localhost:8000/app/`**。停止用 `docker compose down`（加 `-v` 連 `jobs`
volume 一起清）。要暴露到 localhost 以外（token、CORS、反向代理 + TLS）請照
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — **沒設 `EDUSTUDIO_API_TOKEN` 前別開公網 port**。

**或從原始碼跑：**

```bash
# 0. 系統相依 (非 pip): ffmpeg (+ffprobe) 任何 render 都要、Noto CJK 字型確保中文正常。
#    詳見下方「依賴分層」。

# 1. 後端 (Python 3.12)
pip install -r requirements.txt          # 核心依賴 — 裝這個就能跑 server
#   按需加裝: requirements-optional.txt(PPTX 匯出 / 語音轉文字 / F5-TTS)、
#   requirements-song.txt(SONG MV 軸)、requirements-dev.txt(跑測試)
export GEMINI_API_KEY=你的金鑰            # 或直接在 App 的「設定」頁填

# 2. 前端 (統一 /app 介面)
cd frontend && npm install && npx vite build --base=/app/   # --base=/app/ 一定要帶
cd ..

# 3. 啟動
uvicorn server.main:app --host 127.0.0.1 --port 8000
```

接著打開 **`http://127.0.0.1:8000/app/`**。

> ⚠️ 啟動路徑是 **`server.main:app`** —— 專案**沒有**根目錄 `main.py`。打成 `uvicorn main:app`
> 會報 *"Error loading ASGI app. Could not import module 'main'"*。等價指令:`python -m server.main`。

📖 **第一次用?** 完整 [**使用手冊**](docs/USER_MANUAL.md) 涵蓋每個工作站、設定對照、REST API
與疑難排解。最短路徑(考卷 → 影片 → YouTube)看 [上手指南](docs/onboarding.md)。

### 依賴分層

依賴刻意拆開，只裝你會用到的。光裝 `requirements.txt` 就足以跑起 server 與主要 pipeline
（影片、視覺、在地化文字）——要用哪個功能再加裝對應那層即可。

| 分層 | 安裝 | 加了什麼 | 不裝的話 |
|---|---|---|---|
| **核心 core** | `pip install -r requirements.txt` | Server + 影片 / 視覺 / 在地化文字 pipeline（Gemini、FastAPI、Pillow、edge-tts、PyMuPDF、matplotlib） | —（一定要裝） |
| **選用 optional** | `pip install -r requirements-optional.txt` | PPTX 匯出（`python-pptx`）、語音轉文字（`faster-whisper`，自動 GPU→CPU）、F5-TTS 聲音複製、樣本 PDF 工具、outro QR | 對應功能會優雅報錯，其餘照常 |
| **song** | `pip install -r requirements-song.txt` | 只有 SONG MV 軸 — Demucs + WhisperX（重、數 GB、建議 GPU） | song/MV 軸無法用，其他軸不受影響 |
| **dev** | `pip install -r requirements-dev.txt` | 測試套件（`pytest`、`httpx`） | 無法跑 `pytest tests/` |

**系統相依（非 pip 安裝）：**

- **ffmpeg / ffprobe** — 任何影片 render 或抽音訊*必需*。`apt install ffmpeg`／`brew install ffmpeg`／`choco install ffmpeg`。
- **Noto CJK 字型**（例 `fonts-noto-cjk`）— 簡報／黑板中文正確顯示所需。路徑可用 `CLAUDE_FONT_PATH`／`CLAUDE_FALLBACK_FONT_PATH`／`CLAUDE_MONO_FONT_PATH` 覆寫。
- **LibreOffice**（`libreoffice-impress`）— PPTX 來源功能的跨平台 renderer；Windows 已安裝 Microsoft PowerPoint 時可自動改走 COM fallback。其餘軸（考卷／簡報 PDF／文件／HTML／song）都不需要這兩種 renderer。

### 本機 release gates 與可攜式模型 cache

- 雲端 CI 執行 unit／contract／integration tests，並明確排除 `office_live`，因為 hosted runner 不保證具備 desktop Office runtime。Windows 發布前須在本機執行 `pytest -m office_live tests/test_uploads_pptx.py -q`。
- Whisper cache 搬到新電腦後，啟動 server 前設定 `HF_HOME`（例如 `HF_HOME=D:\hf-cache`）。`/health` 必須回報 `whisper.cached=true`，`cache_source` 會顯示採用的 cache 設定；缺檔 snapshot 不會被誤判為可用。

內附的 `Dockerfile` 已幫你裝好 ffmpeg 與 CJK 字型。

### 文件

| 文件 | 用途 |
|---|---|
| 📖 [`docs/USER_MANUAL.md`](docs/USER_MANUAL.md) | **完整使用手冊** — 每個工作站、設定對照、REST API、疑難排解(內含英文速查) |
| 🚀 [`docs/onboarding.md`](docs/onboarding.md) | 從 0 到 1 上手(考卷 → 影片 → YouTube) |
| 🔒 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | 正式上線部署(token · CORS · 反向代理 · TLS) |
| 🛠️ [`CONTRIBUTING.md`](CONTRIBUTING.md) · [`claude.md`](claude.md) | 貢獻指南 + 不可妥協的硬規則 |
| 🗺️ [`ROADMAP.md`](ROADMAP.md) · [`TODO.md`](TODO.md) · [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | 路線圖 · 待辦 · 變更紀錄 |
| 🔍 [`docs/CODE_REVIEW_2026-07.md`](docs/CODE_REVIEW_2026-07.md) | 最新程式碼稽核 + 改善規劃 |

### 專案結構

```
eduStudio/
├── core/          後端核心(影片 pipeline / infocards 視覺 / translation 在地化 / project …)
├── server/        FastAPI routes
├── frontend/      統一 /app 前端原始碼(React 19 + Vite，自包含建置)
├── web/           前端建置產物(/app /studio /ui 靜態檔)
├── tests/         2300+ pytest
└── STATUS.yaml    專案現況
```

---

<div align="center">

**作者 Author** · 劉瑞弘 Juihung Liu — 國立勤益科技大學 智慧自動化工程系 副教授 · [DOF Lab](https://doflab.cc)

*三個前身專案（autoSolver / infoCard / translateGemma）已整合於此，並保留原 repo 供細項功能參考。*

**授權 License** · [MIT](LICENSE) — © 2026 劉瑞弘 Juihung Liu

</div>
