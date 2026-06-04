# TODO

短期可立刻做、小而具體的事項。大方向看 [ROADMAP.md](ROADMAP.md), 內容品質
看 [docs/CONTENT_QUALITY_ROADMAP.md](docs/CONTENT_QUALITY_ROADMAP.md).

規則:
- 完成的打勾, 定期把勾完的搬去 ROADMAP 或刪掉
- 新增項目加日期當引用 (方便追)
- 優先度標示: 🌟 下階段重點 / 🔴 高 / 🟡 中 / 🟢 低
- 完整 iter 歷史看 git log + [docs/CHANGELOG.md](docs/CHANGELOG.md) + STATUS.yaml

> Routine agent 看這個檔挑下一個任務. 看 [docs/ROUTINE_ADVANCE_PROMPT.md](docs/ROUTINE_ADVANCE_PROMPT.md) 流程.

---

## 🌟 等用戶介入 (routine 不該動)

> routine 不該自己決策的事 — 等劉老師實機反饋 / 給樣本 / 給 API key.

- [ ] **詞句 / 發音對照**: 等用戶列實測念錯的詞, 加進 `pronunciation.json`
- [ ] **narration_style preset 選定**: 用戶試 5 個 (academic / storyteller /
  wuxia / dialogue / comedy) 選喜歡, 預設可改
- [ ] **persona/jliu v2 樣本**: 等用戶聽完 v1 給「該怎麼講」樣本, 調 prompt
- [ ] **voice clone (ElevenLabs Instant)**: 等用戶決定是否啟用 — 要錄 1 分鐘
  乾淨人聲 + 月費 $5 起
- [ ] **GCP Voice Studio / Custom Voice**: 等 allowlist 個人帳號開放
- [ ] **C2 F5 pronunciation 樣本**: 已被 GCP TTS 主軌取代, 看用戶是否還要維護 F5

---

## 🏁 Routine closeout backlog — ✅ 完成 (iter 134-138, 2026-05-28)

> closeout 4 項 (runner.py 4 個 orchestrator 補測試) 全完成, 1580→1659 tests。
> 之後用戶 2026-05-28 給 Phase 2 新方向 (N 軸 → V 軸)。歷史細節見 git log +
> STATUS.yaml key_metrics。(原 `docs/ROUTINE_CLOSEOUT.md` 已於 2026-05-29 文件整理移除。)

---

## 🌟 Active backlog (routine 可自主推進)

> **2026-05-28 用戶指定新焦點**: 先做「內容品質 — narration 截斷治本」(N 軸),
> 做完接「動態視覺」(V 軸 = 既有 G/E 軸). **硬約束: offline-first** — routine
> 不自主呼叫 Gemini / GCP TTS 燒額度. 需打 Gemini 驗證的 (prompt 調整) 一律寫成
> proposal docs, STOP 等用戶 review 後手動跑. 細則見
> [docs/ROUTINE_ADVANCE_PROMPT.md](docs/ROUTINE_ADVANCE_PROMPT.md) Phase 2 段.

### 🎯 N 軸 — narration 截斷治本 (offline-first, 先做這個)

> **背景**: `core/narration_validator.py` (iter 79) 只「偵測+標記」過長 narration
> (治標), 刻意不自動截斷/retry. 「22%」是 2026-05-07 舊估計. 真實截斷發生在
> 字幕帶視覺層 — `build_srt` (core/srt.py) 已按標點切句但**單一 cue 無字數上限**,
> 過長句在 `_draw_subtitle_strip` (pptx_style.py) 會視覺溢出/被切. 治本走確定性
> 後處理 (離線可測), Gemini prompt 強化只寫 proposal 等用戶開額度.

按順序做 (一輪一項, 全部 offline / 不打 Gemini):

