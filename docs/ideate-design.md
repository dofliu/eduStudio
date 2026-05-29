# ideate.py — 自動內容企劃 RFC (v4 階段 2 B)

> v4 階段 2 B 設計。把 watched_folders → Gemini 分析 → proposals.json → React UI 的流程跟 v3.x 既有架構接好。

---

## 動機

老師每週要決定「這份新進的 PDF 要不要做成影片?哪幾題?」需要人工掃資料夾、判斷重要性、跟既有片單比對。

`ideate.py` 把這步驟自動化:**watched_folders 掃描 → Gemini 分析 → 產 proposals → React UI 核准 → 自動 submit_job**。

---

## 跟 v3.x 既有元件的對接

```
┌────────────────────┐
│ watched_folders/   │   user 設定要監看的資料夾 (config.yaml)
│ (D:/Materials...)  │
└─────────┬──────────┘
          │  ideate.scan_changed_files (last_modified > N 天前)
          ▼
┌────────────────────┐
│ FileCandidate list │   PDF / md / pptx 候選
└─────────┬──────────┘
          │  ideate.propose_from_file (Gemini Vision 看首頁/目錄)
          ▼
┌────────────────────┐
│ Proposal list      │   每份檔案 → 1+ 個影片企劃
└─────────┬──────────┘
          │  ideate.dedupe_against_jobs (比對 JobStore 既有 job + youtube.video_id)
          ▼
┌────────────────────┐
│ proposals.json     │   存到 jobs/proposals.json (跟 job state.json 並列)
└─────────┬──────────┘
          │  GET /proposals (server route)
          ▼
┌────────────────────┐
│ React UI:          │   ProposalsList 頁
│ /ui/proposals      │   每張卡片: 來源 / 標題 / 原因 / 預估時長 / [核准 / 忽略]
└─────────┬──────────┘
          │  POST /proposals/{id}/approve
          ▼
┌────────────────────┐
│ submit_job 流程     │   走既有 server.runner.schedule_job
│ (跟手動上傳同流程)   │   require_review=True 強制 (P0 #4)
└────────────────────┘
```

關鍵接點: **`approve` 端點不繞 `require_review=True`**(exam_pdf 預設仍要 review)。proposal 只是省了「找檔 + 想標題」的人力,不是省 review。

---

## Schema

### `WatchedFoldersConfig` (`config.yaml`)

```yaml
watched_folders:
  - path: "D:/Teaching/Materials/材料力學"
    source_type: slides_pdf        # exam_pdf / slides_pdf / document
    scan_window_days: 14           # 掃 N 天內修改的檔, 預設 14
  - path: "D:/Teaching/Exams/2026"
    source_type: exam_pdf
    scan_window_days: 30

ideate:
  llm_model: "gemini-2.5-flash"    # 走既有 core.config.GEMINI_MODEL
  max_proposals_per_file: 3        # 一份 PDF 最多產幾個 proposal
  enabled: true                    # off 時 ideate 完全不跑
```

### `Proposal` schema

```python
class ProposalStatus(str, Enum):
    PENDING = "pending"          # 剛產生, 待 user 決策
    APPROVED = "approved"        # user 核准, 已建立 job
    IGNORED = "ignored"          # user 拒絕
    EXPIRED = "expired"          # 過 30 天沒處理, 自動標記

class Proposal(TypedDict):
    id: str                              # prop_<uuid8>
    generated_at: datetime
    source_file: str                     # 絕對路徑
    source_type: SourceType              # 對齊既有 enum
    suggested_title: str                 # Gemini 建議的影片標題
    suggested_chapters: list[str]        # (可選) 給 slides_pdf 用的章節大綱
    reason: str                          # 「為什麼這份值得做」(50~100 字)
    estimated_duration_min: int          # 預估時長 (供排程算 ROI)
    status: ProposalStatus
    job_id: str | None                   # APPROVED 後填, 反查
```

### `proposals.json` 結構

