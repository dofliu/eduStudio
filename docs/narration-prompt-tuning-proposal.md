# Narration prompt 強化提案 (N4 — GATE, 等用戶開額度)

> 撰寫: 2026-05-29 (Phase 2 routine, N 軸 N4)
> 狀態: **提案 — 未驗證**. 改 prompt 需打 Gemini 跑 A/B 才知效果好壞,
> routine 守 offline-first **不自主呼叫 Gemini**. 這份是 prompt diff 草稿 +
> 建議驗證流程, **STOP 等劉老師 review + 手動開額度驗證後再 apply**.

---

## 1. 背景 — N 軸做到哪了

| 階段 | 做了什麼 | 結果 |
|---|---|---|
| N1 | `tools/measure_narration_truncation.py` 量 19 個真實 deck | over-cue (>40 字) **44.9%** (修前), over-slide **88%** |
| N2 | 抽 4 deck 做 length-preserving 匿名化 fixture, CI 可重現 | locked baseline: 196 cue / over-cue 61 (31.1%) / max 105 |
| N3 | `core/srt.py` 加 `SUBTITLE_CUE_CHAR_BUDGET=40` + `_split_long_cue` (次級標點 greedy 切) + `narration_to_cues` | over-cue **31.1% → 0.0%**, max cue **105 → 40 字** |
| N3-verify | 工具/CI `split_cues` 接 `narration_to_cues`, 量「修後」可重現 | over-cue 0.0% (0/265) 固化進 `TestCommittedFixture` |

**N3 是確定性後處理 (字幕帶切分層)**: 不靠 Gemini, 純函式把過長 cue 在逗號/分號
切短, 測量+CI 可離線重現. 已把「字幕視覺溢出」這個症狀治到 0.

---

## 2. 為什麼還需要動 prompt (N3 沒蓋到的兩個缺口)

### 缺口 A — N3 切不了「沒有次級標點的長句」

`_split_long_cue` 的設計是**只在標點切, 不硬斷詞** (語意優先). 程式碼:

```python
segments = [seg for seg in _CLAUSE_SPLIT.split(sentence) if seg.strip()]
if len(segments) <= 1:
    # 沒有次級標點可切 → 不硬斷詞, 整段保留
    return [sentence]
```

也就是說, 若 Gemini 產出像
「材料力學是研究固體在外力作用下會如何變形以及內部會產生什麼樣的應力分布的一門基礎學科」
這種 **42 字、整句沒有一個逗號** 的 narration, N3 **無法切**, 會原樣溢出字幕帶.
目前 fixture 的 4 個 deck 剛好每個長句都有逗號 (所以修後 over-cue 0), 但這是**運氣**,
不是保證 — prompt 沒明文要求 Gemini 在長句裡加次級標點.

→ **prompt 該明文要求: 句子要短; 真的要長, 每 ~20 字內必須有逗號/分號**, 讓 N3 切得動.

### 缺口 B — over-slide ratio 還是很高 (79.5% fixture / 88% 真實)

over-slide = 整段 narration 超出 `length_mode` preset 的 `narration_chars_range`.
prompt 雖然已寫「先在心裡數字數」「超出上限整份會被拒收」, 但 over-slide 仍 ~80%,
表示 **slide 層的字數指令 Gemini 遵守度差**. 這不影響字幕視覺 (N3 切 cue 不切整段),
但影響 **影片總時長** (`estimate_deck_duration` 用整段字數估), quick 模式實測會超 15 分鐘.

→ prompt 該把 slide 層字數約束講得更硬 (見 §3 diff), 但這條的效果**只能靠 A/B 驗證**.

> **N3 (後處理) 與 prompt (源頭) 互補, 不互斥**: N3 保證「即使 Gemini 寫太長,
> 字幕也不溢出」(已達成); prompt 讓「Gemini 一開始就寫得對」(減少 N3 要切的量 +
> 治 over-slide). 兩條都要.

---

## 3. Prompt diff 草稿

