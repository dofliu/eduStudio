# Session Handoff — 2026-05-10

> 給下個 Claude session 看的:現況、上次做了什麼、下次可以接手什麼。
> 讀這個之前可以先掃 `claude.md` 拿產品定位 + 硬規則,再看這份拿執行細節。

---

## 你接手時專案的狀態

**整體位置**:`v3.3 完整收尾`,日常工作流 100% 跑在 Track B(:8000)。`Track A`(:5000)只剩根路徑 redirect。

```
v3.0 平台基礎 ✅ (PR-1 ~ PR-3e)
v3.1 平台合一 ✅ (PR-3f ~ PR-3m)
v3.2 基礎建設 ✅ (PR-4a / 4b / 4c)
v3.3 加分 ✅ (PR-5a Navy / 5b F5 預切句 / 5c 燒字幕)
v3.3 Phase 4 split-left layout ✅ (Option A 靜態版)
Code review Round 1 P0+P1 ✅ (4 P0 + 3 P1)
Code review Round 2 三條實戰 hotfix ✅
v4 平台收斂 (Docker / persistent worker / ideate) 📋 規劃
```

**測試覆蓋**:148 tests / 9 modules,GitHub Actions 4 組 matrix。
**最後 commit**:在 `git log --oneline -1` 查(寫稿時是 `5740e4f`)。

---

## 上一個 session(2026-05-09~10)做了什麼

### Day 1 (5/9): v3.1 + v3.2 + v3.3 加分(13 個 PR)
詳見前一份 handoff(可從 git log 5740007 那個 commit 還原)。重點:

- v3.1 平台合一(PR-3f~3m): YouTube 上傳 / 考卷編輯 / 簡報縮圖 / Library / 聲音切換 / PDF 上傳 / FAILED retry
- v3.2 基礎建設(PR-4a~4c): 單章重 render / pytest CI / structured logging
- v3.3 加分(PR-5a~5c): Navy 主題 / F5 中文預切句 / 燒字幕 進 MP4
- 文件: `docs/CODE_REVIEW.md` Round 1 (4 P0 + 4 P1) + `docs/SESSION_HANDOFF.md`

### Day 2 (5/10): P0 + P1 + Phase 4 + 三條實戰 hotfix(7 個 commit)

**Code review Round 1 follow-ups**:
- `7db9aab` P0 4 條: logging lock / utc_now tz / upload size / sys.exit → raise
- `e093720` P1 3 條: PptxStyle 越界 / F5 seg cleanup / publish 雙擊

**Phase 4 split-left**:
- `7b1eba2` SlideRenderer dispatch _render_full / _render_split_left, 左半 940 寬投影片 + 右半 920 寬 title/bullets, schema 零變更, +7 tests

**三條實戰 hotfix(Round 2)**:
- `f3fca88` AwareDatetime AfterValidator: P0 #4 沒做 schema migration, 既存 naive state.json 跟新 aware datetime 共存炸 sorted() → GET /jobs 500
- `318f5e8` F5 `_lazy_init` 改 `asyncio.to_thread`: 1.35GB safetensors download 阻 event loop, GET /jobs 全部 hang. Track A 多 process 沒踩, Track B 單一 process 踩
- `e372b7f` `update_draft` 允許 DONE state: 接通 PR-4a section re-render(本來只通一半:准重 render 但不准改 deck)
- `07c4a45` `_render_full` letterbox 進 `visible_h = HEIGHT - 180`: slide 底部 16.7% 被字幕帶蓋掉的 bug, PR-3h 引入 SlideRenderer 就有, Phase 4 才注意到

**文件**:
- `5740e4f` CODE_REVIEW.md 補 Round 2 review + lessons-learned 三通則
- TODO / ROADMAP / STATUS / claude.md 全部同步打勾

---

## 你下次可能要接的工作(按優先序)

### 🟡 中優先 — Round 2 殘留小事(看心情, 都低頻)

詳見 [docs/CODE_REVIEW.md](CODE_REVIEW.md) Round 2 段落:

- `_render_split_left` bullets 截斷時機: 越界檢查在 draw 完才檢查
- `tests/test_jobs_store.py` 165/174/176 仍用 `datetime.utcnow()` 風格不一致
- README / ROADMAP 補一句 commit `07c4a45` 之後 _render_full slide 寬度小 16.7% (visual regression)
- `tts_backend.py` 加 module-level docstring 強調「sync method 不能在 async 路徑直接呼叫」
- Phase 4 split-left bullets 上限沒 UI hint(填 10 條會被靜默截斷)

加起來 ~1 小時範圍。

### 🟢 v4 平台收斂(下個大段落)

詳見 [ROADMAP.md](../ROADMAP.md) v4 段落。架構觀察(Round 2 lessons-learned 通則指向):

> 三條 hotfix 都是「抽象層的隱性假設」,跨 commit / 跨層級才浮現衝突。值得在 v4 把這幾個假設明文化:
> - `core/visuals.py` 集中 layout 常數(SUBTITLE_BAND_HEIGHT 等)
> - `core/async_safe.py` 包 sync I/O guard, 強制 to_thread
> - schema migration 框架(下次改 type 不會踩既存資料)

具體 v4 要做的:
- **Docker**:Dockerfile + docker-compose,給雲端部署 + 學生協作用
- **持久化 worker**:取消 `asyncio.create_task` 即起即忘,server 重啟可 resume(候選 RQ / Celery / SQLite + 自寫)
- **`ideate.py` 自動內容企劃**:watched_folders + Gemini 分析 + React UI 列企劃

