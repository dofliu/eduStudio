# [Feature] 電子書輸出模組（EduForge）

**Labels:** `enhancement` `new-feature` `phase-4`  
**Milestone:** v5.0  
**估計工作量：** 3–4 週（兼職開發）

---

## 背景與動機

`examReviewVideo` 目前的輸出管道是：

```
教材來源 → AI 解析 → 影片 + YouTube 上傳
```

本 issue 的目標是在不破壞現有架構的前提下，新增第二條輸出管道：

```
教材來源 → AI 解析 → 電子書（EPUB）
                  ↳ 多版本內容（正式版、摘要版、高中生版、Q&A 版…）
                  ↳ 練習題 / 測驗題（附解答）
                  ↳ 教學簡報（.pptx）
```

核心概念稱為 **EduForge**：**一份工程教材，全套教學資源自動產出**。

---

## 設計原則

1. **不動現有 pipeline**：video 相關模組完全不動，新功能平行開發
2. **複用現有 adapter 層**：`adapters/document.py`、`adapters/url.py` 等已可解析各種來源
3. **Job 狀態機延伸**：在現有 `source_type` 基礎上加入 `output_type` 概念
4. **學術誠信延續**：AI 產出題目 / 內容仍可設 `require_review=True`
5. **Claude API 為主**：版本改寫與題目生成使用 Claude（`claude-sonnet-4`），與現有 Gemini 分工

---

## 功能範圍（Scope）

### ✅ 納入本 issue

| 功能 | 說明 |
|------|------|
| 多版本內容改寫 | 正式版 / 摘要版 / 高中生版 / Q&A 版 / 故事版（各章節平行生成） |
| EPUB 打包 | 將多版本章節組合為單一 EPUB（含封面、目錄、metadata） |
| 練習題生成 | 每章依難度自動產計算題 / 概念題，附解答 |
| 測驗題生成 | 選擇題 / 填充題 / 簡答題，輸出 PDF 或 DOCX |
| 教學簡報輸出 | 章節骨架 → `.pptx`（接 `pptx-jliu-style` 風格系統） |
| Web UI 整合 | 現有 React UI 加入「📚 電子書」頁面，可觸發 / 下載產出物 |
| REST API 擴充 | 新增 `/jobs/{id}/ebook`、`/jobs/{id}/quiz`、`/jobs/{id}/slides` 端點 |

### ❌ 不納入本 issue（留給後續）

- EPUB DRM 加密
- 多語言翻譯版本
- 與 LMS（Moodle / Canvas）整合
- 行動 APP 閱讀器

---

## 架構設計

### 新增模組（`core/` 內）

```
core/
├── versioner.py        ← 新增：Claude API 改寫多版本內容
├── epub_builder.py     ← 新增：版本章節 → EPUB 打包
├── quiz_gen.py         ← 新增：練習題 + 測驗題生成
└── pptx_export.py      ← 新增：呼叫 pptx-jliu-style 產簡報
```

### 新增 API 路由（`server/routes/` 內）

```
server/routes/
└── ebook.py            ← 新增：/ebook、/quiz、/slides 端點
```

### Job 狀態機延伸

```
現有狀態機不動，新增 output_type 欄位：

job.output_type = ["video", "ebook", "quiz", "slides"]

每個 output_type 有各自的 artifacts：
  video   → artifacts/chN.mp4
  ebook   → artifacts/book.epub
  quiz    → artifacts/quiz.pdf
  slides  → artifacts/slides.pptx
```

---

## 詳細模組規格

### 1. `core/versioner.py`

**職責**：接收解析後的章節（`deck.json` 或 `outline.json`），呼叫 Claude API 產生各版本改寫。

```python
# 介面設計（草案）
class Versioner:
    VERSIONS = {
        "formal":    "保留原文完整性，調整格式使其適合電子書閱讀",
        "summary":   "提煉核心概念，每章壓縮至 300 字以內",
        "highschool":"以高中生程度改寫，大量使用比喻與生活例子，避免微積分符號",
        "qa":        "改寫為 10 題問答格式，每題含詳細解答",
        "story":     "以說故事方式呈現工程概念，加入情境與角色",
    }

    def run(self, section: dict, versions: list[str]) -> dict[str, str]:
        """
        輸入：單一章節內容 + 指定版本清單
        輸出：{version_name: rewritten_content}
        平行呼叫 Claude API，每個版本獨立 prompt
        """
```

**Prompt 設計原則**：
- System prompt 標明「工程教育」領域與目標讀者
- 保留公式、圖表參照（用佔位符 `[圖 1.1]`）
- 限制輸出長度（避免超出 EPUB 單章節建議字數）

---

### 2. `core/epub_builder.py`

**職責**：把多版本章節組合成結構化 EPUB 3.0。

**EPUB 內部結構設計**：

```
第一章：流體力學基礎
  ├─ ch01_formal.xhtml     正式版
  ├─ ch01_summary.xhtml    摘要版
  ├─ ch01_highschool.xhtml 高中生版
  ├─ ch01_qa.xhtml         Q&A 版
  └─ ch01_quiz.xhtml       練習題（含解答）

第二章：柏努利方程式
  ├─ ch02_formal.xhtml
  └─ ...
```

**EPUB metadata（可由呼叫端傳入）**：

```python
EpubMeta(
    title="自動控制 — 多版本學習電子書",
    author="劉瑞弘",
    language="zh-TW",
    publisher="勤益科大 DOF Lab",
    cover_image="cover.png",   # 可選，自動生成或指定
    versions_included=["formal", "summary", "highschool", "qa"],
)
```

**依賴套件**：`ebooklib`（`pip install ebooklib`）

