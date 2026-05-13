# 研究室 onboarding — autoSolverVideo

> 給 Kiwi / Christian 或任何接手的人。**30 分鐘讀完就能跑**。
>
> 看完這份之後:`README.md` 有完整功能介紹,`ROADMAP.md` 有版本路線,
> `TODO.md` 有當前任務,`claude.md` 有硬規則。

---

## 1. 這個專案做什麼

一條 pipeline,三種輸入,終點 YouTube:

| 輸入 | 變影片 | 用什麼 renderer |
|---|---|---|
| 考題 PDF | 黑板逐題解答(劉老師旁白) | 深綠黑板 + Pillow 繪製 |
| 教學簡報 PDF | 投影片講解(每頁旁白) | 簡報原圖 letterbox |
| Blog / 文件 / Repo | AI 產簡報內容 + 講解 | Forest / Navy pptx 主題 |

主要使用者:**劉老師個人**(產 YouTube 影片給學生看)。研究室成員的角色是
**幫忙改 bug、加功能、寫測試**,不會直接拿來產自己的影片。

---

## 2. 環境準備(本機開發版)

### 必要

```bash
Python 3.10+    # 主開發 3.12
Node 20+        # React UI build
FFmpeg          # 影片合成, 含 libass for 燒字幕
Git
GEMINI_API_KEY  # 從 https://aistudio.google.com/apikey 拿
```

### 字型(Windows / Linux 不同)

- Windows:`C:/Windows/Fonts/msjh.ttc`(微軟正黑體,預設路徑)
- Mac / Linux:設環境變數
  ```bash
  export CLAUDE_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
  export CLAUDE_FALLBACK_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansSymbols-Regular.ttf
  ```

### 一鍵裝(本機跑)

```bash
git clone <repo>
cd autoSolverVideo

# Python deps (core runtime)
pip install -r requirements.txt

# 開發測試 deps (跑 pytest 才需要)
pip install -r requirements-dev.txt

# 第一次 setup
cp tts_config.example.json tts_config.json     # Windows: copy ...
cp .env.example .env                            # 編輯填 GEMINI_API_KEY

# React UI build (Track B 用)
cd web && npm install && npm run build && cd ..

# 啟動 server
python -m server.main
# → http://localhost:8000/ui/
```

### 一鍵裝(Docker 跑,v4 階段 1 A,未實測完)

```bash
cp .env.example .env       # 編輯填 GEMINI_API_KEY
cp tts_config.example.json tts_config.json
docker compose up -d --build
# → http://localhost:8000/ui/
```

---

## 3. 跑一個 PDF 看看(快速驗證流程)

```bash
# server 已啟動的話:
python scripts/submit_job.py exam D:/path/to/midterm.pdf
# → 印 job_id

# 等到 state=awaiting_review (poll 個 1-2 分鐘)
curl http://localhost:8000/jobs/<job_id>

# 開瀏覽器逐題 review (硬規則: 不能繞)
# http://localhost:8000/ui/jobs/<job_id>

# 在 UI 按 Approve → state 變 rendering → 等 ~5-10 分鐘 → done
# Artifact 在 output/<exam_stem>/qN.mp4
```

### 3a. 自動企劃 ideate(可選)

如果你有一資料夾教材想 AI 預先看過提案影片片單:

```bash
# CLI:
python scripts/run_ideate.py auto D:/Teaching/Materials --window-days 30

# 或開 http://localhost:8000/ui/proposals 點「📂 掃資料夾」modal
```

跑完 `/ui/proposals` 看 AI 建議的影片片單,點「✓ 核准」自動建 job + 進 review。

source_type 走 `auto` Gemini Vision 看 PDF 自動判斷是考題/簡報/文件,不必你手選類型。

### 3b. 工程圖 AI(可選)

`core/diagram_gen.py` 的 `generate_diagram(spec)` 可從文字描述產 matplotlib 圖
(自由體圖 / 彎矩圖 / 方塊圖等)。目前是 module-level API,未來會接 pipeline.py
step image 欄位讓影片內動態切圖。

---

## 4. 開發架構

```
autoSolverVideo/
├── pipeline.py          # 渲染核心: JSON → MP4 + SRT (~700 行)
├── solve.py             # exam_pdf → exam.json (Gemini Vision OCR + 解題)
├── slide_ingest.py      # slides_pdf → deck.json (PDF→PNG + 章節切分)
├── publish.py           # YouTube 上傳 CLI (OAuth)
├── app.py               # Track A Flask UI (legacy, 只剩 redirect)
│
├── core/                # 平台核心 (共用)
│   ├── config.py        # 路徑 / env / model 名稱 常數
│   ├── visuals.py       # SUBTITLE_BAND_HEIGHT 等 layout 常數 (v4 暖身)
│   ├── prompts_loader.py # load_prompt + prompt_version (sha256)
│   ├── outliner.py      # outline 階段 (Gemini)
│   ├── scriptor.py      # scripting 階段 (Gemini, repo/document/url)
│   ├── deck.py          # deck schema 轉 v1 exam schema 的橋
│   ├── ideate.py        # v4 階段 2 B: 自動內容企劃 (完整可運作)
│   │                    #   scan + propose (Gemini Vision) + dedupe + save
│   │                    #   + detect_source_type 自動分類
│   ├── diagram_gen.py   # v4 階段 2 E: 工程圖 AI (完整可運作)
│   │                    #   generate_diagram → propose (Gemini) → AST validate
│   │                    #   → subprocess sandbox render → PNG
│   └── render/
│       └── pptx_style.py # 5 主題 renderer (Forest / Navy / Frieren / Naruto / Journal)
│
├── server/              # Track B FastAPI (主推流程)
│   ├── main.py          # app factory + uvicorn entry
│   ├── jobs.py          # JobStore (state.json 持久化, in-memory cache)
│   ├── runner.py        # ingest + render 編排
│   ├── schemas.py       # Pydantic models (JobRecord / Proposal etc)
│   └── routes/          # REST endpoints
│
├── web/                 # React 18 + Vite + Tailwind
│   └── src/             # 元件結構: pages/ components/ api.ts
│
├── prompts/             # AI prompt 範本 .txt (v4: 從 .py 抽出)
│   ├── scriptor_*.txt
│   ├── outliner_*.txt
│   └── ideate_propose.txt
│
├── tests/               # pytest, 226 tests / GitHub Actions CI
└── docs/                # 設計文件 / RFC / 本檔
```

