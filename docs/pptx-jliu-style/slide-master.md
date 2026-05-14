# slide-master · 母片架構規範

所有主題都必須用 `pres.defineSlideMaster()` 實作母片。
**禁止**在每頁的 `addMasterSlide()` helper 函式裡重複放固定元素。

---

## 母片分工原則

```
defineSlideMaster()
├── objects: []         ← 靜態元素：寫一次，所有投影片自動套用
│   ├── logo / wordmark
│   ├── 上 hairline
│   ├── 下 hairline
│   └── footer 左側文字   ← ★ 這裡改一次 = 全部同步
│
└── placeholder: []     ← 動態佔位框：每頁各自填入
    ├── "chapter"        ← 章節名稱（每頁不同）
    └── "slidenum"       ← 頁碼（pptxgenjs 自動遞增）
```

### 靜態 vs 動態判斷標準

| 內容 | 類型 | 理由 |
|---|---|---|
| Logo / 機構名稱 | 靜態 | 整份簡報相同 |
| 頁尾文字（姓名、系所） | 靜態 | 整份簡報相同 |
| 上下 hairline | 靜態 | 所有內頁相同 |
| 章節名稱 / 節次標籤 | 動態 placeholder | 每頁不同 |
| 頁碼 | slidenum placeholder | 自動遞增 |
| 日期（若固定） | 靜態 | 整份相同 |
| 計畫編號（若固定） | 靜態 | 整份相同 |

---

## 標準母片代碼範本

每個主題都有兩個母片：`THEME_BODY`（一般頁）和 `THEME_COVER`（封面 / 結尾頁）。

### Body 母片（一般內容頁）

```javascript
// 將下方 [佔位符] 替換為實際色碼與文字
pres.defineSlideMaster({
  title: "DOF_ELVEN",          // 主題代碼大寫，加 DOF_ 前綴
  background: { color: "[BG_COLOR]" },

  objects: [
    // ── Logo（靜態，左上）─────────────────────────────────────
    {
      text: {
        text: "DofLab",
        options: {
          x: 0.50, y: 0.18, w: 1.50, h: 0.28,
          fontFace: "[LOGO_FONT]", fontSize: 14, italic: true,
          color: "[INK_COLOR]", margin: 0,
        },
      },
    },

    // ── 上 hairline（靜態）────────────────────────────────────
    {
      text: {
        text: "",
        options: {
          x: 0.50, y: 0.34, w: 12.33, h: 0.01,
          fill: { color: "[HAIR_COLOR]" },
        },
      },
    },

    // ── 下 hairline（靜態）────────────────────────────────────
    {
      text: {
        text: "",
        options: {
          x: 0.50, y: 6.97, w: 12.33, h: 0.01,
          fill: { color: "[HAIR_COLOR]" },
        },
      },
    },

    // ── Footer 左側（靜態）
    //    ★ 唯一需要修改 footer 文字的地方 ★ ──────────────────────
    {
      text: {
        text: "[FOOTER_TEXT]",   // 例：劉瑞弘 · 智慧自動化工程系 · 國立勤益科技大學 · DofLab
        options: {
          x: 0.50, y: 7.10, w: 9.00, h: 0.25,
          fontFace: "[BODY_FONT]", fontSize: 10,
          color: "[GRAY_COLOR]", margin: 0,
        },
      },
    },

    // ── 章節名稱佔位框（動態，每頁填入）─────────────────────────
    {
      placeholder: {
        options: {
          name: "chapter",
          type: "body",
          x: 7.50, y: 0.18, w: 5.33, h: 0.28,
          fontFace: "[LABEL_FONT]", fontSize: 11, italic: true,
          color: "[GRAY_COLOR]", align: "right", margin: 0,
        },
      },
    },

    // ── 頁碼（自動遞增）──────────────────────────────────────
    {
      placeholder: {
        options: {
          name: "slidenum",
          type: "slidenum",
          x: 11.50, y: 7.10, w: 1.33, h: 0.25,
          fontFace: "[LABEL_FONT]", fontSize: 10,
          color: "[GRAY_COLOR]", align: "right", margin: 0,
        },
      },
    },
  ],
});
```

### Cover 母片（封面 / 結尾頁）

封面通常不顯示頂部 logo 列與章節名稱，但保留 footer。

```javascript
pres.defineSlideMaster({
  title: "DOF_ELVEN_COVER",
  background: { color: "[BG_COLOR]" },

  objects: [
    // 下 hairline
    {
      text: {
        text: "",
        options: { x: 0.50, y: 6.97, w: 12.33, h: 0.01, fill: { color: "[HAIR_COLOR]" } },
      },
    },
    // Footer 左側（與 body 母片相同文字）
    {
      text: {
        text: "[FOOTER_TEXT]",
        options: {
          x: 0.50, y: 7.10, w: 7.50, h: 0.25,
          fontFace: "[BODY_FONT]", fontSize: 10,
          color: "[GRAY_COLOR]", margin: 0,
        },
      },
    },
    // 封面右下 meta 佔位（journal 名稱、日期等）
    {
      placeholder: {
        options: {
          name: "meta",
          type: "body",
          x: 6.50, y: 7.10, w: 6.33, h: 0.25,
          fontFace: "[LABEL_FONT]", fontSize: 10, italic: true,
          color: "[GRAY_COLOR]", align: "right", margin: 0,
        },
      },
    },
  ],
});
```

