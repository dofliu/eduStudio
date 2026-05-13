# Session Handoff — 2026-05-14

> 給下個 Claude session 看的:現況、上次做了什麼、下次可以接手什麼。
> 讀這個之前可以先掃 `claude.md` 拿產品定位 + 硬規則,再看這份拿執行細節。

---

## 你接手時專案的狀態

**整體位置**:`v4 規劃` server-side **大致完成**。四大 feature track 都可運作:

```
v4 階段 1 A: Docker ✅ server-side
  - Dockerfile + docker-compose + .env.example 都備好
  - 等 user 本機跑一輪實測 (user 機器目前沒 Docker, 擱置)

v4 階段 1 C: Claude Code skill ✅ scaffold
  - .claude/skills/pdf-to-video/SKILL.md 完整指引
  - 等 user 在另一 session 試觸發看流程順不順

v4 階段 2 B: ideate.py 自動內容企劃 ✅ 完整可運作
  - core/ideate.py: scan + propose (Gemini Vision) + dedupe + save + run_ideate
  - server/routes/proposals.py: GET list / POST scan-folder / POST approve / PATCH ignore
  - React /ui/proposals: 卡片 list + 「掃資料夾」modal
  - scripts/run_ideate.py CLI 排程友善
  - **iter 25 重點**: 自動判斷 source_type — Gemini 看 PDF 前 2 頁分類
    避免 user 踩「整個資料夾標 exam_pdf 但實際混 article」的雷
  - iter 27: 砍 yaml + scheduler, 全 ad-hoc UI modal (user 反饋 UX 太繁瑣)

v4 階段 2 E: 工程圖 AI 輔助 ✅ 完整可運作 (iter 31)
  - core/diagram_gen.py:
    - DiagramKind 7 種 (free_body / bending_moment / shear / stress_strain /
      block_diagram / circuit / generic)
    - generate_diagram(spec) → propose (Gemini) → AST validate → subprocess render
    - AST allowlist: matplotlib/numpy/math/scipy + 擋 eval/exec/builtin/getattr +
      iter 29 加 dunder attribute (obj.__dict__ 之類繞道)
    - subprocess sandbox: timeout / Agg backend / 限 env
  - prompts/diagram_matplotlib.txt: 7 條嚴格規則 + 7 種 kind 範例

技術債清理:
  ✅ tts_config.json gitignored + example
  ✅ requirements.txt 分層 + 修 google-genai 漏列
  ✅ 死碼 deps 真實移除 (anthropic / pdfplumber / reportlab)
  ✅ scriptor + outliner prompts 抽到 prompts/*.txt (合計 -210 行)
  ✅ core/prompts_loader.py + sha256 prompt_version + iter 30 cache invalidation
  ✅ iter 5 stale 雜檔清理 (gemini_raw / test_svg / ui_*.png 等)

P0 結構性弱點 (review iter 22 抓的, 已修):
  ✅ #1 proposal id collision (秒級→納秒級, commit 5d9714b)
  ✅ #2 prompt {{ }} 雙花括號 (commit db1a732)
  ✅ #3 retry 路徑 (state=FAILED + 無 deck.json 走 schedule_job, commit 4fe1802)
  ✅ #4 AST dunder 繞道 (commit 403ffc4)
```

**測試覆蓋**: 309 tests / 13 modules / GitHub Actions 4 組 matrix 全綠
**最後 commit**: 5c4d899 (寫稿時, iter 31)
**整段 /loop /advance 跑了 32 個 iter, 全部 CI 綠**

---

## 上次 session (2026-05-12 ~ 14) 做了什麼

User 啟動 `/loop /advance` 自動化迭代, **32 個 iter 跨多 area 跑完**:

### iter 1~15: 基礎與第一輪同步
- tts_config gitignored, LogPanel pin-to-bottom, pdf-to-video skill scaffold
- test_upload (FastAPI TestClient 第一個整合測試)
- Dockerfile v1 + docker-compose
- test_hardsub 補完 CR Round 1 已知測試覆蓋盲點
- requirements 分層 + 修 google-genai 漏列 bug
- ideate scaffold + scan + save (atomic write)
- 死碼 deps 移除
- scriptor + outliner prompts 抽到 .txt
- SESSION_HANDOFF + STATUS 同步 (iter 15)

