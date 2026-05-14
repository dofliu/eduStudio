# 學習目標頁 (objectives)

每章第二或第三頁。傳達:**本章結束後學生能做到的具體能力**(動詞開頭)。

通常 4–8 個目標,排成 2 欄。

---

## 結構

```
┌───────────────────────────────────────────────┐
│ — 今天結束後,你能夠…                            │  ← 引導句
│   六個可操作的能力指標,課程最後我們會逐項回來確認。  │  ← 補充說明
│                                               │
│  01 判斷 LTI 系統穩定性與極點位置的對應關係。     │  02 推導 Routh 表建立規則,並計算各行元素。
│                                               │
│  03 應用 Routh-Hurwitz 判別法判斷高階系統。      │  04 處理 第一列為零與整行為零兩種特殊情況。
│                                               │
│  05 計算 使閉迴路系統穩定的控制器增益 K 範圍。    │  06 設計 Python 程式自動建立 Routh 表並探索...
└───────────────────────────────────────────────┘
                                              [雙語頁腳]
```

---

## 寫法原則

每個目標以 **可觀察的動詞** 開頭:
- ✓ 判斷、推導、應用、處理、計算、設計、比較、區分、繪製、實作
- ✗ 「了解」、「知道」、「熟悉」、「掌握」(不可觀察,學生無法自評)

每項目標 **不超過 30 字**,確保 20pt 一行可放下。

---

## Journal 風格實作

```javascript
function renderObjectives(slide, pres, {introLine, subline, items, chapterMeta, pageNum}) {
  // 米白背景
  slide.background = { color: "FBF8F1" };

  // 引導句(— 開頭,左上)
  slide.addText("— " + introLine, {       // 例:"— 今天結束後,你能夠…"
    x: 0.8, y: 0.8, w: 11, h: 0.6,
    fontFace: "Noto Serif CJK TC",
    fontSize: 32,
    color: "2A2A2A",
    charSpacing: 5,
  });

  // 補充說明(副標)
  slide.addText(subline, {
    x: 0.8, y: 1.6, w: 11, h: 0.4,
    fontFace: "Noto Serif CJK TC",
    fontSize: 16,
    color: "5C6B5E",
    italic: true,
  });

  // 細分隔線
  slide.addShape(pres.shapes.LINE, {
    x: 0.8, y: 2.2, w: 1.5, h: 0,
    line: { color: "2D5A3D", pt: 1 }
  });

  // 目標列表(2 欄 × N 行)
  const colW = 5.8;
  const rowH = 1.0;
  const startY = 2.7;
  items.forEach((text, idx) => {
    const col = idx % 2;
    const row = Math.floor(idx / 2);
    const x = 0.8 + col * (colW + 0.4);
    const y = startY + row * rowH;
    const num = String(idx + 1).padStart(2, "0");

    // 編號(暖金、Georgia 大字)
    slide.addText(num, {
      x, y, w: 0.7, h: 0.6,
      fontFace: "Georgia",
      fontSize: 28,
      color: "B8935A",
      italic: true,
    });

    // 目標文字
    slide.addText(text, {
      x: x + 0.7, y, w: colW - 0.7, h: 0.8,
      fontFace: "Noto Serif CJK TC",
      fontSize: 18,                          // ← Journal 條列下限
      color: "2A2A2A",
      valign: "top",
    });
  });

  // 雙語頁腳(見 themes/journal.md「雙語頁腳」段)
  addFooter(slide, "第 5 章 學習目標", "Chap. 5 · Stability Analysis  學習目標", pageNum);
}
```

---

## 目標數量建議

| 章節長度 | 目標數 | 排列 |
|---|---|---|
| 1 節(2–3 小時) | 3–4 | 單欄 或 2×2 |
| 2 節(4 小時) | 4–6 | 2 欄 × 2–3 行 |
| 3 節(6 小時) | 6–8 | 2 欄 × 3–4 行 |
| 整章(8+ 小時) | 不超過 8 | 2 欄 × 4 行(再多會看不完) |

---

## 學習目標檢視頁(回頭確認)

章末加一頁「回頭看看,你做到了嗎?」,把同樣 6 個目標再列一次,前面加 ✓ 勾選:

```
✓  判斷 LTI 系統穩定性與極點位置的對應
✓  推導 Routh 表建立規則與行列式公式
✓  應用 Routh-Hurwitz 判別法於高階系統
✓  處理第一列為零與整行為零
✓  計算使系統穩定的 K 範圍
✓  設計 Python 程式自動建 Routh 表
```

實作上是同一個 renderObjectives() 函式,改傳 `introLine: "回頭看看,你做到了嗎?"`,並在每項前加 `✓ `。

---

## ❌ 常見錯誤

- 目標用「了解」、「知道」(改用「判斷」、「比較」)
- 目標寫超過 30 字,需要兩行才放得下
- 目標太籠統(「掌握控制系統」→ 改「設計使閉迴路穩定的控制器增益 K」)
- 編號用粗體黑色(失去設計感,應用暖金 + 義大利體)
- 內文用 16pt 以下(Journal 條列下限是 18pt)
