# Review Assist RFC — review 數值二次校驗 (F9-1)

> **狀態**: 🟡 **草案，待劉老師拍板**（2026-06-12）
> **作者**: Claude（routine，產品化清單 F9-1）
> **Reviewer**: 劉瑞弘
> **不動 code**，只列設計 + 拆子任務 + 標 offline/GATE，等你選了範圍再實作。

---

## 為什麼寫這份

`docs/PRODUCT_READINESS.md` Phase 9 的 **F9-1（review 數值二次校驗）** 標 GATE：碰
二次模型額度的部分要先寫 proposal。這份就是那份 proposal——把功能拆成「現在可 offline
做」與「要你開額度才做」兩堆，讓你只需對少數開放問題拍板。

**核心動機**：eduStudio 最大的差異化是 **review gate（硬規則 #1，AI 答錯不流出）**。
但目前 reviewer 是「肉眼逐題看」——一份期中考十幾題、每題好幾個計算步驟，reviewer 很
容易漏看一個「50000 / 500 算成 1000」的低級錯誤。**把可疑點自動標出來，等於把核心賣點
做深**：不是取代人，是降低人的負擔、提高攔截率。

**不可妥協**：本功能 **只標記、不自動改**（不繞硬規則 #1）。標記是輔助 reviewer 的
注意力，最終 approve 仍是人。任何「AI 自動修正後直接 render」都違反 review gate，
本 RFC 明確排除。

---

## 問題陳述（grounding 到現況資料）

AI 解題輸出落在 deck（exam schema）的 `problems[].steps[]`，reviewer 透過
`GET /jobs/{id}/draft` 看到、`PUT /jobs/{id}/draft` 改、`POST /jobs/{id}/approve`
放行（`server/routes/jobs.py`）。一個 step 長這樣（取自 `solve.py::mock_output`）：

```jsonc
{ "_section": "代入計算", "display": "σ = 50000 / 500 = 100 MPa",
  "narration": "代入數值：50000 牛頓除以 500 平方毫米，等於 100 百萬帕斯卡。" }
```

AI 在這層最常犯、reviewer 最該被提醒的錯：

1. **算術錯**：`display` 寫 `50000 / 500 = 1000`（實際 100）。等號兩邊對不上。
2. **單位不一致**：`P = 50 kN` 但下一步當成 `50 N` 代入；`A = 500 mm²` 與 `σ` 的
   `MPa` 對應關係（N/mm² = MPa）被搞錯數量級。
3. **符號漂移**：第一步定義 `σ = P / A`，後面步驟把 `σ` 寫成 `s` 或 `τ`，或公式
   突然變 `σ = A / P`。
4. **答案與步驟對不上**：最後一步 `display` 的數字與 `narration` 唸出來的數字不同
   （AI 兩處生成不同步）。

這些都不是「需要懂材料力學」才看得出來，是 **形式一致性**問題——很多可以**確定性**
（不靠 LLM）抓出來，剩下「題目本身解法對不對」才需要第二顆模型的判斷。

---

## 設計目標

按優先序：

1. **高精度、低誤報**：標出來的「可疑點」要讓 reviewer 信任。誤報多了 reviewer 就
   全部忽略，等於沒做。寧可漏報（fail-open，反正人還會看）也別狼來了。
2. **只標記不自動改**（硬規則 #1）：產出是 annotation，不碰 deck 內容本身。
3. **offline-first 可漸進**：確定性檢查（②）完全不打 API，先單獨上；二次模型（①）
   是可選增強，要你開額度。沒開額度時系統照常運作，只是少了 ① 那層。
4. **不阻擋 review 流程**：校驗失敗/逾時 → 當作「沒有可疑點」放行（不能因為校驗器
   壞掉就卡住整個 review）。
5. **接在既有 review UI**，不另起爐灶。

---

## 兩個校驗面

### ② 確定性一致性檢查（offline，建議先做）

純 Python，**不打任何 API**。對每個 `step.display` 與跨 step 做形式檢查：