對象: `prompts/scriptor_longform_section.txt` + `prompts/scriptor_repo_section.txt`
(兩檔的「本章 narration 規格」段結構相同, 同步改). **不動** exam 路徑 (solve.py /
Track A) — 那是 require_review 強制人工 review 的考題, 另案處理.

### 3.1 既有片段 (兩檔第 9~16 行附近)

```text
**本章 narration 規格**: 每張 slide narration **{narration_chars_range} 字**, 不可超出.
取下限優先 — 短而精準比長而冗贅好.

★ 寫每張 slide 的 narration 前, **先在心裡數字數**:
   - 中文字數 = 字符數 (1 個漢字 = 1 字), 標點符號也算
   - 寫完一句再估, 超出上限就刪減 / 換更短的同義詞
   - 範例: "材料力學討論固體在外力下的變形與內部應力分布, 是力學的基礎。"
     = 30 字 (含標點). 60-80 字的 slide 寫 2-3 句即可
   - 寫出來的 narration 若任一張超出上限, 整份輸出會被 server 拒收
```

### 3.2 建議改成 (加 cue 層 + 強化 slide 層)

```text
**本章 narration 規格** (兩層字數約束, 都要顧):

【slide 層】每張 slide narration **{narration_chars_range} 字**, 不可超出.
取下限優先 — 短而精準比長而冗贅好.

【句子層 ★ 新增, 字幕直接相關】每一個「句子」(以 。！？ 結尾) **≤ 40 字, 理想 ≤ 30 字**.
字幕一次只顯示一句; 句子超過 40 字, 字幕會被切成多行頂出畫面下緣的字幕帶.
   - 與其寫一個 50 字的長句, 不如拆成兩個 25 字的句子 (各自以 。結尾).
   - **若一個概念真的需要長句**, 句中**每 ~20 字內必須有一個逗號或分號** (，；),
     系統會在逗號處把字幕自動斷行. **整句 40 字卻一個逗號都沒有 = 字幕一定溢出**.
   - 反例 (字幕會溢出, 禁止):
     「材料力學是研究固體在外力作用下會如何變形以及內部產生什麼應力分布的基礎學科。」
     (42 字, 0 逗號 → 無法斷行)
   - 正例 (同義, 可斷行):
     「材料力學研究固體在外力下如何變形, 以及內部的應力分布, 是力學的基礎。」
     (每段 ≤ 20 字, 逗號處可斷)

★ 寫每張 slide 的 narration 前, **先在心裡數字數** (兩層都數):
   - 中文字數 = 字符數 (1 個漢字 = 1 字), 標點符號也算
   - 寫完一句先數這句 ≤ 40 字, 再數整張 slide ≤ 上限
   - 超出就刪減 / 換更短同義詞 / 拆成兩句
   - 寫出來的 narration 若任一張超出 slide 上限, 整份輸出會被 server 拒收
```

### 3.3 數字依據

- **句子層上限 40 字** 對齊 `core.srt.SUBTITLE_CUE_CHAR_BUDGET = 40` (字幕帶可容 2 行
  CJK, 每行 ~20 字). prompt 寫死 40 與該常數重複 — 若未來常數調整, prompt 也要跟著改
  (建議在 prompt 旁註明「對齊 SUBTITLE_CUE_CHAR_BUDGET」, 或日後做成 template 變數
  `{cue_char_budget}` 由 length_mode/srt 注入, 避免漂移; **此提案先寫死 40, 變數化另案**).
- **「每 ~20 字一個逗號」** = 確保 `_split_long_cue` 一定有切點, 切完每段 ≤ 40 字.

---

## 4. 建議 A/B 驗證流程 (需用戶開 Gemini 額度)

> ⚠️ 這段**需打 Gemini**, routine 不跑. 等劉老師 review prompt diff + 開額度後手動執行.

### Step 1 — 固定測試集 (3~5 個 source, 涵蓋 repo / document / url)

