# 內容頁 (content) · 版型庫

一般教學內容用此頁型。依教材性質從版型庫選擇。

---

## 版型選擇決策表

| 版型 | 使用時機 | 典型內容 |
|---|---|---|
| `two-col` | 概念對比、優缺點、前後比較 | 「穩定 vs 不穩定」、「解方程 vs Routh」 |
| `card-grid` | 3–6 個並列項目 | 「六大策略」、「三大判別法」 |
| `stat-callout` | 關鍵數字大字展示 | 「60.00 Hz · 電網正常頻率」 |
| `concept-circle` | 三元素平衡 / 三角結構 | 「穩定/臨界/不穩定」 |
| `quote-block` | 引言框 / 黃金法則框 | 「LTI 穩定 ⟺ 所有極點 Re < 0」 |
| `full-image` | 圖表為主角 | s 平面圖、響應曲線 |
| `formula-block` | LaTeX 公式展示 | Routh 表計算式、特徵多項式 |
| `compare-table` | 多欄資料對比 | 三種 K 值的時域響應對照 |

---

## 通用結構(所有版型共享)

```
┌────────────────────────────────────────┐
│ § 1.2  從一階系統切入                    │  ← 節號 + 標題(charSpacing)
│         為什麼「極點的實部」就是穩定性的關鍵。│  ← 副標(墨綠灰、義大利體)
│                                        │
│           [ 版型內容區 ]                 │
│                                        │
│                                        │
│                                        │
│ § 1 穩定性的基本概念              07     │  ← 雙語頁腳 + 頁碼
│ Chap. 5 · Stability Analysis  § 1.2     │
└────────────────────────────────────────┘
```

---

## two-col(雙欄對比)

```javascript
function renderTwoCol(slide, pres, {sectionLabel, title, subtitle, leftTitle, leftItems, rightTitle, rightItems}) {
  slide.background = { color: "FBF8F1" };
  renderHeader(slide, sectionLabel, title, subtitle);

  const colW = 5.8;
  const startY = 2.5;

  // 左欄
  slide.addText(leftTitle, {
    x: 0.8, y: startY, w: colW, h: 0.5,
    fontFace: "Noto Serif CJK TC", fontSize: 22, color: "2D5A3D",
    charSpacing: 5,
  });
  leftItems.forEach((item, i) => {
    slide.addText("· " + item, {
      x: 0.8, y: startY + 0.7 + i * 0.55, w: colW, h: 0.5,
      fontFace: "Noto Serif CJK TC", fontSize: 18, color: "2A2A2A",  // 18pt 下限
    });
  });

  // 右欄
  slide.addText(rightTitle, {
    x: 7.0, y: startY, w: colW, h: 0.5,
    fontFace: "Noto Serif CJK TC", fontSize: 22, color: "2D5A3D",
    charSpacing: 5,
  });
  rightItems.forEach((item, i) => {
    slide.addText("· " + item, {
      x: 7.0, y: startY + 0.7 + i * 0.55, w: colW, h: 0.5,
      fontFace: "Noto Serif CJK TC", fontSize: 18, color: "2A2A2A",
    });
  });

  // 中央分隔細線
  slide.addShape(pres.shapes.LINE, {
    x: 6.65, y: startY, w: 0, h: 3.5,
    line: { color: "D4CFC0", pt: 0.5 }
  });
}
```

---

## card-grid(卡片網格,3–6 卡)

```javascript
function renderCardGrid(slide, pres, {sectionLabel, title, subtitle, cards}) {
  slide.background = { color: "FBF8F1" };
  renderHeader(slide, sectionLabel, title, subtitle);

  // 計算卡片佈局(3 或 4 欄)
  const cols = cards.length <= 3 ? cards.length : (cards.length === 4 ? 2 : 3);
  const rows = Math.ceil(cards.length / cols);
  const margin = 0.4;
  const cardW = (12.5 - (cols - 1) * margin) / cols;
  const cardH = 2.5;
  const startY = 2.7;

  cards.forEach((card, idx) => {
    const c = idx % cols;
    const r = Math.floor(idx / cols);
    const x = 0.4 + c * (cardW + margin);
    const y = startY + r * (cardH + margin);

    // 卡片外框(米白底 + 細邊框,零圓角)
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: cardW, h: cardH,
      fill: { color: "FFFFFF" },
      line: { color: "D4CFC0", pt: 0.5 },
      rectRadius: 0,                              // ← Journal 鐵則
    });

    // 卡片標題(Q1 · 基礎 / 標籤類)
    slide.addText(card.label, {
      x: x + 0.3, y: y + 0.2, w: cardW - 0.6, h: 0.4,
      fontFace: "Georgia", fontSize: 14, color: "B8935A",
      italic: true, charSpacing: 4,
    });

    // 卡片內文(主要訊息)
    slide.addText(card.body, {
      x: x + 0.3, y: y + 0.65, w: cardW - 0.6, h: cardH - 1.0,
      fontFace: "Noto Serif CJK TC", fontSize: 18, color: "2A2A2A",  // 18pt
      valign: "top",
    });

    // 卡片底部提示(可選)
    if (card.hint) {
      slide.addText(card.hint, {
        x: x + 0.3, y: y + cardH - 0.4, w: cardW - 0.6, h: 0.3,
        fontFace: "Noto Serif CJK TC", fontSize: 12, color: "5C6B5E",
        italic: true,
      });
    }
  });
}
```