- **算術校驗**：把 `display` 裡形如 `<expr> = <number> <unit>` 的等式抽出來，用
  安全數值求值（**不是 `eval`**——用 `ast` 白名單或 `sympy`，只允許 + - * / ^ 與
  數字、括號）算左邊，與右邊比對（含相對容差，處理四捨五入）。對不上 → 標 `arithmetic`。
- **單位/量綱**：抽單位（kN/N/MPa/GPa/mm²/m…），做量綱一致性與數量級檢查（可選
  接 `pint` 做真量綱分析，或先做白名單常見換算表）。`σ = P/A` 的單位不自洽 → 標 `unit`。
- **符號一致性**：蒐集整題出現的符號（σ τ P A E L …），標出「只出現一次的疑似錯字」
  或「同一量用了兩種符號」。
- **display ↔ narration 數字對齊**：抽兩邊的數字 token 比對，差異 → 標 `narration_mismatch`。

**優點**：零成本、零延遲、可重現、好測（fixture in → flags out，全 offline）。
**侷限**：只抓形式錯，不懂「這題該不該用這個公式」。那是 ① 的事。

設計成**純函式** `core/review_assist.py::check_deck(deck) -> list[ReviewFlag]`
（不碰 IO、不依賴 FastAPI，比照 `core/narration_validator.py` 的風格），方便單測。

`ReviewFlag` 草案 schema：

```python
class ReviewFlag(BaseModel):
    problem_id: str          # 對應 problems[].id
    step_index: int          # steps[] 索引（-1 = 題級）
    kind: str                # arithmetic | unit | symbol | narration_mismatch | model_disagree
    severity: str            # info | warn（不做 error——不阻擋，只提醒）
    message: str             # 給 reviewer 看的人話（「左式 50000/500=100，但寫 1000」）
    source: str              # deterministic | second_model
```

### ① 二次獨立模型 pass（GATE，需額度）

用**第二顆模型**（角色 `text.pro`，走 M 軸 `core/models.py::resolve()`，不寫死 id）
獨立重解同一題，比對數值結論。不同 → 標 `model_disagree`（severity=warn）。

- **只比對、不覆寫**：第二顆模型的解**不進 deck**，只用來「有沒有分歧」這個訊號。
- **成本**：每題一次額外 LLM 呼叫。要計帳（`core.usage.record_text_now`，新 station
  如 `review/verify`）並可設開關（預設關，自架者自己決定要不要燒這筆）。
- **為什麼是 GATE**：(a) 燒額度 (b) prompt 設計與「分歧判定門檻」要實測調，會打真 API
  驗品質——正是 offline-first 紀律 #3 要 STOP 的那類。
- **offline 可先備好的**：呼叫端骨架 + flag 合併邏輯 + **mock 測試**（fake 第二模型
  回固定答案，驗「分歧→標 flag、一致→不標」），真實 prompt 調校等你開額度。

---

## 架構：算在哪、surface 在哪

```
ingest 完成 → deck.json 落盤 → 狀態 awaiting_review
                                   │
            （新增）review assist  ▼
        core/review_assist.check_deck(deck)  ②確定性，offline
        [可選] + 二次模型 pass             ①GATE，需開關+額度
                                   │
                            list[ReviewFlag]  ── 落盤 review_flags.json
                                   │
   reviewer：GET /jobs/{id}/draft（既有）+ GET /jobs/{id}/review-flags（新增）
                                   │
            前端 review UI 在對應 step 旁顯示 ⚠ 標記 + 訊息
                                   │
                  人工判讀 → 改 deck / 直接 approve（硬規則 #1 不變）
```

**關鍵設計選擇**：

- **不阻擋、不入狀態機**：flags 是**附帶資訊**，不是新的 job 狀態，不碰 `_run_render_phase`
  的 reviewed assert（R-2）。approve 仍只需人工點，**有沒有未解決的 flag 都能 approve**
  （硬規則 #1 的權威是人，不是校驗器；強制「清空 flag 才能 approve」會把確定性誤報變成
  硬卡，違反設計目標 #4）。
- **何時算**：建議 ingest 完成、進 `awaiting_review` 時算一次（②便宜可同步；①若開啟
  走 `asyncio.to_thread`，呼應 R-3 不阻 event loop）。`PUT /draft` 改 deck 後可重算。
