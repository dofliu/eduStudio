# Routine closeout 完成 — 等用戶切 daily 模式

> 寫於 2026-05-28 (iter 138). hourly `/advance` routine 的 closeout backlog
> 4 項全部完成, routine 該停止每小時推進. 等劉老師用 `/schedule` 把 task 切成
> daily 5pm summary 模式 (或刪掉重建一個 summary-only 版本) + 給新方向.

---

## 背景

iter 111-133 連 23 個 iter 全在補 wrapper / route / helper safety lock
(純測試, 0 production code 改動), 沒抓到任何真 bug, 邊際效益遞減. 用戶
(2026-05-24) 決議設明確終點 → 列 4 項 closeout backlog, 做完即停 hourly.

細則見 [ROUTINE_ADVANCE_PROMPT.md](ROUTINE_ADVANCE_PROMPT.md) 的 "Closeout phase" 段落.

## Closeout backlog — 4 項全完成 ✅

server/runner.py 四個從沒直接測試的主流程 wrapper / orchestrator, 全部補上
安全鎖測試 (純測試, 0 production code 改動):

| iter | 對象 (server/runner.py) | 測試檔 | tests | commit |
|---|---|---|---|---|
| 134 | `_run_ingest_repo` (REPO ingest 主流程) | `tests/test_runner_ingest_repo.py` | +20 (1580→1600) | `34d6de8` |
| 135 | `_run_ingest_long_form` (DOCUMENT / URL 共用 ingest) | `tests/test_runner_ingest_long_form.py` | +22 (1600→1622) | `9c276d3` |
| 136 | `_run_render_inner` (render schema dispatch + section 過濾) | `tests/test_runner_render_inner.py` | +14 (1622→1636) | `0287dd6` |
| 137 | `run_job` (最外層主流程 orchestrator) | `tests/test_runner_run_job.py` | +23 (1636→1659) | `11c0dfd` |

closeout 期間共 +79 tests (1580 → 1659). 加上 iter 132/133 兩個更早的
orchestrator 安全鎖 (`_run_render` wrapper / `_run_render_phase`), server/runner.py
這條 ingest → review → render 主鏈現在每一層 wrapper 都有對應直接測試覆蓋.

## 為什麼停在這

- **server/runner.py 主鏈已全覆蓋**: ingest dispatch (iter 131) / 三條 ingest
  inner (134/135) / render wrapper + phase + inner (132/133/136) / 最外層
  run_job (137) — 沒有再裸奔的 orchestrator 值得鎖.
- **剩下的不該由 routine 自主做** (見 ROUTINE_ADVANCE_PROMPT.md「不可碰」清單):
  - `schedule_job` / `schedule_render` / `schedule_section_render` — 全是 1 行
    `asyncio.create_task(...)`, 沒 wrapper value-add 可鎖
  - E2-2 (Gemini 一次性產 25 個 SVG icon) — 需用戶決議 + 燒 API 額度
  - E1-3 (Gemini flow_diagram SVG + cairosvg) — 新 feature, 非 routine 範圍
  - 前端 UI 元件 (E2-6 / E1-4 的 React 部分) — 需用戶設計決策
  - v4 worker 持久化 (P0 #1/#3) — RFC 階段, 大型架構決策
- **再補 module test < 5 個的小檔純消耗 API**, 都已過保護線.

## 給用戶的下一步

1. **切 schedule 模式**: 用 `/schedule` 把 `autosolver-advance-hourly` 從每小時
   改成 daily (建議下午 5pm summary-only), 或刪掉重建一個只做「總結昨日進度 +
   提後續方案」的 summary 版本. hourly 自主推進階段結束.
2. **給新方向**: routine 已把能自主安全推的低風險工作做完. 接下來要推進需要
   用戶決策的項目 (擇一):
   - **內容品質**: Gemini narration 截斷率 22% (見 TODO 🟡) / pronunciation.json
     念錯詞收集 (需實測影片樣本)
   - **動態視覺 E 軸**: E2-2 Gemini 產 icon SVG / E1-3 flow_diagram frame
     (需確認 API 額度 + 風格)
   - **TTS 個人化**: narration_style 5 preset 選定 / persona/jliu v2 樣本 /
     voice clone (需錄音 + 決定 ElevenLabs 月費)
   - **平台收斂 v4**: job 持久化 worker (P0 #1) — 真要交給 Kiwi / Christian /
     上雲前必做, 但要先定 RFC 選型 (RQ / Celery / SQLite)

## 狀態快照 (2026-05-28)

- **測試**: 1659 passed, CI 4 組 matrix (ubuntu/win × py 3.10/3.12) + frontend-typecheck
- **progress**: 99 (production 可用, 內容品質 + 平台收斂持續迭代中)
- **git**: main 乾淨, 已 push 到 `0287dd6..11c0dfd`

---

**routine STOP**: closeout 完成. 在用戶切 schedule 模式 / 給新方向前, 不再自主
找事做新 iter. 後續若仍被 hourly 觸發, 應直接回報「closeout 已完成, 等用戶決策」
而非硬找工作.
