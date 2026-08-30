# claude.md — eduStudio 教學內容工作站

> 給 Claude / 協作者的 context。對外貢獻規則看 [CONTRIBUTING.md](CONTRIBUTING.md)、
> 推出主線看 [docs/PRODUCT_READINESS.md](docs/PRODUCT_READINESS.md)、版本路線看
> [ROADMAP.md](ROADMAP.md)。**不重複內容**,這份只講「這個 repo 是什麼、不可妥協的規則、
> 怎麼跟我協作」。

## 專案目的

**eduStudio** 是一套**單一、可自架的 Python FastAPI 伺服器**,幫老師(尤其理工/工程科)
把原始素材變成可發布的教學內容,而且**全程人工把關 AI 產出**。它把三個前身專案
(`autoSolver` / `infoCard` / `translateGemma`)整合成**一個 Web 介面(`/app`)+ 一個可
部署後端**。推出形態(2026-06-07 拍板):**公開開源自架**(放 GitHub 讓任何老師 clone
自架,不做多租戶 SaaS)。

可以想成「給在 YouTube 上課的老師用的 NotebookLM」——但伺服器是你自己的,東西沒按下核准
就不會出去。

## 四條 Track(整合後)

同一個後端、同一套 TTS / 字幕 / Project / 計費 / 人工審查通道,前端收斂到單一 `/app`:

```
            ┌─ 🎬 影片 (core/video, outliner/scriptor/slide_ingest/solve, render/)
            │     考題 PDF → 黑板逐題解答 / 簡報 PDF → 逐頁旁白 /
            │     文件·Repo·URL → AI 大綱 → 講解影片 + SRT + 一鍵 YouTube
            │
[ server/ ] │─ 🎨 視覺 (core/infocards)
 FastAPI    │     資訊圖卡 / 印刷級海報 / 兩階段大綱→簡報→PPTX 匯出 /
 + JobStore │     16 主題·受眾語氣引導 / 單頁(逐區)refine / 自動圖表
 + /app UI  │
 (React 19) │─ 🌐 在地化 (core/translation, core/translate, core/meeting, core/learning)
            │     外部影片翻譯/重配音 / 會議·演講錄音→摘要 /
            │     單字卡(SM-2) / 寫作批改
            │
            └─ 🎵 Song MV (core/song_build, song_images, song_render)
                  歌曲 mp3 → 歌詞時間軸 → AI 生圖 MV(M0 手動時間軸已通,
                  M1 自動對齊 Demucs+WhisperX 為 GATE)
```

- **第五條:教學漫畫(2026-08 新,內部 MVP)**:獨立 Comic Core(`core/comics.py` +
  `server/routes/comics.py` + `frontend/edustudio/comic-studio.jsx`),連載 Series Bible /
  證據鎖定生成 / 六道 QA gate / 版本化發布 + Internal Reader,與其他 track 共用
  Project/設定/provider/成本。見 docs/COMIC_PRODUCTION_SYSTEM.md。
- **前端收斂**:`/app` 是唯一正式介面(2026-08 改版:目標導向首頁 + 影片 · 簡報 · 圖卡 ·
  漫畫 四工作站 + 專案/發布/狀態)。`/ui`(原 autoSolver)、`/studio`(原 infoCard,
  client-side 直連 Gemini)**標 legacy 退場中**
  (頂部退場 banner 導向 `/app`;build 產物待 `/app` 對等人工驗收後移除)。
- **一門課＝一工作空間**:頂部選課,之後產的每支影片/每張圖卡自動歸到該課
  (來源 · 任務 · 成品),NotebookLM 式管理。

## 技術棧

- **Python 3.12** 後端主語言;**FastAPI + uvicorn + Pydantic v2**;`JobStore` 非同步 job +
  磁碟持久化 + per-job log。
- **React 19 + Vite + Tailwind CSS** 統一 `/app` 前端(源碼 `frontend/edustudio/`,
  `base` 寫死 `/app/`,build 產物在 `web/`)。