### 每頁使用方式

```javascript
// 一般頁：只需一行，章節名稱填入 placeholder
const slide = pres.addSlide({ masterName: "DOF_ELVEN" });
slide.addText("§ I · 研究背景  Background", { placeholder: "chapter" });

// 封面 / 結尾頁
const cover = pres.addSlide({ masterName: "DOF_ELVEN_COVER" });
cover.addText("Journal of Wind Engineering · 2025", { placeholder: "meta" });
```

---

## 各主題母片色彩對照表

| 主題 | title 前綴 | BG | INK | GRAY | HAIR | LOGO_FONT | BODY_FONT |
|---|---|---|---|---|---|---|---|
| `journal` | `JOURNAL` | `F4EEE3` | `1E1A14` | `8A7C65` | `C9BCA3` | `Georgia` | `Noto Serif TC` |
| `forest` | `FOREST` | `1A2E1A` | `F5F5F0` | `8FAF8F` | `2E4A2E` | `Microsoft JhengHei` | `Microsoft JhengHei` |
| `navy` | `NAVY` | `0A1628` | `E8EDF5` | `6B8BB5` | `1E3050` | `Microsoft JhengHei` | `Microsoft JhengHei` |
| `frieren` | `FRIEREN` | `1E1B2E` | `E8E0F0` | `9080B0` | `3A3060` | `Georgia` | `Microsoft JhengHei` |
| `naruto` | `NARUTO` | `1A0A00` | `F5E8D0` | `C07840` | `3A2010` | `Microsoft JhengHei` | `Microsoft JhengHei` |
| `dof-editorial` | `EDITORIAL` | `F4EEE3` | `1E1A14` | `8A7C65` | `C9BCA3` | `EB Garamond` | `Noto Serif TC` |
| `dof-podium` | `PODIUM` | `EEEDE9` | `18191C` | `8B8F95` | `CFCFC9` | `EB Garamond` | `Noto Serif TC` |
| `dof-notebook` | `NOTEBOOK` | `F1ECE3` | `2A2520` | `9C948A` | `D6CFC1` | `EB Garamond` | `Noto Serif TC` |
| `dof-shinobi` | `SHINOBI` | `16110A` | `F2E5C8` | `8A7D5E` | `3A3024` | `EB Garamond` | `Noto Serif TC` |
| `dof-elven` | `ELVEN` | `F2EEF5` | `1F1B2E` | `9089A4` | `D8D2DE` | `EB Garamond` | `Noto Serif TC` |

> **dof-shinobi 特別注意**：深色底，所有文字色都要用 `F2E5C8`（淺色），包含 footer。

---

## 母片確認問題（每次製作前必問）

在 Step 1 確認輸入後，Step 2 規劃投影片清單前，**必須詢問以下兩個問題**：

### 問題 1：Footer 文字確認

> 目前母片 footer 預設顯示：
> **「劉瑞弘 · 智慧自動化工程系 · 國立勤益科技大學 · DofLab」**
>
> 這次簡報要使用預設，還是需要修改？
> （例如：改成英文、加計畫編號、換成學生姓名等）

- 若使用者說「預設」或直接不回應 → 沿用預設
- 若使用者提供修改內容 → 記錄新文字，套入 `[FOOTER_TEXT]`

### 問題 2：母片額外元素

> 是否有其他固定要出現在每頁的元素？
> 例如：計畫編號、機構 LOGO 圖片、特定日期、英文版姓名

- 若無 → 跳過
- 若有 → 加入 `objects: []` 陣列作為靜態元素，或加入 `placeholder` 供每頁覆寫

---

## 允許自訂的靜態元素清單

以下元素可以在 `objects` 裡動態調整，不影響整體架構：

| 元素 | 預設值 | 常見自訂 |
|---|---|---|
| Footer 左側文字 | 劉瑞弘 · 智慧自動化工程系 · 國立勤益科技大學 · DofLab | 英文姓名、計畫編號 |
| Logo 文字 | DofLab | DofLab × [合辦單位] |
| 頁尾右側（額外） | 無 | 版本號、日期 |
| 機構 logo 圖片 | 無 | `{ image: { path: "...", x, y, w, h } }` |

---

## 禁止事項

- ❌ 不要寫 `addMasterSlide()` helper，由母片取代
- ❌ 不要在每頁的 `addText()` 裡重複放 logo、footer、hairline
- ❌ 不要在 `objects` 裡放會每頁變化的內容（頁碼除外，用 slidenum placeholder）
- ❌ 不要把頁碼用 `addText()` 手動寫，統一用 slidenum placeholder
