# Journal 期刊風 · 完整規格

學術書冊質感的米白墨綠風格。**極簡留白 + 全襯線字體 + 雙語頁腳 + 印刷符號層次**。

適用情境:學術課程、研究所、書冊式教學、正式出版風。

---

## 設計哲學

不靠色塊堆疊,改用 **字距、留白、印刷符號** 建立層次。每一頁都要有書本的呼吸感,不要塞滿。

**鐵則**:
- 所有 rectRadius / 圓角一律 **0**
- 不使用陰影、不使用漸層
- 90% 版面只用米白 + 墨色 + 暗墨綠三色
- 強調用 charSpacing 加寬字距,不用粗體 + 變色組合
- 不使用色塊分割版面,改用印刷符號(§ — · → ✓ ⚠ ✗)

---

## 色票

| 用途 | HEX | 命名 |
|---|---|---|
| 主背景(內容頁) | `FBF8F1` | 米白 (cream) |
| 深色頁(封面/分隔/總結/END) | `1A2E1F` | 暗墨綠 (deep forest) |
| 主文色 | `2A2A2A` | 墨黑 |
| 副文色 | `5C6B5E` | 墨綠灰 |
| 強調色 | `2D5A3D` | 暗墨綠 (accent) |
| 細線色 | `D4CFC0` | 米灰(分隔線、邊框) |
| 黃金強調 | `B8935A` | 暖金(僅用於 highlight、不超過版面 2%) |
| 警示綠 ✓ | `4A7C59` | 成功/穩定 |
| 警示黃 ⚠ | `C9A961` | 臨界 |
| 警示紅 ✗ | `A14444` | 失敗/不穩定 |

---

## 字體

| 用途 | 字體 | 備註 |
|---|---|---|
| 中文 | **Noto Serif CJK TC** | 思源宋體繁體(若無→ fallback PMingLiU) |
| 英文 | **Georgia** | 跨平台可用 |
| 強調英文 | Playfair Display | editorial 感更強(若需要) |
| 程式碼 | Consolas | 例外(無合適襯線等寬中文) |

⚠️ **依賴提醒**:Journal 風格高度依賴 Noto Serif CJK TC。製作前提醒使用者確認字體安裝。

---

## 字體大小(Journal 比一般風格再大 1–2 pt)

| 元素 | pt | 備註 |
|---|---|---|
| 封面大標(章節名) | 60–72 | 留充足上下空白 |
| 頁面主標題 | 36–40 | 大字 + charSpacing |
| 副標題 / § 標題 | 24–28 | |
| 內文 | **20** | 一般風格 18,Journal 加大為 20 |
| 條列項目 | 18 | 一般風格 16,Journal 加大為 18 |
| 表格內文 | 14–16 | |
| 頁腳中文 / 英文 | 10–11 | charSpacing 4–6 |
| 頁碼 | 10 | |
| 章節提示「§ N · N 分鐘」 | 11 | charSpacing 5–8 |

---

## charSpacing 字距加寬(Journal 標誌性技法)

**單位是 pt(不是 em)。有效範圍 3–10**,超過會看起來怪。

| 用途 | charSpacing 值 |
|---|---|
| 章節大標(60pt+) | 8–10 |
| 頁面主標題(36–40pt) | 6–8 |
| 副標題(24–28pt) | 4–6 |
| 章節提示時間戳 | 5–8 |
| 頁腳語言標籤(中/EN) | 4–6 |

⚠️ **只用在標題/標籤/時間戳,不用在正文**。正文加字距會降低閱讀流暢度。

⚠️ **Consolas 字體上 charSpacing 完全失效**(等寬字體限制),不要嘗試。

---

## 雙語頁腳(Journal 標誌)

**每頁(除封面 / END 頁)都要有雙語頁腳**。三段獨立 Text 物件,不要串接成一個字串。

```javascript
// 中文標籤(左)
slide.addText("第 5 章 穩定性分析  目錄", {
  x: 0.4, y: 7.0, w: 6, h: 0.4,
  fontFace: "Noto Serif CJK TC",
  fontSize: 10,
  color: "5C6B5E",
  charSpacing: 4,
  italic: false,           // ← 必填,避免 LibreOffice 誤判
});

// 英文標籤(右)
slide.addText("Chap. 5 · Stability Analysis  整章目錄", {
  x: 6.5, y: 7.0, w: 5.5, h: 0.4,
  fontFace: "Georgia",
  fontSize: 10,
  color: "5C6B5E",
  italic: true,            // 英文用斜體更有期刊感
  charSpacing: 5,
  align: "right",
});

// 頁碼(最右)
slide.addText(`${String(pageNum).padStart(2, "0")}`, {
  x: 12.5, y: 7.0, w: 0.5, h: 0.4,
  fontFace: "Georgia",
  fontSize: 10,
  color: "5C6B5E",
  align: "right",
});
```

