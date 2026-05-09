# Session Handoff — 2026-05-09

> 給下個 Claude session 看的:現況、上次做了什麼、下次可以接手什麼。
> 讀這個之前可以先掃 `claude.md` 拿產品定位 + 硬規則,再看這份拿執行細節。

---

## 你接手時專案的狀態

**整體位置**:`v3.3 部份完成`,日常工作流 100% 跑在 Track B(:8000)。`Track A`(:5000)只剩根路徑 redirect。

```
v3.0 平台基礎 ✅ (PR-1 ~ PR-3e)
v3.1 平台合一 ✅ (PR-3f ~ PR-3m)
v3.2 基礎建設 ✅ (PR-4a / 4b / 4c)
v3.3 加分 ✅ 部份 (PR-5a Navy / 5b F5 預切句 / 5c 燒字幕)
v3.3 Phase 4 split-left layout ⏳ 待做
Code review follow-ups (4 P0 + 4 P1) ⏳ 待補
v4 平台收斂 (Docker / persistent worker / ideate) 📋 規劃
```

**測試覆蓋**:140 tests / 8 modules,GitHub Actions 4 組 matrix。
**最後 commit**:在 `git log --oneline -1` 查。

---

## 上一個 session(2026-05-08~09)做了什麼

兩天連續做完 **13 個 PR**,從 v3.0 完成狀態跨到 v3.3 加分:

### v3.1 平台合一(把 Track A 功能搬到 Track B)
- **PR-3f** Track B 接 YouTube 上傳通道(per-artifact upload + 章節時間軸自動產 + 進度輪詢)
- **PR-3g** 考卷 v1 schema 接 React UI(取代 Flask /edit)
- **PR-3h** slides_pdf 升 deck schema + 投影片縮圖預覽
- **PR-3i** Track A redirect(預設 / → :8000/ui/, KEEP_TRACK_A=1 可關)
- **fix/static-mime-windows** 修 Windows .js MIME(React UI 白畫面)
- **PR-3j** FAILED 可編輯 + retry render
- **PR-3k** Track B PDF multipart 上傳(`POST /upload`)
- **PR-3l** 聲音切換 picker + 試聽 sample
- **PR-3m** 跨 job 影片 Library 頁

### v3.2 基礎建設
- **PR-4a** 單章 / 單題重 render(`POST /jobs/{id}/sections/{sid}/render`)
- **PR-4b** pytest 基底 + GitHub Actions CI(108 tests 初版,後加到 140)
- **PR-4c** structured logging(per-job log file + React UI tail panel)

### v3.3 加分項目
- **PR-5a** Navy pptx 主題(forest/navy 切換)
- **PR-5b** F5 中文預切句(治本 mid-word 切錯)
- **PR-5c** 燒字幕進 MP4 選項(UI checkbox + ffmpeg subtitles filter)

### 文件
- `docs/CODE_REVIEW.md` 獨立審查 13 個 commit,4 P0 + 4 P1 follow-ups
- 重整 README / ROADMAP / TODO / STATUS / claude.md

---

## 你下次可能要接的工作(按優先序)

### 🔴 P0 follow-ups (詳見 [docs/CODE_REVIEW.md](CODE_REVIEW.md))
1. `core/logging_setup.py` `_job_handlers` 加 `threading.Lock`(5 行)
2. `utc_now()` 改 `datetime.now(timezone.utc)`(2 行)
3. `/upload` 加 `MAX_UPLOAD_SIZE` + content-length 預檢(10 行)
4. `solve.py` 改 raise 取代 `sys.exit()`,清掉 runner 的 `SystemExit` catch hack

加起來大約半天,順手做掉再上戰場比較安心。

### 🟡 中優先 — Phase 4 split-left layout
- `SlideRenderer` 加 `layout="split-left"`,投影片縮到左半,右半當黑板區疊累積式 step
- 給解題型投影片用(目前 layout="full" 全螢幕)
- 動 `pipeline.py` 的 SlideRenderer + React 端 SlideEditor 加 layout 下拉