---

## stat-callout(關鍵數字大字)

用於章節開頭情境導入,例如「60.00 Hz · 電網正常頻率」。

```javascript
function renderStatCallout(slide, pres, {sectionLabel, title, subtitle, stats}) {
  // stats = [{value: "60.00 Hz", label: "電網正常頻率"}, ...]
  slide.background = { color: "FBF8F1" };
  renderHeader(slide, sectionLabel, title, subtitle);

  const cols = stats.length;                       // 通常 3–4 個
  const colW = 12.5 / cols;
  const startY = 3.0;

  stats.forEach((stat, idx) => {
    const x = 0.4 + idx * colW;
    // 大數字(Georgia 義大利體,暖金或暗墨綠)
    slide.addText(stat.value, {
      x, y: startY, w: colW, h: 1.0,
      fontFace: "Georgia", fontSize: 48, color: "2D5A3D",
      align: "center", italic: true,
    });
    // 下方說明
    slide.addText(stat.label, {
      x, y: startY + 1.1, w: colW, h: 0.5,
      fontFace: "Noto Serif CJK TC", fontSize: 16, color: "5C6B5E",
      align: "center", charSpacing: 4,
    });
  });
}
```

---

## quote-block(黃金法則框)

Journal 標誌性元件,用於核心定理或關鍵法則。詳見 `themes/journal.md`「黃金法則框」段。

---

## formula-block(LaTeX 公式)

用 matplotlib mathtext 渲染 PNG 嵌入,**不要用文字模擬公式**。

```javascript
slide.addImage({
  path: "./equations/eq_lti_stability.png",
  x: 2.0, y: 3.0, w: 9.0, h: 1.5,                  // 寬高比依公式而定
  sizing: { type: "contain", w: 9.0, h: 1.5 },     // 避免比例變形
});
```

詳見 `references/math-typography.md`(若該檔存在)和 `scripts/latex_equation.py`。

---

## 共用 header 函式

每張內容頁的頂部都一樣,抽出來:

```javascript
function renderHeader(slide, sectionLabel, title, subtitle) {
  // 節號標籤(例:"§ 1.2")
  slide.addText(sectionLabel, {
    x: 0.8, y: 0.4, w: 2, h: 0.4,
    fontFace: "Georgia", fontSize: 12, color: "B8935A",
    italic: true, charSpacing: 5,
  });

  // 標題(例:"從一階系統切入")
  slide.addText(title, {
    x: 0.8, y: 0.9, w: 11.5, h: 0.7,
    fontFace: "Noto Serif CJK TC", fontSize: 32, color: "2A2A2A",
    charSpacing: 5,
  });

  // 副標(例:"為什麼「極點的實部」就是穩定性的關鍵。")
  slide.addText(subtitle, {
    x: 0.8, y: 1.7, w: 11.5, h: 0.4,
    fontFace: "Noto Serif CJK TC", fontSize: 16, color: "5C6B5E",
    italic: true,
  });

  // 細分隔線
  slide.addShape(pres.shapes.LINE, {
    x: 0.8, y: 2.2, w: 1.5, h: 0,
    line: { color: "2D5A3D", pt: 1 }
  });
}
```

---

## ❌ 常見錯誤

- 內文用 14pt 想塞下更多 bullet → 違反字體鐵則,應拆頁
- 卡片用 rectRadius: 8(圓角) → Journal 鐵則:零圓角
- 兩欄高度不一致,版面失衡 → 調整 items 數量或字數使兩欄等高
- 公式用文字模擬 `(s+1)(s+5) = 0` → 用 LaTeX 渲染 PNG
- 沒有節號標籤(§ 1.2) → 學生無法定位現在在哪一節
