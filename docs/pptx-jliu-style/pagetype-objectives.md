# pagetype · objectives · 學習目標

---

## 版面結構

```
┌──────────────────────────────────────────────────────────┐
│ DofLab              § Ch.08 · PID 控制器設計              │  母片
│ ────────────────────────────────────────────────────────  │
│                                                          │
│  學習目標  Learning Objectives  ← 標題（48–54pt）         │  y=0.9"
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ 01       │  │ 02       │  │ 03       │               │  y=2.0"
│  │ 理解     │  │ 推導     │  │ 設計     │  動詞標籤      │
│  │ PID 結構 │  │ 調整公式 │  │ 參數調整 │               │
│  └──────────┘  └──────────┘  └──────────┘               │
│                                                          │
│ ────────────────────────────────────────────────────────  │  母片
│ 劉瑞弘 · ...                                     01      │
└──────────────────────────────────────────────────────────┘
```

---

## pptxgenjs 代碼骨架（Journal 版，3 目標）

```javascript
const slide = pres.addSlide({ masterName: "JOURNAL" });
slide.addText("§ Ch.08 · PID 控制器設計", { placeholder: "chapter" });

// 標題
slide.addText("學習目標", {
  x: 0.83, y: 0.90, w: 6.00, h: 0.70,
  fontFace: "Noto Serif TC", fontSize: 48,
  color: "1E1A14", bold: false,
});
slide.addText("Learning Objectives", {
  x: 0.83, y: 1.55, w: 8.00, h: 0.40,
  fontFace: "Georgia", fontSize: 22, italic: true,
  color: "8A7C65",
});

// 目標卡片（每張約 3.7" 寬）
const objectives = [
  { num: "01", verb: "理解", desc: "PID 各項的物理意義與頻域響應" },
  { num: "02", verb: "推導", desc: "Ziegler-Nichols 調整法則與適用條件" },
  { num: "03", verb: "設計", desc: "結合根軌跡與頻率響應進行 PID 參數調整" },
];

const cardW = 3.60, cardH = 2.80, cardY = 2.20;
const cardX = [0.83, 4.70, 8.57];
const accentColor = "2C4A35"; // Journal 暗墨綠

objectives.forEach((obj, i) => {
  // 序號
  slide.addText(obj.num, {
    x: cardX[i], y: cardY, w: cardW, h: 0.55,
    fontFace: "Georgia", fontSize: 28, italic: true,
    color: accentColor,
  });
  // 動詞標籤（強調色底）
  slide.addText(obj.verb, {
    x: cardX[i], y: cardY + 0.55, w: cardW, h: 0.50,
    fontFace: "Noto Serif TC", fontSize: 26, bold: true,
    color: "F4EEE3", fill: { color: accentColor },
  });
  // 說明文字
  slide.addText(obj.desc, {
    x: cardX[i], y: cardY + 1.10, w: cardW, h: 1.50,
    fontFace: "Noto Serif TC", fontSize: 20,
    color: "1E1A14", valign: "top",
  });
});
```

---

## 目標數量變體

| 目標數 | 卡片寬度 | 起始 x |
|---|---|---|
| 2 | 5.50" | 0.83, 6.50 |
| 3 | 3.60" | 0.83, 4.70, 8.57 |
| 4 | 2.70" | 0.83, 3.68, 6.53, 9.38 |

---

## 注意事項

- 動詞標籤用**強調色底 + 白字**（fill 策略 B）
- 序號用 Georgia/EB Garamond italic
- 說明文字 ≥ 20pt（Journal/dof 系列）
- 不要用圓角（`rectRadius: 0`，或不設定）
