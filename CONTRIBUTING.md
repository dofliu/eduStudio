# 貢獻指南 · Contributing to eduStudio

歡迎！eduStudio 是一個**自架的教學內容工作站**，核心信念是「**每個 AI 產出都有人工審查關卡**」。
貢獻前請花兩分鐘讀完這份——尤其是「不可妥協的規則」一節，它定義了這個專案的底線。

> 中文為主、English summary at the bottom.

---

## 開始之前

- **小改動**（typo、文件、明確的小 bug）：直接開 PR。
- **功能 / 行為 / 架構改動**：請**先開一個 issue 討論**再動手，避免白做。這個專案對「AI 產出
  正確性」與「離線優先」有強紀律（見下），先對齊方向比較省力。

## 本機開發

```bash
# 後端 (Python FastAPI)
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt          # 核心依賴
pip install -r requirements-dev.txt      # 測試/開發依賴
uvicorn server.main:app --host 127.0.0.1 --port 8000

# 前端 — 統一 /app（React 19 + Vite，原始碼在 frontend/edustudio/）
cd frontend && npm install && npm run build   # 或 npm run build:app
```

需要 `GEMINI_API_KEY`（`cp .env.example .env` 後填入）。其餘環境變數都有預設值，見 `.env.example`。

### 前端建置須知（重要）

- `/app` 是**唯一的正式前端**，原始碼自包含在 `frontend/edustudio/`，build 產物輸出到
  `web/eduapp/`，server serve 在 `/app`。
- **base 已在 `frontend/vite.config.ts` 寫死成 `/app/`** → 直接 `npm run build`（或語意別名
  `npm run build:app`）即可，**不必**再記得在 CLI 帶 `--base=/app/`（以前漏了會整頁空白 404）。
- legacy 前端已全數退場（U-1 `/studio`、U-5 `/ui`，2026-08-30）：`web/` 現在只是 build
  輸出目錄（`web/eduapp`），兩個舊路徑一律 307 轉址 `/app/`。前端功能一律進 `/app`。

## 跑測試（送 PR 前必做）

```bash
pytest tests/          # 後端測試護網（~2400 tests）
cd frontend && npm run build   # 前端型別/編譯自檢
```

CI（GitHub Actions）會在每個 PR 跑 **pytest 4 組 matrix（Ubuntu/Windows × Py 3.10/3.12）+
frontend typecheck + GitGuardian 金鑰掃描**。**綠燈才會合併。**

---

## 🔴 不可妥協的規則（這個專案的底線）

1. **AI 產出的數值不能未經人工 review 就當最終答案。**
   適用每一個 step、公式、數字。`require_review=True` 的 job（如考卷）**必須**停在
   `awaiting_review` 等人工核准才能 render。**任何繞過審查關卡的 PR 一律不收**——這是學術
   誠信底線。

2. **離線優先（offline-first）。** 純程式、不打 Gemini/GCP 額度、有測試的改動可以直接做。
   會**消耗 API 額度 / 改安全模型 / 動架構**的改動，請先在 issue 寫清楚再討論，不要在 PR 裡
   夾帶。

3. **動 `server/` `core/runner` `schemas` → 一定跑 `pytest tests/`**，並在 PR 描述貼結果。

4. **新功能進 Track B（FastAPI server），不進 Track A**（Track A 已退到只剩 redirect）。

5. **字型路徑不寫死。** 用 `CLAUDE_FONT_PATH` / `CLAUDE_FALLBACK_FONT_PATH` /
   `CLAUDE_MONO_FONT_PATH`，確保 Win/Mac/Linux 都跑得動。

6. **設定檔 / 路徑常數集中在 `core/config.py`**，不要在各模組各自定義 `BASE_DIR`。

7. **Schema dispatch 用 type guard**（`isExamDraft` / `isDeckDraft` 等），不要硬寫
   `if "problems" in deck` 這種字串判斷。

8. **別誤 commit 機密 / 本機檔。** `settings.json` / `.env` / `client_secret*.json` /
   `youtube_token.json` / `tts_config.json` 都已 gitignore——`tts_config.json` 在 smoke test
   會被改，特別小心。

## PR 規範

- 一個 PR 做一件事，盡量小（多檔大改難 review）。
- 標題簡潔、描述寫清楚「做什麼 / 為什麼 / 怎麼測」。
- 改 schema 型別請附 migration 說明。
- 連結對應 issue（若有）。

## 回報安全問題

請勿開公開 issue。見 [SECURITY.md](SECURITY.md)。

---

## English summary

eduStudio is a self-hostable teaching-content studio built around a **human review gate over every
AI output**. Before contributing:

- Open an **issue first** for any feature/behavior/architecture change; small fixes can go straight to PR.
- Run `pytest tests/` (and `npm run build` in `frontend/`) before sending a PR. CI must be green to merge.
- **Non-negotiable:** never bypass the review gate — AI-produced numbers/steps must stay
  `awaiting_review` until a human approves. Keep changes **offline-first**; anything that spends API
  quota or changes the security/architecture model needs discussion first.
- Don't hardcode font paths (use `CLAUDE_*_FONT_PATH`); keep path constants in `core/config.py`; use
  schema type guards; never commit secrets or local config (`settings.json`, `.env`,
  `client_secret*.json`, `tts_config.json`, …).

Thanks for helping teachers ship better content. 🎓
