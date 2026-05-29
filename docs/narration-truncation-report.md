# Narration 截斷 baseline 測量報告 (N3 修後)

> 產出時間: 2026-05-29
> 工具: `tools/measure_narration_truncation.py` (offline, 純讀 deck.json)
> 掃描 deck 數: 4  |  per-cue 上限: 40 字

本報告量 N3 治本「修後」: cue 切分走 `core.srt.narration_to_cues` (跟 build_srt 同一條), **over-cue ratio** = 單一 cue 經 per-cue 上限切分後仍 超出字幕帶可容字數的殘留比例 (理想 0); **over-slide ratio** = narration 整段超出 length_mode preset 上限 (不受 cue 切分影響). N1 修前在 19 個真實 deck 量到 over-cue 44.9% (見 git 歷史), 治本目標就是把它壓到 ~0.

**無標點長句** = 長度 > 40 字且無次級標點 (，、；：,;:) 可切的 cue 數 — N3 (`_split_long_cue`) 切不動的殘留 (proposal N4 缺口 A). 配合 `--cue-budget 0` (量 Gemini 源頭 raw 句) 看 prompt 是否教會模型在長句裡加逗號; 修後 (預設 budget) 模式下它等於 over-cue 殘留 (殘留的長 cue 正是無標點切不動的那種).

## 全域摘要

- deck 數: **4**, slide 數: 39, cue 數: 265
- **over-cue ratio (> 40 字): 0.0%** (0/265)
- 無標點長句 (N3 切不動, > 40 字且無次級標點): 0.0% (0/265)
- over-slide ratio: 79.5% (31/39)
- cue 長度: 平均 26.8 字, 最長 40 字
- 最長 cue: 40 字 @ `lecture_storyteller` intro/intro_4 — 「文文文文文文文文文文文文文文文文文，文文文文文文文文文文文文文，文文文文文文文。」

## Cue 長度分布 (全域)

> 不同 per-cue 上限下會有多少 cue 過長 — 看切分後的長度散布.

| 上限 (字) | 超過的 cue 數 | 佔比 |
|---|---|---|
| > 20 | 201 | 75.8% |
| > 30 | 110 | 41.5% |
| > 40 | 0 | 0.0% |
| > 50 | 0 | 0.0% |
| > 60 | 0 | 0.0% |
| > 80 | 0 | 0.0% |

## 依 (length_mode × narration_style) 分組

| length_mode | narration_style | decks | slides | over-slide | cues | over-cue (40) | 無標點長句 | 最長 | 平均 | >20 | >30 | >40 | >50 | >60 | >80 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lecture | storyteller | 1 | 10 | 20% | 90 | 0% | 0 | 40 | 27.4 | 68 | 45 | 0 | 0 | 0 | 0 |
| quick | comedy | 1 | 10 | 100% | 74 | 0% | 0 | 39 | 25.6 | 54 | 23 | 0 | 0 | 0 | 0 |
| quick | storyteller | 1 | 10 | 100% | 63 | 0% | 0 | 40 | 27.0 | 48 | 28 | 0 | 0 | 0 | 0 |
| ultra_quick | storyteller | 1 | 9 | 100% | 38 | 0% | 0 | 40 | 27.5 | 31 | 14 | 0 | 0 | 0 | 0 |

### 各組最長 cue 範例

- **lecture / storyteller**: 40 字 @ `lecture_storyteller` intro/intro_4 — 「文文文文文文文文文文文文文文文文文，文文文文文文文文文文文文文，文文文文文文文。」
- **quick / comedy**: 39 字 @ `quick_comedy_with_cover_outro` advanced_practical/advanced_practical_2 — 「文文文文文文文文文文文文文文文文文文，文文文文文文文文文文文文文文文文文文文。」
- **quick / storyteller**: 40 字 @ `quick_storyteller` core_tech/core_tech_2 — 「文文文文文文文文文文文文文文文，文文文文文文，文文文文文文文文文，文文文文文文。」
- **ultra_quick / storyteller**: 40 字 @ `ultra_quick_storyteller` how_it_works/how_it_works_3 — 「文文，xxxxxxxxxxx文文文xx文「文文文文文」，文文文文文文「文文文」、」

