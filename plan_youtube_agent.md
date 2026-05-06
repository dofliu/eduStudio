# plan_youtube_agent.md — YouTube 自動發布代理人規劃

> 本文件根據 2026-05 與 Claude (Cowork) 的規劃討論整理而成。
> 目的：讓 Claude Code session 可銜接繼續開發。
> 文件本身是規劃，不是 spec；實作前請與 Dof 確認細節。

---

## 背景與動機

目前系統（v1.x）已可從考卷 PDF 自動產生 MP4 + SRT，但上傳 YouTube 仍是手動。
升級目標：**系統主動規劃影片內容 → 自動渲染 → 人工確認後一鍵上傳**。

核心原則（不可妥協）：
- AI 產出的影片內容仍需人工審閱，但**審閱時機改為「上傳前」而非「逐步驟」**。
- 不做留言自動回覆，Dof 本人審閱後自行回覆。

---

## 整體架構（修訂版）

```
watched_folders (在 app.py UI 設定)
    │  PDF / 簡報 / 講義
    ▼
ideate.py
    │  掃描檔案 → Claude/Gemini 分析 → 產生影片企劃
    ▼
proposals.json
    │  (app.py 顯示企劃清單，Dof 選擇要製作哪幾個)
    ▼
現有 pipeline / batch (不動)
    │  自動渲染 MP4 + SRT
    ▼
app.py「上傳審查頁」(唯一人工關卡)
    │  播放影片 + 確認/編輯 metadata + 按「上傳」或「跳過」
    ▼
publish.py
    │  YouTube Data API v3 上傳 (預設 unlisted)
    ▼
YouTube 頻道
```

---

## 新增/修改檔案一覽

| 檔案 | 性質 | 說明 |
|---|---|---|
| `ideate.py` | 新增 | 掃描 watched folders → 產生企劃 proposals.json |
| `publish.py` | 新增 | YouTube OAuth 2.0 + 上傳 MP4/SRT |
| `app.py` | 修改 | 新增三頁：watched folders 設定、企劃瀏覽、上傳審查 |
| `config.yaml` | 新增 | 存放 watched_folders 路徑、YouTube 頻道 ID 等設定 |
| `schedule_runner.py` | 新增 (v2.2) | Windows Task Scheduler 整合，定期觸發 ideate + 渲染 |

`pipeline.py` / `batch.py` / `solve.py` **不動**。

---

## v2.0 — YouTube 上傳通道 ✅ 完成 (2026-05)

**目標:先把上傳功能打通,不加任何 AI 自動化。**

實作摘要(commit a6aa08f + 796955b):
- `publish.py` CLI:OAuth flow、resumable upload、SRT 自動偵測、`--out-json`
- Library 影片旁 📺 按鈕 → `/upload_review/<stem>/<pid>` 審查頁
- 審查頁 video player + 預填 metadata + 隱私 radio
- 上傳完寫回 `exam.json` 的 `youtube` 欄位
- Library badge 顯示已上傳狀態 + YouTube 連結

> 以下原規劃內容保留作參考。


### publish.py

功能：
- Google OAuth 2.0 授權流程（首次執行會跳瀏覽器，token 存 `youtube_token.json`）
- 上傳指定 MP4，同時附帶 SRT 字幕（使用 captions API）
- 上傳完成後回傳 video URL

介面（CLI）：
```
python publish.py --video videos/exam1/q1.mp4 \
                  --title "材料力學期中考 第1題解析" \
                  --description "..." \
                  --tags "材料力學,考題解析" \
                  --privacy unlisted
```

注意事項：
- YouTube Data API 每日 quota 10,000 units；一次上傳約 1,600 units，一天最多可上傳約 6 支（不含其他 API 呼叫）
- OAuth client secret 存 `client_secrets.json`（不進 git，加入 .gitignore）
- `youtube_token.json` 同上
- SRT 上傳用 `captions.insert`（language: `zh-TW`）

### app.py 新增：上傳審查頁

路由：`/upload_review/<exam_stem>/<q_id>`

頁面內容：
1. HTML5 `<video>` 播放器播放已渲染的 MP4
2. 可編輯欄位：
   - 標題（系統預填：`{exam_title} {題號}解析`）
   - 說明欄（系統預填，含各步驟章節時間軸）
   - 標籤（逗號分隔）
   - 隱私設定（unlisted / public）
3. 按鈕：「上傳到 YouTube」/ 「跳過」
4. 上傳後顯示 YouTube 連結

路由：`/library`（現有）擴充欄位，顯示每支影片的 YouTube 上傳狀態（未上傳 / unlisted / public + 連結）

### 狀態追蹤

在 exam JSON 裡每題新增欄位：
```json
{
  "youtube": {
    "video_id": "xxxxx",
    "url": "https://youtu.be/xxxxx",
    "privacy": "unlisted",
    "uploaded_at": "2026-05-10T14:30:00"
  }
}
```