- **存哪**：`jobs/<id>/review_flags.json`，與 deck 分檔（reviewer 改 deck 不必動 flags，
  反之亦然），比照 F9-4 artifact 版本分檔的理由。
- **前端**：在既有 review UI 的逐 step 顯示加 ⚠ pill（點開看 message）。純加法，不改
  既有 review 流程。

---

## 拆子任務（offline / GATE 標記）

> 一刀一 PR、≤3~5 檔、動 server/core 跑 pytest（硬規則 #7）。

| # | 子任務 | 類型 | 說明 |
|---|--------|------|------|
| F9-1a | `core/review_assist.py` 確定性算術校驗 + `ReviewFlag` schema | **offline** | 純函式 + 單測（fixture deck → flags）。先只做最高價值的 `arithmetic` + `narration_mismatch`。 |
| F9-1b | 單位/量綱 + 符號一致性檢查 | **offline** | 接 `pint` 或白名單換算表（依賴抉擇見開放問題）。 |
| F9-1c | 接進 pipeline：ingest 後算 ② + 落 `review_flags.json` + `GET /jobs/{id}/review-flags` | **offline** | 動 runner/route 跑 pytest。flags 不入狀態機、不阻 approve。 |
| F9-1d | 前端 review UI 顯示 ⚠ 標記 | **offline** | `frontend/edustudio/app.jsx`，build 為準、人後視覺驗收。 |
| F9-1e | ① 二次模型 pass 呼叫骨架 + flag 合併 + **mock 測試** | **offline** | 走 `resolve("text.pro")`、計帳、預設關。真實 prompt 不調、不打 API。 |
| F9-1f | ① prompt 設計 + 分歧門檻實測 + A/B 驗誤報率 | **GATE（額度）** | 打真 Gemini，要你開額度。寫成 A/B proposal 跑過再開預設。 |

**建議推進序**：F9-1a → F9-1c → F9-1d 先讓「確定性可疑點」端到端跑通並上 UI（純
offline，已能降 reviewer 負擔）；F9-1b 補強；F9-1e 備好 ① 的座位（mock 測）；
**F9-1f 等你開額度**。

---

## 開放問題（待劉老師拍板）

1. **範圍**：先只做確定性（②，F9-1a~d）就上線，還是一定要等二次模型（①）一起？
   建議：**先上 ②**（零成本、馬上有用），① 當後續增強。
2. **量綱依賴**：F9-1b 要不要引入 `pint`（精準量綱分析，多一個依賴）還是先用白名單
   常見換算表（零依賴、覆蓋材力/自控常見單位即可）？建議：**先白名單**，需要再升 `pint`。
3. **① 預設開關**：二次模型 pass 預設**關**（自架者按自己額度開）對嗎？建議：是。
4. **① 用哪個角色**：`text.pro`（較強、較貴）還是另一顆 provider 做「獨立性」更好？
   涉及成本/品質取捨，等 F9-1f 實測時定。
5. **誤報容忍**：算術比對的相對容差設多少（例 1e-3）？這要看真實題目分布，可先給預設
   再依 reviewer 回饋調。

---

## 不可妥協紀律（本功能自我約束）

- **只標記、不自動改**——不繞硬規則 #1，approve 永遠是人。
- **不阻擋 review**——校驗器壞掉/逾時 = fail-open（當作沒可疑點）。
- **offline-first**——②全程不打 API；①預設關、要開額度、全程計帳；mock 測不打真 API。
- **不寫死 model id**——①走 `core/models.py::resolve()`（M 軸）。
- **type guard / config 集中 / 別 commit 機密**——比照既有紀律。
- **動 server/core/runner 跑 `pytest tests/`**。

---

## 不納入（避免範圍蔓延）

- **自動修正 / 自動重生**：明確排除（違反硬規則 #1）。
- **強制「清空 flag 才能 approve」**：不做（誤報會變硬卡）。flag 是提醒不是 gate。
- **第三方數學求解服務（Wolfram 等）**：不引入外部依賴/外洩題目；②用本機 `ast`/`sympy`。
- **跨題語意正確性**（這題該用哪條定理）：超出形式校驗範疇，留給人工 review 本職。