挑能代表常用情境的輸入, 例如:
- 1 個程式 repo (走 `scriptor_repo_section`)
- 1 篇講義 PDF / md (走 `scriptor_longform_section`)
- 1 個 blog URL
每個都跑 `quick` + `lecture` 兩種 length_mode (over-slide 在 quick 最嚴重).

### Step 2 — 產 A / B 兩版 deck

- **A (對照)**: 現行 prompt, 不改.
- **B (處理)**: apply §3.2 diff 後的 prompt.
同一份 source、同 length_mode、同 narration_style、`mock=False`, 各跑一次存
`jobs/<id>/deck.json`. (記錄 job id 兩兩對應.)

### Step 3 — offline 量測 (這步 routine 可代跑, 不打 Gemini)

對 A / B 兩組 deck 各跑:

```bash
python tools/measure_narration_truncation.py --root jobs/  # 或指定 deck 路徑
```

比較三個指標:

| 指標 | 看什麼 | 期望 (B vs A) |
|---|---|---|
| **over-cue (cue_budget=0)** | 用 `--cue-budget 0` 量「修前」cue, 看 Gemini 源頭產出的長句比例 | B 明顯下降 (prompt 教它寫短句) |
| **無次級標點的長句數** | (需在工具加一個 counter, 見 §5) 量缺口 A 殘留風險 | B 趨近 0 |
| **over-slide ratio** | 整段 narration 超 preset | B 下降 (缺口 B) |

> 注意: 修後 (預設 budget 40) 的 over-cue 兩版都會是 ~0 (N3 會切), 所以**比較要用
> `--cue-budget 0`** 量 Gemini 源頭產出, 才看得出 prompt 效果. 這也是 N3-verify 留
> `--cue-budget 0` 對照模式的用途.

### Step 4 — 主觀檢查 (人工, 不可省)

- 加逗號後 narration 念起來會不會變得頓挫不自然? (TTS 試聽 1-2 段)
- 拆句後語意有沒有變破碎?
- 程式碼講解 (repo) 的 code_snippet 覆蓋率有沒有被影響?

### Step 5 — 決策

B 明顯更好且無副作用 → apply prompt diff, 更新 `test_prompts_loader` 的 `.format()`
kwargs (若加了 `{cue_char_budget}` template 變數). 沒明顯差 / 有副作用 → 留 A,
記錄結論. **無論結果都不可繞 require_review** — exam 路徑不在此提案範圍.

---

## 5. 配套小改動 (offline, routine 可在 N4 apply 後另輪做)

驗證流程 Step 3 需要工具能量「無次級標點的長句數」(缺口 A 的殘留指標). 目前
`tools/measure_narration_truncation.py` 只算 over-cue / over-slide / 長度分布,
沒有「這個 cue 是否含可切的次級標點」這個欄位. 建議:

- 在 `measure_deck` / `aggregate` 加一個 counter: `uncuttable_long_cues`
  = 長度 > budget **且** `_CLAUSE_SPLIT.split` 後 `len(segments) <= 1` 的 cue 數.
- report 多一列「無標點長句 (N3 切不動)」.
- +tests.

這步**純離線、不打 Gemini、≤2 檔**, 是 routine 在 N4 STOP 期間可自主推的事
(讓驗證流程 Step 3 的指標就緒). 但**不可代替** A/B 本身 — A/B 仍需用戶開額度.

---

## 6. STOP 理由 (給 routine 自己看)

- 改 prompt 的**效果**只能靠跑 Gemini A/B 得知, routine offline-first 不自主呼叫.
- 這份是**草稿**, prompt 措辭 / 40 字是否該調 / 要不要 template 變數化, 都該等
  劉老師 review 拍板.
- apply diff 後要動 `test_prompts_loader` (既有測試呼叫 `.format(...)` 全要補新
  kwarg, 見 TODO「重要踩坑紀錄」), 這是行為改動, 不該 routine 自己 commit.

**下一步 (等用戶)**: 劉老師 review §3 diff → 開額度跑 §4 A/B → 回報結論 → 再決定 apply.
**routine 在這期間可做**: §5 配套 counter (offline). 之後接 V 軸 (V1 offline 補測試).
