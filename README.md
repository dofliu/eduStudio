# 教學影片自動生成平台

把三種輸入丟進來,自動產出黑板 / 簡報風格的講解影片(含字幕),最後一鍵上傳 YouTube:

1. **考題 PDF** → 黑板風格逐題解答影片(配老師旁白 + SRT 字幕)
2. **教學簡報 PDF** → 投影片講解影片(每頁逐一講解,可換我的聲音)
3. **Blog / 文件 / 程式碼 repo (txt / md / pdf / url)** → AI 產簡報大綱 → 講解影片

設計原則:同一條 pipeline、同一套 TTS / 字幕 / YouTube 上傳通道、同一個 Web UI。

---

## 目前能做到什麼 (2026-05-09 更新)

- **5 種輸入** (`source_type`):`exam_pdf` / `slides_pdf` / `repo` / `document` / `url`
- **3 種渲染風格**:深綠黑板 / 投影片原圖 letterbox / pptx 主題 (Forest 教學/Navy 科技,Pillow 純畫,無 LibreOffice 依賴)
- **2 種 TTS 後端**:edge-tts (預設, 雲端免費, 6 種聲音可切) / F5-TTS (本機聲音複製, 中文預切句修 mid-word 切錯)
- **完整 React UI** (`port 8000`):上傳 / 編輯 / Library / YouTube 上傳審查 / 即時 log / 主題切換 / 燒字幕選項 / 單章重 render
- **REST API**:非同步 job + 磁碟持久化 + per-job 結構化 log,排程器 / Webhook 友善
- **YouTube 上傳通道**:OAuth 2.0 + resumable upload + SRT 字幕同步上傳 + 章節時間軸自動算
- **148 tests + GitHub Actions CI**:Python 3.10/3.12 × Linux/Win 4 組 matrix

---

## 兩個 Server(Track A 已退場到只剩 redirect)

v3.1 平台合一完成後,日常工作只用 **Track B (port 8000)**。Track A (port 5000) 仍在但只剩根路徑 redirect。

| | Track A — Flask v1 (port 5000) | Track B — FastAPI v3 (port 8000) |
|---|---|---|
| 啟動 | `python app.py` (legacy) | `python -m server.main` (主推) |
| 入口 | / 預設 redirect 到 :8000/ui/ | http://localhost:8000/ui/ |
| 用途 | 不必再用; OAuth bootstrap 還是走 publish.py CLI | 全部工作流 |
| 過渡 | `KEEP_TRACK_A=1` 保留原行為(過渡期) | 主入口, React UI 統一介面 |

詳細 Track A → Track B 對照與功能搬遷見 [ROADMAP.md](ROADMAP.md) v3.1 段落。

---

## 快速開始

```bash
# 1. 安裝
pip install -r requirements.txt

# 2. 設 API key
export GEMINI_API_KEY=AIza...        # Linux / macOS
set GEMINI_API_KEY=AIza...           # Windows cmd

# 3. 複製 TTS 設定範本 (第一次 clone 才需要; tts_config.json 已 gitignored)
cp tts_config.example.json tts_config.json     # Linux / macOS
copy tts_config.example.json tts_config.json   # Windows

# 4a. 跑考卷 / 簡報 review UI (Track A, 主推流程)
python app.py
# → http://localhost:5000

# 4b. 跑平台 API + React UI (Track B, repo / document / url 用)
cd web && npm install && npm run build && cd ..
python -m server.main
# → http://localhost:8000  (自動 redirect 到 /ui/)
```

---

## 安裝需求

### 系統依賴
- Python 3.10+
- FFmpeg(在 PATH 裡)
- Node.js 20+ (要建 React UI 才需要)
- 中文字型(預設 `C:/Windows/Fonts/msjh.ttc` 微軟正黑體)
- 符號字型(預設 `C:/Windows/Fonts/seguisym.ttf` Segoe UI Symbol)
- 等寬字型(預設 `C:/Windows/Fonts/consola.ttf` Consolas, pptx code block 用)

### 字型路徑覆寫(macOS / Linux 必設)
```bash
export CLAUDE_FONT_PATH=/path/to/your/cjk-font.ttc
export CLAUDE_FALLBACK_FONT_PATH=/path/to/your/symbol-font.ttf
export CLAUDE_MONO_FONT_PATH=/path/to/your/mono-font.ttf
```

