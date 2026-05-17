# 內容品質 Roadmap (2026-05-16 起)

> 跟 v4 worker (架構) 並行的工作軸 — 讓影片內容更符合教學需求.
> 2026-05-16 劉老師決議: v4 worker 暫緩, 先做這條.
> 預計用 /loop /advance 自動化迭代逐項完成.

---

## A. 主題 / 排版 (進行中, 從 A1 開始)

### A1. 字級 / 行距 per-theme (claude design 04)

**問題**: TITLE=64 / BULLET=38 / line-height 16 套全 15 主題, brutalist 該超大字 / journal 該大字距 / podium 該超少字大字.

**設計**: 新 `THEME_METRICS` dispatch table, per-theme override 全域常數. 不該破壞 iter 71 各 layout 內部的精心調過的字級.

**估時**: 3-4 hr.

### A2. Margin / 對齊 per-theme (claude design 05)

**問題**: SIDE_MARGIN=100 套全 15 主題, podium / elven 該縮窄 / brutalist 該頂邊緣 / editorial 該不對稱.

**設計**: 延伸 A1 的 `THEME_METRICS` 加 margin / align tokens.

**估時**: 2-3 hr.

### A3. 自訂主題色票 UI

**功能**: UI 直接拉色票, 即時預覽, 不必改 code.

**估時**: 1-2 天.

---

## B. 影片格式 (A 完成後啟動)

### B1. 縱向短影片 (9:16) — TikTok / Shorts / Reels

**現狀**: 固定 1920×1080. 加 1080×1920 模式.

**影響範圍**: layout dispatch + slide_renderer + cover/outro 全部. cover 等的 anchor 都要重算.

**估時**: 1 天.

### B2. 解析度可選 (1080p / 1440p / 4K)

**設計**: JobOptions 加 resolution. pipeline.WIDTH/HEIGHT 改 dynamic.

**估時**: 2-3 hr.

### B3. 整段時長可選

**設計**: 加 ultra-quick (3-5 min) 或自由輸入分鐘數.

**估時**: 2-3 hr.

---

## C. 內容品質 / narration (B 後啟動)

### C1. Narration 截斷率 22% 治本

**問題**: Gemini 偶爾 narration 寫太長被字幕截.

**設計**: 改 prompt 強制 60-180 字 + 後處理長度檢查 + retry.

**估時**: 4-6 hr.

### C2. TTS 中文發音治本

**問題**: F5-TTS 中國腔 / 特定詞發音怪.

**設計**: 加 pronunciation.json mapping. 框架已有, 缺 mapping 內容.

**估時**: 跟用戶 review 樣本, 1-2 hr.

### C3. Slide narration AI 品質升級

**設計**: scriptor prompt 加教學風格指令 (「先舉例再講原理」之類).

**估時**: 依用戶想加的風格而定.

---

## D. 其他 (機會性, 看狀況啟動)

### D1. 投影片 outline AI review 介面

**問題**: outliner 大綱有時偏離主軸.

**設計**: review 大綱介面 (現在直接進 scriptor).

**估時**: 1-2 天.

### D2. 字幕風格樣式

**設計**: 字幕字級 / 字色可調 (現在 ffmpeg subtitles filter 寫死).

**估時**: 2-3 hr.

---

## 執行順序

按 A → B → C → D 順序逐項完成. 每項做完更新本檔案進度.

進度:
- [x] A1 字級 / 行距 per-theme (iter 74, commit 5101afa)
- [x] A2 Margin per-theme (iter 75, side_margin 接 title + bullets)
- [x] A3 自訂主題色票 UI (iter 76, 3 色 override: bg / primary / highlight)
- **A 全部完成 (2026-05-16). 接下來啟動 B 影片格式.**
- [x] B1 縱向短影片 9:16 (iter 83, Option B monkey-patch + iter 84 title 多行居中)
- [x] B2 解析度可選 1080p/1440p/4K (iter 83 同步完成, 共用 dimension table)
- [x] B3 整段時長可選 (iter 77, ultra_quick 3~5 min Shorts/Reels, a30a621)
- [x] C1 Narration 長度驗證 + prompt 強化 (iter 79, 治標+追蹤)
- [ ] C2 TTS 中文發音治本 (需 user 提供樣本)
- [x] C3 narration AI 品質升級 (iter 82, scriptor prompts 加「先舉例 + 比喻」)
- [x] D1 v1 outline 預覽 modal (iter 81, 唯讀) — v2 edit/approve gate 留下次
- [x] D2 字幕風格樣式 (iter 80, 字級/字色/描邊色 hex)

---

## 用戶實機反饋追加項 (2026-05-17, iter 87+)

iter 86 後用戶實機測試發現新需求 / bug, 排入 backlog 並完成:

- [x] **iter 87/87b/87c/87d CI 修復** (302c6a7 / 4ac0218 / 6b689a0 / b0016ee)
  - 從 iter 57 起 CI 連紅 30 commit, 4 條獨立根因 (fitz/google.genai 沒裝
    / Linux 缺中文字型 + qrcode / 視覺採點跨字型 brittle / web/ui/ 沒 commit)
- [x] **iter 88 短影片獨立 layout** (a8db669, `bg_type=short_video_slide`)
  - ultra_quick 預設只改字數預算沒改 rendering, 加巨大字居中 + 圖片
    滿版下半. ultra_quick mode UI 自動勾, 用戶可手動取消.
- [x] **iter 89 複製 proposal 為新 PENDING** (db5742b)
  - 同份 PDF 想做多支不同設定影片被 dedupe + APPROVED status 鎖死.
    加 POST /proposals/{id}/duplicate + 「全部 ◌/✓」toggle + 「📋 複製」
    按鈕. 不改 ideate.dedupe_against_jobs 本體.
- [x] **iter 91 中文 wrap 標點 + 孤字後處理**
  - 短影片實測「Skill 的本質與差/異」孤字單字落單 + 開引號可能行尾.
    `_balance_wrap_lines` 三輪修整: 開頭標點推下、收尾標點拉回、
    末行 < 3 字借字. 改 `_wrap_text` 全 caller 自動受惠 (cover / outro /
    short_video_slide / normal slide). +8 tests (test_wrap_balance).
- [x] **iter 92 內容品質三軸升級** (用戶實測三 ask)
  - **talking_head 三段選項**: always / long_form_only (預設) / off.
    短影片 (9:16 / ultra_quick / short_video_layout) 自動 skip.
    core/photo_overlay.py 加 context manager, runner 包進去, UI dropdown.
  - **L2 narration_style 5 preset**: academic / storyteller (預設) /
    wuxia / dialogue / comedy. prompts/styles/*.txt 各風格檔, scriptor
    自動載入注入 prompt. 解 C3 用戶 ask「更多風格 + 比喻 / 幽默」.
  - **L3 persona scaffold**: jliu v1 (基於 CLAUDE.md 寫). prompts/persona/
    jliu.txt — 副教授背景 + 口頭禪 + 舉例偏好 + 避免事項. 等實機反饋
    迭代 v2.
  - **Google Cloud TTS provider**: GoogleTTS class, FallbackTTS 機制.
    zh-TW-Wavenet-A 預設, $16/1M chars (個人月用 ~$1-2). docs/
    GOOGLE_TTS_SETUP.md 完整啟用指南. 解 C2 用戶 ask「付費方案」.
  - +41 tests (test_talking_head_override 13 / test_narration_style 16
    / test_google_tts 12), 1071 total passed.
