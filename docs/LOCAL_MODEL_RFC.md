# Local Model RFC — 本機可插拔模型後端 (F9-3 / M 軸 Option B)

> **狀態**: 🟡 **草案，待劉老師拍板**（2026-06-12）
> **作者**: Claude（routine，產品化清單 F9-3）
> **Reviewer**: 劉瑞弘
> **不動 code**，只列設計 + 拆子任務 + 標 offline/GATE，等你選了範圍/開額度再實作。

---

## 為什麼寫這份

`docs/PRODUCT_READINESS.md` Phase 9 的 **F9-3（本機可插拔模型後端）** 標 GATE：要支援
**Ollama 等本機 LLM** 跑文字角色（大綱/旁白/翻譯/解題），讓老師可**零雲端成本**自架。
這正是 **M 軸拍板的 Option B**——M-1~M-4 已把座位備好（角色登錄表 + provider 協定），
F9-3 就是「坐進去」的第一個非 Gemini provider。

這份是那份 proposal——grounding 到**現況已有什麼**（M-4 provider 介面、`core/translate.py`
已驗過的 Ollama 路徑），把功能拆成「現在可 offline 做」與「要你開額度/本機 GPU 才驗」
兩堆，讓你只需對少數開放問題拍板。

**核心動機**：eduStudio 主軸是「老師內容工作站 + 人工把關 + **自架**」。自架者最在意
「這會花我多少錢」（Phase 4 計費就是為此）。能用**本機模型**跑掉文字大宗（旁白/翻譯
用量小但逐頁累積），等於把「零雲端成本自架」這條 offline-first 主軸做實——與既有
**翻譯層已用本機 translategemma 驗過路子**（`core/translate.py`）一脈相承。

---

## 現況盤點（grounding：已經有什麼）

### M 軸座位已就緒（M-1~M-4，皆已 merged）

- **`core/models.py`（M-1）角色登錄表**：6 個邏輯角色 `text.fast` / `text.pro` /
  `vision` / `image.fast` / `image.pro` / `tts` → `(provider, model_id)`。`resolve(role)`
  **回的第一維就是 provider 名**，A 階段 LLM/視覺/生圖角色 provider 恆 `gemini`，
  `tts` 為 `edge`。provider 維度**就是為 B 階段預留的**。
- **`core/providers.py`（M-4）Provider 協定**：`runtime_checkable` 的 `Provider`
  三能力面 `generate_text` / `generate_image` / `tts`；`register_provider(p)` 登記、
  `get_provider(name)` 取實作、`provider_for_role(role)` 把 `resolve()` 出來的 provider
  名換成實作 + model id。**B 階段只要新增一個實作此協定的 class + `register_provider()`，
  呼叫端零改動即生效**（M-4 docstring 明寫的擴充點）。
- **`core/settings.py`（M-3）逐角色設定 `model_roles`**：設定頁能逐角色覆寫 model id，
  `resolve()` 最高優先讀它。**但目前只覆寫 model id、不覆寫 provider**（A 階段沒有第二個
  provider 可選）——這是 F9-3 要補的最後一塊。

### 本機模型已有實證路徑（不是從零開始）

`core/translate.py` **已內建 Ollama 後端**（`TRANSLATION_BACKEND=ollama`）：

- 標準庫 `urllib` 打 `http://localhost:11434/api/generate`（**零 pip 依賴**，host 走
  `OLLAMA_HOST` env），`ollama pull translategemma` 即可本機翻譯。
- 失敗丟 `TranslateError`，訊息指引「確認 `ollama serve` 已跑且已 `ollama pull <model>`」。

也就是說「打 Ollama 拿文字」這條線**已經驗過、在跑**——F9-3 的工作不是發明它，而是把它
**收斂進 provider 協定**，讓**所有文字角色**（不只翻譯）都能選本機，並讓設定頁能選。

---

## 設計目標

按優先序：

1. **零摩擦 slot-in**：M-4 已留座位，新增 `OllamaProvider` 不該動任何現有呼叫端。
   呼叫端只認 `resolve(role)` → provider，換 provider = 改登錄表/設定頁一個值。
2. **offline-first / 自架友善**：本機 provider **完全不打雲端、不燒額度**。這是
   F9-3 的賣點本身（與硬規則 #3 同向，不是違反）。介面/adapter/mock 測可純 offline 做。
3. **自動退雲端（graceful fallback）**：本機服務沒開 / 模型沒 pull / 逾時 → 可**自動退
   回 Gemini**（若有 key），而不是整個 pipeline 崩。退場行為要可設定、要在 log 講清楚。
4. **不寫死 id、不繞既有紀律**：走 `core/models.py::resolve()`；type guard 擋未知 provider
   （M-4 `get_provider` 已 `ValueError`）；config 集中（host/開關走 `core/config.py`）。
5. **品質誠實**：本機小模型**品質會落差**（尤其解題/長推理）。預設**只對低風險角色**開放
   本機，高風險角色（解題 `text.pro`）預設仍雲端，並在文件/設定頁標清楚。

