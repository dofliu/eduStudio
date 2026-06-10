# eduStudio — 交接筆記 (Handoff)

> 給接手的人 / 下一個 Claude Code session 用。最後更新：2026-06-07。
> 這份是「快速接手」摘要；完整逐項歷史見 `STATUS.yaml`。

## 這是什麼

eduStudio = 單一可自架的 **Python FastAPI server**，把老師的素材變成教學內容：
- **影片**：考卷/簡報/文件/repo/網址 → 旁白教學影片 + 字幕 + YouTube
- **視覺**：教學簡報 / 圖卡 / 海報（Gemini 生成 + PPTX 匯出）
- **在地化**：翻譯 / 配音 / 會議摘要 / 學習工具
- 核心理念：**每個 AI 產出都有人工審查關卡**（考卷解答強制審查）；**一門課＝一個工作空間**。

由三個前身專案整合而成（autoSolver = 本體 / infoCard / translateGemma），現在**完全獨立**，舊 repo 已擱置（保留供參考細項功能）。

## 位置與環境

- **本 repo（唯一工作目錄）**：clone 到任一本機目錄即可（下面指令一律以 repo 根目錄為基準，
  不依賴特定絕對路徑）。
- **GitHub**：`https://github.com/dofliu/eduStudio`（public，本地 main 與遠端同步）
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
npx vite build --base=/app/        # ⚠️ --base=/app/ 一定要帶，漏了 /app 整頁空白 404

# 測試
python -m pytest tests/ -q          # 2394 passed；CI 4 matrix + frontend-typecheck 全綠
```

## 介面

| 路徑 | 內容 |
|---|---|
| `/app` | **統一工作站**（影片/視覺/素材·Project/發布/製作狀態）— 唯一維護的前端 |
| `/api` `/localization` `/projects` `/jobs` | REST 後端 |
| `/docs` | OpenAPI |
| `/studio` `/ui` | 舊獨立前端（不再維護，可留可刪） |

## 架構速覽

```
eduStudio/
├── core/          後端核心
│   ├── (影片 pipeline: outliner/scriptor/slide_ingest/pipeline/runner…)
│   ├── infocards/ 視覺生成(簡報/圖卡/海報/漫畫已移除)、PPTX 匯出、視覺素材庫
│   ├── translation/ learning/ meeting/ video/ storage/   (translateGemma 移植)
│   └── project.py  Project(一課一工作空間)
├── server/        FastAPI routes (jobs/uploads/projects/infocards/settings/localization…)
├── frontend/      統一 /app 前端原始碼 (React 19 + Vite，自包含；app.jsx 是單一大 bundle)
├── web/           build 產物 (/app=eduapp、/studio、/ui)
├── tests/         2394 pytest
├── STATUS.yaml    完整逐項歷史
└── HANDOFF.md     本檔
```

## 重要 gotchas（踩過的雷）

1. **build 一定帶 `--base=/app/`**，否則 /app 空白 404。
2. **Gemini 2.5-flash 預設開 thinking** → 吃掉 max_output_tokens 致回空+慢 5x。逐頁/批次呼叫一律 `thinking_config=types.ThinkingConfig(thinking_budget=0)`（見 `slide_ingest.py`）。
3. **Gemini 3 模型 id 要 live 實測**（這 repo 有 preview id 非 GA 前科）。目前設定頁用：文字 `gemini-3.5-flash` / `gemini-3.1-flash-lite` / `gemini-3.1-pro-preview`；圖片 `gemini-3.1-flash-image` / `gemini-3-pro-image` / `gemini-2.5-flash-image`。劉老師口述的 `gemini-3.1-pro` / `gemini-3.1-pro-image` 實測 **404**（API 沒有），用 `client.models.list()` 查該 key 真正可用的。
4. **CI 裝套件是寫死清單**（`.github/workflows/test.yml`），不是 `requirements.txt`。新增「非 importorskip 直接 import」的依賴要手動加進去（已加 google-genai；缺 ffmpeg 的測試要優雅降級）。
5. **bash 工具在 Windows 是 cp950**，curl 傳含中文的 JSON 會亂碼 → 用 Python urllib/requests（UTF-8）打 API。
6. **改前端後**：build 即生效（server 直接 serve `web/eduapp`），硬重新整理 /app；**改後端後**：要重啟 uvicorn。

## 本 session（2026-06-07）做了什麼

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

## 還沒做 / 待加強（接手可挑）

1. **計費準確化**（優先級高）：目前只算視覺/在地化 Gemini 呼叫，**沒算影片 render pipeline**(最大宗)，且單價是估算。要把 pipeline 的 Gemini 呼叫接進 `core/usage` 計帳 + 對齊真實單價。
2. **影片旁白模型遷 3.x**：`slide_ingest.py` 的 `MODEL` 還是 `gemini-2.5-flash`(會被淘汰)，要先驗證 3.x 旁白品質再換（3.5-flash 實測接受 thinking_budget=0）。
3. **`gemini-3.1-pro-image`**：劉老師想用但 API 還沒開放，等開放再從 `gemini-3-pro-image` 換過去（`core/infocards/models.py`）。
4. **素材庫 lightbox**：點圖目前開新分頁(已修 data:→blob)，可做頁內彈大圖更順；簡報縮圖點擊只開第一頁圖，可做完整 deck 檢視。
5. **舊專案功能細項**：infoCard/translateGemma 可能有沒轉過來的細節，用到再回原 repo 撈。
6. **CI Node.js 20 actions** 之後升 v4 消棄用警告（不急）。

## 詳細記憶（選讀）

本 session 的逐步決策/事實記在 Claude Code 的 project memory（位於本機家目錄下的
`~/.claude/projects/<project-key>/memory/`，Windows 為 `%USERPROFILE%\.claude\...`），
含 edustudio-integration-state、gemini 模型/thinking 陷阱、build flag、env 等。
換機器 / 換 project key 時不會自動載入，要的話可手動參考。
