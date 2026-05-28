# Narration 截斷 baseline 測量報告 (N1)

> 產出時間: 2026-05-28
> 工具: `tools/measure_narration_truncation.py` (offline, 純讀 deck.json)
> 掃描 deck 數: 19  |  per-cue 上限 (provisional): 40 字

本報告用真實 deck 資料取代舊「~22%」估計 (2026-05-07 拍腦袋值). **over-cue ratio** 是真正會在字幕帶視覺溢出的指標 (單一 SRT cue 超出 字幕帶可容字數); **over-slide ratio** 是 narration 整段超出 length_mode preset 上限. N3 治本對象是 over-cue.

## 全域摘要

- deck 數: **19**, slide 數: 458, cue 數: 2423
- **over-cue ratio (> 40 字): 44.9%** (1088/2423)
- over-slide ratio: 88.0% (403/458)
- cue 長度: 平均 40.4 字, 最長 136 字
- 最長 cue: 136 字 @ `jobs/764039d15546/deck.json` model_validation/model_validation_1 — 「這一章節是我們研究的核心，它有兩大主軸：首先，我們要介紹一個創新的現場專屬亂流模型，來更精確地描述台…」

## Cue 長度分布 (全域)

> 不同 per-cue 上限下會有多少 cue 過長 — 給 N3 挑值用.

| 上限 (字) | 超過的 cue 數 | 佔比 |
|---|---|---|
| > 20 | 2150 | 88.7% |
| > 30 | 1610 | 66.5% |
| > 40 | 1088 | 44.9% |
| > 50 | 624 | 25.8% |
| > 60 | 317 | 13.1% |
| > 80 | 70 | 2.9% |

## 依 (length_mode × narration_style) 分組

| length_mode | narration_style | decks | slides | over-slide | cues | over-cue (40) | 最長 | 平均 | >20 | >30 | >40 | >50 | >60 | >80 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| lecture | storyteller | 1 | 80 | 38% | 508 | 44% | 114 | 41.1 | 462 | 356 | 225 | 125 | 74 | 17 |
| quick | comedy | 2 | 35 | 100% | 197 | 39% | 93 | 37.7 | 177 | 117 | 77 | 36 | 18 | 3 |
| quick | storyteller | 13 | 316 | 99% | 1620 | 47% | 136 | 41.1 | 1434 | 1092 | 766 | 456 | 223 | 50 |
| ultra_quick | storyteller | 3 | 27 | 89% | 98 | 20% | 70 | 31.0 | 77 | 45 | 20 | 7 | 2 | 0 |

### 各組最長 cue 範例

- **lecture / storyteller**: 114 字 @ `jobs/792a4cd4483d/deck.json` s3_simulation/s3_simulation_8 — 「對於第一小題，使用PID 標準公式，Kp 應為 0.60 乘以 Ku (4.0)，得到 2.40；K…」
- **quick / comedy**: 93 字 @ `jobs/4cbbd0de6470/deck.json` how_it_works/how_it_works_2 — 「而第二部分的 Markdown 內文，才是我們寫給 Claude 的詳細指令和工作流程，這部分只有在…」
- **quick / storyteller**: 136 字 @ `jobs/764039d15546/deck.json` model_validation/model_validation_1 — 「這一章節是我們研究的核心，它有兩大主軸：首先，我們要介紹一個創新的現場專屬亂流模型，來更精確地描述台…」
- **ultra_quick / storyteller**: 70 字 @ `jobs/113ee97a808d/deck.json` how_it_works/how_it_works_3 — 「所以，Description就像給AI的「關鍵字提示」，必須精準寫出「做什麼」、「何時用」和「觸發詞…」

