---
name: pptx-jliu-style
description: 依照劉老師的個人簡報風格製作課程教學投影片。當使用者說「幫我做簡報」、「依我的風格製作」、「做課程投影片」、「依樣板製作」、「章節簡報」時觸發。支援十種主題風格:Forest（深綠教學風）、Navy（深藍科技風）、Frieren（芙莉蓮幻境風）、Naruto（火影忍者熱血風）、Journal（米白墨綠期刊風）、dof-editorial（雜誌編輯暖色風）、dof-podium（講壇TED冷灰風）、dof-notebook（札記讀書會霧暖風）、dof-shinobi（忍者熱血深夜墨風）、dof-elven（魔法幻境月光紫風），可依課程類型或個人喜好切換。一律使用 pptxgenjs 產出格式正確的 .pptx 檔案。
---

# pptx-jliu-style

依照劉老師的個人風格,製作格式正確、視覺一致的課程教學投影片。本 skill 採**動態載入**架構——主索引只描述「何時讀哪個檔」,實際規格分散在 Project Knowledge,依任務需求逐步載入,避免一次性把全部規格吃進 context。

---

## 🗺️ 載入策略(讀我!)

**不要一次讀所有 references。**每次製作簡報,依以下順序動態載入:

| 觸發條件 | 必讀檔案 | 何時讀 |
|---|---|---|
| 開始任何 pptx 任務 | `/mnt/skills/public/pptx/pptxgenjs.md` | 第一步,確認 pptxgenjs API |
| **任何主題，第一頁前** | `/mnt/project/slide-master.md` | **母片定義前必讀，包含色彩表與確認問題** |
| 開始任何頁面 | `/mnt/project/font-sizes.md` | 一次性,牢記字體鐵則 |
| 用到 fill 屬性背景 | `/mnt/project/object-minimization.md` | 第一頁前讀一次 |
| 用到 Consolas / 程式碼 | `/mnt/project/consolas-indent.md` | 寫到程式碼頁時 |
| 選定主題：journal | `/mnt/project/theme-journal.md` | 選定後立刻讀 |
| 選定主題：dof-editorial | `/mnt/project/dof-editorial.md` | 選定後立刻讀 |
| 選定主題：dof-podium | `/mnt/project/dof-podium.md` | 選定後立刻讀 |
| 選定主題：dof-notebook | `/mnt/project/dof-notebook.md` | 選定後立刻讀 |
| 選定主題：dof-shinobi | `/mnt/project/dof-shinobi.md` | 選定後立刻讀 |
| 選定主題：dof-elven | `/mnt/project/dof-elven.md` | 選定後立刻讀 |
| 選定主題：forest | `/mnt/project/theme-forest.md` | 選定後立刻讀 |
| 選定主題：navy | `/mnt/project/theme-navy.md` | 選定後立刻讀 |
| 頁型：封面 | `/mnt/project/pagetype-cover.md` | 做封面頁時 |
| 頁型：學習目標 | `/mnt/project/pagetype-objectives.md` | 做目標頁時 |
| 頁型：章節地圖 | `/mnt/project/pagetype-roadmap.md` | 做地圖頁時 |
| 頁型：節分隔 | `/mnt/project/pagetype-section-divider.md` | 做分隔頁時 |
| 頁型：一般內容 | `/mnt/project/pagetype-content.md` | 做內容頁時 |
| 頁型：程式碼 | `/mnt/project/pagetype-code.md` | 做程式碼頁時 |
| 頁型：練習題 | `/mnt/project/pagetype-exercise.md` | 做練習題頁時 |
| 頁型：章節小結 | `/mnt/project/pagetype-summary.md` | 做小結頁時 |
| 頁型：END 頁 | `/mnt/project/pagetype-end-page.md` | 做 END 頁時 |
| 用 LaTeX 公式 | `/mnt/project/math-typography.md` | 寫公式頁時 |

**判斷規則**：當下用得到就讀，用不到就跳過。一個任務通常只讀 4–6 個檔，不是全部。

---

