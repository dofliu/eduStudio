# ROADMAP — 三專案整合：教學內容工作站

> 草案 v0.1（2026-06-04）。把 infoCard / autoSolver / translateGemma 收斂成一個
> 「給要在 YouTube 上課的老師用的 NotebookLM+」。本檔只談整合層,各專案內部 roadmap
> 仍各自維護。

---

## 0. 定位（先釘死,避免做成另一個 NotebookLM）

- **不打** 通用 notebook 層(跟 Google 正面對撞會輸)。
- **護城河 = 會發布 + 可審查 + 多語言 + 教學特化**：
  - YouTube 上傳通道(autoSolver 已有)
  - 人工 review gate(autoSolver 硬規則 #1,NotebookLM 不給你改公式/數字)
  - 多語言在地化(translateGemma)
  - 黑板逐題解題、課程簡報講解(NotebookLM 沒有的教學產製物)
- 一句話:**「從任何來源 → 接地、可審查、多語言的教學產製物 → 發布到 YouTube」**。

---

## 1. 現況盤點（Phase 0）

| 專案 | 棧 | 部署 | 角色（整合後） |
|---|---|---|---|
| infoCard | React19 + Node/Express + Gemini | Cloud Run（輕量 SaaS） | 產製站：圖卡 / 簡報 / 圖片 |
| autoSolver | Python FastAPI + FFmpeg + F5-TTS | 本機 RTX 4080（重度渲染） | 產製站：旁白影片 / 字幕 / YT 上傳 + review gate |
| translateGemma | 本機 Gemma 模型 | 本機 | 前處理站：多語言在地化 |

**核心障礙：棧不一致**（輕量雲端 vs GPU 重渲染 vs 本機推理）。
→ 結論:**不做 monolith 重寫**。三個維持獨立服務,只長出一層共用的「Project/Notebook 核心」把它們串成流水線。

**互補流水線**（整合的最強論點,三個剛好各是一站）：

```
來源 →（translateGemma 在地化）→（RAG/notebook 接地）
     → infoCard 產簡報/圖卡 → autoSolver 旁白+字幕+上 YT
```

> **盤點後的關鍵發現（詳見 [DESIGN_SPEC.md](DESIGN_SPEC.md)）**：`autoSolver/server/`
> 已經是「Project 核心」的 80% 雛形(完整 Job 狀態機 + review gate + artifacts +
> Library + 257 tests),而且三者翻譯底層**今天已經是同一個 Ollama `translategemma` 模型**。
> → 真正要「新建」的只有 **RAG 接地層** 與 **薄 Project/Shell 層**,其餘都是整合或局部改。

---

## 1.5 兩個決策（含 trade-off 表）

### 決策 A — 核心層用 Python 還是 Node

| 維度 | Python (FastAPI) | Node/TS (Express) |
|---|---|---|
| 與現有專案契合 | autoSolver + translateGemma 都是（2/3） | 只有 infoCard（1/3） |
| RAG / 向量生態 | ✅ 主場（BM25、faiss、rerank、PyMuPDF） | ⚠️ 薄，常要回呼 Python |
| 既有 Job 核心 | ✅ autoSolver JobStore 直接升格 | ❌ 要重造 |
| 你的熟悉度 | ✅ 熟 | ⚠️ 逐漸熟 |
| 與 infoCard 前端整合 | ⚠️ 跨語言 HTTP | ✅ 同棧型別共用 |
| 研究生接手 (RAG) | ✅ 本來就 Python | ⚠️ 要切換 |

**結論：Python。** 核心=Source Store+RAG+Job 編排,全是後端重活,且 autoSolver JobStore
已是現成基底；infoCard 維持 Node 當前端消費者,跨 HTTP/MCP 即可。

### 決策 B — 整合 vs 重來（三條，不是二選一）

| | A 純整合 | **B 文件化整合（strangler）** | C 全部重來 |
|---|---|---|---|
| 做法 | 三專案各活，加膠水 | **新核心薄層 + 三專案當服務掛上** | 以 Project 為中心重寫一切 |
| 開發成本 | 低 | **中** | 很高（數月+） |
| 保留既有價值 | 全保留 | **全保留** | 幾乎丟光（257 tests、YT、版型引擎） |
| 架構乾淨度 | 低 | **高** | 最高 |
| 風險 | 低 | **中** | 高（重寫常做不完） |
| 適合 | 趕快見效 | **solo + 2 研究生的你** | 有團隊、舊碼是負債 |

**結論：走 B。** 盤點證實核心已存在於 autoSolver,砍掉重來=把成果燒掉。
逐模組判斷見下表。

### 逐模組「整合 / 局部重寫 / 新建」

| 模組 | 判斷 | 理由 |
|---|---|---|
| Job 核心 / 狀態機 / review gate | **整合（升格核心）** | autoSolver 已成熟 |
| 影片 pipeline / TTS / 字幕 / YT | **整合** | 護城河，難重做 |
| 圖卡 / 簡報 / 漫畫（前端） | **整合** | 版型引擎是資產 |
| infoCard 成品儲存（IndexedDB） | **局部重寫** | 改成回寫核心 Project |
| 翻譯 / 配音 | **整合＋砍重複** | 兩處呼叫同一 Ollama 模型 |
| RAG / 接地 / citation | **新建** | 三者皆無，唯一從零 |
| 統一 Shell / Project API | **新建（薄層）** | JobStore 加 project_id + 入口 |

---

## 2. 分階段（A → B 漸進,不走 C 重寫）

### Phase 1 — 鬆耦合套件 + 統一 Project 資料模型（成本：低）

**目標**：三個服務還是各活各的,但有共同的「Project」概念與單一入口。先拿到「一套工具」的體感,不碰 RAG。

**最值得先做的接縫**：統一 infoCard 的 IndexedDB content library 與 autoSolver 的 JobStore,變成一個 `Project` 容器。

- **PR-U1a**　定義 `Project` schema（見 §4）+ 一個薄的 Project API（建立/讀取/列出 project,掛 sources 與 artifacts）。
- **PR-U1b**　autoSolver JobStore 的 job 改成掛在 `project_id` 下；infoCard content library 同步用 `project_id` 標記。
- **PR-U1c**　統一 Web Shell：單一 landing + 共用 auth,左側切 infoCard / autoSolver 模組,共用 Project 清單(Library)。
- **PR-U1d**　跨服務呼叫約定（infoCard 產出的簡報 PPTX/JSON → autoSolver 當 slides 來源）。先用檔案/HTTP 交換,不上 queue。

**驗收**：在同一個 Project 下,上傳一份來源 → infoCard 出簡報 → 一鍵把該簡報丟給 autoSolver 出旁白影片。
**風險**：兩邊資料模型對齊成本;先以 `Project` 為共同 key,不強求 schema 完全一致。

---

### Phase 2 — RAG / Notebook 接地核心（成本：中高，這才是「產品」）

**目標**：補上 NotebookLM 的心臟——持久多來源知識容器 + 接地問答 + 可回溯引用。用你現成的 RAG 能量(`retrieval-helper`、Kiwi/Christian)。

- **PR-U2a**　Source Store：來源切塊 + 向量化(BM25 + 語意,沿用 retrieval-helper)。
- **PR-U2b**　Grounded QA：對 Project 內來源問答,回答帶 citation（指回原文段落）。
- **PR-U2c**　**接地餵產製**：infoCard 大綱 / autoSolver deck 內容改成「先檢索 → 帶來源生成」,降低幻覺,且每個 bullet 可追溯來源。
- **PR-U2d**　Citation 在 review gate 顯示：審查時看得到「這個數字來自哪一頁」。

**驗收**：問 Project「第 3 章重點」→ 得到帶頁碼引用的答案 → 同一接地內容直接生成簡報草稿。
**風險**：接地層若做不穩會拖累兩個產製站;先在 `document`/`repo` 來源試,`exam_pdf` 維持強制 review。

---

### Phase 3 — 多語言貫穿 + 發布通道收斂（成本：中）

**目標**：translateGemma 從獨立工具變成貫穿整條 pipeline 的一層。

- **PR-U3a**　在 Project 設「目標語言」；產製物（圖卡文字 / 簡報 / 旁白稿 / SRT）一鍵在地化。
- **PR-U3b**　多語言 TTS + 多語言 SRT（autoSolver 旁白與字幕走 translateGemma 譯文）。
- **PR-U3c**　發布通道收斂：YouTube 上傳支援多語言標題/描述/字幕軌;PPTX/PDF/圖片匯出統一從 Project 出。

**驗收**：一份中文來源 → 產出中英雙語簡報 + 雙字幕影片 → 同一 Project 一鍵上 YT。

---

### Phase 4 — 定位、打磨、對外（成本：中）

- **PR-U4a**　範本化「課程專案」工作流（一門課 = 一個 Project,多章節）。
- **PR-U4b**　給研究生/系上試用,收斂 UI;考慮整進 IAE 系課程網站 / YouTube 頻道。
- **PR-U4c**　成本面板:Imagen / TTS / Gemini 呼叫數彙整到 Project 層(infoCard 已有 costCalculator,擴成全站)。

---

## 3. 為什麼是 A→B 不是 C

- **C（統一棧重寫）**：棧落差太大、脆弱、成本高 → 否決。
- **A（鬆耦合）**：低成本先拿體感,但還不是 NotebookLM。
- **B（共用核心）**：補 RAG 才真正成為「NotebookLM+」。
- 路線 = 先 A 把接縫接好（Project 資料模型）→ 再 B 長出接地層。

---

## 4. Project / Notebook 資料模型（草案）

```json
{
  "project_id": "course_mechanics_2026",
  "title": "材料力學 2026",
  "target_languages": ["zh-TW", "en"],
  "sources": [
    {
      "source_id": "src_ch3_pdf",
      "type": "exam_pdf | slides_pdf | repo | document | url | youtube",
      "path_or_url": "...",
      "meta": { "primary_language": "zh-TW" },
      "indexed": true
    }
  ],
  "artifacts": [
    {
      "artifact_id": "art_ch3_deck",
      "kind": "infographic | deck | video | srt | image",
      "produced_by": "infoCard | autoSolver",
      "status": "draft | awaiting_review | approved | published",
      "lang": "zh-TW",
      "citations": ["src_ch3_pdf#p12"],
      "links": { "youtube": null, "file": "..." }
    }
  ]
}
```

**設計重點**

- `Project` 是唯一共同 key,三服務都掛在它底下（合一 infoCard IndexedDB library 與 autoSolver JobStore 的接縫）。
- `artifacts[].status` 沿用 autoSolver 的 review 流：`exam_pdf` 來的強制 `awaiting_review`。
- `artifacts[].citations` 是 Phase 2 接地層的回溯欄位。
- `target_languages` 驅動 Phase 3 的多語言貫穿。

---

## 5. 開放問題（待 Dof 拍板）

1. **核心層放哪個棧？** Python（靠 autoSolver/RAG）還是 Node（靠 infoCard）？建議 Python 起 Project/RAG 服務,infoCard 當前端消費。
2. **本機 vs 雲端邊界**：GPU 渲染與 Gemma 推理留本機,Project/RAG/Shell 上雲還是全本機？
3. **YouTube 來源攝取**要不要進 Source（NotebookLM 有）？yt-search skill 已能抓 metadata。
4. **先做哪一個 Project 試水**：建議拿一門你正在開的課當 dogfood。
