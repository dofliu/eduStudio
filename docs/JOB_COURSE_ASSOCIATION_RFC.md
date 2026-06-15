# RFC — Job ↔ 課程（Project）關聯：讓 render 旁白套該課 glossary

> 建立：2026-06-14　·　狀態：**待劉老師拍板**（一個架構抉擇，offline 前置）
> 對應清單：[PRODUCT_READINESS.md](PRODUCT_READINESS.md) **F9-2「課程術語/讀音表 glossary」**
> 的最後一塊 offline slice。
>
> 沿用既有 offline-first 紀律：這份只是把「多種合理解法間的架構抉擇」攤開 + 給建議，
> **不自主決定、不動 schema、不燒額度**（比照 [REVIEW_ASSIST_RFC.md](REVIEW_ASSIST_RFC.md)、
> [LOCAL_MODEL_RFC.md](LOCAL_MODEL_RFC.md)、`docs/latex-formula-rendering-proposal.md` 的先例）。

## 1. 為什麼卡住

F9-2 前五刀已把 **per-course glossary** 從 schema → 儲存 → API → 前端編輯 → 翻譯橋接全部接好：

- `core/glossary.py`：`Glossary`（per-course 術語表）+ 純函式 `to_pronunciation_map()`（→ TTS 讀音）
  / `to_translation_rules(lang)`（→ 翻譯固定譯名）。
- `core/project.py`：`ProjectStore.get_glossary(pid)` / `save_glossary(pid, g)`（每課落
  `{pid}/glossary.json`，與 `project.json` 分檔）。
- `server/routes/projects.py`：`GET/PUT /projects/{pid}/glossary` 編輯端點 + 前端 `GlossaryEditor`。
- `tts_backend.py`：`normalize_text(text, extra_pronunciation=...)`（`tts_backend.py:145`）已能吃
  per-course 讀音表，與全域 `pronunciation.json` **longest-first 合併、同 key 課程優先**
  （`_merged_pronunciation`, `tts_backend.py:68`）。

**唯一缺口**：render 旁白時，TTS 拿不到「這支 job 是哪一門課」，所以套不上該課 glossary。具體有兩道：

1. **缺 job → 課程的關聯**（**本 RFC 的決策點**）。`JobRecord`（`server/schemas.py:387`）沒有
   `project_id`；`ProjectStore.add_job(pid, job_id)`（`core/project.py:272`）只做 **course → jobs[]
   單向掛載**，沒有反查。runner 在 render 時手上只有 `JobRecord`，無從得知它屬於哪門課。
2. **TTS 呼叫端目前不透傳 `extra_pronunciation`**（次級、純 offline）。三個 backend 的
   `synthesize()` 都寫死 `normalize_text(text)`（`tts_backend.py:229` Edge / `:289` F5 / Google
   同理），沒把 per-course 讀音表往下帶。**決策點 1 拍板後，這道就是一條直線的 offline 接線。**

> 同一個 job↔課關聯也是把 `to_translation_rules()` 接進在地化（翻譯）route 的前提，所以這個決策
> 一次解鎖**旁白讀音**與**翻譯固定譯名**兩件事。

## 2. 三個合理解法

### 選項 A — 在 JobRecord 上記 `project_id`（denormalize，**建議**）

`JobRecord` 加 `project_id: str | None = None`（`extra="allow"` 已開 → 舊 `state.json` 無痛相容），
在 `create_project_job`（`server/routes/projects.py:148`，已知 `pid`）建 job 時一併寫入。runner render
時若 `job.project_id` 有值 → `ProjectStore.get_glossary(project_id)` 取 glossary →
`to_pronunciation_map()` 帶進 TTS。

- ✅ O(1)、明確、寫進 `state.json` 持久化、server 重啟後仍在。
- ✅ glossary **render 當下現讀**（編輯術語後重 render 立即生效，不會凍結舊版）。
- ✅ schema 加一個 optional 欄位＝最小 migration（沿 `artifact_versions`/`reviewed` 同手法）。
- ⚠️ 直接 `POST /jobs`（不經課程）建的 job `project_id=None`＝沒 glossary（合理：無主之 job 本就無課）。
- ⚠️ 輕度 denormalize：`project.jobs[]` 與 `job.project_id` 兩處都記關聯（但語意清楚、不易漂移，
  因為只在 `create_project_job` 一處同時寫）。

