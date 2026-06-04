# LaTeX 公式渲染提案 — GATE (新 dep, 等用戶決定)

> **寫於 2026-06-04**, hourly routine 恢復自主推進。STATUS.yaml 推進順序把
> 「LaTeX 公式渲染 (offline, 下輪)」列為 V2 執行包 + YouTube 自動章節之後的
> 下一項, 並註明走「matplotlib mathtext / MathJax→PNG 接 slide_renderer
> 圖片路徑」。
>
> **routine 進場查證後發現這項實際上卡在「新 pip dep」GATE** — 不是
> offline 可自主做的。本檔說明卡在哪、選項 trade-off、建議, 等劉老師拍板
> 後 routine 才接著做 (跟 V2 / SONG 同樣 GATE 模式)。

---

## 為什麼是 GATE (不是 offline)

STATUS 假設 matplotlib 可用, 但查證:

- matplotlib **不在** `requirements.txt` / `requirements-optional.txt` / CI。
- CI (`.github/workflows/test.yml:70`) 明列安裝清單:
  `fastapi uvicorn pydantic python-multipart httpx beautifulsoup4 Pillow
  fonttools mutagen qrcode pymupdf` + `requirements-dev.txt` — **無 matplotlib**。
- 既有用到 matplotlib 的 `core/diagram_gen.py` / `diagram_image_gen.py` 是
  **GATE 功能** (Gemini 產 code → subprocess exec), matplotlib 是 lazy import
  在 subprocess 內, 對應測試在 CI 無 matplotlib 時 skip → 所以 matplotlib
  目前是「optional / GATE」級依賴, 不是核心 runtime dep。

→ 把 LaTeX 公式渲染接進 **主線 slide render 路徑**, 等於把 matplotlib
(或別的 LaTeX→PNG lib) 升成**必裝的核心依賴** (要進 requirements.txt + CI
安裝清單), 才能讓 CI 4 組 matrix 通過。這命中 routine STOP 清單「不加新
pip dep / 新 dep 也 STOP」。

---

## 渲染後端選項 (要先選一個)

| 選項 | dep 變動 | 數學覆蓋 | CJK 混排 | 風險 |
|---|---|---|---|---|
| **A. matplotlib mathtext** | matplotlib 升為核心 dep (~30MB+numpy) | mathtext 子集 (非完整 LaTeX, 無 `\begin{align}` 等環境) | mathtext 內中文要設 font, 公式內純符號通常夠 | 本機已有, 但 CI/部署都要裝; matplotlibrc 字型警告要處理 |
| **B. matplotlib usetex=True** | matplotlib + **系統裝 TeX Live** | 完整 LaTeX | 好 | 要系統級 TeX (~幾 GB), Docker/CI 都要裝, 過重 |
| **C. Pillow 自繪** | 0 新 dep | 幾乎做不到 (上下標/分數/根號/積分全要自刻) | — | 工程量爆炸, 不切實際 |
| **D. 預渲染服務 (CodeCogs / QuickLaTeX API)** | 0 pip dep, 但**線上 API** | 完整 | 好 | 違反 offline-first; 渲染要連外, 課程教材送第三方 |

**routine 建議: 選 A (matplotlib mathtext)**, 理由:

- 材力公式 (應力 σ=F/A、彎矩 M、慣性矩 I、撓度 δ) 多半是分數 / 上下標 /
  希臘字母 / 根號 — mathtext 子集涵蓋得了, 不需完整 LaTeX 環境。
- 本機已裝 matplotlib 3.9.2, 升核心 dep 只是把它寫進 requirements + CI 清單。
- 純 offline (mathtext 不連外, 跟 D 不同)。
- 完整 LaTeX (B) 的 TeX Live 對 Docker image / CI 太重, 暫不值得。

> 若劉老師日後要 `\begin{cases}` / 矩陣 / 對齊環境等 mathtext 子集做不到的,
> 再評估升 B。先 A 覆蓋 8 成材力公式需求。

---

## 要劉老師做什麼 (GATE 解鎖)

1. **拍板渲染後端** (建議 A)。
2. **同意 matplotlib 進核心依賴**:
   - `requirements.txt` 加 `matplotlib>=3.7`。
   - CI `.github/workflows/test.yml:70` 安裝清單加 `matplotlib`。
   - (這步是 routine 不能自主做的 — 改 CI / 加核心 dep 屬架構決策。)
3. 解鎖後 routine 可自主接著做 offline 實作 (見下「解鎖後 routine 做什麼」)。

---

## 解鎖後 routine 做什麼 (offline, 已可規劃)

接 slide 既有圖片疊放路徑 (`slide.icon_overlay` / `slide.image_frames` 已
透過 `core/deck.py` 透傳進三大 renderer), 不另開新渲染管線:

1. **新模組 `core/formula_render.py`**:
   `render_latex_to_png(latex: str, out_path, *, dpi, color) -> bool` —
   matplotlib `Agg` backend + `mathtext`, `figure.text(0,0, f"${latex}$")` →
   `savefig(transparent=True, bbox_inches='tight')`。失敗回 False 不炸 pipeline
   (跟 icon_overlay 單筆失敗靜默 skip 同契約)。
2. **schema 加 `slide.formula`** (`core/deck.py` 透傳, 跟 icon_overlay/image_frames
   同 pattern, type guard 不硬判 key)。
3. **renderer 接 formula→PNG→疊放** (沿用 alpha_composite 既有位置/字幕帶邏輯)。
4. **tests**: mathtext 渲出非空 PNG / 壞 LaTeX 回 False 不炸 / 透明背景 /
   CJK 字型 fallback。**CI 要先有 matplotlib 才能跑** — 所以第 2 步 (CI 加 dep)
   是前置。

> require_review 不可繞: formula 字串若由 Gemini 產 (未來 auto-formula), 一樣
> 停 awaiting_review 人工確認 — AI 產的公式不能未 review 當最終答案 (硬規則 #1)。

---

## 驗收

- [ ] CI 4 組 matrix (含新 matplotlib) 全綠。
- [ ] 一個含 `\sigma = \frac{F}{A}` 的測試 slide 渲出公式 PNG 疊在 slide 上,
      不擋字幕帶, 中文標題 + 公式混排正常。
- [ ] 壞 LaTeX (`\frac{`) 不炸 render, 該 slide 退無公式正常產出。

---

## STOP 理由 (給 routine 紀錄)

LaTeX 公式渲染的每條可行路徑都需要新 pip dep (A/B matplotlib, C 不可行,
D 違反 offline-first) → 命中 STOP 清單「不加新 pip dep / 新 dep 也 STOP」+
「改 CI 安裝清單屬架構決策」。routine 不自主加, 寫本提案 STOP 等劉老師
拍板後端 + 同意 matplotlib 進核心依賴。
