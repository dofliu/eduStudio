# eduStudio P3 完成計畫與驗收矩陣

日期：2026-08-28
狀態：本機驗收完成，等待本次實作 commit 的雲端 CI
基準版本：`2f445a2`

## 範圍

本輪 P3 只處理 P1／P2 驗證報告列出的四項技術債；不擴張到 Google Photos 使用者 consent 或新功能開發。

| ID | 類型 | 項目 | 完成條件 |
|---|---|---|---|
| P3-1 | Framework debt | FastAPI startup lifecycle | 移除 `@app.on_event`，改用 `FastAPI(lifespan=...)`；TestClient 證明 startup checks 只執行一次 |
| P3-2 | Test debt | pytest-asyncio loop scope | `asyncio_default_fixture_loop_scope=function` 明確寫入設定；完整 pytest 不再出現該設定 warning |
| P3-3 | Infrastructure boundary | PowerPoint fallback CI 邊界 | CI 保留 unit／contract／integration tests 並明確排除 `office_live`；Windows 本機真實 PPTX round-trip release gate 通過 |
| P3-4 | Portability debt | Whisper cache portability | 動態支援 `HF_HUB_CACHE`／`HF_HOME`／`XDG_CACHE_HOME`；只接受完整 snapshot；loader 直接使用解析出的本機路徑；`/health` 回報 `cached` 與 `cache_source` |

## Targeted evidence

- P3-1／P3-2／P3-3／P3-4 targeted suite：`27 passed, 1 deselected`。
- Office local release gate：`1 passed, 5 deselected`，由 Windows PowerPoint COM 完成真實 PPTX→PDF→augmentation 流程。
- Office gate collection：CI 可收集 `TestHappyPath::test_creates_job_and_augments`，但 hosted runner 不冒充 desktop Office 驗證。
- Whisper unit tests包含 `HF_HOME`、`HF_HUB_CACHE` 優先序、完整 snapshot 與 partial cache fail-closed。
- Backend full regression（排除獨立 Office gate）：`2845 passed, 1 skipped, 1 deselected`；唯一 skip 為 Windows symlink 能力限制。
- Frontend：正式 `/app` unit tests `7 passed` 且 production build 成功；legacy web TypeScript 與 Vite build 成功。
- Live server：lifespan 啟動成功且 stderr 無 FastAPI startup deprecation；`/health` 回報 `whisper.cached=true`、`cache_source=HF_HOME`。
- Whisper live load：本機 `D:\hf-cache` snapshot 由 RTX 4080 以 `cuda／float16` 載入。

## 證據邊界

- FastAPI lifespan 依官方建議使用 async context manager：<https://fastapi.tiangolo.com/advanced/events/>。
- Hugging Face cache 依官方 `HF_HOME`／`HF_HUB_CACHE` 定義：<https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables>。
- 本機 Office gate 只證明此 Windows／PowerPoint 環境可 round-trip；不代表 GitHub hosted runner 具備 PowerPoint，也不代表所有 Office 版本相容。
- Whisper cache 與 CUDA live readback 只證明此 RTX 4080 環境可用，不等同其他電腦已完成驅動、CUDA 或模型部署。
