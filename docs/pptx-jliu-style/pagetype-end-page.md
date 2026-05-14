# pagetype · end-page · END 頁

---

## 版面結構

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│                    — End —                               │  置中大字
│                                                          │
│         工欲善其事，必先利其器。                          │  中文金句
│                                                          │
│    End of Chapter VIII · Continued in Chapter IX         │  英文收束
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## pptxgenjs 代碼骨架

```javascript
const slide = pres.addSlide({ masterName: "JOURNAL_COVER" });

// 大標「— End —」
slide.addText("— End —", {
  x: 0.83, y: 1.50, w: 11.67, h: 2.20,
  fontFace: "Georgia", fontSize: 120, italic: true,
  color: "2C4A35",
  align: "center", valign: "middle",
});

// 中文金句
slide.addText("工欲善其事，必先利其器。", {
  x: 0.83, y: 3.90, w: 11.67, h: 0.70,
  fontFace: "Noto Serif TC", fontSize: 32,
  color: "1E1A14",
  align: "center",
});

// 英文收束
slide.addText("End of Chapter VIII · Continued in Chapter IX", {
  x: 0.83, y: 4.70, w: 11.67, h: 0.40,
  fontFace: "Georgia", fontSize: 20, italic: true,
  color: "8A7C65",
  align: "center",
});

// meta placeholder（可填入日期 / 課程名）
slide.addText("控制系統 · 2025 秋季", { placeholder: "meta" });
```

---

## 注意事項

- 使用 **COVER 母片**（無頂部 logo 列）
- `— End —` 大字為展示性，不受 20pt 限制
- 金句可依課程主題更換
- 背景保持紙底色，極簡留白