### 選項 B — ProjectStore 反查索引（scan）

不動 `JobRecord`；runner render 時呼叫一個新的 `ProjectStore.project_for_job(job_id)`，掃所有
`project.json` 的 `jobs[]` 找出包含此 `job_id` 的課。

- ✅ 單一真實來源（`project.jobs[]`），不 denormalize。
- ⚠️ render 路徑每次 O(N 課) 掃盤（課多時變慢；或要另維護反查索引，等於把複雜度搬到別處）。
- ⚠️ runner 直接耦合 `ProjectStore`（目前 runner 不依賴 project 層）。
- ⚠️ 課被刪 / job 被移除掛載時的競態要另想。

### 選項 C — 建 job 當下把 glossary snapshot 前傳進 job

`create_project_job` 時就 resolve glossary → 把 `to_pronunciation_map()`（或 glossary 參照）塞進
`JobOptions` / deck，render 直接用，**runner 完全不需碰 ProjectStore**。

- ✅ render 不依賴 project 層、最解耦。
- ⚠️ glossary 在**建 job 當下凍結**：之後編輯術語表，既存 job 重 render **不會**套到新術語
   （與「現讀」選項 A 相反，多數教學情境下會想要編輯即生效）。
- ⚠️ 資料重複（同一份讀音表複製進每支 job）。

## 3. 建議

**選 A（`JobRecord.project_id`）。** 理由：最小且明確的 migration、O(1) 反查、glossary **現讀**
（符合「編輯術語→重 render 立刻生效」的教學直覺），且自然涵蓋「無主 job 就沒 glossary」。B 的掃盤/
耦合與 C 的凍結語意都是為了避免一個 optional 欄位而付更大代價。

## 4. 拍板後的 offline 接線（不需再做架構決策，可逐刀 routine 自主推）

1. **F9-2g（schema + 寫入）**：`JobRecord` 加 `project_id`，`create_project_job` 寫入。動 `schemas.py`
   → 跑 `pytest`（硬規則 #7）。
2. **F9-2h（TTS 透傳）**：render 旁白前以 `ProjectStore.get_glossary(job.project_id).to_pronunciation_map()`
   取讀音表，沿 render_video → TTS `synthesize()` 把 `extra_pronunciation` 帶到
   `normalize_text(text, extra_pronunciation=...)`。glossary 為 None / 無 project_id ＝沿用現行行為
   （零影響）。全 mock、不打真 API、不真跑 TTS。
3. **F9-2i（翻譯 route 接 `to_translation_rules()`）**：同一關聯接進在地化翻譯，術語固定譯名生效。

## 5. 不可妥協紀律（拍板後接線時遵守）

- **不繞 review gate**：本功能只影響「旁白怎麼念 / 術語怎麼譯」，**完全不碰** R-2 render 入口 assert /
  狀態機 / reviewed 機制（硬規則 #1）。
- **glossary 缺失 fail-soft**：沒 project_id / 沒 glossary / 讀音表空 → 沿用現行 `normalize_text`
  行為，絕不因為「想套術語」而讓 render 失敗。
- **路徑/config 集中、type guard**：沿用既有慣例，不寫死。

## 6. 待劉老師拍板的開放問題

1. **選 A / B / C？**（建議 A）
2. glossary 應 **render 現讀**（A/B）還是 **建 job 凍結**（C）？（建議現讀）
3. 直接 `POST /jobs`（不經課程）的 job 沒 glossary，可接受？（建議可接受＝設計如此）

> **STOP**：本 RFC 0 行 production code 改動（純文件）。劉老師於上述三問拍板後，routine 可逐刀
> （F9-2g/h/i）自主 offline 接線。**自動建議術語**（掃教材抽術語）另碰 Gemini 額度＝GATE，不在本 RFC。
