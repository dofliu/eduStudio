# SONG_MV_TRACK_RFC — 歌曲 → AI 生圖 MV 影片 (第 4 條 track)

> Status: **DRAFT — 待用戶 review 後拆 PR**
> 作者: routine /advance 討論產出 (2026-06-03, 劉老師互動 session)
> 決議基礎: forced alignment 走方案 2 (Demucs + WhisperX + 手動 review 層);
> 畫面走 AI 生圖逐段配; 正式做成第 4 source type。

---

## 1. 目的與定位

現有三條 track 的共通形狀是「文字內容 → TTS 合成旁白 → 字幕按字數切 → 渲染 → 上傳」。
歌曲 MV 打破其中兩個假設:

- **音訊不是合成的** — 歌曲音檔 (你用 Suno / Udio 之類 AI 產好) 直接當配樂, TTS 軌繞過。
- **字幕不是按字數切的** — 歌詞要跟節拍對齊, 時間軸來自 forced alignment 而非 cue budget。

但**上傳通道、require_review gate、渲染核心 (clip 串接 + 字幕帶 + 動態視覺) 全部沿用**。
因此它是第 4 個 `source_type = "song"`, 不是另起爐灶的新系統。

跟 V 軸 (動態視覺) 高度重疊:「逐段主動產生對應畫面」就是 icon/frame 基礎建設的放大版,
兩者共用 image_frames / ken burns 渲染路徑。

---

## 2. 輸入 / 輸出契約

**輸入**:
- 歌曲音檔 (`.mp3` / `.wav`)
- 歌詞純文字 (無 LRC 時間軸 — 這是已確認前提, 所以才需要對齊子系統)
- 視覺風格描述 (一句, 餵生圖統一風格, 例「賽博龐克霓虹城市夜景」)

**輸出**:
- MV 影片 (`.mp4`, 影片時長 == 歌曲時長)
- 歌詞字幕 (`.srt`, 由對齊產生)
- 上傳 YouTube (沿用 `publish.py`)

**中間產物 (進 review)**: `deck.json` 同級的 `song.json` — 對齊時間軸 + 逐段生圖 prompt
+ 圖片路徑, **全部停在 `awaiting_review` 等人工微調** (對齊飄移 / 圖不對題都在這層修)。

---

## 3. 與現有 pipeline 的對接

| 子系統 | song track 怎麼處理 | 重用 / 改 / 新增 |
|---|---|---|
| 音訊軌 | 歌曲音檔直接當配樂, 不跑 TTS | **改** — ffmpeg 合成時音軌來源切換 |
| 字幕軌 | 歌詞行 + 對齊時間戳 → SRT | **改** — 繞過 `narration_to_cues` 字數切分, 走對齊時間軸 |
| 對齊子系統 | Demucs 分人聲 + WhisperX word-level | **新增** (見 §4) |
| 畫面軌 | 逐段 Gemini 生圖 + ken burns | **延伸 V 軸** image_frames / ken burns |
| 渲染核心 | 每 segment 一 clip (背景圖 + 歌詞大字), 串接 | **重用** build_clip + 字幕帶 |
| review gate | song.json 停 awaiting_review | **重用** require_review (硬規則) |
| YouTube 上傳 | sections → 章節 (跟新功能「YT 章節」共用) | **重用** publish.py |

---

## 4. 三大子系統設計

### 4.1 歌詞對齊 (方案 2 — 已拍板)

**流程**: 歌曲音檔 → Demucs 剝人聲 `vocals.wav` → WhisperX word-level 對齊已知歌詞
→ 逐行 (理想逐字) 時間戳 → 寫進 song.json → **手動 review 層微調**。

- **Demucs** (`demucs`, htdemucs 模型): 把人聲從伴奏分離, 大幅降低樂器對對齊的干擾。
  本機 RTX 4080 GPU 跑。
- **WhisperX** (`whisperx`): word-level timestamp。對「已知完整歌詞」的對齊策略有兩條,
  **待 M0 spike 拍板**:
  - (a) WhisperX ASR 出時間軸 → 跟已知歌詞做文字對齊 (ASR 對唱歌咬字會錯, 但時間準);
  - (b) 把歌詞粗切成行 → WhisperX `align()` (wav2vec2) 強制對齊已知文字。