---

### 3. `core/quiz_gen.py`

**職責**：針對每章內容生成分級題目。

**題目類型**：

| 類型 | 說明 | 預設每章數量 |
|------|------|-------------|
| 計算題 | 帶數值代入的工程計算 | 3 題 |
| 觀念題 | 簡答 / 申論 | 2 題 |
| 選擇題 | 4 選 1，附解析 | 5 題 |
| 填充題 | 公式 / 定義填空 | 3 題 |

**輸出格式**：

```json
{
  "chapter": "ch01",
  "problems": [
    {
      "id": "ch01_calc_01",
      "type": "calculation",
      "difficulty": "medium",
      "question": "...",
      "solution_steps": ["步驟1", "步驟2", "..."],
      "answer": "42.5 N/m²"
    }
  ]
}
```

**學術誠信**：計算題預設 `require_review=True`，人工確認數值正確後才打包進 EPUB / 輸出 PDF。

---

### 4. `core/pptx_export.py`

**職責**：從 `deck.json` / `outline.json` 產生教學用 `.pptx`，套用 jliu 風格主題。

**介面**：

```python
def export_pptx(
    deck: dict,
    theme: str = "navy",          # forest / navy / dof-dashboard / ...
    output_path: str = "slides.pptx",
    include_notes: bool = True,   # 備忘稿放 narration 內容
) -> str:
    ...
```

**投影片結構（每章）**：
1. 章節封面（章節標題 + 關鍵詞）
2. 學習目標（條列）
3. 正文投影片（每個小節 1–3 張）
4. 重點整理
5. 思考問題（取自 quiz_gen 的觀念題）

---

### 5. REST API 擴充

新增 `server/routes/ebook.py`，掛載至現有 `app`：

```
GET  /jobs/{id}/ebook/status          查詢電子書生成狀態
POST /jobs/{id}/ebook/generate        觸發電子書生成
GET  /jobs/{id}/ebook/download        下載 .epub

POST /jobs/{id}/quiz/generate         觸發題庫生成
GET  /jobs/{id}/quiz/download         下載題庫（PDF 或 DOCX）

POST /jobs/{id}/slides/generate       觸發簡報生成
GET  /jobs/{id}/slides/download       下載 .pptx

POST /jobs/{id}/ebook/approve         人工核准（含計算題 review）
```

**Request body 範例（generate）**：

```json
{
  "versions": ["formal", "summary", "highschool", "qa"],
  "quiz_types": ["calculation", "mcq"],
  "slides_theme": "navy",
  "require_review": true
}
```

---

### 6. React UI 擴充

在現有 `web/src/pages/` 新增：

- **`EbookPage.tsx`**：顯示生成進度、版本預覽、下載按鈕
- **`QuizReviewPage.tsx`**：逐題 review 介面（類比現有 `ExamProblemsPanel`）

現有 `JobEditor` 頁面新增「📚 電子書輸出」分頁 tab。

---

## 實作順序（建議）

### Phase A（2 週）— 核心能力
- [ ] `core/versioner.py`（Claude API 多版本改寫）
- [ ] `core/epub_builder.py`（EPUB 打包）
- [ ] `server/routes/ebook.py`（基本 generate / download）
- [ ] CLI 測試：`python scripts/submit_ebook.py document lecture.pdf`

### Phase B（1 週）— 題庫
- [ ] `core/quiz_gen.py`
- [ ] `QuizReviewPage.tsx`（review UI）
- [ ] 題庫 PDF 輸出（接現有 PDF 輸出工具）

### Phase C（1 週）— 簡報 + UI 整合
- [ ] `core/pptx_export.py`（接 pptx-jliu-style）
- [ ] `EbookPage.tsx`
- [ ] `JobEditor` 整合（新增 tab）
- [ ] 端對端測試（一份 MD → EPUB + 題庫 + PPTX）

---

## 測試計畫

```
tests/
├── test_versioner.py       單元測試：各版本輸出字數 / 語氣合理性
├── test_epub_builder.py    EPUB 格式驗證（epubcheck）
├── test_quiz_gen.py        題型分布、required 欄位存在
└── test_ebook_routes.py    API 端點 integration test
```

---

## 依賴套件新增

```
# requirements.txt 新增
ebooklib>=0.18
anthropic>=0.30        # Claude API（若尚未安裝）
```

---

## 參考資料

- 現有 `core/adapters/document.py` — 文件解析層，可直接複用
- 現有 `core/deck.py` — `deck.json` schema，versioner 的輸入格式
- 現有 `server/routes/jobs.py` — API 路由範本
- [`ebooklib` 文件](https://docs.sourcefabric.org/projects/ebooklib/en/latest/)
- [`epubcheck`](https://github.com/w3c/epubcheck) — EPUB 格式驗證工具

---

## 開放問題（待決定）

1. **版本選擇 UI**：預設產哪幾個版本？讓使用者勾選？還是全部跑完再讓他選要哪幾個進 EPUB？
2. **封面圖**：自動生成（用 AI 圖像）、佔位圖、還是讓使用者上傳？
3. **EPUB 版本**：EPUB 2（相容性高）vs EPUB 3（支援數學公式 MathML）？工程教科書建議 EPUB 3。
4. **公式渲染**：LaTeX → MathML 轉換？或截圖貼圖？
5. **中文字型**：EPUB 需內嵌字型才能在所有裝置正確顯示，建議打包思源宋體（OFL 授權）。

---

*Issue 建立日期：2026-06-05*  
*關聯專案：[examReviewVideo](https://github.com/dofliu/examReviewVideo)*  
*概念發想：EduForge — 一份工程教材，全套教學資源自動產出*
