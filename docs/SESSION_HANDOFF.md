# Session Handoff — 2026-05-13

> 給下個 Claude session 看的:現況、上次做了什麼、下次可以接手什麼。
> 讀這個之前可以先掃 `claude.md` 拿產品定位 + 硬規則,再看這份拿執行細節。

---

## 你接手時專案的狀態

**整體位置**:`v4 規劃` 進行中。階段 1 A(Docker)做完 server-side,等 user 本機實測;階段 2 B(ideate.py)scaffold + scan/save 完成,還缺 Gemini call。

```
v3.0~3.3 全部 ✅ (PR-1 ~ PR-5c + Phase 4 + Code review Round 1+2)
v4 暖身 ✅ — core/visuals.py 集中 layout 常數 (commit 8abfb2e)

v4 階段 1 A: Docker 進行中 (commit d4b3b04 + 3fe99e3)
  ✅ Dockerfile v1 draft + docker-compose.yml v1 + .env.example
  ⏳ user 本機 docker build / compose up 實測
  ⏳ F5 GPU passthrough (nvidia-docker)
  ⏳ production reverse proxy (nginx + TLS)
  ⏳ YouTube OAuth client_secret 安全 mount (STOP, 等用戶討論)

v4 階段 1 C: Claude Code skill 進行中 (commit 0e6cddb)
  ✅ .claude/skills/pdf-to-video/SKILL.md scaffold
  ⏳ 本機實測 + 自動 poll bash helper
  ⏳ video-to-youtube skill (OAuth STOP)

v4 階段 2 B: ideate.py 進行中 (commit f894b74 + f533995)
  ✅ scaffold + design RFC (docs/ideate-design.md)
  ✅ scan_changed_files + load/save_proposals + 15 tests
  ⏳ iter 12 propose_from_file (Gemini Vision call, mock tests)
  ⏳ iter 13 dedupe_against_jobs
  ⏳ iter 14 server route + React UI

技術債清理 ✅:
  ✅ tts_config.json gitignored + example (commit 008ae1e)
  ✅ requirements.txt 分層 + 修漏列 google-genai (commit f8ad547)
  ✅ 死碼 deps 移除 (anthropic / reportlab / pdfplumber, commit 7b68209)
  ✅ scriptor.py + outliner.py prompt 抽到 prompts/*.txt (commit 1828ac5 + a08c15f)
     兩檔合計 987 → 777 行 (-21%), 4 個 .txt + prompts_loader (sha256 版本追蹤)

測試覆蓋 ✅:
  ✅ test_upload +7 (CR 盲點, commit 8548906)
  ✅ test_hardsub +4 (CR 盲點收尾, commit f44ed8f)
  共 198 tests / 10 modules / GitHub Actions 4 組 matrix
```

**最後 commit**:`a08c15f` (寫稿時)
**測試**:198 tests passed (1.18s 本機)

---

## 上次 session (2026-05-12 ~ 13) 做了什麼

User 啟動了 `/loop /advance` 自動化迭代,**15 個 iter 全程綠燈**:

### iter 1~5: TODO 清理 + CI 紅修
- `tts_config.json` gitignored + example 範本 (踩過 2 次的誤 commit)
- LogPanel auto-scroll 上滑不打斷 (pin-to-bottom pattern)
- `pdf-to-video` skill scaffold
- `test_upload` +7 tests (FastAPI TestClient 第一個整合測試)
- CI 紅修: `python-multipart` 缺裝(本機過 ≠ CI 過第二次教訓)

