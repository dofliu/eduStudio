---
name: repo-intro-video
description: 把任何 repo/專案做成一支有動畫張力的介紹影片(MP4),長度可指定 30 秒短版~3 分鐘完整版,背景音樂可選(使用者提供的音樂/安靜合成氛圍/無聲留給後製):分析程式碼與 README 萃取賣點 → 分鏡 → 產生 HTML 動畫場景 → 無頭瀏覽器逐格渲染 → ffmpeg 轉場串接 + 配樂。Use this whenever the user asks for an intro/promo/demo/explainer video of a repository or project — 「幫這個 repo 做介紹影片」「做一支專案宣傳片/形象片/announcement video」「introduce this project as a video」「展示主要功能的影片」— even if they don't say "video" explicitly but want the project "presented/showcased with motion". Also use to REGENERATE or tweak a video previously made by this skill (change scenes, music, duration, loudness).
compatibility: 需要 python3 + playwright(pip)+ 任一 Chromium(版本不合時設 CHROMIUM_PATH)+ ffmpeg;中文字卡需系統 CJK 字型(如 fonts-noto-cjk)
---

# repo-intro-video — 把 repo 變成介紹影片

產出:一支 1080p30 的 MP4,由 HTML 動畫場景以 xfade 轉場串接而成。**長度可指定**:
30 秒短版(4-5 景)~ 60-75 秒標準版(6-9 景)~ 最長 3 分鐘完整版(15-18 景),
伸縮原則見 `references/scene_design.md`。**音樂可指定**:合入使用者提供的背景音樂、
安靜合成氛圍、或無聲(留給使用者後製)。場景是 standalone HTML,之後可單獨改字重渲,
不必重做整支。

## 流程

### 0. 環境自檢(30 秒)

```bash
python3 -c "import playwright" && which ffmpeg && fc-list :lang=zh | head -1
```
缺 playwright → `pip install playwright`(瀏覽器用系統既有的,**不要** `playwright install`);
Chromium 與 playwright 版本不合時,找到瀏覽器執行檔後 `export CHROMIUM_PATH=/path/to/chrome`。

### 1. 讀懂 repo(5 分鐘,別跳過)

讀 README、主要模組、docs/。要抓的是:**一句話定位**、**3~5 個對使用者有感的功能**
(不是架構細節)、**一個差異化主張**(這專案最敢說出口的那句話)、CTA 資訊(repo 網址/作者)。
數字有說服力就用(測試數、支援格式數、模型數)。

### 2. 規格兩問 + 分鏡表 → 給使用者過目

先確認兩個規格(使用者已在需求裡講明的就不再問):

1. **長度**:30 秒短版 / 60-75 秒標準 / 最長 3 分鐘完整版?(預設 60-75 秒)
2. **背景音樂**:(a) 使用者提供音樂檔(mp3/wav 皆可,推薦)(b) 安靜合成氛圍
   (c) **無聲** — 使用者要自己後製配樂時選這個,交無聲版是正解不是偷懶。(預設無聲)

再按 `references/scene_design.md` 的敘事公式(與長度伸縮表)排景,貼一張
「景名/一句話/秒數/轉場」的表格讓使用者確認方向(改分鏡便宜,改成品貴)。
使用者沒空回就用預設值直接做,交付時說明怎麼改。

### 3. 寫場景 HTML

- 建工作目錄(建議 `<repo>/promo/` 或暫存區),每景複製 `assets/scene_template.html` 改內容。
- 先讀 `references/scene_design.md` 的**陷阱清單** — 每一條都是真實踩過的雷,
  特別是「`.in`/`.pop` 會蓋掉置中 transform」與「膠囊要 nowrap」。
- 功能景做「迷你 mock」(進度條、卡片、黑板、面板…),不要只放標語文字。
- 寫 `storyboard.json`:

```json
{
  "fps": 30, "width": 1920, "height": 1080, "xfade": 0.6,
  "scenes": [
    {"file": "scene01_open.html",  "duration": 7, "transition": "fade"},
    {"file": "scene02_feature.html","duration": 7, "transition": "circleopen"},
    {"file": "scene03_climax.html", "duration": 8, "transition": "fade"},
    {"file": "scene04_cta.html",    "duration": 7}
  ]
}
```
`transition` 是「進入下一景」的刀;最後一景不填。

### 4. 渲染 + 自查(必做)

```bash
python <skill>/scripts/render_scenes.py storyboard.json --workdir work/intro
```
每景會產出 `check_<scene>.png`(85% 時間點抽查格)。**逐張 Read 檢查**:文字溢出、元素相撞、
置中跑位、換行斷字。有問題改該景 HTML 後單景重渲:

```bash
python <skill>/scripts/render_scenes.py storyboard.json --workdir work/intro --only scene03_climax
```
沒看過抽查格就出片 = 把排版 bug 直接交給使用者。

### 5. 串接出片

依步驟 2 選定的音樂模式出片:

```bash
# (a) 使用者給了音樂檔(短於片長會自動 1.5s 交叉淡接循環,尾 3s 淡出)
python <skill>/scripts/assemble_video.py storyboard.json --workdir work/intro \
    --out intro.mp4 --music bgm.mp3

# (b) 安靜合成氛圍(暖 pad + 稀疏心跳,-23 LUFS)
python <skill>/scripts/assemble_video.py storyboard.json --workdir work/intro --out intro.mp4 --bed

# (c) 無聲(使用者要後製配樂時的正解)
python <skill>/scripts/assemble_video.py storyboard.json --workdir work/intro --out intro.mp4
```
響度:音樂主導預設 -16 LUFS;使用者要「背景一點/小聲一點」→ `--loudness -20`。
`--sfx` 疊極輕轉場氣音,預設關(有音樂通常不需要)。

### 6. 驗收 + 交付

```bash
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 intro.mp4
ffmpeg -i intro.mp4 -af ebur128 -f null - 2>&1 | grep "I:" | tail -1   # 有音軌時看響度
```
把 MP4 交給使用者,並附一段「怎麼調」:換文案=改該景 HTML 重渲單景、換音樂/響度=只重跑
assemble(秒級)、加旁白可後製。場景 HTML + storyboard.json 一併保留(或 commit),
下次微調不用重做。

## 品質底線

- 交付前每景抽查格都看過;成片時長 = 分鏡表總長(誤差 <0.5s)。
- 中文內容用繁體、字卡文案短句化(標題 ≤14 字,badge ≤8 字)。
- 音訊寧靜勿吵:無音樂就無聲,絕不加持續性噪聲層(詳見 scene_design.md 音訊心法)。