---

## 5. 硬規則(別繞)

完整版在 `claude.md`,**任何 PR 都要遵守**:

| # | 規則 | 為什麼 |
|---|---|---|
| 1 | **AI 數值不能未經 review 就當答案** | 學術誠信底線, exam 強制 review |
| 2 | **不要自動 `git commit`** | 變更等明確確認, 不要主動 commit |
| 3 | **修 bug 前先討論** | 除非顯而易見 typo |
| 4 | **新功能進 Track B 不進 Track A** | 2026-05 起 Track A 已退場 |
| 5 | **字型路徑走環境變數** | 跨平台支援 |
| 6 | **設定 / 路徑常數放 `core/config.py`** | 不在各模組散一份 |
| 7 | **動 schema / OAuth / .env 要先討論** | 破壞性, 影響既有資料 |

新加的 lessons learned(實戰才浮現):

- **本機 pytest 過 ≠ CI 過** — CI install 集合可能缺東西。新加 import 時要看 `.github/workflows/test.yml`
- **async 路徑的 sync I/O 要包 `to_thread`** — 否則阻 event loop 整個 server 死(F5 download 已踩)
- **改 schema 型別前先想 migration** — Pydantic v2 對舊 ISO 字串可能 parse 成不一致型別(naive↔aware datetime 已踩)

---

## 6. 你能改什麼(從小往大)

### 🟢 最容易上手(0.5~1 天)

1. **修文檔錯字 / 補充 docstring** — 對任何模組都歡迎
2. **加測試覆蓋** — 看 `docs/CODE_REVIEW.md` 「已知測試覆蓋盲點」表
3. **TODO.md 🟢 低優先項目** — `pipeline.py` 拆檔 / `requirements.txt` 整理 之類

### 🟡 中型工作(2~5 天)

4. **F5 中國腔治本** — 試拉高 cfg_strength / 換 model
5. **工程圖 AI 輔助** — v4 階段 2 E scaffold 已建,可接 iter 19 補實作
6. **Pronunciation map 補完** — 跑幾份考卷收集 念錯字
7. **內容品質**:Gemini narration 截斷率 22%,可調 prompt 或 retry 策略

### 🔴 大工程(請先討論)

8. **v4 階段 3 D 持久化 worker** — 架構決策,要 RFC,選 RQ/Celery/SQLite 自寫
9. **YouTube OAuth 安全 mount(Docker 部署)** — 影響 publish 流程
10. **課程網站整合** — 跟 IAE 系工作流需先 alignment

---

## 7. 常見問題

| 症狀 | 處理 |
|---|---|
| `python -m server.main` 啟動失敗 | 看 traceback,常見是 GEMINI_API_KEY 沒設 / google-genai 沒裝 |
| `pip install -r requirements.txt` 卡 PyMuPDF | Windows 預編 wheel 通常 OK,Linux 可能要裝 libmupdf-dev |
| 跑考卷時 server hang | F5 第一次跑會下 1.35GB,等 5-10 分(commit 318f5e8 後不阻 event loop) |
| `tts_config.json` 改了又退回 | 它跑 server / smoke test 會自動改;已 gitignored,不會誤 commit |
| FFmpeg 找不到字型 | 設 `CLAUDE_FONT_PATH` env var |
| React UI 白畫面 | `cd web && npm run build`,看 `web/dist/` 是否存在 |
| CI 紅但本機綠 | **常見!** 看 `.github/workflows/test.yml`,確認 install line 有對齊本機 |

---

## 8. 開發習慣

- 一個邏輯單位一個 commit(不要堆一大包)
- Commit message 用 `feat / fix / refactor / docs / chore / test (scope): 中文一句話`
- 改完先跑 `pytest tests/`,綠了再 commit
- 大改動先看 `docs/CODE_REVIEW.md` lessons learned 三通則
- 不確定就問,不要猜

---

## 9. 找資源

- 大方向:`README.md` + `ROADMAP.md`
- 當前任務:`TODO.md`(🌟 下階段規劃是 active 工作清單)
- 設計文件:`docs/*.md`(`ideate-design.md` / `engineering-diagram-design.md` 等)
- Code review 紀錄:`docs/CODE_REVIEW.md`(Round 1 + Round 2 + lessons learned)
- 上次 session 接手筆記:`docs/SESSION_HANDOFF.md`(給 AI / 人類都看)

有問題 → 開 issue 或直接問劉老師。

歡迎加入 DOF Lab 👋
