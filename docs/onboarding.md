# 上手指南 — eduStudio 從 0 到 1

> 給**第一次自架 eduStudio 的老師**。照這份從零走一遍：
> **裝起來 → 配 API key → 產出第一支影片 → 上傳 YouTube**，全程約 30–60 分鐘
> （第一次下載相依、模型回應時間佔大半）。
>
> 想了解全貌看 [`README.md`](../README.md)、要部署上線看
> [`docs/DEPLOYMENT.md`](DEPLOYMENT.md)、想改 code 看 [`CONTRIBUTING.md`](../CONTRIBUTING.md)
> 與 [`claude.md`](../claude.md)（硬規則）。

> 📸 **截圖說明**：本文中標 `<!-- 截圖：… -->` 的位置預留給介面截圖，待補。
> 文字步驟本身已可獨立完成 0→1，截圖是輔助。

---

## 0. 你會得到什麼

走完這份，你會有一台**自己機器上的 eduStudio 伺服器**，可以：

- 丟一份**考卷 PDF** → 得到一支**黑板風格、有旁白的逐題解答影片**（含 SRT 字幕）；
- 在按下渲染前，**逐題人工審查 AI 的答案**（核心原則：沒查證過的 AI 數字不會出去）；
- 一鍵把成品**上傳到你的 YouTube 頻道**（含自動章節、字幕）。

> eduStudio 還能做簡報、資訊圖卡、海報、影片翻譯/配音、歌曲 MV 等（見 README）。
> 這份只帶你走**最短的一條主線**：考卷 → 影片 → YouTube。其餘走通這條後自然會用。

---

## 1. 系統需求

| 類別 | 需要 | 說明 |
|---|---|---|
| **作業系統** | Linux / macOS / Windows | 任一皆可（Docker 或本機 Python） |
| **Python** | 3.10+（建議 **3.12**） | 後端 | 
| **Node.js** | 20+ | 只在**手動建置前端**時需要；用 Docker 或現成產物可免 |
| **ffmpeg / ffprobe** | 必裝（**非 pip**） | 任何影片渲染、抽音訊都要。`apt install ffmpeg` · `brew install ffmpeg` · `choco install ffmpeg` |
| **Noto CJK 字型** | 中文渲染需要（**非 pip**） | 例：`apt install fonts-noto-cjk`。路徑可用 `CLAUDE_FONT_PATH` 等覆寫（見 §2） |
| **Gemini API key** | 必填 | 唯一必填的金鑰，從 <https://aistudio.google.com/apikey> 申請（免費額度即可起步） |
| **YouTube OAuth** | 只在要上傳時 | 第 5 節再設定，不影響前面流程 |

> 用 **Docker** 的話，ffmpeg 與 Noto CJK 字型都已內建在 `Dockerfile`，你只要有 Docker 即可，
> 可跳過上表多數系統相依。

---

## 2. 安裝

兩條路任選。**只想快點跑起來 → 走 A（Docker）**；想改 code / 開發 → 走 B（本機）。

### A. Docker（最少踩雷）

```bash
git clone <repo-url> eduStudio
cd eduStudio

cp .env.example .env          # 用編輯器打開，填入 GEMINI_API_KEY=...（其餘可先留空）

docker compose up -d --build  # 第一次會 build image（含 ffmpeg + 字型），耐心等
```

開瀏覽器 → **<http://127.0.0.1:8000/app/>**。看到工作站介面就成功了。

> 上線到內網/公網前**務必**先讀 [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) 的「上線前安全 checklist」
> （設 `EDUSTUDIO_API_TOKEN`、收斂 CORS、放反向代理 + TLS）。本機自用可先略過。

### B. 本機 Python（開發 / 想改 code）

```bash
git clone <repo-url> eduStudio
cd eduStudio

# 1) 後端相依（建議用 venv 隔離）
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt                     # 核心：裝這個就能跑 server + 主 pipeline
#   需要時再加：requirements-optional.txt（PPTX 匯出 / 語音轉文字 / F5-TTS）
#               requirements-song.txt（歌曲 MV 軸，較重）
#               requirements-dev.txt（跑 pytest）

# 2) 設定檔
cp .env.example .env                  # 填 GEMINI_API_KEY（也可改在 App 設定頁填，見 §3）

# 3) 前端（產出 /app 介面；base 已寫死成 /app/，直接 build 即可）
cd frontend && npm install && npm run build && cd ..

# 4) 啟動 server
python -m server.main --host 127.0.0.1 --port 8000
#   （等同 uvicorn server.main:app --host 127.0.0.1 --port 8000）
```