⚠️ **混合中英文時**,非斜體那段要明確寫 `italic: false`,否則 LibreOffice 可能把 Georgia 的羅馬體誤判為斜體。

⚠️ 頁碼用 `padStart(2, "0")` 補零(01, 02, ..., 12)以維持版面整齊。

---

## 印刷符號系統

不用色塊分割,改用印刷符號建立層次:

| 符號 | 用途 |
|---|---|
| `§` | 節號標記(§ 1.1、§ 2 等) |
| `·` | 標題分隔(章 · 主題) |
| `—` | 段落引言、長破折號 |
| `→` | 流程指向、下一章預告 |
| `✓` | 確認、達成、穩定 |
| `⚠` | 警告、臨界 |
| `✗` | 錯誤、不穩定 |
| `①②③④⑤` | 圓圈編號(章節內步驟) |
| `Q1 / A1` | 練習題編號 |

---

## 章節提示「§ N · N 分鐘」格式

每節分隔頁、學習地圖卡片頂部用此格式標示時間:

```
§ 1 · 1 2 0 分 鐘
```

注意:**數字之間用空格分開**(視覺上的字距),配合 charSpacing 形成期刊風。

```javascript
slide.addText("§ 1 · 1 2 0 分 鐘", {
  fontSize: 11,
  fontFace: "Noto Serif CJK TC",
  charSpacing: 7,
  color: "5C6B5E",
});
```

---

## 黃金法則框(quote-block)

Journal 風格的關鍵法則展示元件,類似書冊的 sidebar:

```javascript
// 邊框框(只用左側細線,不用全框)
slide.addShape(pres.shapes.LINE, {
  x: 1.0, y, w: 0, h: 1.5,
  line: { color: "2D5A3D", pt: 2 }
});

// 標籤(全大寫 + charSpacing)
slide.addText("黃 金 法 則", {
  x: 1.2, y, w: 4, h: 0.4,
  fontFace: "Noto Serif CJK TC",
  fontSize: 11,
  charSpacing: 8,
  color: "2D5A3D",
});

// 法則內文(serif 大字)
slide.addText("LTI 系統穩定 ⟺ 所有極點的實部 < 0", {
  x: 1.2, y: y + 0.5, w: 8, h: 0.8,
  fontFace: "Noto Serif CJK TC",
  fontSize: 22,
  color: "2A2A2A",
});

// 補充說明
slide.addText("只要有任何一個極點落在右半平面...", {
  x: 1.2, y: y + 1.3, w: 8, h: 0.4,
  fontSize: 14,
  color: "5C6B5E",
  italic: true,
});
```

---

## Journal 專屬頁型(學術書冊慣例)

Journal 比一般風格多用這些頁型,各有專屬 reference:
- 情境導入頁(章首真實案例)
- 小結頁「§ X 我們學了…」(每節結尾)
- 練習題頁 + 參考解答頁(題目解答分頁呈現)
- 下一章預告頁(獨立一頁引導)
- END 頁(章末引言收束)
- 公式速查頁(期末復習用單頁)

---

## 常見錯誤檢查

| ❌ 錯誤 | ✅ 正確 |
|---|---|
| rectRadius: 8(圓角) | rectRadius: 0(零圓角) |
| 用陰影增加層次 | 用 charSpacing + 留白 |
| 內文 18pt | 內文 20pt(Journal 加大) |
| 全部用粗體強調 | 用 charSpacing 加寬字距 |
| 中英文混用 fontFace 不分 | 中文 Noto Serif CJK TC,英文 Georgia 分開設定 |
| 頁腳串成一個字串 | 三段獨立 Text 物件 |
| 用色塊分割版面 | 用印刷符號(§ — · →) |
| Consolas 加 charSpacing | Consolas 不支援 charSpacing |

---

## LibreOffice 預覽提醒

LibreOffice 缺少 Noto Serif CJK TC,中文會 fallback 為無襯線。
**PDF 預覽看到中文是黑體不代表 PPTX 錯了**——PPTX 內部正確寫入字體名,Windows/Mac 上開啟時會正確顯示襯線。

---

## 參考檔交叉引用

- 字體大小細節 → `core/font-sizes.md`
- Consolas 縮排處理 → `core/consolas-indent.md`
- 物件最小化策略 → `core/object-minimization.md`
- LaTeX 公式渲染 → `references/math-typography.md`(若有)
- 各頁型具體實作 → `pagetypes/<頁型>.md`
