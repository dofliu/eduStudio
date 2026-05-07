# 考卷檢討影片自動生成系統

把一份期中考 PDF 丟進去,自動產生每題的「黑板解題影片」(含老師口語旁白 + SRT 字幕)。
目的:考完當週就能給學生完整的解題影片,省去錄影 / 直播時間。

---

## 特色

- **PDF → exam.json**:Gemini 2.5 Flash Vision 讀題,自動拆解 20~30 個教學步驟(題目解讀 → 觀念切入 → 公式導入 → 代入計算 → 結果解讀 → 易錯提醒)
- **黑板風格渲染**:1080p 深綠黑板,粉筆色階分層(標題 / 題目 / 已講步驟 / 最新步驟黃字)
- **自動滾動**:步驟累積超過可視區時只保留最新 N 步,下方永遠留 220px 給字幕
- **混合字型 fallback**:主字型缺的數學符號(`≤`、`≥`、`∫` …)自動改用 Segoe UI Symbol 畫,不會 tofu
- **Web UI 全流程**:考卷列表 → 上傳 PDF → Gemini 解析 → 逐題編輯 → 渲染 → 跨考卷影片 Library
- **TTS 可插拔**:Edge-TTS(雲端免費,預設)或 F5-TTS(本機聲音複製,選用)
- **聲音選單**:UI 內切換 5 種邊緣聲音,即時試聽
- **老師頭像 overlay**:右下角圓形照片,營造「有老師在講話」感
- **發音前處理**:分式 `1/(s+3)` 自動改寫成「s 加 3 分之 1」,三角函數、拉氏轉換、希臘字母都有對照表
- **SRT 句級字幕**:narration 按 `。！？` 拆句,每句一個 cue,播放器自然縮成 1 行不擋畫面

---

## 快速開始

```bash
# 1. 安裝
pip install -r requirements.txt

# 2. 設 API key (.bashrc / 系統環境變數)
export GEMINI_API_KEY=AIza...

# 3. 起 Web UI(首次會自動把 repo root 散落的 exam JSON 搬到 exams/)
python app.py
# → 瀏覽器打開 http://localhost:5000
```

介面上:

1. 「📄 考卷列表」→「⬆ 上傳新 PDF」→ 拖 PDF 進去
2. Gemini 解析(~30~60 秒,可勾「Mock 模式」省 API 費)
3. 自動跳到編輯頁 → 逐題 review display / narration
4. 單題「🎬 儲存並渲染」或整份「🎬 批次渲染全部」
5. 完成後在「📚 Library」頁跨考卷瀏覽所有 MP4

---

## 安裝

### 系統需求
- Python 3.10+
- FFmpeg(在 PATH 裡)
- 中文字型(預設 `C:/Windows/Fonts/msjh.ttc` 微軟正黑體)
- 符號字型(預設 `C:/Windows/Fonts/seguisym.ttf` Segoe UI Symbol)

### Windows
```powershell
# 安裝 ffmpeg (https://www.gyan.dev/ffmpeg/builds/ 或 choco install ffmpeg)
pip install -r requirements.txt
```

字型路徑如需自訂:
```bash
set CLAUDE_FONT_PATH=C:\路徑\你的中文字型.ttc
set CLAUDE_FALLBACK_FONT_PATH=C:\路徑\你的符號字型.ttf
```

### macOS / Linux
```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt install ffmpeg fonts-noto-cjk

pip install -r requirements.txt
```
路徑透過環境變數 `CLAUDE_FONT_PATH` / `CLAUDE_FALLBACK_FONT_PATH` 指向本機字型。

### 選用:F5-TTS(本機聲音複製)
```bash
# RTX 4080 / CUDA 12.1 的情況
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install f5-tts

# 錄 10~12 秒參考音檔放 voices/teacher_ref.wav
# 在 tts_config.json 把 backend 改成 "f5",填 ref_text 逐字稿
```

---

## 使用流程

### 網頁介面(推薦)

```bash
python app.py                    # 不指定考卷,從列表頁開始
python app.py exams/real_exam.json   # 直接預開某份
```

### 指令行

```bash
# 單 PDF → exam.json
python solve.py exams/my_exam.pdf exams/my_exam.json

# 跳過 API 用 mock 資料測流程
python solve.py sample_exam.pdf exams/mock.json --mock

# 整份批次渲染(輸出到 videos/<exam_stem>/)
python batch.py exams/my_exam.json

# 只渲染特定題目
python batch.py exams/my_exam.json --only q1 q3
```

