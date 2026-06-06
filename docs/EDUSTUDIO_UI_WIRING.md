# eduStudio 統一介面 `/app` — UI 接線盤點

> 盤點日期：2026-06-06　·　對象：`web/eduapp`（源碼在 `infoCard/edustudio/app.jsx`）
> 用途：列出統一介面 `/app` 每個控制項「接後端了沒」，當作補完的工作清單。

## 🔧 影片站完整化計畫（2026-06-06，劉老師 review 後）

劉老師實測發現兩個整合問題：(1) `/app` 與舊 `/ui`/`/studio` 並存、舊的更完整；
(2) 影片站只剩「解題」，原本的 考卷/簡報/repo/文件/網址 source type 不見了（被我硬塞進
「任務類型」框架，slides_pdf/repo/song 沒入口；source type 跑到 Project 匯入但生成沒接）。

**決議：一步步來，先把影片站做完整 + 進度狀態可恢復；介面可改（Claude Design 只是樣版）。**

- [x] **I1 影片站來源類型完整化**（2026-06-06, infoCard `4f6b228`）：source-type 為主，6 來源全列,
      file→/upload、url/path→/jobs,repo/document/url 可選 theme。影音工具維持獨立。
- [x] **I2 進度／狀態恢復**（2026-06-06, infoCard `b20983d`）：esJobProgress 從 stages 算進度+步驟標籤,
      有 active job 時每 4 秒輪詢,TaskCard 顯示進度條+步驟,重整不丟(JobStore 持久化)。
- [x] **I3 inline 詳情/log**（2026-06-06, infoCard `12d696b`）：TaskCard「詳情」展開 stages 徽章 +
      log tail（GET /jobs/{id}/log,running 每 4s 刷新),次要出口連舊編輯器。不跳舊 /ui。
      **已驗證**：repo path-create → pending→rendering（ingest:done, render:running）1s 內,進度即時。
- [x] **I4 旁白聲音選擇**（2026-06-06, infoCard `bdc7299`）：create panel 接 GET /voices(9 聲音含
      劉老師 F5 複製),選擇→POST /voices 設全域。實測 current=f5:teacher。
- [x] **I5 AI 提案片單(Proposals 對等)**（2026-06-06, infoCard `ef15001`）：ProposalsPanel 掃資料夾
      (scan-folder/async + 輪詢 scan-status)→ 列提案 → 核准建 job(/approve)/忽略(/ignore)。GET 實測通。
- [ ] **（後續）/app 對等剩餘**：逐章 section re-render、主題預覽。舊 /ui /studio 何時退場或標「進階」由劉老師定。
      **影片站核心已與 /ui 對等：6 來源 + 進度恢復 + inline 詳情 + 聲音 + 提案片單。**

job 模型參考：SourceType= exam_pdf/slides_pdf/repo/document/url/song；JobState= pending/
ingesting/awaiting_review/rendering/done/failed；JobRecord.stages[]=各階段 name+state。

---

## 背景：三套 UI 並存

合併後同一個 Python server（`http://127.0.0.1:8000`）同時掛三套前端：

| 路徑 | 是什麼 | 狀態 |
|------|--------|------|
| `/app` | **Claude Design 統一重設計**（4 工作站），目標主介面 | 薄殼：每站只接了「主生成動作」，多數選項/次要動作未接 |
| `/studio` | 原版 infoCard 全功能 UI（16 主題、密度、長寬比、自訂風格、逐區編輯…） | 完整可用，但 **client-side 直連 Gemini**，未走合併後端 |
| `/ui` | 原版 autoSolver 影片 UI（上傳/編輯/Library/YouTube） | 完整可用 |

**核心結論：後端能力大多齊備（生成/翻譯/配音/會議/學習/匯出端點都在），缺的是 `/app` 把它們 surface 出來的 UI 控制項。** 因此下列多數缺口是「純前端接線」，後端現成。

圖例：✅ 已接真後端　·　🟠 UI 在但沒接（死控制項）　·　🔴 連 UI 都沒有　·　⚙️ 後端現成

---

## 🎨 視覺站（VisualComposer）

| 控制項 | 現狀 | 後端端點 | 工作量 |
|--------|------|----------|--------|
| 模式切換（漫畫/海報/圖卡/簡報） | ✅ | `POST /api/generate` | — |
| 標題輸入 | ✅ | — | — |
| 生成 / 大綱預覽 / 微調 / 匯出 PPTX | ✅ | `/api/generate`,`/api/refine`,`/api/export/pptx` | — |
| **視覺風格選擇（16 主題）** | 🟠 寫死 `academic` | ⚙️ `/api/generate` 收 `style` | 小（前端加 select） |
| **數量/張數/格數** | 🟠 寫死（panels=4 / slideCount=10） | ⚙️ 收 `panels`/`slideCount` | 小 |
| **來源素材**（從 Project 講義/上傳/URL 擷取） | 🟠 假下拉 | ⚙️ `/api/generate` 收 `text`，Project 來源讀 `/projects/{id}/notebook` | 中 |
| **自訂風格 prompt** | 🔴 無 UI | ⚙️ 收 `customStylePrompt` | 小 |
| **密度 / 長寬比 / 字型** | 🔴 無 UI | ⚙️ 收 `density`/`aspectRatio`/`typography` | 小 |
| 結果「加入 Project / 存檔 / 分享」 | 🟠「重新生成」是死 Badge | ⚙️ `POST /projects/{id}/artifacts`、`/api/share` | 中 |
| 海報/圖卡 逐區 refine、區域選擇 | 🔴 無 | （infoCard 有，後端未移植 refine 圖卡） | 大 |

