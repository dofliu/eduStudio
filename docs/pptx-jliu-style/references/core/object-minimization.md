# 物件最小化(策略 B)

**每個視覺元素盡量用單一物件完成,不堆疊色塊。**

這讓使用者在 PowerPoint 手動修改時更方便——點一下就選到完整區塊,不需要逐層解開多個物件。

---

## 做法:用 `fill` 屬性取代獨立 Shape 背景

```javascript
// ❌ 舊方式:2 個物件(Shape 背景 + Text)
slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: "2D6A4F" } });
slide.addText("標籤文字", { x, y, w, h, color: "FFFFFF" });

// ✅ 策略 B:1 個物件(Text 自帶 fill)
slide.addText("標籤文字", {
  x, y, w, h,
  color: "FFFFFF", bold: true,
  fill: { color: "2D6A4F" },        // 背景色直接在文字框上
  line: { pt: 1, color: "1B4332" }  // 邊框也可以直接加
});
```

---

## 各頁面物件數對照

| 頁面類型 | 舊方式 | 策略 B | 節省 |
|---|---|---|---|
| 學習目標(5列) | ~20 個 | ~10 個 | 50% |
| 學習地圖(4卡) | ~20 個 | ~8 個 | 60% |
| 內容頁(標題+3項) | ~12 個 | ~6 個 | 50% |
| 整份 20 頁簡報 | ~200 個 | ~100 個 | 50% |

---

## 例外情況(仍需獨立 Shape)

- 純裝飾色塊(無文字):分隔線、背景區域
- 圓形圖示底圈(`OVAL`)
- 需要精確對齊的幾何圖形
- LaTeX 公式 PNG 圖片背後的白底框(圖片無法 fill)
