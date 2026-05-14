# pagetype · summary · 章節小結

---

## 版面結構（三欄並列）

```javascript
const slide = pres.addSlide({ masterName: "JOURNAL" });
slide.addText("§ Ch.08 · 章節總結  Summary", { placeholder: "chapter" });

slide.addText("章節小結", {
  x: 0.83, y: 0.90, w: 6.00, h: 0.70,
  fontFace: "Noto Serif TC", fontSize: 48, color: "1E1A14",
});
slide.addText("Chapter Summary", {
  x: 0.83, y: 1.55, w: 8.00, h: 0.38,
  fontFace: "Georgia", fontSize: 22, italic: true, color: "8A7C65",
});

const summaries = [
  { num: "i", title: "PID 結構", points: ["三項的物理意義", "時域分析方法"] },
  { num: "ii", title: "調整法則", points: ["Z-N 步階響應法", "Cohen-Coon 法"] },
  { num: "iii", title: "進階設計", points: ["頻率響應 Loop Shaping", "IMC 架構"] },
];

const colW = 3.60, colX = [0.83, 4.70, 8.57];

summaries.forEach((s, i) => {
  // 頂部強調線
  slide.addText("", {
    x: colX[i], y: 2.20, w: colW, h: 0.04,
    fill: { color: "2C4A35" },
  });
  // 大序號
  slide.addText(s.num, {
    x: colX[i], y: 2.30, w: colW, h: 0.80,
    fontFace: "Georgia", fontSize: 56, italic: true,
    color: "2C4A35",
  });
  // 子標
  slide.addText(s.title, {
    x: colX[i], y: 3.10, w: colW, h: 0.55,
    fontFace: "Noto Serif TC", fontSize: 28, bold: true, color: "1E1A14",
  });
  // 要點
  s.points.forEach((pt, j) => {
    slide.addText(`→ ${pt}`, {
      x: colX[i], y: 3.75 + j * 0.55, w: colW, h: 0.48,
      fontFace: "Noto Serif TC", fontSize: 20, color: "8A7C65",
    });
  });
});
```
