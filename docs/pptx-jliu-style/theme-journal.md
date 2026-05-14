# journal · 學術期刊風

> DofLab 課程教學主力主題 · 米白墨綠 · 適用於學術課程、研究所、正式書卷感教學。
> 視覺氣質：**像翻開一本精裝教科書，沉穩、可信、印刷品味**。
> 與三條鐵則完全相容（物件最小化 / 字體 ≥20pt / Consolas 用 x 偏移）。

---

## 何時使用

| 場景 | 是否建議 |
|---|---|
| 研究所課程 / 控制系統 / 訊號處理 | ✅ 首選 |
| 學術性本科課程 | ✅ |
| 論文口試簡報 | ✅ |
| 業界演講 | ⚠️ 改用 dof-editorial |
| 黑客松 / 動員會 | ❌ |

---

## 色彩 token

| 用途 | Hex | pptxgenjs |
|---|---|---|
| 米白紙底（背景） | `#F4EEE3` | `"F4EEE3"` |
| 深墨（前景） | `#1E1A14` | `"1E1A14"` |
| 暗墨綠（強調） | `#2C4A35` | `"2C4A35"` |
| 灰褐（次文） | `#8A7C65` | `"8A7C65"` |
| 髮絲線 | `#C9BCA3` | `"C9BCA3"` |
| 淺墨綠（背景強調） | `#3D6B4F` | `"3D6B4F"` |

**用色原則**：
- 米白是預設背景，**不**用純白
- 暗墨綠用於：節次編號、題眉強調色、封面裝飾線
- 淺墨綠用於：section divider 大色塊、卡片底色
- 灰褐用於：次要文字、題眉英文、日期

---

## 字體

| 用途 | 字體 | `fontFace` |
|---|---|---|
| 中文標題 / 內文 | Noto Serif TC | `"Noto Serif TC"` |
| 英文標題 / 題眉 / 序號 | Georgia | `"Georgia"` |
| 程式碼 | Consolas | `"Consolas"` |

**鐵則對應**：
- 內文 ≥ **20pt**
- 章節標題 **48–60pt**
- 封面大標 **72–96pt**
- 頁腳 / 頁碼 **9–11pt**（唯一例外）
- Consolas 縮排用 `x` 偏移

---

## 母片版心（13.33" × 7.5"）

```
┌──────────────────────────────────────────────────────────┐
│ DofLab                          § III · 章節名稱          │  y=0.18"
│ ──────────────────────────────────────────────────────── │  y=0.34" hairline
│                                                          │
│                                                          │
│            ★ 內容區（x: 0.83"–12.5", y: 0.9"–6.6"）      │
│                                                          │
│                                                          │
│ ──────────────────────────────────────────────────────── │  y=6.97" hairline
│ 劉瑞弘 · 智慧自動化工程系 · 國立勤益科技大學 · DofLab  04│  y=7.10"
└──────────────────────────────────────────────────────────┘
```

**座標表（pptxgenjs 用）**

| 元素 | x | y | w | h | fontSize | color |
|---|---|---|---|---|---|---|
| Logo 文字 (左上) | 0.50 | 0.18 | 1.50 | 0.28 | 14 | `1E1A14` |
| 章節名稱 placeholder (右上) | 7.50 | 0.18 | 5.33 | 0.28 | 11 | `8A7C65` |
| 上 hairline | 0.50 | 0.34 | 12.33 | 0.01 | – | fill `C9BCA3` |
| 下 hairline | 0.50 | 6.97 | 12.33 | 0.01 | – | fill `C9BCA3` |
| Footer 左側 | 0.50 | 7.10 | 9.00 | 0.25 | 10 | `8A7C65` |
| 頁碼 placeholder (右下) | 11.50 | 7.10 | 1.33 | 0.25 | 10 | `8A7C65` |

---

## 母片代碼（完整範本）

```javascript
pres.defineSlideMaster({
  title: "JOURNAL",
  background: { color: "F4EEE3" },
  objects: [
    // Logo
    { text: { text: "DofLab", options: {
      x: 0.50, y: 0.18, w: 1.50, h: 0.28,
      fontFace: "Georgia", fontSize: 14, italic: true,
      color: "1E1A14", margin: 0,
    }}},
    // 上 hairline
    { text: { text: "", options: {
      x: 0.50, y: 0.34, w: 12.33, h: 0.01,
      fill: { color: "C9BCA3" },
    }}},
    // 下 hairline
    { text: { text: "", options: {
      x: 0.50, y: 6.97, w: 12.33, h: 0.01,
      fill: { color: "C9BCA3" },
    }}},
    // Footer 左側
    { text: { text: "劉瑞弘 · 智慧自動化工程系 · 國立勤益科技大學 · DofLab", options: {
      x: 0.50, y: 7.10, w: 9.00, h: 0.25,
      fontFace: "Noto Serif TC", fontSize: 10,
      color: "8A7C65", margin: 0,
    }}},
    // 章節名稱 placeholder
    { placeholder: { options: {
      name: "chapter", type: "body",
      x: 7.50, y: 0.18, w: 5.33, h: 0.28,
      fontFace: "Georgia", fontSize: 11, italic: true,
      color: "8A7C65", align: "right", margin: 0,
    }}},
    // 頁碼 placeholder
    { placeholder: { options: {
      name: "slidenum", type: "slidenum",
      x: 11.50, y: 7.10, w: 1.33, h: 0.25,
      fontFace: "Georgia", fontSize: 10,
      color: "8A7C65", align: "right", margin: 0,
    }}},
  ],
});

// 封面母片（無頂部 logo 列）
pres.defineSlideMaster({
  title: "JOURNAL_COVER",
  background: { color: "F4EEE3" },
  objects: [
    { text: { text: "", options: {
      x: 0.50, y: 6.97, w: 12.33, h: 0.01,
      fill: { color: "C9BCA3" },
    }}},
    { text: { text: "劉瑞弘 · 智慧自動化工程系 · 國立勤益科技大學 · DofLab", options: {
      x: 0.50, y: 7.10, w: 9.00, h: 0.25,
      fontFace: "Noto Serif TC", fontSize: 10,
      color: "8A7C65", margin: 0,
    }}},
    { placeholder: { options: {
      name: "meta", type: "body",
      x: 6.50, y: 7.10, w: 6.33, h: 0.25,
      fontFace: "Georgia", fontSize: 10, italic: true,
      color: "8A7C65", align: "right", margin: 0,
    }}},
  ],
});
```

---

## 視覺裝飾規範

- **不**使用圓角、陰影、漸層
- hairline 線寬 `h: 0.01` 吋（約 0.72pt）
- 允許裝飾：`§ · — → ✓ ⚠ ✗` 印刷符號
- 強調用色塊（`fill`），不用底線或斜體（中文）
- 圖表配色：墨色（`1E1A14`）+ 暗墨綠（`2C4A35`）主，灰褐（`8A7C65`）輔

---

## 物件最小化（Journal 版）

每頁目標 ≤ 12 物件：
- 母片固定 6（logo + hairline×2 + footer + chapter + slidenum）
- 標題 1、題眉 1、內容 1–4 = 共 9–12 個
