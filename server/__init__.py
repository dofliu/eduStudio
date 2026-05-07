"""FastAPI server — 把 core/ 的功能包成 HTTP API。

PR-2a 範圍: 純 transport 層,不含新業務邏輯。
- POST /jobs       → 建立 job (exam_pdf | slides_pdf)
- GET  /jobs       → 列出
- GET  /jobs/{id}  → 拿狀態
- GET  /jobs/{id}/draft   → 拿 deck.json (review 模式)
- PUT  /jobs/{id}/draft   → 改 deck.json (review 模式)
- POST /jobs/{id}/approve → 觸發渲染 (review 模式)
- GET  /jobs/{id}/artifacts/{filename} → 下載 MP4 / SRT

Job 狀態持久化採 JSON 檔案 (jobs/<id>/state.json),server 重啟後可恢復。
進入點: `python -m server.main` 或 `uvicorn server.main:app --reload`。
"""