---

## 哪些角色適合跑本機（品質落差評估）

> 原則：**用量大 × 容錯高 × 形式單純** 的角色先支援本機；**正確性關鍵 × 長推理**的角色
> 預設留雲端（自架者可自行覆寫，但要被警告）。

| 角色 | 適合本機？ | 理由 / 品質落差 |
|------|-----------|----------------|
| `text.fast`（翻譯） | ✅ **首選** | 已用 translategemma 驗過；narration/bullet 級短文，容錯高、用量大。 |
| `text.fast`（旁白生成） | 🟡 條件式 | 用量大、適合省雲端，但旁白語感本機模型可能生硬 → 要實測（接 C-3 的品質驗證精神）。 |
| `text.fast`（大綱 outline） | 🟡 條件式 | 結構化輸出，本機中型模型多半可勝任，需驗格式穩定度。 |
| `text.pro`（**解題** solve） | 🔴 **預設留雲端** | **正確性關鍵**——錯了會被 reviewer 攔（review gate），但本機模型誤答率高會把 reviewer 淹沒。預設不開本機。 |
| `vision`（讀題/OCR/投影片） | 🔴 **預設留雲端** | 多模態本機模型（llava 等）品質/設定門檻高，**先不納入本 RFC 範圍**。 |
| `image.*`（生圖） | 🔴 **不納入** | 本機生圖（SD/Flux）是另一套重型子系統，超出 F9-3「文字角色」範圍。 |
| `tts` | ➖ **已是本機可選** | TTS 走獨立 `tts_backend` 子系統（`edge`/`f5`/`google`），F5-TTS 本就本機；不在 LLM provider registry，本 RFC 不重複處理。 |

**結論**：F9-3 第一階段聚焦 **`text.fast` 的本機支援**（翻譯 → 旁白 → 大綱，由穩到險逐步
放開），`text.pro` / `vision` / `image.*` 預設留雲端。這讓「零雲端成本自架」對**最大宗、
最容錯**的用量先成立，同時不拿解題正確性冒險。

---

## 架構：OllamaProvider 怎麼 slot-in

```
              caller（scriptor / outliner / translate / …）
                         │ 只認邏輯角色
                         ▼
        core.models.resolve("text.fast")  →  (provider_name, model_id)
                         │                         │
        provider_name = "ollama"（設定頁/登錄表指定）│
                         ▼                         ▼
        core.providers.get_provider("ollama")   model_id = "translategemma" / "qwen2.5" …
                         │
                         ▼
        OllamaProvider.generate_text(prompt, model=model_id)
                         │  打 localhost:11434/api/generate（沿用 translate.py 的 urllib 路徑）
                         │  失敗 → graceful fallback → GeminiProvider（若有 key + 開關開）
                         ▼
                      文字結果
```

**關鍵設計選擇**：

- **新增 `core/providers.py::OllamaProvider`**（實作 `Provider` 協定）：
  - `generate_text`：把 `core/translate.py::_call_ollama` 的 urllib 呼叫**抽成共用**
    （單一真實來源，translate 與 provider 共用一條 Ollama 線），不重複實作。`generate_image`
    / `tts` → `NotImplementedError`（本機生圖/語音各有專屬子系統，不混進來）。
  - `register_provider(OllamaProvider())`（A 階段只登 gemini，B 階段加這行）。
- **`core/models.py` 加 provider 常數 `PROVIDER_OLLAMA`**：`DEFAULTS` 維持雲端（不改現況
  預設），由**設定頁 `model_roles`**或 env 把特定角色指到 ollama。
- **設定頁 `model_roles` 升級成可帶 provider**：目前只覆寫 model id；F9-3 讓它能寫
  `{"text.fast": {"provider": "ollama", "model": "translategemma"}}`（或沿用扁平字串 +
  另一個 provider 對照）。`resolve()` 解析時若 override 帶 provider，回該 provider 名。
  **向後相容**：舊扁平 `model_roles[role] = "id-string"` 仍只覆 model id、provider 沿用預設。
- **自動退雲端**：provider 層或呼叫端包一層「本機失敗 → 若 `GEMINI_API_KEY` 在且
  `LOCAL_MODEL_FALLBACK` 開 → 改走 GeminiProvider」，並 `log.warning` 講清楚退場原因。
  退場行為走 config 開關（預設**開**：本機掛了不該整批崩；自架者可關成嚴格本機）。
- **config 集中**（硬規則 #6）：`OLLAMA_HOST`（沿用既有）、`LOCAL_MODEL_FALLBACK`、
  逾時等走 `core/config.py` helper，不散落。

---

## 拆子任務（offline / GATE 標記）

> 一刀一 PR、≤3~5 檔、動 server/core 跑 pytest（硬規則 #7）。

