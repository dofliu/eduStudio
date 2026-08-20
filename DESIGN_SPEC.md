# DESIGN_SPEC — 三專案整合設計規格

> 草案 v0.1（2026-06-04）。本檔是 [ROADMAP_UNIFIED.md](ROADMAP_UNIFIED.md) 的事實基礎:
> 把 autoSolver / infoCard / translateGemma 三個現有專案的**實際**結構、API 契約、
> 資料模型、重疊處盤點清楚,作為「整合 vs 局部重寫」逐模組決策的依據。
>
> 內容皆以 2026-06-04 當下 repo 實際程式碼為準(非構想)。標 `⚠️` 處為待 Dof 確認。

---

## 0. 一句話結論（讀完全文前先看）

**不要砍掉重來。** 盤點後發現:`autoSolver/server/` 已經是「Project 核心」的 80% 雛形
(完整 Job 狀態機 + review gate + artifacts + Library + 持久化),而且三者的底層基質
(Ollama `translategemma` 模型、edge-tts、PyMuPDF、FastAPI job 模式)已經高度重疊。
正確做法是**把 autoSolver 的 server/ 升格為共用核心**,infoCard 與 translateGemma
退為「來源/產製服務」掛上去——**新建的東西很少,重複的東西要砍**。

---

## 1. 三服務現況事實表

| | autoSolver | infoCard | translateGemma |
|---|---|---|---|
| 語言/框架 | Python · FastAPI (Track B) | TypeScript · React19 + Express | Python · FastAPI + Gradio |
| 進入點 | `server/main.py` (port 8000) | `server.ts` (port 8080) | `api.py` / `app.py` |
| AI 後端 | Gemini 2.5 (Vision+Text) | Gemini 3 系列 | **Ollama `translategemma`**（本機） |
| 儲存 | JobStore 磁碟持久化 (`jobs/`) | **IndexedDB（client 端）** + share | SQLite (`history.db`) |
| Job/非同步 | ✅ 成熟狀態機 + per-job log | ❌ 同步 generate | ✅ `/api/jobs` + BackgroundTasks |
| Review gate | ✅ `awaiting_review` + approve | ❌ | ❌ |
| MCP server | ❌（有 ideate） | `mcp-server.ts`（有） | ✅ `mcp_server.py`（14 tools，乾淨） |
| 成熟度 | 高（257 tests, CI） | 中高（前端豐富） | 中（功能多，服務化已起步） |
| 角色（整合後） | **核心 + 影片產製站** | 圖卡/簡報產製站（前端） | 來源在地化 + 配音服務 |

---

## 2. 服務契約（實際 API，非構想）

### 2.1 autoSolver — 核心 + 影片產製

**吃什麼**（`CreateJobRequest`，`server/schemas.py`）

```python
source_type: exam_pdf | slides_pdf | repo | document | url   # SourceType enum
source: { path?: str, url?: str }                            # JobSource
options: JobOptions   # 巨型選項：tts_provider, theme, hardsub, length_mode,
                      # cover/outro, palette_*, subtitle_*, aspect_ratio,
                      # talking_head, narration_style, persona, require_review ...
```

**狀態機**（`JobState`）

```
pending → ingesting →┬→ awaiting_review →approve→ rendering → done
                     └────────────────────────→ rendering        ↘ failed（任一階段）
```

**吐什麼**：`JobRecord`（含 `Artifact[]`：`kind = mp4|srt|json|png|other`）、`YoutubeUpload`。

**關鍵 REST 端點**（`server/routes/`，base `/api/jobs`）

| 端點 | 用途 |
|---|---|
| `POST /api/jobs` · `POST /uploads` | 建 job（JSON / 檔案上傳） |
| `GET /api/jobs` · `GET /{id}` | 列表 / 單筆 |
| `GET/PUT /{id}/draft` · `GET /{id}/outline` | 草稿審查/編輯（review gate） |
| `POST /{id}/approve` | 核准 → 進 rendering |
| `POST /{id}/sections/{sid}/render` | 單章重 render |
| `GET /{id}/artifacts/{name}` · `/figures` | 取產出物 |
| `GET /api/library` | 跨 job 成品庫 |
| `GET/POST /api/proposals` · `/scan-folder` | ideate 自動企劃 |
| `*/youtube_meta` · `/publish` · `/youtube_status` | YouTube 上傳通道 |
| `GET /api/voices` · `/themes` | 聲音 / 主題 |

### 2.2 infoCard — 圖卡/簡報產製（前端重）

**吃什麼**（`POST /api/generate`）

```json
{ "mode": "presentation|poster|comic", "text": "...", "style": "...",
  "slideCount": 10, "typography": "...", "density": "...",
  "imageModel": "...", "textModel": "..." }
```

**吐什麼**（`types.ts`）：`PresentationData` / `PresentationOutline`（兩階段大綱）/
`InfographicData` / `ComicData`。成品存 **client 端 IndexedDB**（`contentLibraryService`），
非伺服器持久化 → 整合時這是最大的資料模型落差(見 §4)。

