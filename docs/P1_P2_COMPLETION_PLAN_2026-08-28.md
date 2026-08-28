# eduStudio P1／P2 完成計畫與驗收矩陣

日期：2026-08-28
狀態：本機驗證完成，等待 GitHub Actions 與最終報告
基準版本：`8da9935`

## 範圍

本輪只關閉 2026-08-27 專案稽核與 P0 live E2E 新發現的 P1／P2，不把長期產品 roadmap 或大型架構重寫混入本輪。

| ID | 優先級 | 項目 | 完成條件 |
|---|---|---|---|
| P1-1 | P1 | Ollama provider production 接線 | 可將文字 role 指向 Ollama；integration test 證明選 Ollama 時不呼叫 Gemini；本機 live inference 通過 |
| P1-2 | P1 | 既有 6 檔未提交修正收斂 | targeted tests、`git diff --check`、完整 regression 通過；獨立 commit 並同步遠端 |
| P1-3 | P1 | PPTX live round-trip | 真實執行 upload → conversion → augmentation/export；若需安裝 LibreOffice，完成安裝後再驗證，不以 mock 代替 |
| P1-4 | P1 | `/api/generate` request validation | 非法 `mode`／`style`／`density` 回 422，合法各模式保持相容；具 regression tests |
| P1-5 | P1 | GitHub Actions Node runtime | 官方 actions 升級至不再觸發 Node.js 20 deprecated warning的版本，雲端 CI 全綠 |
| P2-1 | P2 | Whisper 三流程 | `large-v3` 可由 RTX 4080 載入；影片 STT／會議摘要／歌詞抽取各跑一個真實最小流程 |
| P2-2 | P2 | Google Photos OAuth readiness | credentials/status/bootstrap/callback 邊界可測；若需帳號授權，明確停在使用者 OAuth consent，不宣稱未發生的授權 |
| P2-3 | P2 | Deployment token | token on/off、未授權 401、Bearer/cookie 授權與 event sink exemption 通過；localhost 測試 server 不強制開 token |
| P2-4 | P2 | 四工作站 click-through | 影片、簡報、圖卡、漫畫 UI 入口與關鍵控制流程完成 desktop smoke；API/artifact 證據與 UI 證據分開記錄 |

## 本機驗證結果

- P1-1：Ollama `qwen3:4b` live inference 通過；provider routing integration tests 通過。
- P1-2：既有六檔修改已納入 regression；完整 backend `2839 passed, 1 skipped`。
- P1-3：以 Windows PowerPoint COM fallback 完成真實 PPTX → PDF round-trip，`6 passed`。
- P1-4：非法 `mode`／`style`／`density` live 均回 `422`。
- P1-5：Actions 已升級至 `checkout@v6`、`setup-python@v6`、`setup-node@v6` 與 Node 24；待雲端 CI readback。
- P2-1：Whisper `large-v3` 由 RTX 4080 以 `cuda / float16` 載入；meeting、song、dubbing 三條 live API 均回 `200` 且產物非空。
- P2-2：OAuth credentials/bootstrap/callback 邊界通過；帳號 consent 尚未完成，`/google-photos/status` 誠實回 `authorized=false`。
- P2-3：token server live：health `200`、匿名 API `401`、Bearer `200`、cookie `200`、event sink exemption `204`。
- P2-4：Video／Presentation／Card／Comic 逐站點 click-through 通過；手機 390×844 smoke 與 console zero-error 通過。

## 驗證層級

1. Unit／contract：錯誤處理、provider 選路、request validation。
2. Integration：FastAPI route、檔案轉換、provider/backend 邊界。
3. Live：Ollama、Whisper、LibreOffice、Gemini 與實際 artifact。
4. UI smoke：四工作站可進入與操作，並確認產出狀態可追蹤。
5. Release：backend full suite、frontend test/typecheck/build、secret scan、GitHub Actions、local/remote SHA。

最終結果與證據將另寫入版本化 DOCX 報告；未通過或需外部帳號互動的項目保留為 `[BLOCKER]`，不以 mock 或靜態檢查冒充 live 成功。