| # | 子任務 | 類型 | 說明 |
|---|--------|------|------|
| F9-3a | 抽 `core/translate.py::_call_ollama` 的 urllib 呼叫成共用本機文字呼叫 helper | **offline** | 純重構 + 既有 translate 測試不變；單一真實來源，translate 與 provider 共用。 |
| F9-3b | `core/providers.py::OllamaProvider`（實作 `Provider`，`generate_text` 走 helper、生圖/tts `NotImplementedError`）+ `PROVIDER_OLLAMA` 常數 + **mock 測** | **offline** | monkeypatch urllib，不需真 ollama；協定符合測、未知 provider type guard 沿用 M-4。 |
| F9-3c | `model_roles` 支援逐角色帶 provider（向後相容扁平字串）+ `resolve()` 解析 provider override | **offline** | 動 `core/models.py` / `core/settings.py` 跑 pytest；schema 寬鬆相容（`extra` 沿用）。 |
| F9-3d | 自動退雲端：本機失敗 → fallback Gemini（config 開關 + log）+ 測 | **offline** | mock「本機拋錯」驗退場走 Gemini / 開關關時嚴格拋；不打真 API。 |
| F9-3e | 設定頁前端：逐角色 provider 下拉（雲端 Gemini / 本機 Ollama）+ 本機 model 欄 | **offline** | `frontend/edustudio/app.jsx`，build 為準、人後視覺驗收。 |
| F9-3f | **品質落差實測**：本機 translategemma / qwen 等對旁白·大綱·解題的品質 A/B vs Gemini | **GATE** | 要本機跑 ollama（拉模型、產樣本對比），定「哪些角色預設可開本機」。需你的環境實跑。 |

**建議推進序**：F9-3a → F9-3b 先把 `OllamaProvider` 座位坐進去（純 offline，mock 測，
**不改任何現有呼叫端行為**）；F9-3c → F9-3d 讓設定能指角色到本機 + 安全退場；F9-3e 上
設定頁 UI；**F9-3f 等你本機實跑**定預設策略。a~e 全程 offline（mock 測、不需真 ollama），
只有 f（品質實測、定預設）需要你的環境。

---

## 開放問題（待劉老師拍板）

1. **第一階段範圍**：先只支援 `text.fast`（翻譯/旁白/大綱）跑本機，`text.pro`(解題) /
   `vision` 預設留雲端對嗎？建議：**是**——容錯高的先放、正確性關鍵的留雲端。
2. **`model_roles` provider 表示法**：升級成 `{role: {"provider":..., "model":...}}` 巢狀
   物件，還是另開一張 `model_providers` 對照表、`model_roles` 維持扁平 model id？建議：
   **巢狀**（一處看完角色完整指派），向後相容扁平字串。需你定（碰 settings schema 形狀）。
3. **自動退雲端預設**：本機掛了**預設自動退 Gemini**（要有 key），還是**預設嚴格本機**
   （沒 key 就明確報錯、絕不偷偷上雲燒額度）？建議：**預設退雲端 + log 大聲講**，但給
   `LOCAL_MODEL_FALLBACK=0` 關成嚴格本機（隱私/離線場景）。這影響「會不會意外燒額度」，
   要你拍板。
4. **推薦本機模型清單**：除了 translategemma（翻譯專用），旁白/大綱推薦哪些通用本機模型
   （qwen2.5 / llama3.x / gemma2…）寫進文件？需 F9-3f 實測定。
5. **provider 抽象要不要也收 vision/image**：本 RFC 刻意只做文字。本機多模態/生圖要不要
   納入後續（另開 RFC），還是明確不做？建議：**本 RFC 不做**，留 F9-3 後續或獨立項。

---

## 不可妥協紀律（本功能自我約束）

- **offline-first**：本機 provider 不打雲端（賣點本身）；adapter/介面/mock 測純 offline；
  **品質實測（F9-3f）打本機 ollama、定預設策略 = GATE，需你的環境**。
- **不寫死 id / provider**：走 `core/models.py::resolve()`（M 軸）；未知 provider →
  `ValueError`（M-4 type guard）。
- **自動退雲端要誠實**：偷偷上雲會讓自架者意外燒額度——退場一律 `log.warning` 講清楚，
  且可關成嚴格本機。
- **不繞 review gate**：本功能只換「誰來生文字」，**不碰 R-2 reviewed assert / 狀態機 /
  render 入口**（硬規則 #1 完全不動）。本機模型答錯一樣被 reviewer 攔。
- **config 集中 / type guard / 別 commit 機密**——比照既有紀律。
- **動 server/core/models/settings 跑 `pytest tests/`**（硬規則 #7）。

---

## 不納入（避免範圍蔓延）

- **本機多模態（vision）/ 本機生圖（SD/Flux）**：超出「文字角色」範圍，本 RFC 明確不做。
- **解題 `text.pro` 預設改本機**：正確性關鍵，預設留雲端（自架者可覆寫但被警告）。
- **TTS provider**：已走獨立 `tts_backend`（F5 本就本機），不在 LLM provider registry 重做。
- **模型自動下載/管理 UI**：`ollama pull` 是使用者一次性動作，本 RFC 只在錯誤訊息指引，
  不做 in-app 模型管理。
</content>
</invoke>
