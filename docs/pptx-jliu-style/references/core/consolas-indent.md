# Consolas 字體忽略 margin(縮排陷阱)

**經實測確認:`fontFace: "Consolas"` 的文字框完全忽略 `margin` 設定。**

程式碼區塊、公式、等寬文字如果需要左縮排,**必須用 `x` 位置偏移**,不能靠 `margin`。

---

## ❌ 對 Consolas 無效

```javascript
// margin 被完全忽略,文字仍貼左
slide.addText("x₁=pos_x  x₂=vel_x", {
  x: 0.4, w: 12.5, fontFace: "Consolas",
  margin: [0, 0, 0, 36]   // 完全無效!
});
```

## ✅ 正確做法:背景框 + x 偏移的文字框分開

```javascript
// 1. 先畫白底框(用獨立 Shape,因為這是裝飾)
slide.addText("", {
  x: 0.4, y, w: 12.53, h: 0.6,
  fill: { color: "F8FAFC" },
  line: { pt: 0.5, color: "DDDDDD" }
});

// 2. 再放等寬文字,x 往右偏 0.5 吋產生縮排
slide.addText("x₁=pos_x  x₂=vel_x", {
  x: 0.9,        // ← 往右移 0.5 吋產生縮排
  y, w: 12.03, h: 0.6,
  fontFace: "Consolas",
  valign: "middle",
  margin: 0
});
```

---

## 影響範圍

| 字體 | margin 是否生效 |
|---|---|
| Microsoft JhengHei(微軟正黑體) | ✓ 正常 |
| Noto Serif CJK TC(思源宋體) | ✓ 正常 |
| Georgia(英文襯線) | ✓ 正常 |
| **Consolas(等寬)** | ✗ **失效** |
| Courier New(等寬) | 推測同 Consolas,需實測 |

一般中文/襯線字體的 `margin` 正常運作,只有等寬字體有此問題。

---

## 另一個相關陷阱:charSpacing 對 Consolas 也無效

`charSpacing`(字距加寬)在 Consolas 上也不會生效。等寬字體的字距是固定的,無法用 `charSpacing` 調整。需要視覺上的字距加寬時,直接在字串中插入空格。