## ⚠️ 三條鐵則(每次都遵守)

1. **物件最小化**（策略 B）：每個視覺元素用單一 Text+fill 完成，不堆疊 Shape 背景 → 詳見 `/mnt/project/object-minimization.md`
2. **字體大小鐵則**：內文最小 18pt（Journal/dof 系列 20pt），9–11pt 僅限頁腳/頁碼 → 詳見 `/mnt/project/font-sizes.md`
3. **Consolas 縮排陷阱**：等寬字體忽略 margin，須用 `x` 位置偏移 → 詳見 `/mnt/project/consolas-indent.md`

---

## 風格路由表

### 原有風格（插畫 / 教學類）

| 主題代碼 | 適用情境 | 規格檔 |
|---|---|---|
| `forest` | 程式設計、基礎課程、工程概論 | `/mnt/project/theme-forest.md` |
| `navy` | AI/RAG/技術進階課程、研討會 | `/mnt/project/theme-navy.md` |
| `frieren` | 理論探索、學術研究、文學性主題（插畫感 SVG） | 暫無規格檔，依 slide-master.md 色彩表手動實作 |
| `naruto` | 實作專題、競賽激勵、團隊合作（漫畫感 SVG） | 暫無規格檔，依 slide-master.md 色彩表手動實作 |
| `journal` | 學術課程、研究所、書冊式教學、正式出版風 | `/mnt/project/theme-journal.md` |

### DofLab 個人風格（全襯線極簡系列 v1）

| 主題代碼 | 適用情境 | 規格檔 |
|---|---|---|
| `dof-editorial` | 業界演講、對外分享、Demo Day、招生說明 | `/mnt/project/dof-editorial.md` |
| `dof-podium` | 學術 Conference、Keynote、研究發表 | `/mnt/project/dof-podium.md` |
| `dof-notebook` | 讀書會、Journal Club、內部輕量分享、工作筆記 | `/mnt/project/dof-notebook.md` |
| `dof-shinobi` | 黑客松、動員會、競賽出陣前演講 | `/mnt/project/dof-shinobi.md` |
| `dof-elven` | 哲學講座、認知科學、文學主題、通識課程 | `/mnt/project/dof-elven.md` |

### DofLab 衝擊風格（v2）

| 主題代碼 | 適用情境 | 規格檔 |
|---|---|---|
| `dof-zine` | 年度回顧、宣言式 talk | `/mnt/project/dof-zine.md` |
| `dof-arcade` | 黑客松開幕、技術 demo | `/mnt/project/dof-arcade.md` |
| `dof-risograph` | 工作坊、跨界活動 | `/mnt/project/dof-risograph.md` |
| `dof-supergraphic` | 品牌簡介、企業合作 | `/mnt/project/dof-supergraphic.md` |
| `dof-brutalist` | 觀點 talk、批判演講 | `/mnt/project/dof-brutalist.md` |

### 預設選擇邏輯（使用者未指定時）

| 場景描述 | 建議主題 |
|---|---|
| 對外正式演講 / Demo / 招生 | `dof-editorial` |
| Conference / Keynote / 研究發表 | `dof-podium` |
| 讀書會 / Journal Club / 內部分享 | `dof-notebook` |
| 黑客松 / 動員會 / 競賽出陣 | `dof-shinobi` |
| 哲學 / 認知科學 / 文學講座 / 通識 | `dof-elven` |
| 課程教學（程式設計 / 基礎工程） | `forest` |
| 課程教學（AI / 技術進階） | `navy` |
| 學術研究所 / 期刊感 / 書卷味教學 | `journal` |
| 漫畫奇幻風（需明確指定） | `frieren` / `naruto` |

---

## 頁型路由表