v4 是架構決策,動手前先列選項 + trade-off 跟 user 對齊(CLAUDE.md 硬規則)。

### 📋 加分(看心情, 跟主線無關)

- 工程圖 AI 輔助(Gemini → matplotlib / TikZ → 本地畫圖)
- 包成 Claude Code skill(`pdf-to-video` / `video-to-youtube`)
- F5 中國腔治本(GPT-SoVITS / fine-tune)
- Phase 4 Option B 累積式 split-left(section 共用一張題目圖 + 右側疊 step 行,schema 大改)

---

## 環境設定(沒變,從上次 handoff 帶過來)

```bash
OS:        Windows 11 + RTX 4080 (本機 GPU 推論 F5 用)
Python:    3.10+ (主開發 3.12)
Node:      20+ (React build)
FFmpeg:    在 PATH (libass 支援是必要, 燒字幕需要)
字型:       C:/Windows/Fonts/msjh.ttc + seguisym.ttf + consola.ttf
            (跨平台靠環境變數: CLAUDE_FONT_PATH / CLAUDE_FALLBACK_FONT_PATH /
             CLAUDE_MONO_FONT_PATH)

API key:    GEMINI_API_KEY (google-genai SDK)
            client_secret*.json (YouTube OAuth, 從 GCP Console 下)
            youtube_token.json (publish.py 第一次 CLI 跑會自動產)
F5 模型:    第一次跑會自動下載 1.35GB safetensors 到 ~/.cache/huggingface/hub/,
            之後本地命中. uvicorn 不會 hang (318f5e8 修了).
```

---

## 啟動順序(沒變)

```bash
# 1. 主 server (port 8000) — 工作流主入口
python -m server.main

# 2. (選用) Track A — 已退到只剩 redirect, 不必啟
KEEP_TRACK_A=1 python app.py    # 想保留舊 UI 才開

# 3. (開發 React) Vite dev server (port 5173) — 改 React 程式碼用
cd web && npm run dev

# 4. (production React) build + 給 server 服務
cd web && npm run build
# server.main 會自動把 web/dist mount 到 :8000/ui/
```

---

## 我建議你動工前先做這幾件事

1. **拉最新 main**:`git pull`,看上次 commit 在哪
2. **跑全測**:`pytest tests/` 該 148 passed
3. **Build 前端**:`cd web && npm run build`(確認 dist 跟 main 同步)
4. **看 STATUS.yaml + ROADMAP.md 最新段落**:確認當前 phase
5. **如果要動 server**:`python -m server.main` 啟一份起來,確認沒新 bug 才開始改
6. **F5 第一次跑**:不要 panic,1.35GB download 是正常的(`318f5e8` 後不會卡 UI)

---

## 用戶溝通風格(從 claude.md 摘要,沒變)

- **直接、精簡**。不客套開場/結尾、不過度解釋
- 技術討論用繁體中文,程式碼註解也以繁中為主
- **架構層面決策先列選項 + trade-off**,別直接動手做一版丟過去
- 「快版」= 只給結果不解釋
- 「審查」= 只找問題不重寫
- **不要自動 git commit**,變更等明確確認再 commit
- **修 bug 前先討論**,除非顯而易見 typo
- 自動模式下可以連續做多個小 commit,每個 commit 一個獨立邏輯單位

---

## 一些我犯過的錯,你避免一下

從上次 handoff 帶過來:

1. **branch 開很多會把 user 搞亂**:都直接 commit 到 main,user 比較開心。一個小邏輯單位一個 commit,不開 branch
2. **`tts_config.json` 容易誤 commit**:smoke test 跟 server 啟動會改它。每次 commit 前 `git status` 看一下,有的話 `git checkout HEAD -- tts_config.json` 還原
3. **Windows path escape**:`subtitles=` filter 對 Windows 絕對路徑(含冒號)各種 escape 規則跨 OS 不一致。我用 cwd + 相對檔名繞過(見 `pipeline._build_hardsub_cmd`)
4. **deck schema vs v1 exam schema 兩條並存**:轉換在 `core.deck.deck_to_exam_schema` / `_pptx` / `_slides` 三個 helper,每個 source_type 走哪條看 runner.py `_run_render`
5. **smoke test 後別忘清測試 job**:`store.delete('test_id')` 別讓垃圾 job 留在 jobs/

新加的(Round 2 lessons-learned, 詳見 docs/CODE_REVIEW.md):

6. **改 schema type 前先想 migration**:Pydantic v2 對舊 ISO 字串會 parse 成什麼型別?需不需要寫 normalize validator?(P0 #4 沒想就踩)
7. **單一 FastAPI process 任何 sync I/O 都要 to_thread**:F5 download / model load / requests.get / subprocess.run 在 async 路徑要包 `await asyncio.to_thread(...)`,不然阻 event loop 整個 server 卡死(318f5e8 才修)
8. **Letterbox-fit 要扣 overlay 區才算可視區**:不要用 magic number 1080,寫成 `HEIGHT - SUBTITLE_BAND_HEIGHT`(07c4a45 才修)

---

## 給你的最終確認 checklist

接手後第一輪:

- [ ] `git pull && cd web && npm run build && cd ..`
- [ ] `pytest tests/` → 148 passed
- [ ] `python -m server.main` 起來看 startup 訊息正常
- [ ] 瀏覽器 :8000/ui/ 不白畫面
- [ ] JobsIndex 看到舊 job 列表(state.json 沒壞)
- [ ] 跟 user 確認他/她想做什麼方向(Round 2 殘留 / v4 / ideate / 還是其他?)

祝你下個 session 順利。👍
