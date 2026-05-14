# pagetype · exercise · 練習題頁

---

## 版面結構

```
┌──────────────────────────────────────────────────────────┐
│  Exercise · 03  ← 大標（Georgia italic，強調色）          │
│  ──────────────  ← 裝飾線                                 │
│  標題（48pt）                                             │
│                                                          │
│  問題  Question                                           │
│  題幹文字（20–22pt）...                                   │
│                                                          │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─（答案橫線）                       │
└──────────────────────────────────────────────────────────┘
```

---

## pptxgenjs 代碼骨架

```javascript
const slide = pres.addSlide({ masterName: "JOURNAL" });
slide.addText("§ II · 練習題  Exercise", { placeholder: "chapter" });

// 大標
slide.addText("Exercise · 03", {
  x: 0.83, y: 0.90, w: 7.00, h: 0.70,
  fontFace: "Georgia", fontSize: 48, italic: true,
  color: "2C4A35",
});

// 裝飾線
slide.addText("", {
  x: 0.83, y: 1.65, w: 3.50, h: 0.04,
  fill: { color: "2C4A35" },
});

// 標題
slide.addText("Ziegler-Nichols 法則應用", {
  x: 0.83, y: 1.80, w: 11.67, h: 0.65,
  fontFace: "Noto Serif TC", fontSize: 44, color: "1E1A14",
});

// 題眉「問題」
slide.addText("問題  Question", {
  x: 0.83, y: 2.60, w: 4.00, h: 0.38,
  fontFace: "Georgia", fontSize: 20, italic: true, color: "8A7C65",
});

// 題幹
slide.addText(
  "已知受控系統 G(s) = 1/(s+1)³，利用 Ziegler-Nichols 步階響應法求取 PID 參數，並驗證閉迴路步階響應的超越量是否低於 25%。",
  {
    x: 0.83, y: 3.00, w: 11.67, h: 1.60,
    fontFace: "Noto Serif TC", fontSize: 22, color: "1E1A14",
    valign: "top",
  }
);

// 答案橫線
for (let i = 0; i < 3; i++) {
  slide.addText("", {
    x: 0.83, y: 4.80 + i * 0.55, w: 11.67, h: 0.01,
    fill: { color: "C9BCA3" },
  });
}
```

---

## 參考解答頁（同題目頁架構）

```javascript
// 將 "Exercise · 03" 改成 "Solution · 03"
// 移除答案橫線
// 填入解答步驟（條列，20–22pt）
slide.addText("Solution · 03", {
  // ... 同上但色用暗墨綠
});
```