### 選用:F5-TTS 聲音複製
```bash
# RTX 4080 / CUDA 12.1 範例
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install f5-tts

# 錄 10~12 秒參考音檔放 voices/teacher_ref.wav
# 把 tts_config.json 的 backend 改成 "f5",填 ref_text 逐字稿
```

> F5 目前狀態:中文 mid-word 切點偶發、中國腔仍可聽出,長片建議留 edge。詳見 TODO.md。

---

## 三種使用情境

### A. 考題解答影片(成熟)

```
PDF 考題 ──▶ solve.py (Gemini Vision 三 pass)
            ──▶ app.py 編輯 (人工逐題 review)
            ──▶ batch.py 渲染 ──▶ videos/<exam_stem>/qN.mp4 + qN.srt
            ──▶ Library 影片旁 📺 上傳 YouTube
```

進入點:`http://localhost:5000` →「📄 考卷列表」→「⬆ 上傳新 PDF」。

### B. 教學簡報講解影片(成熟)

```
簡報 PDF ──▶ slide_ingest.py (PyMuPDF 切頁 → Gemini Vision 章節+逐頁 narration)
          ──▶ app.py 編輯 (縮圖預覽 + 逐頁 narration 校對)
          ──▶ batch.py 渲染 ──▶ videos/<stem>/chN.mp4
          ──▶ YouTube 上傳
```

進入點同上,上傳時選類型「簡報」。

### C. 文件 / Blog / Repo → AI 產簡報 → 影片(平台化中)

```
原始來源 ──▶ adapters (repo / document / url 三種)
            ──▶ outliner.py (Gemini 產 outline.json,章節骨架)
            ──▶ scriptor.py (逐 section Gemini, 產 deck.json: sections / slides)
            ──▶ React UI 編輯 (5 秒 auto-poll + 字數提示)
            ──▶ render → MP4 (Forest pptx 主題, code_snippet 自動取真實檔案內容)
            ──▶ (規劃中) 一鍵上傳 YouTube
```

進入點:`http://localhost:8000/ui/`。或用 CLI:
```bash
python scripts/submit_job.py repo D:/path/to/repo
python scripts/submit_job.py document D:/lecture.pdf
python scripts/submit_job.py url https://example.com/blog/article
```

---

## 平台 REST API (`server/`)

### Job 主流程
| Method | Path | 用途 |
|---|---|---|
| `GET`    | `/health`                              | 健康檢查 (含 ui_built 旗標) |
| `POST`   | `/jobs`                                | 建立 job (JSON, source.path) 並背景排程 |
| `POST`   | `/upload`                              | 多部分上傳 PDF/MD/TXT 並建 job (PR-3k) |
| `GET`    | `/jobs`                                | 列出全部 (created_at desc) |
| `GET`    | `/jobs/{id}`                           | 拿單一 job 完整 state |
| `DELETE` | `/jobs/{id}`                           | 刪除 (含磁碟資料) |
| `GET`    | `/jobs/{id}/draft`                     | 拿 deck.json |
| `PUT`    | `/jobs/{id}/draft`                     | 改 deck.json (awaiting_review / failed) |
| `POST`   | `/jobs/{id}/approve`                   | review 通過,觸發渲染 (failed 也可重試) |
| `POST`   | `/jobs/{id}/sections/{sid}/render`     | 重渲染單章 (PR-4a, done/failed 才能跑) |
| `GET`    | `/jobs/{id}/artifacts/{filename}`      | 下載 MP4 / SRT |
| `GET`    | `/jobs/{id}/log?tail=N`                | per-job log tail (PR-4c, JSONL parse 後) |

### YouTube 上傳 (PR-3f)
| Method | Path | 用途 |
|---|---|---|
| `GET`    | `/jobs/{id}/artifacts/{name}/youtube_meta`   | 預填 metadata (含章節時間軸) |
| `POST`   | `/jobs/{id}/artifacts/{name}/publish`        | 觸發 YouTube 背景上傳 |
| `GET`    | `/jobs/{id}/artifacts/{name}/youtube_status` | 上傳進度輪詢 |