| 頁型 | 使用時機 | 規格檔 |
|---|---|---|
| `cover` | 章節封面(每章第一頁) | `/mnt/project/pagetype-cover.md` |
| `objectives` | 學習目標(動詞標籤列表) | `/mnt/project/pagetype-objectives.md` |
| `roadmap` | 學習地圖(各節卡片) | `/mnt/project/pagetype-roadmap.md` |
| `section-divider` | 節分隔頁(§ N 開頭) | `/mnt/project/pagetype-section-divider.md` |
| `content` | 一般內容頁(含版型庫) | `/mnt/project/pagetype-content.md` |
| `code` | 程式碼頁 | `/mnt/project/pagetype-code.md` |
| `exercise` | 練習題頁 / 參考解答頁 | `/mnt/project/pagetype-exercise.md` |
| `summary` | 章節小結 / 整章總結 | `/mnt/project/pagetype-summary.md` |
| `end-page` | END 頁（章末引言收束） | `/mnt/project/pagetype-end-page.md` |

---

## 製作流程

### Step 1 · 確認輸入
- 章節主題、各節標題、內容大綱（或講義/PDF，用 `python -m markitdown` 解析）
- 確認風格代碼
- 若選 Journal / dof 系列 → 提醒使用者確認 Noto Serif TC 字體是否安裝

### Step 1.5 · 母片內容確認（必做，不可跳過）

讀取 `/mnt/project/slide-master.md` 後，向使用者詢問以下兩個問題：

**問題 A：Footer 文字**
> 母片 footer 預設顯示：「劉瑞弘 · 智慧自動化工程系 · 國立勤益科技大學 · DofLab」
> 這次要使用預設，還是需要修改？

**問題 B：額外母片元素**
> 是否有其他固定要出現在每頁的元素？（例如計畫編號、機構圖片、特定日期）

處理原則：
- 使用者說「預設」或「不用改」→ 直接用預設值
- 使用者提供新文字 → 記錄並套入母片 `[FOOTER_TEXT]`

### Step 2 · 規劃投影片清單
列出每張投影片：**頁碼、頁型、標題、版型**。先給使用者確認架構再進入 Step 3。

### Step 3 · 動態載入 references
依本檔「載入策略」表逐步讀規格檔。**不要一次讀完所有檔**。

### Step 4 · 定義母片，再寫投影片內容

**先定義母片（`defineSlideMaster`），再逐頁寫內容。**

母片規則：
- 所有主題都必須用 `defineSlideMaster()` 實作 — 詳見 `/mnt/project/slide-master.md`
- **不要**寫 `addMasterSlide()` helper 函式在每頁重複放固定元素
- 每頁只需：`pres.addSlide({ masterName: "..." })` + 填入 `{ placeholder: "chapter" }`
- 嚴格依規格，不自行發明顏色或字體

### Step 5 · 執行並 QA
```bash
node slides.js
python -m markitdown output.pptx               # 文字內容確認

# 字體大小檢查（必做）
grep -n "fontSize: 9\b\|fontSize: 1[0-5]\b" slides.js

# 轉 PDF 視覺確認
python /mnt/skills/public/pptx/scripts/office/soffice.py --headless --convert-to pdf output.pptx
pdftoppm -jpeg -r 120 output.pdf slide
```
逐張檢視，**特別檢查內文是否 ≥ 18pt（Journal/dof 系列 ≥ 20pt）**。

### Step 6 · 交付
輸出至 `/mnt/user-data/outputs/`，使用 `present_files` 提供下載。

---

## 基本格式參數（不論風格都套用）

- 投影片尺寸：**寬 13.33 吋 × 高 7.5 吋**（16:9 標準）
- 所有文字尺寸用 **pt**，位置用 **吋**
- 字體：
  - Forest/Navy/Frieren/Naruto → **Microsoft JhengHei**（微軟正黑體）
  - Journal / **dof 系列 v1** → **Noto Serif TC**（中文）+ **EB Garamond**（英文）
  - dof 系列 v2 → 各主題規格檔指定字體
  - 程式碼一律 **Consolas**
- 每頁都要有視覺元素（色塊、圖示、圖表），不做純文字頁
  - **Journal / dof 系列例外**：可只靠字距、留白、印刷符號（§/—/·/→/◇）建立視覺
- **dof-shinobi** 是深色底（`#16110A`），其他所有風格都是淺色底
