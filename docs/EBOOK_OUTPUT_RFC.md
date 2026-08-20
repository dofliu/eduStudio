# RFC — 電子書輸出模組（EduForge）

> 來源:劉老師 2026-06-05 提的 issue（原稿 `D:\Dropbox\ISSUE_ebook_output.md`）落地進 repo。
> 狀態:**backlog / 待拍板**,尚未動 code。對應 TODO「✨ 新功能 backlog → 📚 EBOOK 軸」。
> 里程碑:v5.0｜估 3–4 週（兼職）。

---

## 1. 一句話

在不動現有 video pipeline 的前提下,新增**第二條輸出管道**:

```
教材來源 → AI 解析 →（既有）影片 + YouTube
                  ↳（新）電子書 EPUB（多版本內容）
                  ↳（新）練習題 / 測驗題（附解答）
                  ↳（新）教學簡報 .pptx（接 pptx-jliu-style）
```

核心概念 **EduForge**:一份工程教材,全套教學資源自動產出。

---

## 2. 設計原則

1. **不動現有 pipeline**:video 模組完全不碰,新功能平行開發。
2. **複用 adapter 層**:`core/adapters/document.py`、`url.py` 已能解析各來源。
3. **Job 狀態機延伸**:在現有 `source_type` 之上加 `output_type` 概念
   （`video | ebook | quiz | slides`）,各自有 artifacts。
4. **學術誠信延續**(硬規則 #1):AI 產出題目/內容仍可設 `require_review=True`,
   計算題人工確認數值才打包。
5. **Claude API 為主**:版本改寫與題目生成用 Claude（`claude-sonnet-4`),與現有 Gemini 分工。
   ⚠️ 與 INTEGRATION_KICKOFF §5「翻譯切 Gemini」決策不衝突(那是翻譯;這是改寫/出題,
   可獨立選型,待拍板)。

---

## 3. 範圍

### 納入
| 功能 | 說明 |
|------|------|
| 多版本內容改寫 | formal / summary / highschool / qa / story（各章平行生成） |
| EPUB 打包 | 多版本章節 → 單一 EPUB（封面 / 目錄 / metadata） |
| 練習題生成 | 每章依難度產計算題 / 概念題,附解答 |
| 測驗題生成 | 選擇 / 填充 / 簡答 → PDF 或 DOCX |
| 教學簡報輸出 | 章節骨架 → .pptx（接 pptx-jliu-style） |
| Web UI 整合 | React UI 加「📚 電子書」分頁,觸發/下載 |
| REST API 擴充 | `/jobs/{id}/ebook`、`/quiz`、`/slides` 端點 |

### 不納入（後續）
EPUB DRM、多語翻譯版、LMS（Moodle/Canvas）整合、行動閱讀器 APP。

---

## 4. 架構

### 新增模組（`core/`）
```
core/
├── versioner.py     ← Claude API 改寫多版本內容
├── epub_builder.py  ← 版本章節 → EPUB 打包（ebooklib）
├── quiz_gen.py      ← 練習題 + 測驗題生成
└── pptx_export.py   ← 呼叫 pptx-jliu-style 產簡報
```

### 新增路由
```
server/routes/ebook.py   ← /ebook、/quiz、/slides 端點
```

### Job 狀態機延伸
```
現有狀態機不動,新增 output_type 欄位:
  video   → artifacts/chN.mp4
  ebook   → artifacts/book.epub
  quiz    → artifacts/quiz.pdf
  slides  → artifacts/slides.pptx
```

---

## 5. 模組規格摘要

### 5.1 `core/versioner.py`
接收解析後章節（deck.json / outline.json）→ 呼叫 Claude 產各版本改寫。

```python
class Versioner:
    VERSIONS = {
        "formal":     "保留原文完整性,調整格式適合電子書閱讀",
        "summary":    "提煉核心,每章壓縮至 300 字以內",
        "highschool": "高中生程度,大量比喻/生活例子,避免微積分符號",
        "qa":         "改寫為 10 題問答,每題含詳解",
        "story":      "說故事方式呈現工程概念,加入情境與角色",
    }
    def run(self, section: dict, versions: list[str]) -> dict[str, str]: ...
```
Prompt 原則:標明「工程教育」領域 + 目標讀者;保留公式/圖表參照（佔位符 `[圖 1.1]`）;限輸出長度。

