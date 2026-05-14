# CHANGELOG — v4 階段累積進度

> 一頁掃完 v4 階段(2026-05-12 ~ 2026-05-15)做了什麼。對接手助理 / 自己日後查考很有用。
>
> 詳細 PR 級內容看 git log;詳細設計看 `docs/*.md`;當前 active 工作看 `TODO.md` 🌟 段落。

---

## Session 2 — 影片成品打磨(2026-05-14 ~ 2026-05-15, iter 39 ~ 48)

| iter | commit | 內容 |
|---|---|---|
| 39 | `73b07a1` | **修 test job leak** — 三層根因(routes `_store` 中介, `_persist` self.root, staticmethod → instance method);清 5 個 leak dir;從此 pytest 不再污染真實 jobs/ |
| 40 | `f5b8db4` | **Proposals 卡片主題下拉** — `POST /proposals/{id}/approve` 接 optional body, 核准前可選 pptx 主題, 不必先核准再到 review page 改 |
| 41 | `035cb52` | **個人 intro 串接** — `core/video_concat.py`(concat + audio normalize cache + SRT offset, 22 tests);runner hook 在每支主影片前接 8 秒 intro;UI checkbox 雙處 |
| 42 | `f4b22d9` | **開場白多樣化** — `core/intro_rewriter.py`(30 tests);exam/slides → 同學變體 8 個, document/repo/url → 大家好變體 8 個;stable md5 hash seed |
| 43 | `e527b1f` | **影片長度模式** — `core/length_mode.py`(12 tests);quick(8-15 min)/ lecture(60-180 min)兩 preset;4 份 prompts 加 placeholder;雙 UI 下拉 |
| 44 | `35a0307`<br>`fa32f64` | **DofLab 10 套主題 + intro 路徑重構**;v1 沉穩(editorial/podium/notebook/shinobi/elven)+ v2 衝擊(zine/arcade/risograph/supergraphic/brutalist);total 5 → **15 套主題**;intro mp4 從 `D:/Dropbox/` 移到 repo 內 `docs/intro_journal.mp4` |
| 45 | `537cb93` | **多章合 final.mp4** — 修「選 quick 出了 5 支獨立 mp4」設計 bug;render 完所有章節後 ffmpeg concat 成單支 `final.mp4` + `final.srt`;intro 改接到 `final.mp4` 不再每章重複;各章 mp4 保留供 section re-render |
| 46 | `7d43a9f` | **收緊 quick mode 預算** — sections 4-6→3-4 / slides 5-10→4-5 / chars 100-200→80-120;加 `total_narration_budget_chars` (quick=2500 / lecture=20000);4 份 prompts 加「取下限優先, 上限是極限」+「強制步驟先估總字數」 |
| 47 | `df32583` | **`final.mp4` UI prominence** — JobEditor emerald 區塊「🎬 完整影片」排頂, 各章列下方標「重 render 用」;JobCard preview button 優先 final;Library 多章 job 只列 final.mp4(各章不污染 YT 上傳列表)+ 6 個新 test |
| 48 | `034d6d7` | **deck 時長 estimator** — `estimate_deck_duration(deck, mode)` 純函式;runner 在 ingest 完跑一輪 log 估算結果, over-budget 用 `logger.warning ⚠`;8 個新 test |

**iter 46 修法效果實測** (用戶實機跑 Journal_Paper PDF):
| Job | prompt 版本 | sections | 字數 | 估時 | budget 使用率 |
|---|---|---|---|---|---|
| 7d93439a0793 (新) | iter 46 | 3 | 2374 | 11.9 min | **95%** ✓ |
| 9c8e3df46ba5 (舊) | iter 43 | 5 | 8594 | 43.0 min | 344% ⚠ |
| 764039d15546 (舊) | iter 43 | 5 | 6774 | 33.9 min | 271% ⚠ |

字數降到老 prompt 28%, 落在預算內. 渲染後 final.mp4 實際 11.0 分鐘 (vs estimator 預估 11.9, 誤差 8%).

**測試成長(session 2)**: 354 → **467 tests**(+113 tests),全綠;無 test job leak。

**用戶可見變化(React UI)**:
- 建 job / 核准 proposal 三個新選項:
  - pptx 主題下拉:5 既有 + 10 dof-* 分 5 組 optgroup(課程教學 / 期刊 / 漫畫 / DofLab v1 / DofLab v2)
  - 影片長度下拉:快速(8-15 min)/ 詳細授課(60-180 min)
  - 串個人 intro checkbox:勾起來在主影片前接 8 秒個人開場
