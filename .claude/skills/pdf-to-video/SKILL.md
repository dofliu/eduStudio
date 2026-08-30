---
name: pdf-to-video
description: 把考題 PDF / 教學簡報 PDF / 文件變成黑板或簡報講解 MP4 + SRT。需要 Track B server (port 8000) 已啟動。包含「強制 review」階段防 AI 答錯流出 — 不可繞過 require_review=True。Triggers when 用戶說「把這份 PDF 變影片」「PDF 轉影片」「pdf-to-video <path>」「考題 PDF 出講解影片」「簡報 PDF 配旁白」, 或附 .pdf 檔說想要影片。
---

# pdf-to-video — PDF 變講解影片

把 PDF 餵給 autoSolverVideo 平台,自動 OCR / Gemini 分析 → 暫停讓老師 review → 渲染 MP4 + SRT。**永遠不繞 `require_review=True`**(學術誠信硬規則,見 `claude.md`)。

## 適用情境

- **考題 PDF** → 黑板逐題解答影片(每題每步驟動畫 + 配音)
- **教學簡報 PDF** → 投影片講解影片(每頁逐一旁白)
- **文件 PDF**(blog / 講義 / 論文) → AI 產簡報內容 → 講解影片

不適用:
- 純文字 blog / Markdown / URL → 用 `submit_job.py document / url`,不是這個 skill
- Git repo → 用 `submit_job.py repo`,不是這個 skill
- 影片想直上 YouTube → 用 `video-to-youtube` skill(尚未實作)

## 前置

跟用戶確認:
1. PDF 的絕對路徑(Windows 路徑用正斜線或加引號)
2. 是哪種類型:
   - 考題 → `source_type=exam`
   - 簡報 → `source_type=slides`
   - 文件 → `source_type=document`
3. **Track B server 是否啟動**(`curl http://localhost:8000/health` 或 `python -m server.main`)
4. **GEMINI_API_KEY 是否設**(`echo $GEMINI_API_KEY`)
5. 想用哪種聲音(預設讀 `tts_config.json`,edge 或 f5)

不確定就問,不要猜。

## 流程

### Step 1 — 確認 server alive

```bash
curl -s http://localhost:8000/health || echo "server not running"
```

若 server 沒起:**停下,請用戶開 server**,別自動 spawn(harness 啟動的 server 會跟用戶開的衝)。

### Step 2 — 提交 job

```bash
python scripts/submit_job.py <type> <pdf-path>
# type ∈ exam | slides | document
```

回傳 JSON,解析 `job_id` 跟 `status_url`。

⚠️ **強制 review** 預設行為:
- `exam`: `require_review=True`(預設,別改)
- `slides` / `document`: `require_review=False`(預設 fluent)

老師若**明確說**「我要 review 再 render」,加 `--review` flag。**永遠不要** 加 `--no-review` 對 exam,除非用戶極明確要求且講清楚為什麼(學術誠信底線)。

### Step 3 — 等 ingest 完成

Poll `status_url` 直到 `state` 變成 `awaiting_review`(exam)或 `rendering`(其他):

```bash
curl -s http://localhost:8000/jobs/<job_id> | jq -r .state
```

- 卡 `ingesting` 超過 5 分鐘:可能 Gemini 慢/API 限流,等就好
- 變 `failed`:看 `error_message`,告訴用戶失敗原因

### Step 4 — Review(exam 才有)

`state=awaiting_review` 時,**停下,叫用戶開 UI**:

```
http://localhost:8000/app/ (製作狀態 → 該 job → Review)
```

用戶逐題對 step 文字 / 公式 / 易錯提醒,**改完按 Approve**。skill 不要自動 approve。

可以 poll 直到 state 變 `rendering`(代表用戶按了 approve)。

### Step 5 — 等 render 完成

```bash
curl -s http://localhost:8000/jobs/<job_id> | jq -r .state
```

- `rendering` → 等(15 分簡報 ~ 30 分鐘,看頁數)
- `done` → 走 Step 6
- `failed` → 看 error,常見:F5 model 下載中(第一次)、字型缺、subprocess 失敗

### Step 6 — 印 artifacts 路徑

```bash
curl -s http://localhost:8000/jobs/<job_id>/artifacts | jq
```

回傳 MP4 + SRT 清單,告訴用戶:

- 影片在 `output/<exam_stem>/qN.mp4` 或 `videos/<exam_stem>/chN.mp4`
- 字幕在 `output/<exam_stem>/qN.srt` 同上
- 可以本地播放(VLC / mpv),或丟 `/video-to-youtube` skill 上傳(尚未實作)

## 不可繞過的硬規則

從 `claude.md`:

- ✅ **AI 數值不能未經 review 就當答案** — exam 必過 review
- ❌ **不自動 `--no-review`** — 即使用戶說「快點」,先問清楚為什麼
- ❌ **不偽裝 AI 估算值為實驗數據** — 從不,毫無例外
- ❌ **不自動 git commit** — render 完不要 commit 任何東西(影片在 gitignored 目錄,本來也 commit 不到,但仍然不要主動嘗試)

## 常見問題

| 症狀 | 原因 | 處理 |
|---|---|---|
| `connection refused localhost:8000` | server 沒開 | 請用戶開,別自動啟 |
| `awaiting_review` 但沒 ingest 結果 | Gemini API key 沒設 / 限流 | 檢查 `GEMINI_API_KEY` |
| F5 第一次卡住 5+ 分鐘 | 下載 1.35GB safetensors | 等就好,commit 318f5e8 已解 event loop blocking |
| `failed` 找不到字型 | Windows 字型路徑跟 Linux/Mac 不同 | 設 `CLAUDE_FONT_PATH` env var |
| Submit 之後 state 直接 `failed` | submit_job.py 把 server 錯誤吐 stderr | 看 stderr |

## 範例對話

```
用戶: 把 D:\exams\midterm_2026.pdf 變影片
你:
  1. 確認類型: 「這是考題 (`exam`) 還是教學簡報 (`slides`)?」
  2. 確認 server: curl /health 通的話進下一步
  3. python scripts/submit_job.py exam "D:/exams/midterm_2026.pdf"
     → job_id = abc123
  4. poll state, 等到 awaiting_review
  5. 「請開 http://localhost:8000/app/ 在製作狀態找到該 job 逐題 review, 改完按 Approve 我會繼續」
  6. 用戶按 approve 後 state → rendering
  7. 等 done, 印 artifacts 路徑
```

## 後續(尚未實作)

- `video-to-youtube` skill — 動 OAuth,要先跟用戶討論安全模型
- skill UI 整合 — 目前靠 CLI + 開瀏覽器手動 review,未來可整合 server review API