### 5.2 `core/epub_builder.py`
多版本章節 → 結構化 EPUB 3.0。每章內含 `ch01_formal/summary/highschool/qa/quiz.xhtml`。
metadata 可由呼叫端傳入（title/author/language/publisher/cover/versions_included）。依賴 `ebooklib`。

### 5.3 `core/quiz_gen.py`
每章分級題目:計算題 3 / 觀念題 2 / 選擇題 5 / 填充題 3（預設）。
輸出 JSON（id/type/difficulty/question/solution_steps/answer）。
**計算題預設 `require_review=True`**,人工確認數值才打包。

### 5.4 `core/pptx_export.py`
deck.json → .pptx,套 jliu 風格主題。每章:封面 / 學習目標 / 正文(每小節1–3張) / 重點 / 思考問題（取 quiz_gen 觀念題）。

### 5.5 REST API（`server/routes/ebook.py`）
```
GET  /jobs/{id}/ebook/status        POST /jobs/{id}/ebook/generate
GET  /jobs/{id}/ebook/download      POST /jobs/{id}/ebook/approve
POST /jobs/{id}/quiz/generate       GET  /jobs/{id}/quiz/download
POST /jobs/{id}/slides/generate     GET  /jobs/{id}/slides/download
```
generate body: `{versions, quiz_types, slides_theme, require_review}`。

### 5.6 React UI
新增 `EbookPage.tsx`（進度/版本預覽/下載）、`QuizReviewPage.tsx`（逐題 review,類比 `ExamProblemsPanel`）;`JobEditor` 加「📚 電子書輸出」tab。

---

## 6. 實作順序（建議）

- **Phase A（2 週）核心**:versioner / epub_builder / routes/ebook（基本 generate+download）
  / CLI 測試 `python scripts/submit_ebook.py document lecture.pdf`。
- **Phase B（1 週）題庫**:quiz_gen / QuizReviewPage / 題庫 PDF 輸出。
- **Phase C（1 週）簡報+UI**:pptx_export / EbookPage / JobEditor 整合 / 端到端（MD → EPUB+題庫+PPTX）。

---

## 7. 測試計畫
```
tests/test_versioner.py     各版本字數/語氣
tests/test_epub_builder.py  EPUB 格式驗證（epubcheck）
tests/test_quiz_gen.py      題型分布 / required 欄位
tests/test_ebook_routes.py  API integration
```

## 8. 依賴新增
```
ebooklib>=0.18
anthropic>=0.30   # Claude API（若尚未安裝）
```

---

## 9. 開放問題（待拍板）

1. **版本選擇 UI**:預設產哪幾個?讓使用者勾選?還是全跑完再選進 EPUB?
2. **封面圖**:AI 生成 / 佔位圖 / 使用者上傳?
3. **EPUB 版本**:EPUB 2(相容) vs EPUB 3(MathML 數學公式)?工程教科書建議 3。
4. **公式渲染**:LaTeX → MathML?或截圖貼圖?（repo 已有 `core/formula_render.py` mathtext→PNG 可複用）
5. **中文字型**:EPUB 需內嵌字型;建議打包思源宋體（OFL 授權）。
6. **改寫/出題模型**:Claude vs Gemini?(INTEGRATION_KICKOFF 翻譯已定 Gemini,但改寫/出題可獨立決。)

---

## 10. 參考
- `core/adapters/document.py` — 文件解析,可複用
- `core/deck.py` — deck.json schema,versioner 輸入格式
- `server/routes/jobs.py` — API 路由範本
- [ebooklib 文件](https://docs.sourcefabric.org/projects/ebooklib/en/latest/) / [epubcheck](https://github.com/w3c/epubcheck)

*原 issue 建立 2026-06-05｜概念:EduForge。*