### iter 16~22: ideate 完整收尾
- iter 16: propose_from_file (Gemini Vision call)
- iter 17: dedupe_against_jobs (三層去重)
- iter 18: diagram_gen scaffold + design RFC
- iter 19: onboarding.md
- iter 20: AST allowlist + subprocess sandbox
- iter 21: ideate server route (GET / POST approve / PATCH ignore)
- iter 22: React UI ProposalsList page (空清單導引 + 卡片 + 操作)

### review + 真實踩雷修補 (iter 22-25)
- Explore agent 抓出 P0 id collision / 設計疑慮 4 條
- 6 個 stale 雜檔清理 (commit 5d9714b)
- 修 P0 proposal id collision (秒級 → 納秒級)
- iter 23: CLI scripts/run_ideate.py + run_ideate 整合函式
- iter 24: 修 approve retry 走錯階段 (ingest fail 時)
- iter 25: ideate 自動判斷 source_type (解 user 真實踩的雷)
- iter 25 hotfix: prompt {{ }} 雙花括號 bug 修

### UX 翻轉 + 加分 (iter 26-31)
- iter 26: ideate yaml + 自動排程 (被 user 反饋砍)
- iter 27: 改 ad-hoc UI modal (用戶批評「設定檔太麻煩」)
- iter 28: pptx 主題 + 3 (Frieren / Naruto / Journal, 從 pptx-jliu-style 移植)
- iter 29: AST dunder fix (review 第 4 條設計疑慮)
- iter 30: prompts_loader cache invalidation + PROMPTS_NO_CACHE env
- iter 31: 工程圖 AI 收尾 — generate_diagram + Gemini call + prompts 完整鏈

---

## 你下次可能要接的工作 (按優先序)

### 🟡 主菜 — 大段落

**A. ideate UI 進度 streaming** (1-2 iter)
- 現在 POST /scan-folder 同步等 10+ 分, modal 卡住
- 改 async: return task_id + GET /tasks/{id}/status poll + React 顯示進度
- 或 SSE (server-sent events) 更即時

**B. pipeline.py 拆檔** (3-5 iter, 中大型 refactor)
- 800+ 行單一檔, 候選拆成 render.py / compose.py / tts.py / srt.py / photo_overlay.py
- 影響大, 每個拆出來都要 import path 更新 + test 覆蓋
- 不適合一輪做完, 拆 iter 序列

**C. 階段 3 D 持久化 worker** (大工程, 要先 RFC)
- 沒這個雲端化卡死, 但 user 機器目前不用 Docker
- 候選: RQ / Celery / SQLite + 自寫
- 動架構決策, **STOP 條件 — 必須先跟 user 對齊技術選型**

### 🟢 小段落 / 加分

**D. F5 中國腔治本**
- 短期: cfg_strength 拉高試 (調 tts_config.f5)
- 中期: 換 model (XTTS / GPT-SoVITS 試)
- 長期: 自己 fine-tune 台灣腔 checkpoint
- 需實機 + 真樣本驗證, 不適合純自動 /loop

**E. Gemini narration 截斷率 22%**
- TODO 列的內容品質問題, 影響成品
- 候選: 換 Gemini 2.5 Pro / 加第 4 次 retry / 調 prompt
- 需實跑幾份考卷才能驗證

**F. Pronunciation map 缺漏**
- TODO 內容品質, 念錯字收集進 pronunciation.json
- 純資料補充, 需實聽錄音

**G. pdf-to-video skill 自動 poll helper**
- iter 3 scaffold 留的 TODO
- 把 SKILL.md 純文字指引升級成 bash / python helper
- 需 user 在另一 session 實測, /loop 自動驗證困難

### 📋 review 殘留 (低優先)