- **Google Gemini 3 系列**(設定頁可逐角色配,見「模型抽象」):
  - 文字:`gemini-3.5-flash`(主力)/ `gemini-3.1-flash-lite` / `gemini-3.1-pro-preview`
  - 生圖:`gemini-3.1-flash-image`(主力)/ `gemini-3-pro-image`(海報最高畫質)
  - ⚠️ 影片旁白/解題目前仍 `gemini-2.5-flash`(`slide_ingest.py` / `solve.py` / `config.py`),
    遷 3.x = **C-3 GATE**(需開額度 A/B 驗品質),見 PRODUCT_READINESS。
- **edge-tts / F5-TTS / Google TTS** 三條 TTS 線(F5 聲音複製,自動退回 edge/google)。
- **FFmpeg** 影片合成 · **PyMuPDF** PDF→PNG · **matplotlib** LaTeX 公式 · **python-pptx** PPTX 匯出 ·
  **faster-whisper** STT · **BeautifulSoup4** URL adapter · **Google YouTube Data API v3** 上傳。

## 模型抽象(M 軸)

模型 id 收斂到**單一真實來源**,未來換代(4.0/5.0…)零(或極小)改動:

- `core/models.py` — **角色登錄表**:6 個邏輯角色(`text.fast` / `text.pro` / `vision` /
  `image.fast` / `image.pro` / `tts`)→ `(provider, model_id)`。呼叫端只認角色,
  用 `resolve(role)` / `resolve_id(role)` 解析。解析優先序:設定頁逐角色 `model_roles`
  覆寫 → legacy 單值欄位 `text_model`/`image_model` → 內建 `DEFAULTS`。
- `core/providers.py` — **provider adapter 介面**:`gemini` 主力;**`OllamaProvider` 已
  production 接線**(2026-08-28 P1-1,文字角色可經設定頁 `model_roles` 巢狀寫法
  `{"provider": "ollama", "model": "..."}` 指向本機,選 Ollama 不呼叫 Gemini,live 驗證過)。
  再加新 provider(claude/f5…)只要實作協定 + `register_provider`,呼叫端零改動。
- 視覺/infocards 世界已全面換接 `resolve()`;影片/解析文字 pipeline 的硬編 id 換接綁 C-3 GATE。
- `tools/check_models.py` — 模型 id 自我健檢(比對哪些 id 在這把 key 下已不存在,防 preview id 404)。

## 硬規則(不可妥協)

1. **AI 產出的數值不能未經人工 review 就當最終答案。**(核心賣點,學術誠信底線)
   - 適用每個 step、公式、數字。`require_review=True`(`exam_pdf` 強制)的 job 停在
     `awaiting_review`,**必須人工 `/approve` 才能 render**。
   - **不可繞過 review gate**:`server/runner.py` 的 render 入口 assert(`require_review=True`
     且 `reviewed=False` → 拒絕渲染標 FAILED)+ 狀態機強制,**不得弱化**。
2. **offline-first**:會消耗 Gemini/GCP 額度、改安全模型、動大架構的事 = GATE,寫 proposal
   後 STOP,不自己跑真實 API。測試一律 mock Gemini/生圖/ffmpeg。
3. **字型路徑不寫死。** 用 `CLAUDE_FONT_PATH` / `CLAUDE_FALLBACK_FONT_PATH` /
   `CLAUDE_MONO_FONT_PATH`,Win/Mac/Linux 都跑得動。
4. **設定檔 / 路徑常數集中 `core/config.py`**,不在各模組各定義 `BASE_DIR`。
5. **動 `server` / `runner` / `schemas` / `core` 要跑 `pytest tests/`**(~2850 tests 護網)。
6. **Schema dispatch 用 type guard**(`isExamDraft` / `isDeckDraft` / `_deck_has_section_id`),
   不要硬寫 `if "problems" in deck`。
7. **改 schema 型別寫 migration**(見 docs/CODE_REVIEW.md Round 2 naive↔aware datetime 教訓)。
8. **別誤 commit 機密 / 本機檔**:`settings.json`、`.env`、`tts_config.json`、
   `client_secret*.json`、`youtube_token.json`(smoke/server test 會改 `tts_config.json`,踩過)。

## 安全與部署(自架預設)

