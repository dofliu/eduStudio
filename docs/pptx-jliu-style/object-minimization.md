# object-minimization · 物件最小化（策略 B）

所有主題通用。第一頁製作前讀一次。

---

## 核心原則：單一 Text + fill 完成視覺元素

**不要堆疊**：Shape 背景 + Text 物件兩個 → 改成一個 Text 物件加 `fill`

```javascript
// ❌ 錯誤：兩個物件
slide.addShape(pptx.ShapeType.rect, { x, y, w, h, fill: { color: "1E3050" } });
slide.addText("標題文字", { x, y, w, h, color: "FFFFFF" });

// ✅ 正確：一個物件
slide.addText("標題文字", {
  x, y, w, h,
  fill: { color: "1E3050" },
  color: "FFFFFF",
});
```

---

## 每張投影片物件數量目標

| 主題 | 目標上限 | 母片固定 | 可用內容物件 |
|---|---|---|---|
| 所有主題 | **≤ 12** | 6（logo + hairline×2 + footer + chapter + slidenum） | 6–8 |

---

## 允許使用 `fill` 的物件

| 場景 | 做法 |
|---|---|
| 色塊標題列 | `addText("", { fill: { color: "..." } })` 純色塊無文字 |
| 強調標籤 | `addText("關鍵詞", { fill: { color: "..." }, color: "..." })` |
| 程式碼底色 | `addText(code, { fill: { color: "1E1A14" }, color: "F4EEE3" })` |
| hairline 分隔線 | `addText("", { fill: { color: "..." }, h: 0.01 })` |

---

## 禁止的做法

- ❌ `addShape()` + `addText()` 疊在同位置
- ❌ 用多個 hairline Shape 裝飾（每頁最多 3 條）
- ❌ 為了「強調效果」在文字下方疊透明矩形
- ❌ 用 `addImage()` 做純色背景（改用 `fill`）

---

## 策略 B 速查

> **每個視覺元素 = 一個 pptxgenjs 物件**
> 能合併就合併，不能合併就問自己「這個物件是否必要？」