- `_normalize_path` 對 relative 處理已正確 (iter 22 review 看錯, 已驗證不必動)
- LogPanel auto-scroll 已修 (iter 2 完成)

---

## 重要 lessons learned (本輪累積)

1. **本機過 ≠ CI 過** — iter 1-5 踩了兩次 (mutagen / python-multipart 缺裝).
   加新 import 時要看 `.github/workflows/test.yml` install line, 對齊。

2. **atomic write 在 Windows 也得用 `os.replace`** — `save_proposals` 用這
   pattern (commit f533995). 寫 .tmp + rename, Vista+ 也 atomic。

3. **改 schema 型別前先想 migration** — naive↔aware datetime 已踩兩次,
   `AwareDatetime AfterValidator` 已修但要記得新欄位也要套。

4. **`prompts/` 內 prompt 檔走不走 `.format()` 規則不同** —
   `propose.txt` 走 format 所以 `{{ }}` 對, `detect_type.txt` 不走所以該用 `{ }`.
   下次加新 prompt 要明文標 (iter 25 踩了這個雷)。

5. **review agent 的 false alarm 要 verify 過再說** — iter 22 review 指
   `_normalize_path` relative 處理錯, 實際看 code 兩條 branch 都有 `.lower()`,
   是 agent 看錯。不該照單全收。

6. **user UX 反饋優先級高於文件設計** — iter 26 寫了 yaml + scheduler,
   user 一句「為何要設定檔這麼麻煩」 → iter 27 整段重寫 ad-hoc UI modal。
   不要過度設計, 用 user 真實工作流回推。

7. **`/loop /advance` 自動化 — 跨 area 避免發散** — 連續 3 commit 同檔
   /同 module 是發散信號. iter 序列要主動切換 area (config → React → server
   → tests → docs → ...)。

---

## /loop 使用方式 (這個 session 已成熟)

```
/loop /advance          # 自我配速 (建議, 25 分一輪)
/loop 30m /advance      # 每 30 分一輪 (cache 友善 — 但 30+ 也會 miss)
```

dynamic mode 內部 ScheduleWakeup 1500s (25 分), cache TTL 5 分必 miss 一次。
session 必須開著, 跨 session 自動跑要走 `/schedule` (cloud)。

接手時 user 若想繼續 `/loop /advance` 自動化 — 你接續做 TODO.md
🌟 下階段規劃 內的項目, 每輪 25 分內收尾一個 commit。

---

## 環境設定 (沒變, 從上次 handoff 帶過來)

```bash
OS:        Windows 11 + RTX 4080
Python:    3.10+ (主開發 3.12)
Node:      20+ (React build, Docker 也用)
FFmpeg:    在 PATH (libass 支援是必要, 燒字幕需要)
字型:       C:/Windows/Fonts/msjh.ttc + seguisym.ttf + consola.ttf
            (Docker image 內走 Noto CJK)
API key:    GEMINI_API_KEY (google-genai SDK)
            client_secret*.json (YouTube OAuth)
F5 模型:    第一次跑會自動下載 1.35GB safetensors
```

---

## 給你的最終確認 checklist

接手後第一輪:

- [ ] `git pull` 確認最新 commit (寫稿時 `5c4d899`)
- [ ] `pytest tests/` → 309 passed
- [ ] 看 `TODO.md` 🌟 下階段規劃, 確認當前 phase (注意 iter 25 後 ideate
      變動很多, TODO 內容應對齊現況)
- [ ] 看 `ROADMAP.md` v4 段落, 看 階段 1/2 進度
- [ ] 看 `core/ideate.py` + `server/routes/proposals.py` + `web/src/pages/ProposalsList.tsx` —
      ideate 整段是新人最容易踩 / 想理解的核心
- [ ] 跟 user 確認他/她想做什麼:
  - 階段 2 E diagram_gen 實機跑一張看效果?
  - ideate 加進度 streaming 改 UX?
  - 進階段 3 D 持久化 worker?
  - 換大主題 (F5 / pipeline 拆 / 內容品質)?

祝你下個 session 順利。👍
