# pagetype · cover · 章節封面

所有主題通用骨架，各主題色彩 / 字體依對應 theme.md 套入。

---

## 版面結構

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  Ch. 08  ← 大序號（Georgia/EB Garamond italic，120–180pt）│  y≈1.2"
│                                                          │
│  PID 控制器設計  ← 中文大標（48–72pt）                    │  y≈2.4"
│  PID Controller Design  ← 英文副標（24–32pt，灰）         │  y≈3.2"
│                                                          │
│  ──────────────────  ← 裝飾線（強調色，w≈4"）             │  y≈3.9"
│                                                          │
│  智慧自動化工程系 · 劉瑞弘  ← 課程資訊（20pt，灰）         │  y≈4.5"
│                                                          │
│ ──────────────────────────────────────────────────────── │  母片 hairline
│ 劉瑞弘 · ... · DofLab                                    │  母片 footer
└──────────────────────────────────────────────────────────┘
```

---

## pptxgenjs 代碼骨架

```javascript
const cover = pres.addSlide({ masterName: "JOURNAL_COVER" }); // 換成對應主題 _COVER

// 大序號
cover.addText("Ch. 08", {
  x: 0.83, y: 1.00, w: 11.67, h: 1.40,
  fontFace: "Georgia",        // dof 系列用 "EB Garamond"
  fontSize: 120, italic: true,
  color: "2C4A35",            // 強調色（Journal 用暗墨綠；各主題換色）
  align: "left", valign: "middle",
});

// 中文大標
cover.addText("PID 控制器設計", {
  x: 0.83, y: 2.40, w: 11.67, h: 0.90,
  fontFace: "Noto Serif TC",  // 黑體系用 "Microsoft JhengHei"
  fontSize: 60, bold: false,
  color: "1E1A14",
  align: "left",
});

// 英文副標
cover.addText("PID Controller Design", {
  x: 0.83, y: 3.20, w: 11.67, h: 0.50,
  fontFace: "Georgia",
  fontSize: 28, italic: true,
  color: "8A7C65",
  align: "left",
});

// 裝飾線
cover.addText("", {
  x: 0.83, y: 3.85, w: 4.00, h: 0.04,
  fill: { color: "2C4A35" },  // 強調色
});

// 課程資訊
cover.addText("智慧自動化工程系 · 劉瑞弘 · 控制系統", {
  x: 0.83, y: 4.40, w: 11.67, h: 0.40,
  fontFace: "Noto Serif TC",
  fontSize: 20,
  color: "8A7C65",
  align: "left",
});

// meta placeholder（學期資訊）
cover.addText("2025 秋季 · Chapter 08", { placeholder: "meta" });
```

---

## 各主題調整

| 主題 | 大序號色 | 裝飾線色 | masterName |
|---|---|---|---|
| `journal` | `2C4A35` | `2C4A35` | `JOURNAL_COVER` |
| `dof-editorial` | `B25530` | `B25530` | `EDITORIAL_COVER` |
| `dof-podium` | `18191C` | `18191C` | `PODIUM_COVER` |
| `dof-notebook` | `6E7E62` | `6E7E62` | `NOTEBOOK_COVER` |
| `dof-shinobi` | `C0392B` | `C0392B` | `SHINOBI_COVER` |
| `dof-elven` | `7B5EA7` | `7B5EA7` | `ELVEN_COVER` |
| `forest` | `5DB86C` | `5DB86C` | `FOREST_COVER` |
| `navy` | `4A9EE0` | `4A9EE0` | `NAVY_COVER` |

---

## 注意事項

- 封面使用 `_COVER` 母片，不顯示頂部 logo 列
- 大序號 `Ch. XX` 字級 **不受** 18/20pt 下限限制（展示性文字）
- 裝飾線 `h: 0.04` 而非 `0.01`（比 hairline 粗，作為設計元素）
- `fill: { color: "..." }` 不要加 `line`