```json
{
  "generated_at": "2026-05-12T18:00:00+08:00",
  "config_hash": "sha256:...",
  "proposals": [Proposal, ...]
}
```

`config_hash` 用來偵測 config 變更, 變更後下次 ideate 重新掃所有資料夾(不能信賴 last_scan_at)。

---

## 流程細節

### 1. 掃 watched_folders (`ideate.scan_changed_files`)

- 輸入: `WatchedFoldersConfig`
- 輸出: `list[FileCandidate]`
- 邏輯:
  - 對每個 `watched_folders[i]`:
    - `Path.glob("**/*.pdf")` (依 `source_type` 決定 ext: pdf / md / pptx)
    - filter `mtime > now() - scan_window_days`
    - 排除 hidden / `.tmp` / `~$*`
- 不分析內容, 只列檔

### 2. 對每個 candidate 跑 Gemini (`ideate.propose_from_file`)

- 輸入: `FileCandidate`, `IdeateConfig`
- 輸出: `list[Proposal]` (≤ `max_proposals_per_file`)
- 邏輯:
  - 對 PDF: PyMuPDF 抓首頁 + 目錄頁 (或前 5 頁) → base64 → Gemini Vision
  - prompt: 「這份是 {source_type}, 評估它能做成幾段影片, 每段建議標題 + 為什麼值得做」
  - 解析 JSON 輸出成 `Proposal[]`
- **失敗處理**: API 限流 / parse 失敗 → log + 跳過, 不擋整批

### 3. 去重 (`ideate.dedupe_against_jobs`)

- 輸入: `list[Proposal]`, `JobStore`
- 輸出: `list[Proposal]` (移除重複)
- 邏輯:
  - 每個 proposal 對照 JobStore: 既有 job source.path 相同 + state=DONE 就 skip
  - 對照 YouTube uploads (`YoutubeUpload.video_id` 存在表已上傳)
  - 對照前次 proposals.json: 已 APPROVED/IGNORED 不要再產出

### 4. 寫 proposals.json (`ideate.save_proposals`)

- 寫到 `core.config.PROPOSALS_PATH` (新加, jobs/proposals.json)
- 用既有 atomic write pattern (write tmp + rename)

### 5. React UI (新增 page `ProposalsList`)

- GET `/proposals` → 列出 pending
- 每張卡片顯示 source / title / reason / duration
- 操作:
  - **核准** → POST `/proposals/{id}/approve` → 內部 `store.create(...)` + `schedule_job(...)` (跟既有 upload 流程一樣, **require_review 依 source_type 預設**)
  - **忽略** → PATCH `/proposals/{id}` status=IGNORED
- 加 header 連結 `/ui/proposals`

---

## v4 階段 2 B 拆解 (建議 5 個 iter)

1. **scaffold + schema + design RFC** (本 iter 10) ← 我們在這
2. `scan_changed_files` 實作 + tests
3. `propose_from_file` 實作 (Gemini call + parse) + tests with mock
4. `dedupe_against_jobs` 實作 + tests
5. server route + React UI ProposalsList page

每階段都會 commit + push, user 可在任何點 pause / 給 feedback。

---

## STOP 條件 (一定要等用戶決策的)

- **config.yaml schema 確認**: watched_folders 結構是否合用戶實際資料夾佈局?
- **第一份 proposals.json 跑出來後**: Gemini 提案品質如何?要不要調 prompt?
- **approve 流程的 review gate**: 是否所有 source_type 都過 review (跟 P0 #4)?
- **schedule_runner / 定時觸發** (v2.2): cron 還是 Windows Task Scheduler? user 偏好?

---

## 不在這個 RFC 範圍 (留下次 iter)

- Gemini prompt tuning (要實跑幾份 PDF 看品質才能調)
- watched_folders UI 設定頁 (現在用手 edit config.yaml)
- ROI 排序邏輯 (按 estimated_duration / 預測觀看數排)
- 通知機制 (email / Telegram / Slack)
- A/B 多模型比較