---

## 目錄結構

```
autoSolverVideo/
├── app.py              # Web UI (Flask)
├── pipeline.py         # v0 核心渲染:JSON → MP4 + SRT
├── solve.py            # PDF → exam.json (Gemini Vision)
├── slide_ingest.py     # 簡報 PDF → exam.json (slide 模式)
├── batch.py            # 呼叫 pipeline 跑整份考卷
├── publish.py          # 上傳 MP4 + SRT 到 YouTube
├── tts_backend.py      # TTS 抽象層 (edge / f5 / fallback)
├── make_sample_pdf.py  # 測試用考卷產生器
│
├── core/               # 公開 Python API (PR-1 引入,for 未來 FastAPI 包裝)
│   ├── __init__.py     #   re-export render_video / solve_pdf / ingest_slides 等
│   ├── config.py       #   集中 paths / env vars / 模型名 / 字型路徑常數
│   ├── runtime.py      #   setup_utf8_stdout() (Windows cp950 修正)
│   └── text_utils.py   #   strip_latex / clean_json_escapes
│
├── server/             # FastAPI server (PR-2a)
│   ├── main.py         #   app factory + uvicorn CLI
│   ├── schemas.py      #   Pydantic request / response / state models
│   ├── jobs.py         #   JobStore (in-memory + JSON 檔案持久化)
│   ├── runner.py       #   背景任務 dispatch (source_type → core fn)
│   └── routes/jobs.py  #   /jobs CRUD + /draft + /approve + /artifacts
│
├── jobs/               # Server runtime (gitignored)
│   └── <job_id>/state.json + deck.json + artifacts/
│
├── tts_config.json     # TTS 設定(backend、voice、速度…)
├── pipeline_config.json  # 渲染設定(老師頭像 overlay …)
├── pronunciation.json  # 符號 → TTS 發音對照表
│
├── exams/              # 考卷 JSON(網頁可上傳、編輯、渲染)
├── pdfs/               # 上傳的 PDF 原檔(gitignored)
├── videos/             # 影片輸出,每份考卷一個子目錄
│   └── <exam_stem>/
│       ├── q1.mp4
│       ├── q1.srt
│       └── q1.json
├── voices/
│   ├── teacher_ref.wav       # F5-TTS 參考音(gitignored)
│   └── samples/              # Edge-TTS 5 支聲音試聽樣本
├── photos/
│   └── teacher.png           # 右下角老師頭像(gitignored)
├── tools/
│   └── fetch_ref_voice.py    # YouTube → WAV 工具
└── work/               # 渲染暫存(gitignored)
```

---

## 設定檔

### `tts_config.json`

```json
{
  "backend": "edge",
  "edge": { "voice": "zh-TW-HsiaoChenNeural", "rate": "-5%" },
  "f5": {
    "ref_audio": "./voices/teacher_ref.wav",
    "ref_text": "(必填)ref_audio 的逐字稿",
    "model": "F5TTS_v1_Base",
    "speed": 0.7,
    "lead_trim_sec": 0.6,
    "remove_silence": true
  }
}
```

- Web UI 的聲音下拉選單改的就是 `edge.voice`
- `backend="f5"` 失敗會自動 fallback 到 edge,不會卡住 pipeline

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

符號 → TTS 發音對照表,longest-match 替換。新增符號直接編 JSON,不用動 code。
範例:

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

同時 `pipeline.py` 對 `1/(s+3)` 這類有括號的分式會自動改寫成「s 加 3 分之 1」。

---

## Schema

### v1 整份考卷格式(`solve.py` / `app.py` 用)

```json
{
  "exam_title": "自動控制 — 期中考",
  "problems": [
    {
      "id": "q1",
      "number": "第 1 題",
      "score": 20,
      "problem": "題目原文(簡潔,保留關鍵數值)",
      "steps": [
        {
          "_section": "題目解讀 | 觀念切入 | 公式導入 | 代入計算 | 單位檢查 | 結果解讀 | 易錯提醒 | 填充作答",
          "display": "黑板顯示內容(≤40 字,公式/等式/關鍵字)",
          "narration": "老師口語講解(60~180 字,含停頓標點)",
          "image": "(選填)此步驟要顯示的圖,覆蓋上一個 image"
        }
      ]
    }
  ]
}
```