開瀏覽器 → **<http://127.0.0.1:8000/app/>**。

> **字型沒裝在預設路徑時**（中文變方框），用環境變數指過去，例如：
> ```bash
> export CLAUDE_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
> export CLAUDE_FALLBACK_FONT_PATH=/usr/share/fonts/opentype/noto/NotoSansSymbols-Regular.ttf
> export CLAUDE_MONO_FONT_PATH=/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf
> ```
> server 啟動時會印一輪**自檢**（ffmpeg / 字型 / key 在不在），缺東西會在 log 標紅 —— 先看那段。

<!-- 截圖：/app 首頁工作站（頂欄選課 + 影片/視覺/素材/發布頁籤） -->

---

## 3. 配 API key

eduStudio 唯一必填的金鑰是 **`GEMINI_API_KEY`**。兩種設法（擇一即可）：

1. **環境變數 / `.env`**（推薦自架）：在 `.env` 寫 `GEMINI_API_KEY=你的key`，重啟 server 生效。
2. **App 設定頁**：開 `/app` → 右上角設定（齒輪）→ 貼上 key 存檔。

> 設定頁還能逐角色挑模型（文字 / 圖片用哪個 Gemini 型號）、設月預算等。
> 預設值已對齊現行可用的 Gemini 3 系列，**第一次不用動**。

<!-- 截圖：設定抽屜（API key 欄位 + 逐角色模型下拉 + 月預算） -->

---

## 4. 產出第一支影片（圖形介面，建議首選）

以**考卷 PDF → 逐題解答影片**為例。準備一份題目 PDF（幾題即可，先別丟整本）。

1. **選課**：頂欄選一門課（或新建），之後產的東西都會歸到這門課。
2. **影片頁籤 → 新建**：來源類型選**考卷（exam）**，上傳你的 PDF。
   - 考卷類型會**強制人工審查**（學術誠信，硬規則，不可關）。
3. 按下開始 → 狀態走 `ingesting`（AI 看 PDF、OCR、解題）→ 停在 **`awaiting_review`（待審查）**。
   <!-- 截圖：任務卡顯示「待審查」狀態 + 「開始審查」按鈕 -->
4. **逐題審查**：點「開始審查」，逐段檢查 AI 的解題數字 / 公式 / 旁白文字，**就地修改**錯的地方。
   - 這一步是 eduStudio 的核心價值：**AI 算錯的不會默默流到影片裡**。
   <!-- 截圖：審查頁（逐段內容 + 信心標記 + 可編輯） -->
5. 確認無誤 → 按 **核准（Approve）**。狀態轉 `rendering`（合成影片、燒字幕、配旁白）。
6. 等渲染完 → 狀態 `done`。在任務卡 / 發布頁可**預覽、下載 MP4 + SRT**。
   <!-- 截圖：完成的影片任務卡（預覽 + 下載 + 發布按鈕） -->

> **第一次跑會比較慢**：若用 F5-TTS 語音複製，第一次會下載約 1.3GB 模型；Gemini 解題也要時間。
> 旁白預設可退回 edge-tts（不需下載），急著看結果可在進階選項把 TTS 設成 `edge`。

### 4a.（可選）用 CLI 觸發

排程 / 自動化情境可用 wrapper（server 要先啟動）：

```bash
python scripts/submit_job.py exam ./path/to/midterm.pdf       # 印出 job_id（考卷預設需審查）
python scripts/submit_job.py document ./path/to/lecture.pdf   # 講義文件
python scripts/submit_job.py url https://example.com/article  # 部落格/網頁
python scripts/submit_job.py repo ./path/to/code-repo         # 程式碼倉庫
```

審查與核准仍走 `/app`（考卷的 review gate **不能用 CLI 繞過**）。

---

## 5. 上傳 YouTube

第一次要做一次性的 **Google OAuth 設定**，之後就一鍵上傳。