其他端點：`POST /api/share`（7 天連結）、`GET /api/share/:id`、`GET /api/docs`（OpenAPI）。

### 2.3 translateGemma — 在地化 + 配音服務

已是**服務化**的：同時有 REST (`api.py`) 與 MCP (`mcp_server.py`, 14 tools)。

**REST**：`/api/translate/text|text/batch|image|pdf`、`/api/dub/video`、
`/api/jobs/video`、`/api/jobs/meeting-summary`、`/api/jobs/{id}`、`/api/learning/*`（單字卡/寫作糾錯/會話）。

**MCP tools**（最適合被核心呼叫）：`translate_text`、`translate_batch_text`、
`translate_pdf`、`translate_image`、`dub_video(burn_subtitles)`、`translate_with_learning` …

**契約細節**：語言碼用 `zh_TW` / `en_US`（底線式，見 `languages.py`）；
`dub_video` 吃 YouTube URL 或本地檔，可燒字幕。`batch` 支援 `glossary` + `style`（術語表/文風）。

---

## 3. 重疊 / 重複盤點（整合的真正價值在「砍重複」）

| 能力 | autoSolver | infoCard | translateGemma | 處置建議 |
|---|---|---|---|---|
| **翻譯後端** | `core/translate.py` → Ollama `translategemma` | — | 同一個 Ollama `translategemma` | **已定案（2026-06-04）**：text 翻譯改用雲端 Gemini API（用量小、成本可忽略），砍掉 Ollama 路徑 → 解除「全系統須本地」限制，且與既有 Gemini 雲端棧一致。詳見 §3.1。 |
| TTS | edge-tts + F5-TTS | — | edge-tts | 統一到一條 TTS 服務 |
| PDF→文字/圖 | PyMuPDF | （前端讀檔） | PyMuPDF | 收斂到核心的 ingest |
| YouTube | 上傳（publish.py） | — | 下載 + 配音（yt-dlp） | 一個「YT 進/出」模組 |
| 非同步 Job | ✅ JobStore | ❌ | ✅ /api/jobs | **以 autoSolver JobStore 為唯一真相** |
| 成品庫 | Library（伺服器） | IndexedDB（client） | history.db | 統一到 §5 Project（最大工作量） |

> **最重要的單一發現**：`autoSolver/core/translate.py` 的檔頭註明「劉老師 2026-06-04 決定
> 翻譯後端用本機 Ollama translategemma」——也就是說**三者的翻譯底層今天已經是同一個模型**,
> 只是包了兩層 service wrapper。整合不是要新接什麼,是要決定**誰呼叫誰、砍掉哪一層重複**。

### 3.1 翻譯後端定案（2026-06-04，推翻當天稍早的 Ollama 決定）

**決定：text 翻譯改用雲端 Gemini API。** 理由:

1. **解除部署限制**：本地 Ollama 把任何需要翻譯的元件釘在本地;改雲端後 core/RAG/Shell/infoCard
   都能上雲(autoSolver 因 FFmpeg/F5-TTS/GPU 仍本地,但那與翻譯無關)。
2. **與既有棧一致**：autoSolver(Gemini Vision 讀題)、infoCard(全 Gemini)本就在雲端,
   Ollama 本地翻譯是整個棧唯一的本地 AI 異類。
3. **隱私無新損失**：考卷內容早已送 Gemini Vision 讀題,翻譯改雲端不多洩漏。
4. **用量小**：narration/bullet 級文字,成本可忽略。

**落地做法**

- 建一個共用 `translate()` helper → 呼叫 Gemini（沿用既有 client/key，不另接 vendor）。
- autoSolver `core/translate.py` 退掉 Ollama,改呼叫該 helper。
- translateGemma **保留**(OCR 圖譯、STT→翻譯→TTS 配音、會議摘要、單字卡 SRS 仍有獨有價值);
  只把它的 **text 翻譯後端**切到 Gemini——其 `meeting-summary` 端點已有 `ai_backend=ollama|gemini`
  + `gemini_api_key` 切換,同 pattern 套到 translate 路徑即可。
- 觸發回頭點:若日後大量整份 PDF 批譯使量爆增,再評估 DeepL / 批次 API。

---

## 4. 整合接縫（落差最大的地方）

1. **成品庫資料模型落差（最大）**：infoCard 成品在 client IndexedDB,autoSolver 在伺服器
   JobStore,translateGemma 在 SQLite。建議:**以 autoSolver JobStore 為基底**擴 `project_id`,
   infoCard 改成把成品 POST 回核心。
   **定案（2026-06-04）：舊 IndexedDB 成品不遷移**,只有「之後新產生」的成品回寫核心 Project
   → infoCard 這塊改動更小(只加一條 write-back,不做資料遷移)。