### 跨 job 視圖 + 設定 (PR-3l, 3m)
| Method | Path | 用途 |
|---|---|---|
| `GET`    | `/library`                             | 跨 job 平鋪所有 mp4 (PR-3m) |
| `GET`    | `/voices`                              | 列 6 種聲音 + 當前 active |
| `POST`   | `/voices`                              | 切換聲音 (寫 tts_config.json) |
| `GET`    | `/voices/{id}/sample`                  | 試聽 mp3 sample |

### 投影片縮圖 (PR-3h)
| Method | Path | 用途 |
|---|---|---|
| `GET`    | `/slide_images/{stem}/{filename}`      | 簡報 PDF 切出的 PNG 縮圖 |

### React UI / Vanilla
| Method | Path | 用途 |
|---|---|---|
| `GET`    | `/ui/`                                 | React Web UI (預設, PR-3e) |
| `GET`    | `/editor`                              | Vanilla fallback Web UI |

詳細互動文件:`http://localhost:8000/docs` (Swagger)。

### Source types

| `source_type` | `source.path` 指向 | ingest pipeline | 預設 require_review |
|---|---|---|---|
| `exam_pdf`   | 考卷 PDF | `solve.py` 三段 Gemini | True (硬規則 #1) |
| `slides_pdf` | 簡報 PDF | `slide_ingest.py` 章節+逐頁 narration | False |
| `repo`       | 資料夾路徑 | `adapters.repo` → `outliner_repo` → `script_repo` | False |
| `document`   | PDF / MD / TXT 檔 | `adapters.document` → `outliner_long_form` → `script_long_form` | False |
| `url`        | HTTP(S) URL | `adapters.url` (BS4) → `outliner_long_form` → `script_long_form` | False |

### Job 狀態機

```
pending ── ingest ──► ingesting ──┬──► awaiting_review ──approve──┐
                                  │                                ▼
                                  └────────(require_review=False)──► rendering ──► done
                                                                                     │
                                                            (任何階段失敗) ─► failed
```

`exam_pdf` 預設 `require_review=True`(學術誠信硬規則 #1);其他類型 `False` 一路跑完。

---

## 設定檔

### `tts_config.json`
```json
{
  "backend": "edge",
  "edge": { "voice": "zh-TW-HsiaoChenNeural", "rate": "-5%" },
  "f5": {
    "ref_audio": "./voices/teacher_ref.wav",
    "ref_text": "(必填) ref_audio 的逐字稿",
    "model": "F5TTS_v1_Base",
    "speed": 0.7,
    "lead_trim_sec": 0.6,
    "remove_silence": true
  }
}
```

### `pipeline_config.json`
```json
{
  "teacher_photo": {
    "enabled": true,
    "path": "./photos/teacher.png",
    "size": 220,
    "shape": "circle",
    "margin": 40,
    "border_width": 3
  }
}
```

### `pronunciation.json`
符號 → TTS 發音對照表,longest-match 替換。新增直接編 JSON,不動 code:
```json
{
  "ωn": "omega n",
  "ζ": "zeta",
  "²": " 的平方",
  "sin(": "sine (",
  "拉氏": "拉普拉斯",
  "+": " 加 "
}
```

---

## Schema

### v1 exam schema(`solve.py` / Track A 用)

```json
{
  "exam_title": "材料力學 — 期中考",
  "problems": [
    {
      "id": "q1",
      "number": "第 1 題",
      "score": 20,
      "problem": "題目原文",
      "steps": [
        {
          "_section": "題目解讀 | 觀念切入 | 公式導入 | 代入計算 | 易錯提醒 ...",
          "display": "黑板顯示內容 (≤40 字)",
          "narration": "老師口語講解 (60~180 字)",
          "image": "(選填) 此步驟要顯示的圖"
        }
      ]
    }
  ]
}
```

### deck schema(repo / document / url 用,Track B)

```json
{
  "deck_title": "...",
  "source_type": "repo | document | url",
  "source_meta": { "path": "...", "primary_language": "python", ... },
  "sections": [
    {
      "id": "intro",
      "title": "專案目的與架構概觀",
      "slides": [
        {
          "id": "intro_1",
          "title": "為什麼有這個專案",
          "bullets": ["..."],
          "code_snippet": null,
          "code_lang": null,
          "file_path": null,
          "narration": "(100~200 字, 對應 30~60 秒語音)",
          "notes": null
        }
      ]
    }
  ]
}
```

渲染前用 `core.deck.deck_to_exam_schema_pptx` 壓平成 v1 schema 餵 pipeline。**v3.x 後可能取消這層轉換,讓 pipeline 直接吃 deck schema。**

---

## 目錄結構

```
autoSolverVideo/
├── app.py               # Track A: Flask Web UI (port 5000)
├── pipeline.py          # 渲染核心: JSON → MP4 + SRT
├── solve.py             # 考卷 PDF → exam.json (Gemini Vision)
├── slide_ingest.py      # 簡報 PDF → exam.json (slide 模式)
├── batch.py             # 批次渲染整份 exam.json
├── publish.py           # YouTube CLI + OAuth (Track A 用)
├── tts_backend.py       # TTS 抽象層 (edge / f5 / fallback)
│
├── core/                # Track B 共用 Python API
│   ├── __init__.py      #   lazy re-export
│   ├── config.py        #   path / env / 字型 / 模型常數
│   ├── deck.py          #   deck schema + deck_to_exam_schema(_pptx)
│   ├── outliner.py      #   raw_content → outline.json
│   ├── scriptor.py      #   outline → deck.json (逐 section Gemini)
│   ├── adapters/
│   │   ├── repo.py      #   資料夾掃描, ≤50 檔
│   │   ├── document.py  #   PDF / MD / TXT 單檔 long-form
│   │   └── url.py       #   靜態 HTML 文章 (BS4 啟發式)
│   └── render/
│       └── pptx_style.py  # Forest 主題 Pillow renderer
│
├── server/              # Track B: FastAPI (port 8000)
│   ├── main.py          #   app factory + uvicorn CLI + /ui/ mount
│   ├── schemas.py       #   Pydantic request / response / state
│   ├── jobs.py          #   JobStore (memory + JSON 持久化)
│   ├── runner.py        #   背景 task: source → core fn dispatch
│   └── routes/
│       ├── jobs.py      #   /jobs CRUD + /draft + /approve + /artifacts +
│                        #     /sections/{id}/render (PR-4a) + /log (PR-4c)
│       ├── youtube.py   #   PR-3f: YouTube 上傳 (per-artifact)
│       ├── slides.py    #   PR-3h: /slide_images/{stem}/{filename}
│       ├── uploads.py   #   PR-3k: POST /upload multipart
│       ├── voices.py    #   PR-3l: /voices GET/POST/sample
│       ├── library.py   #   PR-3m: /library 跨 job 平鋪
│       └── editor.py    #   Vanilla fallback Web UI
│
├── scripts/
│   └── submit_job.py    # 排程端 CLI wrapper
│
├── web/                 # React UI
│   ├── package.json     #   React 18 + TS + Vite + Tailwind
│   ├── vite.config.ts   #   base=/ui/, dev proxy → :8000
│   └── src/
│       ├── pages/       #   JobsIndex / JobEditor / Library / PublishReview
│       └── components/  #   JobCard / StatusBadge / Toast / CreateJobForm /
│                        #   SlideEditor / StepEditor / ExamProblemsPanel /
│                        #   VoicePicker / LogPanel
│
├── tests/               # PR-4b: pytest (148 tests, 9 modules)
├── docs/
│   ├── CODE_REVIEW.md   # 2026-05-09 獨立審查結果, 4 P0 + 4 P1 follow-ups
│   └── SESSION_HANDOFF.md  # 給下個 Claude session 接手用
├── pyproject.toml       # pytest 設定
├── requirements-dev.txt # pytest + httpx
├── .github/
│   └── workflows/
│       └── test.yml     # GitHub Actions CI (4 組 matrix)
│
├── exams/               # exam.json (Track A 編輯, gitignored)
├── pdfs/                # 上傳的 PDF 原檔 (gitignored)
├── slides/              # 簡報 PDF 切出的 PNG (gitignored)
├── videos/              # 影片輸出, 每份一個子目錄 (gitignored)
├── voices/              # F5 ref + edge 試聽樣本 (部份 gitignored)
├── photos/              # 老師頭像 overlay (gitignored)
├── jobs/                # Track B job 持久化 (gitignored)
│   └── <job_id>/
│       ├── state.json
│       ├── raw_content.json    # repo / document / url 才有
│       ├── outline.json        # 同上
│       ├── deck.json
│       └── artifacts/
└── work/                # 渲染暫存 (gitignored)
```

---

## 排程使用

### `submit_job.py` CLI

```bash
# repo 講解 (預設 require_review=false, 一路跑完)
python scripts/submit_job.py repo D:/path/to/repo

# 文件 (PDF / MD / TXT)
python scripts/submit_job.py document D:/lecture.pdf

# 部落格文章 / 網頁
python scripts/submit_job.py url https://example.com/blog/article

# 考卷 (預設 require_review=true, 加 --no-review 跳過 review 一路跑)
python scripts/submit_job.py exam D:/exam.pdf --no-review

# 跨機器: 指 server 位址
python scripts/submit_job.py repo D:/repo --server http://192.168.1.5:8000
```

### Windows 工作排程器
1. 開啟「工作排程器」→ 建立基本工作
2. 觸發程序: 每日 / 每週
3. 動作: 啟動程式
   - 程式: `python`
   - 引數: `D:\Project_CodingSimulation\...\scripts\submit_job.py repo D:\path`

---

## 人工 Review(硬規則)

> **AI 產出的數值不能未經人工 review 就當最終答案。**

對 **`exam_pdf`** 強制 `require_review=True`,job 會停在 `awaiting_review`,人去 UI 逐題 review 過再 `approve`。其他 source 預設不停,但仍可改 `options.require_review=true` 強制停下。

Gemini 偶爾會犯的錯:
- 單位換算寫錯(kN vs N)
- 公式記憶錯(`δ = ML/(EI)` vs `δ = PL³/(3EI)`)
- 計算數值偏差
- 5% vs 2% 安定時間準則混用

學術誠信底線,不可妥協。

---

## 常見問題

**Q: 影片字幕太大蓋到最後一步?**
A: 已處理 — 渲染時底部 220px 預留給字幕,SRT 按句切。播放器(VLC / PotPlayer)自己調字幕大小亦可。

**Q: 數學符號 `≤` `≥` 變成 □(tofu)?**
A: 預設用 Segoe UI Symbol fallback。設 `CLAUDE_FALLBACK_FONT_PATH` 換字型。

**Q: `ζωn` 被唸成 "zetaomega n" 黏一起?**
A: 已修 — `normalize_for_tts` 替換時前後補空白再 collapse。

**Q: Gemini 只產 10 個 step,不夠深入?**
A: `solve.py` SYSTEM_PROMPT 已要求計算題 ≥ 20 step,概念類 narration ≥ 130 字。仍偷懶就再跑一次或升 Gemini 2.5 Pro。

**Q: F5-TTS 輸出亂掉(幻覺)?**
A: 多半是 ref_audio 跟 ref_text 沒對齊。F5 自動截 ref 到 12 秒,把 ref_audio 重截到 ≤ 12 秒,ref_text 只寫那段內容。

**Q: 想換聲音?**
A: Track B header 有「🗣 聲音」下拉即時試聽(PR-3l);也可改 `tts_config.json` 的 `edge.voice`。

**Q: render 中途想看進度?**
A: JobEditor 編輯頁的「📋 Job Log」摺疊面板(PR-4c),展開後 INGESTING / RENDERING 期間每 3 秒 auto-poll。

**Q: 改一張 slide 要重跑整份 30 分鐘?**
A: 不用。state=DONE 後每章 header 有「🎬 重 render 本章」(PR-4a)只重跑這一章。

---

## 開發 / 測試

```bash
# 跑單元測試
pip install -r requirements-dev.txt
pytest tests/

# 確認 React UI build 過
cd web && npm install && npm run build
```

GitHub Actions 在 push / PR 時跑 4 組 matrix(Python 3.10/3.12 × Linux/Win)。

---

## 相關文件

- [ROADMAP.md](ROADMAP.md) — 版本路線圖(v3.1+v3.2 完成,v3.3/v4 規劃中)
- [TODO.md](TODO.md) — 短期可立即做的事項 + Code review follow-ups
- [claude.md](claude.md) — 專案規則 / 溝通原則(給 Claude Code 用)
- [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md) — 2026-05-09 獨立審查結果
- [docs/SESSION_HANDOFF.md](docs/SESSION_HANDOFF.md) — 給下個 Claude session 接手用

---

## 授權

個人 / 教學用途。外部分享影片前請確認考題版權。