### 5a. 一次性：拿 OAuth 憑證

1. 到 [Google Cloud Console](https://console.cloud.google.com/) 建一個專案。
2. 啟用 **YouTube Data API v3**。
3. 建 **OAuth client ID**（類型：桌面應用程式 / Desktop app），下載 JSON。
4. 把下載的檔案**原封不動**放到 eduStudio 專案根目錄（檔名通常是
   `client_secret_xxxx.apps.googleusercontent.com.json`，**不用改名**，系統會自動配對）。
   - 此檔已被 `.gitignore`，不會誤 commit；請妥善保管、勿放共享磁碟。

### 5b. 上傳

**圖形介面**：在 `/app` 發布頁，對已 `done` 的影片按「發布到 YouTube」。
第一次會跳瀏覽器走 OAuth 授權，授權後 token 存成 `youtube_token.json`（已 gitignore，會自動 refresh）。

<!-- 截圖：發布頁（YouTube 上傳 + 標題/說明/章節） -->

**或用 CLI**：

```bash
python publish.py --video output/<exam_stem>/q1.mp4 --title "期中考 第1題 解析"
```

> YouTube 配額：一次上傳約 1,600 units，每日上限 10,000（約 6 支/天），到頂隔天重置。

完成 — 你已經從一份 PDF 走到一支發布在 YouTube 上的解題影片 🎉

---

## 6. 常見錯誤排查

| 症狀 | 處理 |
|---|---|
| `/app` 整頁空白 / 404 | 前端沒 build 或 base 不對。`cd frontend && npm install && npm run build`（base 已寫死 `/app/`），或用 Docker（已內含產物） |
| server 啟動就掛 | 看 traceback，最常見是 `GEMINI_API_KEY` 沒設、google-genai 沒裝。啟動自檢 log 會標紅缺什麼 |
| 影片中文變方框 / FFmpeg 找不到字型 | 沒裝 Noto CJK 字型，或路徑不對。`apt install fonts-noto-cjk`，或設 `CLAUDE_FONT_PATH`（見 §2） |
| 渲染失敗：找不到 ffmpeg | ffmpeg/ffprobe 沒裝或不在 PATH。`apt/brew/choco install ffmpeg` |
| 第一支影片卡很久 | 正常：F5-TTS 首次下載 ~1.3GB 模型 + Gemini 解題需時。想快可在進階選項把 TTS 設 `edge` |
| `pip install` 卡在 PyMuPDF | Linux 可能要先 `apt install libmupdf-dev`；多數平台有預編 wheel |
| YouTube 上傳：找不到 `client_secret*.json` | OAuth JSON 沒放到專案根目錄（見 §5a），檔名不用改 |
| YouTube 上傳：`quotaExceeded` | 當日配額用盡（約 6 支/天），隔天重置 |
| server 重啟後 job 不見了 / 標 failed | 重啟會把「正在跑」的 job 標 failed 請重試（止血機制）；`awaiting_review` 的會保留。重新提交即可 |
| 暴露到內網/公網安全嗎？ | **預設零驗證**，只適合 localhost。對外請先讀 [`DEPLOYMENT.md`](DEPLOYMENT.md)：設 `EDUSTUDIO_API_TOKEN` + 反向代理 + TLS |

---

## 7. 下一步

- **做更多內容**：影片不只考卷 —— 講義 PDF、文件、Repo、網址都能變影片；視覺頁可做簡報 /
  資訊圖卡 / 海報；在地化頁可翻譯/配音外部影片。同樣的「產出 → 審查 → 發布」流程。
- **正式上線**：[`docs/DEPLOYMENT.md`](DEPLOYMENT.md)（production override + 反向代理 + TLS + 安全 checklist）。
- **想改 code / 貢獻**：[`CONTRIBUTING.md`](../CONTRIBUTING.md)（本機開發、跑測試、**不可妥協的硬規則**：
  review gate 不可繞 / offline-first / 字型不寫死 / 設定集中 / 別 commit 機密）。
- **回報問題 / 安全漏洞**：一般問題開 GitHub issue；安全漏洞走 [`SECURITY.md`](../SECURITY.md) 的私密管道。

歡迎自架，把 AI 把關權留在你手上 👋