- 開場白會自動依 source_type 換變體(同學好 / 大家好), 同題穩定跨題會變
- 多章 job 自動合成 `final.mp4`, UI emerald 區塊醒目標「🎬 完整影片」當主交付

**沒做(延後)**:
- **Idea 2 多 voice / 多語言** — 用戶要求放到後面(Edge TTS 替代 F5、英 / 日翻譯軌)

---

## v4 階段四大 feature track(全部 server-side 完成)

### 🟢 階段 1 A — Docker 部署

| iter | commit | 內容 |
|---|---|---|
| 6 | `d4b3b04` | `Dockerfile` v1 — multi-stage(Node 20 build → Python 3.12-slim + FFmpeg + Noto CJK),~700MB |
| 9 | `3fe99e3` | `docker-compose.yml` + `.env.example` — volumes / restart unless-stopped(解 P0 #1 部分)/ F5 GPU passthrough section 註解 |

**等 user 本機實測**(目前 user 機器沒 Docker 環境,擱置)。

### 🟢 階段 1 C — Claude Code skill

| iter | commit | 內容 |
|---|---|---|
| 3 | `0e6cddb` | `.claude/skills/pdf-to-video/SKILL.md` — 完整流程指引(server health → submit_job → review → render) |

**等 user 在另一 Claude session 試觸發**(目前還沒手動驗收 + 沒寫 self-poll helper)。

### 🟢 階段 2 B — ideate.py 自動內容企劃(完整可運作)

| iter | commit | 內容 |
|---|---|---|
| 10 | `f894b74` | scaffold + design RFC(`docs/ideate-design.md`)|
| 11 | `f533995` | `scan_changed_files` + `load/save_proposals`(atomic write) |
| 12 | `e474c40` | `propose_from_file`(Gemini Vision 看 PDF 前 5 頁提案) |
| 13 | `ee01c8a` | `dedupe_against_jobs`(三層去重: JobStore done / YouTube uploaded / 前次 approved/ignored) |
| 14 (前半) | `8285432` | server route `/proposals` — GET list / POST approve / PATCH ignore |
| 14 (後半) | `25c2044` | React UI `ProposalsList.tsx` 卡片頁 |
| 23 | `d55809f` | CLI `scripts/run_ideate.py` + `run_ideate` 整合函式 |
| 24 | `4fe1802` | 修 retry 走錯階段(`state=FAILED + 無 deck.json` 走 schedule_job) |
| 25 | `1ebd398` | **自動判斷 source_type** — Gemini Vision 看前 2 頁分類,解 user 真實踩雷 |
| 25 hotfix | `db1a732` | prompt `{{ }}` 雙花括號 bug 修(detect 沒走 `.format()` 不該 escape) |
| 27 | `4577675` | UX 翻轉:砍 yaml + 自動排程,全 ad-hoc UI modal(user 反饋 UX 太繁瑣) |
| 33 | `43e1ac3` | 進度 streaming server-side: `POST /scan-folder/async` + `GET /scan-status/{id}` + in-memory state |
| 34 | `a574627` | React UI modal 配對 — fire-and-forget + 3 秒 poll + 即時 metrics |

**user 已驗證 ideate 端到端跑通**(2026-05-13 用 `pdfs/test/` 混合內容測過,auto 正確分類 article vs 考題)。

### 🟢 階段 2 E — 工程圖 AI 輔助(完整可運作)

| iter | commit | 內容 |
|---|---|---|
| 18 | `17826a9` | scaffold + design RFC(`docs/engineering-diagram-design.md`)|
| 19 | `dd47798` | `_validate_code_ast` AST allowlist(matplotlib/numpy/math/scipy + 擋 eval/exec/open/getattr)+ `_render_matplotlib_diagram` subprocess sandbox |
| 29 | `403ffc4` | AST 補擋 dunder attribute(`obj.__dict__` / `cls.__class__` 繞道,review 抓的 P0) |
| 31 | `5c4d899` | `_propose_matplotlib_code`(Gemini text gen)+ `generate_diagram` 整合 + `prompts/diagram_matplotlib.txt` 規則 |

**等 user 給 spec 跑一張真實圖看效果**(自由體圖 / 彎矩圖 / 方塊圖等 7 種 kind 都支援)。

---

## P0 結構性弱點(review iter 22 抓的,全修)

| # | bug | 修法 commit |
|---|---|---|
| #1 | proposal id collision(秒級精度同秒撞 id) | `5d9714b` 改 `time.time_ns()` 納秒級 |
| #2 | prompt `{{ }}` 雙花括號(detect 沒走 `.format()`) | `db1a732` 改單花括號 + `_parse_detect_response` 補防呆 |
| #3 | retry 路徑(ingest fail 時走 render 找不到 deck.json) | `4fe1802` `state=FAILED + 無 deck.json` 走 schedule_job |
| #4 | AST allowlist 漏 dunder attribute 繞道 | `403ffc4` 加 dunder reject + 7 regression tests |

---

## 技術債清理

| iter | commit | 內容 |
|---|---|---|
| 1 | `008ae1e` | `tts_config.json` gitignored + `tts_config.example.json`(server 跑會改檔,踩過 2 次誤 commit) |
| 5 | `dfac939` | CI 紅修兩條 — Py 3.10 f-string 反斜線 + 缺 mutagen |
| 8 | `f8ad547` | `requirements.txt` 分層(core/llm/pdf/server/legacy)+ **修 google-genai 漏列** bug |
| 12 | `7b68209` | 死碼 deps 真實移除(anthropic / pdfplumber / reportlab) |
| 13 | `1828ac5` | `scriptor.py` prompt 抽到 `prompts/*.txt`(555 → 434 行,-22%) |
| 14 | `a08c15f` | `outliner.py` prompt 抽到 `prompts/*.txt`(432 → 343 行,-21%) |
| 28 | `894ae78` | `pptx-jliu-style` 5 主題色票移植(+Frieren / Naruto / Journal) |
| 30 | `439e540` | `prompts_loader` cache invalidation(`clear_prompt_cache()` + `PROMPTS_NO_CACHE` env) |
| 35 | `9f65707` | `pipeline.py` 拆出 `core/photo_overlay.py`(decouple from 全局狀態) |
| 37 | `99d48bc` | `pipeline.py` 拆出 `core/srt.py`(純函式 + 16 tests cover 中英切句 / 字數比例 / float 誤差) |

---

## 加分項目

| iter | commit | 內容 |
|---|---|---|
| 2 | `ffd1df6` | `LogPanel` 上滑不被打斷(pin-to-bottom pattern,CR P2 #10) |
| 19 | `699abcc` | `docs/onboarding.md`(給研究室助理 Kiwi / Christian 上手用)|
| 36 | `7235ca7` | `/health` 加強 8 條 setup diagnostics(gemini_key / fonts / proposals.json 等) |

---

## 測試覆蓋

| 起點 | 終點 | 變化 |
|---|---|---|
| 148 tests / 9 modules | **354 tests / 16 modules** | **+206 tests** |

新增 modules(對應 v4 新功能):
- `tests/test_upload.py`(7,iter 4)
- `tests/test_ideate.py`(57,iter 10-25)
- `tests/test_prompts_loader.py`(16,iter 13 + 30)
- `tests/test_ideate_runner.py`(11,iter 27 + 33)
- `tests/test_proposals_route.py`(17,iter 14 + 27 + 33)
- `tests/test_diagram_gen.py`(42,iter 18-31)
- `tests/test_visuals.py`(7,iter 9 暖身)
- `tests/test_photo_overlay.py`(8,iter 35)
- `tests/test_srt.py`(16,iter 37)
- `tests/test_health_endpoint.py`(6,iter 36)

`hardsub` 跟 `pptx_themes` 也擴充(各 +4 / +7 tests cover Windows path 跟 5 主題)。

---

## 還沒做(低優先 / 需 user 互動)

- **F5 中國腔治本** — 需實機跑樣本對比(cfg_strength / 換 model / fine-tune)
- **Gemini narration 截斷率 22%** — 需實跑驗證
- **Pronunciation map 缺漏** — 需實聽錄音收集念錯字
- **`pdf-to-video` skill 實測 + auto-poll helper** — 需 user 在另一 session 試
- **Docker compose up 實測** — 等 user 有 Docker 環境
- **diagram_gen 真實圖 demo** — 需 user 給工程圖 spec 跑一張
- **階段 3 D 持久化 worker** — 大工程,要先 RFC 對齊技術選型(RQ / Celery / SQLite 自寫)
- **pipeline.py 繼續拆檔**(剩 dynamic_avatar / hardsub wrapper 等可獨立)
- **ROADMAP 同步 v4 段落**(可能 stale,等下波)

---

## 開發體驗工具(本次 session 引入)

| 工具 | 用途 |
|---|---|
| `/loop /advance` | 自我配速自動推進(dynamic mode,25 分一輪) |
| `/advance` slash command | 單輪手動觸發 health check → 挑任務 → execute → commit → push → 同步追蹤檔 |
| 主動 stop loop | 任務做完 + 沒 backlog 時 AI 自主停(這個 session 還沒觸發過) |

37 個 iter 跑下來,**所有 commit 都 CI 綠燈**,沒回滾。