- [x] **N1 真實 baseline 測量** (Phase 2 iter 1, 2026-05-28): `tools/measure_narration_truncation.py`
  掃 `jobs/*/deck.json` (+ OUTPUT_DIR), 算 slide over-budget + per-cue 過長句統計
  + 多 threshold 分布, 輸出 [docs/narration-truncation-report.md](docs/narration-truncation-report.md).
  **真實數字: 19 deck / 2423 cue, over-cue ratio (>40 字) = 44.9%** (舊估「~22%」偏低一半),
  over-slide ratio 88%. +43 tests (1659→1702). 純離線, 復用 narration_validator + srt._SENTENCE_SPLIT.
- [x] **N2 可重現 eval fixture** (Phase 2 iter 2, 2026-05-28): 從既有 jobs 抽 4 個
  代表性 deck (lecture/quick/ultra_quick × storyteller/comedy, 含 _cover/_outro)
  做 length-preserving 匿名化 fixture 進 `tests/fixtures/narration/decks.json`
  (CJK→文 / ASCII→x / 數字→0, cue 切分與字數逐字不變 → 截斷率在 CI 無 Gemini
  逐字重現). 工具加 `make_record` 共用 helper + `load_fixture_records` +
  `--fixtures` CLI 模式. +17 tests (1702→1719). locked baseline: 4 deck / 39
  slide / 196 cue / over-cue 61 (budget 40) / over-slide 31.
- [x] **N3 確定性後處理 (治本核心)** (Phase 2 iter 3, 2026-05-29): `core/srt.py`
  加 `SUBTITLE_CUE_CHAR_BUDGET=40` + `_split_long_cue` (次級標點 ，、；：,;: greedy
  裝箱到 ≤ budget, 不硬斷詞) + `narration_to_cues` (切分單一真實來源), `build_srt`
  加 `max_cue_chars` kwarg. 量修前 vs 修後 (N2 fixture): over-cue **61 (31.1%) → 0
  (0.0%)**, max cue **105 → 40 字**, cue 196 → 265 (細). +14 tests (1719→1733).
  - [x] **N3-verify** (Phase 2 iter 4, 2026-05-29): `tools/measure_narration_truncation.py`
    的 `split_cues` 接上 `core.srt.narration_to_cues` (build_srt 同一條切分), 工具/CI
    直接量修後. DEFAULT_CUE_CHAR_BUDGET 改綁 SUBTITLE_CUE_CHAR_BUDGET; split_cues 加
    `max_cue_chars` kwarg (<=0 關閉切分 = 修前對照). N2 locked baseline 更新成修後:
    cue 196→265, over-cue **61 (31.1%) → 0 (0.0%)**, max-cue 105→40 (over-slide 31 /
    slide 39 不變). 報告從 N2 fixture 重生 (匿名化, CI 可重現): over-cue 0.0% (0/265).
    +3 tests (1733→1736). 改 3 檔 (tool + test + report).
- [x] **N4 Gemini prompt 強化提案 (GATE — 不自動跑)** (Phase 2 iter 5, 2026-05-29):
  寫 [docs/narration-prompt-tuning-proposal.md](docs/narration-prompt-tuning-proposal.md)
  — prompt diff 草稿 (兩個 scriptor prompt 加「句子層 ≤40 字 + 長句每 ~20 字逗號」cue
  層約束, 補 N3 切不動的「無次級標點長句」缺口 + 強化 over-slide 79.5% 的 slide 層) +
  A/B 驗證流程 (跑 Gemini 產 A/B deck → `--cue-budget 0` 量源頭 over-cue + over-slide).
  **STOP 等用戶 review + 手動開額度驗證**. 0 production code 改動 (純 doc). offline-first.
  - [x] **§5 配套 counter** (Phase 2 iter 6, 2026-05-29): `tools/measure_narration_truncation.py`
    加 `is_uncuttable_long_cue` + `uncuttable_long_count` (長度 > `SUBTITLE_CUE_CHAR_BUDGET`
    且 `_CLAUSE_SPLIT` 切不出 >1 段 = N3 切不動的殘留, 復用 core.srt 不漂移). 全域摘要 +
    分組表 + 報告各加一列. 配 `--cue-budget 0` 量 Gemini 源頭, 修後等於 over-cue 殘留.
    fixture locked 0 (4 deck 長句剛好都有逗號 = 缺口 A「運氣」實證). +12 tests (1736→1748).
    純離線, 改 3 檔 (tool + test + report). **N 軸全收尾, 下一輪接 V 軸 V1 (offline)**.

