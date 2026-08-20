# INTEGRATION_KICKOFF — 三專案整併啟動書（給 Claude Code ultraplan）

> 用途:把這份文件複製到**新整合資料夾**根目錄,在該資料夾開 Claude Code,
> 用 ultraplan / ultrathink + plan 模式請它展開完整實作計畫。本檔自足,
> 不依賴任何對話上下文;細節事實基礎見下方「延伸閱讀」兩份文件。
>
> 建立日期:2026-06-04。決策已定案(見 §5),ultraplan 可挑戰但需明講理由。

---

## 1. 一句話目標

把三個現有專案整併成一個產品:**「給要在 YouTube 上課的老師用的 NotebookLM+」**——
從任何來源 → 接地、可審查、多語言的教學產製物 → 一鍵發布到 YouTube。

不是砍掉重來;是**以 autoSolver 為核心,把另外兩個當服務掛上去,砍掉重複**。

---

## 2. 三個來源專案（實際路徑，CLI 可直接讀）

| 專案 | 絕對路徑 | 棧 | 整併後角色 |
|---|---|---|---|
| **autoSolver**（主） | `D:\Project_CodingSimulation\courseRelated\autoSolverVideo` | Python · FastAPI · port 8000 | **核心 + 影片產製站** |
| infoCard | `D:\Project_CodingSimulation\PersonalHelper\infoCard` | TypeScript · React19 + Express · port 8080 | 圖卡/簡報產製站（前端） |
| translateGemma | `D:\Project_CodingSimulation\PersonalHelper\translateGemma` | Python · FastAPI + MCP · Gradio | 在地化 + 配音 + OCR/會議/學習 |

**延伸閱讀（事實基礎，務必先讀）**：
- `D:\Project_CodingSimulation\courseRelated\autoSolverVideo\DESIGN_SPEC.md` — 三服務真實 API 契約、重疊盤點、資料模型、逐模組判斷、決策紀錄
- `D:\Project_CodingSimulation\courseRelated\autoSolverVideo\ROADMAP_UNIFIED.md` — 定位、分階段、兩張 trade-off 表

---

## 3. 為什麼以 autoSolver 為主

盤點三個 repo 的實際程式碼後確認:

- `autoSolver/server/` **已經是「Project 核心」的 80% 雛形**:完整 Job 狀態機
  (`pending → ingesting → awaiting_review → rendering → done → failed`)、人工 review gate、
  artifacts、Library、磁碟持久化、per-job 結構化 log、**257 tests + CI**。
- 它已支援 5 種來源(`exam_pdf / slides_pdf / repo / document / url`),涵蓋整條攝取→產製→發布。
- 護城河(YouTube 上傳、字幕、review gate)都在這裡,且難重做。

→ 其餘兩個專案 **不複製進核心**,維持原 repo,透過 HTTP / MCP 被核心呼叫。

---

## 4. 整併策略：strangler（新薄層 + 既有當服務）

**新整合 repo 只放兩樣新東西**(其餘全靠呼叫既有服務):

1. **Project / Notebook 薄層**:在 autoSolver JobStore 基礎上加 `project_id` 概念 +
   統一 Shell 入口(一個 landing,路由到各模組,共用 Project 清單/Library)。
2. **RAG 接地層**(Phase 2 才做):Source Store + 向量檢索 + 帶 citation 的接地問答。

**真正要「新建」的只有這兩塊;其餘是整合或局部改**(逐模組判斷見 DESIGN_SPEC §6)。

> ⚠️ 建議的 repo 形態:新 repo = 編排核心(Python/FastAPI),三個來源 repo 留原地當服務。
> 若 ultraplan 認為 monorepo 更好,可提出但需列 trade-off。

---

## 5. 已定案決策（ultraplan 視為前提，要改需明講理由）

1. **核心棧 = Python**(2/3 已是 + RAG 生態 + autoSolver JobStore 直接升格)。
2. **翻譯 = 雲端 Gemini API**,砍掉本地 Ollama `translategemma`。理由:解除「全系統須本地」限制
   讓 core/RAG/Shell 能上雲;且 autoSolver/infoCard 本就用 Gemini,Ollama 是唯一本地 AI 異類。
   做法:建共用 `translate()` helper(Gemini),autoSolver `core/translate.py` 退掉 Ollama;
   translateGemma 保留 OCR/配音/會議/學習等獨有管線,其 text 翻譯也切 Gemini(其 meeting-summary
   端點已有 `ai_backend=ollama|gemini` 切換可複用)。
3. **infoCard 舊 IndexedDB 成品不遷移**,只「之後新成品」write-back 回核心 Project → 改動輕。
4. **語言碼 canonical = `zh-TW`（BCP-47 連字號）**;只在呼叫 translateGemma 邊界轉其底線式 `zh_TW`。
5. **第一個 dogfood Project = 靜力學課程**(走最成熟的 `exam_pdf` track 最快驗證整條鏈);
   自動控制當第二個。兩門課素材都在 autoSolver 下。

---

## 6. 目標架構（分層）