---

## v2.1 — 自動內容企劃（ideate.py）

**目標：系統主動從教材資料夾分析，提出本週要做哪些影片。**

### Watched Folders 設定（in app.py UI）

路由：`/settings`（新增，或整合進現有設定頁）

設定項目：
- watched_folders：可新增多個資料夾路徑（用 `+` 按鈕）
  - 每個資料夾可標記類型：`exam`（考卷）/ `slide`（簡報）/ `handout`（講義）
- 設定存入 `config.yaml`（格式見下）

```yaml
watched_folders:
  - path: "D:/Teaching/Materials/材料力學"
    type: slide
  - path: "D:/Teaching/Exams/2026"
    type: exam
youtube:
  channel_id: "UCxxxxxxxx"
  default_privacy: unlisted
```

### ideate.py 邏輯

1. 讀取 `config.yaml` 的 watched_folders
2. 掃描各資料夾，找出「最近 N 天新增或修改的 PDF」（N 可設定，預設 14 天）
3. 對每個新檔案：
   - 用 Gemini Vision 讀首頁/目錄，判斷：這份文件能做幾題/幾段影片？
   - 輸出企劃清單（proposals）
4. 排除已有影片的題目（對照 exam JSON 的 youtube.video_id）
5. 輸出 `proposals.json`

proposals.json 格式：
```json
{
  "generated_at": "2026-05-10T08:00:00",
  "proposals": [
    {
      "id": "prop_001",
      "source_file": "D:/Teaching/Exams/2026/midterm.pdf",
      "source_type": "exam",
      "suggested_title": "自動控制 期中考 第3題解析",
      "reason": "答錯率高（根據題目難度判斷），尚未製作影片",
      "estimated_duration_min": 5,
      "status": "pending"
    }
  ]
}
```

### app.py 新增：企劃瀏覽頁

路由：`/proposals`

頁面內容：
- 列出 proposals.json 的所有企劃
- 每個企劃顯示：標題、來源檔案、建議原因、預估時長
- 操作：「核准製作」/ 「忽略」
- 按下核准 → 呼叫對應的 solve.py（考卷）或 slide_ingest.py（簡報）→ 送 pipeline 渲染
- 渲染完畢後，自動進入「上傳審查頁」

---

## v2.2 — 排程自動化

**目標：每週自動跑 ideate，渲染完成後通知 Dof 去審查。**

### schedule_runner.py

功能：
1. 執行 `ideate.py`（掃描教材、產生企劃）
2. 對所有 `status: pending` 的企劃自動觸發渲染
3. 渲染完成後發通知

通知方式（擇一）：
- Email（smtplib，Gmail SMTP）
- Line Notify（最簡單，一行 POST request）
- Windows 桌面通知（`plyer` 套件）

設定方式（Windows Task Scheduler）：
```
觸發：每週一 08:00
執行：python D:\...\schedule_runner.py
工作目錄：D:\...\autoSolverVideo
```

`schedule_runner.py` 提供 `--dry-run` 模式（只掃描、列出企劃，不觸發渲染），方便手動確認。

---

## 實作優先序建議

```
v2.0 先做（1~2 週）
  → publish.py CLI 版打通 YouTube 上傳
  → app.py 上傳審查頁
  → .gitignore 加入 client_secrets.json / youtube_token.json

v2.1 次之（2~3 週）
  → config.yaml 結構定義
  → app.py /settings 頁（watched folders 設定）
  → ideate.py 掃描邏輯
  → app.py /proposals 頁

v2.2 最後（1~2 週）
  → schedule_runner.py
  → 通知機制（Line Notify 最快）
```

---

## 決策備忘

| 決策 | 選擇 | 原因 |
|---|---|---|
| RAG 知識庫 | **不做** | 題庫量小，直接 Claude/Gemini Vision 讀 PDF 夠用；等題庫 > 200 題再評估 |
| 留言自動回覆 | **不做** | 學術帳號風險高，Dof 本人手動回覆 |
| 人工審查時機 | **上傳前（一個關卡）** | 影片生成全自動，只在上傳前確認 |
| watched folders 設定位置 | **app.py UI** | 不另開設定工具，統一在現有 Web UI 管理 |
| YouTube 預設隱私 | **unlisted** | 確認無誤後再從 YouTube Studio 改公開 |
| YouTube quota 限制 | 每天約 6 支 | 排程一次不要超過 5 支；批次上傳考慮分天執行 |
| 留言管理 | **不在此次範圍** | 之後視需求再規劃 |

---

## 相關參考

- YouTube Data API v3 Python 範例：https://developers.google.com/youtube/v3/guides/uploading_a_video
- OAuth 2.0 client secret 申請：GCP Console → API & Services → Credentials
- Line Notify token 申請：https://notify-bot.line.me/

---

> 最後更新：2026-05-06（Cowork 規劃討論）