- `_section` 是 Gemini 自我分類用的 meta,pipeline / UI 不依賴它
- `display` ≤ 40 字,漸進式累積顯示
- `narration` 分級:概念類 ≥ 130 字、代入計算 60~120 字
- `image` 可選,方塊圖化簡這類「每步不同圖」的題型會派上用場

### v0 單題格式(`pipeline.py` 吃這個)

```json
{
  "title": "自動控制 — 第 1 題",
  "subtitle": "題目前 30 字...",
  "problem": "題目原文",
  "steps": [ { "display": "...", "narration": "..." } ],
  "image": "(選填)題目層級的圖,fallback"
}
```

---

## 架構

```
考卷 PDF
    │
    ▼  solve.py (Gemini 2.5 Flash Vision)
exam.json  ───── exams/<stem>.json
    │
    ▼  app.py  (Flask Web UI,人工逐題 review)
    │           ├─ 聲音選單   (tts_config.json)
    │           ├─ 老師頭像   (pipeline_config.json)
    │           └─ 發音表     (pronunciation.json)
    ▼
batch.py  ──►  pipeline.py  ◄──  tts_backend.py
    │                            ├─ EdgeTTS
    │                            └─ F5TTS (選用)
    ▼
videos/<exam_stem>/
    ├── q1.mp4 + q1.srt
    ├── q2.mp4 + q2.srt
    └── ...
```

---

## REST API (`server/`)

PR-2a 引入的 FastAPI server,把 `core/` 包成 HTTP 端點供排程器 / 前端 / Webhook 使用。
Job 採非同步背景執行 + JSON 檔案持久化 (重啟保留)。

### 啟動

```bash
# 開發模式 (auto-reload)
python -m server.main --reload

# 預設 host=127.0.0.1 port=8000
python -m server.main --port 8000

# 也可以用 uvicorn (CI / docker compose)
uvicorn server.main:app --host 127.0.0.1 --port 8000
```

開瀏覽器到 `http://localhost:8000/docs` 看互動式 OpenAPI 文件。

### 端點

| Method | Path | 用途 |
|---|---|---|
| `GET`    | `/health`                              | 健康檢查 |
| `POST`   | `/jobs`                                | 建立 job 並背景排程 |
| `GET`    | `/jobs`                                | 列出全部 (created_at desc) |
| `GET`    | `/jobs/{id}`                           | 拿單一 job 完整 state |
| `DELETE` | `/jobs/{id}`                           | 刪除 (含磁碟資料) |
| `GET`    | `/jobs/{id}/draft`                     | 拿 deck.json |
| `PUT`    | `/jobs/{id}/draft`                     | 改 deck.json (僅 awaiting_review) |
| `POST`   | `/jobs/{id}/approve`                   | review 通過,觸發渲染 |
| `GET`    | `/jobs/{id}/artifacts/{filename}`      | 下載 MP4 / SRT |

### Job 狀態機

```
pending ── ingest ──► ingesting ──┬──► awaiting_review ──approve──┐
                                  │                                ▼
                                  └────────(require_review=False)──► rendering ──► done
                                                                                     │
                                                            (任何階段失敗) ─► failed
```

`require_review` 預設值依 `source_type`:
- `exam_pdf` → `True` (CLAUDE.md 硬規則 #1: AI 答案必須人工 review)
- `slides_pdf` → `False` (簡報講解風險低,可一路跑完)

### 範例:建立一個 mock exam job

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "exam_pdf",
    "source": {"path": "D:/path/to/exam.pdf"},
    "options": {"mock": true, "require_review": true}
  }'
# {"job_id":"abc123def456","state":"pending","status_url":"/jobs/abc123def456"}

# Poll
curl http://localhost:8000/jobs/abc123def456

# 看 deck
curl http://localhost:8000/jobs/abc123def456/draft

# 通過 review,進渲染
curl -X POST http://localhost:8000/jobs/abc123def456/approve

# 下載成果
curl http://localhost:8000/jobs/abc123def456/artifacts/q1.mp4 -o q1.mp4
```

### 檔案佈局

```
jobs/                          # gitignored
└── <job_id>/
    ├── state.json             # JobRecord (狀態 / stages / artifacts)
    ├── deck.json              # ingest 產物 (exam.json schema)
    └── artifacts/
        ├── q1.mp4 / q1.srt / q1.json
        └── ...
