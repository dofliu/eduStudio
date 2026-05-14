# math-typography · 數學公式排版

公式頁製作前讀一次。

---

## 策略選擇

| 情境 | 建議方式 |
|---|---|
| 簡單分數、上下標 | Unicode 直接輸入（±、²、→、∞、∫、Σ） |
| 複雜公式（傳遞函數、積分式） | LaTeX PNG 嵌入 |
| 矩陣、state-space | LaTeX PNG 嵌入 |

---

## 方式 A：Unicode 符號（簡單公式）

```javascript
// 直接在 addText 裡使用 Unicode
slide.addText("G(s) = Kp · (1 + 1/Ti·s + Td·s)", {
  x: 0.83, y: 2.00, w: 11.67, h: 0.60,
  fontFace: "Georgia", fontSize: 28,
  color: "1E1A14",
});

// 常用符號
// ± · × ÷ → ← ↑ ↓
// ∞ ∫ ∑ ∏ √ ∂ Δ
// ≤ ≥ ≠ ≈ ∝
// α β γ δ ε ζ θ λ μ ξ π ρ σ τ φ ω
// Α Β Γ Δ Θ Λ Π Σ Φ Ω
```

---

## 方式 B：LaTeX PNG 嵌入

### 生成指令

```bash
python scripts/latex_equation.py \
  --name "pid_transfer" \
  --latex "C(s) = K_p\left(1 + \frac{1}{T_i s} + T_d s\right)" \
  --fontsize 32 \
  --width 10
```

生成後存於 `img/equations/pid_transfer.png`

### 嵌入投影片（關鍵：高度固定，寬度依比例）

```javascript
// 1. 先量測 PNG 的實際像素尺寸
// 2. 計算比例：ratio = width_px / height_px
// 3. 固定高度（吋），計算寬度

const imgH = 1.20;        // 固定高度（吋）
const ratio = 4.0;        // 單行公式約 4:1，含分數約 2.5:1
const imgW = imgH * ratio;
const centerX = 0.83 + (11.67 - imgW) / 2;

slide.addImage({
  path: "img/equations/pid_transfer.png",
  x: centerX, y: 2.20,
  w: imgW, h: imgH,
});
```

### 長寬比參考

| 公式類型 | 典型比例 |
|---|---|
| 單行（無分數） | 4.0 : 1 |
| 含分數 | 2.5 : 1 |
| 矩陣（2×2） | 1.2 : 1 |
| 矩陣（3×3） | 1.0 : 1 |
| state-space 組合式 | 2.0 : 1 |

---

## 常見錯誤

| 錯誤 | 後果 | 修正 |
|---|---|---|
| 同時指定 w 和 h（不保持比例） | 公式水平扭曲 | 固定 h，用比例算 w |
| 用純白底生成 PNG | 在米白背景上有白框 | 生成時用透明底（`transparent=True`） |
| 字級過小（fontsize < 28） | PNG 放大後模糊 | 使用 28–36 生成 |