```
[ 統一 Web Shell / UI ]   單一入口 · 共用 auth · 路由各模組
            │
[ 來源攝取 ]   PDF · repo · 文件 · URL · YouTube
            │
[ ★ Project / Notebook 核心（autoSolver server/ 升格） ]
   Source Store │ RAG 接地+引用(Phase 2) │ Content Library │ Job 編排
            │
[ 產製階段 = 三服務各一站 ]
   translateGemma(在地化) │ infoCard(圖卡/簡報) │ autoSolver(旁白影片/字幕)
            │
[ ★ 人工 Review Gate ]   逐段審查公式/數字 · 學術誠信 · NotebookLM 沒有的差異化
            │
[ 發布 ]   YouTube · PPTX/PDF · 圖片 · SRT
```

---

## 7. Project / Notebook 資料模型（建在既有 JobRecord 之上）

```jsonc
{
  "project_id": "course_statics_2026",
  "title": "靜力學 2026",
  "target_languages": ["zh-TW", "en-US"],          // canonical = BCP-47 連字號
  "sources": [
    { "source_id": "src_ch3", "type": "exam_pdf|slides_pdf|repo|document|url|youtube",
      "path_or_url": "...", "lang": "zh-TW", "indexed": false }   // indexed = Phase 2 RAG
  ],
  "jobs": [ "<autoSolver JobRecord.id>" ],          // 直接沿用既有 JobStore，不重造
  "artifacts": [
    { "artifact_id": "art_ch3_deck", "kind": "infographic|deck|video|srt|image",
      "produced_by": "infoCard|autoSolver|translateGemma",
      "state": "draft|awaiting_review|approved|published",   // 沿 JobState 語意
      "lang": "zh-TW", "citations": ["src_ch3#p12"],          // citations = Phase 2
      "links": { "youtube": null, "file": "..." } }
  ]
}
```

---

## 8. 分階段（A→B 漸進，不走全重寫）

- **Phase 1｜鬆耦合 + Project 薄層**：定義 `Project` schema + 薄 API;autoSolver JobStore 加
  `project_id`;統一 Shell 入口;跨服務呼叫約定(infoCard 簡報 → autoSolver 旁白)。
  破冰 PR 建議:共用 `translate()` helper(Gemini)+ autoSolver 退 Ollama(最小、最獨立)。
- **Phase 2｜RAG 接地核心**：Source Store 切塊+向量化;帶 citation 接地問答;接地餵產製。
- **Phase 3｜多語言貫穿 + 發布收斂**：Project 設目標語言一鍵在地化;多語 TTS/SRT;YT 多語軌。
- **Phase 4｜定位/打磨/對外**：課程專案範本化;研究生試用;成本面板。

---

## 9. 給 ultraplan 的明確任務

請產出:

1. **新整合 repo 的骨架方案**(目錄結構、核心服務、與三個既有 repo 的呼叫邊界/協定)。
2. **Phase 1 的 PR 級拆解**:每個 PR 的範圍、要改/新增哪些檔(含三個既有 repo 內的改動點)、
   驗收條件、相依順序。沿用 autoSolver 既有的 `PR-x` 命名風格。
3. **破冰 PR 的逐步實作計畫**(共用 `translate()` helper + autoSolver 退 Ollama)。
4. **風險與回頭點**(跨語言邊界、語言碼轉換、infoCard write-back、Project 與 JobStore 對齊)。

### 必守硬規則（沿 autoSolver CLAUDE.md，不可妥協）

- **AI 產出數值未經人工 review 不得當最終答案**;`exam_pdf` 強制 `require_review=True`,
  停在 `awaiting_review`。學術誠信底線。
- **不要自動 `git commit`**;變更等劉老師明確確認。
- **動 server / runner / schemas 要跑 `pytest tests/`**(autoSolver 有 257 tests 護網)。
- **字型路徑不寫死**,用 `CLAUDE_FONT_PATH` 等環境變數。
- **設定/路徑常數集中 `core/config.py`**,不在各模組各自定義。
- **Schema dispatch 用 type guard**,不要硬寫 `if "problems" in deck`。
- 溝通:直接、精簡、繁體中文;架構決策先列選項 + trade-off。

---

## 10. 第一個 dogfood Project 的素材（已盤點，2026-06-04）

> 本檔的權威複本已移到整合資料夾 `D:\Project_CodingSimulation\PersonalHelper\eduStudio\`。

第一個 Project = **114-02 靜力學期中考**，素材都在本 repo（autoSolver）底下:

| 用途 | 檔案 | track | 備註 |
|---|---|---|---|
| **建議起點（最快）** | `exams/114-02靜力學期中考.json` | exam_pdf（已解析） | 已是 v1 schema、7 題、含解題步驟,可跳過 Gemini 讀題 |
| 備選已解析 | `exams/114-02靜力學期中考2.json` | exam_pdf（已解析） | 7 題，分基礎/中等/進階 |
| 原始考卷 | `pdfs/114-02靜力學期中考.pdf`（≈276 KB） | exam_pdf | 走完整 Gemini 讀題流程 |
| 考卷分段 | `pdfs/114-02_靜力學期中考題_試題卷_1-3.pdf`、`_5-7.pdf` | exam_pdf | 分段測試 |
| 教學簡報 | `pdfs/靜力wk10-wk12第四章.pdf`（≈2 MB） | slides_pdf | 第四章三週講義 |

第二個 Project = 自動控制:`pdfs/1150420-自動控制_期中考試卷1.pdf`、
`pdfs/第八章_PID控制器設計.pdf`、`pdfs/Chap08-PID控制器設計-合併版.pdf`。
