<div align="center">

# 🎓 eduStudio

**教學內容工作站 · Teaching Content Studio**

*Turn exams, slides, documents, code repos and audio into narrated teaching videos, slide decks, infographics and localized content — from one self-hostable server, organized per course, with a human review gate over every AI output.*

把考卷、講義、文件、程式碼、音檔，一站式變成**有旁白的教學影片**、**簡報 / 圖卡 / 海報**與**多語在地化內容** — 單一可自架伺服器、以「一門課一工作空間」管理、且每個 AI 產出都有人工審查關卡。

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Gemini](https://img.shields.io/badge/Google-Gemini%203-4285F4?logo=googlegemini&logoColor=white)
![Status](https://img.shields.io/badge/status-active-success)

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
| Subtitles (SRT) + one-click YouTube upload | Per-slide refine + auto chart/diagram | Flashcards (SM-2), writing correction |

### Highlights

- **🛡️ Human review gate** — AI output (especially exam answers / numbers) stops at an editable review screen before rendering. The product's core principle: *never publish unverified AI numbers.* Exam solutions are review-locked by design.
- **🗂️ One course = one workspace** — pick a course at the top; every video and visual you generate is automatically filed under it (sources · tasks · products), NotebookLM-style.
- **🎙️ Your own voice** — F5-TTS voice cloning lets narration speak in *your* voice, with automatic fallback to edge-tts / Google TTS.
- **🧩 Gemini 3 powered** — `gemini-3.5-flash` / `gemini-3.1-pro-preview` for text, `gemini-3.1-flash-image` / `gemini-3-pro-image` for images, fully configurable in-app.
- **📤 Publish-ready** — PPTX export, YouTube auto-chapters, bilingual subtitle tracks, LaTeX formula rendering, personal-brand footer baked into slides & cards.
- **🔒 Self-hosted & offline-first** — your API key, your machine, your data. No third-party SaaS in the loop.

### Quick start

```bash
# 1. Backend (Python 3.12)
pip install -r requirements.txt          # core deps
#   optional: requirements-optional.txt for F5-TTS / GPU Whisper, requirements-dev.txt for tests
export GEMINI_API_KEY=your_key           # or set it in the in-app Settings page

# 2. Frontend (the unified /app UI)
cd frontend && npm install && npx vite build --base=/app/   # --base=/app/ is required
cd ..

# 3. Run
uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Then open **`http://127.0.0.1:8000/app/`**.

### Interfaces

| Path | What | |
|---|---|---|
| **`/app`** | Unified workstation (Video · Visual · Material/Project · Publish · Status) | primary |
| `/api`, `/localization`, `/projects`, `/jobs` | REST backend (generation, translation, projects, jobs) | |
| `/docs` | Auto-generated OpenAPI docs | |
| `/studio`, `/ui` | Legacy standalone UIs (kept for reference) | legacy |

### Tech stack

`Python 3.12` · `FastAPI` · `React 19 + Vite` · `Google Gemini 3` · `faster-whisper` · `F5-TTS` · `edge-tts` · `PyMuPDF` · `python-pptx` · `matplotlib` (LaTeX) · `ffmpeg`

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
| 字幕（SRT）+ 一鍵上傳 YouTube | 單頁微調 + 自動圖表/架構圖 | 單字卡（SM-2）、寫作批改 |

### 特色

- **🛡️ 人工審查關卡** — AI 產出（尤其解題答案 / 數字）會停在**可編輯的審查頁**，核准後才渲染。核心原則：*絕不發布未經查證的 AI 數值*。考卷解答一律強制審查。
- **🗂️ 一門課＝一工作空間** — 右上選課，之後產的每支影片 / 每張圖卡都自動歸到該課（來源 · 任務 · 成品），NotebookLM 式管理。
- **🎙️ 你自己的聲音** — F5-TTS 聲音複製讓旁白用**你的**聲音念，並自動退回 edge-tts / Google TTS。
- **🧩 Gemini 3 驅動** — 文字用 `gemini-3.5-flash` / `gemini-3.1-pro-preview`，圖片用 `gemini-3.1-flash-image` / `gemini-3-pro-image`，App 內可自由設定。
- **📤 隨時可發布** — PPTX 匯出、YouTube 自動章節、雙語字幕軌、LaTeX 公式渲染、個人品牌頁尾自動帶進簡報與圖卡。
- **🔒 自架、離線優先** — 你的 API key、你的機器、你的資料，中間不經第三方 SaaS。

### 快速開始

```bash
# 1. 後端 (Python 3.12)
pip install -r requirements.txt          # 核心依賴
#   選用: requirements-optional.txt(F5-TTS / GPU Whisper)、requirements-dev.txt(測試)
export GEMINI_API_KEY=你的金鑰            # 或直接在 App 的「設定」頁填

# 2. 前端 (統一 /app 介面)
cd frontend && npm install && npx vite build --base=/app/   # --base=/app/ 一定要帶
cd ..

# 3. 啟動
uvicorn server.main:app --host 127.0.0.1 --port 8000
```

接著打開 **`http://127.0.0.1:8000/app/`**。

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

</div>
