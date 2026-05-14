# pagetype · section-divider · 節分隔頁

---

## 版面結構

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  § I  ← 大節次編號（Georgia italic，120–160pt，強調色）   │
│                                                          │
│  PID 基礎  ← 節標題（48–60pt）                           │
│  PID Fundamentals  ← 英文副標（24pt，灰）                 │
│                                                          │
│  ── 15 分鐘 ──  ← 時間標記（20pt，灰）                   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## pptxgenjs 代碼骨架

```javascript
const slide = pres.addSlide({ masterName: "JOURNAL" });
slide.addText("§ Ch.08 · PID 控制器設計", { placeholder: "chapter" });

// 大節次編號（展示性大字，不受 20pt 下限限制）
slide.addText("§ I", {
  x: 0.83, y: 0.80, w: 11.67, h: 2.00,
  fontFace: "Georgia", fontSize: 150, italic: true,
  color: "2C4A35",          // 暗墨綠（Journal），各主題換強調色
  align: "left", valign: "bottom",
});

// 節標題
slide.addText("PID 基礎", {
  x: 0.83, y: 3.00, w: 11.67, h: 0.80,
  fontFace: "Noto Serif TC", fontSize: 54,
  color: "1E1A14",
});

// 英文副標
slide.addText("PID Fundamentals", {
  x: 0.83, y: 3.75, w: 11.67, h: 0.45,
  fontFace: "Georgia", fontSize: 26, italic: true,
  color: "8A7C65",
});

// 時間標記
slide.addText("· 15 分鐘 ·", {
  x: 0.83, y: 4.40, w: 11.67, h: 0.38,
  fontFace: "Georgia", fontSize: 20, italic: true,
  color: "8A7C65",
});
```

---

## 注意事項

- `§ I` 大字為展示性文字，字級 **不受** 20pt 下限限制
- 使用 **body 母片**（非 COVER），保留頂部 logo 列與 chapter placeholder
- 背景保持紙底色，不加色塊