2. **語言碼** → **定案：canonical = `zh-TW`（BCP-47 連字號）**。因為下游 YouTube captions /
   SRT / HTML `lang` 都吃 BCP-47;只在「呼叫 translateGemma」的邊界轉成它的底線式 `zh_TW`
   (`languages.py` 第三元素已是 BCP-47,轉換 trivial)。核心/儲存/infoCard 一律用連字號。
3. **同步 vs 非同步**：infoCard 是同步 generate,核心是 job 模式。infoCard 接核心時要包成 job。
4. **棧邊界**：核心(Python) ↔ infoCard(Node) 跨語言,走 HTTP/MCP；translateGemma 已有 MCP,
   最容易接。

---

## 5. Project / Notebook 資料模型（建在 autoSolver JobRecord 之上，非全新）

```jsonc
{
  "project_id": "course_mechanics_2026",
  "title": "材料力學 2026",
  "target_languages": ["zh-TW", "en-US"],   // canonical = BCP-47 連字號
  "sources": [
    { "source_id": "src_ch3", "type": "exam_pdf|slides_pdf|repo|document|url|youtube",
      "path_or_url": "...", "lang": "zh-TW", "indexed": false }   // indexed = Phase 2 RAG
  ],
  "jobs": [ "<autoSolver JobRecord.id>" ],     // 直接沿用既有 JobStore，不重造
  "artifacts": [
    { "artifact_id": "art_ch3_deck", "kind": "infographic|deck|video|srt|image",
      "produced_by": "infoCard|autoSolver|translateGemma",
      "state": "draft|awaiting_review|approved|published",  // 沿 JobState 語意
      "lang": "zh-TW", "citations": ["src_ch3#p12"],         // citations = Phase 2
      "links": { "youtube": null, "file": "..." } }
  ]
}
```

設計重點:`jobs[]` 直接引用既有 `JobRecord`；`artifacts[].state` 沿用 `awaiting_review`
語意(`exam_pdf` 仍強制 review)；`citations` 與 `indexed` 是 Phase 2 RAG 才填的欄位。

---

## 6. 逐模組「整合 / 局部重寫 / 新建」判斷

| 模組 | 現況 | 判斷 | 理由 |
|---|---|---|---|
| Job 核心 / 狀態機 / review gate | autoSolver server/ 成熟 | **整合（升格為核心）** | 257 tests，已是雛形，重寫純損失 |
| 影片 pipeline / TTS / 字幕 / YT 上傳 | autoSolver 成熟 | **整合** | 護城河，且難重做 |
| 圖卡 / 簡報 / 漫畫 產製 | infoCard 前端豐富 | **整合（前端保留）** | 版型引擎是資產 |
| infoCard 成品儲存（IndexedDB） | client 端 | **局部重寫（輕）** | 只加新成品 write-back，舊資料不遷移（§4.1） |
| 翻譯 / 配音 | 兩處重複呼叫同模型 | **整合 + 砍重複** | translateGemma 當唯一翻譯服務，autoSolver 退 wrapper⚠️ |
| RAG / 接地 / citation | **三者皆無** | **新建（greenfield）** | 唯一真正要從零做的一塊（Phase 2） |
| 統一 Shell / Project API | 不存在 | **新建（薄層）** | 在既有 JobStore 上加 project_id + 入口 |

→ 真正「新建」的只有 **RAG 接地層** 與 **薄 Project/Shell 層**;其餘都是整合或局部改。

---

## 7. 決策紀錄（2026-06-04 全數定案）

1. ~~翻譯重複怎麼收~~ → **已定案（見 §3.1）**：text 翻譯走雲端 Gemini API,砍 Ollama,
   解除全系統本地限制;translateGemma 保留獨有管線,其 text 翻譯亦切 Gemini backend。
2. ~~核心棧~~ → **定案：Python**（2/3 已是 + RAG 生態 + 既有 JobStore 直接升格）。
3. ~~infoCard 成品~~ → **定案：舊 IndexedDB 不遷移**,只新成品回寫核心(見 §4.1)。
4. ~~語言碼~~ → **定案：canonical `zh-TW`（BCP-47）**,translateGemma 邊界轉 `zh_TW`(見 §4.2)。
5. ~~先 dogfood 哪門課~~ → **定案:autoSolver 下的「靜力學」或「自動控制」課程**。
   建議第一個 Project 先用**靜力學**:走最成熟的 `exam_pdf` track、題目/公式結構乾淨,
   最快驗證整條鏈;自動控制(你的本行)當第二個。

---

## 附錄：盤點來源（repo 實際檔案）

- autoSolver：`server/main.py`、`server/schemas.py`、`server/routes/*.py`、`server/jobs.py`、`core/translate.py`
- infoCard：`server.ts`、`types.ts`、`mcp-server.ts`、`services/contentLibraryService.ts`
- translateGemma：`api.py`、`mcp_server.py`、`languages.py`
