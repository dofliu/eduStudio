# 封面頁 (cover)

每章第一頁。傳達:**章節編號 + 主題 + 副標 + 學習時間 + 講者資訊**。

---

## 結構元素

```
┌────────────────────────────────────────────────┐
│  CHAPTER FIVE                                  │  ← 英文章節編號(小、字距加寬)
│                                                │
│  穩定性分析                                     │  ← 大標(襯線、極大字)
│                                                │
│  只看多項式係數,就能判斷系統會不會失控。           │  ← 副標一句話
│                                                │
│  ─────────                                     │  ← 細分隔線
│                                                │
│  《現代自動控制:從經典到智慧》                    │  ← 書名 / 課程名(義大利體)
│  第二週 | 六小時課程 | 三節課 + 練習              │  ← 課程資訊
│                                                │
│  劉瑞弘                                         │  ← 講者
│  國立勤益科技大學 · 智慧自動化工程系               │  ← 單位
└────────────────────────────────────────────────┘
```

---

## Journal 風格實作

```javascript
function renderCover(slide, pres, {chapterEN, chapterTitle, subtitle, bookTitle, schedule, author, affiliation}) {
  // 整頁深色背景
  slide.background = { color: "1A2E1F" };

  // 英文章節編號(小、字距大、上方)
  slide.addText(chapterEN, {     // 例:"C H A P T E R   F I V E"
    x: 0.8, y: 1.0, w: 12, h: 0.5,
    fontFace: "Georgia",
    fontSize: 14,
    charSpacing: 10,
    color: "B8935A",             // 暖金
    italic: true,
  });

  // 章節主標題(超大、襯線)
  slide.addText(chapterTitle, {  // 例:"穩定性分析"
    x: 0.8, y: 1.8, w: 12, h: 1.5,
    fontFace: "Noto Serif CJK TC",
    fontSize: 72,
    charSpacing: 10,
    color: "FBF8F1",             // 米白
    bold: false,
  });

  // 副標一句話(墨綠灰、襯線)
  slide.addText(subtitle, {      // 例:"只看多項式係數,就能判斷系統會不會失控。"
    x: 0.8, y: 3.5, w: 12, h: 0.6,
    fontFace: "Noto Serif CJK TC",
    fontSize: 20,
    color: "C9C0A5",             // 暖米灰
    italic: false,
  });

  // 細分隔線
  slide.addShape(pres.shapes.LINE, {
    x: 0.8, y: 4.4, w: 1.5, h: 0,
    line: { color: "B8935A", pt: 1 }
  });

  // 課程資訊區
  slide.addText(bookTitle, {     // 例:"《現代自動控制:從經典到智慧》"
    x: 0.8, y: 4.7, w: 12, h: 0.5,
    fontFace: "Noto Serif CJK TC",
    fontSize: 16,
    color: "FBF8F1",
    italic: true,
  });
  slide.addText(schedule, {      // 例:"第二週 | 六小時課程 | 三節課 + 練習"
    x: 0.8, y: 5.2, w: 12, h: 0.4,
    fontFace: "Noto Serif CJK TC",
    fontSize: 14,
    color: "C9C0A5",
    charSpacing: 4,
  });

  // 講者(底部)
  slide.addText(author, {        // 例:"劉瑞弘"
    x: 0.8, y: 6.4, w: 6, h: 0.4,
    fontFace: "Noto Serif CJK TC",
    fontSize: 16,
    color: "FBF8F1",
  });
  slide.addText(affiliation, {   // 例:"國立勤益科技大學 · 智慧自動化工程系"
    x: 0.8, y: 6.85, w: 12, h: 0.35,
    fontFace: "Noto Serif CJK TC",
    fontSize: 12,
    color: "C9C0A5",
    charSpacing: 3,
  });
}
```

---

## 風格差異重點

| 元素 | Forest/Navy | Frieren/Naruto | Journal |
|---|---|---|---|
| 背景 | 全深色 | 淺色 + SVG 裝飾 | 暗墨綠純色 |
| 主標字體 | 微軟正黑體 粗 | 微軟正黑體 粗 | 思源宋體 細、charSpacing |
| 主標大小 | 54–60pt | 54–60pt | 60–72pt(更大) |
| 裝飾 | 直線色條 | 魔法陣/螺旋紋 | 細分隔線 + 暖金點綴 |
| 講者位置 | 右下角小字 | 右下角小字 | 左下、襯線、明確 |

---

## ❌ 封面常見錯誤

- 章節編號用阿拉伯數字「5」(Journal 用英文「FIVE」更有書冊感)
- 主標加粗 + 加底線雙重強調(Journal 只用 charSpacing,不加粗)
- 副標太長(超過一行就壓縮版面,應 ≤ 30 字)
- 沒有日期/週次資訊(學生無法定位這是哪一週)
- **封面不加雙語頁腳**(Journal 規則:封面與 END 頁不放頁腳)

---

## 不放頁腳的頁

封面頁與 END 頁是 Journal 唯二**不放雙語頁腳和頁碼**的頁面,以保持書封與結束的儀式感。
