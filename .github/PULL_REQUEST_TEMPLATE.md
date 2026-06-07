<!-- 一個 PR 做一件事，盡量小。功能/架構改動請先開 issue 討論。 -->

## 做什麼 / What
<!-- 一兩句說明這個 PR 的改動 -->

## 為什麼 / Why
<!-- 動機；若有對應 issue 請連結：Closes #___ -->

## 怎麼測 / How tested
- [ ] `pytest tests/`（動 server/runner/schemas 必跑，請貼結果）
- [ ] `cd frontend && npm run build`（有動前端時）
- [ ] 手動驗證：<!-- 描述 -->

## 自我檢查 / Checklist
- [ ] **沒有繞過 AI 產出的人工 review 關卡**（`require_review` 行為未被弱化）
- [ ] 這是 **offline-first** 的改動；若會花 API 額度 / 改安全模型 / 動架構，已先在 issue 討論
- [ ] 沒有寫死字型路徑、沒有在各模組另立路徑常數（集中於 `core/config.py`）
- [ ] 沒有 commit 機密 / 本機檔（`settings.json`、`.env`、`client_secret*.json`、`tts_config.json` …）
- [ ] schema 型別有改 → 附了 migration 說明
