# DofLab 個人簡報風格 · 整合包 (v2)

劉瑞弘老師個人簡報風格，**十套主題** + 共通母片骨架，可整合進現有的 `pptx-jliu-style` skill。
v1（沉穩五套）+ v2（衝擊五套）涵蓋從學術期刊到街機霓虹的完整光譜。

## 檔案結構

```
.
├── DofLab 簡報風格.html         ← v1 預覽（5 沉穩風格 × 7 頁型，41 張）
├── DofLab 簡報風格 v2.html      ← v2 預覽（5 衝擊風格 × 5 頁型，26 張）
├── DofLab Logo.html             ← 六個 logo 方向實驗
├── styles.css                   ← v1 預覽 CSS
├── styles-v2.css                ← v2 預覽 CSS
├── deck-stage.js                ← 投影片框架
└── specs/
    └── themes/
        ├── dof-editorial.md     ← v1 · 雜誌編輯風（暖色系）
        ├── dof-podium.md        ← v1 · 講壇風 / TED 感（冷灰）
        ├── dof-notebook.md      ← v1 · 札記風 / 讀書會（霧暖）
        ├── dof-shinobi.md       ← v1 · 忍者熱血（深夜墨 + 朱印紅）
        ├── dof-elven.md         ← v1 · 魔法幻境（月光紫 + 燙金）
        ├── dof-zine.md          ← v2 · 獨立雜誌海報（黃紅黑撞色）
        ├── dof-arcade.md        ← v2 · 街機霓虹 8-bit（深夜霓虹）
        ├── dof-risograph.md     ← v2 · Riso 兩色疊印（藍 + 粉）
        ├── dof-supergraphic.md  ← v2 · Pentagram 大色塊瑞士幾何
        └── dof-brutalist.md     ← v2 · 野獸派宣言（黑白警示紅）
```

## 十套風格速覽

### v1 · 沉穩家族（全襯線、極簡、學者氣質）

| 代號 | 風格 | 主場景 | 色調 |
|---|---|---|---|
| `dof-editorial` | 雜誌編輯風 | 業界演講 / 對外分享 / Demo Day | 暖色（赭橘 · 米金）|
| `dof-podium` | 講壇風 · TED 感 | 研究發表 / Conference / Keynote | 冷灰（霧藍）|
| `dof-notebook` | 札記風 | 讀書會 / 思考筆記 | 霧暖（苔綠 · 粉藕）|
| `dof-shinobi` | 忍者熱血 | 黑客松 / 動員會 / 出陣前 | 深夜墨 + 朱印紅 |
| `dof-elven` | 魔法幻境 | 哲學講座 / 認知科學 / 文學主題 | 月光紫 + 燙金 |

### v2 · 衝擊家族（粗 sans、撞色、玩心或立場）

| 代號 | 風格 | 主場景 | 色調 |
|---|---|---|---|
| `dof-zine` | 獨立雜誌海報 | 年度回顧 / 宣言式 talk | 螢光黃 · 撞色紅 · 黑 |
| `dof-arcade` | 街機霓虹 8-bit | 黑客松開幕 / 技術 demo | 深夜霓虹（青 · 洋紅）|
| `dof-risograph` | Riso 兩色疊印 | 工作坊 / 跨界活動 | 油墨藍 + 螢光粉 |
| `dof-supergraphic` | Pentagram 大色塊 | 品牌簡介 / 企業合作 | 三原色 + 黑白 |
| `dof-brutalist` | 野獸派宣言 | 觀點 talk / 批判演講 | 黑白 + 警示紅 |

## Logo 系統

`DofLab Logo.html` 提供六個方向，皆以 **DoF = Degrees of Freedom**（6 自由度 = 機構/機器人核心概念）為設計基礎：

| # | 方向 | 描述 |
|---|---|---|
| 01 | 6-DoF Constellation | 六個圓點 (3 平移 + 3 旋轉)，最忠於概念 |
| 02 | Axis Cross | 三軸座標符號，工程感最強 |
| 03 | Pure Wordmark | 純襯線文字，與 v1 五套相容 |
| 04 | Monogram D | D 形內藏 6 個自由度點，名片印章皆宜 |
| 05 | Round Seal | 圓章式設計，shinobi 與正式場合首選 |
| 06 | Vector Field | 向量場流體，控制論氣質 |