```

### 排程使用

未來搭配 cron / Windows Task Scheduler / scheduled-tasks MCP, 直接 `curl` 即可
觸發定期 ingest + render, 不必 Web UI。`require_review=False` + `mock=False` 可以
在後台跑完整 pipeline。

---

## 公開 Python API (`core/`)

PR-1 引入的薄再匯出層,提供穩定的 import 介面給未來 FastAPI / scheduled job 使用。
原 CLI 入口(`python pipeline.py`、`python solve.py` 等)行為**完全沒變**。

```python
import core

# 呼叫主功能
exam_data = core.solve_pdf(Path("exam.pdf"))               # PDF → dict (Gemini)
core.ingest_slides(Path("slides.pdf"), Path("out.json"),    # 簡報 PDF → dict
                   mock=False, single=False, brief=False)
await core.render_video("q1.json", "q1_out")                # JSON → MP4 + SRT
v0_dict = core.problem_to_v0_json(exam_title, prob)         # v1 → v0 schema

# TTS
backend = core.load_tts_backend()
await backend.synthesize("文字內容", Path("out.mp3"))

# YouTube
creds = core.get_youtube_credentials()
video_id = core.upload_video(youtube, video_path, title=..., description=..., ...)

# 文字工具
clean = core.strip_latex(r"$\theta = \frac{a}{b}$")
fixed = core.clean_json_escapes(raw_llm_output)

# 設定常數 (paths / env vars / model name / 字型路徑)
core.config.PROJECT_ROOT
core.config.GEMINI_MODEL
core.config.get_font_path()
```

設計重點:
- **Lazy import** — `core/__init__.py` 用 `__getattr__` 第一次存取才載入對應模組,
  避免 import core 就把 PIL / pymupdf / google-genai 一次拉進來
- **無 import 副作用** — `setup_utf8_stdout()` 只在 CLI / Web 啟動時才呼叫,
  FastAPI process 不會被改 stdout
- **向後相容** — `from solve import strip_latex` 仍然能用 (solve.py 從 core re-export)

---

## 人工 Review(硬規則)

這個系統有一條**不可妥協的原則**:

> AI 產出的數值不能未經人工 review 就當最終答案。

每一個 step、每一個公式、每一個數字都必須透過 Web UI 逐段檢查。Gemini 偶爾會:
- 單位換算寫錯(kN vs N)
- 公式記憶錯(例如 `δ = ML/(EI)` vs `δ = PL³/(3EI)`)
- 計算數值偏差
- 5% vs 2% 安定時間準則混用

**上傳完 PDF → 一定要進編輯頁檢查過再渲染**,這是學術誠信底線。

---

## 常見問題

**Q: 影片字幕太大蓋到最後一步?**
A: 已處理 — 渲染時底部 220px 預留給字幕;SRT 按句切,播放器自然縮 1 行。還是太大就在播放器(VLC / PotPlayer)自己調字幕大小。

**Q: 數學符號 `≤` `≥` 變成 □(tofu)?**
A: 預設用 Segoe UI Symbol 做 fallback。如果你的字型不一樣,設環境變數 `CLAUDE_FALLBACK_FONT_PATH`。

**Q: `ζωn` 被唸成 "zetaomega n" 黏一起?**
A: 已修 — `normalize_for_tts` 替換時前後補空白再 collapse。

**Q: Gemini 只產 10 個 step,不夠深入?**
A: `solve.py` 的 SYSTEM_PROMPT 已硬規則要求計算題 ≥ 20 step、概念類 narration ≥ 130 字。Gemini 仍偶爾偷懶,可再跑一次 / 微調 prompt / 升級 Gemini 2.5 Pro。

**Q: F5-TTS 輸出內容亂掉(幻覺)?**
A: 幾乎是 ref_audio 跟 ref_text 沒對齊。F5 自動把 ref 截到 12 秒,若你 ref_audio 是 15 秒但 ref_text 對應 15 秒,對齊會壞。把 ref 重截到 ≤ 12 秒,ref_text 只寫那段的內容。

**Q: 想換聲音?**
A: Web UI header 有「🗣 聲音」下拉,即時試聽再切換;或改 `tts_config.json` 的 `edge.voice`。

---

## 相關文件

- [ROADMAP.md](ROADMAP.md) — 未來功能規劃
- [TODO.md](TODO.md) — 短期可立即做的事項
- [CLAUDE.md](CLAUDE.md) — 專案規則 / 溝通原則(給 Claude Code 用)

---

## 授權

個人 / 教學用途。外部分享影片前請確認考題版權。
