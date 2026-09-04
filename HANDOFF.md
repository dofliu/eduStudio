# eduStudio — 交接筆記 (Handoff)

> 給接手的人 / 下一個 Claude Code session 用。最後更新：2026-09-04。
> 這份是「快速接手」摘要；完整逐項歷史見 `STATUS.yaml`、階段摘要見 `docs/CHANGELOG.md`。

## 這是什麼

eduStudio = 單一可自架的 **Python FastAPI server**，把老師的素材變成教學內容：
- **影片**：考卷/簡報/文件/repo/網址/HTML 動畫/相簿/歌曲 → 旁白教學影片 + 字幕 + YouTube
- **視覺**：教學簡報 / 圖卡 / 海報（Gemini 生成 + PPTX 匯出、缺圖簡報補圖）
- **在地化**：翻譯 / 配音 / 會議摘要 / 學習工具
- **漫畫（2026-08 新，內部 MVP）**：連載教學漫畫 — Series Bible / 證據鎖定生成 / 六道 QA gate /
  版本化發布 + 內部閱讀器（`docs/COMIC_PRODUCTION_SYSTEM.md`）
- 核心理念：**每個 AI 產出都有人工審查關卡**（考卷解答強制審查）；**一門課＝一個工作空間**。

由三個前身專案整合而成（autoSolver = 本體 / infoCard / translateGemma），現在**完全獨立**，舊 repo 已擱置（保留供參考細項功能）。

## 位置與環境

- **本 repo（唯一工作目錄）**：clone 到任一本機目錄即可（下面指令一律以 repo 根目錄為基準，
  不依賴特定絕對路徑）。
- **GitHub**：`https://github.com/dofliu/eduStudio`（public）。2026-09-04 現況：`main` 已含
  2026-08-30 工程收斂輪與 08-31 promo／skill（`ac07ab4`）；文件同步輪走 PR #101。
- **Python**：3.12（建議用 venv；若本機 pip resolver 有問題可改用 `uv pip install`）。
- **Gemini 金鑰**：讀環境變數 `GEMINI_API_KEY`；設定頁(settings.json)若填了會優先。settings.json 含金鑰，**已 gitignore**。
- **字型（CJK）**：跨平台走 `CLAUDE_FONT_PATH` 環境變數指向任一 CJK `.ttf/.ttc`（硬規則：字型路徑不寫死）。
  各平台常見預設：Windows `C:/Windows/Fonts/msjh.ttc`、Linux `…/NotoSansCJK-Regular.ttc`、
  macOS `/System/Library/Fonts/PingFang.ttc`。Docker 映像已內建 Noto CJK。

## 跑起來（三個關鍵指令）

```powershell
# 後端
pip install -r requirements.txt              # 或 uv pip install -r requirements.txt
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
#   → http://127.0.0.1:8000/app/   (統一介面)

# 前端（改了 frontend/edustudio/*.jsx|css 後要重 build）
cd frontend
npm install        # 第一次
npm run build                      # base 已寫死在 vite.config.ts（U-6），不必再帶 --base

# 測試
python -m pytest tests/ -q          # 2855 collected (2026-09-04 於 Linux 容器實跑：2842 passed /
                                    # 13 skipped(mcp + 缺 ffmpeg) / 1 deselected)；CI 全綠
                                    # （office_live 為 Windows 本機 release gate，CI 明確排除）
```

## 介面

| 路徑 | 內容 |
|---|---|
| `/app` | **統一工作站**（目標導向首頁 + 影片/簡報/圖卡/漫畫 四工作站 + 專案/發布/狀態）— 唯一維護的前端 |
| `/api` `/localization` `/projects` `/jobs` | REST 後端 |
| `/docs` | OpenAPI |
| `/studio` `/ui` | 已退場（U-5 2026-08-30）：一律 307 轉導 `/app/`；原 web/ 原始碼專案已移除（要考古走 git 歷史） |

## 架構速覽

```
eduStudio/
├── core/          後端核心
│   ├── (影片 pipeline: outliner/scriptor/slide_ingest/pipeline/runner…)
│   ├── infocards/ 視覺生成(簡報/圖卡/海報)、PPTX 匯出、視覺素材庫、comic_service
│   ├── comics.py  Comic Core(連載/版本/證據/QA/發布,file-first)
│   ├── translation/ learning/ meeting/ video/ storage/   (translateGemma 移植)
│   ├── providers.py + ollama_client.py  provider 抽象(Gemini 主力;文字角色可指本機 Ollama)
│   └── project.py  Project(一課一工作空間)
├── server/        FastAPI routes (jobs/uploads/projects/infocards/comics/settings/localization…)
├── frontend/      統一 /app 前端原始碼 (React 19 + Vite；app.jsx + comic-studio.jsx)
├── web/           build 產物 (僅 /app=eduapp;legacy /ui /studio 已退場)
├── tests/         2855 pytest（office_live 1 個是 Windows 本機 gate）
├── STATUS.yaml    完整逐項歷史
└── HANDOFF.md     本檔
```

