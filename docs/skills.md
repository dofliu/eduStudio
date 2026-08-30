# Claude Code Skills — autoSolverVideo

這份是「Claude Code skill」在本 repo 的索引與使用筆記。Skill = 在 Claude
Code 對話裡用一句自然語言就觸發的封裝流程。本專案的 skill 不在使用者個人
資料夾 (`~/.claude/skills/`) 而是 **跟著 repo 走** (`.claude/skills/`),
讓 Kiwi / Christian 一 clone 就能用同一套流程。

> 目的: 把 server-based 工作流 (PDF 入 → review → MP4 + SRT → YouTube)
> 包成「一句話呼叫」, 而不必每次手寫 `curl` 跟 `submit_job.py`。
> Skill 仍受 [claude.md](../claude.md) 的硬規則約束 — 不會自動繞 review,
> 不會自動 commit, 不會自動上傳。

---

## 索引 (現況)

| Skill | 狀態 | 觸發詞範例 | 對應 CLI |
|---|---|---|---|
| `pdf-to-video` | ✅ 已實作 (文字指引) | 「把這份 PDF 變影片」 / 「pdf-to-video <path>」 | `scripts/submit_job.py` |
| `video-to-youtube` | ⛔ 未實作 (需先決議 OAuth 安全模型) | 「把這支影片傳上 YouTube」 | `core/publish.py` |

實作位置:`.claude/skills/<name>/SKILL.md`。Claude Code 啟動時會掃這個
目錄,把 SKILL.md frontmatter 的 `description` 拿去比對使用者自然語言。

---

## pdf-to-video

把 PDF 餵給 Track B server (port 8000),自動 OCR + Gemini 分析,**停下
等老師 review**,然後渲染 MP4 + SRT。

### 適用三種輸入

- **考題 PDF** (`source_type=exam`) → 黑板逐題解答影片
- **教學簡報 PDF** (`source_type=slides`) → 每頁旁白講解
- **文件 PDF** (`source_type=document`) → AI 產簡報 → 講解影片

純文字 blog / Markdown / URL 不用這個 skill, 直接 `submit_job.py
document` 或 `url`。Git repo 也是 `submit_job.py repo`。

### 前置 (不會自動做)

1. **Track B server 已啟動** — `python -m server.main` 跑在 port 8000
2. **`GEMINI_API_KEY` 已設** — `.env` 或 shell env
3. **`tts_config.json` 已選 backend** — `edge` / `f5` / `google`
4. **`output/` 跟 `videos/` 目錄有寫入權限**

任何一個沒備好,skill 會停下叫你補,不會自動 spawn server 或亂寫 config。

### 流程概覽

```
[用戶說: 把 D:\midterm.pdf 變影片]
  ↓
[skill 問: 考題 / 簡報 / 文件?]
  ↓
[curl /health 確認 server alive]
  ↓
[python scripts/submit_job.py <type> <path>]
  → job_id, status_url
  ↓
[poll /jobs/<id> 直到 state ∈ {awaiting_review, rendering}]
  ↓
[exam → awaiting_review → 開 http://localhost:8000/app/ (製作狀態) review]
  ↓ (用戶 approve)
[poll 直到 done]
  ↓
[curl /jobs/<id>/artifacts → 印 MP4 + SRT 路徑]
```

完整步驟 + 常見問題見 [.claude/skills/pdf-to-video/SKILL.md](../.claude/skills/pdf-to-video/SKILL.md)。

### 硬規則 (skill 不繞)

- ✅ **exam 一定走 review** — `require_review=True` 預設,skill 永遠不
  自動加 `--no-review`。即使用戶說「快點直接跑」,先問為什麼。
- ✅ **不自動 approve** — `state=awaiting_review` 必須老師手動按 Approve,
  skill 只 poll 不 click。
- ✅ **不自動 git commit** — render 完不要 commit 任何東西。
- ✅ **不自動上傳** — 上 YouTube 是 `video-to-youtube` 的事,不在這個
  skill 範圍。

---

## video-to-youtube (規劃中, 未實作)

把 `output/<exam>/qN.mp4` 一系列影片透過 `core/publish.py` 上 YouTube。

**為什麼還沒做**: 動 OAuth client_secret + refresh_token 的安全模型要
先跟用戶決議。可選方案:

1. Skill 跟 server 共用 `~/.youtube_oauth_token.json`,server 已有的 refresh
   flow 直接套
2. Skill 走 server `/jobs/<id>/publish` route (server 內部處理 OAuth)
3. Skill 純命令列、不碰 OAuth,只列出該上傳的 MP4 路徑 + 提示用戶手動上傳

選 (2) 最乾淨,user 一個 OAuth flow 在 server side 跑完就行。目前等用戶
決議,屬於 TODO.md 階段 1 內 STOP 條件之一。

---

## 自寫 skill (給 Kiwi / Christian)

要在本 repo 加新 skill, **建議流程**:

1. 在 `.claude/skills/<name>/` 建一個資料夾
2. 寫 `SKILL.md`,frontmatter 至少要有:

   ```yaml
   ---
   name: <name>
   description: <一句話, Claude Code 拿這個比對自然語言, 寫清楚什麼情境會觸發>
   ---
   ```

3. body 寫:
   - 適用情境 / 不適用情境
   - 前置 (要 user 確認的事)
   - 流程步驟
   - 硬規則 (這個 skill 不能繞的事)
   - 常見問題 + 對應 CLI 範例

4. 不要在 SKILL.md 內塞 secret / API key — skill 是 commit 進 repo 的。

5. Test:在 Claude Code 對話裡用觸發詞句測,確認 skill 有被選中。

**避免**:把 skill 寫得太「黏」(自己 spawn server / 自己 commit / 自己
approve review)。Skill 是「自動化常見指令鏈」,不是「自動化整個產品決策」。
人工判斷的地方一定要停下問。

---

## 相關文件

- [.claude/skills/pdf-to-video/SKILL.md](../.claude/skills/pdf-to-video/SKILL.md) — 完整 skill 內容
- [scripts/submit_job.py](../scripts/submit_job.py) — skill 底層的 CLI wrapper
- [claude.md](../claude.md) — 專案硬規則 (skill 不可繞)
- [docs/ROUTINE_ADVANCE_PROMPT.md](ROUTINE_ADVANCE_PROMPT.md) — 自動 routine 流程 (跟 skill 不同, routine 是非互動)