- **手動 review 層 (方案 3 併入)**: review UI 逐行顯示 `[start–end] 歌詞`, 可拖拉 / 微調 /
  整體 offset。**契合 `require_review` 硬規則** — 對齊是 AI 估值, 必須人工確認才渲染。

**GATE**: 新 dep `demucs` + `whisperx` (+ torch GPU)。方案 2 已拍板 = 授權加這組 dep,
但實裝前我會先確認 torch/CUDA 版本對得上 4080 環境 (寫進 M0)。

### 4.2 畫面生成 (AI 生圖逐段 — 已拍板)

- 每段歌詞 (verse / chorus, 或每 N 行) → 組 Gemini image prompt。
- **風格一致性**: 統一 style suffix + 固定種子 / 參考圖, 避免逐段畫風跳。
- 生圖 → ken burns (緩慢平移縮放) 填滿該段時長, 歌詞大字疊在上面。
- prompt 由 Gemini 文字模型先產 (依歌詞語意), 進 review 可改, 再送生圖。

**GATE**: Gemini image 額度 (跟 V2 同一個額度開關)。

### 4.3 音訊軌

- 影片總時長 = 歌曲時長 (ffmpeg `-i song.mp3` 直接當音軌)。
- 不做 TTS, 不做 narration。BGM mixing (新功能) 之後可共用這條音訊合成路徑。

---

## 5. song schema (草稿)

```json
{
  "track_type": "song",
  "song_title": "...",
  "audio_path": "jobs/<id>/song.mp3",
  "visual_style": "統一視覺風格 prompt",
  "segments": [
    {
      "id": "seg_1",
      "lines": ["歌詞第一行", "第二行"],
      "start": 0.0,
      "end": 12.3,
      "image_prompt": "(Gemini 依語意產, 可 review 改)",
      "image_path": null,
      "reviewed": false
    }
  ]
}
```

`start`/`end` 由對齊填、`image_prompt`/`image_path` 由生圖填 — **三者皆 AI 估值, 全進 review**。
schema dispatch 沿用既有 type guard 慣例 (新增 `is_song_schema` 判 `track_type == "song"`,
不硬寫 `if "segments" in x`)。

---

## 6. 分階段實作 (一階段一 PR, 守 ≤3 檔紀律不適用大 PR — 這是新 track 級)

- **M0 POC (spike)**: 裝 demucs + whisperx, 確認 4080 CUDA 跑得動; 手動歌詞 + 手填時間軸,
  1 首歌走通到 mp4 (先不接生圖, 用純色/單圖背景驗渲染 + 音軌 + 歌詞字幕)。
- **M1 對齊子系統**: Demucs + WhisperX 自動對齊, 出 song.json 時間軸 + review UI 微調層。
- **M2 生圖子系統**: 逐段 Gemini 生圖 + 風格一致性 + ken burns。
- **M3 整合**: 渲染核心串接 + 字幕燒錄 + require_review + YouTube 上傳 (含章節)。

每階段附 tests。對齊 / 生圖兩個 GATE 在 M1/M2 觸發 (新 dep + Gemini image 額度)。

---

## 7. GATE / 未決清單

1. **新 dep** demucs + whisperx + torch(CUDA) — 方案 2 已授權, M0 確認環境後實裝。
2. **Gemini image 額度** — 跟 V2 同一個開關, 等你開。
3. **對齊策略 (a) vs (b)** — M0 spike 拍板。
4. **歌曲是否含和聲/多人聲** — Demucs 對合唱分離品質待實測。
5. **YouTube 音樂版權** — AI 產的歌 (Suno/Udio) 商用授權條款需你確認 (內容策略, 非工程)。

---

## 8. routine 能自主做的 offline 部分

- M0 的**渲染骨架** (純色/單圖背景 + 給定時間軸的歌詞字幕 → mp4) 是純 offline,
  routine 可在 dep 裝好後自主推 + 補測試。
- 對齊 / 生圖兩子系統碰 GATE → 寫 proposal + STOP, 不自主燒額度 (offline-first 不變)。
