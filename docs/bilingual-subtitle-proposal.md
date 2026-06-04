# 雙語字幕 — proposal (GATE: 翻譯 API)

> 狀態: **proposal / STOP 等劉老師決策 + 開翻譯額度**
> 對應 backlog: TODO.md ✨ 新功能 backlog「雙語字幕 (🟡 中)」(2026-06-03 用戶挑選進場)
> 撰寫: hourly routine, 2026-06-04
> 0 production code 改動 — 純設計文件。

## 目標

既有 SRT (中文 narration → `core/srt.py build_srt`) 出第二語言 (英 / 日) 雙語字幕,
讓影片觸及非中文觀眾 (YouTube 國際化 + 課程網站外籍生)。

## 為什麼是 GATE

翻譯本身需要 **Gemini / Google Translate API** — routine offline-first 不自主燒額度。
且 AI 翻譯是估值, 命中硬規則「AI 產出未經 review 不當最終答案」→ 翻譯結果要停
`awaiting_review` 人工校。故翻譯流程整段 STOP 等用戶開額度 + 確認 review gate。

**但「SRT 雙語格式 + 渲染」是 offline 可先做的** (見下方「offline 可先做」段) —
前提是先把三個架構決策拍板, 否則做了也是猜。

---

## 架構決策 (要劉老師選, routine 不自主決定)

### 決策 1 — 雙語呈現格式

| 選項 | 做法 | 優點 | 缺點 |
|---|---|---|---|
| **A 單檔交錯雙行** | 同一 `.srt`, 每個 cue 兩行 `中文\n譯文` | 一個檔、一次燒錄、所有播放器通吃 | 字幕帶溢出 (見決策 2) |
| **B 雙獨立軌** | `name.zh.srt` + `name.en.srt` 兩檔 | 不溢出、YouTube 可上多軌讓觀眾切換、燒一軌另出獨立軌 | 燒錄只能挑一軌、要管兩檔命名 |
| **C ASS 雙樣式** | `.ass` 上中下兩 style 不同字級/色 | 視覺最佳、可精準控雙語位置 | 要從 SRT 轉 ASS、force_style 路線整段改、複雜度高 |

**建議 B**: 跟既有架構衝突最小 (build_srt 換 narration 欄位重跑即得第二軌, 幾乎 0 新
code), 避開字幕帶溢出, 又能吃 YouTube 多字幕軌原生功能 (publish.py 上傳時帶
`caption` track)。燒錄維持燒中文一軌 (現況不變), 英/日軌只上傳 YouTube 供切換。

### 決策 2 — 字幕帶溢出約束 (只有選 A / C 才要解)

現況硬約束 (實測值, 不是猜):
- 字幕帶高 **180px** (`core.visuals.SUBTITLE_BAND_HEIGHT`)
- ffmpeg 燒字幕 `FontSize=22` / 1080p / `MarginV=40` (pipeline.py `_build_hardsub_cmd`)
- N3 已把單 cue 上限壓到 `SUBTITLE_CUE_CHAR_BUDGET=40` ≈ **2 行 CJK** 剛好塞滿帶

→ 雙語 (中文 1~2 行 + 譯文 1~2 行 = 最多 **4 行**) **必然頂出 180px 帶**。

選 A/C 必須二擇一:
- (a) 縮字級 (22→15?) — 譯文那行小一號, 但中文也跟著小, 老人/手機看不清
- (b) 加高字幕帶 (180→300?) — 連動 `CONTENT_BOTTOM` / letterbox-fit / 所有
  renderer 的 `canvas_h` 定位 (icon/formula 疊放都吃這常數), 牽動面大
- (c) 只燒一語 + 另一語出獨立軌 — 這其實就退回選 B

選 **B 直接繞過整個決策 2** (各軌獨立燒/上傳, 不疊)。這是建議 B 的主因。

### 決策 3 — cue 對齊 (翻譯 ↔ 時間槽)

翻譯是 **per-step / per-句** 產出, 但字幕時間槽是 **per-cue** (N3 把長句切成多 cue)。
中文一句切 3 cue, 英文譯文可能只 1~2 個子句 → cue 數不等, 時間對不齊。

對齊策略 (選 B 時較單純, 因兩軌獨立切):
- **B 路線**: 第二語言 narration **整段** 經 `narration_to_cues` 自己切自己的 cue,
  時間用「該 step 的 start/end 平均分配」(跟中文軌同 step 邊界, 但 cue 內部各切各的)。
  → 不需逐 cue 對齊, 只需 step 邊界對齊 (build_srt 已是 per-step 切, 天然對得上)。
- A/C 路線才需要逐 cue 強制對齊 (難, 子句數不等要補空/合併) — 又一個選 B 的理由。

---

## offline 可先做 (拍板決策 1 = B 之後, routine 可自主做, 不需翻譯額度)

選 B 後, 第二語言軌 = 拿「已翻譯好的第二語言 narration」重跑 `build_srt`。核心其實
**已存在** (build_srt 跟語言無關)。要補的 offline 小工程:

1. **`build_bilingual_srt_tracks(steps, durations, *, secondary_field="narration_en")`**
   (core/srt.py 加薄 helper) — 對同一組 steps/durations, 分別用 `narration` 與
   `secondary_field` 跑兩次 `build_srt`, 回 `{"zh": srt_str, "en": srt_str}`。
   純確定性、可離線測 (餵假 step dict 含 `narration` + `narration_en`)。
2. **publish.py 上傳第二字幕軌** — YouTube Data API `captions.insert` 帶 language code。
   (這段碰 YouTube OAuth, 屬「等用戶討論安全模型」, 跟翻譯額度一起 STOP。)
3. **schema 透傳** — deck/exam step 加 optional `narration_en` 欄位 (向後相容, 無此欄
   NoOp), `core/deck.py` flatten 保住。沿用 LaTeX `slide.formula` / icon_overlay 同套
   「optional 欄位 normalize + flatten 透傳」pattern。

**仍是 GATE 的**: 產出 `narration_en` 的翻譯步驟 (Gemini/Translate 額度 + review gate)。
helper #1 拿到翻譯後才有東西可切, 但 helper 本身 (吃假資料) 可先寫 + 測。

## 驗收 (解鎖後)

- helper 對 `narration`-only step (無 `narration_en`) → 只回 zh 軌, 不炸 (向後相容)。
- 雙欄 step → zh/en 兩軌 cue 數各自獨立、step 邊界時間對齊 (en 軌第 k step 的
  start == zh 軌第 k step 的 start)。
- 翻譯結果停 `awaiting_review` (硬規則, 不可繞)。

## 要劉老師決定

1. **格式選 A / B / C** (建議 B — 衝突最小、繞過溢出、吃 YouTube 多軌)。
2. **翻譯後端** (Gemini 2.5 Flash 既有管線 / Google Translate API) + 開額度。
3. 確認翻譯走 `require_review` (預設要, 學術誠信)。

拍板 1 = B 後, routine 可自主做 helper #1 + schema 透傳 (純 offline, 不碰額度);
#2 上傳軌 + 翻譯步驟等額度 + OAuth 安全模型討論。