- **驗證**:`server/auth.py` 單一共享 token(`EDUSTUDIO_API_TOKEN`)。沒設→全開 + 啟動大聲警告;
  設了→瀏覽器走 session cookie、CLI 走 `Bearer`。
- **CORS** 收緊(`EDUSTUDIO_ALLOWED_ORIGINS`)、**path-traversal** 三道防護(`server/path_safety.py`)、
  **上傳硬化**(副檔名/MIME 白名單)、**rate limit**(`server/ratelimit.py` token bucket)。
- **重啟不丟工作**:`JobStore.resume_interrupted()` 把中斷的 in-flight job 標 FAILED 提示重試;
  `awaiting_review` 合法暫停不動。
- **部署**:`Dockerfile` + `docker-compose.yml`(+ `docker-compose.prod.yml` override)+
  `deploy/nginx.conf.example` / `Caddyfile.example` 反向代理範本。見 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。
- 詳細處置看 [SECURITY.md](SECURITY.md)。

## JSON Schema

### exam schema(`solve.py`,考題逐題解答)

```json
{
  "exam_title": "材料力學 — 期中考",
  "problems": [
    { "id": "q1", "number": "第 1 題", "score": 20, "problem": "題目原文",
      "steps": [
        { "_section": "題目解讀 | 觀念切入 | 公式導入 | 代入計算 | 易錯提醒",
          "display": "黑板顯示 (≤40 字)", "narration": "口語 (60~180 字)" }
      ] }
  ]
}
```

### deck schema(repo / document / url)

```json
{
  "deck_title": "...",
  "source_type": "repo | document | url",
  "source_meta": { "path": "...", "primary_language": "python" },
  "sections": [
    { "id": "intro", "title": "...",
      "slides": [
        { "id": "intro_1", "title": "...", "bullets": ["..."],
          "code_snippet": null, "code_lang": null, "file_path": null,
          "narration": "(100~200 字)" }
      ] }
  ]
}
```

渲染前用 `core.deck.deck_to_exam_schema_pptx` 壓平成 exam schema 餵 pipeline。
視覺(infocards)有自己的 schema,見 `core/infocards/schemas.py`。

## 關於我

- **劉瑞弘 (Dof)** — 國立勤益科技大學 智慧自動化工程系 副教授
- 教學科目:材料力學、自動控制、風力發電系統、C/Python 程式設計
- DOF Lab: doflab.cc
- 開發環境:Windows 11 + RTX 4080,必要時 WSL

## 開發偏好 / 溝通風格

- **直接、精簡。** 不要客套開場/結尾、不要過度解釋。
- **技術討論用繁體中文**,程式碼註解也以繁中為主。
- **架構層面決策先列選項 + trade-off**,別直接動手做一版丟給我。
- **Bullet point 可以用,實用為主**,不要為湊格式寫廢話。
- 每次交付前,先簡述「改了什麼、為什麼、有哪些副作用」。
- 「快版」= 只給結果不解釋;「審查」= 只找問題不重寫。

## 我熟的 / 不熟的

**熟:** Python、Windows/Linux、MCP、RAG、SCADA、風力發電、工業通訊協定 (Modbus TCP/OPC UA)、IEC 61400、學術論文寫作

**不太熟但願意學:** 前端細節、複雜 CSS 動畫、React 生態(逐漸熟)、雲端部署 (AWS/GCP)

## 相關背景 Context

- 實驗室有兩位研究生會接觸到這個 repo:Kiwi (RAG domain)、Christian (RAG 架構)
- 工具未來可能整合進 IAE 系課程網站 / 我的 YouTube 頻道
- 影片輸出考慮檔案大小,單題目標 < 3 MB(1 分鐘左右)
- 簡報講解類影片每章 ~15 分鐘,長片要注意 TTS 累積誤差

## Git 同步規則

- 結束工作前 commit + push;切換環境(本地 ↔ 雲端)前確認 `git status` 乾淨。
- 主目錄開 branch,不用 worktree(主目錄 = 工作區,避免測試摩擦)。
- 一個 PR 做一件事,盡量 ≤3~5 個檔。