### 🎵 SONG 軸 — 歌曲 → AI 生圖 MV 影片 (第 4 條 track, 2026-06-03 用戶拍板正式做)

> **決議 (2026-06-03 互動 session)**: 新增第 4 個 `source_type = "song"` — 歌曲音檔
> (AI 產) + 純文字歌詞 (無 LRC) → forced alignment 對齊時間軸 → 逐段 AI 生圖 → MV
> 影片 → YouTube。forced alignment 走**方案 2 (Demucs 分人聲 + WhisperX word-level +
> 手動 review 微調層)**, 畫面走 **AI 生圖逐段配**。完整設計見
> [docs/SONG_MV_TRACK_RFC.md](docs/SONG_MV_TRACK_RFC.md)。
>
> **GATE**: ① 新 dep demucs + whisperx + torch(CUDA) — 方案 2 已授權, M0 先確認 4080
> 環境再實裝 ② Gemini image 額度 (跟 V2 同開關)。offline-first 不變: 對齊/生圖碰
> 額度的部分寫 proposal + STOP, 不自主燒額度。

- [ ] **M0 POC (spike)**: 裝 demucs + whisperx 確認 4080 CUDA 跑得動 + 手動歌詞/時間軸
  1 首歌走通到 mp4 (純色/單圖背景, 先不接生圖, 驗渲染 + 歌曲音軌 + 歌詞字幕)
  - dep 清單已備: `requirements-song.txt` (demucs + whisperx, 獨立檔不進主 requirements
    避免 CI 裝 torch; 含 CUDA wheel 安裝順序註解)。劉老師本機 install 後推 M0。
- [ ] **M1 對齊子系統**: Demucs + WhisperX 自動對齊出 song.json 時間軸 + review UI 微調層
- [ ] **M2 生圖子系統**: 逐段 Gemini 生圖 + 風格一致性 (統一 style suffix/seed) + ken burns
- [ ] **M3 整合**: 渲染串接 + 字幕燒錄 + require_review + YouTube 上傳 (含章節)
- 對齊策略 (WhisperX ASR→文字對齊 vs align() 強制對齊已知歌詞) 在 M0 spike 拍板

### ✨ 新功能 backlog (2026-06-03 用戶挑選進場)

> 互動 session 用戶從建議清單挑這 4 個進 backlog。多數可接既有結構, 不需 Gemini 額度
> 的先做 (offline-first)。

- [ ] **LaTeX 公式渲染** (🔴 高, 教學剛需): 材料力學公式進 slide。matplotlib mathtext
  或 MathJax→PNG 渲 LaTeX, 接 slide_renderer 既有圖片疊放路徑。**offline 可做**。