### iter 6~9: v4 階段 1 A Docker
- Dockerfile v1 draft (multi-stage, Noto CJK 字型, ~700MB)
- `test_hardsub` +4 tests (Windows path 防禦 + cwd 驗證,CR 盲點收尾)
- requirements.txt 分層 + 修 `google-genai` 漏列 bug
- docker-compose.yml v1 + .env.example(restart: unless-stopped 解 P0 #1 部分)

### iter 10~14: 階段 2 B + 技術債
- ideate.py scaffold + design RFC (docs/ideate-design.md)
- ideate `scan_changed_files` + `load/save_proposals` (atomic write, 15 tests)
- 死碼 deps 真實移除 (anthropic / reportlab / pdfplumber)
- scriptor.py 555 → 434 行,prompt 抽到 prompts/scriptor_*.txt
- outliner.py 432 → 343 行,prompt 抽到 prompts/outliner_*.txt
- `core/prompts_loader.py`:load_prompt(lru_cache) + prompt_version(sha256)

---

## 你下次可能要接的工作(按優先序)

### 🟡 主菜 — ideate.py 後續 (階段 2 B 還沒完)

**iter 12**: `propose_from_file` 實作(~25 分)
- Gemini Vision call:首頁 + 目錄頁 → 提案
- JSON parse + 容錯(API 限流 / parse 失敗 / 空回應)
- 新 prompt 檔 `prompts/ideate_propose.txt`(用 prompts_loader,iter 13 已建好 infra)
- Mock tests 用 monkeypatch(不真打 Gemini)

**iter 13**: `dedupe_against_jobs`(~20 分)
- 比對 JobStore 既有 job source.path
- 比對 YoutubeUpload.video_id
- 比對前次 proposals.json 已 APPROVED/IGNORED

**iter 14**: server route + React UI(~45 分,可能要拆)
- `GET /proposals` / `POST /proposals/{id}/approve` / `PATCH /proposals/{id}`
- React `ProposalsList.tsx` 頁 + header nav
- approve 流程**不繞 require_review=True**(P0 #4 學術誠信)

### 🟢 階段 1 A Docker user feedback 後

等 user 本機 `docker compose up --build` 跑一次,看會踩到什麼:
- 字型問題(Linux 沒 msjh.ttc,我配的 Noto CJK 視覺對不對?)
- F5 GPU passthrough(user 有 RTX 4080,nvidia-docker 設定)
- volume mount permissions(Windows / Linux 差異)

### 🟢 階段 1 C 技能 user 對話實測

`pdf-to-video` SKILL.md 是純文字指引,可以給 user 試一輪看流程順不順。要不要包成自動 poll bash helper 等實測後決定。

### 📋 v4 階段 3 (重頭戲,要先 RFC)

- **D 持久化 worker**: 沒這個雲端化卡死,但 user 還沒選技術(RQ / Celery / SQLite + 自寫)。寫架構 RFC 才能動。
- **F 課程網站整合**: 10+ 天工程,需 IAE 課程網站工作流先 alignment。

### 加分 / 技術債(無壓力做)

- `pipeline.py` 拆檔(800+ 行,候選 render/compose/tts/photo_overlay 拆出來,中型重構)
- F5 中國腔治本(cfg_strength / 換 model / 自己 fine-tune)
- 工程圖 AI 輔助(Gemini → matplotlib / TikZ → 本地畫圖,材料力學影片價值跳一階)

---

## /advance loop 使用方式(這個 session 新加的)

```
/loop /advance          # 自我配速 (建議, 25 分一輪)
/loop 30m /advance      # 每 30 分一輪
```

詳見 `.claude/commands/advance.md`。每輪做 7 步(健康檢查 → 挑任務 → 執行 → 驗證 → commit → push → 更新追蹤檔)。STOP 條件明文化(架構決策 / 破壞性 / OAuth / schema / 紅且不顯而易見)。

下次接手前可以:

```bash
git pull
pytest tests/                # 198 passed
ls TODO.md ROADMAP.md docs/  # 確認追蹤檔同步
```

然後 `/loop /advance` 自動接續,或手動挑 TODO 🌟 下階段規劃裡的項目做。

---

## 環境設定(沒變)

```bash
OS:        Windows 11 + RTX 4080
Python:    3.10+ (主開發 3.12)
Node:      20+ (React build, Docker 也用)
FFmpeg:    在 PATH (libass 支援是必要, 燒字幕需要)
字型:       C:/Windows/Fonts/msjh.ttc + seguisym.ttf + consola.ttf
            (Docker image 內走 Noto CJK)
API key:    GEMINI_API_KEY (google-genai SDK, 之前漏列已修)
            client_secret*.json (YouTube OAuth)
F5 模型:    第一次跑會自動下載 1.35GB safetensors (commit 318f5e8 後不阻 event loop)
```

---

## 重要 lessons learned(2026-05-12 新累積)

1. **本機過 ≠ CI 過**:踩了兩次同一個雷
   - mutagen 沒裝(iter 4 前)
   - python-multipart 沒裝(iter 5)
   - 教訓:加新測試 / 新 import 時要回頭看 `.github/workflows/test.yml` install 集合

2. **atomic write 在 Windows 也得用 `os.replace`**:`save_proposals` 用這 pattern(commit f533995)
   - 寫 .tmp + os.replace, Windows Vista+ 也是 atomic
   - server 跑到一半被 kill 不會留半成品 JSON 擋下次 read

3. **prompt 抽到 .txt 檔之後 IDE diff 直觀**:scriptor / outliner 都改完(commit 1828ac5 + a08c15f)
   - prompt_version() sha256 給未來 A/B 測試 / 線上問題追溯
   - 維持 module level 常數名做 backward compat,既有 caller 不必動

4. **`/loop /advance` 自動化要明文 STOP 條件**:防發散
   - 連續 3 commit 同檔 / 同 module → 已發散
   - 動 schema / OAuth / .env / 架構決策 → 停下來等用戶
   - 單一任務 > 30 分 → 該拆

---

## 一些我犯過的錯,你避免一下

從上幾次 handoff 帶過來(仍然有效):

1. **branch 開很多會把 user 搞亂**:都直接 commit 到 main,user 比較開心
2. **`tts_config.json` 容易誤 commit**:現在 gitignored 了 ✅
3. **Windows path escape**:`subtitles=` filter 對 Windows 絕對路徑各種 escape 規則跨 OS 不一致。用 cwd + 相對檔名繞過(`pipeline._build_hardsub_cmd`)
4. **deck schema vs v1 exam schema 兩條並存**:轉換在 `core.deck.deck_to_exam_schema*` 三個 helper
5. **smoke test 後別忘清測試 job**:`store.delete('test_id')` 別讓垃圾 job 留在 jobs/

2026-05-12 新加的:

6. **改 CI / 新 import 之前先看 install 集合**(本機過 ≠ CI 過)
7. **atomic write 寫 .tmp + os.replace**(不要直接 write_text)
8. **prompt 改 .py 字串 → 改 .txt 檔**,記得 prompts_loader.load_prompt(name) + alias 維持 backward compat

---

## 給你的最終確認 checklist

接手後第一輪:

- [ ] `git pull` 確認最新 commit (寫稿時 `a08c15f`)
- [ ] `pytest tests/` → 198 passed
- [ ] 看 `TODO.md` 🌟 下階段規劃,確認當前 phase
- [ ] 看 `ROADMAP.md` v4 段落,看 階段 1 A / 階段 2 B 進度
- [ ] 跟 user 確認他/她想做什麼:
  - ideate.py 繼續推 (propose_from_file iter 12)
  - 還是 user 自己本機跑 Docker / skill 看反饋
  - 還是換大主題 (階段 3 D 寫 RFC)

祝你下個 session 順利。👍
