# forest · 深綠教學風

> 適用於程式設計、基礎課程、工程概論。
> 視覺氣質：**深色底、護眼深綠、適合長時間教學使用**。

---

## 色彩 token

| 用途 | Hex | pptxgenjs |
|---|---|---|
| 深綠背景 | `#1A2E1A` | `"1A2E1A"` |
| 前景白 | `#F5F5F0` | `"F5F5F0"` |
| 亮綠強調 | `#5DB86C` | `"5DB86C"` |
| 次文灰綠 | `#8FAF8F` | `"8FAF8F"` |
| hairline | `#2E4A2E` | `"2E4A2E"` |

---

## 字體

| 用途 | `fontFace` |
|---|---|
| 中文標題 / 內文 | `"Microsoft JhengHei"` |
| 英文 / 數字 | `"Microsoft JhengHei"` |
| 程式碼 | `"Consolas"` |

**字級**：內文 ≥ 18pt，標題 40–54pt，封面 60–80pt

---

## 母片代碼

```javascript
pres.defineSlideMaster({
  title: "FOREST",
  background: { color: "1A2E1A" },
  objects: [
    { text: { text: "DofLab", options: {
      x: 0.50, y: 0.18, w: 1.50, h: 0.28,
      fontFace: "Microsoft JhengHei", fontSize: 14,
      color: "F5F5F0", margin: 0,
    }}},
    { text: { text: "", options: {
      x: 0.50, y: 0.34, w: 12.33, h: 0.01,
      fill: { color: "2E4A2E" },
    }}},
    { text: { text: "", options: {
      x: 0.50, y: 6.97, w: 12.33, h: 0.01,
      fill: { color: "2E4A2E" },
    }}},
    { text: { text: "劉瑞弘 · 智慧自動化工程系 · 國立勤益科技大學 · DofLab", options: {
      x: 0.50, y: 7.10, w: 9.00, h: 0.25,
      fontFace: "Microsoft JhengHei", fontSize: 10,
      color: "8FAF8F", margin: 0,
    }}},
    { placeholder: { options: {
      name: "chapter", type: "body",
      x: 7.50, y: 0.18, w: 5.33, h: 0.28,
      fontFace: "Microsoft JhengHei", fontSize: 11,
      color: "8FAF8F", align: "right", margin: 0,
    }}},
    { placeholder: { options: {
      name: "slidenum", type: "slidenum",
      x: 11.50, y: 7.10, w: 1.33, h: 0.25,
      fontFace: "Microsoft JhengHei", fontSize: 10,
      color: "8FAF8F", align: "right", margin: 0,
    }}},
  ],
});
```
