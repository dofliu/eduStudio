# pagetype · roadmap · 學習地圖

---

## 版面結構

```
┌──────────────────────────────────────────────────────────┐
│  章節地圖  Chapter Roadmap  ← 標題                        │
│                                                          │
│  § I · PID 基礎     § II · 調整法則    § III · 進階設計   │
│  15 分鐘            20 分鐘            25 分鐘             │
│  ─────────────      ──────────────     ──────────────    │
│  · 結構定義         · Ziegler-Nichols  · 頻率響應法        │
│  · 時域分析         · Cohen-Coon       · IMC 設計          │
└──────────────────────────────────────────────────────────┘
```

---

## pptxgenjs 代碼骨架（3 節）

```javascript
const slide = pres.addSlide({ masterName: "JOURNAL" });
slide.addText("§ Ch.08 · PID 控制器設計", { placeholder: "chapter" });

slide.addText("章節地圖", {
  x: 0.83, y: 0.90, w: 5.00, h: 0.65,
  fontFace: "Noto Serif TC", fontSize: 48, color: "1E1A14",
});
slide.addText("Chapter Roadmap", {
  x: 0.83, y: 1.50, w: 7.00, h: 0.38,
  fontFace: "Georgia", fontSize: 22, italic: true, color: "8A7C65",
});

const sections = [
  { num: "§ I", title: "PID 基礎", time: "15 分鐘", items: ["結構定義", "時域分析"] },
  { num: "§ II", title: "調整法則", time: "20 分鐘", items: ["Ziegler-Nichols", "Cohen-Coon"] },
  { num: "§ III", title: "進階設計", time: "25 分鐘", items: ["頻率響應法", "IMC 設計"] },
];

const colW = 3.60, colY = 2.10;
const colX = [0.83, 4.70, 8.57];

sections.forEach((sec, i) => {
  slide.addText(`${sec.num} · ${sec.title}`, {
    x: colX[i], y: colY, w: colW, h: 0.50,
    fontFace: "Georgia", fontSize: 22, italic: true, color: "2C4A35",
  });
  slide.addText(sec.time, {
    x: colX[i], y: colY + 0.50, w: colW, h: 0.35,
    fontFace: "Noto Serif TC", fontSize: 20, color: "8A7C65",
  });
  // hairline 分隔
  slide.addText("", {
    x: colX[i], y: colY + 0.90, w: colW, h: 0.01,
    fill: { color: "C9BCA3" },
  });
  // 條列
  sec.items.forEach((item, j) => {
    slide.addText(`· ${item}`, {
      x: colX[i], y: colY + 1.00 + j * 0.45, w: colW, h: 0.40,
      fontFace: "Noto Serif TC", fontSize: 20, color: "1E1A14",
    });
  });
});
```