## 重要 gotchas（踩過的雷）

1. ~~build 一定帶 `--base=/app/`~~ → U-6 起 `base: '/app/'` 已寫死進 `frontend/vite.config.ts`，
   `npm run build` 即可（歷史雷：漏了 base 會整頁空白 404）。
2. **Gemini 2.5-flash 預設開 thinking** → 吃掉 max_output_tokens 致回空+慢 5x。逐頁/批次呼叫一律 `thinking_config=types.ThinkingConfig(thinking_budget=0)`（見 `slide_ingest.py`）。
3. **Gemini 3 模型 id 要 live 實測**（這 repo 有 preview id 非 GA 前科）。目前設定頁用：文字 `gemini-3.7-flash`（2026-08-30 遷主力 · **尚待 live 實測**，404 就退 `gemini-3.6-flash`）/ `gemini-3.6-flash` / `gemini-3.5-flash` / `gemini-3.1-flash-lite` / `gemini-3.1-pro-preview`；圖片三階 `gemini-3.1-flash-lite-image`（Nano Banana 2 Lite · 2026-07 新入門階 PR #98 · **尚待 live 實測**）/ `gemini-3.1-flash-image` / `gemini-3-pro-image`。劉老師口述的 `gemini-3.1-pro` / `gemini-3.1-pro-image` 實測 **404**（API 沒有），用 `client.models.list()` 查該 key 真正可用的。圖片模型 id 的單一目錄在 `core/infocards/models.py`，`core.models` 的 image 角色引用它（改一處即同步）。
4. **CI 裝套件是寫死清單**（`.github/workflows/test.yml`），不是 `requirements.txt`。新增「非 importorskip 直接 import」的依賴要手動加進去（已加 google-genai；缺 ffmpeg 的測試要優雅降級）。
5. **bash 工具在 Windows 是 cp950**，curl 傳含中文的 JSON 會亂碼 → 用 Python urllib/requests（UTF-8）打 API。
6. **改前端後**：build 即生效（server 直接 serve `web/eduapp`），硬重新整理 /app；**改後端後**：要重啟 uvicorn。

## 最近狀態（2026-09-04 快照）

- **分支**：`main` 已推進到 **`ac07ab4`**（2026-08-31），含 2026-08-30 工程收斂輪、`/ui` 退場、
  Dockerfile 改建 frontend/、promo 影片與 `repo-intro-video` skill。2026-09-04 的文件同步輪
  在 `claude/project-status-sync-9z5v6p` 上走 PR #101（純文件，1 個 commit）。
  （更早的歷史：feature branch 均已合併刪除，PR 到 #100。）
- **2026-08-20 ~ 08-26**：`/app` 改版**目標導向首頁** + 新增**漫畫工作站**(內部 MVP,獨立
  Comic Core)；視覺模式 UI alias 收斂、視覺審查修復。
- **2026-08-27 ~ 08-28**：P0 live E2E 稽核 → **P1/P2 驗證完成**（Ollama provider 接線 live 通、
  PPTX round-trip、`/api/generate` validation、Actions Node 24、Whisper `large-v3` 三流程、
  token 部署驗證、四站 click-through）→ **P3 技術債收斂**（FastAPI lifespan、asyncio loop
  scope、office gate CI 邊界、Whisper cache 可攜 `HF_HOME`）。backend `2845 passed`。
- ~~唯一 BLOCKER：Google Photos OAuth consent~~ ✅ 2026-08-30 劉老師完成授權
  （token 存 `photos_token.json`），相片簡報軸 live 全通。
- **2026-08-30 工程收斂輪**：Sprint 1 三小修 / 統一 Gemini client（`core/gemini_client`）/
  共用 ffmpeg runner（`core/ffmpeg`）/ 文字主力遷 `gemini-3.7-flash`（⚠️ 待 live 實測）/
  計費分 model + 補漏帳 / **U-5 legacy `/ui` 退場**（Dockerfile 改建 frontend/）/
  漫畫正式化啟動（checklist 見 `docs/COMIC_PRODUCTION_SYSTEM.md`）。
  全套 `2854 passed`。詳見 `docs/CHANGELOG.md` 頂部兩段。
- 驗收證據：`docs/P1_P2_COMPLETION_PLAN_2026-08-28.md`、`docs/P3_COMPLETION_PLAN_2026-08-28.md`、
  `reports/eduStudio_P1_P2_Function_Verification_Report_2026-08-28_v1.0.docx`。
- **2026-08-31**：官方介紹影片收尾（配樂安靜版 v2 → 音樂主導 -16 LUFS → 交叉淡接循環 +
  `--loudness` 檔位）+ 新 skill **`repo-intro-video`**（把任意 repo 做成介紹影片，長度/音樂
  可指定）。見 `docs/promo/README.md`、`.claude/skills/repo-intro-video/`。