---

## 🎬 影片站（VideoStation）

| 控制項 | 現狀 | 後端端點 | 工作量 |
|--------|------|----------|--------|
| 任務列表（讀 jobs） | ✅ | `GET /jobs` | — |
| 建任務（上傳 PDF / URL） | ✅ | `POST /upload`,`POST /jobs` | — |
| review gate 審查 / 核准 | ✅ | `/jobs/{id}/draft`,`/approve` | — |
| **TaskCard「即時預覽」** | 🟠 死 | ⚙️ artifact_url 可開 | 小 |
| **TaskCard「發布」（approved）** | 🟠 死 | ⚙️ 走發布站 youtube 流程 | 小 |
| **TaskCard「重試 / 取消」** | 🟠 死 | ⚙️ 重 `POST /jobs`、`DELETE /jobs/{id}` | 小 |
| **任務篩選 tab（全部/待審/生成中）** | 🟠 onChange 空 | 純前端 | 小 |
| **translateGemma 配音（影片→多語配音）** | 🔴 站內無 UI | ⚙️ `POST /localization/dub` | 中 |
| **會議摘要（錄音→重點影片）** | 🔴 站內無 UI | ⚙️ `POST /localization/meeting/summarize` | 中 |
| **多語字幕生成** | 🔴 站內無 UI | ⚙️（job pipeline / dub 產 SRT） | 中 |
| review gate 逐段「編輯後存回」 | 🟠 編輯只在前端 state，未存回 | ⚙️ 需 server 端 deck patch 端點（待確認） | 中 |

---

## 📁 素材 · Project 站（ProjectStation）

| 控制項 | 現狀 | 後端端點 | 工作量 |
|--------|------|----------|--------|
| 讀取第一個 Project 的素材 + 成品庫 | ✅ | `GET /projects`,`/projects/{id}/notebook` | — |
| 成品庫篩選（全部/影片/視覺） | ✅ 前端篩選 | — | — |
| **拖曳匯入 / 匯入類型按鈕** | 🟠 死 | ⚙️ `POST /projects/{id}/sources`（檔案另需上傳） | 中 |
| **來源「⋯」選單（刪除/重命名/重索引）** | 🟠 死 | ⚙️ 需 source 刪改端點（待補） | 中 |
| **建立新 Project** | 🔴 無 UI | ⚙️ `POST /projects` | 小 |
| **多 Project 切換**（topbar 選單） | 🟠 只顯示第一個 | ⚙️ `GET /projects` 列全部 | 中 |
| 成品卡「在地化 / 發布」 | 🟠 localize 是前端 state | ⚙️ `/localization/*`、youtube | 中 |

---

## 📤 發布站（PublishStation）— 相對完整 ✅

| 控制項 | 現狀 | 後端端點 |
|--------|------|----------|
| 成品列表（跨 job 平鋪 mp4） | ✅ | `GET /library` |
| YouTube 上傳（meta→publish→輪詢） | ✅ | `/jobs/.../youtube_meta`,`/publish`,`/youtube_status` |
| 下載 MP4 / 字幕 | ✅ | `artifact_url` |
| 複製分享連結 | ✅ | — |
| 發布語言版本多選 | 🟠 UI 在，但只是視覺（未驅動多語上傳） | ⚙️ 待接多語 metadata | 中 |

---

## 🌐 一鍵在地化（LocalizeMenu）

| 控制項 | 現狀 | 後端端點 |
|--------|------|----------|
| 多語翻譯 | ✅ | `POST /localization/translate` |

## 📚 學習工具箱（Toolbox 抽屜）

| 控制項 | 現狀 | 後端端點 | 工作量 |
|--------|------|----------|--------|
| 單字卡 | 🟠 按鈕無 onClick | ⚙️ `POST /localization/learning/flashcards` | 中 |
| 寫作糾錯 | 🟠 死 | ⚙️ `POST /localization/learning/writing-correction` | 中 |
| 會話練習 | 🟠 死 | ⚙️ `POST /localization/learning/conversation` | 中 |
| 聽寫檢查 | 🔴 無卡 | ⚙️ `POST /localization/learning/dictation-check` | 中 |

## 💰 成本面板（CostPanel）

| 控制項 | 現狀 | 後端 |
|--------|------|------|
| 用量/預算/各站花費/近期紀錄 | 🟠 全 mock 假數字 | 🔴 **無用量統計後端**（需新做，或先標「示意」） |

## 🎛️ 其他

| 控制項 | 現狀 |
|--------|------|
| 介面風格切換（Aurora/Lumen/Carbon） | ✅ 即時切換（純前端主題） |
| 側欄收合 / 工作站導航 | ✅ |

---

## 補完優先序（建議）

1. **🌟 視覺站選項真化**（風格/張數/自訂 prompt/密度/長寬比）— 後端現成、純前端、最有感
2. **🌟 學習工具箱接線**（4 個學習端點都現成）
3. 影片站 TaskCard 次要動作（預覽/重試/取消/發布）— 後端現成
4. translateGemma 配音 / 會議摘要 進影片站 — 後端現成、需新 UI
5. Project 站寫入動作（建 Project / 匯入來源 / 多 Project 切換）
6. 成本面板真實用量統計 — 需先決定是否新做後端
7. 結果「加入 Project / 分享」串接

> 多數項目是「純前端接線」（後端 ⚙️ 已現成），風險低；真正需要新後端的是「成本用量統計」與「review gate 逐段存回 / source 刪改」少數幾項。