- [x] **YouTube 自動章節** (🔴 高, 近零成本高 CP) (2026-06-04): deck section 結構 → YT
  description 時間軸章節格式 (`0:00 章節名`)。實作在 `core/youtube.py` (Track B 真正組
  description 的地方, 非 publish.py CLI)。`auto_youtube_meta` 原只認 exam schema
  (problems/steps), deck schema (repo/document/url 的 sections/slides) 走 problems 必空 →
  description 全空無章節。加 `_is_deck_schema` type guard (硬規則 #9) + `_deck_youtube_meta`:
  artifact stem 對到 section.id → 單章影片章節=slides; 對不到 (final.mp4 整份) → 章節=各
  section (該章 slides 旁白估算秒數總和)。抽 `_estimate_narration_seconds` +
  `_build_chapter_lines` 共用 (exam 路徑改用後不變)。+15 tests (1814→1829)。改 2 檔。
- [ ] **雙語字幕** (🟡 中): 既有 SRT → 翻英/日雙語軌。翻譯需 Gemini/翻譯 API → GATE
  寫 proposal 等用戶開額度; SRT 雙語合併格式 + 渲染是 offline 可先做。
- [ ] **學生提問 → RAG → 解答影片** (🟢 探索, 戰略價值高工程重): 串 RAG 研究
  (Kiwi/Christian) + EdTech 論文 + 課程網站整合。先寫 RFC 拆子系統, 不急著動 code。

### 🎬 V 軸 — 動態視覺 (N 軸全完成後啟動)

> 接既有 G/E 軸 RFC (見下方階段 2「G. 動態視覺素材」+ CONTENT_QUALITY_ROADMAP
> E 軸). offline 可做的先做; 需 Gemini SVG 產生 (E2-2) / 新 dep cairosvg (E1-3)
> 的一律 STOP 寫 proposal 等用戶.

- [x] **V1 (offline)**: E1-5 / E2 既有 slice 補測試 + icon_picker / image_frames
  parser 強化 (不需 Gemini / 新 dep 的部分) — V1a~V1d 全完成 (Phase 2 iter 7~12)
  - [x] **V1a icon_overlay 尺寸/比例路徑補測試** (Phase 2 iter 7, 2026-05-29):
    既有 icon_overlay 測試 icon 全是 256×256 正方形, aspect-ratio 縮放
    (`target_h = icon_h * target_w/icon_w`) 與 size_ratio 上界 clamp (0.50) 從沒被
    驗過. +6 tests — 上界 clamp / 預設 0.10 / 非數值 size_ratio 靜默 skip + 不擋同
    list 其他 icon / 寬 icon (2:1) 高按比例縮 / 高 icon (1:2) 寬鎖 size_ratio. 純
    PIL pixel 驗, 0 production code 改動. 1748→1754. 改 1 檔 (tests/test_icon_overlay.py).
  - [x] **V1b icon_picker manifest 優先序 + image_frames require_file_exists 透傳補測試** (Phase 2 iter 8, 2026-05-29):
    icon_picker docstring 明定『結果順序 = manifest 出現順序』且 max_icons 截斷依此序,
    但既有測試用 set 沒鎖順序 / 截斷依 manifest 序; manifest 缺 icons key fallback 沒測.
    image_frames select_frame / terminal_frame 的 require_file_exists 透傳給 valid_frames
    從沒驗過. +7 tests (icon_picker 3 + image_frames 4). 純測試 0 production 改動.
    1754→1761. 改 2 檔.
  - [x] **V1c SlideRenderer icon 疊圖整合補測試** (Phase 2 iter 9, 2026-05-29):
    SlideRenderer (pipeline, iter 102) 是最早接 E2-5 compose_icons 的 renderer,
    但 iter 103 整合測試只補了 Blackboard + Pptx, SlideRenderer 自己兩 layout
    (full / split-left) 從沒被直接整合測. +5 tests (TestSlideRendererIntegration) —
    full/split-left 各疊 icon 渲染 / 無 overlay NoOp / bottom-right icon 用
    canvas_h=900 定位 (y=700 在 icon 內證非 1080) / split-left 字幕帶不被 icon 污染.
    純整合測試 0 production 改動. 1761→1766. 改 1 檔 (tests/test_icon_overlay.py).
  - [x] **V1d icon-suggestions / image-frames endpoint 序列化 + 過濾契約補測試** (Phase 2 iter 12, 2026-05-29):
    icon-suggestions endpoint 親手組的 payload dict (jobs.py:179-193) 的 `position` /
    `size_ratio` 兩欄沒被既有 happy path 鎖過 (只測 key/matched_keyword/domain/file_exists/icon),
    重構漏掉前端疊圖位置/大小就錯但測試不紅; max_icons ge=1 le=20 只測界外 (0/21→422)
    沒測界內 (1/20→200). image-frames endpoint 既有 query-param 測試是『全存在』或『全缺檔』
    兩極端, 沒測混合 (缺檔被 valid_frames 踢但存在的保留, terminal 取存在裡最大) /
    亂序輸入 terminal 仍取 display_ratio 最大 (非陣列末筆). +5 tests (icon 3 + frames 2).
    純 endpoint 序列化/過濾契約, 0 production 改動. 1766→1771. 改 2 檔
    (tests/test_icon_suggestions_endpoint.py + tests/test_image_frames_endpoint.py).
    **V1 (offline) 收尾.** 下一輪 = V2 (E2-2 Gemini SVG) / V3 (E1-3 cairosvg) GATE 需用戶開額度/新 dep STOP.
- [ ] **V2 (GATE)**: E2-2 Gemini 產 25 個 SVG icon — 需用戶開額度. proposal 已寫:
  [docs/dynamic-visual-v2-v3-proposal.md](docs/dynamic-visual-v2-v3-proposal.md).
  manifest 已定義 25 icon 但 0 SVG 檔在磁碟 → 補檔後 routine 可自主做驗收測試 (offline).
  - [x] **V2 執行包 (offline)** (2026-06-04): `tools/gen_icon_svgs.py` — 讀 manifest 25
    icon → 內建 VISUAL_DESC 視覺描述 + 統一風格規範 (viewBox 256 / #1e3a2e / #ffd96b /
    無文字 label) 組 per-icon prompt。**SVG 用文字模型 gemini-2.5-flash 產 (不吃 image
    額度)**。預設 dry-run (印 prompt 不打 API), `--execute` 才呼叫 Gemini + 落檔, 產完印
    人工 review checklist + 不自動 commit (硬規則)。+20 tests (完整性鎖 VISUAL_DESC==manifest
    / prompt 含風格+語意 / extract_svg / dry-run)。劉老師開額度後跑 `--execute` → review → 補
    25 SVG → routine 自動接 V2 驗收測試 (tests/test_icon_library_complete.py, proposal §驗收)。
- [ ] **V3 (GATE)**: E1-3 flow_diagram SVG + cairosvg 渲 frame — 新 pip dep + 行為
  refactor. 見上方同一份 proposal. 建議先做完 V2 再評估 (或退候選 C 純 Pillow 不加 dep).

### 🎙️ S 軸 — 語音 voices UI 修補 (offline, 劉老師 2026-05-29 授權 routine 自主)

> **背景**: 2026-05-29 互動 session 查 TTS 現況時發現 voices route 有真 bug —
> `server/routes/voices.py` 的 `_read_current_voice` / `_write_current_voice` 只認
> edge / f5 兩種 backend, 完全沒有 google 分支。後果: 若 `tts_config.json` 的
> `backend` 是 google, UI 會顯示**錯的** current voice (掉成 edge 第一個「小陳」),
> 且使用者在 UI 選任何聲音都會把 google 設定覆蓋掉 → 「Google 在 UI 上管不到、
> 還會騙人」。系統文件 (CLAUDE.md / GOOGLE_TTS_SETUP) 宣稱「預設 google」但 UI 接不住。
>
> **授權**: 劉老師明確授權 routine 自主修這組 (解除硬規則 #3「修 bug 先討論」gate)。
> 全 offline、純 code、低風險、有測試。一輪一項, 按順序做。
>
> **預先定好的設計約束 (routine 照做, 不用自己決策)**:
> - google voice id 格式 = `google:<voiceName>`, 例 `google:cmn-TW-Wavenet-A`
>   (跟 `f5:teacher` 的 prefix 風格一致)。
> - google voice 清單取 docs/GOOGLE_TTS_SETUP.md: cmn-TW-Wavenet-A (女, 預設) /
>   -B (男) / -C (男, 深沉)。
> - 不動 `tts_config.json` 內容本身 (gitignored, smoke test 會改); 只改 route 邏輯 + 測試。

- [x] **S1 voices route 認得 google backend (修顯示斷層)** (2026-05-30): `_read_current_voice`
  加 google 分支 (backend==google → 回 `google:` + cfg["google"]["voice"], 缺 voice 退
  預設 cmn-TW-Wavenet-A); `_write_current_voice` 加 google 分支 (id 以 `google:` 開頭 →
  backend=google + cfg.setdefault("google",{})["voice"] = prefix 後字串, 不動 f5/edge 區塊)。
  google: 走 prefix 命名空間驗證 (不要求在 VOICE_IDS, 因 GCP 合法 voice 名很多, 預設清單
  S2 才補)。+5 tests (TestGoogleBackend: read / read 缺 voice 退預設 / write 切 backend /
  write 保留 edge+f5 區塊 / round-trip)。1777→1782。改 2 檔 (voices.py + test_voices.py)。
- [x] **S2 VOICES 清單加 Google 選項** (2026-05-30): VOICES list 加 3 個 google entry
  (cmn-TW-Wavenet-A 女預設 / B 男中性 / C 男深沉), label 標「(Google 雲端 TTS, 需 GCP
  額度)」, VOICE_IDS 自動含。順帶收緊 `_write_current_voice`: S1 曾為 google: prefix 開
  命名空間放行 (清單未補時的過渡), S2 補進預設清單後改回一律走 VOICE_IDS 白名單 → 未知
  google id 也 400 (符合驗收)。read 仍如實顯示 cfg 裡清單外的 GCP voice (只是 UI 下拉限
  3 個預設)。+8 tests (list 3: 3 google / 進 VOICE_IDS / label 標額度; endpoint 5: GET
  含 3 google / POST 各 google 成功套用 / 未知 google 400)。1782→1790。改 3 檔
  (voices.py + test_voices.py + test_voices_route.py 的 six→nine)。
- [x] **S3 sample 試聽對無預錄 sample 的 voice 優雅降級** (2026-05-30): VoiceInfo schema
  加 `has_sample: bool`, list_voices 以 `(VOICE_SAMPLE_DIR / v["sample"]).exists()` 回填。
  google voice 無 voices/samples/*.mp3 → has_sample==False, 前端據此 disable 試聽鈕優雅
  降級 (sample endpoint 仍維持 404 行為不動)。+4 tests (TestHasSample: 空 dir 全 False /
  google 永遠 False (即使 edge+f5 鋪了) / edge+f5 鋪檔則 True / 逐 voice 獨立判斷) +
  shape test 加 has_sample 欄。1790→1794。改 2 檔 (voices.py + test_voices_route.py)。
  (前端 web/ disable 試聽鈕另開小項, 後端契約先就緒。)

> **S 軸 (S1→S3) 全完成 → 回 wind-down**。其餘大目標 (GitHub issue #12 P0 穩固化 / #13 V2-V3 /
> #14 發佈擴展) 多需架構決策 / Gemini 額度 / 用戶操作, routine 不自主碰, 等劉老師
> 互動 session 推或拆出新 offline 子任務。B1/B2 動態尺寸 (docs/B1_B2_DYNAMIC_DIMENSIONS_RFC.md)
> 卡在「等用戶選 Option A/B/C」架構決策, 選定後才好拆。

---

### 階段 1 — 短期 (1~2 週內)

**C. Claude Code skill 包裝 `pdf-to-video`** ✨ 進行中
- [ ] skill 自動 poll 流程實作 (現在是文字指引, 改 Bash 包成 helper)
- [ ] `video-to-youtube` skill: 已 review 的 JSON → publish
  - 動 OAuth → 需先跟用戶討論安全模型, STOP 條件
- [x] skill README 整合 (放 docs/skills.md, iter 96) — 範例 PDF 留下次

**A. Docker + docker-compose** ✨ 進行中
- [ ] user 本機 `docker compose up --build` 實測, 修可能踩到的問題
- [ ] F5 GPU passthrough 實測 (nvidia-docker, 需 user 有 GPU 環境)
- [ ] production reverse proxy (nginx + TLS) — 等真要上雲時做
- [ ] YouTube OAuth client_secret 安全 mount 模式 — STOP 條件

### 階段 2 — 中期 (2~3 週)

**E. 工程圖 AI 輔助** ✨ 進行中
- [ ] **iter 21**: 整合 pipeline.py step image 欄位 (取代或補圖)
- 設計細節見 [docs/engineering-diagram-design.md](docs/engineering-diagram-design.md)

**G. 動態視覺素材** ✨ RFC approved, routine 可推 (2026-05-22 用戶決議)
- 決議: E1 走候選 A (PNG frame 序列), E2 走候選 A (keyword grep),
  icon library 風能/自動控制/材力各 5 + generic 10 = 25 個扁平 SVG,
  SVG 全 Gemini 產
- 建議推進順序 (見 design memo 末段):
  - [x] **E2-1**: `assets/icon_library/` 目錄 + manifest.json 框架 (iter 98)
  - [ ] **E2-2**: Gemini 一次性產 25 個扁平 SVG icon, commit 進 repo
  - [x] **E2-3**: `core/icon_picker.py` keyword grep 模組 (iter 99)
  - [x] **E2-4**: schema 加 `slide.icon_overlay` (iter 100)
  - [x] **E2-5**: slide_renderer alpha_composite 疊 icon (iter 102 SlideRenderer 兩 layout; iter 103 擴 BlackboardRenderer + PptxStyleRenderer 4 路 layout — 三大 renderer 全覆蓋)
  - [x] **E2-7**: +8~12 tests (iter 102 +19 含 NoOp/SVG/Position/Size; iter 103 +8 含 BlackboardRendererIntegration / PptxStyleRendererIntegration)
  - [~] **E2-6**: review UI 自動建議 icon 勾選列 (iter 106 backend slice `suggest_for_deck`; iter 107 API endpoint `GET /jobs/{id}/icon-suggestions` 包 suggest_for_deck — 含 require_file_exists / max_icons query params 跟 IconMatch JSON 序列化. 前端 UI 待後續 iter)
  - [x] **E1-1**: schema 加 `slide.image_frames` (iter 101)
  - [~] **E1-2**: slide_renderer 偵測 frame list 走多 PNG 順序 (iter 104: parser + SlideRenderer 兩 layout 接 terminal frame fallback; 真 frame 序列拆 step + build_clip refactor 待 E1-3)
  - [ ] **E1-3**: Gemini flow_diagram SVG prompt + cairosvg 渲 frame (含 build_clip refactor 拆 step → 多 PNG 配 narration 時長均分)
  - [~] **E1-4**: review UI frame preview (iter 108 backend slice `summarize_for_deck`; iter 109 API endpoint `GET /jobs/{id}/image-frames` 包 summarize_for_deck — 含 require_file_exists query param 跟 terminal_path JSON 序列化. 前端 UI 待後續 iter)
  - [ ] **E1-5**: +5~10 tests
- 設計細節 + Gemini prompt 草稿見 [docs/dynamic-visual-assets-design.md](docs/dynamic-visual-assets-design.md)
- 對應 `CONTENT_QUALITY_ROADMAP.md` E 軸 (E1 + E2)
- 不可繞 require_review=True 硬規則 — 自動建議走 proposals 人工確認

### 階段 3 — 遠期 (等真要上雲再做)

**D. 持久化 job worker** (7~10 天, 要先列選型 RFC)
- [ ] 技術選型 RFC: RQ / Celery / SQLite + 自寫 trade-off
- [ ] schema migration 設計 (跟 P0 #3 一起做)
- [ ] worker process 拆出 server, IPC 機制
- [ ] server 重啟 resume 機制
- 對應 RFC: [docs/V4_WORKER_RFC.md](docs/V4_WORKER_RFC.md)

**F. 課程網站整合 / Moodle plugin** (10+ 天)
- 學生掃 QR code → 跳該題目影片
- 學期跑下來實際使用數據, 寫 EdTech 論文

---

## 🔴 P0 結構性弱點

> 對個人使用 OK, 對「交給 Kiwi / Christian / 雲端」不可接受。
> 動 D 之前要先想清楚 #1 + #3 怎麼解.

- [ ] **#1 無 job 持久化** — `asyncio.create_task` 即起即忘, server 重啟丟所有 job
- [ ] **#2 單一 process FastAPI sync I/O 仍是炸雷** — F5 已踩, 沒 enforcement
- [ ] **#3 schema migration 無框架** — Round 2 P0 #4 已踩 (naive↔aware datetime)
- [ ] **#4 無 review gate 強制機制** — `require_review=True` 靠 server flag 擋, 可繞

---

## 🟡 中優先

### 內容品質
- [→] **Gemini narration 截斷率** (2026-05-07) — 已升級為 🎯 N 軸 (見上方 Active
  backlog), routine 治本中. 此舊條目保留追溯.
- [ ] **Pronunciation map 缺漏收集** — 跑樣本影片自動收念錯詞

### F5 後續
- [ ] **F5 中國腔仍明顯** (已被 GCP TTS 取代主軌, 但若想留 voice clone 軌)
- [ ] **錄音腳本工具** `tools/record_ref_script.py`

### UI / UX
- [ ] **上傳審查頁 SRT 重生成預覽** (若 user 手動編了 narration 後)

### Track A 殘留 (可選)
- [ ] **Track A 完全退場** (Track B 已涵蓋全部工作流)

---

## 🟢 低優先

### 技術債
- [ ] **`pipeline.py` 拆檔** (800+ 行, 候選: render / tts / srt / photo overlay)
- [ ] **更多測試覆蓋**:
  - [ ] `test_runner_concurrent_section_render` (需 asyncio TestClient + 真 runner mock)

### 文件
- [ ] **demo 影片** — YouTube 頻道開專區介紹這個系統

### Round 2 殘留 (實戰罕見不修)
- [ ] `_render_split_left` bullets 截斷時機: 越界檢查在已畫完之後

---

## 已知問題 (不修)

- **F5-TTS 幻覺**: ref 12 秒 cutoff + ref_text 對齊是主因
- **Gemini 偶爾寫錯單位**: 硬規則是人工 review, 不是系統 bug
- **edge-tts 停用 `zh-TW-YunJheNeural`**: 台灣男聲無選項
- **Windows 終端 cp950 吃不下 emoji**: 已用 `core.runtime.setup_utf8_stdout` 解決

---

## 重要踩坑紀錄 (給 routine 看)

- **`tts_config.json` 在 server 啟動 / smoke test 後會被改**: 不要 commit
- **CI 4 組 matrix 必須全綠才算過**: ubuntu/win × py 3.10/3.12 + frontend-typecheck
- **`from X import Y` 跨 module sync 問題**: import 時 capture 不 follow 後續變化,
  改 module-level 常數要 patch 所有 import 過的地方 (iter 83/85 踩過)
- **dispatch 雙層**: 既有 `overlay_teacher_photo` (PIL) + `build_clip` (ffmpeg overlay)
  兩條都會畫頭像, 加 override 要兩處都接 (iter 92→94)
- **prompt placeholder 加新欄位**: 既有測試呼叫 `.format(...)` 全部要補新 kwarg
  (iter 92 踩過 test_length_mode / test_prompts_loader)
- **要改 schema 型別**: 看 docs/CODE_REVIEW.md Round 2 lessons-learned, 寫 migration
- **letterbox-fit 跟字幕帶**: visible_h = HEIGHT - SUBTITLE_BAND_HEIGHT, 不是整個 HEIGHT
