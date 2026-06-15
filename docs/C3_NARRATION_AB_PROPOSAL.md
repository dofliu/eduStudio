# C-3 旁白模型遷移 A/B 提案（2.5-flash → 3.x）

> 對應 `docs/PRODUCT_READINESS.md` C-3（🟡 GATE，需開額度驗證品質）。
> 狀態：**A/B 工具已備好（offline），等劉老師本機開額度跑過 → 看品質 → 決定切不切。**

## 1. 為什麼要動

- `slide_ingest.py:43` 旁白模型寫死 `MODEL = "gemini-2.5-flash"`（**將淘汰**，有 EOL 風險）。
- M 軸（角色登錄表 `core/models.py`）`text.fast` 預設已是 `gemini-3.5-flash`，但旁白 chokepoint
  **還沒走 `resolve()`**（M-2 刻意把這段 defer 給 C-3，因為直接換 = 把旁白默默從 2.5 遷到 3.5，
  品質沒驗就上線不可接受）。
- `3.5-flash` 實測接受 `thinking_budget=0`（旁白生成本來就關 thinking）。技術上可換，**只差品質驗證**。

## 2. 為什麼是 GATE（routine 不自主切）

換模型會**燒你的 Gemini 額度**且**影響每一支影片的旁白品質**（正確性 / 通順度 / 完整收尾 /
講解深度）。這是主觀品質判斷，必須**你本機開額度跑、用眼睛看**。routine 只負責把「能跑的工具 +
切換步驟」備好，不自主打真實 API、不自主切預設。

## 3. A/B 工具（已 offline 備好）

`tools/ab_narration.py`：對**同一份簡報的同幾頁**，用舊模型與候選模型**各生一次旁白並排輸出**。

- **只跑旁白生成**——不跑章節切分 / TTS / ffmpeg / 完整 render，比「跑兩支完整影片」**省很多額度**。
- **不改正式 pipeline 預設**——只是對同一頁注入不同 `model` 呼叫**真實的** `narrate_page_with_gemini`
  （prompt、三段式 retry、`thinking_budget=0`、`_clean_narration` 全與正式線一致，**不會 prompt 漂移**）。
  為此 `narrate_page_with_gemini` 加了一個**選填 `model` 參數**（預設仍 `MODEL`，正式 pipeline 零影響）。

### 怎麼跑（在你本機，設好 `GEMINI_API_KEY`）

```bash
export GEMINI_API_KEY=...          # 別貼進任何會 commit 的檔案
python tools/ab_narration.py 你的簡報.pdf \
    --pages 1,3,5 \
    --models gemini-2.5-flash,gemini-3.5-flash \
    --out ab_narration_report.md
```

挑**有代表性的幾頁**（純文字頁 + 含公式/圖表頁 + 章節銜接頁）即可，不必整份跑。
輸出 `ab_narration_report.md` 兩欄並排 + 各模型字元用量小結。

## 4. 決策準則（看報告時對照）

逐頁比兩欄旁白，3.x 要**不劣於** 2.5 才值得遷：

| 面向 | 看什麼 |
|---|---|
| **正確性** | 公式/數字/專有名詞有沒有講錯（最重要，呼應 review gate 賣點） |
| **完整收尾** | 句子有沒有腰斬 / 需要 retry 的頻率（3.x 若更少觸發 retry = 更省） |
| **通順度** | 中文是否自然、口語講解感 |
| **深度/長度** | 講解詳盡度是否與 2.5 相當（別變太短/太長拖影片） |
| **成本** | 字元用量小結相對量級（精準單價待 C-2 對齊官方定價） |

## 5. 驗過怎麼切（後續一刀，offline）

A/B 滿意後，把旁白 chokepoint 從寫死改成走登錄表（= M-2 defer 的那段）：

1. `slide_ingest.py`：`MODEL` 改成 `resolve("text.fast")`（或新增 `narration` 角色再 resolve）。
2. 章節切分（`detect_chapters_with_gemini`）同步換。
3. 跑 `pytest tests/`（硬規則 #7）。

切完「換模型 = 改登錄表一個值 / 設定頁一個下拉」（M-3 已給逐角色設定 UI）。

### Rollback

若上線後發現品質退步：設定頁把 `text.fast`（或 `narration` 角色）覆寫回 `gemini-2.5-flash`
即可即時退回，**不需改 code、不需重啟**（M-3 `model_roles` 最高優先）。

## 6. 待你拍板的開放問題

1. **遷移範圍**：只遷「逐頁旁白」，還是連「章節切分」一起？（兩者都吃 image input，建議一起驗一起換。）
2. **走 `text.fast` 還是新增 `narration` 角色**？走 `text.fast` 最省（複用既有角色）；新增 `narration`
   角色可讓旁白與其他 fast 文字用途**各自選模型**（更彈性，但多一個角色要維護）。建議**先走 `text.fast`**，
   有需要再拆。
3. **候選模型**：預設比 `gemini-2.5-flash` vs `gemini-3.5-flash`。要不要也納 `gemini-3-pro` 之類更強的比？
   （pro 貴、旁白未必需要，建議先 flash 對 flash。）