- **2026-09-04**：純文件同步輪（零 code 變更）— 對照程式碼查核各文件說法，修掉漂移
  （U-5 撞號 → U-7、M-2 剩餘項描述、routine 快照、skills 索引）。實跑驗證：
  backend `2842 passed / 13 skipped / 1 deselected`（此容器沒 ffmpeg 故 skip 較多）、
  frontend `npm test` 7 綠 + `vite build` 產物正確指向 `/app/assets/...`。
- **2026-09-04（同日第二輪）**：2026-07 審查的 offline 殘項收尾 —— T2-1 SSRF 位址過濾
  （新 `core/net_safety.py`，url 來源擋內網/metadata + 轉址每跳重驗）、T1-3 背景 job
  並行上限 + task 強參照（新 `server/background.py`）、T1-4 `state.json` 原子寫、
  T1-5 dubber 中間檔清理。測試 +74，全套 `2916 passed`。
  新增兩個環境變數：`EDUSTUDIO_MAX_CONCURRENT_JOBS`（預設 2）、
  `EDUSTUDIO_ALLOW_PRIVATE_URLS`（預設關）。
- 下一步候選清單見 `TODO.md` 🌟 段（2026-09-04 盤點）。

## 更早的 session（2026-06-07）做了什麼

整合 + 一大批 /app UI 補完 + 修復，重點：
- **整合**：資料夾 autoSolverVideo→eduStudio、GitHub repo 改名、前端原始碼搬進 `frontend/` 自包含、README/metadata、CI 修綠。
- **slides_pdf ingest 卡死修復**（thinking_budget=0 + 逐頁 logging + timeout）。
- **視覺站**：移除漫畫、圖卡/海報合併、生成依據(標題/內容/自動)、簡報恢復全 16 主題 + 受眾/語氣面板。
- **影片站**：來源九宮格 6→9(併影音工具)、下方只留進行中。
- **製作狀態**：統一任務管理(詳情/審查/發布/刪除)。**發布頁**：專心挑成品+語言。
- **Project**：接成「一課一工作空間」(頂部選課→生成自動歸屬→工作空間檢視)。
- **素材庫**：成功生成自動保存 + 縮圖牆。
- **模型**：更新為 Gemini 3 系列。
- **個人品牌**：帶進簡報母片頁尾 + 圖卡/海報底部(overlay)。
- **端到端 smoke 驗收通過**（真 Gemini 生海報+簡報、品牌頁尾、素材庫、Project 歸屬、PPTX 匯出全 OK）。

## 還沒做 / 待加強（接手可挑,完整清單見 TODO.md 🌟 段）

1. **`gemini-3.7-flash` live 確認**（🔴 目前唯一的全域單點）：本機跑
   `python tools/check_models.py`，404 就把設定頁 text 模型退 `gemini-3.6-flash`
   （目錄 `flash_36`）。旁白／大綱／翻譯／解題／視覺**現在全吃這個 id**，壞就一起壞。
2. **漫畫正式化 GATE**：真實生成 QA 一輪（開額度）+ 匯出實機檢查 + 手冊案例，
   checklist 見 `docs/COMIC_PRODUCTION_SYSTEM.md`。
3. **計費尾巴**：多模態「圖片輸入」token 未計；各 model 費率為估算，官方價出來後在
   `core/infocards/models.py` MODEL_PRICING 校正。
4. **2026-07 程式碼審查殘項**（2026-09-04 又收一批：T2-1 SSRF、T1-3 並行上限 + task 強參照、
   T1-4 state.json 原子寫、T1-5 dubber 暫存清理）：**剩** T2-4 schema 輸入界限、
   T0-3 review_assist 覆蓋率提示、T3-1 core 依賴反轉、T3-4 刪 app.py、T3-5 拆 god 檔、
   T3-6 測試鏡射（`TODO.md` 🔍 段，全部 offline 不需額度）。
5. **M-2 尾巴（GATE，待拍板）**：`scriptor`（考卷旁白）/ `outliner`（大綱）/ `translate`（翻譯）
   走 legacy `core/config.get_gemini_model()`，**吃不到設定頁逐角色 `model_roles`**（視覺站與
   `solve` 吃得到）。模型值已隨 `GEMINI_MODEL` 對齊 3.7、無 2.5 殘留 —— 剩的是「兩套解析路徑」
   不一致，改設定頁把 `text.fast` 指到本機 Ollama 時這三條不會跟著改。
6. **素材庫 lightbox**：點圖目前開新分頁(已修 data:→blob)，可做頁內彈大圖更順；簡報縮圖點擊只開第一頁圖，可做完整 deck 檢視。
7. **舊專案功能細項**：infoCard/translateGemma 可能有沒轉過來的細節，用到再回原 repo 撈。
8. **README/手冊 4 張截圖**（`docs/screenshots/`，需實機瀏覽器）。

## 詳細記憶（選讀）

本 session 的逐步決策/事實記在 Claude Code 的 project memory（位於本機家目錄下的
`~/.claude/projects/<project-key>/memory/`，Windows 為 `%USERPROFILE%\.claude\...`），
含 edustudio-integration-state、gemini 模型/thinking 陷阱、build flag、env 等。
換機器 / 換 project key 時不會自動載入，要的話可手動參考。