挑你喜歡的方向後告訴我，我可以做出 SVG / PNG 各尺寸版本。

## 整合進 `pptx-jliu-style` skill

### Step 1 · 主題路由表（加入十行）

```markdown
| `dof-editorial`    | 業界演講、對外分享、Demo Day      | themes/dof-editorial.md    |
| `dof-podium`       | 研究發表、Conference、Keynote    | themes/dof-podium.md       |
| `dof-notebook`     | 讀書會、輕鬆分享、思考筆記        | themes/dof-notebook.md     |
| `dof-shinobi`      | 黑客松（學者氣）、出陣訓話       | themes/dof-shinobi.md      |
| `dof-elven`        | 哲學講座、認知科學、文學主題      | themes/dof-elven.md        |
| `dof-zine`         | 年度回顧、宣言、重磅發表          | themes/dof-zine.md         |
| `dof-arcade`       | 黑客松開幕、技術 demo、競賽動員  | themes/dof-arcade.md       |
| `dof-risograph`    | 工作坊、跨界活動、設計工程橋接    | themes/dof-risograph.md    |
| `dof-supergraphic` | 品牌簡介、企業合作、招生大型場合  | themes/dof-supergraphic.md |
| `dof-brutalist`    | 觀點 talk、批判演講、call to action | themes/dof-brutalist.md   |
```

### Step 2 · 預設選擇邏輯

> 若使用者未指定：
>
> **正式 / 沉穩：**
> - 對外正式演講 / Demo / 招生 → `dof-editorial`
> - Conference / Keynote / 研究發表 → `dof-podium`
> - 讀書會 / Journal Club → `dof-notebook`
> - 動員會（學者氣質）→ `dof-shinobi`
> - 哲學 / 認知科學 → `dof-elven`
>
> **活潑 / 衝擊：**
> - 年度回顧 / 雜誌式 talk → `dof-zine`
> - 黑客松開幕 / Tech demo → `dof-arcade`
> - 跨界工作坊 / 設計工程橋接 → `dof-risograph`
> - 品牌簡介 / 企業合作 → `dof-supergraphic`
> - 觀點演講 / 立場宣言 → `dof-brutalist`
>
> **既有家族（不變動）：**
> - 課程教學（程式設計）→ `forest`
> - 課程教學（AI 進階）→ `navy`
> - 學術研究所 / 期刊感 → `journal`
> - 漫畫風格需明確指定（`frieren` / `naruto`）

### Step 3 · 複製 spec 檔

```
<skill_root>/references/themes/dof-editorial.md
<skill_root>/references/themes/dof-podium.md
<skill_root>/references/themes/dof-notebook.md
<skill_root>/references/themes/dof-shinobi.md
<skill_root>/references/themes/dof-elven.md
<skill_root>/references/themes/dof-zine.md
<skill_root>/references/themes/dof-arcade.md
<skill_root>/references/themes/dof-risograph.md
<skill_root>/references/themes/dof-supergraphic.md
<skill_root>/references/themes/dof-brutalist.md
```

## 設計理念註記

**v1 與 v2 是補集關係，不衝突**：v1 五套用同一語法（全襯線 + 極簡）做出五種「溫度」；v2 五套各自有完全不同的視覺語言（雜誌 / 街機 / Riso / 瑞士 / 野獸派），不假裝彼此相關。但兩個家族共享**同一個 logo 系統 + 同一個母片元素架構**，所以放在一起時仍然是「同一個 DofLab」。

**字體分組**：
- v1：思源宋 + EB Garamond + Consolas
- v2：Inter / Archivo Black / JetBrains Mono / Press Start 2P / Caveat / Work Sans / Noto Sans TC

**所有風格**都不畫人物剪影、不用 emoji（v2 允許 ASCII 符號 `► ★ ♥ ▲ ◯` 等作為裝飾，但不是 emoji）。