### 🟢 v4 平台收斂(看時機)
- **Docker**:Dockerfile + docker-compose,給雲端部署用
- **持久化 worker**:取消 `asyncio.create_task` 即起即忘,server 重啟可 resume(候選 RQ / Celery / SQLite + 自寫)
- **`ideate.py` 自動內容企劃**:watched_folders + Gemini 分析 + React UI 列企劃

### 📋 加分(看心情)
- 工程圖 AI 輔助(Gemini → matplotlib / TikZ → 本地畫圖)
- 包成 Claude Code skill (`pdf-to-video` / `video-to-youtube`)
- F5 中國腔治本(GPT-SoVITS / fine-tune)

---

## 環境設定

```bash
# 你預期會看到的環境
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
```

---

## 啟動順序

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
2. **跑全測**:`pytest tests/` 該 140 passed
3. **Build 前端**:`cd web && npm run build`(確認 dist 跟 main 同步)
4. **看 STATUS.yaml + ROADMAP.md 最新段落**:確認當前 phase
5. **如果要動 server**:`python -m server.main` 啟一份起來,確認沒新 bug 才開始改

---

## 用戶溝通風格(從 claude.md 摘要)

- **直接、精簡**。不客套開場/結尾、不過度解釋
- 技術討論用繁體中文,程式碼註解也以繁中為主
- **架構層面決策先列選項 + trade-off**,別直接動手做一版丟過去
- 「快版」= 只給結果不解釋
- 「審查」= 只找問題不重寫
- **不要自動 git commit**,變更等明確確認再 commit
- **修 bug 前先討論**,除非顯而易見 typo
- 自動模式下可以連續做多個小 PR,但每個 PR 一個獨立 commit + push

---

## 一些我犯過的錯,你避免一下

1. **branch 開很多會把 user 搞亂**:5 個 PR branch 同時 push 然後個別 merge,user 混亂。後來改成都直接 commit 到 main,user 比較開心。一個小 PR 一個 commit,不開 branch
2. **`tts_config.json` 容易誤 commit**:smoke test 跟 server 啟動會改它。每次 commit 前 `git status` 看一下,有的話 `git checkout HEAD -- tts_config.json` 還原
3. **Windows path escape**:`subtitles=` filter 對 Windows 絕對路徑(含冒號)各種 escape 規則跨 OS 不一致。我用 cwd + 相對檔名繞過(見 `pipeline._build_hardsub_cmd`)
4. **deck schema vs v1 exam schema 兩條並存**:轉換在 `core.deck.deck_to_exam_schema` / `_pptx` / `_slides` 三個 helper,每個 source_type 走哪條看 runner.py `_run_render`
5. **smoke test 後別忘清測試 job**:`store.delete('test_id')` 別讓垃圾 job 留在 jobs/

---

## 最近實戰跑過的 jobs(你接手時可能還在)

`b40d51a96a07` — Chap05 第五章 穩定性分析 (50 頁簡報, slides_pdf, mock=False, edge backend)
- 上次狀態:render 中(50 頁要 30~40 分鐘)
- 用來實戰驗證 PR-3h slides_pdf 升 deck schema + PR-3f YouTube 上傳

如果還在 rendering 不要去打擾它,等 done 再用 PublishReview 試 YouTube 上傳。

---

## 給你的最終確認 checklist

接手後第一輪:

- [ ] `git pull && cd web && npm run build && cd ..`
- [ ] `pytest tests/` → 140 passed
- [ ] `python -m server.main` 起來看 startup 訊息正常
- [ ] 瀏覽器 :8000/ui/ 不白畫面
- [ ] JobsIndex 看到舊 job 列表(state.json 沒壞)
- [ ] 跟 user 確認他/她想做什麼方向(Phase 4 / P0 follow-ups / v4 / 還是其他?)

祝你下個 session 順利。👍
