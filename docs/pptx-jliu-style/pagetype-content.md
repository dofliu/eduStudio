# pagetype · content · 一般內容頁

提供多種版型（layout）選擇。每頁選一種版型使用。

---

## 版型 A：單欄條列（最常用）

```javascript
const slide = pres.addSlide({ masterName: "JOURNAL" });
slide.addText("§ I · PID 基礎  §I · Fundamentals", { placeholder: "chapter" });

// 題眉
slide.addText("§ I.i · 比例控制  Proportional Control", {
  x: 0.83, y: 0.90, w: 11.67, h: 0.35,
  fontFace: "Georgia", fontSize: 20, italic: true, color: "8A7C65",
});

// 主標題
slide.addText("比例控制器的作用", {
  x: 0.83, y: 1.20, w: 11.67, h: 0.70,
  fontFace: "Noto Serif TC", fontSize: 48, color: "1E1A14",
});

// 條列內容（每條 ≥ 20pt）
const items = [
  "比例增益 Kp 決定誤差的即時修正量",
  "Kp 越大，響應越快但超越量增加",
  "穩態誤差存在，需加入積分項消除",
];
items.forEach((text, i) => {
  slide.addText(`→ ${text}`, {
    x: 0.83, y: 2.10 + i * 0.70, w: 11.67, h: 0.60,
    fontFace: "Noto Serif TC", fontSize: 22, color: "1E1A14",
  });
});
```

---

## 版型 B：兩欄（左說明 + 右圖表）

```javascript
// 左欄說明（40% 寬）
slide.addText("條列說明內容...", {
  x: 0.83, y: 2.00, w: 4.80, h: 4.00,
  fontFace: "Noto Serif TC", fontSize: 20, color: "1E1A14", valign: "top",
});

// 右欄圖片（55% 寬）
slide.addImage({ path: "img/response_curve.png", x: 6.00, y: 1.80, w: 6.50, h: 4.50 });
```

---

## 版型 C：卡片 Grid（2×2 或 3×1）

```javascript
// 2×2 卡片
const cards = [
  { title: "比例 P", desc: "即時誤差修正" },
  { title: "積分 I", desc: "累積誤差消除" },
  { title: "微分 D", desc: "誤差變化預測" },
  { title: "PID", desc: "三項協同控制" },
];
const positions = [
  { x: 0.83, y: 2.00 }, { x: 6.70, y: 2.00 },
  { x: 0.83, y: 4.40 }, { x: 6.70, y: 4.40 },
];
cards.forEach((card, i) => {
  slide.addText(card.title, {
    x: positions[i].x, y: positions[i].y, w: 5.50, h: 0.55,
    fontFace: "Georgia", fontSize: 28, italic: true, color: "2C4A35",
  });
  slide.addText(card.desc, {
    x: positions[i].x, y: positions[i].y + 0.55, w: 5.50, h: 0.60,
    fontFace: "Noto Serif TC", fontSize: 22, color: "1E1A14",
  });
  // 底部 hairline
  slide.addText("", {
    x: positions[i].x, y: positions[i].y + 1.20, w: 5.50, h: 0.01,
    fill: { color: "C9BCA3" },
  });
});
```

---

## 版型 D：stat-callout（大數字強調）

```javascript
// 大數字
slide.addText("48%", {
  x: 0.83, y: 1.80, w: 5.00, h: 1.80,
  fontFace: "Georgia", fontSize: 96, italic: false,
  color: "2C4A35",
});
// 說明
slide.addText("使用 PID 控制可降低的穩態誤差", {
  x: 0.83, y: 3.50, w: 5.00, h: 0.60,
  fontFace: "Noto Serif TC", fontSize: 22, color: "8A7C65",
});
```

---

## 通用注意事項

- 題眉：**一定要有**，格式 `§ N.n · 中文  English`，italic，灰色，20pt
- 主標題：48–54pt
- 內文：**≥ 20pt**（Journal/dof），≥ 18pt（Forest/Navy）
- 不用純文字頁：每頁至少有一個視覺元素（hairline、卡片、圖表）
