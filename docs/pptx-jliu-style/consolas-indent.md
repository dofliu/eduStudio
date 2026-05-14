# consolas-indent · Consolas 縮排陷阱

程式碼頁製作前必讀。

---

## 問題說明

pptxgenjs 的 `charSpacing`（字距）在 `Consolas` 字型上**完全無效**。
同理，`indentLevel` 和 margin 設定對等寬字型也無法產生視覺縮排。

---

## 正確做法：用 `x` 位置偏移模擬縮排

```javascript
// 縮排一層（約 0.3" per level）
const INDENT = 0.30; // 吋，每層縮排量

slide.addText("function calculate() {", {
  x: 0.83, y: 1.20, w: 11.0, h: 0.35,
  fontFace: "Consolas", fontSize: 18,
  color: "F4EEE3",
});

// 縮排一層
slide.addText("  const result = a + b;", {
  x: 0.83 + INDENT, y: 1.55, w: 11.0, h: 0.35,
  fontFace: "Consolas", fontSize: 18,
  color: "F4EEE3",
});

// 縮排兩層
slide.addText("  return result;", {
  x: 0.83 + INDENT * 2, y: 1.90, w: 11.0, h: 0.35,
  fontFace: "Consolas", fontSize: 18,
  color: "F4EEE3",
});
```

---

## `charSpacing` 正確使用範圍

| 字型 | charSpacing 是否有效 | 建議值 |
|---|---|---|
| Noto Serif TC / Georgia | ✅ 有效 | 頁腳：3–5pt；標題：6–10pt |
| EB Garamond | ✅ 有效 | 題眉：6–8pt |
| Microsoft JhengHei | ✅ 有效 | 標題：4–8pt |
| **Consolas** | ❌ 無效 | 不要設定，改用 `x` 偏移 |

---

## charSpacing 數值範圍（pt 單位）

> ⚠️ `charSpacing` 單位是 **pt（點）**，不是 em！

| 效果 | 值 | 適用位置 |
|---|---|---|
| 微展開 | 3–5 | 頁腳、頁碼 |
| 標準展開 | 6–8 | 題眉、標籤 |
| 寬展開 | 9–12 | 封面英文副標 |
| ❌ 過寬 | > 15 | 禁止（字母會分開） |

---

## 快速自查

寫完程式碼頁後，確認每一行 `addText` 若用了 `Consolas`：
- [ ] 沒有設定 `charSpacing`
- [ ] 縮排用 `x` 偏移，不用空白字元或 margin
- [ ] `fontSize` ≥ 18pt
