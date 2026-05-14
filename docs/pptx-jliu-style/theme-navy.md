# navy · 深藍科技風

> 適用於 AI / RAG / 技術進階課程、研討會。
> 視覺氣質：**深藍底、科技感、適合進階技術課程**。

---

## 色彩 token

| 用途 | Hex | pptxgenjs |
|---|---|---|
| 深藍背景 | `#0A1628` | `"0A1628"` |
| 前景白藍 | `#E8EDF5` | `"E8EDF5"` |
| 亮藍強調 | `#4A9EE0` | `"4A9EE0"` |
| 次文灰藍 | `#6B8BB5` | `"6B8BB5"` |
| hairline | `#1E3050` | `"1E3050"` |

---

## 字體

| 用途 | `fontFace` |
|---|---|
| 中文標題 / 內文 | `"Microsoft JhengHei"` |
| 程式碼 | `"Consolas"` |

**字級**：內文 ≥ 18pt，標題 40–54pt，封面 60–80pt

---

## 母片代碼

```javascript
pres.defineSlideMaster({
  title: "NAVY",
  background: { color: "0A1628" },
  objects: [
    { text: { text: "DofLab", options: {
      x: 0.50, y: 0.18, w: 1.50, h: 0.28,
      fontFace: "Microsoft JhengHei", fontSize: 14,
      color: "E8EDF5", margin: 0,
    }}},
    { text: { text: "", options: {
      x: 0.50, y: 0.34, w: 12.33, h: 0.01,
      fill: { color: "1E3050" },
    }}},
    { text: { text: "", options: {
      x: 0.50, y: 6.97, w: 12.33, h: 0.01,
      fill: { color: "1E3050" },
    }}},
    { text: { text: "劉瑞弘 · 智慧自動化工程系 · 國立勤益科技大學 · DofLab", options: {
      x: 0.50, y: 7.10, w: 9.00, h: 0.25,
      fontFace: "Microsoft JhengHei", fontSize: 10,
      color: "6B8BB5", margin: 0,
    }}},
    { placeholder: { options: {
      name: "chapter", type: "body",
      x: 7.50, y: 0.18, w: 5.33, h: 0.28,
      fontFace: "Microsoft JhengHei", fontSize: 11,
      color: "6B8BB5", align: "right", margin: 0,
    }}},
    { placeholder: { options: {
      name: "slidenum", type: "slidenum",
      x: 11.50, y: 7.10, w: 1.33, h: 0.25,
      fontFace: "Microsoft JhengHei", fontSize: 10,
      color: "6B8BB5", align: "right", margin: 0,
    }}},
  ],
});
```
